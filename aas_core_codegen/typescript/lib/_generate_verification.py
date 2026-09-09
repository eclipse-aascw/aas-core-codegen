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
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
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
            # pylint: disable=line-too-long
            # NOTE (mristin, 2022-12-09):
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

        parts = []  # type: List[str]

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
            # NOTE (mristin, 2022-06-11):
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

            # NOTE (mristin, 2022-11-04):
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

        # NOTE (mristin, 2022-11-24):
        # We assume that the variables won't change in the patterns. If this assumption
        # is broken, fix the code here by first inspecting the scope and classifying
        # the variables into constant ones and modifiable ones.
        return Stripped(f"const {variable} = {code};"), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_pattern_verification(
    verification: intermediate.PatternVerification,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the verification function that checks the regular expressions."""
    # NOTE (mristin, 2022-11-12):
    # We assume that we performed all the checks at the intermediate stage.

    construct_name = typescript_naming.function_name(
        Identifier(f"construct_{verification.name}")
    )

    blocks = []  # type: List[Stripped]

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
        Identifier(f"regexp_{verification.name}")
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

    writer.write(
        f"""\
export function {function_name}({arg_name}: string): boolean {{
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
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
    ) -> None:
        """Initialize with the given values."""
        typescript_transpilation.Transpiler.__init__(
            self, type_map=type_map, environment=environment
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
            return Stripped(f"AasConstants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(typescript_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"AasTypes.{typescript_naming.enum_name(node.identifier)}"),
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

    transpiler = _TranspilableVerificationTranspiler(
        type_map=type_inference.type_map,
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

    if verification.returns is None:
        return_type = "void"
    else:
        return_type = typescript_common.generate_type(
            type_annotation=verification.returns, types_module=Identifier("aas_types")
        )

    arg_defs = []  # type: List[Stripped]
    for arg in verification.arguments:
        arg_type = typescript_common.generate_type(
            arg.type_annotation, types_module=Identifier("AasTypes")
        )
        arg_name = typescript_naming.argument_name(arg.name)
        arg_defs.append(Stripped(f"{arg_name}: {arg_type}"))

    if len(arg_defs) == 0:
        writer.write(
            f"""\
export function {function_name}(): {return_type}:"""
        )
    else:
        writer.write(
            f"""\
export function {function_name}(
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
        symbol_table: intermediate.SymbolTable,
    ) -> None:
        """Initialize with the given values."""
        typescript_transpilation.Transpiler.__init__(
            self, type_map=type_map, environment=environment
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
            return Stripped(f"AasConstants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(typescript_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"AasTypes.{typescript_naming.enum_name(node.identifier)}"),
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
    environment: intermediate_type_inference.Environment,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Translate the invariant from the meta-model into TypeScript code."""
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

    transpiler = _InvariantTranspiler(
        type_map=type_map,
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
        writer.write("\n)) {\n")
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

        writer.write(f"if ({not_expr}) {{\n")

    writer.write(f"{I}yield new VerificationError(\n")

    # NOTE (mristin, 2022-11-12):
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
    Generate the snippet to transform a property to verification errors.

    Return an empty string if there is nothing to be verified for the given property.
    """
    # NOTE (mristin, 2022-11-12):
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
    else:
        pass

    stmts = []  # type: List[Stripped]

    prop_name = typescript_naming.property_name(prop.name)
    prop_name_literal = typescript_common.string_literal(prop_name)

    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None and primitive_type is intermediate.PrimitiveType.INT:
        stmts.append(
            Stripped(
                f"""\
if (!Number.isInteger(that.{prop_name})) {{
{I}const error = new VerificationError(
{II}"Expected an integer, but got a floating-point number"
{I});
{I}error.path.prepend(
{II}new PropertySegment(
{III}that,
{III}{prop_name_literal}
{II})
{I});
{I}yield error;
}}"""
            )
        )

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        # There is nothing more that we check for primitive types explicitly. The values
        # of the primitive properties are checked at the level of class invariants.
        return Stripped(""), None
    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            # We rely on TypeScript compiler to check for valid enumerations, so we do
            # not check the enumerations on our side.
            return Stripped(""), None

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            function_name = typescript_naming.function_name(
                Identifier(f"verify_{type_anno.our_type.name}")
            )

            # fmt: off
            for_error_of_verify = (
                f"for (const error of {function_name}(that.{prop_name}))"
            )
            # fmt: on

            # Heuristic to break the lines, very rudimentary
            if len(for_error_of_verify) > 70:
                for_error_of_verify = f"""\
for (const error of {function_name}(
{II}that.{prop_name})
)"""

            stmts.append(
                Stripped(
                    f"""\
{for_error_of_verify} {{
{I}error.path.prepend(
{II}new PropertySegment(
{III}that,
{III}{prop_name_literal}
{II})
{I});
{I}yield error;
}}"""
                )
            )

        elif isinstance(
            type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            for_error_of_this_transform = f"""\
for (const error of this.transformWithContext(that.{prop_name}, context))"""

            # Heuristic to break the lines, very rudimentary
            if len(for_error_of_this_transform) > 70:
                for_error_of_this_transform = f"""\
for (const error of this.transformWithContext(
{II}that.{prop_name}, context)
)"""

            stmts.append(
                Stripped(
                    f"""\
{for_error_of_this_transform} {{
{I}error.path.prepend(
{II}new PropertySegment(
{III}that,
{III}{prop_name_literal}
{II})
{I});
{I}yield error;
}}"""
                )
            )
        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_error_generation_expr: Stripped

        if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
            # Lists of primitives are verified at the level of class invariants.
            return Stripped(""), None

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                # We rely on TypeScript compiler to check for valid enumerations, so we
                # do not check the lists of enumerations on our side.
                return Stripped(""), None

            elif isinstance(
                type_anno.items.our_type, intermediate.ConstrainedPrimitive
            ):
                verify_function = typescript_naming.function_name(
                    Identifier(f"verify_{type_anno.items.our_type.name}")
                )

                item_error_generation_expr = Stripped(f"{verify_function}(item)")

            elif isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                item_error_generation_expr = Stripped(
                    "this.transformWithContext(item, context)"
                )

            else:
                assert_never(type_anno.items.our_type)

        else:
            raise NotImplementedError(
                "(mristin) We currently generate only the code to verify lists of "
                f"atomic values, but we got a list of type {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

        index_var = typescript_naming.variable_name(Identifier(f"{prop.name}_index"))

        stmts.append(
            Stripped(
                f"""\
let {index_var} = 0;
for (const item of that.{prop_name}) {{
{I}for (const error of {item_error_generation_expr}) {{
{II}error.path.prepend(
{III}new IndexSegment(
{IIII}that.{prop_name},
{IIII}{index_var}
{III})
{II});
{II}error.path.prepend(
{III}new PropertySegment(
{IIII}that,
{IIII}{prop_name_literal}
{III})
{II});
{II}yield error;
{I}}}
{I}{index_var}++;
}}"""
            )
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # Unlike lists, tuples are heterogeneous and fixed-length, so we
        # verify every item at its own fixed index instead of looping.
        for i, item_type_anno in enumerate(type_anno.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, "
                "constrained primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so no "
                "nested optionals, lists or tuples are expected here."
            )

            item_access = Stripped(f"that.{prop_name}[{i}]")

            for_error_of_item: Optional[Stripped]

            if isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
                # There is nothing to verify about the primitive types.
                for_error_of_item = None

            elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                if isinstance(item_type_anno.our_type, intermediate.Enumeration):
                    # We rely on the TypeScript compiler to check for valid
                    # enumerations, so there is nothing to verify here.
                    for_error_of_item = None

                elif isinstance(
                    item_type_anno.our_type, intermediate.ConstrainedPrimitive
                ):
                    verify_function = typescript_naming.function_name(
                        Identifier(f"verify_{item_type_anno.our_type.name}")
                    )

                    for_error_of_item = Stripped(
                        f"for (const error of {verify_function}({item_access})) {{"
                    )

                    if len(for_error_of_item) > 70:
                        for_error_of_item = Stripped(
                            f"""\
for (const error of {verify_function}(
{II}{item_access})
) {{"""
                        )

                elif isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    for_error_of_item = Stripped(
                        f"""\
for (const error of this.transformWithContext({item_access}, context)) {{"""
                    )

                    if len(for_error_of_item) > 70:
                        for_error_of_item = Stripped(
                            f"""\
for (const error of this.transformWithContext(
{II}{item_access}, context)
) {{"""
                        )

                else:
                    assert_never(item_type_anno.our_type)
            else:
                assert_never(item_type_anno)

            if for_error_of_item is None:
                continue

            stmts.append(
                Stripped(
                    f"""\
{for_error_of_item}
{I}error.path.prepend(
{II}new IndexSegment(
{III}that.{prop_name},
{III}{i}
{II})
{I});
{I}error.path.prepend(
{II}new PropertySegment(
{III}that,
{III}{prop_name_literal}
{II})
{I});
{I}yield error;
}}"""
                )
            )

    else:
        assert_never(type_anno)

    verify_block = Stripped("\n".join(stmts))

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return (
            Stripped(
                f"""\
if (that.{prop_name} !== null) {{
{I}{indent_but_first_line(verify_block, I)}
}}"""
            ),
            None,
        )

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

    # region Split properties in two, constrained primitives and others

    # We split the properties in two, those of constrained primitives and others.
    # We do this in a separate step instead of duplicating the code to avoid bugs
    # related to DRY on the splitting logic.

    properties_constrained_primitives = []  # type: List[intermediate.Property]
    properties_non_constrained_primitives = []  # type: List[intermediate.Property]
    for prop in cls.properties:
        prop_type = intermediate.beneath_optional(prop.type_annotation)
        if isinstance(prop_type, intermediate.OurTypeAnnotation) and isinstance(
            prop_type.our_type, intermediate.ConstrainedPrimitive
        ):
            properties_constrained_primitives.append(prop)
        else:
            properties_non_constrained_primitives.append(prop)

    # endregion

    # region Include constrained primitive verification in non-recusrive part

    # Since constrained primitives are not included in the recursion, we verify
    # properties of constrained primitives at the non-recurse block as well.
    for prop in properties_constrained_primitives:
        prop_type = intermediate.beneath_optional(prop.type_annotation)
        if isinstance(prop_type, intermediate.OurTypeAnnotation) and isinstance(
            prop_type.our_type, intermediate.ConstrainedPrimitive
        ):
            constrained_primitive_block, error = _generate_verify_property_snippet(
                prop=prop
            )
            if error is not None:
                errors.append(error)
            else:
                assert constrained_primitive_block is not None
                if constrained_primitive_block != "":
                    blocks.append(constrained_primitive_block)

    if len(errors) > 0:
        return None, errors

    # endregion

    # region Generate the recursive part

    recurse_prop_blocks = []  # type: List[Stripped]

    for prop in properties_non_constrained_primitives:
        prop_block, error = _generate_verify_property_snippet(prop=prop)
        if error is not None:
            errors.append(error)
        else:
            assert prop_block is not None
            if prop_block != "":
                recurse_prop_blocks.append(prop_block)

    if len(errors) > 0:
        return None, errors

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
{maybe_disable_that_unused}{I}that: AasTypes.{cls_name},
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


def _generate_transformer(
    symbol_table: intermediate.SymbolTable,
    base_environment: intermediate_type_inference.Environment,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a transformer to double-dispatch an instance to errors."""
    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    # The abstract classes are directly dispatched by the transformer,
    # so we do not need to handle them separately.
    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            transform_key = specific_implementations.ImplementationKey(
                f"Verification/transform_{cls.name}.ts"
            )

            implementation = spec_impls.get(transform_key, None)
            if implementation is None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The transformation snippet is missing "
                        f"for the implementation-specific "
                        f"class {cls.name}: {transform_key}",
                    )
                )
                continue

            blocks.append(spec_impls[transform_key])
        else:
            block, cls_errors = _generate_transform_for_class(
                cls=cls,
                symbol_table=symbol_table,
                base_environment=base_environment,
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
{I}extends AasTypes.AbstractTransformerWithContext<
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

    blocks = [
        Stripped("Verify that the instances of the meta-model satisfy the invariants.")
    ]  # type: List[Stripped]

    first_cls = (
        symbol_table.concrete_classes[0]
        if len(symbol_table.concrete_classes) > 0
        else None
    )  # type: Optional[intermediate.ConcreteClass]

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
import * as AasTypes from "{package_identifier}/types";
import * as AasVerification from "{package_identifier}/verification";

const {an_instance_variable} = new AasTypes.{cls_name}(
{I}// ... some constructor arguments ...
);

for (const error of AasVerification.verify({an_instance_variable})) {{
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
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code of verification logic."""
    errors = []  # type: List[Error]

    module_docstring, module_docstring_error = _generate_module_comment(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if module_docstring_error is not None:
        errors.append(module_docstring_error)
        # NOTE (mristin, 2023-03-18):
        # Allow the execution to continue to catch other errors as well
        module_docstring = Stripped("")

    assert module_docstring is not None

    blocks = [
        module_docstring,
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasCommon from "./common";
import * as AasConstants from "./constants";
import * as AasTypes from "./types";"""
        ),
        Stripped(
            """\
// The generated code might contain deliberately double negations. For example,
// when the constraint is formulated as a NAND and we check that the constraint
// is not fulfilled. Therefore, we disable this linting rule.
/* eslint no-extra-boolean-cast: 0 */"""
        ),
        Stripped(
            f"""\
/**
 * Represent a property access on a path to an erroneous value.
 */
export class PropertySegment {{
{I}/**
{I} * Instance containing the property
{I} */
{I}readonly instance: AasTypes.Class;

{I}/**
{I} * Name of the property
{I} */
{I}readonly name: string;

{I}constructor(instance: AasTypes.Class, name: string) {{
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
        Stripped("export type Segment = PropertySegment | IndexSegment;"),
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
{I}// NOTE (mristin, 2022-11-12):
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
    ]  # type: List[Stripped]

    base_environment = intermediate_type_inference.populate_base_environment(
        symbol_table=symbol_table
    )

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
                environment=base_environment,
            )

            if error is not None:
                errors.append(error)
            else:
                assert implementation is not None
                blocks.append(implementation)

        else:
            # noinspection PyTypeChecker
            assert_never(verification)

    transformer_block, transformer_errors = _generate_transformer(
        symbol_table=symbol_table,
        base_environment=base_environment,
        spec_impls=spec_impls,
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
  that: AasTypes.Class,
  recurse = true
): IterableIterator<VerificationError> {{
{I}yield * VERIFIER.transformWithContext(that, recurse);
}}"""
        )
    )

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            # NOTE (mristin, 2022-11-12):
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
                base_environment=base_environment,
            )

            if constrained_primitive_errors is not None:
                errors.extend(constrained_primitive_errors)
            else:
                assert constrained_primitive_block is not None
                blocks.append(constrained_primitive_block)

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # NOTE (mristin, 2022-11-12):
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
