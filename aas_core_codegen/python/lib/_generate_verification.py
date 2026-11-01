"""Generate code of verification logic."""
import io
import textwrap
from typing import (
    Dict,
    Final,
    Tuple,
    Optional,
    List,
    Sequence,
    Mapping,
    Union,
)

from icontract import ensure, require

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    assert_never,
    Identifier,
    indent_but_first_line,
    wrap_text_into_lines,
    assert_union_without_excluded,
)
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
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
    errors: List[str] = []

    expected_keys: List[specific_implementations.ImplementationKey] = []

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

        parts: List[str] = []

        # NOTE (mristin):
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
    # NOTE (mristin):
    # We assume that we performed all the checks at the intermediate stage.

    construct_name = python_naming.function_name(
        Identifier(f"_construct_{verification.name.lstrip('_')}")
    )

    blocks: List[Stripped] = []

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

    regex_name = python_naming.constant_name(
        Identifier(f"_regex_{verification.name.lstrip('_')}")
    )

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
            return Stripped(f"our_constants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(python_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"our_types.{python_naming.enum_name(node.identifier)}"),
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
    type_inference: intermediate_type_inference.TypeInference,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Transpile a verification function."""
    inference = type_inference.by_verification[verification]

    transpiler = _TranspilableVerificationTranspiler(
        type_map=inference.type_map,
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

    writer = io.StringIO()

    function_name = python_naming.function_name(verification.name)

    if verification.returns is None:
        return_type = "None"
    else:
        return_type = python_common.generate_type(
            type_annotation=verification.returns, types_module=Identifier("our_types")
        )

    arg_defs: List[Stripped] = []
    for arg in verification.arguments:
        arg_type = python_common.generate_argument_type(
            arg, types_module=Identifier("our_types")
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

    docstring: Optional[Stripped] = None
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
            return Stripped(f"our_constants.{constant_name}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(python_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(f"our_types.{python_naming.enum_name(node.identifier)}"),
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
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Translate the invariant from the meta-model into Python code."""
    inference = type_inference.by_invariant[invariant]

    transpiler = _InvariantTranspiler(
        type_map=inference.type_map,
        environment=inference.environment_with_self,
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
            parse_tree.IsInstance,
        )

        if isinstance(invariant.parsed.body, no_parenthesis_type_in_this_context):
            not_expr = f"not {expr}"
        else:
            not_expr = f"not ({expr})"

        writer.write(f"if {not_expr}:\n")

    writer.write(f"{I}yield Error(\n")

    # NOTE (mristin):
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

    In Python, we verify the constrained primitives, the instances of our classes,
    all the JSON-able values and the integers, which have to lie in the safe integer
    range to be serializable to JSON. We rely on mypy to spot invalid enumeration
    literals, so we do not verify the enumerations at all.
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

    We follow the grammar of the monikers of the composed de/serializers, see
    :py:attr:`aas_core_codegen.python.common.MONIKER_BY_PRIMITIVE_TYPE`, except
    that we name all the instances of our classes and named unions ``class``,
    and that we nest the containers in Polish notation (*e.g.*,
    ``list_of__list_of__class``). The arity of a container is fixed by its kind,
    or spelled out for a tuple, so a nested moniker is still uniquely decodable.

    All the instances are verified with the very same call to ``verify``, so
    the containers of different classes can share one verification function.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"list_of__{_verification_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        return f"set_of__{_verification_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        joined = "__".join(_verification_moniker(item) for item in type_anno.items)
        return f"tuple{len(type_anno.items)}_of__{joined}"

    # NOTE (mristin):
    # A class of the meta-model named ``Class`` would give the same moniker, but
    # it would clash with ``our_types.Class`` in the first place.
    if _is_instance(type_anno):
        return "class"

    # NOTE (mristin):
    # The de/serializers name a constrained primitive by its constrainee, as only
    # the Python type matters there. Here, the constrained primitives are verified
    # differently, so each needs a moniker of its own.
    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.ConstrainedPrimitive
    ):
        return naming.lower_snake_case(type_anno.our_type.name)

    return python_common.atomic_moniker(type_anno)


def _verification_parameter_type(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Generate the type of the value at ``type_anno`` as a function parameter.

    We use the covariant read-only containers so that a single function accepts
    the containers of different classes, all given as ``our_types.Class``.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"Sequence[{_verification_parameter_type(type_anno.items)}]"

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        return f"AbstractSet[{_verification_parameter_type(type_anno.items)}]"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_types = [_verification_parameter_type(item) for item in type_anno.items]

        one_liner = f"Tuple[{', '.join(item_types)}]"
        # Heuristic to break the lines, very rudimentary
        if len(one_liner) <= 60:
            return one_liner

        joined = ",\n".join(item_types)
        return f"""\
Tuple[
{I}{indent_but_first_line(joined, I)}
]"""

    if _is_instance(type_anno):
        return "our_types.Class"

    return python_common.generate_type(type_anno, types_module=Identifier("our_types"))


#: Name of the module-level function verifying an integer
_VERIFY_INT: Final[Identifier] = Identifier("_verify_int")


def _verify_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """Name the module-level function verifying ``type_anno``."""
    return Identifier(f"_verify_{_verification_moniker(type_anno)}")


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
            function = python_naming.function_name(
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
        function = _VERIFY_INT

    elif isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        function = "our_json_value_verification.verify_json_value"

    elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        function = "our_json_value_verification.verify_json_array"

    elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        function = "our_json_value_verification.verify_json_object"

    elif isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        function = _verify_container_name(type_anno)

    else:
        raise AssertionError(
            f"Unexpected type annotation with something to verify: {type_anno}. "
            f"The optionals nested in the containers should have been refused in "
            f"parse._translate._verify_symbol_table."
        )

    for_header = f"for error in {function}({expr})"
    # Heuristic to break the lines, very rudimentary
    if len(for_header) > 70:
        for_header = f"""\
for error in {function}(
{II}{expr}
)"""

    prepend_stmts = "\n".join(
        f"""\
error.path._prepend(
{I}{indent_but_first_line(segment, I)}
)"""
        for segment in segments
    )

    blocks.append(
        Stripped(
            f"""\
{for_header}:
{I}{indent_but_first_line(prepend_stmts, I)}
{I}yield error"""
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
KeySegment(
{I}{expr},
{I}key
)""",
                *segments,
            ],
        )

        blocks.append(
            Stripped(
                f"""\
for key in {expr}:
{I}# NOTE (mristin):
{I}# The key segment names the member whose key is erroneous. The path
{I}# thus leads to the member, and the cause says what is wrong with
{I}# the key which names it.
{I}{indent_but_first_line(key_stmts, I)}"""
            )
        )

    return Stripped("\n\n".join(blocks))


@require(lambda type_anno: _needs_verification(type_anno))
def _generate_verify_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the module-level function verifying ``type_anno``."""
    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_stmts = _generate_verify_into(
            expr="item",
            type_anno=type_anno.items,
            segments=[
                f"""\
IndexSegment(
{I}that,
{I}i
)"""
            ],
        )

        body = Stripped(
            f"""\
for i, item in enumerate(that):
{I}{indent_but_first_line(item_stmts, I)}"""
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        item_stmts = _generate_verify_into(
            expr="item",
            type_anno=type_anno.items,
            segments=[
                f"""\
IndexSegment(
{I}sorted_that,
{I}i
)"""
            ],
        )

        # NOTE (mristin):
        # A set has no index, so we report the position of the item in the sorted
        # order, which is also its position in the serialized array.
        body = Stripped(
            f"""\
sorted_that = sorted(that)
for i, item in enumerate(sorted_that):
{I}{indent_but_first_line(item_stmts, I)}"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = Stripped(
            "\n\n".join(
                _generate_verify_into(
                    expr=f"that[{i}]",
                    type_anno=item_type_anno,
                    segments=[
                        f"""\
IndexSegment(
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
def {name}(
{II}that: {indent_but_first_line(parameter_type, II)}
) -> Iterator[Error]:
{I}\"\"\"Verify the items of :paramref:`that` recursively.\"\"\"
{I}{indent_but_first_line(body, I)}"""
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

        prop_name = python_naming.property_name(prop.name)

        block = _generate_verify_into(
            expr=f"that.{prop_name}",
            type_anno=type_anno,
            segments=[
                f"""\
PropertySegment(
{I}that,
{I}{python_common.string_literal(prop_name)}
)"""
            ],
        )

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            block = Stripped(
                f"""\
if that.{prop_name} is not None:
{I}{indent_but_first_line(block, I)}"""
            )

        blocks.append(block)

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
{II}that: our_types.{cls_name}
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
class _Transformer(
{II}our_types.AbstractTransformer[
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
    # The constrainee has to be serializable to JSON in the first place, so we
    # check its range before its invariants.
    if constrained_primitive.constrainee is intermediate.PrimitiveType.INT:
        blocks.insert(0, Stripped(f"yield from {_VERIFY_INT}(that)"))

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
        # NOTE (mristin):
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
    docstring_blocks: List[Stripped] = [
        Stripped("Verify that the instances of the meta-model satisfy the invariants.")
    ]

    first_cls: Optional[intermediate.ConcreteClass] = (
        symbol_table.concrete_classes[0]
        if len(symbol_table.concrete_classes) > 0
        else None
    )

    if first_cls is not None:
        cls_name = python_naming.class_name(first_cls.name)
        an_instance_variable = python_naming.variable_name(Identifier("an_instance"))

        docstring_blocks.append(
            Stripped(
                f"""\
Here is an example how to verify an instance of :py:class:`{qualified_module_name}.types.{cls_name}`:

.. code-block::

    import {qualified_module_name}.types as our_types
    import {qualified_module_name}.verification as our_verification

    {an_instance_variable} = our_types.{cls_name}(
        # ... some constructor arguments ...
    )

    for error in our_verification.verify({an_instance_variable}):
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
    type_inference: intermediate_type_inference.TypeInference,
    qualified_module_name: python_common.QualifiedModuleName,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code of verification logic.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    # NOTE (mristin):
    # The JSON-able values are verified in a module of their own, which is only
    # generated where the meta-model actually has such a value.
    json_value_verification_import = (
        f"\nimport {qualified_module_name}.jsonvalueverification"
        f" as our_json_value_verification"
        if intermediate_uses.json_types(symbol_table)
        else ""
    )

    # NOTE (mristin):
    # The helpers of the transpiled code live in the common module, so that both
    # the types and the verification can use them.
    imported_modules = [
        "constants as our_constants",
        "reporting as our_reporting",
        "types as our_types",
    ]
    if intermediate_uses.int_call(symbol_table) or intermediate_uses.integers(
        symbol_table
    ):
        imported_modules.insert(0, "common as our_common")

    imported_modules_joined = "\n".join(
        f"{I}{imported_module}," for imported_module in imported_modules
    )

    typing_imports = [
        Identifier("Any"),
        Identifier("Callable"),
        Identifier("Iterable"),
        Identifier("Iterator"),
        Identifier("List"),
        Identifier("Mapping"),
        Identifier("Optional"),
        Identifier("Pattern"),
        Identifier("Sequence"),
        Identifier("Set"),
        Identifier("Tuple"),
        Identifier("Union"),
    ]

    container_blocks_by_name: Dict[Identifier, Stripped] = dict()
    uses_set_container = False

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
                if name in container_blocks_by_name:
                    continue

                container_blocks_by_name[name] = _generate_verify_container(
                    type_anno=type_anno
                )

                if isinstance(type_anno, intermediate.SetTypeAnnotation):
                    uses_set_container = True

    if uses_set_container or Identifier(
        "AbstractSet"
    ) in python_common.typing_imports_for_sets(symbol_table.verification_functions):
        typing_imports.insert(0, Identifier("AbstractSet"))

    typing_imports_joined = ",\n".join(f"{I}{name}" for name in typing_imports)

    # region Module docstring
    blocks: List[Stripped] = [
        _generate_module_docstring(
            symbol_table=symbol_table, qualified_module_name=qualified_module_name
        ),
        python_common.WARNING,
        Stripped(
            f"""\
import collections.abc
import math
import re
import struct
import sys
from typing import (
{typing_imports_joined}
)

if sys.version_info >= (3, 8):
{I}from typing import Final
else:
{I}from typing_extensions import Final

from {qualified_module_name} import (
{imported_modules_joined}
){json_value_verification_import}"""
        ),
        # NOTE (mristin):
        # The vocabulary of the error paths lives in ``reporting``, so that this
        # module and the verification of a JSON-able value report with the very
        # same classes. It is re-exported here, as it belonged to this module
        # before the two were split apart.
        Stripped(
            """\
PropertySegment = our_reporting.PropertySegment
IndexSegment = our_reporting.IndexSegment
KeySegment = our_reporting.KeySegment
Segment = our_reporting.Segment
Path = our_reporting.Path

Error = our_reporting.Error"""
        ),
    ]

    errors: List[Error] = []

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
                type_inference=type_inference,
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
        type_inference=type_inference,
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
{II}that: our_types.Class
) -> Iterator[Error]:
{I}\"\"\"
{I}Verify the constraints of :paramref:`that` recursively.

{I}:param that: instance whose constraints we want to verify
{I}:yield: constraint violations
{I}\"\"\"
{I}yield from _TRANSFORMER.transform(that)"""
        )
    )

    if intermediate_uses.integers(symbol_table):
        blocks.append(
            Stripped(
                f"""\
def {_VERIFY_INT}(
{II}that: int
) -> Iterator[Error]:
{I}\"\"\"Verify that :paramref:`that` lies in the safe integer range.\"\"\"
{I}if not our_common.is_safe_integer(that):
{II}yield Error(our_common.unsafe_integer_message(that))"""
            )
        )

    blocks.extend(container_blocks_by_name.values())

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            # NOTE (mristin):
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
                type_inference=type_inference,
            )

            if constrained_primitive_errors is not None:
                errors.extend(constrained_primitive_errors)
            else:
                assert constrained_primitive_block is not None
                blocks.append(constrained_primitive_block)

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # NOTE (mristin):
            # We provide a general dispatch function for the most abstract
            # class ``Class``.
            pass

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union has no invariants of its own, so there is
            # nothing to generate here.
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
