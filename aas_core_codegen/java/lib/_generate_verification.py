"""Generate code of verification logic."""

import io
import textwrap
from typing import (
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from icontract import ensure, require

from aas_core_codegen import (
    intermediate,
    specific_implementations,
)
from aas_core_codegen.common import (
    assert_never,
    Error,
    indent_but_first_line,
    Identifier,
    Stripped,
    wrap_text_into_lines,
)
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.java import (
    common as java_common,
    description as java_description,
    optional as java_optional,
    naming as java_naming,
    transpilation as java_transpilation,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)
from aas_core_codegen.parse import tree as parse_tree, retree as parse_retree


# region Verify


def verify(
    spec_impls: specific_implementations.SpecificImplementations,
    verification_functions: Sequence[intermediate.Verification],
) -> Optional[List[str]]:
    """Verify all the implementation snippets related to verification."""
    errors = []  # type: List[str]

    expected_keys = []  # type: List[specific_implementations.ImplementationKey]

    for func in verification_functions:
        if isinstance(func, intermediate.ImplementationSpecificVerification):
            expected_keys.append(
                specific_implementations.ImplementationKey(
                    f"Verification/{func.name}.java"
                ),
            )

    for key in expected_keys:
        if key not in spec_impls:
            errors.append(f"The implementation snippet is missing for: {key}")

    if len(errors) == 0:
        return None

    return errors


# endregion

# region Generate


class RegexRenderer(parse_retree.Renderer):
    """
    Render the regular expressions for Java.

    """

    def char_to_str_and_escape_or_encode_if_necessary(
        self, node: parse_retree.Char, escaping: Mapping[str, str]
    ) -> List[Union[str, parse_tree.FormattedValue]]:
        if not node.explicitly_encoded:
            escaped = escaping.get(node.character, None)
            if escaped is not None:
                result: List[Union[str, parse_tree.FormattedValue]] = [escaped]
            else:
                result = [node.character]

            return result

        else:
            code = ord(node.character)
            return [f"\\x{{{code:02x}}}"]


_REGEX_RENDERER = RegexRenderer()


class _PatternVerificationTranspiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a statement of a pattern verification into Java."""

    def __init__(self, defined_variables: Set[Identifier]) -> None:
        """
        Initialize with the given values.

        The ``defined_variables`` are shared between different statement
        transpilations. It is also mutated when assignments are transpiled. We need to
        keep track of variables so that we know when we have to define them, and when
        we can simply assign them a value, if they have been already defined.
        """
        self.defined_variables = defined_variables

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_joined_str_values(
        self, values: Sequence[Union[str, parse_tree.FormattedValue]]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Transform the values of a joined string to a Java string literal."""
        if all(isinstance(value, str) for value in values):
            return (
                Stripped(java_common.string_literal("".join(values))),  # type: ignore
                None,
            )

        parts = []  # type: List[str]
        for value in values:
            if isinstance(value, str):
                string_literal = java_common.string_literal(value)

                assert string_literal.startswith('"') and string_literal.endswith('"')

                parts.append(string_literal)

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self.transform(value.value)
                if error is not None:
                    return None, error
                assert code is not None

                assert (
                    "\n" not in code
                ), f"New-lines are not expected in formatted values, but got: {code}"

                parts.append(f"{code}")
            else:
                assert_never(value)

        return Stripped(" + ".join(parts)), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if isinstance(node.value, str):
            regex, parse_error = parse_retree.parse(values=[node.value])
            if parse_error is not None:
                regex_line, pointer_line = parse_retree.render_pointer(
                    parse_error.cursor
                )

                return (
                    None,
                    Error(
                        node.original_node,
                        f"The string constant could not be parsed "
                        f"as a regular expression: \n"
                        f"{parse_error.message}\n"
                        f"{regex_line}\n"
                        f"{pointer_line}",
                    ),
                )

            assert regex is not None

            return self._transform_joined_str_values(
                values=parse_retree.render(regex=regex, renderer=_REGEX_RENDERER)
            )
        else:
            raise AssertionError(f"Unexpected {node=}")

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return Stripped(java_naming.variable_name(node.identifier)), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_joined_str(
        self, node: parse_tree.JoinedStr
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        regex, parse_error = parse_retree.parse(values=node.values)
        if parse_error is not None:
            regex_line, pointer_line = parse_retree.render_pointer(parse_error.cursor)

            return (
                None,
                Error(
                    node.original_node,
                    f"The joined string could not be parsed "
                    f"as a regular expression: \n"
                    f"{parse_error.message}\n"
                    f"{regex_line}\n"
                    f"{pointer_line}",
                ),
            )

        assert regex is not None

        return self._transform_joined_str_values(
            values=parse_retree.render(regex=regex, renderer=_REGEX_RENDERER)
        )

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        assert isinstance(node.target, parse_tree.Name)
        variable = java_naming.variable_name(node.target.identifier)
        code, error = self.transform(node.value)
        if error is not None:
            return None, error
        assert code is not None

        if node.target.identifier in self.defined_variables:
            return Stripped(f"{variable} = {code};"), None

        else:
            self.defined_variables.add(node.target.identifier)

            # NOTE (mristin):
            # We assume here that we checked in the parse stage that all the variables
            # used in a pattern verification function are actually typed as strings.

            return Stripped(f"String {variable} = {code};"), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_pattern_verification(
    verification: intermediate.PatternVerification,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the verification function that checks the regular expressions."""
    # We assume that we performed all the checks at the intermediate stage.

    construct_name = java_naming.private_method_name(
        Identifier(f"construct_{verification.name}")
    )

    blocks = []  # type: List[Stripped]

    # region Construct block

    writer = io.StringIO()
    writer.write(
        f"""\
private static Pattern {construct_name}() {{
"""
    )

    defined_variables = set()  # type: Set[Identifier]
    transpiler = _PatternVerificationTranspiler(defined_variables=defined_variables)

    for i, stmt in enumerate(verification.parsed.body):
        if i == len(verification.parsed.body) - 1:
            break

        code, error = transpiler.transform(stmt)
        if error is not None:
            return None, error
        assert code is not None

        writer.write(textwrap.indent(code, I))
        writer.write("\n")

    if len(verification.parsed.body) >= 2:
        writer.write("\n")

    pattern_expr, error = transpiler.transform(verification.pattern_expr)
    if error is not None:
        return None, error
    assert pattern_expr is not None

    # A pragmatic heuristics for breaking lines
    if len(pattern_expr) < 50:
        writer.write(textwrap.indent(f"return Pattern.compile({pattern_expr});\n", I))
    else:
        writer.write(
            textwrap.indent(f"return Pattern.compile(\n{I}{pattern_expr});\n", I)
        )

    writer.write("}")

    blocks.append(Stripped(writer.getvalue()))

    # endregion

    # region Initialize the regex

    regex_name = java_naming.property_name(Identifier(f"regex_{verification.name}"))

    blocks.append(
        Stripped(f"private static final Pattern {regex_name} = {construct_name}();")
    )

    assert len(verification.arguments) == 1
    assert isinstance(
        verification.arguments[0].type_annotation, intermediate.PrimitiveTypeAnnotation
    )
    # noinspection PyUnresolvedReferences
    assert (
        verification.arguments[0].type_annotation.a_type
        == intermediate.PrimitiveType.STR
    )

    arg_name = java_naming.argument_name(verification.arguments[0].name)

    writer = io.StringIO()
    if verification.description is not None:
        comment, comment_errors = java_description.generate_comment_for_signature(
            verification.description,
            context=java_description.Context(package=package, cls_or_enum=None),
        )
        if comment_errors is not None:
            return None, Error(
                verification.description.parsed.node,
                "Failed to generate the documentation comment",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    method_name = java_naming.method_name(verification.name)

    writer.write(
        f"""\
public static Boolean {method_name}(String {arg_name}) {{
{I}return {regex_name}.matcher({arg_name}).matches();
}}"""
    )

    blocks.append(Stripped(writer.getvalue()))

    # endregion

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    return Stripped(writer.getvalue()), None


class _TranspilableVerificationTranspiler(java_transpilation.Transpiler):
    """Transpile the body of a :class:`.TranspilableVerification`."""

    # fmt: off
    @require(
        lambda environment, verification:
        all(
            environment.find(arg.name) is not None
            for arg in verification.arguments
        ),
        "All arguments defined in the environment"
    )
    # fmt: on
    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        is_optional_map: Mapping[
            parse_tree.Node,
            bool,
        ],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
    ) -> None:
        """Initialize with the given values."""
        java_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            optional_map=is_optional_map,
            environment=environment,
        )

        self._symbol_table = symbol_table

        self._argument_name_set = frozenset(arg.name for arg in verification.arguments)

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(java_naming.variable_name(node.identifier)), None

        if node.identifier in self._argument_name_set:
            return Stripped(java_naming.variable_name(node.identifier)), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_as_prop = java_naming.property_name(node.identifier)
            return Stripped(f"Constants.{constant_as_prop}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(java_naming.method_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(java_naming.enum_name(node.identifier)), None

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to Java. We could not find it neither in the constants, nor in "
            f"verification functions, nor as an enumeration. "
            f"If you expect this name to be transpilable, please contact "
            f"the developers.",
        )


def _transpile_transpilable_verification(
    verification: intermediate.TranspilableVerification,
    symbol_table: intermediate.SymbolTable,
    environment: intermediate_type_inference.Environment,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Transpile a verification function.

    The ``package`` defines the root Java package.
    """
    # fmt: off
    type_inference, error = (
        intermediate_type_inference.infer_for_verification(
            verification=verification,
            base_environment=environment
        )
    )
    # fmt: on

    if error is not None:
        return None, error

    assert type_inference is not None

    optional_inferrer = java_optional.OptionalInferrer(
        environment=type_inference.environment_with_args,
        type_map=type_inference.type_map,
    )

    for node in verification.parsed.body:
        _ = optional_inferrer.transform(node)

    if len(optional_inferrer.errors):
        return None, Error(
            verification.parsed.node,
            f"Failed to infer whether types are "
            f"optional in verification function {verification.name!r}",
            optional_inferrer.errors,
        )

    transpiler = _TranspilableVerificationTranspiler(
        type_map=type_inference.type_map,
        is_optional_map=optional_inferrer.is_optional_map,
        environment=type_inference.environment_with_args,
        symbol_table=symbol_table,
        verification=verification,
    )

    body = []  # type: List[Stripped]
    for node in verification.parsed.body:
        stmt, error = transpiler.transform(node)
        if error is not None:
            return None, Error(
                verification.parsed.node,
                f"Failed to transpile the verification function {verification.name!r}",
                [error],
            )

        assert stmt is not None
        body.append(stmt)

    writer = io.StringIO()
    if verification.description is not None:
        comment, comment_errors = java_description.generate_comment_for_signature(
            description=verification.description,
            context=java_description.Context(package=package, cls_or_enum=None),
        )
        if comment_errors is not None:
            return None, Error(
                verification.description.parsed.node,
                "Failed to generate the documentation comment",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    method_name = java_naming.method_name(verification.name)

    if verification.returns is None:
        return_type = "void"
    else:
        return_type = java_common.generate_type(type_annotation=verification.returns)

    arg_defs = []  # type: List[Stripped]
    for arg in verification.arguments:
        arg_type = java_common.generate_type(arg.type_annotation)
        arg_name = java_naming.argument_name(arg.name)
        arg_defs.append(Stripped(f"{arg_type} {arg_name}"))

    if len(arg_defs) == 0:
        writer.write(
            f"""\
public static {return_type} {method_name}() {{"""
        )
    else:
        writer.write(
            f"""\
public static {return_type} {method_name}(
"""
        )

        for i, arg_def in enumerate(arg_defs):
            if i > 0:
                writer.write(",\n")
            writer.write(textwrap.indent(arg_def, I))

        writer.write(") {")

    for stmt in body:
        writer.write("\n")
        writer.write(textwrap.indent(stmt, I))

    if len(body) > 0:
        writer.write("\n")

    writer.write("}")

    return Stripped(writer.getvalue()), None


def _generate_enum_value_sets(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate a class that pre-computes the sets of allowed enumeration literals."""
    blocks = []  # type: List[Stripped]

    for enum in symbol_table.enumerations:
        enum_name = java_naming.enum_name(enum.name)

        if len(enum.literals) == 0:
            blocks.append(
                Stripped(
                    f"""\
private static final Set<{enum_name}> for{enum_name} = new HashSet<>();"""
                )
            )
        else:
            hash_init_writer = io.StringIO()

            for i, literal in enumerate(enum.literals):
                literal_name = java_naming.enum_literal_name(literal.name)
                hash_init_writer.write(f"temp.add({enum_name}.{literal_name});\n")

            hash_init_body = hash_init_writer.getvalue()

            blocks.append(
                Stripped(
                    f"""\
private static final Set<{enum_name}> for{enum_name};
static {{
{I}final Set<{enum_name}> temp = new HashSet<>();

{I}{indent_but_first_line(hash_init_body, I)}

{I}if (!temp.containsAll(Arrays.asList({enum_name}.values()))) {{
{II}throw new IllegalStateException("Uncovered {enum_name}");
{I}}}

{I}for{enum_name} = Collections.unmodifiableSet(temp);
}}"""
                )
            )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Hash allowed enum values for efficient validation of enums.
 */
private static class _EnumValueSet {
"""
    )
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


class _InvariantTranspiler(java_transpilation.Transpiler):
    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        is_optional_map: Mapping[
            parse_tree.Node,
            bool,
        ],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
    ) -> None:
        """Initialize with the given values."""
        java_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            optional_map=is_optional_map,
            environment=environment,
        )

        self._symbol_table = symbol_table

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(java_naming.variable_name(node.identifier)), None

        if node.identifier == "self":
            # The ``that`` refers to the argument of the verification function.
            return Stripped("that"), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_as_prop = java_naming.property_name(node.identifier)
            return Stripped(f"Constants.{constant_as_prop}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(java_naming.method_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(java_naming.enum_name(node.identifier)), None

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to Java. We could not find it "
            f"neither in the local variables, "
            f"nor in the global constants, "
            f"nor in verification functions, "
            f"nor as an enumeration. "
            f"If you expect this name to be transpilable, please contact "
            f"the developers.",
        )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_invariant(
    invariant: intermediate.Invariant,
    symbol_table: intermediate.SymbolTable,
    environment: intermediate_type_inference.Environment,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Translate the invariant from the meta-model into C# code."""
    # fmt: off
    type_map, inference_error = (
        intermediate_type_inference.infer_for_invariant(
            invariant=invariant,
            environment=environment
        )
    )
    # fmt: on

    if inference_error is not None:
        return None, inference_error

    assert type_map is not None

    optional_inferrer = java_optional.OptionalInferrer(
        environment=environment,
        type_map=type_map,
    )

    _ = optional_inferrer.transform(invariant.body)

    if len(optional_inferrer.errors):
        return None, Error(
            invariant.parsed.node,
            "Failed to infer whether types are optional in the invariant",
            optional_inferrer.errors,
        )

    transpiler = _InvariantTranspiler(
        type_map=type_map,
        is_optional_map=optional_inferrer.is_optional_map,
        environment=environment,
        symbol_table=symbol_table,
    )

    expr, error = transpiler.transform(invariant.parsed.body)
    if error is not None:
        return None, error

    assert expr is not None

    writer = io.StringIO()
    if len(expr) > 50 or "\n" in expr:
        writer.write("if (!(\n")
        writer.write(textwrap.indent(expr, I))
        writer.write(")) {\n")
    else:
        no_parenthesis_type_in_this_context = (
            parse_tree.Name,
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
        )

        if isinstance(invariant.parsed.body, no_parenthesis_type_in_this_context):
            not_expr = f"!{expr}"
        else:
            not_expr = f"!({expr})"

        writer.write(f"if ({not_expr}) {{\n")

    writer.write(
        textwrap.indent(
            f"""\
errorStream = Stream.<Reporting.Error>concat(errorStream,
{I}Stream.of(new Reporting.Error(
{II}"Invariant violated:\\n" +
""",
            I,
        )
    )

    # NOTE (empwilli):
    # We need to wrap the description in multiple literals as a single long
    # string literal is often too much for the readability.
    invariant_description_lines = wrap_text_into_lines(invariant.description)

    for i, literal in enumerate(invariant_description_lines):
        if i < len(invariant_description_lines) - 1:
            writer.write(f"{III}{java_common.string_literal(literal)} +\n")
        else:
            writer.write(f"{III}{java_common.string_literal(literal)})));")

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_verify_method(our_type: intermediate.OurType) -> Stripped:
    """Generate the name of the ``verify*`` method."""
    if isinstance(our_type, intermediate.Enumeration):
        name = java_naming.enum_name(our_type.name)
        return Stripped(f"verify{name}")

    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        name = java_naming.class_name(our_type.name)
        return Stripped(f"verify{name}")

    elif isinstance(our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)):
        return Stripped("verifyToErrorStream")
    else:
        assert_never(our_type)

    raise AssertionError("Unexpected execution path")


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transform_property(
    prop: intermediate.Property,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the snippet to transform a property to errors."""
    # NOTE (empwilli):
    # Instead of writing here a complex but general solution with unrolling we choose
    # to provide a simple, but limited, solution. First, the meta-model is quite
    # limited itself at the moment, so the complexity of the general solution is not
    # warranted. Second, we hope that there will be fewer bugs in the simple solution
    # which is particularly important at this early adoption stage.
    #
    # We anticipate that in the future we will indeed need a general and complex
    # solution. Here are just some thoughts on how to approach it:
    # * Leave the pattern matching to produce more readable code for simple cases,
    # * Unroll only in case of composite types and optional composite types.

    type_anno = (
        prop.type_annotation
        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        else prop.type_annotation.value
    )

    if isinstance(type_anno, intermediate.OptionalTypeAnnotation):
        return None, Error(
            prop.parsed.node,
            "We currently implemented verification based on a very limited "
            "pattern matching due to code simplicity. We did not handle "
            "the case of nested optional values. Please contact "
            "the developers if you need this functionality.",
        )
    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        if isinstance(type_anno.items, intermediate.OptionalTypeAnnotation):
            return None, Error(
                prop.parsed.node,
                "We currently implemented verification based on a very limited "
                "pattern matching due to code simplicity. We did not handle "
                "the case of lists of optional values. Please contact "
                "the developers if you need this functionality.",
            )
        elif isinstance(type_anno.items, intermediate.ListTypeAnnotation):
            return None, Error(
                prop.parsed.node,
                "We currently implemented verification based on a very limited "
                "pattern matching due to code simplicity. We did not handle "
                "the case of lists of lists. Please contact "
                "the developers if you need this functionality.",
            )
        else:
            pass
    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        pass
    else:
        pass

    stmts = []  # type: List[Stripped]

    getter_name = java_naming.getter_name(prop.name)
    prop_literal = java_common.string_literal(prop.json_name)

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        source_expr = Stripped(f"that.{getter_name}().get()")
    else:
        source_expr = Stripped(f"that.{getter_name}()")

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        # There is nothing that we check for primitive types.
        return Stripped(""), None
    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        verify_method = _generate_verify_method(our_type=type_anno.our_type)

        stmts.append(
            Stripped(
                f"""\
errorStream = Stream.<Reporting.Error>concat(errorStream,
{I}Stream.of({source_expr})
{II}.flatMap(Verification::{verify_method})
{III}.map(error -> {{
{IIII}error.prependSegment(
{IIIII}new Reporting.NameSegment({prop_literal}));
{IIII}return error;
{III}}}));"""
            )
        )

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            "We chose to implement only a very limited pattern matching; "
            "see the note above in the code."
        )

        # NOTE (empwilli):
        # We only descend into our classes here.
        if not isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            return Stripped(""), None

        verify_method = _generate_verify_method(type_anno.items.our_type)
        item_type = java_common.generate_type(type_anno.items)

        stmts.append(
            Stripped(
                f"""\
errorStream = Stream.<Reporting.Error>concat(errorStream,
{I}Verification.zip(
{II}IntStream.iterate(0, i -> i + 1).boxed(),
{II}{source_expr}.stream())
{III}.flatMap(elemTuple -> {{
{IIII}final int index = elemTuple.getFirst();
{IIII}final {item_type} elem = elemTuple.getSecond();
{IIII}return Verification.{verify_method}(elem)
{IIIII}.map(error -> {{
{IIIIII}error.prependSegment(new Reporting.IndexSegment(index));
{IIIIII}return error;
{IIIII}}});
{III}}})
{II}.map(error -> {{
{III}error.prependSegment(
{IIII}new Reporting.NameSegment({prop_literal}));
{III}return error;
{II}}}));"""
            )
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        for i, item_type_anno in enumerate(type_anno.items):
            if not isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                # There is nothing that we check for primitive items.
                continue

            verify_method = _generate_verify_method(our_type=item_type_anno.our_type)
            item_expr = Stripped(f"{source_expr}.item{i + 1}()")

            stmts.append(
                Stripped(
                    f"""\
errorStream = Stream.<Reporting.Error>concat(errorStream,
{I}Stream.of({item_expr})
{II}.flatMap(Verification::{verify_method})
{III}.map(error -> {{
{IIII}error.prependSegment(
{IIIII}new Reporting.IndexSegment({i}));
{IIII}error.prependSegment(
{IIIII}new Reporting.NameSegment({prop_literal}));
{IIII}return error;
{III}}}));"""
                )
            )

    else:
        assert_never(type_anno)

    verify_block = Stripped("\n".join(stmts))
    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return (
            Stripped(
                f"""\
if (that.{getter_name}().isPresent()) {{
{I}{indent_but_first_line(verify_block, I)}
}}"""
            ),
            None,
        )
    else:
        return verify_block, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transform_for_class(
    cls: intermediate.ConcreteClass,
    symbol_table: intermediate.SymbolTable,
    base_environment: intermediate_type_inference.Environment,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transform method to errors for the given concrete class."""
    errors = []  # type: List[Error]
    blocks = []  # type: List[Stripped]

    name = java_naming.class_name(cls.name)

    environment = intermediate_type_inference.MutableEnvironment(
        parent=base_environment
    )

    assert environment.find(Identifier("self")) is None
    environment.set(
        identifier=Identifier("self"),
        type_annotation=intermediate_type_inference.OurTypeAnnotation(our_type=cls),
    )

    for invariant in cls.invariants:
        invariant_code, error = _transpile_invariant(
            invariant=invariant, symbol_table=symbol_table, environment=environment
        )
        if error is not None:
            errors.append(
                Error(
                    cls.parsed.node,
                    f"Failed to transpile the invariant of the class {cls.name!r}",
                    [error],
                )
            )
            continue

        assert invariant_code is not None

        blocks.append(invariant_code)

    if len(errors) > 0:
        return None, errors

    for prop in cls.properties:
        block, error = _generate_transform_property(prop=prop)
        if error is not None:
            errors.append(error)
        else:
            assert block is not None
            if block != "":
                blocks.append(block)

    if len(errors) > 0:
        return None, errors

    if len(blocks) == 0:
        blocks.append(
            Stripped(
                f"""\
// No verification has been defined for {name}."""
            )
        )

    writer = io.StringIO()

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    writer.write(
        f"""\
@Override
public Stream<Reporting.Error> {transform_name}(
{I}{interface_name} that) {{
{I}Stream<Reporting.Error> errorStream = Stream.empty();

"""
    )

    for i, stmt in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(stmt, I))

    writer.write("\n\n")
    writer.write(f"{I}return errorStream;")
    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_transformer(
    symbol_table: intermediate.SymbolTable,
    base_environment: intermediate_type_inference.Environment,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a transformer to double-dispatch an instance to errors."""
    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            continue

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            continue

        elif isinstance(our_type, intermediate.AbstractClass):
            # The abstract classes are directly dispatched by the transformer,
            # so we do not need to handle them separately.
            pass

        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                transform_key = specific_implementations.ImplementationKey(
                    f"Verification/transform_{our_type.name}.java"
                )

                implementation = spec_impls.get(transform_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The transformation snippet is missing "
                            f"for the implementation-specific "
                            f"class {our_type.name}: {transform_key}",
                        )
                    )
                    continue

                blocks.append(spec_impls[transform_key])
            else:
                block, cls_errors = _generate_transform_for_class(
                    cls=our_type,
                    symbol_table=symbol_table,
                    base_environment=base_environment,
                )
                if cls_errors is not None:
                    errors.extend(cls_errors)
                else:
                    assert block is not None
                    blocks.append(block)
        else:
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    writer.write(
        """\
private static class _Transformer extends AbstractTransformer<Stream<Reporting.Error>> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_verify_enumeration(enumeration: intermediate.Enumeration) -> Stripped:
    """Generate the verify method to check that an enum is valid."""
    name = java_naming.enum_name(enumeration.name)

    return Stripped(
        f"""\
/**
 * Verify that {{@code that}} is a valid enumeration value.
 */
public static Stream<Reporting.Error> verify{name}(
{I}{name} that) {{
{I}if (!_EnumValueSet.for{name}.contains(that)) {{
{II}return Stream.of(new Reporting.Error(
{III}"Invalid {name}: " + that));
{I}}} else {{
{II}return Stream.empty();
{I}}}
}}"""
    )


def _generate_verify_constrained_primitive(
    constrained_primitive: intermediate.ConstrainedPrimitive,
    symbol_table: intermediate.SymbolTable,
    base_environment: intermediate_type_inference.Environment,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the verify function for the constrained primitives."""
    errors = []  # type: List[Error]
    blocks = []  # type: List[Stripped]

    environment = intermediate_type_inference.MutableEnvironment(
        parent=base_environment
    )

    assert environment.find(Identifier("self")) is None
    environment.set(
        identifier=Identifier("self"),
        type_annotation=intermediate_type_inference.OurTypeAnnotation(
            our_type=constrained_primitive
        ),
    )

    for invariant in constrained_primitive.invariants:
        invariant_code, error = _transpile_invariant(
            invariant=invariant, symbol_table=symbol_table, environment=environment
        )
        if error is not None:
            errors.append(
                Error(
                    constrained_primitive.parsed.node,
                    f"Failed to transpile the invariant of "
                    f"the constrained primitive {constrained_primitive.name!r}",
                    [error],
                )
            )
            continue

        assert invariant_code is not None

        blocks.append(invariant_code)

    if len(errors) > 0:
        return None, errors

    if len(blocks) == 0:
        blocks.append(
            Stripped(
                """\
// There is no verification specified."""
            )
        )

    # NOTE (empwilli):
    # Constrained primitives are not really classes, but we simply use the naming
    # for classes here since we need to pick *something*.
    name = java_naming.class_name(constrained_primitive.name)

    that_type = java_common.PRIMITIVE_TYPE_MAP[constrained_primitive.constrainee]

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Verify the constraints of {{@code that}}.
 */
public static Stream<Reporting.Error> verify{name} (
{I}{that_type} that) {{
{I}Stream<Reporting.Error> errorStream = Stream.empty();

"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n\n")
    writer.write(f"{I}return errorStream;")
    writer.write("\n}")

    assert len(errors) == 0
    return Stripped(writer.getvalue()), None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code of verification logic.
    """

    imports = [
        Stripped("import java.lang.Iterable;"),
        Stripped("import java.math.BigInteger;"),
        Stripped("import java.util.Arrays;"),
        Stripped("import java.util.Collections;"),
        Stripped("import java.util.function.Consumer;"),
        Stripped("import java.util.HashSet;"),
        Stripped("import java.util.Iterator;"),
        Stripped("import java.util.Objects;"),
        Stripped("import java.util.regex.Matcher;"),
        Stripped("import java.util.regex.Pattern;"),
        Stripped("import java.util.Set;"),
        Stripped("import java.util.Spliterator;"),
        Stripped("import java.util.Spliterators;"),
        Stripped("import java.util.stream.IntStream;"),
        Stripped("import java.util.stream.Stream;"),
        Stripped("import java.util.stream.StreamSupport;"),
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.constants.*;"),
        Stripped(f"import {package}.reporting.Reporting;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.AbstractTransformer;"),
    ]  # type: List[Stripped]

    verification_blocks = []  # type: List[Stripped]
    errors = []  # type: List[Error]

    base_environment = intermediate_type_inference.populate_base_environment(
        symbol_table=symbol_table
    )

    for verification in symbol_table.verification_functions:
        if isinstance(verification, intermediate.ImplementationSpecificVerification):
            implementation_key = specific_implementations.ImplementationKey(
                f"Verification/{verification.name}.java"
            )

            implementation = spec_impls.get(implementation_key, None)
            if implementation is None:
                errors.append(
                    Error(
                        None,
                        f"The snippet for the verification function "
                        f"{verification.name!r} is missing: {implementation_key}",
                    )
                )
            else:
                verification_blocks.append(implementation)

        elif isinstance(verification, intermediate.PatternVerification):
            implementation, error = _transpile_pattern_verification(
                verification=verification,
                package=package,
            )

            if error is not None:
                errors.append(error)
            else:
                assert implementation is not None
                verification_blocks.append(implementation)

        elif isinstance(verification, intermediate.TranspilableVerification):
            implementation, error = _transpile_transpilable_verification(
                verification=verification,
                symbol_table=symbol_table,
                environment=base_environment,
                package=package,
            )

            if error is not None:
                errors.append(error)
            else:
                assert implementation is not None
                verification_blocks.append(implementation)

        else:
            assert_never(verification)

    verification_blocks.append(_generate_enum_value_sets(symbol_table=symbol_table))

    verification_blocks.append(
        Stripped(
            """\
private static final _Transformer transformer = new _Transformer();"""
        )
    )

    transformer_block, transformer_errors = _generate_transformer(
        symbol_table=symbol_table,
        base_environment=base_environment,
        spec_impls=spec_impls,
    )
    if transformer_errors is not None:
        errors.extend(transformer_errors)
    else:
        assert transformer_block is not None
        verification_blocks.append(transformer_block)

    verification_blocks.append(
        Stripped(
            f"""\
public static Stream<Reporting.Error> verifyToErrorStream(IClass that) {{
{I}return transformer.transform(that);
}}

private static class _ValidationErrorIterable implements Iterable<Reporting.Error> {{
{I}private final IClass element;

{I}public _ValidationErrorIterable(IClass element) {{
{II}this.element = element;
}}

{I}@Override
{I}public Iterator<Reporting.Error> iterator() {{
{II}Stream<Reporting.Error> stream = stream();

{II}return stream.iterator();
{I}}}

{I}@Override
{I}public void forEach(Consumer<? super Reporting.Error> action) {{
{II}Stream<Reporting.Error> stream = stream();

{II}stream.forEach(action);
{I}}}

{I}@Override
{I}public Spliterator<Reporting.Error> spliterator() {{
{II}Stream<Reporting.Error> stream = stream();

{II}return stream.spliterator();
{I}}}

{I}private Stream<Reporting.Error> stream() {{
{II}return Verification.verifyToErrorStream(element);
{I}}}
}}

/**
 * Verify the constraints of {{@code that}} recursively.
 *
 * @param that The instance of the meta-model to be verified
 */
public static Iterable<Reporting.Error> verify(IClass that) {{
{I}return new _ValidationErrorIterable(that);
}}"""
        )
    )

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            verification_blocks.append(
                _generate_verify_enumeration(enumeration=our_type)
            )
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            (
                constrained_primitive_block,
                constrained_primitive_errors,
            ) = _generate_verify_constrained_primitive(
                constrained_primitive=our_type,
                symbol_table=symbol_table,
                base_environment=base_environment,
            )

            if constrained_primitive_errors is not None:
                errors.extend(constrained_primitive_errors)
            else:
                assert constrained_primitive_block is not None
                verification_blocks.append(constrained_primitive_block)

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # We provide a general dispatch function.
            pass
        else:
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    verification_blocks.append(
        Stripped(
            f"""\
private static class _Pair<A, B> {{
{I}private final A first;
{I}private final B second;

{I}public _Pair(A first, B second) {{
{II}this.first = first;
{II}this.second = second;
{I}}}

{I}public A getFirst() {{
{II}return first;
{I}}}

{I}public B getSecond() {{
{II}return second;
{I}}}
}}

// Java 8 doesn't provide a split operation out of the box, so we have to ship our own.
// Adapted from: https://stackoverflow.com/a/23529010
private static <A, B> Stream<_Pair<A, B>> zip(
{I}Stream<? extends A> a,
{I}Stream<? extends B> b) {{
{I}Spliterator<? extends A> aSplit = Objects.requireNonNull(a).spliterator();
{I}Spliterator<? extends B> bSplit = Objects.requireNonNull(b).spliterator();

{I}int characteristics = aSplit.characteristics() & bSplit.characteristics() &
{II}~(Spliterator.DISTINCT | Spliterator.SORTED);

{I}long zipSize = ((characteristics & Spliterator.SIZED) != 0)
{II}? Math.min(aSplit.getExactSizeIfKnown(), bSplit.getExactSizeIfKnown())
{II}: -1;

{I}Iterator<A> aIter = Spliterators.iterator(aSplit);
{I}Iterator<B> bIter = Spliterators.iterator(bSplit);
{I}Iterator<_Pair<A, B>> cIter = new Iterator<_Pair<A, B>>() {{
{II}@Override
{II}public boolean hasNext() {{
{III}return aIter.hasNext() && bIter.hasNext();
{II}}}

{II}@Override
{II}public _Pair<A, B> next() {{
{III}return new _Pair<>(aIter.next(), bIter.next());
{II}}}
{I}}};

{I}Spliterator<_Pair<A, B>> split = Spliterators.spliterator(cIter, zipSize, characteristics);
{I}return StreamSupport.stream(split, false);
}}"""
        )
    )

    verification_writer = io.StringIO()
    verification_writer.write(
        f"""\
{I}/*
{I} * Verify that the instances of the meta-model satisfy the invariants.
{I} *
"""
    )

    # region Write an example usage

    first_cls = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )  # type: Optional[intermediate.ClassUnion]

    if first_cls is not None:
        cls_name = None  # type: Optional[str]
        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = java_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = java_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = java_naming.variable_name(Identifier("an_instance"))

        verification_writer.write(
            # We can not use textwrap.dedent since we indent everything including the
            # first line.
            f"""\
{I} * <p>Here is an example how to verify an instance of {cls_name}:
{I} * {{@code
{I} * {cls_name} {an_instance_variable} = new {cls_name}(
{I} *     // ... some constructor arguments ...
{I} * );
{I} * for (Reporting.Error error : Verification.verify({an_instance_variable})) {{
{I} * {I}System.out.println(error.cause + " at: " +
{I} * {II}Reporting.generateJsonPath(error.PathSegments));
{I} * }}
{I} */
"""
        )

    # endregion

    verification_writer = io.StringIO()
    verification_writer.write(
        """\
public class Verification {
"""
    )

    for i, verification_block in enumerate(verification_blocks):
        if i > 0:
            verification_writer.write("\n\n")

        verification_writer.write(textwrap.indent(verification_block, I))

    verification_writer.write("\n}")

    if len(errors) > 0:
        return None, errors

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.verification;"),
        Stripped("\n".join(imports)),
        Stripped(verification_writer.getvalue()),
        java_common.WARNING,
    ]  # type: List[Stripped]

    code = "\n\n".join(blocks)

    return [java_common.JavaFile("Verification.java", f"{code}\n")], None


# endregion+


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
