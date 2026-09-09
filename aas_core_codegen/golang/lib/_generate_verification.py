"""Generate code of verification logic."""

import io
import textwrap
from typing import (
    Tuple,
    Optional,
    List,
    Sequence,
    Mapping,
    Union,
)

from icontract import ensure, require

from aas_core_codegen import intermediate, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    assert_never,
    Identifier,
    indent_but_first_line,
    wrap_text_into_lines,
    assert_union_without_excluded,
)
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    PrimitiveTypeAnnotation,
)
from aas_core_codegen.parse import tree as parse_tree, retree as parse_retree
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    description as golang_description,
    pointering as golang_pointering,
    transpilation as golang_transpilation,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


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
                    f"Verification/{func.name}.go"
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
    Render the regular expressions for Go.

    Notably, do not escape character points, but leave them as-are, since that is
    what Go regular expression engine expects.

    For example:

    .. code-block ::

        package main

        import (
            "fmt"
            "regexp"
        )

        func main() {
            re := regexp.MustCompile(
                "^[\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]*$",
            )
            text := "\U0001F600"
            fmt.Printf("%v", re.MatchString(text))
            // Prints "true"
        }

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

        return [node.character]


_REGEX_RENDERER = RegexRenderer()


class _PatternVerificationTranspiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a statement of a pattern verification into Golang."""

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_joined_str_values(
        self, values: Sequence[Union[str, parse_tree.FormattedValue]]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Transform the values of a joined string to a Golang string literal."""
        # If we do not need interpolation, simply return the string literals
        # joined together.
        needs_interpolation = any(
            isinstance(value, parse_tree.FormattedValue) for value in values
        )
        if not needs_interpolation:
            return (
                Stripped(
                    golang_common.string_literal(
                        "".join(value for value in values)  # type: ignore
                    )
                ),
                None,
            )

        parts = []  # type: List[str]

        for value in values:
            if isinstance(value, str):
                parts.append(golang_common.string_literal(value))

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self.transform(value.value)
                if error is not None:
                    return None, error

                assert code is not None

                parts.append(code)
            else:
                assert_never(value)

        if len(parts) > 1:
            parts_joined = "\n".join(f"{part}," for part in parts)

            return (
                Stripped(
                    f"""\
aascommon.Concat(
{I}{indent_but_first_line(parts_joined, I)}
)"""
                ),
                None,
            )

        assert len(parts) == 1, "At least one part expected in the formatted string"
        return Stripped(parts[0]), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if isinstance(node.value, str):
            # NOTE (mristin):
            # We assume that all the string constants are valid regular expressions.
            # At this point, we could not find any difference between Golang and
            # Python regex languages which are relevant to the features we currently
            # support.

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

            # NOTE (mristin):
            # Strictly speaking, this is a joined string with a single value, a string
            # literal. Thus, do not be confused by the name of the function —
            # this function treats both joined formatted values *and* string literals.
            return self._transform_joined_str_values(
                values=parse_retree.render(regex=regex, renderer=_REGEX_RENDERER)
            )
        else:
            raise AssertionError(f"Unexpected {node=}")

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return Stripped(golang_naming.variable_name(node.identifier)), None

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
            values=parse_retree.render(regex=regex)
        )

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        assert isinstance(node.target, parse_tree.Name)
        variable = golang_naming.variable_name(node.target.identifier)
        code, error = self.transform(node.value)
        if error is not None:
            return None, error
        assert code is not None

        # NOTE (mristin):
        # We assume that the variables won't change in the patterns. If this assumption
        # is broken, fix the code here by first inspecting the scope and deciding
        # which variables need to be first defined and which have been already
        # defined.
        return Stripped(f"{variable} := {code}"), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_pattern_verification(
    verification: intermediate.PatternVerification,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the verification function that checks the regular expressions."""
    # NOTE (mristin):
    # We assume that we performed all the checks at the intermediate stage.

    construct_name = golang_naming.private_function_name(
        Identifier(f"construct_{verification.name}")
    )

    blocks = []  # type: List[Stripped]

    # region Construct block

    writer = io.StringIO()
    writer.write(
        f"""\
func {construct_name}() *regexp.Regexp {{
"""
    )

    transpiler = _PatternVerificationTranspiler()

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

    writer.write(
        textwrap.indent(
            f"""\
return regexp.MustCompile(
{I}{pattern_expr},
)""",
            I,
        )
    )

    writer.write("\n}")

    blocks.append(Stripped(writer.getvalue()))

    # endregion

    # region Initialize the regex

    regex_name = golang_naming.private_constant_name(
        Identifier(f"{verification.name}_re")
    )

    blocks.append(Stripped(f"var {regex_name} = {construct_name}()"))

    # endregion

    # region Define the verification function

    assert len(verification.arguments) == 1
    assert isinstance(
        verification.arguments[0].type_annotation, intermediate.PrimitiveTypeAnnotation
    )
    # noinspection PyUnresolvedReferences
    assert (
        verification.arguments[0].type_annotation.a_type
        == intermediate.PrimitiveType.STR
    )

    arg_name = golang_naming.argument_name(verification.arguments[0].name)

    function_name = golang_naming.function_name(verification.name)

    writer = io.StringIO()

    if verification.description is not None:
        (comment, comment_errors,) = golang_description.generate_comment_for_signature(
            description=verification.description,
            context=golang_description.Context(
                package=golang_common.VERIFICATION_PACKAGE, cls_or_enum=None
            ),
        )
        if comment_errors is not None:
            return None, Error(
                verification.description.parsed.node,
                f"Failed to generate the documentation comment for {verification.name!r}",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    writer.write(
        f"""\
func {function_name}({arg_name} string) bool {{
{I}return {regex_name}.MatchString(
{II}{arg_name},
{I})
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


class _TranspilableVerificationTranspiler(golang_transpilation.Transpiler):
    """Transpile the body of a :py:class:`TranspilableVerification`."""

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
        is_pointer_map: Mapping[parse_tree.Node, bool],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
    ) -> None:
        """Initialize with the given values."""
        golang_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            is_pointer_map=is_pointer_map,
            environment=environment,
        )

        self._symbol_table = symbol_table

        self._argument_name_set = frozenset(arg.name for arg in verification.arguments)

    def _transform_enumeration_literal(
        self, enumeration_name: Identifier, literal_name: Identifier
    ) -> Stripped:
        literal = golang_naming.enum_literal_name(
            enumeration_name=enumeration_name, literal_name=literal_name
        )
        return Stripped(f"aastypes.{literal}")

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(golang_naming.variable_name(node.identifier)), None

        if node.identifier in self._argument_name_set:
            return Stripped(golang_naming.argument_name(node.identifier)), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_name = golang_naming.constant_name(node.identifier)
            return Stripped(f"aasconstants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(golang_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"aastypes.{golang_naming.enum_name(node.identifier)}"),
                None,
            )

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to Golang. We could not find it neither in the constants, nor in "
            f"verification functions, nor as an enumeration. "
            f"If you expect this name to be transpilable, please contact "
            f"the developers.",
        )


def _transpile_transpilable_verification(
    verification: intermediate.TranspilableVerification,
    symbol_table: intermediate.SymbolTable,
    environment: intermediate_type_inference.Environment,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Transpile a verification function."""
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

    pointer_inferrer = golang_pointering.Inferrer(
        environment=type_inference.environment_with_args,
        type_map=type_inference.type_map,
    )

    for node in verification.parsed.body:
        _ = pointer_inferrer.transform(node)

    if len(pointer_inferrer.errors) > 0:
        return None, Error(
            verification.parsed.node,
            f"Failed to infer whether a node is a Golang pointer "
            f"in the verification function {verification.name!r}",
            pointer_inferrer.errors,
        )

    transpiler = _TranspilableVerificationTranspiler(
        type_map=type_inference.type_map,
        is_pointer_map=pointer_inferrer.is_pointer_map,
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
        (comment, comment_errors,) = golang_description.generate_comment_for_signature(
            description=verification.description,
            context=golang_description.Context(
                package=golang_common.VERIFICATION_PACKAGE,
                cls_or_enum=None,
            ),
        )
        if comment_errors is not None:
            return None, Error(
                verification.description.parsed.node,
                f"Failed to generate the comment "
                f"for verification function {verification.name!r}",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    function_name = golang_naming.function_name(verification.name)

    if verification.returns is None:
        return_type_suffix = ""
    else:
        return_type = golang_common.generate_type(
            type_annotation=verification.returns, types_package=Identifier("aastypes")
        )
        return_type_suffix = f" {return_type}"

    arg_defs = []  # type: List[Stripped]
    for arg in verification.arguments:
        arg_type = golang_common.generate_type(
            arg.type_annotation, types_package=Identifier("aastypes")
        )
        arg_name = golang_naming.argument_name(arg.name)
        arg_defs.append(Stripped(f"{arg_name} {arg_type}"))

    if len(arg_defs) == 0:
        writer.write(
            f"""\
func {function_name}(){return_type_suffix} {{"""
        )
    else:
        arg_defs_joined = "\n".join(f"{arg_def}," for arg_def in arg_defs)
        writer.write(
            f"""\
func {function_name}(
{I}{indent_but_first_line(arg_defs_joined, I)}
){return_type_suffix} {{"""
        )

    if len(body) == 0:
        writer.write("\n")
        writer.write("// Intentionally empty.")
    else:
        for stmt in body:
            writer.write("\n")
            writer.write(textwrap.indent(stmt, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


class _InvariantTranspiler(golang_transpilation.Transpiler):
    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        is_pointer_map: Mapping[parse_tree.Node, bool],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
    ) -> None:
        """Initialize with the given values."""
        golang_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            is_pointer_map=is_pointer_map,
            environment=environment,
            types_package=Identifier("aastypes"),
        )

        self._symbol_table = symbol_table

    def _transform_enumeration_literal(
        self, enumeration_name: Identifier, literal_name: Identifier
    ) -> Stripped:
        literal = golang_naming.enum_literal_name(
            enumeration_name=enumeration_name, literal_name=literal_name
        )
        return Stripped(f"aastypes.{literal}")

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            name = Stripped(golang_naming.variable_name(node.identifier))

        elif node.identifier == "self":
            # The ``that`` refers to the argument of the verification function.
            name = Stripped("that")

        elif node.identifier in self._symbol_table.constants_by_name:
            constant_name = golang_naming.constant_name(node.identifier)
            name = Stripped(f"aasconstants.{constant_name}")

        elif node.identifier in self._symbol_table.verification_functions_by_name:
            name = Stripped(golang_naming.function_name(node.identifier))

        elif (
            our_type := self._symbol_table.find_our_type(name=node.identifier),
            isinstance(our_type, intermediate.Enumeration),
        )[1]:
            name = Stripped(f"aastypes.{golang_naming.enum_name(node.identifier)}")
        else:
            return None, Error(
                node.original_node,
                f"We can not determine how to transpile the name {node.identifier!r} "
                f"to Golang. We could not find it neither in the local variables, "
                f"nor in the global constants, nor in verification functions, "
                f"nor as an enumeration. If you expect this name to be transpilable, "
                f"please contact the developers.",
            )

        assert name is not None
        return name, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_invariant(
    invariant: intermediate.Invariant,
    symbol_table: intermediate.SymbolTable,
    environment: intermediate_type_inference.Environment,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Translate the invariant from the meta-model into Golang code."""
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

    pointer_inferrer = golang_pointering.Inferrer(
        environment=environment, type_map=type_map
    )

    _ = pointer_inferrer.transform(invariant.body)

    if len(pointer_inferrer.errors) > 0:
        return None, Error(
            invariant.parsed.node,
            "Failed to infer whether a node is a Golang pointer in the invariant",
            pointer_inferrer.errors,
        )

    transpiler = _InvariantTranspiler(
        type_map=type_map,
        is_pointer_map=pointer_inferrer.is_pointer_map,
        environment=environment,
        symbol_table=symbol_table,
    )

    expr, error = transpiler.transform(invariant.parsed.body)
    if error is not None:
        return None, error

    assert expr is not None

    writer = io.StringIO()
    if len(expr) > 50 or "\n" in expr:
        writer.write(
            f"""\
if !(
{I}{indent_but_first_line(expr, I)}) {{
"""
        )
    else:
        no_parenthesis_type_in_this_context = (
            parse_tree.Index,
            parse_tree.Name,
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
        )

        if isinstance(invariant.parsed.body, no_parenthesis_type_in_this_context):
            not_expr = f"!{expr}"
        else:
            not_expr = f"!({expr})"

        writer.write(f"if {not_expr} {{\n")

    new_verification_error_writer = io.StringIO()

    new_verification_error_writer.write("newVerificationError(\n")

    # NOTE (mristin):
    # We need to wrap the description in multiple literals as a single long
    # string literal is often too much for the readability.
    invariant_description_lines = wrap_text_into_lines(invariant.description)

    if len(invariant_description_lines) == 1:
        line = invariant_description_lines[0]
        new_verification_error_writer.write(f"{I}{golang_common.string_literal(line)},")
        new_verification_error_writer.write(")")
    else:
        for i, line in enumerate(invariant_description_lines):
            if i == 0:
                new_verification_error_writer.write(
                    f"{I}{golang_common.string_literal(line)} +\n"
                )
            elif i < len(invariant_description_lines) - 1:
                new_verification_error_writer.write(
                    f"{I}{golang_common.string_literal(line)} +\n"
                )
            else:
                new_verification_error_writer.write(
                    f"{I}{golang_common.string_literal(line)},\n"
                )
                new_verification_error_writer.write(")")

    new_verification_error = Stripped(new_verification_error_writer.getvalue())

    writer.write(
        f"""\
{I}abort = onError(
{II}{indent_but_first_line(new_verification_error, II)},
{I})
{I}if abort {{
{II}return
{I}}}
}}"""
    )

    return Stripped(writer.getvalue()), None


OurTypeExceptEnumeration = Union[
    intermediate.ConstrainedPrimitive,
    intermediate.AbstractClass,
    intermediate.ConcreteClass,
]
assert_union_without_excluded(
    original_union=intermediate.OurType,
    subset_union=OurTypeExceptEnumeration,
    excluded=[intermediate.Enumeration],
)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_verify_property_snippet(
    prop: intermediate.Property,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the snippet to verify a property.

    Return an empty string if there is nothing to be verified for the given property.
    """
    # NOTE (mristin):
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

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    prop_name = golang_naming.property_name(prop.name)
    prop_name_literal = golang_common.string_literal(prop_name)

    getter_name = golang_naming.getter_name(prop.name)

    optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

    block = None  # type: Optional[Stripped]

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        if type_anno.a_type is intermediate.PrimitiveType.BYTEARRAY and not optional:
            block = Stripped(
                f"""\
if that.{getter_name}() == nil {{
{I}abort = onError(
{II}newVerificationError(
{III}"Required property not set: {prop_name}",
{II}),
{I})
{I}if abort {{
{II}return
{I}}}
}}"""
            )

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(
            our_type, (intermediate.Enumeration, intermediate.ConstrainedPrimitive)
        ):
            verify_function_name = golang_naming.function_name(
                Identifier(f"verify_{our_type.name}")
            )

            pointer_prefix = (
                "*" if golang_pointering.is_pointer_type(prop.type_annotation) else ""
            )

            block = Stripped(
                f"""\
abort = {verify_function_name}(
{I}{pointer_prefix}that.{getter_name}(),
{I}func(err *VerificationError) bool {{
{II}err.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_name_literal},
{III}}},
{II})
{II}return onError(err)
{I}}},
)
if abort {{
{I}return
}}"""
            )

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            block = Stripped(
                f"""\
abort = Verify(
{I}that.{getter_name}(),
{I}func(err *VerificationError) bool {{
{II}err.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_name_literal},
{III}}},
{II})
{II}return onError(err)
{I}}},
)
if abort {{
{I}return
}}"""
            )
        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            f"NOTE (mristin): We expect only lists of atomic values "
            f"at the moment, but you specified {type_anno}. "
            f"Please contact the developers if you need this feature."
        )

        loop_body: Optional[Stripped] = None

        if isinstance(type_anno.items, PrimitiveTypeAnnotation):
            # There is no verification for primitive types within a list.
            pass

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            # NOTE (mristin):
            # We adapted the code for verifying the atomic values from above. This does
            # cause a bit of duplication, but abstracting away the code to make it
            # reusable resulted in a much more convoluted and less understandable code
            # that we decided to duplicate it here. For example, the logic for
            # prepending the path to the error can not be easily abstracted.

            if isinstance(
                type_anno.items.our_type,
                (intermediate.Enumeration, intermediate.ConstrainedPrimitive),
            ):
                verify_function_name = golang_naming.function_name(
                    Identifier(f"verify_{type_anno.items.our_type.name}")
                )

                pointer_prefix = (
                    "*" if golang_pointering.is_pointer_type(type_anno.items) else ""
                )

                loop_body = Stripped(
                    f"""\
abort = {verify_function_name}(
{I}{pointer_prefix}v,
{I}func(err *VerificationError) bool {{
{II}err.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{
{IIII}Index: i,
{III}}},
{II})

{II}err.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_name_literal},
{III}}},
{II})

{II}return onError(err)
{I}}},
)
if abort {{
{I}return
}}"""
                )

            elif isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                loop_body = Stripped(
                    f"""\
abort = Verify(
{I}v,
{I}func(err *VerificationError) bool {{
{II}err.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{
{IIII}Index: i,
{III}}},
{II})

{II}err.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_name_literal},
{III}}},
{II})

{II}return onError(err)
{I}}},
)
if abort {{
{I}return
}}"""
                )

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.items.our_type)

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.items)

        if loop_body is not None:
            block = Stripped(
                f"""\
for i, v := range that.{getter_name}() {{
{I}{indent_but_first_line(loop_body, I)}
}}"""
            )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_blocks = []  # type: List[Stripped]

        for i, item_type_anno in enumerate(type_anno.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"NOTE (mristin): We expect only atomic items in a tuple "
                f"at the moment, but got {item_type_anno} in {type_anno}. "
                f"This should have already been verified in "
                f"intermediate._translate._verify_only_simple_type_patterns."
            )

            item_expr = f"that.{getter_name}().Item{i + 1}"

            if isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
                # There is no verification for primitive types within a tuple.
                continue

            elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                if isinstance(
                    item_type_anno.our_type,
                    (intermediate.Enumeration, intermediate.ConstrainedPrimitive),
                ):
                    verify_function_name = golang_naming.function_name(
                        Identifier(f"verify_{item_type_anno.our_type.name}")
                    )

                    item_blocks.append(
                        Stripped(
                            f"""\
abort = {verify_function_name}(
{I}{item_expr},
{I}func(err *VerificationError) bool {{
{II}err.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{
{IIII}Index: {i},
{III}}},
{II})

{II}err.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_name_literal},
{III}}},
{II})

{II}return onError(err)
{I}}},
)
if abort {{
{I}return
}}"""
                        )
                    )

                elif isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    item_blocks.append(
                        Stripped(
                            f"""\
abort = Verify(
{I}{item_expr},
{I}func(err *VerificationError) bool {{
{II}err.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{
{IIII}Index: {i},
{III}}},
{II})

{II}err.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_name_literal},
{III}}},
{II})

{II}return onError(err)
{I}}},
)
if abort {{
{I}return
}}"""
                        )
                    )

                else:
                    # noinspection PyTypeChecker
                    assert_never(item_type_anno.our_type)

            else:
                # noinspection PyTypeChecker
                assert_never(item_type_anno)

        if len(item_blocks) > 0:
            block = Stripped("\n\n".join(item_blocks))

    else:
        assert_never(type_anno)

    primitive_type = intermediate.try_primitive_type(type_anno)

    is_reference = (
        optional
        or primitive_type is intermediate.PrimitiveType.BYTEARRAY
        or (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            )
        )
        or isinstance(type_anno, intermediate.ListTypeAnnotation)
    )

    if not optional and is_reference and block is None:
        block = Stripped(
            f"""\
if that.{getter_name}() == nil {{
{I}abort = onError(
{II}newVerificationError(
{III}"Required property not set: {prop_name}",
{II}),
{I})
{I}if abort {{
{II}return
{I}}}
}}"""
        )
    elif not optional and is_reference and block is not None:
        block = Stripped(
            f"""\
if that.{getter_name}() == nil {{
{I}abort = onError(
{II}newVerificationError(
{III}"Required property not set: {prop_name}",
{II}),
{I})
{I}if abort {{
{II}return
{I}}}
}} else {{
{I}{indent_but_first_line(block, I)}
}}"""
        )
    elif optional and block is not None:
        block = Stripped(
            f"""\
if that.{getter_name}() != nil {{
{I}{indent_but_first_line(block, I)}
}}"""
        )
    elif block is None:
        return Stripped(""), None
    else:
        assert AssertionError(f"Unhandled case: {block=}, {optional=}, {is_reference=}")

    return block, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_verify_class(
    cls: intermediate.ConcreteClass,
    symbol_table: intermediate.SymbolTable,
    base_environment: intermediate_type_inference.Environment,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the verification function for the given concrete class."""
    errors = []  # type: List[Error]
    blocks = []  # type: List[Stripped]

    environment = intermediate_type_inference.MutableEnvironment(
        parent=base_environment
    )

    assert environment.find(Identifier("self")) is None
    environment.set(
        identifier=Identifier("self"),
        type_annotation=intermediate_type_inference.OurTypeAnnotation(our_type=cls),
    )

    # region Generate the non-recursive part verifying the invariants

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

    # endregion

    # region Recurse into properties

    for prop in cls.properties:
        block, error = _generate_verify_property_snippet(prop=prop)
        if error is not None:
            errors.append(
                Error(
                    cls.parsed.node,
                    f"Failed to generate the verification of the property {prop.name!r} "
                    f"of the class {cls.name!r}",
                    [error],
                )
            )
            continue

        assert block is not None

        if block != "":
            blocks.append(block)

    # endregion

    if len(errors) > 0:
        return None, errors

    interface_name = golang_naming.interface_name(cls.name)

    if len(blocks) == 0:
        blocks.append(
            Stripped(
                f"""\
// No verification has been defined for {interface_name}."""
            )
        )

    function_name = golang_naming.function_name(Identifier(f"verify_{cls.name}"))

    body = "\n\n".join(blocks)

    return (
        Stripped(
            f"""\
// Verify `that` instance of [aastypes.{interface_name}].
//
// You have to supply the callback `onError` to iterate over the errors.
// If `onError` returns abort `true`, this function will abort
// further verification as well, and return abort `true`. Otherwise,
// abort `false` is returned.
func {function_name}(
{I}that aastypes.{interface_name},
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}abort = false

{I}{indent_but_first_line(body, I)}

{I}return
}}"""
        ),
        None,
    )


def _generate_verify(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the main entry point for verification."""
    case_blocks = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=cls.name
        )

        verification_function = golang_naming.function_name(
            Identifier(f"verify_{cls.name}")
        )

        interface_name = golang_naming.interface_name(cls.name)

        case_blocks.append(
            Stripped(
                f"""\
case aastypes.{literal}:
{I}abort = {verification_function}(
{II}that.(aastypes.{interface_name}),
{II}onError,
{I})"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}abort = onError(
{II}newVerificationError(
{III}fmt.Sprintf(
{IIII}"Unexpected model type literal: %v",
{IIII}modelType,
{III}),
{II}),
{I})"""
        )
    )

    switch_body = Stripped("\n".join(case_blocks))
    switch_statement = Stripped(
        f"""\
switch modelType {{
{switch_body}
}}"""
    )

    model_type_getter = golang_naming.getter_name(Identifier("model_type"))

    return Stripped(
        f"""\
// Verify ``that`` instance.
//
// You have to supply the callback `onError` to iterate over the errors.
// If `onError` returns abort `true`, this function will abort
// further verification as well, and return abort `true`. Otherwise,
// abort `false` is returned.
func Verify(
{I}that aastypes.IClass,
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}modelType := that.{model_type_getter}()
{I}{indent_but_first_line(switch_statement, I)}
{I}return
}}"""
    )


def _generate_verify_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the verify function that checks the range of the enumeration literal."""
    function_name = golang_naming.function_name(
        Identifier(f"verify_{enumeration.name}")
    )

    enum_name = golang_naming.enum_name(enumeration.name)

    # NOTE (mristin):
    # The case where we have no literals defined is an edge case where no
    # literal satisfies the condition.
    if len(enumeration.literals) == 0:
        body = Stripped(
            f"""\
abort = onError(
{I}newVerificationError(
{II}fmt.Sprintf(
{III}"The enumeration {enum_name} has no literals defined, " +
{III}"but you passed in: %v",
{III}that,
{II}),
{I}),
)

return"""
        )

    else:
        first_literal = golang_naming.enum_literal_name(
            enumeration_name=enumeration.name,
            literal_name=enumeration.literals[0].name,
        )

        last_literal = golang_naming.enum_literal_name(
            enumeration_name=enumeration.name,
            literal_name=enumeration.literals[-1].name,
        )

        body = Stripped(
            f"""\
abort = false

if
{I}that < aastypes.{first_literal} ||
{I}that > aastypes.{last_literal} {{
{I}abort = onError(
{II}newVerificationError(
{III}fmt.Sprintf(
{IIII}"Invalid literal value for {enum_name}: %v",
{IIII}that,
{III}),
{II}),
{I})
}}

return"""
        )

    return Stripped(
        f"""\
// Verify that `that` is a literal in the valid range
// of {enum_name}.
//
// You have to supply the callback `onError` to iterate over the errors.
// If `onError` returns abort `true`, this function will abort
// further verification as well, and return abort `true`. Otherwise,
// abort `false` is returned.
func {function_name}(
{I}that aastypes.{enum_name},
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}{indent_but_first_line(body, I)}
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
        blocks.append(Stripped("// There is no verification specified."))

    body = "\n\n".join(blocks)

    function_name = golang_naming.function_name(
        Identifier(f"verify_{constrained_primitive.name}")
    )

    that_type = golang_common.PRIMITIVE_TYPE_MAP[constrained_primitive.constrainee]

    return (
        Stripped(
            f"""\
// Verify the constraints of `that` value.
//
// You have to supply the callback `onError` to iterate over the errors.
// If `onError` returns abort `true`, this function will abort
// further verification as well, and return abort `true`. Otherwise,
// abort `false` is returned.
func {function_name}(
{I}that {that_type},
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}abort = false

{I}{indent_but_first_line(body, I)}

{I}return
}}"""
        ),
        None,
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code of verification logic."""
    errors = []  # type: List[Error]

    constants_url_literal = golang_common.string_literal(f"{repo_url}/constants")

    common_url_literal = golang_common.string_literal(f"{repo_url}/common")

    reporting_url_literal = golang_common.string_literal(f"{repo_url}/reporting")

    types_url_literal = golang_common.string_literal(f"{repo_url}/types")

    blocks = [
        Stripped(
            """\
// Package verification allows you to verify model instances.
//
// The main function is [Verify].
//
// Other verification functions (`Verify*`) are left for modularity, in case you want
// to be explicit about the typing in your code. However, in the large majority of
// the cases, you only want to call [Verify].
package verification"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"math/big"
{I}"fmt"
{I}"regexp"
{I}"strconv"
{I}"strings"
{I}aascommon {common_url_literal}
{I}aasconstants {constants_url_literal}
{I}aasreporting {reporting_url_literal}
{I}aastypes {types_url_literal}
)"""
        ),
        Stripped(
            f"""\
// Represent a verification violation.
//
// Implements `error`.
type VerificationError struct{{
{I}Path *aasreporting.Path
{I}Message string
}}"""
        ),
        Stripped(
            f"""\
func newVerificationError(message string) *VerificationError {{
{I}return &VerificationError{{
{II}Path: &aasreporting.Path{{}},
{II}Message: message,
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func (ve *VerificationError) Error() string {{
{I}return fmt.Sprintf(
{II}"%s: %s",
{II}ve.PathString(),
{II}ve.Message,
{I})
}}"""
        ),
        Stripped(
            f"""\
// Render the path as a string.
func (ve *VerificationError) PathString() string {{
{I}return aasreporting.ToGolangPath(ve.Path)
}}"""
        ),
    ]  # type: List[Stripped]

    base_environment = intermediate_type_inference.populate_base_environment(
        symbol_table=symbol_table
    )

    for verification in symbol_table.verification_functions:
        if isinstance(verification, intermediate.ImplementationSpecificVerification):
            implementation_key = specific_implementations.ImplementationKey(
                f"Verification/{verification.name}.go"
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
                blocks.append(implementation)

        elif isinstance(verification, intermediate.PatternVerification):
            implementation, error = _transpile_pattern_verification(
                verification=verification
            )

            if error is not None:
                errors.append(error)
            else:
                assert implementation is not None
                blocks.append(implementation)

        elif isinstance(verification, intermediate.TranspilableVerification):
            implementation, error = _transpile_transpilable_verification(
                verification=verification,
                symbol_table=symbol_table,
                environment=base_environment,
            )

            if error is not None:
                errors.append(error)
            else:
                assert implementation is not None
                blocks.append(implementation)

        else:
            assert_never(verification)

    for cls in symbol_table.concrete_classes:
        block, underlying_errors = _generate_verify_class(
            cls=cls, symbol_table=symbol_table, base_environment=base_environment
        )
        if underlying_errors is not None:
            errors.append(
                Error(
                    cls.parsed.node,
                    f"Failed to generate the verification for the class {cls.name!r}",
                    underlying_errors,
                )
            )
        else:
            assert block is not None
            blocks.append(block)

    for enumeration in symbol_table.enumerations:
        block = _generate_verify_enumeration(enumeration=enumeration)
        blocks.append(block)

    for constrained_primitive in symbol_table.constrained_primitives:
        block, underlying_errors = _generate_verify_constrained_primitive(
            constrained_primitive=constrained_primitive,
            symbol_table=symbol_table,
            base_environment=base_environment,
        )
        if underlying_errors is not None:
            errors.append(
                Error(
                    constrained_primitive.parsed.node,
                    f"Failed to generate the verification for "
                    f"the constrained primitive {constrained_primitive.name!r}",
                    underlying_errors,
                )
            )
        else:
            assert block is not None
            blocks.append(block)

    blocks.append(_generate_verify(symbol_table=symbol_table))

    blocks.append(golang_common.WARNING)

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


# endregion


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
