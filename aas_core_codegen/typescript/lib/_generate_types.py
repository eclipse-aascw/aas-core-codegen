"""Generate code of the data structures representing the meta-model."""

import io
import textwrap
from typing import (
    Optional,
    Dict,
    List,
    Tuple,
    cast,
    Union,
    Mapping,
    Final,
)

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen import specific_implementations
from aas_core_codegen.common import (
    Error,
    Identifier,
    assert_never,
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.intermediate import (
    construction as intermediate_construction,
)
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
    description as typescript_description,
    unrolling as typescript_unrolling,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
)


# region Checks


def _human_readable_identifier(
    something: Union[
        intermediate.Enumeration, intermediate.AbstractClass, intermediate.ConcreteClass
    ]
) -> str:
    """
    Represent ``something`` in a human-readable text.

    The reader should be able to trace ``something`` back to the meta-model.
    """
    # NOTE (mristin, 2022-11-10):
    # This function has been copy-pasted from
    # :py:mod:`aas_core_codegen.python.structure._generate`. We tried to refactor it to
    # :py:mod:`aas_core_codegen.intermediate`, but it turned out that the refactored
    # code was nigh unreadable. So we preferred a little bit of copying to a little
    # bit of complexity.

    result: str

    if isinstance(something, intermediate.Enumeration):
        result = f"meta-model enumeration {something.name!r}"
    elif isinstance(something, intermediate.AbstractClass):
        result = f"meta-model abstract class {something.name!r}"
    elif isinstance(something, intermediate.ConcreteClass):
        result = f"meta-model concrete class {something.name!r}"
    else:
        # noinspection PyTypeChecker
        assert_never(something)

    return result


def _verify_intra_structure_collisions(
    our_type: intermediate.OurType,
) -> Optional[Error]:
    """Verify that no member names collide in the TypeScript structure of our type."""
    errors = []  # type: List[Error]

    if isinstance(our_type, intermediate.Enumeration):
        enum_literal_map = (
            dict()
        )  # type: Dict[Identifier, intermediate.EnumerationLiteral]

        for literal in our_type.literals:
            literal_name = typescript_naming.enum_literal_name(literal.name)
            colliding_literal = enum_literal_map.get(literal_name, None)
            if colliding_literal is not None:
                errors.append(
                    Error(
                        literal.parsed.node,
                        f"The TypeScript name, {literal_name!r}, "
                        f"for the literal {literal.name!r} collides with "
                        f"the TypeScript name of another "
                        f"literal {colliding_literal.name!r}",
                    )
                )
            else:
                enum_literal_map[literal_name] = literal

    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        pass

    elif isinstance(our_type, intermediate.Class):
        observed_member_names = {}  # type: Dict[Identifier, str]

        for prop in our_type.properties:
            prop_name = typescript_naming.property_name(prop.name)
            if prop_name in observed_member_names:
                errors.append(
                    Error(
                        prop.parsed.node,
                        f"TypeScript property {prop_name!r} corresponding "
                        f"to the meta-model property {prop.name!r} collides with "
                        f"the {observed_member_names[prop_name]}",
                    )
                )
            else:
                observed_member_names[prop_name] = (
                    f"TypeScript property {prop_name!r} corresponding to "
                    f"the meta-model property {prop.name!r}"
                )

        observed_constructor_arg_names = {}  # type: Dict[Identifier, str]
        for constructor_arg in our_type.constructor.arguments:
            arg_name = typescript_naming.argument_name(constructor_arg.name)

            if arg_name in observed_constructor_arg_names:
                errors.append(
                    Error(
                        constructor_arg.parsed.node,
                        f"TypeScript argument {arg_name!r} corresponding "
                        f"to the meta-model constructor argument {constructor_arg.name!r} "
                        f"collides with the {observed_constructor_arg_names[arg_name]}",
                    )
                )
            else:
                observed_constructor_arg_names[arg_name] = (
                    f"TypeScript argument {arg_name!r} corresponding to "
                    f"the meta-model constructor argument {constructor_arg.name!r}"
                )

        for method in our_type.methods:
            method_name = typescript_naming.method_name(method.name)

            if method_name in observed_member_names:
                errors.append(
                    Error(
                        method.parsed.node,
                        f"TypeScript method {method_name!r} corresponding "
                        f"to the meta-model method {method.name!r} collides with "
                        f"the {observed_member_names[method_name]}",
                    )
                )
            else:
                observed_member_names[method_name] = (
                    f"TypeScript method {method_name!r} corresponding to "
                    f"the meta-model method {method.name!r}"
                )

            observed_method_arg_names = {}  # type: Dict[Identifier, str]
            for arg in method.arguments:
                arg_name = typescript_naming.argument_name(arg.name)

                if arg_name in observed_method_arg_names:
                    errors.append(
                        Error(
                            arg.parsed.node,
                            f"TypeScript argument {arg_name!r} corresponding "
                            f"to the meta-model method argument {arg.name!r} "
                            f"of the method {method.name} "
                            f"collides with the {observed_method_arg_names[arg_name]}",
                        )
                    )
                else:
                    observed_method_arg_names[arg_name] = (
                        f"TypeScript argument {arg_name!r} corresponding to "
                        f"the meta-model method argument {arg.name!r}"
                    )

    else:
        # noinspection PyTypeChecker
        assert_never(our_type)

    if len(errors) > 0:
        return Error(
            our_type.parsed.node,
            f"Naming collision(s) in TypeScript code for our type {our_type.name!r}",
            underlying=errors,
        )

    return None


def _verify_structure_name_collisions(
    symbol_table: intermediate.SymbolTable,
) -> List[Error]:
    """Verify that the TypeScript names of the structures do not collide."""
    observed_structure_names: Dict[
        Identifier,
        Union[
            intermediate.Enumeration,
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
        ],
    ] = dict()

    errors = []  # type: List[Error]

    # region Inter-structure collisions

    for our_type in symbol_table.our_types:
        if not isinstance(
            our_type,
            (
                intermediate.Enumeration,
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            continue

        name = typescript_naming.name_of(our_type)

        other = observed_structure_names.get(name, None)

        if other is not None:
            errors.append(
                Error(
                    our_type.parsed.node,
                    f"The TypeScript name {name!r} "
                    f"of the "
                    f"{_human_readable_identifier(our_type)} "
                    f"collides with the TypeScript name "
                    f"of the "
                    f"{_human_readable_identifier(other)}",
                )
            )
        else:
            observed_structure_names[name] = our_type

    # endregion

    # region Intra-structure collisions

    for our_type in symbol_table.our_types:
        collision_error = _verify_intra_structure_collisions(our_type=our_type)

        if collision_error is not None:
            errors.append(collision_error)

    # endregion

    return errors


class VerifiedIntermediateSymbolTable(intermediate.SymbolTable):
    """Represent a verified symbol table which can be used for code generation."""

    # noinspection PyInitNewSignature
    def __new__(
        cls, symbol_table: intermediate.SymbolTable
    ) -> "VerifiedIntermediateSymbolTable":
        raise AssertionError("Only for type annotation")


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def verify(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[VerifiedIntermediateSymbolTable], Optional[List[Error]]]:
    """Verify that code can be generated from the ``symbol_table``."""
    errors = []  # type: List[Error]

    structure_name_collisions = _verify_structure_name_collisions(
        symbol_table=symbol_table
    )

    errors.extend(structure_name_collisions)

    if len(errors) > 0:
        return None, errors

    return cast(VerifiedIntermediateSymbolTable, symbol_table), None


# endregion

# region Generation


def _generate_model_type_enum(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the enumerator to represent runtime model type of an instance."""
    blocks = []

    for i, cls in enumerate(symbol_table.concrete_classes):
        literal = typescript_naming.enum_literal_name(cls.name)

        blocks.append(Stripped(f"{literal} = {i}"))

    enum_name = typescript_naming.enum_name(Identifier("Model_type"))

    body = ",\n".join(blocks)

    return Stripped(
        f"""\
/**
 * Represent runtime model type of an instance.
 */
export enum {enum_name} {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_over_model_type_enum(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the iterator over the model type enumerator."""
    blocks = []

    model_type_enum = typescript_naming.enum_name(Identifier("Model_type"))

    for i, cls in enumerate(symbol_table.concrete_classes):
        literal = typescript_naming.enum_literal_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
yield <{model_type_enum}>{i};  // {literal}"""
            )
        )

    over_model_type = typescript_naming.function_name(Identifier("over_model_type"))

    body = "\n".join(blocks)

    return Stripped(
        f"""\
/**
 * Iterate over the literals of {{@link {model_type_enum}}}.
 *
 * @remark
 * TypeScript does not provide an elegant way to iterate over the literals, so
 * this function helps you avoid common errors and pitfalls.
 *
 * @return iterator over the literals
 */
export function *{over_model_type} (
): Iterable<{model_type_enum}> {{
{I}// NOTE (mristin, 2022-12-03):
{I}// We yield numbers instead of literals to avoid name lookups on platforms
{I}// which do not provide JIT compilation of hot paths.
{I}{indent_but_first_line(body, I)}
}}"""
    )


@require(lambda enumeration, literal: id(literal) in enumeration.literal_id_set)
@require(lambda literal: literal.description is not None)
def _generate_comment_for_enumeration_literal(
    enumeration: intermediate.Enumeration,
    literal: intermediate.EnumerationLiteral,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given enumeration literal."""
    # NOTE (mristin, 2022-10-29):
    # We need to state the pre-condition for the second time for mypy.
    assert literal.description is not None

    # fmt: off
    comment, errors = (
        typescript_description.generate_documentation_comment_for_summary_remarks(
            description=literal.description,
            context=typescript_description.Context(
                module=typescript_common.TYPES_MODULE,
                cls_or_enum=enumeration
            )
        )
    )
    # fmt: on

    if errors is not None:
        return None, errors

    assert comment is not None

    return comment, None


@require(lambda cls_or_enum: cls_or_enum.description is not None)
def _generate_comment_for_cls_or_enum(
    cls_or_enum: Union[intermediate.Enumeration, intermediate.ClassUnion],
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the docstring for our type."""
    # NOTE (mristin, 2022-10-29):
    # We need to state the pre-condition for the second time for mypy.
    assert cls_or_enum.description is not None

    # fmt: off
    comment, errors = (
        typescript_description
        .generate_documentation_comment_for_summary_remarks_constraints(
            description=cls_or_enum.description,
            context=typescript_description.Context(
                module=typescript_common.TYPES_MODULE, cls_or_enum=None
            )
        )
    )
    # fmt: on

    if errors is not None:
        return None, errors

    assert comment is not None

    return comment, None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_enum(
    enum: intermediate.Enumeration,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate code for the enum."""
    writer = io.StringIO()

    errors = []  # type: List[Error]

    comment = None  # type: Optional[Stripped]
    if enum.description is not None:
        comment, comment_errors = _generate_comment_for_cls_or_enum(cls_or_enum=enum)

        if comment_errors:
            errors.append(
                Error(
                    enum.description.parsed.node,
                    f"Failed to generate the comment "
                    f"for the enumeration {enum.name!r}",
                    comment_errors,
                )
            )
        else:
            assert comment is not None

    if comment is not None:
        writer.write(comment)
        writer.write("\n")

    name = typescript_naming.enum_name(enum.name)

    if len(enum.literals) == 0:
        writer.write(f"export enum {name} {{}}")
    else:
        writer.write(f"export enum {name} {{\n")

        for i, literal in enumerate(enum.literals):
            if literal.description is not None:
                comment, comment_errors = _generate_comment_for_enumeration_literal(
                    enumeration=enum, literal=literal
                )
                if comment_errors is not None:
                    errors.append(
                        Error(
                            literal.description.parsed.node,
                            f"Failed to generate the documentation comment "
                            f"for enumeration literal {literal.name!r}",
                            comment_errors,
                        )
                    )
                else:
                    assert comment is not None
                    writer.write(textwrap.indent(comment, I))
                    writer.write("\n")

            literal_name = typescript_naming.enum_literal_name(literal.name)

            # NOTE (mristin, 2022-11-10):
            # We optimize for comparisons instead of stringification.
            # The stringification is delegated to a separate module, with efficient
            # array look-ups to get the actual string value of a literal.

            if i == 0:
                writer.write(textwrap.indent(f"{literal_name} = 0", I))
            else:
                writer.write(textwrap.indent(f"{literal_name}", I))

            if i < len(enum.literals) - 1:
                writer.write(",")

            writer.write("\n")

        writer.write("}")

    if len(errors) > 0:
        return None, Error(
            enum.parsed.node,
            f"Failed to generate the TypeScript code for the enumeration {enum.name!r}",
            errors,
        )

    return Stripped(writer.getvalue()), None


def _generate_over_enum(enum: intermediate.Enumeration) -> Stripped:
    """Generate code for the function to iterate over the literals."""
    name = typescript_naming.enum_name(enum.name)
    function_name = typescript_naming.function_name(Identifier(f"over_{enum.name}"))

    statements = [
        f"yield <{name}>{i}; // {typescript_naming.enum_literal_name(literal.name)}"
        for i, literal in enumerate(enum.literals)
    ]
    body = "\n".join(statements)

    return Stripped(
        f"""\
/**
 * Iterate over the literals of {{@link {name}}}.
 *
 * @remark
 * TypeScript does not provide an elegant way to iterate over the literals, so
 * this function helps you avoid common errors and pitfalls.
 *
 * @return iterator over the literals
 */
export function *{function_name}(
): IterableIterator<{name}> {{
{I}// NOTE (mristin, 2022-12-03):
{I}// We yield numbers instead of literals to avoid name lookups on platforms
{I}// which do not provide JIT compilation of hot paths.
{I}{indent_but_first_line(body, I)}
}}"""
    )


class _DescendBodyUnroller(typescript_unrolling.AbstractUnroller):
    """Generate code that unrolls descent into an element."""

    #: If set, generates the code with unrolled yields.
    #: Otherwise, we do not unroll recursively.
    _recurse: Final[bool]

    #: Pre-computed descendability map. A type is descendable if we should unroll it
    #: further.
    _descendability: Final[Mapping[intermediate.TypeAnnotationUnion, bool]]

    #: Generator of loop variable names.
    #:
    #: We generate for each list iteration a new variable to avoid shadowing
    #: of the variables. Even though TypeScript tracks variables in the block scope,
    #: we want to avoid confusion for the reader.
    _generator_for_loop_variables: Final[typescript_common.GeneratorForLoopVariables]

    def __init__(
        self,
        recurse: bool,
        descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
        generator_for_loop_variables: typescript_common.GeneratorForLoopVariables,
    ) -> None:
        """Initialize with the given values."""
        self._recurse = recurse
        self._descendability = descendability
        self._generator_for_loop_variables = generator_for_loop_variables

    def _unroll_primitive_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.PrimitiveTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[typescript_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        # We can not descend into a primitive type.
        return []

    def _unroll_our_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OurTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[typescript_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            # We can not descend into an enumeration.
            return []

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # We can not descend into a primitive type.
            return []

        assert isinstance(our_type, intermediate.Class)  # Exhaustively match

        result = [typescript_unrolling.Node(f"yield {unrollee_expr};", children=[])]

        if self._recurse:
            if self._descendability[type_annotation]:
                result.append(
                    typescript_unrolling.Node(
                        text=f"yield * {unrollee_expr}.descend();",
                        children=[],
                    )
                )

        return result

    def _unroll_list_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.ListTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[typescript_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        if (
            not self._recurse
            and isinstance(type_annotation.items, intermediate.OurTypeAnnotation)
            and isinstance(
                type_annotation.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            )
        ):
            return [typescript_unrolling.Node(f"yield * {unrollee_expr};", children=[])]

        loop_var = next(self._generator_for_loop_variables)
        children = self.unroll(
            unrollee_expr=loop_var,
            type_annotation=type_annotation.items,
            path=[],  # Path is unused in this context
            list_loop_level=list_loop_level + 1,
        )

        if len(children) == 0:
            return []

        node = typescript_unrolling.Node(
            text=f"for (const {loop_var} of {unrollee_expr})",
            children=children,
        )

        return [node]

    def _unroll_optional_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OptionalTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[typescript_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        children = self.unroll(
            unrollee_expr=unrollee_expr,
            type_annotation=type_annotation.value,
            path=path,
            list_loop_level=list_loop_level,
        )

        if len(children) == 0:
            return []

        return [
            typescript_unrolling.Node(
                text=f"if ({unrollee_expr} !== null)", children=children
            )
        ]

    def _unroll_tuple_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.TupleTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[typescript_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        # NOTE (mristin):
        # Unlike lists, tuples are heterogeneous and fixed-length, so we unroll
        # every item at its own fixed index instead of looping.
        result = []  # type: List[typescript_unrolling.Node]
        for i, item_type_annotation in enumerate(type_annotation.items):
            result.extend(
                self.unroll(
                    unrollee_expr=f"{unrollee_expr}[{i}]",
                    type_annotation=item_type_annotation,
                    path=[],  # Path is unused in this context
                    list_loop_level=list_loop_level,
                )
            )

        return result


def _generate_descend_body(cls: intermediate.ConcreteClass, recurse: bool) -> Stripped:
    """
    Generate the body of the ``descend`` and ``descend_once`` methods.

    With this function, we unroll the recursion as a simple optimization
    in the recursive case.
    """
    blocks = []  # type: List[Stripped]

    generator_for_loop_variables = typescript_common.GeneratorForLoopVariables()

    for prop in cls.properties:
        descendability = intermediate.map_descendability(
            type_annotation=prop.type_annotation
        )

        if not descendability[prop.type_annotation]:
            continue

        # region Unroll

        unroller = _DescendBodyUnroller(
            recurse=recurse,
            descendability=descendability,
            generator_for_loop_variables=generator_for_loop_variables,
        )

        roots = unroller.unroll(
            unrollee_expr=f"this.{typescript_naming.property_name(prop.name)}",
            type_annotation=prop.type_annotation,
            path=[],  # We do not use path in this context
            list_loop_level=0,
        )

        assert len(roots) > 0, (
            "Since the type annotation was descendable, we must have obtained "
            "at least one unrolling node"
        )

        blocks.extend(Stripped(typescript_unrolling.render(root)) for root in roots)

        # endregion

    if len(blocks) == 0:
        blocks.append(Stripped("// No descendable properties"))

    return Stripped("\n\n".join(blocks))


def _generate_descend_once_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the ``descend_once`` method for the concrete class ``cls``."""

    body = _generate_descend_body(cls=cls, recurse=False)

    return Stripped(
        f"""\
/**
 * Iterate over the instances referenced from this instance.
 *
 * We do not recurse into the referenced instances.
 *
 * @returns Iterator over the referenced instances
 */
*descendOnce(): IterableIterator<Class> {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_descend_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the recursive ``descend`` method for the concrete class ``cls``."""

    body = _generate_descend_body(cls=cls, recurse=True)

    return Stripped(
        f"""\
/**
 * Iterate recursively over the instances referenced from this instance.
 *
 * @returns Iterator over the referenced instances
 */
*descend(): IterableIterator<Class> {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_default_value(
    default: intermediate.Default,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate code representing the default value of an argument."""
    code: str

    if isinstance(default, intermediate.DefaultPrimitive):
        if default.value is None:
            code = "null"
        elif isinstance(default.value, bool):
            code = typescript_common.boolean_literal(default.value)
        elif isinstance(default.value, int):
            if not typescript_common.representable_as_number(default.value):
                return None, Error(
                    default.parsed.node,
                    f"The value is not representable as a double-precision "
                    f"floating point number: {default.value}",
                )
            code = typescript_common.numeric_literal(default.value)
        elif isinstance(default.value, float):
            code = typescript_common.numeric_literal(default.value)
        elif isinstance(default.value, str):
            code = typescript_common.string_literal(default.value)
        else:
            # noinspection PyTypeChecker
            assert_never(default.value)

    elif isinstance(default, intermediate.DefaultEnumerationLiteral):
        code = ".".join(
            [
                typescript_naming.enum_name(default.enumeration.name),
                typescript_naming.enum_literal_name(default.literal.name),
            ]
        )
    else:
        # noinspection PyTypeChecker
        assert_never(default)

    return Stripped(code), None


@require(lambda cls: not cls.is_implementation_specific)
@require(lambda cls: not cls.constructor.is_implementation_specific)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_constructor(
    cls: intermediate.ClassUnion,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the constructor function for the given concrete class ``cls``.

    Return empty string if there is an empty constructor.
    """
    if (
        len(cls.constructor.arguments) == 0
        and len(cls.constructor.inlined_statements) == 0
    ):
        return Stripped(""), None

    blocks = []  # type: List[str]

    arg_codes = []  # type: List[str]
    for arg in cls.constructor.arguments:
        arg_type = typescript_common.generate_type(type_annotation=arg.type_annotation)
        arg_name = typescript_naming.argument_name(arg.name)

        if arg.default is None:
            arg_codes.append(Stripped(f"{arg_name}: {arg_type}"))
        else:
            default_value, default_value_error = _generate_default_value(arg.default)
            if default_value_error is not None:
                return None, Error(
                    cls.parsed.node,
                    f"Failed to generate the default value for "
                    f"the constructor argument {arg.name!r} of class {cls.name!r}",
                    [default_value_error],
                )

            assert default_value is not None

            arg_codes.append(Stripped(f"{arg_name}: {arg_type} = {default_value}"))

    if len(arg_codes) == 0:
        blocks.append("constructor() {")
    if len(arg_codes) == 1:
        blocks.append(f"constructor({arg_codes[0]}) {{")
    else:
        arg_block = ",\n".join(arg_codes)
        blocks.append(
            Stripped(
                f"""\
constructor(
{I}{indent_but_first_line(arg_block, I)}
) {{"""
            )
        )

    body = ["super();"]  # type: List[str]

    for stmt in cls.constructor.inlined_statements:
        if isinstance(stmt, intermediate_construction.AssignArgument):
            if stmt.default is None:
                body.append(
                    f"this.{typescript_naming.property_name(stmt.name)} = "
                    f"{typescript_naming.argument_name(stmt.argument)};"
                )
            else:
                if isinstance(stmt.default, intermediate_construction.EmptyList):
                    prop = cls.properties_by_name[stmt.name]

                    type_anno = prop.type_annotation
                    while isinstance(type_anno, intermediate.OptionalTypeAnnotation):
                        type_anno = type_anno.value

                    prop_type = typescript_common.generate_type(
                        type_annotation=type_anno
                    )

                    arg_name = typescript_naming.argument_name(stmt.argument)

                    body.append(
                        f"""\
this.{typescript_naming.property_name(stmt.name)} = ({arg_name} !== null)
{I}? {arg_name}
{I}: new {prop_type}();"""
                    )
                elif isinstance(
                    stmt.default, intermediate_construction.DefaultEnumLiteral
                ):
                    literal_code = ".".join(
                        [
                            typescript_naming.enum_name(stmt.default.enum.name),
                            typescript_naming.enum_literal_name(
                                stmt.default.literal.name
                            ),
                        ]
                    )

                    arg_name = typescript_naming.argument_name(stmt.argument)

                    body.append(
                        Stripped(
                            f"""\
this.{typescript_naming.property_name(stmt.name)} = ({arg_name})
{I}? {arg_name}
{I}: {literal_code};"""
                        )
                    )
                else:
                    # noinspection PyTypeChecker
                    assert_never(stmt.default)

        else:
            # noinspection PyTypeChecker
            assert_never(stmt)

    blocks.append("\n".join(textwrap.indent(stmt_code, I) for stmt_code in body))

    blocks.append("}")

    return Stripped("\n".join(blocks)), None


@require(lambda cls, prop: id(prop) in cls.property_id_set)
@require(lambda prop: prop.description is not None)
def _generate_comment_for_property(
    cls: intermediate.ClassUnion,
    prop: intermediate.Property,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given property."""
    # NOTE (mristin, 2022-10-29):
    # We need to write a double assertion for mypy.
    assert prop.description is not None

    # fmt: off
    comment, errors = (
        typescript_description
        .generate_documentation_comment_for_summary_remarks_constraints(
            description=prop.description,
            context=typescript_description.Context(
                module=typescript_common.TYPES_MODULE,
                cls_or_enum=cls,
            )
        )
    )
    # fmt: on

    if errors is not None:
        return None, errors

    assert comment is not None

    return comment, None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_interface(
    interface: intermediate.Interface,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate code for the given ``interface``."""
    # Code blocks separated by double newlines and indented once
    blocks = []  # type: List[Stripped]

    # region Properties

    for prop in interface.properties:
        prop_type = typescript_common.generate_type(
            type_annotation=prop.type_annotation
        )
        prop_name = typescript_naming.property_name(prop.name)

        if prop.description is not None:
            (
                prop_comment,
                prop_comment_errors,
            ) = _generate_comment_for_property(cls=interface.base, prop=prop)

            if prop_comment_errors is not None:
                return None, Error(
                    prop.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for the property {prop.name!r}",
                    prop_comment_errors,
                )

            blocks.append(Stripped(f"{prop_comment}\n" f"{prop_name}: {prop_type};"))
        else:
            blocks.append(Stripped(f"{prop_name}: {prop_type};"))

    # endregion

    # region Signatures

    for signature in interface.signatures:
        signature_blocks = []  # type: List[Stripped]

        if signature.description is not None:
            (
                signature_comment,
                signature_comment_errors,
            ) = typescript_description.generate_documentation_comment_for_signature(
                signature.description,
                context=typescript_description.Context(
                    module=typescript_common.TYPES_MODULE, cls_or_enum=interface.base
                ),
            )

            if signature_comment_errors is not None:
                return None, Error(
                    signature.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for signature {signature.name!r}",
                    signature_comment_errors,
                )

            assert signature_comment is not None

            signature_blocks.append(signature_comment)

        # fmt: off
        # noinspection PyTypeChecker
        returns = (
            typescript_common.generate_type(type_annotation=signature.returns)
            if signature.returns is not None else "void"
        )
        # fmt: on

        arg_codes = []  # type: List[Stripped]
        for arg in signature.arguments:
            arg_type = typescript_common.generate_type(
                type_annotation=arg.type_annotation
            )
            arg_name = typescript_naming.argument_name(arg.name)
            arg_codes.append(Stripped(f"{arg_name}: {arg_type}"))

        signature_name = typescript_naming.method_name(signature.name)
        if len(arg_codes) > 2:
            arg_block = ",\n".join(arg_codes)
            signature_blocks.append(
                Stripped(
                    f"""\
{signature_name}(
{I}{indent_but_first_line(arg_block, I)}
): {returns};"""
                )
            )
        elif len(arg_codes) == 1:
            signature_blocks.append(
                Stripped(f"{signature_name}({arg_codes[0]}): {returns};")
            )
        else:
            assert len(arg_codes) == 0
            signature_blocks.append(Stripped(f"{signature_name}(): {returns};"))

        blocks.append(Stripped("\n".join(signature_blocks)))

    # region over_X_or_empty getter

    for prop in interface.properties:
        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            prop_name = typescript_naming.property_name(prop.name)
            items_type = typescript_common.generate_type(
                prop.type_annotation.value.items
            )

            over_x_or_empty = typescript_naming.method_name(
                Identifier(f"over_{prop.name}_or_empty")
            )

            blocks.append(
                Stripped(
                    f"""\
/**
 * Yield from {{@link {prop_name}}} if it is set, or yield nothing.
 */
{over_x_or_empty}(): IterableIterator<{items_type}>;"""
                )
            )

    # endregion

    comment = None  # type: Optional[Stripped]
    if interface.description is not None:
        # fmt: off
        comment, comment_errors = (
            typescript_description
            .generate_documentation_comment_for_summary_remarks_constraints(
                interface.description,
                context=typescript_description.Context(
                    module=typescript_common.TYPES_MODULE,
                    cls_or_enum=interface.base
                )
            )
        )
        # fmt: on

        if comment_errors is not None:
            return None, Error(
                interface.description.parsed.node,
                "Failed to generate the documentation comment",
                comment_errors,
            )

        assert comment is not None

    empty_interface = False
    if len(blocks) == 0:
        blocks = [Stripped("// Intentionally empty.")]
        empty_interface = True

    writer = io.StringIO()
    if comment is not None:
        writer.write(comment)
        writer.write("\n")

    name = typescript_naming.interface_name(interface.name)

    if empty_interface:
        writer.write(
            "// eslint-disable-next-line @typescript-eslint/no-empty-interface\n"
        )

    if len(interface.inheritances) == 0:
        writer.write(
            f"""\
export interface {name} extends Class {{
"""
        )
    elif len(interface.inheritances) == 1:
        # NOTE (mristin, 2022-12-07):
        # We can omit Class in the list of inheritances as one of the parents already
        # extends it.
        writer.write(
            f"""\
export interface {name}
{I}extends {typescript_naming.interface_name(interface.inheritances[0].name)} {{
"""
        )
    else:
        # NOTE (mristin, 2022-12-07):
        # We can omit Class in the list of inheritances as one of the parents already
        # extends it.
        writer.write(
            f"""\
export interface {name}
"""
        )

        for i, inheritance in enumerate(interface.inheritances):
            if i == 0:
                writer.write(
                    f"""\
{I}extends {typescript_naming.interface_name(inheritance.name)},
"""
                )
            elif i < len(interface.inheritances) - 1:
                writer.write(
                    f"""\
{II}{typescript_naming.interface_name(inheritance.name)},
"""
                )
            else:
                writer.write(
                    f"""\
{II}{typescript_naming.interface_name(inheritance.name)} {{
"""
                )

    for i, code in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(code, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


@require(lambda cls: not cls.is_implementation_specific)
@require(lambda concrete_cls_index: concrete_cls_index >= 0)
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_class(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
    concrete_cls_index: int,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate code for the given concrete class ``cls``.

    ``concrete_cls_index`` refers to the number of the concrete class in
    the ``concrete_classes`` of the symbol table.
    """
    # NOTE (mristin):
    # Code blocks of the class body separated by double newlines and indented once.

    model_type_enum = typescript_naming.enum_name(Identifier("Model_type"))
    model_type_getter = typescript_naming.method_name(Identifier("model_type"))

    model_type_literal = typescript_naming.enum_literal_name(Identifier(cls.name))

    blocks = [
        Stripped(
            f"""\
/**
 * Indicate the runtime model type of the instance.
 */
{model_type_getter}(): {model_type_enum} {{
{I}// NOTE (mristin, 2022-12-03):
{I}// We yield numbers instead of literals to avoid name lookups on platforms
{I}// which do not provide JIT compilation of hot paths.
{I}return <{model_type_enum}>{concrete_cls_index};  // {model_type_literal}
}}"""
        )
    ]  # type: List[Stripped]

    # region Property definitions

    for prop in cls.properties:
        prop_comment = None  # type: Optional[Stripped]
        if prop.description is not None:
            prop_comment, prop_comment_errors = _generate_comment_for_property(
                cls=cls, prop=prop
            )
            if prop_comment_errors is not None:
                return None, Error(
                    prop.description.parsed.node,
                    "Failed to generate the property comment",
                    prop_comment_errors,
                )
            else:
                assert prop_comment is not None

        prop_type = typescript_common.generate_type(
            type_annotation=prop.type_annotation
        )
        prop_name = typescript_naming.property_name(prop.name)

        writer = io.StringIO()
        if prop_comment is not None:
            writer.write(prop_comment)
            writer.write("\n")
        writer.write(f"{prop_name}: {prop_type};")
        blocks.append(Stripped(writer.getvalue()))

    # endregion

    # region over_X_or_empty getter

    for prop in cls.properties:
        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            prop_name = typescript_naming.property_name(prop.name)
            items_type = typescript_common.generate_type(
                prop.type_annotation.value.items
            )

            over_x_or_empty = typescript_naming.method_name(
                Identifier(f"over_{prop.name}_or_empty")
            )

            blocks.append(
                Stripped(
                    f"""\
/**
 * Yield from {{@link {prop_name}}} if it is set, or yield nothing.
 */
*{over_x_or_empty}(): IterableIterator<{items_type}> {{
{I}if (this.{prop_name} !== null) {{
{II}yield * this.{prop_name};
{I}}}
{I}return;
}}"""
                )
            )

    # endregion

    # region Methods

    errors = []  # type: List[Error]

    for method in cls.methods:
        if isinstance(method, intermediate.ImplementationSpecificMethod):
            implementation_key = specific_implementations.ImplementationKey(
                f"Types/{method.specified_for.name}/{method.name}.ts"
            )

            implementation = spec_impls.get(implementation_key, None)

            if implementation is None:
                errors.append(
                    Error(
                        method.parsed.node,
                        f"The implementation is missing for "
                        f"the implementation-specific method: {implementation_key}",
                    )
                )
                continue

            blocks.append(implementation)
        else:
            errors.append(
                Error(
                    cls.parsed.node,
                    "(mristin, 2022-11-10) "
                    "At the moment, we do not transpile the method body and "
                    "its contracts. We want to finish the meta-model for the V3, "
                    "fix de/serialization and generate SDKs for a couple of languages "
                    "before taking on this rather hard task.",
                )
            )

    blocks.append(_generate_descend_once_method(cls=cls))

    blocks.append(_generate_descend_method(cls=cls))

    visit_name = typescript_naming.method_name(Identifier(f"visit_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
/**
 * Dispatch `visitor` on this instance.
 *
 * @param visitor - to visit this instance
 */
accept(visitor: AbstractVisitor): void {{
{I}visitor.{visit_name}(this);
}}"""
        )
    )

    visit_with_context_name = typescript_naming.method_name(
        Identifier(f"visit_{cls.name}_with_context")
    )

    blocks.append(
        Stripped(
            f"""\
/**
 * Dispatch `visitor` with `context` on this instance.
 *
 * @param visitor - to visit this instance
 * @param context - to be passed along to the dispatched visitor method
 * @typeParam ContextT - type of the context
 */
acceptWithContext<ContextT>(
{I}visitor: AbstractVisitorWithContext<ContextT>,
{I}context: ContextT
) {{
{I}visitor.{visit_with_context_name}(this, context);
}}"""
        )
    )

    transform_name = typescript_naming.method_name(Identifier(f"transform_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
/**
 * Dispatch the `transformer` on this instance.
 *
 * @param transformer - to transform this instance
 * @returns transformation of this instance
 * @paramType T - type of the transformation result
 */
transform<T>(transformer: AbstractTransformer<T>): T {{
{I}return transformer.{transform_name}(this);
}}"""
        )
    )

    transform_with_context_name = typescript_naming.method_name(
        Identifier(f"transform_{cls.name}_with_context")
    )

    blocks.append(
        Stripped(
            f"""\
/**
 * Dispatch the `transformer` on this instance in `context`.
 *
 * @param transformer - to transform this instance
 * @param context - to be passed along to the `transformer`
 * @returns transformation of this instance
 * @paramType T - type of the transformation result
 * @paramType ContextT - type of the transformation context
 */
transformWithContext<ContextT, T>(
{I}transformer: AbstractTransformerWithContext<ContextT, T>,
{I}context: ContextT
): T {{
{I}return transformer.{transform_with_context_name}(
{II}this, context
{I});
}}"""
        )
    )

    # endregion

    # region Constructor

    if cls.constructor.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"Types/{cls.name}/{cls.name}.py"
        )
        implementation = spec_impls.get(implementation_key, None)

        if implementation is None:
            errors.append(
                Error(
                    cls.parsed.node,
                    f"The implementation of the implementation-specific constructor "
                    f"is missing: {implementation_key}",
                )
            )
        else:
            blocks.append(implementation)
    else:
        constructor_block, error = _generate_constructor(cls=cls)

        if error is not None:
            errors.append(error)
        else:
            assert constructor_block is not None

            # NOTE (mristin, 2022-06-21):
            # Empty constructor will be automatically generated by the interpreter.
            if constructor_block != "":
                blocks.append(constructor_block)

    # endregion

    if len(errors) > 0:
        return None, Error(
            cls.parsed.node,
            f"Failed to generate the code for the class {cls.name}",
            errors,
        )

    if len(blocks) == 0:
        blocks = [Stripped("// Intentionally empty.")]

    # region Description

    comment = None  # type: Optional[Stripped]
    if cls.description is not None:
        comment, comment_errors = _generate_comment_for_cls_or_enum(cls_or_enum=cls)
        if comment_errors is not None:
            return None, Error(
                cls.description.parsed.node,
                f"Failed to generate the documentation comment for class {cls.name!r}",
                comment_errors,
            )

        assert comment is not None

    # endregion

    # region Implements

    # NOTE (mristin, 2022-12-14):
    # Since JavaScript and hence TypeScript do not support multiple inheritance, we
    # model all the abstract classes as interfaces. Our class therefore extends only
    # the most general class ``Class``, but implements all the corresponding interfaces.
    #
    # Interfaces are only descriptive in TypeScript, so we can not use them directly
    # for efficient type switching at runtime. To implement type switches, we rely
    # on transformer pattern, where we generate the corresponding type-switching
    # transformers. See ``AS_*_TRANSFORMER``'s.

    interface_names = []  # type: List[Identifier]

    if len(cls.concrete_descendants) > 0:
        # NOTE (mristin, 2022-12-14):
        # We do not have to add any other interfaces, as the interface corresponding
        # to this concrete class will already entail all the antecedents.

        assert cls.interface is not None, (
            f"Expected interface for the class {cls.name!r} "
            f"as it has concrete descendants"
        )

        interface_names.append(typescript_naming.interface_name(cls.name))
    else:
        for inheritance in cls.inheritances:
            assert inheritance.interface is not None, (
                f"Expected interface in the parent class {inheritance.name!r} "
                f"of class {cls.name!r}"
            )

            interface_names.append(
                typescript_naming.interface_name(inheritance.interface.name)
            )

    # endregion

    writer = io.StringIO()
    if comment is not None:
        writer.write(comment)
        writer.write("\n")

    name = typescript_naming.class_name(cls.name)

    if len(interface_names) == 0:
        writer.write(
            f"""\
export class {name} extends Class {{
"""
        )
    else:
        interface_names_joined = ",\n".join(interface_names)
        writer.write(
            f"""\
export class {name}
{I}extends Class
{I}implements {indent_but_first_line(interface_names_joined, I)} {{
"""
        )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_abstract_visitor(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate code for the abstract visitor."""
    blocks = [
        Stripped(
            f"""\
/**
 * Double-dispatch on `that`.
 */
visit(that: Class): void {{
{I}that.accept(this);
}}"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        visit_name = typescript_naming.method_name(Identifier(f"visit_{cls.name}"))
        cls_name = typescript_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
/**
 * Visit `that`.
 *
 * @param that - instance to be visited
 */
abstract {visit_name}(
{I}that: {cls_name}
): void;"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Visit the instances of the model.
 */
export abstract class AbstractVisitor {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_abstract_visitor_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the abstract visitor with context."""
    blocks = [
        Stripped(
            f"""\
/**
 * Double-dispatch on `that` in `context`.
 *
 * @param that - instance to be visited
 * @param context - of the visitation
 */
visitWithContext(
{I}that: Class,
{I}context: ContextT
): void {{
{I}that.acceptWithContext(this, context);
}}"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        visit_with_context_name = typescript_naming.method_name(
            Identifier(f"visit_{cls.name}_with_context")
        )
        cls_name = typescript_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
/**
 * Visit `that` in `context`.
 *
 * @param that - instance to be visited
 * @param context - of the visitation
 */
abstract {visit_with_context_name}(
{I}that: {cls_name},
{I}context: ContextT
): void;"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Visit the instances of the model with context.
 *
 * @typeParam ContextT - type of the visitation context
 */
export abstract class AbstractVisitorWithContext<ContextT> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_pass_through_visitor(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate code for the pass-through visitor."""
    blocks = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        visit_name = typescript_naming.method_name(Identifier(f"visit_{cls.name}"))
        cls_name = typescript_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
/**
 * Visit `that`.
 *
 * @param that - instance to be visited
 */
{visit_name}(
{I}that: {cls_name}
): void {{
{I}for (const another of that.descendOnce()) {{
{II}this.visit(another);
{I}}}
}}"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Visit the instances of the model without action.
 *
 * @remarks
 * This visitor is not meant to be directly used. Instead, you usually
 * inherit from it, and implement only the relevant visit methods.
 */
export class PassThroughVisitor extends AbstractVisitor {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_pass_through_visitor_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the pass-through visitor with context."""
    blocks = [
        Stripped(
            f"""\
/**
 * Double-dispatch on `that` in `context`.
 */
visitWithContext(
{I}that: Class,
{I}context: ContextT
): void {{
{I}that.acceptWithContext(this, context);
}}"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        visit_with_context_name = typescript_naming.method_name(
            Identifier(f"visit_{cls.name}_with_context")
        )
        cls_name = typescript_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
/**
 * Visit `that` in `context`.
 *
 * @param that - instance to be visited
 * @param context - of the visitation
 */
{visit_with_context_name}(
{I}that: {cls_name},
{I}context: ContextT
): void {{
{I}for (const another of that.descendOnce()) {{
{II}this.visitWithContext(another, context);
{I}}}
}}"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Visit the instances of the model without action and in context.
 *
 * @remarks
 * This visitor is not meant to be directly used. Instead, you usually
 * inherit from it, and implement only the relevant visit methods.
 */
export class PassThroughVisitorWithContext<ContextT>
{II}extends AbstractVisitorWithContext<ContextT> {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_abstract_transformer(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate code for the abstract transformer."""
    blocks = [
        Stripped(
            f"""\
/**
 * Double-dispatch on `that`.
 */
transform(that: Class): T {{
{I}return that.transform(this);
}}"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        transform_name = typescript_naming.method_name(
            Identifier(f"transform_{cls.name}")
        )

        cls_name = typescript_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
/**
 * Transform `that`.
 *
 * @param that - instance to be transformed
 * @returns transformed `that`
 */
abstract {transform_name}(
{I}that: {cls_name}
): T;"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Transform the instance of the model.
 *
 * @typeParam T - type of the transformation result
 */
export abstract class AbstractTransformer<T> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_abstract_transformer_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the abstract transformer with context."""
    blocks = [
        Stripped(
            f"""\
/**
 * Double-dispatch on `that` in `context`.
 *
 * @param that - instance to be transformed
 * @param context - of the transformation
 * @returns transformed `that`
 */
transformWithContext(
{I}that: Class,
{I}context: ContextT
): T {{
{I}return that.transformWithContext(this, context);
}}"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        transform_with_context_name = typescript_naming.method_name(
            Identifier(f"transform_{cls.name}_with_context")
        )

        cls_name = typescript_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
/**
 * Transform `that` in `context`.
 *
 * @param that - instance to be transformed
 * @param context - of the transformation
 * @returns transformed `that`
 */
abstract {transform_with_context_name}(
{I}that: {cls_name},
{I}context: ContextT
): T;"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Transform the instances of the model in context.
 *
 * @typeParam ContextT - type of the transformation context
 * @typeParam T - type of the transformation result
 */
export abstract class AbstractTransformerWithContext<ContextT, T> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_transformer_with_default(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the transformer with default transformation."""
    blocks = [
        Stripped(
            """\
/**
 * Default value which is returned if no override of the transformation
 */
defaultResult: T"""
        ),
        Stripped(
            f"""\
/**
 * Initialize with the given `default` value.
 *
 * @param defaultResult - returned if no override of the transformation
 */
constructor(defaultResult: T) {{
{I}super();
{I}this.defaultResult = defaultResult;
}}"""
        ),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        transform_name = typescript_naming.method_name(
            Identifier(f"transform_{cls.name}")
        )

        cls_name = typescript_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
/**
 * Transform `that`.
 *
 * @param that - instance to be transformed
 * @returns transformed `that`
 */
/* eslint-disable @typescript-eslint/no-unused-vars */
{transform_name}(
{I}that: {cls_name}
): T {{
{I}return this.defaultResult;
}}
/* eslint-enable @typescript-eslint/no-unused-vars */"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Transform the instances of the model.
 *
 * @remarks
 * If you do not override the transformation methods, they simply
 * return {@link defaultResult}.
 *
 * @typeParam T - type of the transformation result
 */
export class TransformerWithDefault<T> extends AbstractTransformer<T> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_transformer_with_default_and_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the transformer with default transformation and context."""
    blocks = [
        Stripped(
            """\
/**
 * Default value which is returned if no override of the transformation
 */
defaultResult: T"""
        ),
        Stripped(
            f"""\
/**
 * Initialize with the given `default` value.
 *
 * @param defaultResult - returned if no override of the transformation
 */
constructor(defaultResult: T) {{
{I}super();
{I}this.defaultResult = defaultResult;
}}"""
        ),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        transform_with_context_name = typescript_naming.method_name(
            Identifier(f"transform_{cls.name}_with_context")
        )

        cls_name = typescript_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
/**
 * Transform `that` in `context`.
 *
 * @param that - instance to be transformed
 * @param context - of the visitation
 * @returns transformed `that`
 */
/* eslint-disable @typescript-eslint/no-unused-vars */
{transform_with_context_name}(
{I}that: {cls_name},
{I}context: ContextT
): T {{
{I}return this.defaultResult;
}}
/* eslint-enable @typescript-eslint/no-unused-vars */"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Transform the instances of the model in context.
 *
 * @remarks
 * If you do not override the transformation methods, they simply
 * return {{@link defaultResult}}.
 *
 * @typeParam ContextT - type of the visitation context
 * @typeParam T - type of the transformation result
 */
export class TransformerWithDefaultAndContext<ContextT, T>
{II}extends AbstractTransformerWithContext<ContextT, T> {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_comment_for_meta_model(
    description: intermediate.DescriptionOfMetaModel,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the docstring for the given meta-model."""
    # fmt: off
    comment, errors = (
        typescript_description
        .generate_documentation_comment_for_summary_remarks_constraints(
            description=description,
            context=typescript_description.Context(
                module=typescript_common.TYPES_MODULE, cls_or_enum=None
            )
        )
    )
    # fmt: on

    if errors is not None:
        return None, errors

    assert comment is not None

    return comment, None


def _generate_as_interface_transformer(
    interface: intermediate.Interface, symbol_table: intermediate.SymbolTable
) -> Stripped:
    blocks = []  # type: List[Stripped]

    interface_name = typescript_naming.interface_name(interface.name)

    for cls in symbol_table.concrete_classes:
        transform_name = typescript_naming.method_name(
            Identifier(f"transform_{cls.name}")
        )

        cls_name = typescript_naming.class_name(cls.name)

        if cls.is_subclass_of(interface.base):
            blocks.append(
                Stripped(
                    f"""\
{transform_name}(
{I}that: {cls_name}
): {interface_name} | null {{
{I}return that as {interface_name};
}}"""
                )
            )
        else:
            blocks.append(
                Stripped(
                    f"""\
/* eslint-disable @typescript-eslint/no-unused-vars */
{transform_name}(
{I}that: {cls_name}
): {interface_name} | null {{
{I}return null;
}}
/* eslint-enable @typescript-eslint/no-unused-vars */"""
                )
            )

    transformer_name = typescript_naming.class_name(
        Identifier(f"As_{interface.name}_transformer")
    )

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Try to cast an instance of the model to {{@link {interface_name}}}.
 */
class {transformer_name}
{II}extends AbstractTransformer<{interface_name} | null> {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_type_matcher(symbol_table: intermediate.SymbolTable) -> Stripped:
    blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        transform_name = typescript_naming.method_name(
            Identifier(f"transform_{cls.name}_with_context")
        )

        cls_name = typescript_naming.class_name(cls.name)

        is_name = typescript_naming.function_name(Identifier(f"is_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
/* eslint-disable @typescript-eslint/no-unused-vars */
{transform_name}(
{I}that: {cls_name},
{I}other: Class
): boolean {{
{I}return {is_name}(other);
}}
/* eslint-enable @typescript-eslint/no-unused-vars */"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class TypeMatcher extends AbstractTransformerWithContext<
{I}Readonly<Class>,
{I}boolean
> {{"""
    )

    for i, block in enumerate(blocks):
        if i == 0:
            writer.write("\n")
        else:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: VerifiedIntermediateSymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code of the data structures representing the meta-model."""
    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    if symbol_table.meta_model.description is not None:
        # fmt: off
        comment, comment_errors = (
            _generate_comment_for_meta_model(
                description=symbol_table.meta_model.description
            )
        )
        # fmt: on

        if comment_errors is not None:
            errors.extend(comment_errors)
        else:
            assert comment is not None
            blocks.append(comment)

    model_type_getter = typescript_naming.method_name(Identifier("model_type"))

    blocks.extend(
        [
            typescript_common.WARNING,
            _generate_model_type_enum(symbol_table=symbol_table),
            _generate_over_model_type_enum(symbol_table=symbol_table),
            Stripped(
                f"""\
/**
 * Represent the most general class of an AAS model.
 */
export abstract class Class {{
{I}/**
{I} * Indicate the runtime model type of an instance.
{I} */
{I}abstract {model_type_getter}(): ModelType;

{I}/**
{I} * Iterate over all the instances referenced from this one.
{I} */
{I}abstract descendOnce(): IterableIterator<Class>;

{I}/**
{I} * Iterate recursively over all the instances referenced from this one.
{I} */
{I}abstract descend(): IterableIterator<Class>;

{I}/**
{I} * Dispatch the `visitor` on this instance.
{I} *
{I} * @param visitor - to be dispatched
{I} */
{I}abstract accept(visitor: AbstractVisitor): void;

{I}/**
{I} * Dispatch the `visitor` on this instance with `context`.
{I} *
{I} * @param visitor - to be dispatched
{I} * @param context - of the visitation
{I} * @typeParam ContextT - type of the visitation context
{I} */
{I}abstract acceptWithContext<ContextT>(
{II}visitor: AbstractVisitorWithContext<ContextT>,
{II}context: ContextT
{I}): void;

{I}/**
{I} * Dispatch the `transformer` on this instance.
{I} *
{I} * @param transformer - to be dispatched
{I} * @return this instance transformed
{I} * @typeParam T - type of the transformation result
{I} */
{I}abstract transform<T>(transformer: AbstractTransformer<T>): T;

{I}/**
{I} * Dispatch the `transformer` on this instance in `context`.
{I} *
{I} * @param transformer - to be dispatched
{I} * @param context - of the transformation
{I} * @return this instance transformed
{I} * @typeParam T - type of the transformation result
{I} */
{I}abstract transformWithContext<ContextT, T>(
{II}transformer: AbstractTransformerWithContext<ContextT, T>,
{II}context: ContextT
{I}): T;
}}"""
            ),
        ]
    )

    concrete_class_to_index = {
        concrete_cls: i for i, concrete_cls in enumerate(symbol_table.concrete_classes)
    }

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            block, error = _generate_enum(enum=our_type)
            if error is not None:
                errors.append(error)
                continue
            else:
                assert block is not None
                blocks.append(block)
                blocks.append(_generate_over_enum(enum=our_type))

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin, 2022-11-10):
            # We do not generate the constrained primitives as types. We only
            # consider them in the verification.
            continue

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Types/{our_type.name}.ts"
                )

                block = spec_impls.get(implementation_key, None)
                if block is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The implementation is missing "
                            f"for the implementation-specific "
                            f"class: {implementation_key}",
                        )
                    )
                else:
                    blocks.append(block)
            else:
                if our_type.interface is not None:
                    block, error = _generate_interface(interface=our_type.interface)
                    if error is not None:
                        errors.append(error)
                    else:
                        assert block is not None
                        blocks.append(block)

                if isinstance(our_type, intermediate.ConcreteClass):
                    block, error = _generate_class(
                        cls=our_type,
                        spec_impls=spec_impls,
                        concrete_cls_index=concrete_class_to_index[our_type],
                    )
                    if error is not None:
                        errors.append(error)
                    else:
                        assert block is not None
                        blocks.append(block)
        else:
            # noinspection PyTypeChecker
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    blocks.extend(
        [
            _generate_abstract_visitor(symbol_table=symbol_table),
            _generate_abstract_visitor_with_context(symbol_table=symbol_table),
            _generate_pass_through_visitor(symbol_table=symbol_table),
            _generate_pass_through_visitor_with_context(symbol_table=symbol_table),
            _generate_abstract_transformer(symbol_table=symbol_table),
            _generate_abstract_transformer_with_context(symbol_table=symbol_table),
            _generate_transformer_with_default(symbol_table=symbol_table),
            _generate_transformer_with_default_and_context(symbol_table=symbol_table),
        ]
    )

    for cls in symbol_table.classes:
        if cls.interface is not None:
            transformer_name = typescript_naming.class_name(
                Identifier(f"As_{cls.interface.name}_transformer")
            )
            constant_transformer = typescript_naming.constant_name(
                Identifier(f"As_{cls.interface.name}_transformer")
            )

            as_interface = typescript_naming.function_name(
                Identifier(f"as_{cls.interface.name}")
            )

            is_interface = typescript_naming.function_name(
                Identifier(f"is_{cls.interface.name}")
            )

            interface_name = typescript_naming.interface_name(cls.interface.name)

            blocks.extend(
                [
                    _generate_as_interface_transformer(
                        interface=cls.interface, symbol_table=symbol_table
                    ),
                    Stripped(
                        f"""\
const {constant_transformer} =
{I}new {transformer_name}();"""
                    ),
                    Stripped(
                        f"""\
/**
 * Try to cast `that` instance to
 * the interface {{@link {interface_name}}}.
 *
 * @param that - instance to be casted
 * @returns - casted `that` if cast successful, or `null`
 */
export function {as_interface}(
{I}that: Class
): {interface_name} | null {{
{I}return {constant_transformer}.transform(that);
}}"""
                    ),
                    Stripped(
                        f"""\
/**
 * Check the type of `that` instance.
 *
 * @param that - instance to be type-checked
 * @returns `true` if the type check is successful
 */
export function {is_interface}(
{I}that: Class
): that is {interface_name} {{
{I}return {as_interface}(that) !== null;
}}"""
                    ),
                ]
            )

        # NOTE (mristin, 2022-11-23):
        # We add these functions to make a uniform interface to ``isX`` checks.
        # Without these functions, the clients would have to refactor a lot once
        # the meta-model changes and a class gets descendants where it had none before.
        if (
            isinstance(cls, intermediate.ConcreteClass)
            and len(cls.concrete_descendants) == 0
        ):
            cls_name = typescript_naming.class_name(cls.name)

            as_cls = typescript_naming.function_name(Identifier(f"as_{cls.name}"))

            is_cls = typescript_naming.function_name(Identifier(f"is_{cls.name}"))

            blocks.extend(
                [
                    Stripped(
                        f"""\
/**
 * Try to cast `that` instance to
 * the class {{@link {cls_name}}}.
 *
 * @param that - instance to be casted
 * @returns - casted `that` if cast successful, or `null`
 */
export function {as_cls}(
{I}that: Class
): {cls_name} | null {{
{I}return (that instanceof {cls_name})
{II}? <{cls_name}>that
{II}: null;
}}"""
                    ),
                    Stripped(
                        f"""\
/**
 * Check the type of `that` instance.
 *
 * @param that - instance to be type-checked
 * @returns `true` if the type check is successful
 */
export function {is_cls}(
{I}that: Class
): that is {cls_name} {{
{I}return that instanceof {cls_name};
}}"""
                    ),
                ]
            )

    blocks.append(_generate_type_matcher(symbol_table=symbol_table))
    blocks.append(
        Stripped(
            """\
const TYPE_MATCHER = new TypeMatcher();"""
        )
    )

    blocks.append(
        Stripped(
            f"""\
/**
 * Check whether the type of `that` matches the type of `other` instance.
 *
 * @remarks
 * We check with `is*` function. Hence, if the class of `other` is a subclass of
 * the class of `that`, we confirm the match.
 *
 * @param that - standard instance
 * @param other - instance whose type is compared against `that`
 */
export function typesMatch<ClassT extends Class>(
{I}that: ClassT,
{I}other: Class
): other is ClassT {{
{I}return TYPE_MATCHER.transformWithContext(that, other);
}}"""
        )
    )

    blocks.append(typescript_common.WARNING)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue(), None


# endregion

assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
