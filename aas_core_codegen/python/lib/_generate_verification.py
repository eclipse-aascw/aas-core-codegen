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
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.parse import tree as parse_tree, retree as parse_retree
from aas_core_codegen.python import (
    common as python_common,
    naming as python_naming,
    description as python_description,
    transpilation as python_transpilation,
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
                    f"Verification/{func.name}.py"
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
    """Transpile a statement of a pattern verification into Python."""

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_joined_str_values(
        self, values: Sequence[Union[str, parse_tree.FormattedValue]]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Transform the values of a joined string to a Python string literal."""
        # If we do not need interpolation, simply return the string literals
        # joined together by newlines.
        needs_interpolation = any(
            isinstance(value, parse_tree.FormattedValue) for value in values
        )
        if not needs_interpolation:
            return (
                Stripped(
                    python_common.string_literal(
                        "".join(value for value in values)  # type: ignore
                    )
                ),
                None,
            )

        parts = []  # type: List[str]

        # NOTE (mristin, 2022-09-30):
        # See which quotes occur more often in the non-interpolated parts, so that we
        # pick the escaping scheme which will result in as little escapes as possible.
        double_quotes_count = 0
        single_quotes_count = 0

        for value in values:
            if isinstance(value, str):
                double_quotes_count += value.count('"')
                single_quotes_count += value.count("'")

            elif isinstance(value, parse_tree.FormattedValue):
                pass
            else:
                assert_never(value)

        # Pick the escaping scheme
        if single_quotes_count <= double_quotes_count:
            enclosing = "'"
            quoting = python_common.StringQuoting.SINGLE_QUOTES
        else:
            enclosing = '"'
            quoting = python_common.StringQuoting.DOUBLE_QUOTES

        for value in values:
            if isinstance(value, str):
                parts.append(
                    python_common.string_literal(
                        value,
                        quoting=quoting,
                        without_enclosing=True,
                        duplicate_curly_brackets=True,
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

                parts.append(f"{{{code}}}")
            else:
                assert_never(value)

        writer = io.StringIO()
        writer.write("f")
        writer.write(enclosing)
        for part in parts:
            writer.write(part)
        writer.write(enclosing)

        return Stripped(writer.getvalue()), None

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

            # NOTE (mristin, 2022-09-30):
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
        return Stripped(python_naming.variable_name(node.identifier)), None

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
        variable = python_naming.variable_name(node.target.identifier)
        code, error = self.transform(node.value)
        if error is not None:
            return None, error
        assert code is not None

        return Stripped(f"{variable} = {code}"), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_pattern_verification(
    verification: intermediate.PatternVerification,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the verification function that checks the regular expressions."""
    # NOTE (mristin, 2022-09-30):
    # We assume that we performed all the checks at the intermediate stage.

    construct_name = python_naming.function_name(
        Identifier(f"_construct_{verification.name}")
    )

    blocks = []  # type: List[Stripped]

    # region Construct block

    writer = io.StringIO()
    writer.write(
        f"""\
# noinspection SpellCheckingInspection
def {construct_name}() -> Pattern[str]:
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
        writer.write(textwrap.indent(f"return re.compile({pattern_expr})", I))
    else:
        writer.write(
            textwrap.indent(
                f"""\
return re.compile(
{I}{indent_but_first_line(pattern_expr, I)}
)""",
                I,
            )
        )

    blocks.append(Stripped(writer.getvalue()))

    # endregion

    # region Initialize the regex

    regex_name = python_naming.constant_name(Identifier(f"_regex_{verification.name}"))

    blocks.append(Stripped(f"{regex_name} = {construct_name}()"))

    assert len(verification.arguments) == 1
    assert isinstance(
        verification.arguments[0].type_annotation, intermediate.PrimitiveTypeAnnotation
    )
    # noinspection PyUnresolvedReferences
    assert (
        verification.arguments[0].type_annotation.a_type
        == intermediate.PrimitiveType.STR
    )

    arg_name = python_naming.argument_name(verification.arguments[0].name)

    function_name = python_naming.function_name(verification.name)

    writer = io.StringIO()
    writer.write(
        f"""\
def {function_name}({arg_name}: str) -> bool:
"""
    )

    if verification.description is not None:
        (
            docstring,
            docstring_errors,
        ) = python_description.generate_docstring_for_signature(
            description=verification.description,
            context=python_description.Context(
                qualified_module_name=qualified_module_name,
                module=Identifier("verification"),
                cls_or_enum=None,
            ),
        )
        if docstring_errors is not None:
            return None, Error(
                verification.description.parsed.node,
                "Failed to generate the docstring",
                docstring_errors,
            )

        assert docstring is not None

        writer.write(textwrap.indent(docstring, I))
        writer.write("\n")

    writer.write(f"{I}return {regex_name}.match({arg_name}) is not None")

    blocks.append(Stripped(writer.getvalue()))

    # endregion

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    return Stripped(writer.getvalue()), None


class _TranspilableVerificationTranspiler(python_transpilation.Transpiler):
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
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
    ) -> None:
        """Initialize with the given values."""
        python_transpilation.Transpiler.__init__(
            self, type_map=type_map, environment=environment
        )

        self._symbol_table = symbol_table

        self._argument_name_set = frozenset(arg.name for arg in verification.arguments)

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(python_naming.variable_name(node.identifier)), None

        if node.identifier in self._argument_name_set:
            return Stripped(python_naming.argument_name(node.identifier)), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_name = python_naming.constant_name(node.identifier)
            return Stripped(f"aas_constants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(python_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"aas_types.{python_naming.enum_name(node.identifier)}"),
                None,
            )

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to Python. We could not find it neither in the constants, nor in "
            f"verification functions, nor as an enumeration. "
            f"If you expect this name to be transpilable, please contact "
            f"the developers.",
        )


def _transpile_transpilable_verification(
    verification: intermediate.TranspilableVerification,
    symbol_table: intermediate.SymbolTable,
    environment: intermediate_type_inference.Environment,
    qualified_module_name: python_common.QualifiedModuleName,
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

    function_name = python_naming.function_name(verification.name)

    if verification.returns is None:
        return_type = "None"
    else:
        return_type = python_common.generate_type(
            type_annotation=verification.returns, types_module=Identifier("aas_types")
        )

    arg_defs = []  # type: List[Stripped]
    for arg in verification.arguments:
        arg_type = python_common.generate_type(
            arg.type_annotation, types_module=Identifier("aas_types")
        )
        arg_name = python_naming.argument_name(arg.name)
        arg_defs.append(Stripped(f"{arg_name}: {arg_type}"))

    if len(arg_defs) == 0:
        writer.write(
            f"""\
def {function_name}() -> {return_type}:"""
        )
    else:
        writer.write(
            f"""\
def {function_name}(
"""
        )

        for i, arg_def in enumerate(arg_defs):
            if i > 0:
                writer.write(",\n")
            writer.write(textwrap.indent(arg_def, I))

        writer.write("\n")
        writer.write(
            f"""\
) -> {return_type}:"""
        )

    docstring = None  # type: Optional[Stripped]
    if verification.description is not None:
        (
            docstring,
            docstring_errors,
        ) = python_description.generate_docstring_for_signature(
            description=verification.description,
            context=python_description.Context(
                qualified_module_name=qualified_module_name,
                module=Identifier("verification"),
                cls_or_enum=None,
            ),
        )
        if docstring_errors is not None:
            return None, Error(
                verification.description.parsed.node,
                "Failed to generate the docstring",
                docstring_errors,
            )

        assert docstring is not None

        writer.write("\n")
        writer.write(textwrap.indent(docstring, I))

    writer.write(f"\n{I}# pylint: disable=all")

    if docstring is None and len(body) == 0:
        writer.write(f"\n{I}pass")

    for stmt in body:
        writer.write("\n")
        writer.write(textwrap.indent(stmt, I))

    return Stripped(writer.getvalue()), None


class _InvariantTranspiler(python_transpilation.Transpiler):
    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
    ) -> None:
        """Initialize with the given values."""
        python_transpilation.Transpiler.__init__(
            self, type_map=type_map, environment=environment
        )

        self._symbol_table = symbol_table

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(python_naming.variable_name(node.identifier)), None

        if node.identifier == "self":
            # The ``that`` refers to the argument of the verification function.
            return Stripped("that"), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant_name = python_naming.constant_name(node.identifier)
            return Stripped(f"aas_constants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(python_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"aas_types.{python_naming.enum_name(node.identifier)}"),
                None,
            )

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to Python. We could not find it neither in the local variables, "
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
    """Translate the invariant from the meta-model into Python code."""
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
        writer.write("if not (\n")
        writer.write(textwrap.indent(expr, I))
        writer.write("\n):\n")
    else:
        no_parenthesis_type_in_this_context = (
            parse_tree.Index,
            parse_tree.Name,
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
        )

        if isinstance(invariant.parsed.body, no_parenthesis_type_in_this_context):
            not_expr = f"not {expr}"
        else:
            not_expr = f"not ({expr})"

        writer.write(f"if {not_expr}:\n")

    writer.write(f"{I}yield Error(\n")

    # NOTE (mristin, 2022-09-30):
    # We need to wrap the description in multiple literals as a single long
    # string literal is often too much for the readability.
    invariant_description_lines = wrap_text_into_lines(invariant.description)

    for i, literal in enumerate(invariant_description_lines):
        if i < len(invariant_description_lines) - 1:
            writer.write(f"{II}{python_common.string_literal(literal)} +\n")
        else:
            writer.write(f"{II}{python_common.string_literal(literal)}\n")
            writer.write(f"{I})")

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
    generator_for_loop_variables: python_common.GeneratorForLoopVariables,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the snippet to transform a property to verification errors.

    Return an empty string if there is nothing to be verified for the given property.
    """
    # NOTE (mristin, 2022-10-01):
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
        elif isinstance(type_anno.items, intermediate.TupleTypeAnnotation):
            return None, Error(
                prop.parsed.node,
                "We currently implemented verification based on a very limited "
                "pattern matching due to code simplicity. We did not handle "
                "the case of lists of tuples. Please contact "
                "the developers if you need this functionality.",
            )
        else:
            pass
    else:
        pass

    stmts = []  # type: List[Stripped]

    prop_name = python_naming.property_name(prop.name)
    prop_name_literal = python_common.string_literal(prop_name)

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        # There is nothing that we check for primitive types explicitly. The values
        # of the primitive properties are checked at the level of class invariants.
        return Stripped(""), None
    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            # We rely on mypy to check for valid enumerations, so we do not check
            # the enumerations on our side.
            return Stripped(""), None

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            function_name = python_naming.function_name(
                Identifier(f"verify_{type_anno.our_type.name}")
            )

            for_error_in_verify = f"for error in {function_name}(that.{prop_name})"
            # Heuristic to break the lines, very rudimentary
            if len(for_error_in_verify) > 70:
                for_error_in_verify = f"""\
for error in {function_name}(
{II}that.{prop_name}
)"""

            stmts.append(
                Stripped(
                    f"""\
{for_error_in_verify}:
{I}error.path._prepend(
{II}PropertySegment(
{III}that,
{III}{prop_name_literal}
{II})
{I})
{I}yield error"""
                )
            )

        elif isinstance(
            type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            for_error_in_self_transform = (
                f"for error in self.transform(that.{prop_name})"
            )
            # Heuristic to break the lines, very rudimentary
            if len(for_error_in_self_transform) > 70:
                for_error_in_self_transform = f"""\
for error in self.transform(
{II}that.{prop_name}
)"""

            stmts.append(
                Stripped(
                    f"""\
{for_error_in_self_transform}:
{I}error.path._prepend(
{II}PropertySegment(
{III}that,
{III}{prop_name_literal}
{II})
{I})
{I}yield error"""
                )
            )
        else:
            assert_never(type_anno.our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert not isinstance(
            type_anno.items,
            (
                intermediate.OptionalTypeAnnotation,
                intermediate.ListTypeAnnotation,
                intermediate.TupleTypeAnnotation,
            ),
        ), (
            "We chose to implement only a very limited pattern matching; "
            "see the note above in the code."
        )

        loop_variable = next(generator_for_loop_variables)

        for_error: Stripped

        if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
            # NOTE (mristin):
            # There is nothing to verify about the primitive types.
            return Stripped(""), None

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                # NOTE (mristin):
                # There is nothing to verify about the enumeration.
                return Stripped(""), None

            elif isinstance(
                type_anno.items.our_type, intermediate.ConstrainedPrimitive
            ):
                function_name = python_naming.function_name(
                    Identifier(f"verify_{type_anno.items.our_type.name}")
                )

                for_error = Stripped(f"for error in {function_name}({loop_variable})")

                # Heuristic to break the lines, very rudimentary
                if len(for_error) > 70:
                    for_error = Stripped(
                        f"""\
for error in {function_name}(
{II}{loop_variable}
)"""
                    )

            elif isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                for_error = Stripped(
                    f"""for error in self.transform({loop_variable})"""
                )

                if len(for_error) > 70:
                    for_error = Stripped(
                        f"""\
for error in self.transform(
{II}{loop_variable}
)"""
                    )

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.items.our_type)

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.items)

        for_i_item_in_that_prop = (
            f"for i, {loop_variable} in enumerate(that.{prop_name})"
        )

        # Rudimentary heuristics for line breaking
        if len(for_i_item_in_that_prop) > 70:
            for_i_item_in_that_prop = f"""\
for i, {loop_variable} in enumerate(
{II}that.{prop_name}
)"""

        stmts.append(
            Stripped(
                f"""\
{for_i_item_in_that_prop}:
{I}{indent_but_first_line(for_error, I)}:
{II}error.path._prepend(
{III}IndexSegment(
{IIII}that.{prop_name},
{IIII}i
{III})
{II})
{II}error.path._prepend(
{III}PropertySegment(
{IIII}that,
{IIII}{prop_name_literal}
{III})
{II})
{II}yield error"""
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

            item_access = f"that.{prop_name}[{i}]"

            for_error_in_verification: Optional[Stripped]

            if isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
                # NOTE (mristin):
                # There is nothing to verify about the primitive types.
                for_error_in_verification = None

            elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                if isinstance(item_type_anno.our_type, intermediate.Enumeration):
                    # NOTE (mristin):
                    # There is nothing to verify about the enumeration.
                    for_error_in_verification = None

                elif isinstance(
                    item_type_anno.our_type, intermediate.ConstrainedPrimitive
                ):
                    function_name = python_naming.function_name(
                        Identifier(f"verify_{item_type_anno.our_type.name}")
                    )

                    for_error_in_verification = Stripped(
                        f"for error in {function_name}({item_access})"
                    )

                    # Heuristic to break the lines, very rudimentary
                    if len(for_error_in_verification) > 70:
                        for_error_in_verification = Stripped(
                            f"""\
for error in {function_name}(
{II}{item_access}
)"""
                        )

                elif isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    for_error_in_verification = Stripped(
                        f"for error in self.transform({item_access})"
                    )

                    if len(for_error_in_verification) > 70:
                        for_error_in_verification = Stripped(
                            f"""\
for error in self.transform(
{II}{item_access}
)"""
                        )

                else:
                    # noinspection PyTypeChecker
                    assert_never(item_type_anno.our_type)
            else:
                # noinspection PyTypeChecker
                assert_never(item_type_anno)

            if for_error_in_verification is None:
                continue

            stmts.append(
                Stripped(
                    f"""\
{for_error_in_verification}:
{I}error.path._prepend(
{II}IndexSegment(
{III}that.{prop_name},
{III}{i}
{II})
{I})
{I}error.path._prepend(
{II}PropertySegment(
{III}that,
{III}{prop_name_literal}
{II})
{I})
{I}yield error"""
                )
            )

    else:
        assert_never(type_anno)

    verify_block = Stripped("\n".join(stmts))

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return (
            Stripped(
                f"""\
if that.{prop_name} is not None:
{I}{indent_but_first_line(verify_block, I)}"""
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

    # NOTE (mristin, 2022-10-14):
    # We need to generate unique loop variable for each loop since Python tracks
    # the variables in function scope, not block scope.
    generator_for_loop_variables = python_common.GeneratorForLoopVariables()

    for prop in cls.properties:
        block, error = _generate_verify_property_snippet(
            prop=prop, generator_for_loop_variables=generator_for_loop_variables
        )
        if error is not None:
            errors.append(error)
        else:
            assert block is not None
            if block != "":
                blocks.append(block)

    if len(errors) > 0:
        return None, errors

    cls_name = python_naming.class_name(cls.name)

    if len(blocks) == 0:
        blocks.append(
            Stripped(
                f"""\
# No verification has been defined for {cls_name}.
return
# For this uncommon return-yield construction, see:
# https://stackoverflow.com/questions/13243766/how-to-define-an-empty-generator-function
# noinspection PyUnreachableCode
yield"""
            )
        )

    transform_name = python_naming.method_name(Identifier(f"transform_{cls.name}"))

    writer = io.StringIO()
    writer.write(
        f"""\
# noinspection PyMethodMayBeStatic
def {transform_name}(
{II}self,
{II}that: aas_types.{cls_name}
) -> Iterator[Error]:
"""
    )

    for i, stmt in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(stmt, I))

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
                f"Verification/transform_{cls.name}.py"
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
class _Transformer(
{II}aas_types.AbstractTransformer[
{III}Iterator[Error]
{II}]
):
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

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

    no_verification_specified = False
    if len(blocks) == 0:
        no_verification_specified = True
        blocks.append(
            Stripped(
                """\
# There is no verification specified.
return

# Empty generator according to:
# https://stackoverflow.com/a/13243870/1600678
# noinspection PyUnreachableCode
yield"""
            )
        )

    function_name = python_naming.function_name(
        Identifier(f"verify_{constrained_primitive.name}")
    )

    that_type = python_common.PRIMITIVE_TYPE_MAP[constrained_primitive.constrainee]

    writer = io.StringIO()

    if no_verification_specified:
        # NOTE (mristin, 2022-10-02):
        # We provide a function for evolvability even though it does nothing.
        writer.write("# noinspection PyUnusedLocal\n")

    writer.write(
        f"""\
def {function_name}(
{II}that: {that_type}
) -> Iterator[Error]:
{I}\"\"\"Verify the constraints of :paramref:`that`.\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    assert len(errors) == 0
    return Stripped(writer.getvalue()), None


def _generate_module_docstring(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the docstring for the module."""
    docstring_blocks = [
        Stripped("Verify that the instances of the meta-model satisfy the invariants.")
    ]  # type: List[Stripped]

    first_cls = (
        symbol_table.concrete_classes[0]
        if len(symbol_table.concrete_classes) > 0
        else None
    )  # type: Optional[intermediate.ConcreteClass]

    if first_cls is not None:
        cls_name = python_naming.class_name(first_cls.name)
        an_instance_variable = python_naming.variable_name(Identifier("an_instance"))

        docstring_blocks.append(
            Stripped(
                f"""\
Here is an example how to verify an instance of :py:class:`{qualified_module_name}.types.{cls_name}`:

.. code-block::

    import {qualified_module_name}.types as aas_types
    import {qualified_module_name}.verification as aas_verification

    {an_instance_variable} = aas_types.{cls_name}(
        # ... some constructor arguments ...
    )

    for error in aas_verification.verify({an_instance_variable}):
        print(f"{{error.cause}} at: {{error.path}}")"""
            )
        )

    # endregion

    if len(docstring_blocks) == 1:
        doc_escaped = docstring_blocks[0].replace('"""', '\\"\\"\\"')
        docstring = f'"""{doc_escaped}"""'
    else:
        doc_escaped = ("\n\n".join(docstring_blocks)).replace('"""', '\\"\\"\\"')
        docstring = f'''\
"""
{doc_escaped}
"""'''

    return Stripped(docstring)


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
    qualified_module_name: python_common.QualifiedModuleName,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code of verification logic.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    # region Module docstring
    blocks = [
        _generate_module_docstring(
            symbol_table=symbol_table, qualified_module_name=qualified_module_name
        ),
        python_common.WARNING,
        Stripped(
            f"""\
import math
import re
import struct
import sys
from typing import (
{I}Any,
{I}Callable,
{I}Iterable,
{I}Iterator,
{I}List,
{I}Mapping,
{I}Optional,
{I}Pattern,
{I}Sequence,
{I}Set,
{I}Union
)

if sys.version_info >= (3, 8):
{I}from typing import Final
else:
{I}from typing_extensions import Final

from {qualified_module_name} import (
{I}constants as aas_constants,
{I}types as aas_types,
)"""
        ),
        Stripped(
            f"""\
class PropertySegment:
{I}\"\"\"Represent a property access on a path to an erroneous value.\"\"\"

{I}#: Instance containing the property
{I}instance: Final[aas_types.Class]

{I}#: Name of the property
{I}name: Final[str]

{I}def __init__(
{III}self,
{III}instance: aas_types.Class,
{III}name: str
{I}) -> None:
{II}\"\"\"Initialize with the given values.\"\"\"
{II}self.instance = instance
{II}self.name = name

{I}def __str__(self) -> str:
{II}return f'.{{self.name}}'"""
        ),
        Stripped(
            f"""\
class IndexSegment:
{I}\"\"\"Represent an index access on a path to an erroneous value.\"\"\"

{I}#: Sequence containing the item at :py:attr:`~index`
{I}sequence: Final[Sequence[Any]]

{I}#: Index of the item
{I}index: Final[int]

{I}def __init__(
{III}self,
{III}sequence: Sequence[Any],
{III}index: int
{I}) -> None:
{II}\"\"\"Initialize with the given values.\"\"\"
{II}self.sequence = sequence
{II}self.index = index

{I}def __str__(self) -> str:
{II}return f'[{{self.index}}]'"""
        ),
        Stripped("Segment = Union[PropertySegment, IndexSegment]"),
        Stripped(
            f"""\
class Path:
{I}\"\"\"Represent the relative path to the erroneous value.\"\"\"

{I}def __init__(self) -> None:
{II}\"\"\"Initialize as an empty path.\"\"\"
{II}self._segments = []  # type: List[Segment]

{I}@property
{I}def segments(self) -> Sequence[Segment]:
{II}\"\"\"Get the segments of the path.\"\"\"
{II}return self._segments

{I}def _prepend(self, segment: Segment) -> None:
{II}\"\"\"Insert the :paramref:`segment` in front of other segments.\"\"\"
{II}self._segments.insert(0, segment)

{I}def __str__(self) -> str:
{II}return "".join(str(segment) for segment in self._segments)"""
        ),
        Stripped(
            f"""\
class Error:
{I}\"\"\"Represent a verification error in the data.\"\"\"

{I}#: Human-readable description of the error
{I}cause: Final[str]

{I}#: Path to the erroneous value
{I}path: Final[Path]

{I}def __init__(self, cause: str) -> None:
{II}\"\"\"Initialize as an error with an empty path.\"\"\"
{II}self.cause = cause
{II}self.path = Path()

{I}def __repr__(self) -> str:
{II}return f"Error(path={{self.path}}, cause={{self.cause}})\""""
        ),
    ]  # type: List[Stripped]

    errors = []  # type: List[Error]

    base_environment = intermediate_type_inference.populate_base_environment(
        symbol_table=symbol_table
    )

    for verification in symbol_table.verification_functions:
        if isinstance(verification, intermediate.ImplementationSpecificVerification):
            implementation_key = specific_implementations.ImplementationKey(
                f"Verification/{verification.name}.py"
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
                verification=verification, qualified_module_name=qualified_module_name
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
                qualified_module_name=qualified_module_name,
            )

            if error is not None:
                errors.append(error)
            else:
                assert implementation is not None
                blocks.append(implementation)

        else:
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

    blocks.append(Stripped("_TRANSFORMER = _Transformer()"))

    blocks.append(
        Stripped(
            f"""\
def verify(
{II}that: aas_types.Class
) -> Iterator[Error]:
{I}\"\"\"
{I}Verify the constraints of :paramref:`that` recursively.

{I}:param that: instance whose constraints we want to verify
{I}:yield: constraint violations
{I}\"\"\"
{I}yield from _TRANSFORMER.transform(that)"""
        )
    )

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            # NOTE (mristin, 2022-10-01):
            # We do not verify the enumerations explicitly in Python as mypy
            # is capable enough to spot invalid enum literals.
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
            # NOTE (mristin, 2022-10-01):
            # We provide a general dispatch function for the most abstract
            # class ``Class``.
            pass
        else:
            assert_never(our_type)

    blocks.append(python_common.WARNING)

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


# endregion

assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
