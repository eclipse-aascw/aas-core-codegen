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
from aas_core_codegen.intermediate import uses as intermediate_uses
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
    errors: List[str] = []

    expected_keys: List[specific_implementations.ImplementationKey] = []

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

        parts: List[str] = []
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

    blocks: List[Stripped] = []

    # region Construct block

    writer = io.StringIO()
    writer.write(
        f"""\
private static Pattern {construct_name}() {{
"""
    )

    defined_variables: Set[Identifier] = set()
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

    # NOTE (mristin):
    # The invariants are checked in a class nested in ``Verification``, so they can
    # call the private static methods.
    modifier = (
        "private"
        if verification.visibility is intermediate.Visibility.INTERNAL
        else "public"
    )

    writer.write(
        f"""\
{modifier} static Boolean {method_name}(String {arg_name}) {{
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
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
    ) -> None:
        """Initialize with the given values."""
        java_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            optional_map=is_optional_map,
            environment=environment,
            downcast_map=downcast_map,
        )

        self._symbol_table = symbol_table

        self._argument_name_set = frozenset(arg.name for arg in verification.arguments)

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if (
            node.identifier in self._variable_name_set
            or node.identifier in self._argument_name_set
        ):
            return (
                self._unwrap_if_optional(
                    node=node,
                    variable=Stripped(java_naming.variable_name(node.identifier)),
                ),
                None,
            )

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
    type_inference: intermediate_type_inference.TypeInference,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Transpile a verification function.

    The ``package`` defines the root Java package.
    """
    inference = type_inference.by_verification[verification]

    optional_inferrer = java_optional.OptionalInferrer(
        environment=inference.environment_with_args,
        type_map=inference.type_map,
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
        type_map=inference.type_map,
        is_optional_map=optional_inferrer.is_optional_map,
        environment=inference.environment_with_args,
        downcast_map=inference.downcast_map,
        symbol_table=symbol_table,
        verification=verification,
    )

    body: List[Stripped] = []
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

    # NOTE (mristin):
    # The ``List<T>`` is invariant in Java, so we declare the generic sequences,
    # see :py:func:`intermediate.generic_sequence_item_class`, with the wildcard
    # ``List<? extends T>``. This way, the lists of the descendants can be passed
    # without a copy. The ``Optional<T>`` is invariant as well, so we declare
    # the optional generic sequences as ``Optional<? extends List<? extends T>>``.
    arg_defs: List[Stripped] = []
    remarks_on_generic_sequences: List[str] = []
    for arg in verification.arguments:
        arg_name = java_naming.argument_name(arg.name)

        if intermediate.generic_sequence_item_class(arg) is None:
            arg_type = java_common.generate_type(arg.type_annotation)
        else:
            list_type_anno = intermediate.beneath_optional(arg.type_annotation)
            assert isinstance(list_type_anno, intermediate.ListTypeAnnotation)

            item_type = java_common.generate_type(list_type_anno.items)

            arg_type = Stripped(f"List<? extends {item_type}>")
            if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
                arg_type = Stripped(f"Optional<? extends {arg_type}>")

            remarks_on_generic_sequences.append(
                f"The argument {{@code {arg_name}}} is declared with the wildcard "
                f"{{@code List<? extends {item_type}>}} instead of the invariant "
                f"{{@code List<{item_type}>}} so that the lists of "
                f"the descendants of {{@link {item_type}}} can be passed without "
                f"a copy."
            )

        arg_defs.append(Stripped(f"{arg_type} {arg_name}"))

    writer = io.StringIO()
    if verification.description is not None:
        comment, comment_errors = java_description.generate_comment_for_signature(
            description=verification.description,
            context=java_description.Context(package=package, cls_or_enum=None),
            extra_remarks=remarks_on_generic_sequences,
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
    elif len(remarks_on_generic_sequences) > 0:
        writer.write(
            java_description.documentation_comment(
                Stripped("\n\n".join(remarks_on_generic_sequences))
            )
        )
        writer.write("\n")
    else:
        pass

    method_name = java_naming.method_name(verification.name)

    # NOTE (mristin):
    # The invariants are checked in a class nested in ``Verification``, so they can
    # call the private static methods.
    modifier = (
        "private"
        if verification.visibility is intermediate.Visibility.INTERNAL
        else "public"
    )

    if verification.returns is None:
        return_type = "void"
    else:
        return_type = java_common.generate_type(type_annotation=verification.returns)

    if len(arg_defs) == 0:
        writer.write(
            f"""\
{modifier} static {return_type} {method_name}() {{"""
        )
    else:
        writer.write(
            f"""\
{modifier} static {return_type} {method_name}(
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
    blocks: List[Stripped] = []

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

            for literal in enum.literals:
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
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        symbol_table: intermediate.SymbolTable,
    ) -> None:
        """Initialize with the given values."""
        java_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            optional_map=is_optional_map,
            environment=environment,
            downcast_map=downcast_map,
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
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Translate the invariant from the meta-model into C# code."""
    inference = type_inference.by_invariant[invariant]
    environment = inference.environment_with_self
    type_map = inference.type_map

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
        downcast_map=inference.downcast_map,
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


def _needs_verification(type_annotation: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether a value of ``type_annotation`` has anything to verify at any depth.

    In Java, we verify all our types, including the enumerations, and all
    the JSON-able values.
    """
    return any(
        isinstance(
            type_anno,
            (
                intermediate.OurTypeAnnotation,
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        )
        for type_anno in intermediate.over_type_annotation_and_nested_type_annotations(
            type_annotation
        )
    )


def _verification_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name ``type_anno`` by what its verification depends on.

    This follows the Polish notation of
    :py:func:`aas_core_codegen.java.common.type_moniker`, except that
    a constrained primitive is named by itself (*e.g.*, ``NonEmptyString``),
    and not by its constrainee (``String``), and a JSON object by its
    constrained key, if any (*e.g.*, ``jsonObjectByNonEmptyString``).

    We need a moniker of our own since
    :py:func:`aas_core_codegen.java.common.type_moniker` names the types by
    their Java type. For example, ``List[Non_empty_string]`` and
    ``List[Id_short_type]`` would both be named ``ListOf_String``. However,
    they are verified differently, so they can not share one verification
    method.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return java_common.list_moniker(_verification_moniker(type_anno.items))

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        return java_common.set_moniker(_verification_moniker(type_anno.items))

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return java_common.tuple_moniker(
            [_verification_moniker(item) for item in type_anno.items]
        )

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.ConstrainedPrimitive
    ):
        return java_naming.class_name(type_anno.our_type.name)

    if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        key_constrained_primitive = intermediate.try_constrained_primitive(
            type_anno.key
        )
        if key_constrained_primitive is not None:
            return (
                f"jsonObjectBy"
                f"{java_naming.class_name(key_constrained_primitive.name)}"
            )

    if isinstance(type_anno, intermediate.OptionalTypeAnnotation):
        raise AssertionError(
            f"Unexpected optional to be verified: {type_anno}. The optionals "
            f"nested in the containers should have been refused in "
            f"parse._translate._verify_symbol_table."
        )

    return java_common.leaf_moniker(type_anno)


@require(lambda type_anno: _needs_verification(type_anno))
def _verify_method(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Name the method of ``Verification`` verifying a value of ``type_anno``.

    The names of the methods generated for the containers and for the JSON
    objects with constrained keys contain an underscore, so they never collide
    with the methods of the enumerations and of the constrained primitives,
    which are named by ``capitalized_camel_case``.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return Identifier(f"verify{java_naming.enum_name(our_type.name)}")

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return Identifier(f"verify{java_naming.class_name(our_type.name)}")

        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            # NOTE (mristin):
            # A named union has no invariants of its own; ``verifyToErrorStream``
            # has an overload for it (see
            # :py:func:`_generate_union_verify_helper`) that recurses into
            # the underlying instance, so it is dispatched exactly like a class.
            return Identifier("verifyToErrorStream")

        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return Identifier("verifyJsonValue")

    elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return Identifier("verifyJsonArray")

    elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        key_constrained_primitive = intermediate.try_constrained_primitive(
            type_anno.key
        )

        # NOTE (mristin):
        # A bare ``str`` key has nothing to verify.
        if key_constrained_primitive is None:
            return Identifier("verifyJsonObject")

        return Identifier(
            f"verifyJsonObjectBy_"
            f"{java_naming.class_name(key_constrained_primitive.name)}"
        )

    elif isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        return Identifier(f"verify{_verification_moniker(type_anno)}")

    raise AssertionError(
        f"Unexpected type annotation with something to verify: {type_anno}. "
        f"The optionals nested in the containers should have been refused in "
        f"parse._translate._verify_symbol_table."
    )


@require(lambda type_anno: _needs_verification(type_anno))
def _generate_verify_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """
    Generate the method of ``Verification`` verifying ``type_anno``.

    The method verifies only one level and calls the method of its items by
    name. This way the verification is composed of plain methods, to any depth.
    """
    body: Stripped

    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        # NOTE (mristin):
        # A set has no index of its own, so we verify its items in the order
        # in which they are serialized. The index in the error path hence
        # points to the item in the serialized array.
        items_expr = (
            java_common.sorted_set_items(type_anno.items, Stripped("that"))
            if isinstance(type_anno, intermediate.SetTypeAnnotation)
            else "that"
        )

        body = Stripped(
            f"""\
return Verification.zip(
{I}IntStream.iterate(0, i -> i + 1).boxed(),
{I}{items_expr}.stream())
{II}.flatMap(itemTuple ->
{III}Verification.{_verify_method(type_anno.items)}(itemTuple.getSecond())
{IIII}.map(error -> {{
{IIIII}error.prependSegment(
{IIIIII}new Reporting.IndexSegment(itemTuple.getFirst()));
{IIIII}return error;
{IIII}}}));"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_streams = [
            Stripped(
                f"""\
Stream.of(that.item{i + 1}())
{I}.flatMap(Verification::{_verify_method(item_type_anno)})
{II}.map(error -> {{
{III}error.prependSegment(
{IIII}new Reporting.IndexSegment({i}));
{III}return error;
{II}}})"""
            )
            for i, item_type_anno in enumerate(type_anno.items)
            if _needs_verification(item_type_anno)
        ]

        stream = item_streams[0]
        for item_stream in item_streams[1:]:
            stream = Stripped(
                f"""\
Stream.<Reporting.Error>concat(
{I}{indent_but_first_line(stream, I)},
{I}{indent_but_first_line(item_stream, I)})"""
            )

        body = Stripped(f"return {stream};")

    else:
        assert_never(type_anno)

    value_type = java_common.generate_type(type_anno)

    return Stripped(
        f"""\
/**
 * Verify the items of {{@code that}} recursively.
 */
private static Stream<Reporting.Error> {_verify_method(type_anno)}(
{I}{indent_but_first_line(value_type, I)} that) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


@require(
    lambda type_anno: intermediate.try_constrained_primitive(type_anno.key) is not None
)
def _generate_verify_json_object_with_constrained_key(
    type_anno: intermediate.JsonObjectTypeAnnotation,
) -> Stripped:
    """Generate the method of ``Verification`` verifying ``type_anno``."""
    key_verify_method = _verify_method(type_anno.key)

    return Stripped(
        f"""\
/**
 * Verify that {{@code that}} is a JSON-able object with valid keys.
 */
private static Stream<Reporting.Error> {_verify_method(type_anno)}(
{I}ObjectNode that) {{
{I}return Stream.<Reporting.Error>concat(
{II}Verification.verifyJsonObject(that),
{II}Verification.streamOfFieldNames(that)
{III}.flatMap(key ->
{IIII}Verification.{key_verify_method}(key)
{IIIII}.map(error ->
{IIIIII}// NOTE (mristin):
{IIIIII}// A member of an open JSON object is no property of one of
{IIIIII}// our classes, so it gets no segment of its own -- the key
{IIIIII}// goes into the message instead, as it does in
{IIIIII}// ``verifyJsonValue``.
{IIIIII}new Reporting.Error(
{IIIIII}{I}"In the member \\"" + key + "\\": " + error.getCause()))));
}}"""
    )


def _generate_union_verify_helper() -> Stripped:
    """
    Generate a single ``verifyToErrorStream`` overload shared by every named union.

    A named union is not itself an ``IClass``, so it can not be passed to
    the general ``verifyToErrorStream(IClass that)`` dispatch function
    directly. We add this overload, next to it, so that call sites can keep
    calling ``verifyToErrorStream`` directly on a named union, exactly as
    they would on a class instance.

    Dispatching over the common ``IUnion<?>`` (see ``_generate_iunion`` in
    ``_generate_types.py``) instead of the union's own type means we need
    only this one overload for *all* named unions, not one per union.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
public static Stream<Reporting.Error> verifyToErrorStream(IUnion<?> that) {{
{I}return verifyToErrorStream(that.getUnderlying());
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transform_for_class(
    cls: intermediate.ConcreteClass,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transform method to errors for the given concrete class."""
    errors: List[Error] = []
    blocks: List[Stripped] = []

    name = java_naming.class_name(cls.name)

    for invariant in cls.invariants:
        invariant_code, error = _transpile_invariant(
            invariant=invariant,
            symbol_table=symbol_table,
            type_inference=type_inference,
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
        type_anno = intermediate.beneath_optional(prop.type_annotation)
        if not _needs_verification(type_anno):
            continue

        getter_name = java_naming.getter_name(prop.name)
        prop_literal = java_common.string_literal(prop.json_name)

        optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

        source_expr = (
            f"that.{getter_name}().get()" if optional else f"that.{getter_name}()"
        )

        block = Stripped(
            f"""\
errorStream = Stream.<Reporting.Error>concat(errorStream,
{I}Stream.of({source_expr})
{II}.flatMap(Verification::{_verify_method(type_anno)})
{III}.map(error -> {{
{IIII}error.prependSegment(
{IIIII}new Reporting.NameSegment({prop_literal}));
{IIII}return error;
{III}}}));"""
        )

        if optional:
            block = Stripped(
                f"""\
if (that.{getter_name}().isPresent()) {{
{I}{indent_but_first_line(block, I)}
}}"""
            )

        blocks.append(block)

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


def _generate_verify_json_value(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the methods verifying that a value is JSON-able.

    A JSON-able value is, recursively, exactly as JSON itself is defined, but
    a Jackson node rules out neither of the two ways of not being one:
    a missing node and a non-finite number. Both are reported here, at any
    depth. A null node is a JSON null, and hence a JSON-able value.

    The path *within* a JSON-able value goes into the message rather than into
    the structured path of the error: a name segment points at a property of
    one of our classes and an index segment at an item of one of our lists,
    and a member of an open JSON object is neither.
    """
    if not intermediate_uses.json_types(symbol_table):
        return []

    return [
        Stripped(
            f"""\
/**
 * Stream the field names of {{@code node}}.
 *
 * <p>Jackson gives an {{@link java.util.Iterator}}, which is not a stream.
 */
private static Stream<String> streamOfFieldNames(JsonNode node) {{
{I}final List<String> names = new ArrayList<>();
{I}node.fieldNames().forEachRemaining(names::add);
{I}return names.stream();
}}"""
        ),
        Stripped(
            f"""\
/**
 * Verify that {{@code node}} is a JSON-able value, at any depth.
 *
 * @param node to be verified
 * @param path JSON path to {{@code node}}, written into the messages
 * @return a stream of errors, if any
 */
private static Stream<Reporting.Error> verifyJsonValueAt(
{II}JsonNode node, String path) {{
{I}if (node == null || node.isMissingNode()) {{
{II}return Stream.of(
{III}new Reporting.Error(
{IIII}"Expected a JSON-able value at " + path
{IIIII}+ ", but got: " + node));
{I}}}

{I}if (node.isNull()) {{
{II}return Stream.empty();
{I}}}

{I}if (node.isNumber()) {{
{II}// NOTE (mristin):
{II}// JSON knows neither an infinity nor a not-a-number, so neither is
{II}// a JSON-able value, even though a Jackson node holds either.
{II}final double value = node.doubleValue();
{II}if (Double.isInfinite(value) || Double.isNaN(value)) {{
{III}return Stream.of(
{IIII}new Reporting.Error(
{IIIII}"Expected a JSON-able value at " + path
{IIIIII}+ ", but got the number " + value
{IIIIII}+ ", which is neither finite nor representable in JSON"));
{II}}}
{II}return Stream.empty();
{I}}}

{I}if (node.isBoolean() || node.isTextual()) {{
{II}return Stream.empty();
{I}}}

{I}if (node.isArray()) {{
{II}return Verification.zip(
{III}IntStream.iterate(0, i -> i + 1).boxed(),
{III}StreamSupport.stream(node.spliterator(), false))
{IIII}.flatMap(elemTuple -> verifyJsonValueAt(
{IIIII}elemTuple.getSecond(),
{IIIII}path + "[" + elemTuple.getFirst() + "]"));
{I}}}

{I}if (node.isObject()) {{
{II}return streamOfFieldNames(node)
{III}.flatMap(name -> verifyJsonValueAt(
{IIII}node.get(name), path + "." + name));
{I}}}

{I}return Stream.of(
{II}new Reporting.Error(
{III}"Expected a JSON-able value (a null, a boolean, a number, a string, "
{IIII}+ "an array or an object) at " + path
{IIII}+ ", but got: " + node.getNodeType()));
}}"""
        ),
        Stripped(
            f"""\
/**
 * Verify that {{@code node}} is a JSON-able value, at any depth.
 *
 * @param node to be verified
 * @return a stream of errors, if any
 */
public static Stream<Reporting.Error> verifyJsonValue(JsonNode node) {{
{I}return verifyJsonValueAt(node, "$");
}}"""
        ),
        Stripped(
            f"""\
/**
 * Verify that {{@code node}} is a JSON-able array.
 *
 * @param node to be verified
 * @return a stream of errors, if any
 */
public static Stream<Reporting.Error> verifyJsonArray(ArrayNode node) {{
{I}if (node == null) {{
{II}return Stream.of(
{III}new Reporting.Error(
{IIII}"Expected a JSON-able array, but got: null"));
{I}}}

{I}return verifyJsonValue(node);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Verify that {{@code node}} is a JSON-able object.
 *
 * @param node to be verified
 * @return a stream of errors, if any
 */
public static Stream<Reporting.Error> verifyJsonObject(ObjectNode node) {{
{I}if (node == null) {{
{II}return Stream.of(
{III}new Reporting.Error(
{IIII}"Expected a JSON-able object, but got: null"));
{I}}}

{I}return verifyJsonValue(node);
}}"""
        ),
    ]


def _generate_transformer(
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a transformer to double-dispatch an instance to errors."""
    errors: List[Error] = []

    blocks: List[Stripped] = []

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
            block, cls_errors = _generate_transform_for_class(
                cls=our_type,
                symbol_table=symbol_table,
                type_inference=type_inference,
            )
            if cls_errors is not None:
                errors.extend(cls_errors)
            else:
                assert block is not None
                blocks.append(block)
        elif isinstance(our_type, intermediate.NamedUnion):
            # A named union is never double-dispatched here directly -- it
            # is unwrapped by its own ``verifyToErrorStream`` overload
            # instead (see :py:func:`_generate_union_verify_helper`).
            pass

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
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the verify function for the constrained primitives."""
    errors: List[Error] = []
    blocks: List[Stripped] = []

    for invariant in constrained_primitive.invariants:
        invariant_code, error = _transpile_invariant(
            invariant=invariant,
            symbol_table=symbol_table,
            type_inference=type_inference,
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
    type_inference: intermediate_type_inference.TypeInference,
    package: java_common.PackageIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code of verification logic.
    """

    imports: List[Stripped] = [
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
    ]

    # NOTE (mristin):
    # A JSON-able value is a Jackson node, and only the models which use one
    # pay for the import and for the verification which goes with it.
    if intermediate_uses.json_types(symbol_table):
        imports.extend(
            [
                Stripped("import com.fasterxml.jackson.databind.JsonNode;"),
                Stripped("import com.fasterxml.jackson.databind.node.ArrayNode;"),
                Stripped("import com.fasterxml.jackson.databind.node.ObjectNode;"),
                Stripped("import java.util.ArrayList;"),
            ]
        )

    # NOTE (mristin):
    # We verify the containers and the JSON objects with constrained keys
    # through methods of their own, one per verification moniker.
    own_method_type_annos: List[
        Union[
            intermediate.ContainerTypeAnnotation, intermediate.JsonObjectTypeAnnotation
        ]
    ] = []

    observed_monikers: Set[str] = set()

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if not (
                    (
                        isinstance(
                            type_anno, intermediate.ContainerTypeAnnotationAsTuple
                        )
                        and _needs_verification(type_anno)
                    )
                    or (
                        isinstance(type_anno, intermediate.JsonObjectTypeAnnotation)
                        and intermediate.try_constrained_primitive(type_anno.key)
                        is not None
                    )
                ):
                    continue

                moniker = _verification_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)
                own_method_type_annos.append(type_anno)

    # NOTE (mristin):
    # A verification function which takes or returns a list or an optional needs
    # the import of ``List`` or ``Optional``, respectively, in its signature.
    # The signatures of the implementation-specific functions are written by hand,
    # but follow the same types. The same holds for the methods verifying
    # the lists.
    signature_type_annotations: List[intermediate.TypeAnnotationUnion] = [
        *(
            arg.type_annotation
            for verification in symbol_table.verification_functions
            for arg in verification.arguments
        ),
        *(
            verification.returns
            for verification in symbol_table.verification_functions
            if verification.returns is not None
        ),
    ]

    if (
        intermediate_uses.json_types(symbol_table)
        or any(
            isinstance(type_anno, intermediate.ListTypeAnnotation)
            for type_annotation in signature_type_annotations
            for type_anno in intermediate.over_type_annotation_and_nested_type_annotations(
                type_annotation
            )
        )
        or any(
            isinstance(type_anno, intermediate.ListTypeAnnotation)
            for type_anno in own_method_type_annos
        )
    ):
        imports.append(Stripped("import java.util.List;"))

    if any(
        isinstance(type_annotation, intermediate.OptionalTypeAnnotation)
        for type_annotation in signature_type_annotations
    ):
        imports.append(Stripped("import java.util.Optional;"))

    verification_blocks: List[Stripped] = []
    errors: List[Error] = []

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
                type_inference=type_inference,
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

    verification_blocks.extend(_generate_verify_json_value(symbol_table=symbol_table))

    transformer_block, transformer_errors = _generate_transformer(
        symbol_table=symbol_table,
        type_inference=type_inference,
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
                type_inference=type_inference,
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

        elif isinstance(our_type, intermediate.NamedUnion):
            # A named union has no invariants of its own; it is unwrapped by
            # the single shared ``verifyToErrorStream(IUnion<?>)`` overload
            # instead (see :py:func:`_generate_union_verify_helper`).
            pass

        else:
            assert_never(our_type)

    if len(symbol_table.named_unions) > 0:
        verification_blocks.append(_generate_union_verify_helper())

    for type_anno in own_method_type_annos:
        if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
            verification_blocks.append(
                _generate_verify_json_object_with_constrained_key(type_anno=type_anno)
            )
        else:
            verification_blocks.append(_generate_verify_container(type_anno=type_anno))

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

    first_cls: Optional[intermediate.ClassUnion] = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )

    if first_cls is not None:
        cls_name: Optional[str] = None
        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = java_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = java_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = java_naming.variable_name(Identifier("an_instance"))

        verification_writer.write(
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

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.verification;"),
        Stripped("\n".join(imports)),
        Stripped(verification_writer.getvalue()),
        java_common.WARNING,
    ]

    code = "\n\n".join(blocks)

    return [java_common.JavaFile("Verification.java", f"{code}\n")], None


# endregion+


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
