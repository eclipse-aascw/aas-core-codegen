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
    Set,
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
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.parse import tree as parse_tree, retree as parse_retree
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
    description as typescript_description,
    transpilation as typescript_transpilation,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
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
                    f"Verification/{func.name}.ts"
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


class _RegexRendererForJavaScript(parse_retree.Renderer):
    r"""
    Render the regular expressions as expected by JavaScript.

    For example, Unicode characters are rendered as ``\u{...}``.
    """

    def char_to_str_and_escape_or_encode_if_necessary(
        self, node: parse_retree.Char, escaping: Mapping[str, str]
    ) -> List[Union[str, parse_tree.FormattedValue]]:
        """Convert the ``node`` to a string, and escape and/or encode appropriately."""
        if not node.explicitly_encoded:
            escaped = escaping.get(node.character, None)
            if escaped is not None:
                result: List[Union[str, parse_tree.FormattedValue]] = [escaped]
            else:
                result = [node.character]

            return result
        else:
            code = ord(node.character)
            # NOTE (mristin):
            # See: https://dmitripavlutin.com/what-every-javascript-developer-should-know-about-unicode/#24-surrogate-pairs
            return [f"\\u{{{code:x}}}"]


_REGEX_RENDERER_FOR_JAVASCRIPT = _RegexRendererForJavaScript()


class _PatternVerificationTranspiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a statement of a pattern verification into TypeScript."""

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_joined_str_values(
        self, values: Sequence[Union[str, parse_tree.FormattedValue]]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Transform the values of a joined string to a TypeScript string literal."""
        # If we do not need interpolation, simply return the string literals
        # joined together.
        needs_interpolation = any(
            isinstance(value, parse_tree.FormattedValue) for value in values
        )
        if not needs_interpolation:
            return (
                Stripped(
                    typescript_common.string_literal(
                        "".join(value for value in values)  # type: ignore
                    )
                ),
                None,
            )

        parts: List[str] = []

        for value in values:
            if isinstance(value, str):
                parts.append(
                    typescript_common.string_literal(
                        value,
                        without_enclosing=True,
                        in_backticks=True,
                    )
                )

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self.transform(value.value)
                if error is not None:
                    return None, error

                assert code is not None

                assert (
                    "\n" not in code
                ), f"New-lines are not expected in formatted values, but got: {code}"

                parts.append(f"${{{code}}}")
            else:
                # noinspection PyTypeChecker
                assert_never(value)

        parts_joined = "".join(parts)
        return Stripped(f"`{parts_joined}`"), None

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

            # NOTE (mristin):
            # Strictly speaking, this is a joined string with a single value, a string
            # literal. Thus, do not be confused by the name of the function —
            # this function treats both joined formatted values *and* string literals.
            return self._transform_joined_str_values(
                values=parse_retree.render(
                    regex=regex, renderer=_REGEX_RENDERER_FOR_JAVASCRIPT
                )
            )
        else:
            raise AssertionError(f"Unexpected {node=}")

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return Stripped(typescript_naming.variable_name(node.identifier)), None

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
            values=parse_retree.render(
                regex=regex, renderer=_REGEX_RENDERER_FOR_JAVASCRIPT
            )
        )

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        assert isinstance(node.target, parse_tree.Name)
        variable = typescript_naming.variable_name(node.target.identifier)
        code, error = self.transform(node.value)
        if error is not None:
            return None, error
        assert code is not None

        # NOTE (mristin):
        # We assume that the variables won't change in the patterns. If this assumption
        # is broken, fix the code here by first inspecting the scope and classifying
        # the variables into constant ones and modifiable ones.
        return Stripped(f"const {variable} = {code};"), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_pattern_verification(
    verification: intermediate.PatternVerification,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the verification function that checks the regular expressions."""
    # NOTE (mristin):
    # We assume that we performed all the checks at the intermediate stage.

    construct_name = typescript_naming.function_name(
        Identifier(f"construct_{verification.name}")
    )

    blocks: List[Stripped] = []

    # region Construct block

    writer = io.StringIO()
    writer.write(
        f"""\
function {construct_name}(): RegExp {{
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

    # A pragmatic heuristics for breaking lines
    if len(pattern_expr) < 50:
        writer.write(textwrap.indent(f'return new RegExp({pattern_expr}, "u");', I))
    else:
        writer.write(
            textwrap.indent(
                f"""\
return new RegExp(
{I}{indent_but_first_line(pattern_expr, I)},
{I}"u"
);""",
                I,
            )
        )

    writer.write("\n}")

    blocks.append(Stripped(writer.getvalue()))

    # endregion

    # region Initialize the regex

    regex_name = typescript_naming.constant_name(
        Identifier(f"regexp_{verification.name.lstrip('_')}")
    )

    blocks.append(Stripped(f"const {regex_name} = {construct_name}();"))

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

    arg_name = typescript_naming.argument_name(verification.arguments[0].name)

    function_name = typescript_naming.function_name(verification.name)

    writer = io.StringIO()

    if verification.description is not None:
        (
            comment,
            comment_errors,
        ) = typescript_description.generate_documentation_comment_for_signature(
            description=verification.description,
            context=typescript_description.Context(
                module=typescript_common.VERIFICATION_MODULE, cls_or_enum=None
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

    # NOTE (mristin):
    # The internal functions are not exported so that they remain invisible to
    # the users of the SDK.
    export = (
        "" if verification.visibility is intermediate.Visibility.INTERNAL else "export "
    )

    writer.write(
        f"""\
{export}function {function_name}({arg_name}: string): boolean {{
{I}return {regex_name}.test({arg_name});
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


class _TranspilableVerificationTranspiler(typescript_transpilation.Transpiler):
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
        environment: intermediate_type_inference.Environment,
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
    ) -> None:
        """Initialize with the given values."""
        typescript_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            environment=environment,
            downcast_map=downcast_map,
            reassigned_definitions=(
                typescript_transpilation.collect_reassigned_definitions(
                    verification.parsed.body
                )
            ),
        )

        self._symbol_table = symbol_table

        self._argument_name_set = frozenset(arg.name for arg in verification.arguments)

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(typescript_naming.variable_name(node.identifier)), None

        if node.identifier in self._argument_name_set:
            return Stripped(typescript_naming.argument_name(node.identifier)), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_name = typescript_naming.constant_name(node.identifier)
            return Stripped(f"OurConstants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(typescript_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"OurTypes.{typescript_naming.enum_name(node.identifier)}"),
                None,
            )

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to TypeScript. We could not find it neither in the constants, nor in "
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

    writer = io.StringIO()

    if verification.description is not None:
        (
            comment,
            comment_errors,
        ) = typescript_description.generate_documentation_comment_for_signature(
            description=verification.description,
            context=typescript_description.Context(
                module=typescript_common.VERIFICATION_MODULE,
                cls_or_enum=None,
            ),
        )
        if comment_errors is not None:
            return None, Error(
                verification.description.parsed.node,
                f"Failed to generate the comment for verification function {verification.name!r}",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    function_name = typescript_naming.function_name(verification.name)

    # NOTE (mristin):
    # The internal functions are not exported so that they remain invisible to
    # the users of the SDK.
    export = (
        "" if verification.visibility is intermediate.Visibility.INTERNAL else "export "
    )

    if verification.returns is None:
        return_type = "void"
    else:
        return_type = typescript_common.generate_type(
            type_annotation=verification.returns, types_module=Identifier("OurTypes")
        )

    arg_defs: List[Stripped] = []
    for arg in verification.arguments:
        arg_type = typescript_common.generate_type(
            arg.type_annotation, types_module=Identifier("OurTypes")
        )
        arg_name = typescript_naming.argument_name(arg.name)
        arg_defs.append(Stripped(f"{arg_name}: {arg_type}"))

    if len(arg_defs) == 0:
        writer.write(
            f"""\
{export}function {function_name}(): {return_type} {{"""
        )
    else:
        writer.write(
            f"""\
{export}function {function_name}(
"""
        )

        for i, arg_def in enumerate(arg_defs):
            if i > 0:
                writer.write(",\n")
            writer.write(textwrap.indent(arg_def, I))

        writer.write("\n")
        writer.write(
            f"""\
): {return_type} {{"""
        )

    if len(body) == 0:
        writer.write("// Intentionally empty.")
    else:
        for stmt in body:
            writer.write("\n")
            writer.write(textwrap.indent(stmt, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


class _InvariantTranspiler(typescript_transpilation.Transpiler):
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
        typescript_transpilation.Transpiler.__init__(
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
            return Stripped(typescript_naming.variable_name(node.identifier)), None

        if node.identifier == "self":
            # The ``that`` refers to the argument of the verification function.
            return Stripped("that"), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_name = typescript_naming.constant_name(node.identifier)
            return Stripped(f"OurConstants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(typescript_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"OurTypes.{typescript_naming.enum_name(node.identifier)}"),
                None,
            )

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to TypeScript. We could not find it neither in the local variables, "
            f"nor in the global constants, nor in verification functions, "
            f"nor as an enumeration. If you expect this name to be transpilable, "
            f"please contact the developers.",
        )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_invariant(
    invariant: intermediate.Invariant,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Translate the invariant from the meta-model into TypeScript code."""
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
        writer.write("\n)) {\n")
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

        writer.write(f"if ({not_expr}) {{\n")

    writer.write(f"{I}yield new VerificationError(\n")

    # NOTE (mristin):
    # We need to wrap the description in multiple literals as a single long
    # string literal is often too much for the readability.
    invariant_description_lines = wrap_text_into_lines(invariant.description)

    for i, literal in enumerate(invariant_description_lines):
        if i < len(invariant_description_lines) - 1:
            writer.write(f"{II}{typescript_common.string_literal(literal)} +\n")
        else:
            writer.write(f"{II}{typescript_common.string_literal(literal)}\n")
            writer.write(f"{I})")

    writer.write("\n}")

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

    In TypeScript, we verify the integers, the constrained primitives, the instances
    of our classes and all the JSON-able values. We rely on the TypeScript compiler
    to spot invalid enumeration literals, so we do not verify the enumerations at all.

    An integer is a TypeScript ``number``, so we verify that it is a whole number
    in the safe integer range, which is exactly what its JSON serialization
    requires.
    """
    return any(
        (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and not isinstance(type_anno.our_type, intermediate.Enumeration)
        )
        or (
            isinstance(type_anno, intermediate.PrimitiveTypeAnnotation)
            and type_anno.a_type is intermediate.PrimitiveType.INT
        )
        or isinstance(
            type_anno,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        )
        for type_anno in intermediate.over_type_annotation_and_nested_type_annotations(
            type_annotation
        )
    )


def _is_instance(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """Check whether ``type_anno`` denotes an instance of one of our classes."""
    return isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    )


def _verification_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name ``type_anno`` by what its verification depends on.

    We follow the Polish notation of
    :py:func:`aas_core_codegen.typescript.common.type_moniker`, except that we name
    all the instances of our classes and named unions ``class``, a constrained
    primitive by itself (*e.g.*, ``NonEmptyString``) instead of its constrainee
    (``str``), and a JSON object by its constrained key, if any
    (*e.g.*, ``jsonObjectByNonEmptyString``).

    All the instances are verified with the very same call to ``verify``, so
    the containers of different classes can share one verification function.
    On the other hand, the constrained primitives share a TypeScript type, but are
    verified differently, so each needs a moniker of its own.

    The leaf monikers spelled in lower case can never be confused with our types,
    which all go through :py:func:`aas_core_codegen.naming.capitalized_camel_case`.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ListOf_{_verification_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        return f"SetOf_{_verification_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        monikers = "_".join(_verification_moniker(item) for item in type_anno.items)
        return f"TupleOf{len(type_anno.items)}_{monikers}"

    if _is_instance(type_anno):
        return "class"

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.ConstrainedPrimitive
    ):
        return typescript_naming.class_name(type_anno.our_type.name)

    if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        key_constrained_primitive = intermediate.try_constrained_primitive(
            type_anno.key
        )
        if key_constrained_primitive is not None:
            return (
                f"jsonObjectBy"
                f"{typescript_naming.class_name(key_constrained_primitive.name)}"
            )

    return typescript_common.atomic_moniker(type_anno)


def _verification_parameter_type(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Generate the type of the value at ``type_anno`` as a function parameter.

    We use the read-only containers so that a single function accepts
    the containers of different classes, all given as ``OurTypes.Class``.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ReadonlyArray<{_verification_parameter_type(type_anno.items)}>"

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        return f"ReadonlySet<{_verification_parameter_type(type_anno.items)}>"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_types = [_verification_parameter_type(item) for item in type_anno.items]

        one_liner = f"readonly [{', '.join(item_types)}]"
        # Heuristic to break the lines, very rudimentary
        if len(one_liner) <= 60:
            return one_liner

        joined = ",\n".join(item_types)
        return f"""\
readonly [
{I}{indent_but_first_line(joined, I)}
]"""

    if _is_instance(type_anno):
        return "OurTypes.Class"

    return typescript_common.generate_type(type_anno, types_module=Stripped("OurTypes"))


def _verify_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the module-level function verifying ``type_anno``.

    We name the function with an underscore so that it can not collide with any of
    the other names in the module, which never contain one.
    """
    return Identifier(f"verify_{_verification_moniker(type_anno)}")


@require(lambda type_anno: _needs_verification(type_anno))
def _generate_verify_into(
    expr: str, type_anno: intermediate.TypeAnnotationUnion, segments: Sequence[str]
) -> Stripped:
    """
    Generate the statements yielding the errors of the value at ``expr``.

    The ``segments`` are prepended to the path of each error, the innermost first.

    An atomic value is verified by its own function. A container is delegated to
    its module-level function, which verifies only one level and calls
    the function of its items by name. This way the verification is composed of
    plain functions, to any depth.
    """
    blocks: List[Stripped] = []

    function: str

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            function = typescript_naming.function_name(
                Identifier(f"verify_{type_anno.our_type.name}")
            )
        else:
            assert _is_instance(type_anno), (
                f"Unexpected our type with something to verify: "
                f"{type_anno.our_type}"
            )
            function = "verify"

    elif isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        assert type_anno.a_type is intermediate.PrimitiveType.INT, (
            f"Unexpected primitive type with something to verify: "
            f"{type_anno.a_type}"
        )
        function = "verifyInteger"

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

    for_header = f"for (const error of {function}({expr}))"
    # Heuristic to break the lines, very rudimentary
    if len(for_header) > 70:
        for_header = f"""\
for (const error of {function}(
{II}{expr})
)"""

    prepend_stmts = "\n".join(
        f"""\
error.path.prepend(
{I}{indent_but_first_line(segment, I)}
);"""
        for segment in segments
    )

    blocks.append(
        Stripped(
            f"""\
{for_header} {{
{I}{indent_but_first_line(prepend_stmts, I)}
{I}yield error;
}}"""
        )
    )

    # NOTE (mristin):
    # A bare ``str`` key has nothing to verify.
    if isinstance(
        type_anno, intermediate.JsonObjectTypeAnnotation
    ) and _needs_verification(type_anno.key):
        key_stmts = _generate_verify_into(
            expr="key",
            type_anno=type_anno.key,
            segments=[
                f"""\
new KeySegment(
{I}{expr},
{I}key
)""",
                *segments,
            ],
        )

        blocks.append(
            Stripped(
                f"""\
for (const key of Object.keys({expr})) {{
{I}// NOTE (mristin):
{I}// The key segment names the member whose key is erroneous. The path
{I}// thus leads to the member, and the message says what is wrong with
{I}// the key which names it.
{I}{indent_but_first_line(key_stmts, I)}
}}"""
            )
        )

    return Stripped("\n".join(blocks))


@require(lambda type_anno: _needs_verification(type_anno))
def _generate_verify_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the module-level function verifying ``type_anno``."""
    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_stmts = _generate_verify_into(
            expr="that[i]",
            type_anno=type_anno.items,
            segments=[
                f"""\
new IndexSegment(
{I}that,
{I}i
)"""
            ],
        )

        body = Stripped(
            f"""\
for (let i = 0; i < that.length; i++) {{
{I}{indent_but_first_line(item_stmts, I)}
}}"""
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        item_stmts = _generate_verify_into(
            expr="sortedThat[i]",
            type_anno=type_anno.items,
            segments=[
                f"""\
new IndexSegment(
{I}sortedThat,
{I}i
)"""
            ],
        )

        sorted_items = typescript_common.generate_sorted_set_items(
            type_anno=type_anno, set_expression=Stripped("that")
        )

        # NOTE (mristin):
        # A set has no index, so we verify the items in the sorted order in which
        # they are serialized. Thus, the path of an error resolves in
        # the serialized array.
        body = Stripped(
            f"""\
const sortedThat = {sorted_items};
for (let i = 0; i < sortedThat.length; i++) {{
{I}{indent_but_first_line(item_stmts, I)}
}}"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = Stripped(
            "\n\n".join(
                _generate_verify_into(
                    expr=f"that[{i}]",
                    type_anno=item_type_anno,
                    segments=[
                        f"""\
new IndexSegment(
{I}that,
{I}{i}
)"""
                    ],
                )
                for i, item_type_anno in enumerate(type_anno.items)
                if _needs_verification(item_type_anno)
            )
        )

    else:
        assert_never(type_anno)

    name = _verify_container_name(type_anno)
    parameter_type = _verification_parameter_type(type_anno)

    return Stripped(
        f"""\
/**
 * Verify the items of `that` recursively.
 */
function *{name}(
{I}that: {indent_but_first_line(parameter_type, I)}
): IterableIterator<VerificationError> {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_verify_property(prop: intermediate.Property) -> Optional[Stripped]:
    """
    Generate the snippet to transform a property to verification errors.

    Return ``None`` if there is nothing to be verified for the given property.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    if not _needs_verification(type_anno):
        return None

    prop_name = typescript_naming.property_name(prop.name)
    prop_name_literal = typescript_common.string_literal(prop_name)

    property_segment = f"""\
new PropertySegment(
{I}that,
{I}{prop_name_literal}
)"""

    block = _generate_verify_into(
        expr=f"that.{prop_name}", type_anno=type_anno, segments=[property_segment]
    )

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        block = Stripped(
            f"""\
if (that.{prop_name} !== null) {{
{I}{indent_but_first_line(block, I)}
}}"""
        )

    return block


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transform_for_class(
    cls: intermediate.ConcreteClass,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transform method to errors for the given concrete class."""
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

    if len(errors) > 0:
        return None, errors

    # region Verify the properties

    # NOTE (mristin):
    # The primitives, constrained or not, are not included in the recursion, so we
    # verify the properties of primitives in the non-recursive part as well.
    recurse_prop_blocks: List[Stripped] = []

    for prop in cls.properties:
        prop_block = _generate_verify_property(prop)
        if prop_block is None:
            continue

        if (
            intermediate.try_primitive_type(
                intermediate.beneath_optional(prop.type_annotation)
            )
            is not None
        ):
            blocks.append(prop_block)
        else:
            recurse_prop_blocks.append(prop_block)

    if len(recurse_prop_blocks) > 0:
        joined_prop_blocks = "\n\n".join(recurse_prop_blocks)
        blocks.append(
            Stripped(
                f"""\
if (context === true) {{
{I}{indent_but_first_line(joined_prop_blocks, I)}
}}"""
            )
        )

    # endregion

    cls_name = typescript_naming.class_name(cls.name)

    no_verification = len(blocks) == 0
    if len(blocks) == 0:
        blocks.append(
            Stripped(
                f"""\
// No verification has been defined for {cls_name}."""
            )
        )

    transform_name = typescript_naming.method_name(
        Identifier(f"transform_{cls.name}_with_context")
    )

    maybe_disable_that_unused = (
        ""
        if not no_verification
        else f"{I}// eslint-disable-next-line @typescript-eslint/no-unused-vars\n"
    )

    maybe_disable_context_unused = (
        ""
        if len(recurse_prop_blocks) > 0
        else f"{I}// eslint-disable-next-line @typescript-eslint/no-unused-vars\n"
    )

    writer = io.StringIO()
    writer.write(
        f"""\
*{transform_name}(
{maybe_disable_that_unused}{I}that: OurTypes.{cls_name},
{maybe_disable_context_unused}{I}context: boolean
): IterableIterator<VerificationError> {{
"""
    )

    for i, stmt in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(stmt, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_verify_json_value(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the functions verifying that a value is JSON-able.

    A JSON-able value is, recursively, exactly as JSON itself is defined, but
    its TypeScript type rules out neither of the two ways of not being one:
    a non-finite number and an ``undefined``, which `strictNullChecks` catches
    at the boundary but not inside a value handed over as `any` by
    a JavaScript caller. Both are reported here, at any depth. A ``null`` is
    a JSON null, and hence a JSON-able value.

    The path of an error leads all the way down to the culprit: an item of
    an open JSON array contributes an `IndexSegment` and a member of an open
    JSON object a `KeySegment`, just as a property of one of our classes
    contributes a `PropertySegment`.
    """
    if not intermediate_uses.json_types(symbol_table):
        return []

    return [
        Stripped(
            f"""\
/**
 * Verify that `value` is a JSON-able value, at any depth.
 *
 * @remarks
 *
 * The path of an error points into `value` itself: an item of an array
 * contributes an index segment and a member of an object a key segment, so
 * that the path leads all the way down to the culprit.
 *
 * The value is walked depth first, so an error deep inside the first member
 * is reported before an error on the second one. The errors thus come in
 * the order in which a reader meets them going through the value.
 *
 * @param value - to be verified
 * @returns errors, if any
 */
export function *verifyJsonValue(
{I}value: OurTypes.JsonValue
): IterableIterator<VerificationError> {{
{I}if (value === null) {{
{II}return;
{I}}}

{I}if (value === undefined) {{
{II}yield new VerificationError(
{III}`Expected a JSON-able value, but got: ${{value}}`
{II});
{II}return;
{I}}}

{I}switch (typeof value) {{
{II}case "boolean":
{II}case "string":
{III}return;

{II}case "number":
{III}// NOTE (mristin):
{III}// JSON knows neither an infinity nor a not-a-number, so neither is
{III}// a JSON-able value, even though a TypeScript `number` holds either.
{III}if (!Number.isFinite(value)) {{
{IIII}yield new VerificationError(
{IIIII}`Expected a JSON-able value, but got the number ${{value}}, ` +
{IIIII}`which is neither finite nor representable in JSON`
{IIII});
{III}}}
{III}return;

{II}case "object":
{III}break;

{II}default:
{III}yield new VerificationError(
{IIII}`Expected a JSON-able value (a null, a boolean, a number, a string, ` +
{IIIII}`an array or an object), but got: ${{typeof value}}`
{III});
{III}return;
{I}}}

{I}if (Array.isArray(value)) {{
{II}for (let i = 0; i < value.length; i++) {{
{III}for (const error of verifyJsonValue(value[i])) {{
{IIII}error.path.prepend(new IndexSegment(value, i));
{IIII}yield error;
{III}}}
{II}}}
{II}return;
{I}}}

{I}for (const key of Object.keys(value)) {{
{II}for (const error of verifyJsonValue(value[key])) {{
{III}error.path.prepend(new KeySegment(value, key));
{III}yield error;
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Verify that `value` is a JSON-able array.
 *
 * @param value - to be verified
 * @returns errors, if any
 */
export function *verifyJsonArray(
{I}value: OurTypes.JsonArray
): IterableIterator<VerificationError> {{
{I}if (!Array.isArray(value)) {{
{II}yield new VerificationError(
{III}`Expected a JSON-able array, but got: ${{typeof value}}`
{II});
{II}return;
{I}}}

{I}yield* verifyJsonValue(value);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Verify that `value` is a JSON-able object.
 *
 * @param value - to be verified
 * @returns errors, if any
 */
export function *verifyJsonObject(
{I}value: OurTypes.JsonObject
): IterableIterator<VerificationError> {{
{I}if (
{II}value === null
{II}|| value === undefined
{II}|| typeof value !== "object"
{II}|| Array.isArray(value)
{I}) {{
{II}yield new VerificationError(
{III}`Expected a JSON-able object, but got: ${{typeof value}}`
{II});
{II}return;
{I}}}

{I}yield* verifyJsonValue(value);
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

    # The abstract classes are directly dispatched by the transformer,
    # so we do not need to handle them separately.
    for cls in symbol_table.concrete_classes:
        block, cls_errors = _generate_transform_for_class(
            cls=cls,
            symbol_table=symbol_table,
            type_inference=type_inference,
        )
        if cls_errors is not None:
            errors.extend(cls_errors)
        else:
            assert block is not None
            blocks.append(block)
    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Verify an instance of the model recursively or non-recursively (depending on the context).
 */
class Verifier
{I}extends OurTypes.AbstractTransformerWithContext<
{II}boolean, IterableIterator<VerificationError>
{I}> {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


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
    # An integer is a TypeScript ``number``, so we check that it is a safe integer
    # before the invariants, which assume one.
    if constrained_primitive.constrainee is intermediate.PrimitiveType.INT:
        blocks.insert(
            0,
            Stripped(
                f"""\
if (!Number.isSafeInteger(that)) {{
{I}yield* verifyInteger(that);
{I}return;
}}"""
            ),
        )

    no_verification = False
    if len(blocks) == 0:
        blocks.append(Stripped("// There is no verification specified."))
        no_verification = True

    function_name = typescript_naming.function_name(
        Identifier(f"verify_{constrained_primitive.name}")
    )

    that_type = typescript_common.PRIMITIVE_TYPE_MAP[constrained_primitive.constrainee]

    writer = io.StringIO()

    writer.write(
        """\
/**
 * Verify the constraints of `that` value.
 *
 * @param that - to be verified
 * @returns errors, if any
 */
"""
    )

    if no_verification:
        writer.write(
            f"""\
export function *{function_name}(
{I}// eslint-disable-next-line @typescript-eslint/no-unused-vars
{I}that: {that_type}
): IterableIterator<VerificationError> {{
"""
        )
    else:
        writer.write(
            f"""\
export function *{function_name}(
{I}that: {that_type}
): IterableIterator<VerificationError> {{
"""
        )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    assert len(errors) == 0
    return Stripped(writer.getvalue()), None


def _generate_module_comment(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the documentation comment for the module."""
    package_identifier_key = specific_implementations.ImplementationKey(
        "package_identifier.txt"
    )

    package_identifier = spec_impls.get(package_identifier_key, None)
    if package_identifier is None:
        return None, Error(
            None,
            f"The package identifier snippet is missing "
            f"in the specific implementations: {package_identifier_key}",
        )

    assert package_identifier is not None

    blocks: List[Stripped] = [
        Stripped("Verify that the instances of the meta-model satisfy the invariants.")
    ]

    first_cls: Optional[intermediate.ConcreteClass] = (
        symbol_table.concrete_classes[0]
        if len(symbol_table.concrete_classes) > 0
        else None
    )

    if first_cls is not None:
        cls_name = typescript_naming.class_name(first_cls.name)
        an_instance_variable = typescript_naming.variable_name(
            Identifier("an_instance")
        )

        blocks.append(
            Stripped(
                f"""\
Here is an example how to verify an instance of {{@link types.{cls_name}}}:

```ts
import * as OurTypes from "{package_identifier}/types";
import * as OurVerification from "{package_identifier}/verification";

const {an_instance_variable} = new OurTypes.{cls_name}(
{I}// ... some constructor arguments ...
);

for (const error of OurVerification.verify({an_instance_variable})) {{
{I}console.log(`${{error.message}} at: ${{error.path}}`);
}}
```"""
            )
        )

    # endregion

    text = "\n\n".join(blocks)

    return Stripped(typescript_description.documentation_comment(Stripped(text))), None


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
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code of verification logic."""
    errors: List[Error] = []

    module_docstring, module_docstring_error = _generate_module_comment(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if module_docstring_error is not None:
        errors.append(module_docstring_error)
        # NOTE (mristin):
        # Allow the execution to continue to catch other errors as well
        module_docstring = Stripped("")

    assert module_docstring is not None

    blocks: List[Stripped] = [
        module_docstring,
        typescript_common.WARNING,
        Stripped(
            """\
import * as OurCommon from "./common";
import * as OurConstants from "./constants";
import * as OurTypes from "./types";"""
        ),
        Stripped(
            """\
// The generated code might contain deliberately double negations. For example,
// when the constraint is formulated as a NAND and we check that the constraint
// is not fulfilled. Therefore, we disable this linting rule.
/* eslint no-extra-boolean-cast: 0 */"""
        ),
        typescript_common.NOTE_ON_THE_THREE_ERROR_PATHS,
        Stripped(
            f"""\
/**
 * Represent a property access on a path to an erroneous value.
 */
export class PropertySegment {{
{I}/**
{I} * Instance containing the property
{I} */
{I}readonly instance: OurTypes.Class;

{I}/**
{I} * Name of the property
{I} */
{I}readonly name: string;

{I}constructor(instance: OurTypes.Class, name: string) {{
{II}this.instance = instance;
{II}this.name = name;
{I}}}

{I}toString(): string {{
{II}return `.${{this.name}}`;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent an index access on a path to an erroneous value.
 */
export class IndexSegment {{
{I}/**
{I} * Sequence containing the item at {{@link index}}
{I} */
{I}readonly sequence: ReadonlyArray<unknown>;

{I}/**
{I} * Index of the item in the {{@link sequence}}
{I} */
{I}readonly index: number;

{I}constructor(sequence: ReadonlyArray<unknown>, index: number) {{
{II}this.sequence = sequence;
{II}this.index = index;
{I}}}

{I}toString(): string {{
{II}return `[${{this.index}}]`;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent a member access on a path to an erroneous value.
 *
 * @remarks
 *
 * Unlike a {{@link PropertySegment}}, which names a property of one of our
 * classes, a key names a member of an open JSON-able object. It is known only
 * at run time, and can be any string at all, so it is always rendered as
 * a subscript.
 */
export class KeySegment {{
{I}/**
{I} * Object containing the value at {{@link key}}
{I} */
{I}readonly object: {{ readonly [key: string]: unknown }};

{I}/**
{I} * Key of the value in the {{@link object}}
{I} */
{I}readonly key: string;

{I}constructor(object: {{ readonly [key: string]: unknown }}, key: string) {{
{II}this.object = object;
{II}this.key = key;
{I}}}

{I}toString(): string {{
{II}return `[${{JSON.stringify(this.key)}}]`;
{I}}}
}}"""
        ),
        Stripped("export type Segment = PropertySegment | IndexSegment | KeySegment;"),
        Stripped(
            f"""\
/**
 * Represent the relative path to the erroneous value.
 */
export class Path {{
{I}readonly segments: Array<Segment> = [];

{I}prepend(segment: Segment): void {{
{II}this.segments.unshift(segment);
{I}}}

{I}toString(): string {{
{II}return this.segments.join("");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent a verification error in the data.
 */
export class VerificationError {{
{I}// NOTE (mristin):
{I}// The name `VerificationError` is redundant since it lives in `verification` module,
{I}// and it would have made more sense to call it simply `Error`. Unfortunately in this case,
{I}// `Error` is a reserved name by JavaScript.

{I}/**
{I} * Human-readable description of the error
{I} */
{I}readonly message: string;

{I}/**
{I} * Path to the erroneous value
{I} */
{I}readonly path: Path = new Path();

{I}/**
{I} * Initialize with the given `message` and `path`.
{I} *
{I} * @remarks
{I} * If no `path` is specified, initialize with an empty path.
{I} */
{I}constructor(message: string, path: Path | null = null) {{
{II}this.message = message;
{II}this.path = (path !== null)
{III}? path
{III}: new Path();
{I}}}
}}"""
        ),
    ]

    for verification in symbol_table.verification_functions:
        if isinstance(verification, intermediate.ImplementationSpecificVerification):
            implementation_key = specific_implementations.ImplementationKey(
                f"Verification/{verification.name}.ts"
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
            # noinspection PyTypeChecker
            assert_never(verification)

    if intermediate_uses.integers(symbol_table):
        blocks.append(
            Stripped(
                f"""\
/**
 * Verify that `that` is a safe integer so that it can be serialized to JSON.
 *
 * @param that - to be verified
 * @returns errors, if any
 */
export function *verifyInteger(
{I}that: number
): IterableIterator<VerificationError> {{
{I}if (!Number.isInteger(that)) {{
{II}yield new VerificationError(OurCommon.notWholeIntegerMessage(that));
{I}}} else if (!Number.isSafeInteger(that)) {{
{II}yield new VerificationError(OurCommon.unsafeIntegerMessage(that));
{I}}}
}}"""
            )
        )

    blocks.extend(_generate_verify_json_value(symbol_table=symbol_table))

    observed_container_names: Set[Identifier] = set()

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

                name = _verify_container_name(type_anno)
                if name in observed_container_names:
                    continue

                observed_container_names.add(name)

                blocks.append(_generate_verify_container(type_anno=type_anno))

    transformer_block, transformer_errors = _generate_transformer(
        symbol_table=symbol_table,
        type_inference=type_inference,
    )
    if transformer_errors is not None:
        errors.extend(transformer_errors)
    else:
        assert transformer_block is not None
        blocks.append(transformer_block)

    blocks.append(Stripped("const VERIFIER = new Verifier();"))

    blocks.append(
        Stripped(
            f"""\
/**
 * Verify the constraints of `that`.
 *
 * @param that - instance to be verified
 * @param recurse - if set, continue the verification recursively
 * @returns a stream of verification errors
 */
export function *verify(
  that: OurTypes.Class,
  recurse = true
): IterableIterator<VerificationError> {{
{I}yield * VERIFIER.transformWithContext(that, recurse);
}}"""
        )
    )

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            # NOTE (mristin):
            # We do not verify the enumerations explicitly in TypeScript and
            # leave those checks to TypeScript compiler.
            pass

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
                blocks.append(constrained_primitive_block)

        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            # NOTE (mristin):
            # We provide a general dispatch function for the most abstract
            # class ``Class``.
            pass

        else:
            # noinspection PyTypeChecker
            assert_never(our_type)

    blocks.append(typescript_common.WARNING)

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
