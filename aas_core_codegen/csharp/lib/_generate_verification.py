"""Generate code of verification logic."""
import io
import textwrap
from typing import (
    Final,
    Tuple,
    Optional,
    List,
    Sequence,
    Set,
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
)
from aas_core_codegen.csharp import (
    common as csharp_common,
    naming as csharp_naming,
    description as csharp_description,
    transpilation as csharp_transpilation,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.intermediate import uses as intermediate_uses
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
                    f"Verification/{func.name}.cs"
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


class _PatternVerificationTranspiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a statement of a pattern verification into C#."""

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
        """Transform the values of a joined string to a C# string literal."""
        if all(isinstance(value, str) for value in values):
            return (
                Stripped(csharp_common.string_literal("".join(values))),  # type: ignore
                None,
            )

        needs_interpolation = False

        parts: List[str] = []
        for value in values:
            if isinstance(value, str):
                string_literal = csharp_common.string_literal(
                    value.replace("{", "{{").replace("}", "}}")
                )

                # We need to remove double-quotes since we are joining everything
                # ourselves later.

                assert string_literal.startswith('"') and string_literal.endswith('"')

                string_literal_wo_quotes = string_literal[1:-1]
                parts.append(string_literal_wo_quotes)

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self.transform(value.value)
                if error is not None:
                    return None, error
                assert code is not None

                assert (
                    "\n" not in code
                ), f"New-lines are not expected in formatted values, but got: {code}"

                needs_interpolation = True
                parts.append(f"{{{code}}}")
            else:
                assert_never(value)

        writer = io.StringIO()

        if needs_interpolation:
            writer.write('$"')
        else:
            writer.write('"')

        for part in parts:
            writer.write(part)

        writer.write('"')

        return Stripped(writer.getvalue()), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if isinstance(node.value, str):
            # NOTE (mristin):
            # We assume that all the string constants are valid regular expressions.

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
            parse_retree.fix_for_utf16_regex_in_place(regex)

            # NOTE (mristin):
            # Strictly speaking, this is a joined string with a single value, a string
            # literal.
            return self._transform_joined_str_values(
                values=parse_retree.render(regex=regex)
            )
        else:
            raise AssertionError(f"Unexpected {node=}")

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return Stripped(csharp_naming.variable_name(node.identifier)), None

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
        parse_retree.fix_for_utf16_regex_in_place(regex)

        return self._transform_joined_str_values(
            values=parse_retree.render(regex=regex)
        )

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        assert isinstance(node.target, parse_tree.Name)
        variable = csharp_naming.variable_name(node.target.identifier)
        code, error = self.transform(node.value)
        if error is not None:
            return None, error
        assert code is not None

        if node.target.identifier in self.defined_variables:
            return Stripped(f"{variable} = {code};"), None

        else:
            self.defined_variables.add(node.target.identifier)
            return Stripped(f"var {variable} = {code};"), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_pattern_verification(
    verification: intermediate.PatternVerification,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the verification function that checks the regular expressions."""
    # NOTE (mristin):
    # We assume that we performed all the checks at the intermediate stage.

    construct_name = csharp_naming.private_method_name(
        Identifier(f"construct_{verification.name}")
    )

    blocks: List[Stripped] = []

    # region Construct block

    writer = io.StringIO()
    writer.write(
        f"""\
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
[CodeAnalysis.SuppressMessageAttribute("ReSharper", "IdentifierTypo")]
[CodeAnalysis.SuppressMessage("ReSharper", "StringLiteralTypo")]
private static Regex {construct_name}()
{{
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
        writer.write(textwrap.indent(f"return new Regex({pattern_expr});\n", I))
    else:
        writer.write(textwrap.indent(f"return new Regex(\n{I}{pattern_expr});\n", I))

    writer.write("}")

    blocks.append(Stripped(writer.getvalue()))

    # endregion

    # region Initialize the regex

    # NOTE (mristin):
    # We make this property look "public" since it is static and read-only.
    regex_name = csharp_naming.property_name(Identifier(f"regex_{verification.name}"))

    blocks.append(
        Stripped(f"private static readonly Regex {regex_name} = {construct_name}();")
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

    arg_name = csharp_naming.argument_name(verification.arguments[0].name)

    writer = io.StringIO()
    if verification.description is not None:
        comment, comment_errors = csharp_description.generate_comment_for_signature(
            verification.description
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

    method_name = csharp_naming.method_name(verification.name)

    modifier = (
        "internal"
        if verification.visibility is intermediate.Visibility.INTERNAL
        else "public"
    )

    writer.write(
        f"""\
{modifier} static bool {method_name}(string {arg_name})
{{
{I}return {regex_name}.IsMatch({arg_name});
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


class _TranspilableVerificationTranspiler(csharp_transpilation.Transpiler):
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
        environment: intermediate_type_inference.Environment,
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
    ) -> None:
        """Initialize with the given values."""
        csharp_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            environment=environment,
            downcast_map=downcast_map,
        )

        self._symbol_table = symbol_table

        self._argument_name_set = frozenset(arg.name for arg in verification.arguments)

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(csharp_naming.variable_name(node.identifier)), None

        if node.identifier in self._argument_name_set:
            return Stripped(csharp_naming.variable_name(node.identifier)), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_as_prop = csharp_naming.property_name(node.identifier)
            return Stripped(f"Our.Constants.{constant_as_prop}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(csharp_naming.method_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(csharp_naming.enum_name(node.identifier)), None

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to C#. We could not find it neither in the constants, nor in "
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

    transpiler = _TranspilableVerificationTranspiler(
        type_map=inference.type_map,
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
    # The ``List<T>`` is invariant in C#, so we declare the generic sequences,
    # see :py:func:`intermediate.generic_sequence_item_class`, as the covariant
    # ``IReadOnlyList<T>``. This way, the lists of the descendants can be passed
    # without a copy, as ``List<T>`` implements ``IReadOnlyList<T>``.
    arg_defs: List[Stripped] = []
    remarks_on_generic_sequences: List[str] = []
    for arg in verification.arguments:
        arg_name = csharp_naming.argument_name(arg.name)

        if intermediate.generic_sequence_item_class(arg) is None:
            arg_type = csharp_common.generate_type(arg.type_annotation)
        else:
            list_type_anno = intermediate.beneath_optional(arg.type_annotation)
            assert isinstance(list_type_anno, intermediate.ListTypeAnnotation)

            item_type = csharp_common.generate_type(list_type_anno.items)

            arg_type = Stripped(f"IReadOnlyList<{item_type}>")
            if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
                arg_type = Stripped(f"{arg_type}?")

            remarks_on_generic_sequences.append(
                f"The argument {arg_name} is declared as the covariant "
                f"IReadOnlyList<{item_type}> instead of the invariant "
                f"List<{item_type}> so that the lists of the descendants of "
                f"{item_type} can be passed without a copy."
            )

        arg_defs.append(Stripped(f"{arg_type} {arg_name}"))

    writer = io.StringIO()
    if verification.description is not None:
        comment, comment_errors = csharp_description.generate_comment_for_signature(
            verification.description, extra_remarks=remarks_on_generic_sequences
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
            csharp_description.generate_comment_for_remarks(
                remarks_on_generic_sequences
            )
        )
        writer.write("\n")
    else:
        pass

    method_name = csharp_naming.method_name(verification.name)

    modifier = (
        "internal"
        if verification.visibility is intermediate.Visibility.INTERNAL
        else "public"
    )

    if verification.returns is None:
        return_type = "void"
    else:
        return_type = csharp_common.generate_type(type_annotation=verification.returns)

    if len(arg_defs) == 0:
        writer.write(
            f"""\
{modifier} static {return_type} {method_name}()
{{"""
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

        writer.write("\n)\n{")

    for stmt in body:
        writer.write("\n")
        writer.write(textwrap.indent(stmt, I))

    if len(body) > 0:
        writer.write("\n")

    writer.write(f"}}  // {modifier} static {return_type} {method_name}")

    return Stripped(writer.getvalue()), None


class _InvariantTranspiler(csharp_transpilation.Transpiler):
    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        environment: intermediate_type_inference.Environment,
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        symbol_table: intermediate.SymbolTable,
    ) -> None:
        """Initialize with the given values."""
        csharp_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            environment=environment,
            downcast_map=downcast_map,
        )

        self._symbol_table = symbol_table

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(csharp_naming.variable_name(node.identifier)), None

        if node.identifier == "self":
            # The ``that`` refers to the argument of the verification function.
            return Stripped("that"), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_as_prop = csharp_naming.property_name(node.identifier)
            return Stripped(f"Our.Constants.{constant_as_prop}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(csharp_naming.method_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(csharp_naming.enum_name(node.identifier)), None

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to C#. We could not find it "
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

    transpiler = _InvariantTranspiler(
        type_map=inference.type_map,
        environment=inference.environment_with_self,
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
        writer.write("))\n{\n")
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

        writer.write(f"if ({not_expr})\n{{\n")

    writer.write(
        textwrap.indent(
            f"""\
yield return new Reporting.Error(
{I}"Invariant violated:\\n" +
""",
            I,
        )
    )

    # NOTE (mristin):
    # We need to wrap the description in multiple literals as a single long
    # string literal is often too much for the readability.
    invariant_description_lines = wrap_text_into_lines(invariant.description)

    for i, literal in enumerate(invariant_description_lines):
        if i < len(invariant_description_lines) - 1:
            writer.write(f"{II}{csharp_common.string_literal(literal)} +\n")
        else:
            writer.write(f"{II}{csharp_common.string_literal(literal)});")

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


#: Define the helper for ``len`` on tuples.
def _generate_enum_value_sets(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate a class that pre-computes the sets of allowed enumeration literals."""
    blocks: List[Stripped] = []

    for enum in symbol_table.enumerations:
        enum_name = csharp_naming.enum_name(enum.name)

        if len(enum.literals) == 0:
            blocks.append(
                Stripped(
                    f"""\
internal static readonly HashSet<int> For{enum_name} = new HashSet<int>();"""
                )
            )
        else:
            hash_set_writer = io.StringIO()
            hash_set_writer.write(
                f"""\
internal static readonly HashSet<int> For{enum_name} = new HashSet<int>\n{{\n
"""
            )

            for i, literal in enumerate(enum.literals):
                literal_name = csharp_naming.enum_literal_name(literal.name)
                hash_set_writer.write(f"{I}(int)Our.{enum_name}.{literal_name}")
                if i < len(enum.literals) - 1:
                    hash_set_writer.write(",\n")
                else:
                    hash_set_writer.write("\n")

            hash_set_writer.write("};")

            blocks.append(Stripped(hash_set_writer.getvalue()))

    writer = io.StringIO()
    writer.write(
        """\
/// <summary>
/// Hash allowed enum values for efficient validation of enums.
/// </summary>
internal static class EnumValueSet
{
"""
    )
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal static class EnumValueSet")

    return Stripped(writer.getvalue())


def _generate_verify_method(our_type: intermediate.OurType) -> Stripped:
    """Generate the name of the ``Verification.Verify*`` method."""
    if isinstance(our_type, intermediate.Enumeration):
        name = csharp_naming.enum_name(our_type.name)
        return Stripped(f"Verification.Verify{name}")

    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        name = csharp_naming.class_name(our_type.name)
        return Stripped(f"Verification.Verify{name}")

    elif isinstance(
        our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    ):
        # A named union has no invariants of its own; ``Verification.Verify``
        # has an overload for it (see
        # :py:func:`_generate_union_verify_helper`) that recurses into
        # the underlying instance, so it is dispatched exactly like a class.
        return Stripped("Verification.Verify")
    else:
        assert_never(our_type)

    raise AssertionError("Unexpected execution path")


def _is_int(type_annotation: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether ``type_annotation`` is the bare primitive ``int``.

    A constrained primitive over ``int`` is not included, as it is verified by
    its own method, which checks the safe integer range itself.
    """
    return (
        isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation)
        and type_annotation.a_type is intermediate.PrimitiveType.INT
    )


def _needs_verification(type_annotation: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether a value of ``type_annotation`` has anything to verify at any depth.

    In C#, we verify all our types, including the enumerations, as any integer
    can be cast to an enumeration, and all the JSON-able values. We also verify
    the integers, since a ``long`` outside the safe integer range can not be
    serialized to JSON, and the verification has to catch whatever
    the serialization would refuse.

    This check is specific to C#, and hence does not live in
    :py:mod:`aas_core_codegen.intermediate`: other targets verify different
    types. For example, the Python SDK relies on mypy for the enumerations,
    and does not verify them at all.
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
        or _is_int(type_anno)
        for type_anno in intermediate.over_type_annotation_and_nested_type_annotations(
            type_annotation
        )
    )


def _verification_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name ``type_anno`` by what its verification depends on.

    This follows the Polish notation of
    :py:func:`aas_core_codegen.csharp.common.type_moniker`, except that
    a constrained primitive is named by itself (*e.g.*, ``NonEmptyString``),
    and not by its constrainee (``string``), and a JSON object by its
    constrained key, if any (*e.g.*, ``jsonObjectByNonEmptyString``).

    We need a moniker of our own since
    :py:func:`aas_core_codegen.csharp.common.type_moniker` names the types by
    their C# type. For example, ``List[Non_empty_string]`` and
    ``List[Id_short_type]`` would both be named ``ListOf_string``. However,
    they are verified differently, so they can not share one verification
    method.

    We deliberately do not change
    :py:func:`aas_core_codegen.csharp.common.leaf_moniker` itself to
    distinguish the constrained primitives. The JSON and XML de/serialization
    key their cached de/serializers by the moniker as well, and there
    the C# type is all that matters. For example, the XML de-serialization
    of ``aas-core-meta`` V3 would then emit about 20 identical
    ``Read_...`` content readers, one per constrained primitive, instead of
    a single ``Read_string``.
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
        return csharp_naming.class_name(type_anno.our_type.name)

    if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        key_constrained_primitive = intermediate.try_constrained_primitive(
            type_anno.key
        )
        if key_constrained_primitive is not None:
            return (
                f"jsonObjectBy"
                f"{csharp_naming.class_name(key_constrained_primitive.name)}"
            )

    return csharp_common.leaf_moniker(type_anno)


# NOTE (mristin):
# The verification of a bare ``long`` is named by its moniker just like
# the verification of a container (*e.g.*, ``Verify_ListOf_long``), so that it
# can never clash with the verification of a constrained primitive, say,
# named ``Long``.
_VERIFY_LONG: Final[Identifier] = Identifier(
    f"Verify_{csharp_common.PRIMITIVE_TYPE_TO_MONIKER[intermediate.PrimitiveType.INT]}"
)


def _verify_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """Name the method of ``Verification`` verifying ``type_anno``."""
    return Identifier(f"Verify_{_verification_moniker(type_anno)}")


@require(lambda type_anno: _needs_verification(type_anno))
def _generate_verify_into(
    expr: str, type_anno: intermediate.TypeAnnotationUnion, segments: Sequence[str]
) -> Stripped:
    """
    Generate the statements yielding the errors of the value at ``expr``.

    The ``segments`` are prepended to the path of each error, the innermost first.

    An atomic value is verified by its own method. A container is delegated to
    its method in ``Verification``, which verifies only one level and calls
    the method of its items by name. This way the verification is composed of
    plain functions, to any depth, without any delegates.
    """
    blocks: List[Stripped] = []

    method: str
    args: List[str]

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        method = _generate_verify_method(our_type=type_anno.our_type)
        args = [expr]

    elif _is_int(type_anno):
        method = f"Verification.{_VERIFY_LONG}"
        args = [expr]

    elif isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        method = "JsonValueVerification.Verify"
        args = [expr, "JsonValueVerification.ExpectedShape.Any"]

    elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        method = "JsonValueVerification.Verify"
        args = [expr, "JsonValueVerification.ExpectedShape.Array"]

    elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        method = "JsonValueVerification.Verify"
        args = [expr, "JsonValueVerification.ExpectedShape.Object"]

    elif isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        method = f"Verification.{_verify_container_name(type_anno)}"
        args = [expr]

    else:
        raise AssertionError(
            f"Unexpected type annotation with something to verify: {type_anno}. "
            f"The optionals nested in the containers should have been refused in "
            f"parse._translate._verify_symbol_table."
        )

    args_joined = ", ".join(args)

    foreach_header = f"foreach (var error in {method}({args_joined}))"
    # Heuristic to break the lines, very rudimentary
    if len(foreach_header) > 70:
        foreach_header = f"""\
foreach (
{I}var error in {method}(
{II}{args_joined}))"""

    prepend_stmts = "\n".join(
        f"""\
error.PrependSegment(
{I}{segment});"""
        for segment in segments
    )

    blocks.append(
        Stripped(
            f"""\
{foreach_header}
{{
{I}{indent_but_first_line(prepend_stmts, I)}
{I}yield return error;
}}"""
        )
    )

    # NOTE (mristin):
    # A bare ``str`` key has nothing to verify.
    if isinstance(
        type_anno, intermediate.JsonObjectTypeAnnotation
    ) and _needs_verification(type_anno.key):
        key_stmts = _generate_verify_into(
            expr="member.Key",
            type_anno=type_anno.key,
            segments=["new Reporting.KeySegment(member.Key)", *segments],
        )

        blocks.append(
            Stripped(
                f"""\
foreach (var member in {expr})
{{
{I}{indent_but_first_line(key_stmts, I)}
}}"""
            )
        )

    return Stripped("\n\n".join(blocks))


@require(lambda type_anno: _needs_verification(type_anno))
def _generate_verify_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the method of ``Verification`` verifying ``type_anno``."""
    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_stmts = _generate_verify_into(
            expr="item",
            type_anno=type_anno.items,
            segments=["new Reporting.IndexSegment(index)"],
        )

        body = Stripped(
            f"""\
int index = 0;
foreach (var item in that)
{{
{I}{indent_but_first_line(item_stmts, I)}
{I}index++;
}}"""
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        item_stmts = _generate_verify_into(
            expr="item",
            type_anno=type_anno.items,
            segments=["new Reporting.IndexSegment(index)"],
        )

        comparison = csharp_common.set_items_comparison(type_anno.items)

        # NOTE (mristin):
        # A set has no index of its own, so we report the position of the item
        # in the sorted order, which is the index in the serialized array.
        body = Stripped(
            f"""\
int index = 0;
foreach (
{I}var item in {csharp_common.COMMON_CLASS}.SetHelpers.Sorted(
{II}that,
{II}{comparison}))
{{
{I}{indent_but_first_line(item_stmts, I)}
{I}index++;
}}"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = Stripped(
            "\n\n".join(
                _generate_verify_into(
                    expr=f"that.Item{i + 1}",
                    type_anno=item_type_anno,
                    segments=[f"new Reporting.IndexSegment({i})"],
                )
                for i, item_type_anno in enumerate(type_anno.items)
                if _needs_verification(item_type_anno)
            )
        )

    else:
        assert_never(type_anno)

    name = _verify_container_name(type_anno)
    value_type = csharp_common.generate_type(
        type_anno, our_type_qualifier=Stripped("Our")
    )

    return Stripped(
        f"""\
/// <summary>
/// Verify the items of <paramref name="that" /> recursively.
/// </summary>
private static IEnumerable<Reporting.Error> {name}(
{I}{value_type} that)
{{
{I}{indent_but_first_line(body, I)}
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

    name = csharp_naming.class_name(cls.name)

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

        prop_name = csharp_naming.property_name(prop.name)

        # NOTE (mristin):
        # An optional of a value type, such as an enumeration or a tuple, is
        # a System.Nullable, so we have to unwrap it before we can verify it.
        source_expr = f"that.{prop_name}"
        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and csharp_common.is_value_type(type_anno):
            source_expr = f"that.{prop_name}.Value"

        block = _generate_verify_into(
            expr=source_expr,
            type_anno=type_anno,
            segments=[
                (
                    f"new Reporting.NameSegment("
                    f"{csharp_common.string_literal(prop.json_name)})"
                )
            ],
        )

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            condition = (
                f"that.{prop_name}.HasValue"
                if csharp_common.is_value_type(type_anno)
                else f"that.{prop_name} != null"
            )

            block = Stripped(
                f"""if ({condition})
{{
{I}{indent_but_first_line(block, I)}
}}"""
            )

        blocks.append(block)

    if len(blocks) == 0:
        blocks.append(
            Stripped(
                f"""\
// No verification has been defined for {name}.
yield break;"""
            )
        )

    writer = io.StringIO()

    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    writer.write(
        f"""\
[CodeAnalysis.SuppressMessage("ReSharper", "NegativeEqualityExpression")]
public override IEnumerable<Reporting.Error> {transform_name}(
{I}Our.{interface_name} that
)
{{
"""
    )

    for i, stmt in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(stmt, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


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
            # A named union is never double-dispatched here directly -- it is
            # unwrapped by its own ``Verification.Verify`` overload instead
            # (see :py:func:`_generate_union_verify_helper`).
            pass

        else:
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    writer.write(
        f"""\
private class Transformer
{I}: Visitation.AbstractTransformer<IEnumerable<Reporting.Error>>
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // private class Transformer")

    return Stripped(writer.getvalue()), None


def _generate_verify_enumeration(enumeration: intermediate.Enumeration) -> Stripped:
    """Generate the verify method to check that an enum is valid."""
    name = csharp_naming.enum_name(enumeration.name)

    return Stripped(
        f"""\
/// <summary>
/// Verify that <paramref name="that" /> is a valid enumeration value.
/// </summary>
public static IEnumerable<Reporting.Error> Verify{name}(
{I}Our.{name} that)
{{
{I}if (!EnumValueSet.For{name}.Contains(
{II}(int)that))
{I}{{
{II}yield return new Reporting.Error(
{III}$"Invalid {name}: {{that}}");
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

    if constrained_primitive.constrainee is intermediate.PrimitiveType.INT:
        # NOTE (mristin):
        # The constrainee has to be serializable to JSON, regardless of
        # the invariants, so we check the safe integer range first.
        blocks.insert(
            0,
            Stripped(
                f"""\
foreach (var error in {_VERIFY_LONG}(that))
{{
{I}yield return error;
}}"""
            ),
        )

    if len(blocks) == 0:
        blocks.append(
            Stripped(
                """\
// There is no verification specified.
yield break;"""
            )
        )

    # NOTE (mristin):
    # Constrained primitives are not really classes, but we simply use the naming
    # for classes here since we need to pick *something*.
    name = csharp_naming.class_name(constrained_primitive.name)

    that_type = csharp_common.PRIMITIVE_TYPE_MAP[constrained_primitive.constrainee]

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Verify the constraints of <paramref name="that" />.
/// </summary>
public static IEnumerable<Reporting.Error> Verify{name} (
{I}{that_type} that)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    assert len(errors) == 0
    return Stripped(writer.getvalue()), None


def _generate_union_verify_helper() -> Stripped:
    """
    Generate a single ``Verify`` overload shared by every named union.

    A named union is not itself an ``Our.IClass``, so it can not be passed to
    the general ``Verify(Our.IClass that)`` dispatch function directly. We add
    this overload, next to it, so that call sites can keep calling ``Verify``
    directly on a named union, exactly as they would on a class instance.

    Dispatching over the common, non-generic ``Our.IUnion`` (see ``generate()``
    in ``_generate_types.py``) instead of the union's own type means we need
    only this one overload for *all* named unions, not one per union.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
public static IEnumerable<Reporting.Error> Verify(Our.IUnion that)
{{
{I}foreach (var error in Verify(that.Underlying))
{I}{{
{II}yield return error;
{I}}}
}}"""
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
    type_inference: intermediate_type_inference.TypeInference,
    namespace: csharp_common.NamespaceIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code of verification logic.

    The ``namespace`` defines the base C# namespace of the generated code.
    """
    using_directives: List[Stripped] = []
    using_directives.extend(
        csharp_common.generate_using_our_directive_if_necessary(namespace)
    )

    # NOTE (mristin):
    # A verification function can take a JSON-able value, and an invariant can
    # name one, so the alias is needed here just as it is in the types.
    json_using_directive = (
        "\nusing Nodes = System.Text.Json.Nodes;"
        if intermediate_uses.json_types(symbol_table)
        else ""
    )

    using_directives.append(
        Stripped(
            f"""\
using CodeAnalysis = System.Diagnostics.CodeAnalysis;
using Regex = System.Text.RegularExpressions.Regex;{json_using_directive}

using System.Collections.Generic;  // can't alias
using System.Linq;  // can't alias"""
        )
    )

    blocks: List[Stripped] = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
    ]

    verification_blocks: List[Stripped] = []
    errors: List[Error] = []

    for verification in symbol_table.verification_functions:
        if isinstance(verification, intermediate.ImplementationSpecificVerification):
            implementation_key = specific_implementations.ImplementationKey(
                f"Verification/{verification.name}.cs"
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
                verification=verification
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
            f"""\
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
private static readonly Verification.Transformer _transformer = (
{I}new Verification.Transformer());"""
        )
    )

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
/// <summary>
/// Verify the constraints of <paramref name="that" /> recursively.
/// </summary>
/// <param name="that">
/// The instance of the meta-model to be verified
/// </param>
public static IEnumerable<Reporting.Error> Verify(Our.IClass that)
{{
{I}foreach (var error in _transformer.Transform(that))
{I}{{
{II}yield return error;
{I}}}
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
            # the single shared ``Verify(Our.IUnion)`` overload instead (see
            # :py:func:`_generate_union_verify_helper`).
            pass

        else:
            assert_never(our_type)

    if len(symbol_table.named_unions) > 0:
        verification_blocks.append(_generate_union_verify_helper())

    if intermediate_uses.integers(symbol_table):
        verification_blocks.append(
            Stripped(
                f"""\
/// <summary>
/// Report that the integer <paramref name="value" /> is not a safe integer.
/// </summary>
/// <remarks>
/// See <see cref="Common.IsSafeInteger(long)" /> for what a safe integer is.
/// </remarks>
/// <param name="value">integer outside the safe integer range</param>
/// <returns>the cause of the error</returns>
internal static string UnsafeIntegerMessage(System.IFormattable value)
{{
{I}return $"Expected an integer, but got {{value}}, " +
{II}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]";
}}"""
            )
        )

        verification_blocks.append(
            Stripped(
                f"""\
/// <summary>
/// Verify that <paramref name="that" /> lies in the safe integer range.
/// </summary>
/// <remarks>
/// See <see cref="Common.IsSafeInteger(long)" /> for what a safe integer is.
/// </remarks>
private static IEnumerable<Reporting.Error> {_VERIFY_LONG}(
{I}long that)
{{
{I}if (!Common.IsSafeInteger(that))
{I}{{
{II}yield return new Reporting.Error(
{III}UnsafeIntegerMessage(that));
{I}}}
}}"""
            )
        )

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
                verification_blocks.append(
                    _generate_verify_container(type_anno=type_anno)
                )

    if len(errors) > 0:
        return None, errors

    verification_writer = io.StringIO()
    verification_writer.write(
        f"""\
namespace {namespace}
{{
{I}/// <summary>
{I}/// Verify that the instances of the meta-model satisfy the invariants.
{I}/// </summary>
"""
    )

    # region Write an example usage

    first_cls: Optional[intermediate.ClassUnion] = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )

    if first_cls is not None:
        cls_name: str

        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = csharp_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = csharp_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = csharp_naming.variable_name(Identifier("an_instance"))

        verification_writer.write(
            f"""\
{I}/// <example>
{I}/// Here is an example how to verify an instance of {cls_name}:
{I}/// <code>
{I}/// var {an_instance_variable} = new Our.{cls_name}(
{I}///     // ... some constructor arguments ...
{I}/// );
{I}/// foreach (var error in Verification.Verify({an_instance_variable}))
{I}/// {{
{I}/// {I}System.Console.Writeln(
{I}/// {II}$"{{error.Cause}} at: " +
{I}/// {II}Reporting.GenerateJsonPath(error.PathSegments));
{I}/// }}
{I}/// </code>
{I}/// </example>
"""
        )

    # endregion

    verification_writer.write(
        f"""\
{I}public static class Verification
{I}{{
"""
    )

    for i, verification_block in enumerate(verification_blocks):
        if i > 0:
            verification_writer.write("\n\n")

        verification_writer.write(textwrap.indent(verification_block, II))

    verification_writer.write(f"\n{I}}}  // public static class Verification")
    verification_writer.write(f"\n}}  // namespace {namespace}")

    blocks.append(Stripped(verification_writer.getvalue()))

    blocks.append(csharp_common.WARNING)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        out.write(block)

    out.write("\n")

    return out.getvalue(), None


# endregion

assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
