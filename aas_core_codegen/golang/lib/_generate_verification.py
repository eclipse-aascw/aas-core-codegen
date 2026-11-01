"""Generate code of verification logic."""

import io
import textwrap
from typing import (
    Tuple,
    Optional,
    List,
    MutableMapping,
    Sequence,
    Mapping,
    Union,
    Set,
    Dict,
    Final,
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
)
from aas_core_codegen.intermediate import uses as intermediate_uses
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
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
    INDENT7 as IIIIIII,
    INDENT8 as IIIIIIII,
)


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
    r"""
    Render the regular expressions for Go.

    Preserve explicitly encoded characters as ``\x{...}`` escapes so that regex
    metacharacters retain their literal meaning. Go's regex engine supports this
    notation for both ASCII and Unicode characters.
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

        return [f"\\x{{{ord(node.character):x}}}"]


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

        parts: List[str] = []

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
ourcommon.Concat(
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

    blocks: List[Stripped] = []

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


def _type_parameter_name(argument: intermediate.Argument) -> Identifier:
    """
    Generate the name of the type parameter for the items of the ``argument``.

    For example, ``items`` gives ``ItemsT``.
    """
    return Identifier(f"{golang_naming.function_name(argument.name)}T")


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
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
    ) -> None:
        """Initialize with the given values."""
        golang_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            is_pointer_map=is_pointer_map,
            downcast_map=downcast_map,
            environment=environment,
            types_package=Identifier("ourtypes"),
        )

        self._symbol_table = symbol_table

        self._argument_name_set = frozenset(arg.name for arg in verification.arguments)

        # NOTE (mristin):
        # The type inference propagates the very type annotation of the items of
        # an argument to the loop variables, the generator variables and
        # the indexed items, so we can tell by the identity of the type annotation
        # that a value is of the type parameter of a generic sequence.
        type_parameter_by_items_id: Dict[int, Identifier] = dict()
        for arg in verification.arguments:
            if intermediate.generic_sequence_item_class(arg) is None:
                continue

            arg_type_anno = environment.find(arg.name)
            assert arg_type_anno is not None

            list_type_anno = intermediate_type_inference.beneath_optional(arg_type_anno)
            assert isinstance(
                list_type_anno, intermediate_type_inference.ListTypeAnnotation
            )

            type_parameter_by_items_id[id(list_type_anno.items)] = _type_parameter_name(
                arg
            )

        self._type_parameter_by_items_id = type_parameter_by_items_id

    def _type_parameter_of(
        self, type_annotation: intermediate_type_inference.TypeAnnotationUnion
    ) -> Optional[Identifier]:
        return self._type_parameter_by_items_id.get(id(type_annotation), None)

    def _transform_enumeration_literal(
        self, enumeration_name: Identifier, literal_name: Identifier
    ) -> Stripped:
        literal = golang_naming.enum_literal_name(
            enumeration_name=enumeration_name, literal_name=literal_name
        )
        return Stripped(f"ourtypes.{literal}")

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(golang_naming.variable_name(node.identifier)), None

        if node.identifier in self._argument_name_set:
            return Stripped(golang_naming.argument_name(node.identifier)), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_name = golang_naming.constant_name(node.identifier)
            return Stripped(f"ourconstants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(golang_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"ourtypes.{golang_naming.enum_name(node.identifier)}"),
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
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Transpile a verification function."""
    inference = type_inference.by_verification[verification]

    pointer_inferrer = golang_pointering.Inferrer(
        environment=inference.environment_with_args,
        type_map=inference.type_map,
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
        type_map=inference.type_map,
        is_pointer_map=pointer_inferrer.is_pointer_map,
        downcast_map=inference.downcast_map,
        environment=inference.environment_with_args,
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
    # The slices are invariant in Go, so we declare a type parameter for the items
    # of each generic sequence, see :py:func:`intermediate.generic_sequence_item_class`.
    # This way, the slices of the descendants can be passed without a copy.
    # The methods can not have type parameters in Go, so only the verification
    # functions have generic sequences.
    arg_defs: List[Stripped] = []
    type_parameter_defs: List[Stripped] = []
    remarks_on_generic_sequences: List[str] = []
    for arg in verification.arguments:
        arg_name = golang_naming.argument_name(arg.name)

        if intermediate.generic_sequence_item_class(arg) is None:
            arg_type = golang_common.generate_type(
                arg.type_annotation, types_package=Identifier("ourtypes")
            )
        else:
            list_type_anno = intermediate.beneath_optional(arg.type_annotation)
            assert isinstance(list_type_anno, intermediate.ListTypeAnnotation)

            item_type = golang_common.generate_type(
                list_type_anno.items, types_package=Identifier("ourtypes")
            )

            type_parameter = _type_parameter_name(arg)
            type_parameter_defs.append(Stripped(f"{type_parameter} {item_type}"))

            # NOTE (mristin):
            # The optional slices are not pointers in Go, as the slices are nilable.
            arg_type = Stripped(f"[]{type_parameter}")

            remarks_on_generic_sequences.append(
                f"The items of the argument {arg_name} are of the type parameter "
                f"{type_parameter} instead of {item_type} so that the slices of "
                f"the descendants of {item_type} can be passed without a copy, as "
                f"the slices are invariant in Go."
            )

        arg_defs.append(Stripped(f"{arg_name} {arg_type}"))

    writer = io.StringIO()

    if verification.description is not None:
        (comment, comment_errors,) = golang_description.generate_comment_for_signature(
            description=verification.description,
            context=golang_description.Context(
                package=golang_common.VERIFICATION_PACKAGE,
                cls_or_enum=None,
            ),
            extra_remarks=remarks_on_generic_sequences,
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
    elif len(remarks_on_generic_sequences) > 0:
        writer.write(
            golang_description.documentation_comment(
                Stripped("\n\n".join(remarks_on_generic_sequences))
            )
        )
        writer.write("\n")
    else:
        pass

    function_name = golang_naming.function_name(verification.name)

    type_parameters = (
        f"[{', '.join(type_parameter_defs)}]" if len(type_parameter_defs) > 0 else ""
    )

    if verification.returns is None:
        return_type_suffix = ""
    else:
        return_type = golang_common.generate_type(
            type_annotation=verification.returns, types_package=Identifier("ourtypes")
        )
        return_type_suffix = f" {return_type}"

    if len(arg_defs) == 0:
        writer.write(
            f"""\
func {function_name}{type_parameters}(){return_type_suffix} {{"""
        )
    else:
        arg_defs_joined = "\n".join(f"{arg_def}," for arg_def in arg_defs)
        writer.write(
            f"""\
func {function_name}{type_parameters}(
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
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
    ) -> None:
        """Initialize with the given values."""
        golang_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            is_pointer_map=is_pointer_map,
            downcast_map=downcast_map,
            environment=environment,
            types_package=Identifier("ourtypes"),
        )

        self._symbol_table = symbol_table

    def _transform_enumeration_literal(
        self, enumeration_name: Identifier, literal_name: Identifier
    ) -> Stripped:
        literal = golang_naming.enum_literal_name(
            enumeration_name=enumeration_name, literal_name=literal_name
        )
        return Stripped(f"ourtypes.{literal}")

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
            name = Stripped(f"ourconstants.{constant_name}")

        elif node.identifier in self._symbol_table.verification_functions_by_name:
            name = Stripped(golang_naming.function_name(node.identifier))

        elif (
            our_type := self._symbol_table.find_our_type(name=node.identifier),
            isinstance(our_type, intermediate.Enumeration),
        )[1]:
            name = Stripped(f"ourtypes.{golang_naming.enum_name(node.identifier)}")
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
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Translate the invariant from the meta-model into Golang code."""
    inference = type_inference.by_invariant[invariant]
    environment = inference.environment_with_self
    type_map = inference.type_map

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
        downcast_map=inference.downcast_map,
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
            parse_tree.IsInstance,
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


OurTypeExceptEnumerationAndNamedUnion = Union[
    intermediate.ConstrainedPrimitive,
    intermediate.AbstractClass,
    intermediate.ConcreteClass,
]
assert_union_without_excluded(
    original_union=intermediate.OurType,
    subset_union=OurTypeExceptEnumerationAndNamedUnion,
    # NOTE (mristin):
    # Named unions have no verification logic of their own (no properties or
    # invariants), so they are excluded here just like enumerations.
    excluded=[intermediate.Enumeration, intermediate.NamedUnion],
)


def _needs_verification(type_annotation: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether a value of ``type_annotation`` has anything to verify at any depth.

    In Go, we verify all our types, including the enumerations, as any string
    can be converted to an enumeration, all the JSON-able values, and all
    the integers, as an ``int64`` might lie outside the safe integer range
    of JSON.
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
        or (
            isinstance(type_anno, intermediate.PrimitiveTypeAnnotation)
            and type_anno.a_type is intermediate.PrimitiveType.INT
        )
        for type_anno in intermediate.over_type_annotation_and_nested_type_annotations(
            type_annotation
        )
    )


def _verification_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name ``type_anno`` by what its verification depends on.

    This follows the Polish notation of
    :py:func:`aas_core_codegen.golang.common.type_moniker`, except that a constrained primitive is named by itself
    (*e.g.*, ``NonEmptyXMLSerializableString``), and not by its constrainee
    (``string``), and a JSON object by its constrained key, if any (*e.g.*,
    ``jsonObjectByNonEmptyXMLSerializableString``).

    We need a moniker of our own since
    :py:func:`aas_core_codegen.golang.common.type_moniker` names the types by
    their Go type. For example, ``List[Non_empty_XML_serializable_string]`` and
    ``List[Id_short_type]`` would both be named ``ListOf_string``. However,
    they are verified differently, so they can not share one verification
    function.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ListOf_{_verification_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        return f"SetOf_{_verification_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        joined = "_".join(_verification_moniker(item) for item in type_anno.items)
        return f"TupleOf{len(type_anno.items)}_{joined}"

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.ConstrainedPrimitive
    ):
        return golang_naming.capital_camel_case(type_anno.our_type.name)

    if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        key_constrained_primitive = intermediate.try_constrained_primitive(
            type_anno.key
        )
        if key_constrained_primitive is not None:
            return (
                f"jsonObjectBy"
                f"{golang_naming.capital_camel_case(key_constrained_primitive.name)}"
            )

    if isinstance(type_anno, intermediate.OptionalTypeAnnotation):
        raise AssertionError(
            f"Unexpected optional to be verified: {type_anno}. The optionals "
            f"nested in the containers should have been refused in "
            f"parse._translate._verify_symbol_table."
        )

    return golang_common.leaf_moniker(type_anno)


def _verify_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the function verifying ``type_anno``.

    The underscore keeps the name apart from the names of the other verification
    functions, which go through
    :py:func:`aas_core_codegen.golang.naming.function_name` and never contain
    an underscore.
    """
    return Identifier(f"verify{_verification_moniker(type_anno)}")


def _prepend_index(index_expr: str) -> Stripped:
    """Generate the statement prepending the index segment to the path of ``err``."""
    return Stripped(
        f"""\
err.Path.PrependIndex(
{I}&ourreporting.IndexSegment{{
{II}Index: {index_expr},
{I}}},
)"""
    )


@require(lambda type_anno: _needs_verification(type_anno))
def _generate_verify_into(
    expr: str,
    type_anno: intermediate.TypeAnnotationUnion,
    segments: Sequence[Stripped],
) -> Stripped:
    """
    Generate the statements reporting the errors of the value at ``expr``.

    The ``segments`` are the statements prepending to the path of an error,
    the innermost first.

    An atomic value is verified by its own function. A container is delegated to
    its function, which verifies only one level and calls the function of its
    items by name. This way the verification is composed of plain functions, to
    any depth.
    """
    function: str

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(
            our_type, (intermediate.Enumeration, intermediate.ConstrainedPrimitive)
        ):
            function = golang_naming.function_name(
                Identifier(f"verify_{our_type.name}")
            )

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            function = "Verify"

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union has no verification function of its own -- it is
            # verified through the same general [Verify] dispatch function
            # as a class, over its underlying instance.
            function = "Verify"
            expr = f"{expr}.Underlying()"

        else:
            assert_never(our_type)

    elif (
        isinstance(type_anno, intermediate.PrimitiveTypeAnnotation)
        and type_anno.a_type is intermediate.PrimitiveType.INT
    ):
        function = "verifyInt64"

    elif isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        function = "verifyJsonValue"

    elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        function = "verifyJsonArray"

    elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        function = "verifyJsonObject"

    elif isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        function = _verify_container_name(type_anno)

    else:
        raise AssertionError(
            f"Unexpected type annotation with something to verify: {type_anno}. "
            f"The optionals nested in the containers should have been refused in "
            f"parse._translate._verify_symbol_table."
        )

    prepend_stmts = "\n".join(segments)

    blocks = [
        Stripped(
            f"""\
abort = {function}(
{I}{expr},
{I}func(err *VerificationError) bool {{
{II}{indent_but_first_line(prepend_stmts, II)}
{II}return onError(err)
{I}}},
)
if abort {{
{I}return
}}"""
        )
    ]

    # NOTE (mristin):
    # A bare ``str`` key has nothing to verify.
    if isinstance(
        type_anno, intermediate.JsonObjectTypeAnnotation
    ) and _needs_verification(type_anno.key):
        key_stmts = _generate_verify_into(
            expr="key",
            type_anno=type_anno.key,
            segments=[
                Stripped(
                    f"""\
err.Path.PrependKey(
{I}&ourreporting.KeySegment{{
{II}Key: key,
{I}}},
)"""
                ),
                *segments,
            ],
        )

        blocks.append(
            Stripped(
                f"""\
for _, key := range sortedKeysOfJsonObject({expr}) {{
{I}{indent_but_first_line(key_stmts, I)}
}}"""
            )
        )

    return Stripped("\n\n".join(blocks))


@require(lambda type_anno: _needs_verification(type_anno))
def _generate_verify_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the function verifying ``type_anno``."""
    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_stmts = _generate_verify_into(
            expr="item", type_anno=type_anno.items, segments=[_prepend_index("i")]
        )

        body = Stripped(
            f"""\
for i, item := range that {{
{I}{indent_but_first_line(item_stmts, I)}
}}"""
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        item_stmts = _generate_verify_into(
            expr="item", type_anno=type_anno.items, segments=[_prepend_index("i")]
        )

        # NOTE (mristin):
        # A set has no index, so we report the position of the item in
        # the sorted order. This is the index of the item in the serialized
        # array, so that the path resolves in the serialized data.
        loop_head = "for i, item := range "

        # NOTE (mristin):
        # The loop is indented by one tab in the body of the function.
        sorted_items_expr = golang_common.sorted_set_items_expr(
            "that",
            type_anno.items,
            column=golang_common.TAB_WIDTH + len(loop_head),
        )

        body = Stripped(
            f"""\
{loop_head}{sorted_items_expr} {{
{I}{indent_but_first_line(item_stmts, I)}
}}"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = Stripped(
            "\n\n".join(
                _generate_verify_into(
                    expr=f"that.Item{i + 1}",
                    type_anno=item_type_anno,
                    segments=[_prepend_index(str(i))],
                )
                for i, item_type_anno in enumerate(type_anno.items)
                if _needs_verification(item_type_anno)
            )
        )

    else:
        assert_never(type_anno)

    value_type = golang_common.generate_type(
        type_anno, types_package=golang_common.TYPES_PACKAGE
    )

    return Stripped(
        f"""\
// Verify the items of `that` recursively.
func {_verify_container_name(type_anno)}(
{I}that {value_type},
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}{indent_but_first_line(body, I)}

{I}return
}}"""
    )


def _generate_verify_json_value(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the functions verifying that a value is JSON-able.

    A JSON-able value is, recursively, exactly as JSON itself is defined, but
    ``JsonValue`` is an ``any``, so it rules out none of the two ways of not
    being one: a number which is not JSON-able (see ``IsSafeInteger`` and
    ``CheckJsonAbleFloat64`` in the common package) and a value of some other
    type altogether. Each is reported here, at any depth. A ``nil`` is a JSON null, and hence
    a JSON-able value.

    The path *within* a JSON-able value is a path of the error like any other:
    an index segment points at an item of a JSON-able array, and a key segment
    at a member of a JSON-able object. A key segment is what a name segment is
    not: it names a key which is known only at run time.
    """
    if not intermediate_uses.json_types(symbol_table):
        return []

    return [
        Stripped(
            f"""\
// Sort the keys of `that` so that the errors come in a stable order,
// as the iteration order of a Go map is deliberately random.
func sortedKeysOfJsonObject(that ourtypes.JsonObject) []string {{
{I}keys := make([]string, 0, len(that))
{I}for key := range that {{
{II}keys = append(keys, key)
{I}}}
{I}sort.Strings(keys)
{I}return keys
}}"""
        ),
        Stripped(
            f"""\
// Verify that `value` is a JSON-able value, at any depth.
//
// The path of an error is relative to `value`, and the caller is expected to
// prepend the way to it.
func verifyJsonValue(
{I}value ourtypes.JsonValue,
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}if value == nil {{
{II}return false
{I}}}

{I}// NOTE (mristin):
{I}// An int is widened to an int64 first, so that a single case below
{I}// handles both, as in the de/serialization.
{I}if integer, ok := value.(int); ok {{
{II}value = int64(integer)
{I}}}

{I}switch casted := value.(type) {{
{II}case bool:
{III}return false

{II}case string:
{III}return false

{II}case int64:
{III}if !ourcommon.IsSafeInteger(casted) {{
{IIII}return onError(
{IIIII}newVerificationError(ourcommon.NotJsonAbleIntegerMessage(casted)),
{IIII})
{III}}}
{III}return false

{II}case float64:
{III}if cause := ourcommon.CheckJsonAbleFloat64(casted); cause != "" {{
{IIII}return onError(newVerificationError(cause))
{III}}}
{III}return false

{II}case ourtypes.JsonArray:
{III}for i, item := range casted {{
{IIII}abort = verifyJsonValue(
{IIIII}item,
{IIIII}func(err *VerificationError) bool {{
{IIIIII}err.Path.PrependIndex(
{IIIIIII}&ourreporting.IndexSegment{{
{IIIIIIII}Index: i,
{IIIIIII}}},
{IIIIII})

{IIIIII}return onError(err)
{IIIII}}},
{IIII})
{IIII}if abort {{
{IIIII}return
{IIII}}}
{III}}}
{III}return false

{II}case ourtypes.JsonObject:
{III}for _, key := range sortedKeysOfJsonObject(casted) {{
{IIII}abort = verifyJsonValue(
{IIIII}casted[key],
{IIIII}func(err *VerificationError) bool {{
{IIIIII}err.Path.PrependKey(
{IIIIIII}&ourreporting.KeySegment{{
{IIIIIIII}Key: key,
{IIIIIII}}},
{IIIIII})

{IIIIII}return onError(err)
{IIIII}}},
{IIII})
{IIII}if abort {{
{IIIII}return
{IIII}}}
{III}}}
{III}return false

{II}default:
{III}return onError(
{IIII}newVerificationError(
{IIIII}fmt.Sprintf(
{IIIIII}"Expected a JSON-able value (a bool, a float64, an int, an int64, "+
{IIIIII}"a string, a JsonArray or a JsonObject), but got: %T",
{IIIIII}value,
{IIIII}),
{IIII}),
{III})
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Verify that `value` is a JSON-able array.
func verifyJsonArray(
{I}value ourtypes.JsonArray,
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}if value == nil {{
{II}return onError(
{III}newVerificationError(
{IIII}"Expected a JSON-able array, but got a nil",
{III}),
{II})
{I}}}

{I}return verifyJsonValue(value, onError)
}}"""
        ),
        Stripped(
            f"""\
// Verify that `value` is a JSON-able object.
func verifyJsonObject(
{I}value ourtypes.JsonObject,
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}if value == nil {{
{II}return onError(
{III}newVerificationError(
{IIII}"Expected a JSON-able object, but got a nil",
{III}),
{II})
{I}}}

{I}return verifyJsonValue(value, onError)
}}"""
        ),
    ]


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_verify_class(
    cls: intermediate.ConcreteClass,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the verification function for the given concrete class."""
    errors: List[Error] = []
    blocks: List[Stripped] = []

    # region Generate the non-recursive part verifying the invariants

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

    # endregion

    # region Recurse into properties

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        getter_name = golang_naming.getter_name(prop.name)
        prop_name = golang_naming.property_name(prop.name)

        block: Optional[Stripped] = None
        if _needs_verification(type_anno):
            pointer_prefix = (
                "*" if golang_pointering.is_pointer_type(prop.type_annotation) else ""
            )

            prop_name_literal = golang_common.string_literal(prop_name)

            block = _generate_verify_into(
                expr=f"{pointer_prefix}that.{getter_name}()",
                type_anno=type_anno,
                segments=[
                    Stripped(
                        f"""\
err.Path.PrependName(
{I}&ourreporting.NameSegment{{
{II}Name: {prop_name_literal},
{I}}},
)"""
                    )
                ],
            )

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            if block is not None:
                block = Stripped(
                    f"""\
if that.{getter_name}() != nil {{
{I}{indent_but_first_line(block, I)}
}}"""
                )

        elif (
            intermediate.try_primitive_type(type_anno)
            is intermediate.PrimitiveType.BYTEARRAY
            or isinstance(
                type_anno,
                (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
            )
            or (
                isinstance(type_anno, intermediate.OurTypeAnnotation)
                and isinstance(
                    type_anno.our_type,
                    (
                        intermediate.AbstractClass,
                        intermediate.ConcreteClass,
                        intermediate.NamedUnion,
                    ),
                )
            )
        ):
            # NOTE (mristin):
            # Go represents these values by nilable references, so we have to
            # check that a required property is actually set.
            else_block = (
                ""
                if block is None
                else f""" else {{
{I}{indent_but_first_line(block, I)}
}}"""
            )

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
}}{else_block}"""
            )

        if block is not None:
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
// Verify `that` instance of [ourtypes.{interface_name}].
//
// You have to supply the callback `onError` to iterate over the errors.
// If `onError` returns abort `true`, this function will abort
// further verification as well, and return abort `true`. Otherwise,
// abort `false` is returned.
func {function_name}(
{I}that ourtypes.{interface_name},
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
    case_blocks: List[Stripped] = []

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
case ourtypes.{literal}:
{I}abort = {verification_function}(
{II}that.(ourtypes.{interface_name}),
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
{I}that ourtypes.IClass,
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
{I}that < ourtypes.{first_literal} ||
{I}that > ourtypes.{last_literal} {{
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
{I}that ourtypes.{enum_name},
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


#: Report an integer ``that`` outside the safe integer range of JSON, as
#: the statements of a verification function
_SAFE_INTEGER_CHECK: Final[Stripped] = Stripped(
    f"""\
if !ourcommon.IsSafeInteger(that) {{
{I}abort = onError(newVerificationError(ourcommon.UnsafeIntegerMessage(that)))
{I}if abort {{
{II}return
{I}}}
}}"""
)


def _generate_verify_int64() -> Stripped:
    """Generate the function verifying an ``int64`` as an item or a property."""
    return Stripped(
        f"""\
// Verify that `that` integer lies in the safe integer range of JSON, as
// checked by [ourcommon.IsSafeInteger] in the serialization as well.
func verifyInt64(
{I}that int64,
{I}onError func(*VerificationError) bool,
) (abort bool) {{
{I}{indent_but_first_line(_SAFE_INTEGER_CHECK, I)}

{I}return
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

    # NOTE (mristin):
    # An integer outside the safe range can not be serialized to JSON, so we
    # report it before the invariants, with the same check as the serialization.
    if constrained_primitive.constrainee is intermediate.PrimitiveType.INT:
        blocks.insert(0, _SAFE_INTEGER_CHECK)

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


#: Stand in for the import block, which is filled in at the very end: it
#: depends on what the generated code actually names, and an unused import does
#: not compile in Go.
_IMPORT_PLACEHOLDER = Stripped("")


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
    type_inference: intermediate_type_inference.TypeInference,
    spec_impls: specific_implementations.SpecificImplementations,
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code of verification logic."""
    errors: List[Error] = []

    constants_url_literal = golang_common.string_literal(f"{repo_url}/constants")

    common_url_literal = golang_common.string_literal(f"{repo_url}/common")

    reporting_url_literal = golang_common.string_literal(f"{repo_url}/reporting")

    stringification_url_literal = golang_common.string_literal(
        f"{repo_url}/stringification"
    )

    types_url_literal = golang_common.string_literal(f"{repo_url}/types")

    blocks: List[Stripped] = [
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
        _IMPORT_PLACEHOLDER,
        Stripped(
            f"""\
// Represent a verification violation.
//
// Implements `error`.
type VerificationError struct{{
{I}Path *ourreporting.Path
{I}Message string
}}"""
        ),
        Stripped(
            f"""\
func newVerificationError(message string) *VerificationError {{
{I}return &VerificationError{{
{II}Path: &ourreporting.Path{{}},
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
{I}return ourreporting.ToGolangPath(ve.Path)
}}"""
        ),
    ]

    # NOTE (mristin):
    # The internal verification functions are unexported, so their names might
    # collide with the unexported names that we generate in the same package.
    origin_by_unexported_name: MutableMapping[str, str] = {
        "newVerificationError": "our helper function to create verification errors",
        "verifyInt64": "our helper function to verify integers",
        "verifyJsonValue": "our helper function to verify JSON-able values",
        "verifyJsonArray": "our helper function to verify JSON-able arrays",
        "verifyJsonObject": "our helper function to verify JSON-able objects",
        "sortedKeysOfJsonObject": (
            "our helper function to sort the keys of JSON-able objects"
        ),
    }

    for verification in symbol_table.verification_functions:
        if isinstance(verification, intermediate.PatternVerification):
            origin = (
                f"the unexported name generated for the pattern verification "
                f"function {verification.name!r}"
            )

            origin_by_unexported_name[
                golang_naming.private_function_name(
                    Identifier(f"construct_{verification.name}")
                )
            ] = origin

            origin_by_unexported_name[
                golang_naming.private_constant_name(
                    Identifier(f"{verification.name}_re")
                )
            ] = origin

    for verification in symbol_table.verification_functions:
        if verification.visibility is not intermediate.Visibility.INTERNAL:
            continue

        verification_name = golang_naming.function_name(verification.name)
        colliding_origin = origin_by_unexported_name.get(verification_name)
        if colliding_origin is not None:
            errors.append(
                Error(
                    verification.parsed.node,
                    f"The name of the internal verification function "
                    f"{verification.name!r} collides in Go with {colliding_origin}: "
                    f"{verification_name}",
                )
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
                type_inference=type_inference,
            )

            if error is not None:
                errors.append(error)
            else:
                assert implementation is not None
                blocks.append(implementation)

        else:
            assert_never(verification)

    blocks.extend(_generate_verify_json_value(symbol_table=symbol_table))

    if intermediate_uses.integers(symbol_table):
        blocks.append(_generate_verify_int64())

    for cls in symbol_table.concrete_classes:
        block, underlying_errors = _generate_verify_class(
            cls=cls, symbol_table=symbol_table, type_inference=type_inference
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

    observed_monikers: Set[str] = set()

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ) or not _needs_verification(type_anno):
                    continue

                moniker = _verification_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)
                blocks.append(_generate_verify_container(type_anno=type_anno))

    for enumeration in symbol_table.enumerations:
        block = _generate_verify_enumeration(enumeration=enumeration)
        blocks.append(block)

    for constrained_primitive in symbol_table.constrained_primitives:
        block, underlying_errors = _generate_verify_constrained_primitive(
            constrained_primitive=constrained_primitive,
            symbol_table=symbol_table,
            type_inference=type_inference,
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

    import_index = blocks.index(_IMPORT_PLACEHOLDER)

    import_lines: List[str] = []
    for module, literal in (
        ("big", f'{I}"math/big"'),
        ("fmt", f'{I}"fmt"'),
        ("math", f'{I}"math"'),
        ("regexp", f'{I}"regexp"'),
        ("sort", f'{I}"sort"'),
        ("strconv", f'{I}"strconv"'),
        ("strings", f'{I}"strings"'),
        ("ourcommon", f"{I}ourcommon {common_url_literal}"),
        ("ourconstants", f"{I}ourconstants {constants_url_literal}"),
        ("ourreporting", f"{I}ourreporting {reporting_url_literal}"),
        (
            "ourstringification",
            f"{I}ourstringification {stringification_url_literal}",
        ),
        ("ourtypes", f"{I}ourtypes {types_url_literal}"),
    ):
        if golang_common.names_package(blocks, module):
            import_lines.append(literal)

    blocks[import_index] = Stripped("import (\n" + "\n".join(import_lines) + "\n)")

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
