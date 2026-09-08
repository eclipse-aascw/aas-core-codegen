"""Generate code of the data structures representing the meta-model."""

import io
import itertools
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
from aas_core_codegen.python import (
    common as python_common,
    naming as python_naming,
    description as python_description,
    unrolling as python_unrolling,
)
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
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
    result: str

    if isinstance(something, intermediate.Enumeration):
        result = f"meta-model enumeration {something.name!r}"
    elif isinstance(something, intermediate.AbstractClass):
        result = f"meta-model abstract class {something.name!r}"
    elif isinstance(something, intermediate.ConcreteClass):
        result = f"meta-model concrete class {something.name!r}"
    else:
        assert_never(something)

    return result


def _verify_intra_structure_collisions(
    our_type: intermediate.OurType,
) -> Optional[Error]:
    """Verify that no member names collide in the Python structure of our type."""
    errors = []  # type: List[Error]

    if isinstance(our_type, intermediate.Enumeration):
        enum_literal_map = (
            dict()
        )  # type: Dict[Identifier, intermediate.EnumerationLiteral]

        for literal in our_type.literals:
            literal_name = python_naming.enum_literal_name(literal.name)
            colliding_literal = enum_literal_map.get(literal_name, None)
            if colliding_literal is not None:
                errors.append(
                    Error(
                        literal.parsed.node,
                        f"The Python name, {literal_name!r}, "
                        f"for the literal {literal.name!r} collides with "
                        f"the Python name of another "
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
            prop_name = python_naming.property_name(prop.name)
            if prop_name in observed_member_names:
                errors.append(
                    Error(
                        prop.parsed.node,
                        f"Python property {prop_name!r} corresponding "
                        f"to the meta-model property {prop.name!r} collides with "
                        f"the {observed_member_names[prop_name]}",
                    )
                )
            else:
                observed_member_names[prop_name] = (
                    f"Python property {prop_name!r} corresponding to "
                    f"the meta-model property {prop.name!r}"
                )

        observed_constructor_arg_names = {}  # type: Dict[Identifier, str]
        for constructor_arg in our_type.constructor.arguments:
            arg_name = python_naming.argument_name(constructor_arg.name)

            if arg_name in observed_constructor_arg_names:
                errors.append(
                    Error(
                        constructor_arg.parsed.node,
                        f"Python argument {arg_name!r} corresponding "
                        f"to the meta-model constructor argument {constructor_arg.name!r} "
                        f"collides with the {observed_constructor_arg_names[arg_name]}",
                    )
                )
            else:
                observed_constructor_arg_names[arg_name] = (
                    f"Python argument {arg_name!r} corresponding to "
                    f"the meta-model constructor argument {constructor_arg.name!r}"
                )

        for method in our_type.methods:
            method_name = python_naming.method_name(method.name)

            if method_name in observed_member_names:
                errors.append(
                    Error(
                        method.parsed.node,
                        f"Python method {method_name!r} corresponding "
                        f"to the meta-model method {method.name!r} collides with "
                        f"the {observed_member_names[method_name]}",
                    )
                )
            else:
                observed_member_names[method_name] = (
                    f"Python method {method_name!r} corresponding to "
                    f"the meta-model method {method.name!r}"
                )

            observed_method_arg_names = {}  # type: Dict[Identifier, str]
            for arg in method.arguments:
                arg_name = python_naming.argument_name(arg.name)

                if arg_name in observed_method_arg_names:
                    errors.append(
                        Error(
                            arg.parsed.node,
                            f"Python argument {arg_name!r} corresponding "
                            f"to the meta-model method argument {arg.name!r} "
                            f"of the method {method.name} "
                            f"collides with the {observed_method_arg_names[arg_name]}",
                        )
                    )
                else:
                    observed_method_arg_names[arg_name] = (
                        f"Python argument {arg_name!r} corresponding to "
                        f"the meta-model method argument {arg.name!r}"
                    )

    else:
        assert_never(our_type)

    if len(errors) > 0:
        return Error(
            our_type.parsed.node,
            f"Naming collision(s) in Python code for our type {our_type.name!r}",
            underlying=errors,
        )

    return None


def _verify_structure_name_collisions(
    symbol_table: intermediate.SymbolTable,
) -> List[Error]:
    """Verify that the Python names of the structures do not collide."""
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

    for enum_or_cls in itertools.chain(symbol_table.enumerations, symbol_table.classes):
        name = python_naming.name_of(enum_or_cls)

        other = observed_structure_names.get(name, None)

        if other is not None:
            errors.append(
                Error(
                    enum_or_cls.parsed.node,
                    f"The Python name {name!r} "
                    f"of the {_human_readable_identifier(enum_or_cls)} "
                    f"collides with the Python name "
                    f"of the {_human_readable_identifier(other)}",
                )
            )
        else:
            observed_structure_names[name] = enum_or_cls

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
    """Verify that Python code can be generated from the ``symbol_table``."""
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


@require(lambda enumeration, literal: id(literal) in enumeration.literal_id_set)
@require(lambda literal: literal.description is not None)
def _generate_comment_for_enumeration_literal(
    enumeration: intermediate.Enumeration,
    literal: intermediate.EnumerationLiteral,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given enumeration literal."""
    # NOTE (mristin, 2022-10-29):
    # We need to state the pre-condition for the second time for mypy.
    assert literal.description is not None

    text, errors = python_description.generate_summary_remarks(
        description=literal.description,
        context=python_description.Context(
            qualified_module_name=qualified_module_name,
            module=Identifier("types"),
            cls_or_enum=enumeration,
        ),
    )

    if errors is not None:
        return None, errors

    assert text is not None

    return python_description.documentation_comment(text), None


@require(lambda cls_or_enum: cls_or_enum.description is not None)
def _generate_docstring_for_cls_or_enum(
    cls_or_enum: Union[intermediate.Enumeration, intermediate.ClassUnion],
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the docstring for our type."""
    # NOTE (mristin, 2022-10-29):
    # We need to state the pre-condition for the second time for mypy.
    assert cls_or_enum.description is not None

    text, errors = python_description.generate_summary_remarks_constraints(
        description=cls_or_enum.description,
        context=python_description.Context(
            qualified_module_name=qualified_module_name,
            module=Identifier("types"),
            cls_or_enum=cls_or_enum,
        ),
    )

    if errors is not None:
        return None, errors

    assert text is not None

    return python_description.docstring(text), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_enum(
    enum: intermediate.Enumeration,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate code for the enum."""
    writer = io.StringIO()

    errors = []  # type: List[Error]

    docstring = None  # type: Optional[Stripped]
    if enum.description is not None:
        # fmt: off
        docstring, docstring_errors = (
            _generate_docstring_for_cls_or_enum(
                cls_or_enum=enum,
                qualified_module_name=qualified_module_name
            )
        )
        # fmt: on

        if docstring_errors:
            errors.append(
                Error(
                    enum.description.parsed.node,
                    f"Failed to generate the docstring "
                    f"for the enumeration {enum.name!r}",
                    docstring_errors,
                )
            )
        else:
            assert docstring is not None

    name = python_naming.enum_name(enum.name)

    writer.write(f"class {name}(enum.Enum):\n")
    if len(enum.literals) == 0:
        if docstring is not None:
            writer.write(textwrap.indent(docstring, I))
        else:
            writer.write(
                f"""\
{I}# pylint: disable=missing-class-docstring
{I}pass
"""
            )
    else:
        if docstring is not None:
            writer.write(textwrap.indent(docstring, I))
        else:
            writer.write(f"{I}# pylint: disable=missing-class-docstring")

        for literal in enum.literals:
            writer.write("\n\n")

            if literal.description is not None:
                comment, comment_errors = _generate_comment_for_enumeration_literal(
                    enumeration=enum,
                    literal=literal,
                    qualified_module_name=qualified_module_name,
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

            literal_name = python_naming.enum_literal_name(literal.name)
            writer.write(textwrap.indent(f"{literal_name} = {repr(literal.value)}", I))

    if len(errors) > 0:
        return None, Error(
            enum.parsed.node,
            f"Failed to generate the Python code for the enumeration {enum.name!r}",
            errors,
        )

    return Stripped(writer.getvalue()), None


class _DescendBodyUnroller(python_unrolling.AbstractUnroller):
    """Generate code that unrolls descent into an element."""

    #: If set, generates the code with unrolled yields.
    #: Otherwise, we do not unroll recursively.
    _recurse: Final[bool]

    #: Pre-computed descendability map. A type is descendable if we should unroll it
    #: further.
    _descendability: Final[Mapping[intermediate.TypeAnnotationUnion, bool]]

    #: Generator of loop variable names.
    #:
    #: We generate for each list iteration a new variable since Python tracks
    #: variables in the function scope, not block scope.
    _generator_for_loop_variables: Final[python_common.GeneratorForLoopVariables]

    def __init__(
        self,
        recurse: bool,
        descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
        generator_for_loop_variables: python_common.GeneratorForLoopVariables,
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
    ) -> List[python_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        # We can not descend into a primitive type.
        return []

    def _unroll_our_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OurTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[python_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            # We can not descend into an enumeration.
            return []

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # We can not descend into a primitive type.
            return []

        assert isinstance(our_type, intermediate.Class)  # Exhaustively match

        result = [python_unrolling.Node(f"yield {unrollee_expr}", children=[])]

        if self._recurse:
            if self._descendability[type_annotation]:
                result.append(
                    python_unrolling.Node(
                        text=f"yield from {unrollee_expr}.descend()",
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
    ) -> List[python_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        if (
            not self._recurse
            and isinstance(type_annotation.items, intermediate.OurTypeAnnotation)
            and isinstance(
                type_annotation.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            )
        ):
            return [python_unrolling.Node(f"yield from {unrollee_expr}", children=[])]

        loop_var = next(self._generator_for_loop_variables)
        children = self.unroll(
            unrollee_expr=loop_var,
            type_annotation=type_annotation.items,
            path=[],  # Path is unused in this context
            list_loop_level=list_loop_level + 1,
        )

        if len(children) == 0:
            return []

        node = python_unrolling.Node(
            text=f"for {loop_var} in {unrollee_expr}:",
            children=children,
        )

        return [node]

    def _unroll_tuple_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.TupleTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[python_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        # NOTE (mristin):
        # Unlike lists, tuples are heterogeneous and fixed-length, so we unroll
        # every item at its own fixed index instead of looping.
        result = []  # type: List[python_unrolling.Node]
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

    def _unroll_optional_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OptionalTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[python_unrolling.Node]:
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
            python_unrolling.Node(
                text=f"if {unrollee_expr} is not None:", children=children
            )
        ]


def _generate_descend_body(cls: intermediate.ConcreteClass, recurse: bool) -> Stripped:
    """
    Generate the body of the ``descend`` and ``descend_once`` methods.

    With this function, we unroll the recursion as a simple optimization
    in the recursive case.
    """
    blocks = []  # type: List[Stripped]

    generator_for_loop_variables = python_common.GeneratorForLoopVariables()

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
            unrollee_expr=f"self.{python_naming.property_name(prop.name)}",
            type_annotation=prop.type_annotation,
            path=[],  # We do not use path in this context
            list_loop_level=0,
        )

        assert len(roots) > 0, (
            "Since the type annotation was descendable, we must have obtained "
            "at least one unrolling node"
        )

        blocks.extend(Stripped(python_unrolling.render(root)) for root in roots)

        # endregion

    if len(blocks) == 0:
        blocks.append(
            Stripped(
                """\
# No descendable properties
return
# For this uncommon return-yield construction, see:
# https://stackoverflow.com/questions/13243766/how-to-define-an-empty-generator-function
# noinspection PyUnreachableCode
yield"""
            )
        )

    return Stripped("\n\n".join(blocks))


def _generate_descend_once_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the ``descend_once`` method for the concrete class ``cls``."""

    body = _generate_descend_body(cls=cls, recurse=False)

    return Stripped(
        f"""\
def descend_once(self) -> Iterator[Class]:
{I}\"\"\"
{I}Iterate over the instances referenced from this instance.

{I}We do not recurse into the referenced instance.

{I}:yield: instances directly referenced from this instance
{I}\"\"\"
{I}{indent_but_first_line(body, I)}"""
    )


def _generate_descend_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the recursive ``descend`` method for the concrete class ``cls``."""

    body = _generate_descend_body(cls=cls, recurse=True)

    return Stripped(
        f"""\
def descend(self) -> Iterator[Class]:
{I}\"\"\"
{I}Iterate recursively over the instances referenced from this one.

{I}:yield: instances recursively referenced from this instance
{I}\"\"\"
{I}{indent_but_first_line(body, I)}"""
    )


def _generate_default_value(default: intermediate.Default) -> Stripped:
    """Generate code representing the default value of an argument."""
    code: str

    if isinstance(default, intermediate.DefaultPrimitive):
        if default.value is None:
            code = "None"
        elif isinstance(default.value, bool):
            code = "True" if default.value else "False"
        elif isinstance(default.value, str):
            code = python_common.string_literal(default.value)
        elif isinstance(default.value, int):
            code = str(default.value)
        elif isinstance(default.value, float):
            code = f"{default}"
        else:
            assert_never(default.value)
    elif isinstance(default, intermediate.DefaultEnumerationLiteral):
        code = ".".join(
            [
                python_naming.enum_name(default.enumeration.name),
                python_naming.enum_literal_name(default.literal.name),
            ]
        )
    else:
        assert_never(default)

    return Stripped(code)


@require(lambda cls: not cls.is_implementation_specific)
@require(lambda cls: not cls.constructor.is_implementation_specific)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_constructor(
    cls: intermediate.ClassUnion,
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the constructor function for the given class ``cls``.

    Return empty string if there is an empty constructor.
    """
    if len(cls.constructor.arguments) == 0 and len(cls.constructor.statements) == 0:
        return Stripped(""), None

    # region Construct the body

    body = []  # type: List[Stripped]
    for stmt in cls.constructor.statements:
        if isinstance(stmt, intermediate_construction.CallSuperConstructor):
            super_class = symbol_table.must_find_class(stmt.super_name)

            writer = io.StringIO()

            if len(super_class.constructor.arguments) == 0:
                writer.write(
                    f"""\
{python_naming.class_name(super_class.name)}.__init__(
{I}self
)"""
                )
            else:
                writer.write(
                    f"""\
{python_naming.class_name(super_class.name)}.__init__(
{I}self,
"""
                )
                for i, arg in enumerate(super_class.constructor.arguments):
                    writer.write(f"{I}{python_naming.argument_name(arg.name)}")
                    if i < len(super_class.constructor.arguments) - 1:
                        writer.write(",\n")
                    else:
                        writer.write("\n")
                writer.write(")")

            body.append(Stripped(writer.getvalue()))

        elif isinstance(stmt, intermediate_construction.AssignArgument):
            if stmt.default is None:
                body.append(
                    Stripped(
                        f"self.{python_naming.property_name(stmt.name)} = "
                        f"{python_naming.argument_name(stmt.argument)}"
                    )
                )
            else:
                if isinstance(stmt.default, intermediate_construction.EmptyList):
                    arg_name = python_naming.argument_name(stmt.argument)

                    # Write the assignment as a ternary operator
                    writer = io.StringIO()
                    writer.write(
                        f"""\
self.{python_naming.property_name(stmt.name)} = (
{I}{arg_name}
{I}if {arg_name} is not None
{I}else []
)"""
                    )

                    body.append(Stripped(writer.getvalue()))
                elif isinstance(
                    stmt.default, intermediate_construction.DefaultEnumLiteral
                ):
                    literal_code = ".".join(
                        [
                            python_naming.enum_name(stmt.default.enum.name),
                            python_naming.enum_literal_name(stmt.default.literal.name),
                        ]
                    )

                    arg_name = python_naming.argument_name(stmt.argument)

                    body.append(
                        Stripped(
                            f"""\
self.{python_naming.property_name(stmt.name)} = (
{I}{arg_name}
{I}if {arg_name} is not None
{I}else {literal_code}
)"""
                        )
                    )
                else:
                    assert_never(stmt.default)

        else:
            assert_never(stmt)

    # endregion

    # region Assemble the constructor with the definition and the body

    arg_codes = []  # type: List[str]
    for arg in cls.constructor.arguments:
        arg_type = python_common.generate_type(type_annotation=arg.type_annotation)
        arg_name = python_naming.argument_name(arg.name)

        if arg.default is None:
            arg_codes.append(Stripped(f"{arg_name}: {arg_type}"))
        else:
            arg_codes.append(
                Stripped(
                    f"{arg_name}: {arg_type} = {_generate_default_value(arg.default)}"
                )
            )

    writer = io.StringIO()

    if len(arg_codes) == 0:
        writer.write("def __init__(self) -> None:\n")
    if len(arg_codes) == 1:
        writer.write(f"def __init__(self, {arg_codes[0]}) -> None:\n")
    else:
        arg_block = ",\n".join(["self"] + arg_codes)
        arg_block_indented = textwrap.indent(arg_block, II)
        writer.write(f"def __init__(\n{arg_block_indented}\n) -> None:\n")

    writer.write(f'{I}"""Initialize with the given values."""')

    if len(body) > 0:
        for body_stmt in body:
            writer.write(f"\n{I}{indent_but_first_line(body_stmt, I)}")

    # endregion

    return Stripped(writer.getvalue()), None


@require(lambda cls, prop: id(prop) in cls.property_id_set)
@require(lambda prop: prop.description is not None)
def _generate_comment_for_property(
    cls: intermediate.ClassUnion,
    prop: intermediate.Property,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given property."""
    # NOTE (mristin, 2022-10-29):
    # We need to write a double assertion for mypy.
    assert prop.description is not None

    text, errors = python_description.generate_summary_remarks_constraints(
        description=prop.description,
        context=python_description.Context(
            qualified_module_name=qualified_module_name,
            module=Identifier("types"),
            cls_or_enum=cls,
        ),
    )

    if errors is not None:
        return None, errors

    assert text is not None

    return python_description.documentation_comment(text), None


@require(lambda cls: not cls.is_implementation_specific)
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_class(
    cls: intermediate.ClassUnion,
    spec_impls: specific_implementations.SpecificImplementations,
    qualified_module_name: python_common.QualifiedModuleName,
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate Python code for the given concrete class ``cls``."""
    # region Collect blocks of the class body

    # Code blocks of the class body separated by double newlines and indented once
    blocks = []  # type: List[Stripped]

    # region Property definitions

    for prop in cls.properties:
        if prop.specified_for is not cls:
            continue

        prop_comment = None  # type: Optional[Stripped]
        if prop.description is not None:
            prop_comment, prop_comment_errors = _generate_comment_for_property(
                cls=cls, prop=prop, qualified_module_name=qualified_module_name
            )
            if prop_comment_errors is not None:
                return None, Error(
                    prop.description.parsed.node,
                    "Failed to generate the property comment",
                    prop_comment_errors,
                )

        prop_type = python_common.generate_type(type_annotation=prop.type_annotation)
        prop_name = python_naming.property_name(prop.name)

        writer = io.StringIO()
        if prop_comment is not None:
            writer.write(prop_comment)
            writer.write("\n")
        writer.write(f"{prop_name}: {prop_type}")
        blocks.append(Stripped(writer.getvalue()))

    # endregion

    # region over_X_or_empty getter

    for prop in cls.properties:
        if prop.specified_for is not cls:
            continue

        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            prop_name = python_naming.property_name(prop.name)
            items_type = python_common.generate_type(prop.type_annotation.value.items)

            blocks.append(
                Stripped(
                    f"""\
def over_{prop_name}_or_empty(
{II}self
) -> Iterator[{items_type}]:
{I}\"\"\"Yield from :py:attr:`.{prop_name}` if set.\"\"\"
{I}if self.{prop_name} is not None:
{II}yield from self.{prop_name}"""
                )
            )

    # endregion

    # region Methods

    errors = []  # type: List[Error]

    for method in cls.methods:
        if method.specified_for is not cls:
            continue

        if isinstance(method, intermediate.ImplementationSpecificMethod):
            implementation_key = specific_implementations.ImplementationKey(
                f"Types/{method.specified_for.name}/{method.name}.py"
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
            # NOTE (mristin, 2022-09-28):
            # At the moment, we do not transpile the method body and its contracts.
            # We want to finish the meta-model for the V3, fix de/serialization and
            # generate SDKs for a couple of languages before taking on this rather hard
            # task.

            errors.append(
                Error(
                    cls.parsed.node,
                    "At the moment, we do not transpile the method body and "
                    "its contracts. We want to finish the meta-model for the V3, "
                    "fix de/serialization and generate SDKs for a couple of languages "
                    "before taking on this rather hard task.",
                )
            )

    if isinstance(cls, intermediate.ConcreteClass):
        blocks.append(_generate_descend_once_method(cls=cls))

        blocks.append(_generate_descend_method(cls=cls))

        visit_name = python_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
def accept(self, visitor: "AbstractVisitor") -> None:
{I}\"\"\"Dispatch the :paramref:`visitor` on this instance.\"\"\"
{I}visitor.{visit_name}(self)"""
            )
        )

        visit_with_context_name = python_naming.method_name(
            Identifier(f"visit_{cls.name}_with_context")
        )

        blocks.append(
            Stripped(
                f"""\
def accept_with_context(
{II}self,
{II}visitor: "AbstractVisitorWithContext[ContextT]",
{II}context: ContextT
) -> None:
{I}\"\"\"Dispatch the :paramref:`visitor` on this instance in :paramref:`context`.\"\"\"
{I}visitor.{visit_with_context_name}(self, context)"""
            )
        )

        transform_name = python_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
def transform(
{II}self,
{II}transformer: "AbstractTransformer[T]"
) -> T:
{I}\"\"\"Dispatch the :paramref:`transformer` on this instance.\"\"\"
{I}return transformer.{transform_name}(self)"""
            )
        )

        transform_with_context_name = python_naming.method_name(
            Identifier(f"transform_{cls.name}_with_context")
        )

        blocks.append(
            Stripped(
                f"""\
def transform_with_context(
{II}self,
{II}transformer: "AbstractTransformerWithContext[ContextT, T]",
{II}context: ContextT
) -> T:
{I}\"\"\"
{I}Dispatch the :paramref:`transformer` on this instance in :paramref:`context`.
{I}\"\"\"
{I}return transformer.{transform_with_context_name}(
{II}self, context)"""
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
        constructor_block, error = _generate_constructor(
            cls=cls, symbol_table=symbol_table
        )

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

    docstring = None  # type: Optional[Stripped]
    if cls.description is not None:
        docstring, docstring_errors = _generate_docstring_for_cls_or_enum(
            cls_or_enum=cls, qualified_module_name=qualified_module_name
        )
        if docstring_errors is not None:
            return None, Error(
                cls.description.parsed.node,
                "Failed to generate the docstring",
                docstring_errors,
            )

        assert docstring is not None

    # endregion

    # region Assemble the class definition with its body

    name = python_naming.class_name(cls.name)

    # NOTE (mristin, 2022-09-17):
    # Every class in the meta-model inherits from the most general abstract class
    # ``Class`.

    super_names = []  # type: List[str]

    if len(cls.inheritances) == 0:
        # NOTE (mristin, 2022-09-17):
        # We only have to include the most general ancestor ``Class`` if there are no
        # ancestors. Otherwise, one of the ancestors will have already inherited from
        # it.
        super_names.append("Class")
    else:
        super_names = [
            python_naming.class_name(inheritance.name)
            for inheritance in cls.inheritances
        ]

    assert len(super_names) > 0, "Assumption for the code generation below"

    writer = io.StringIO()
    if sum(len(super_name) + 2 for super_name in super_names) + len(name) < 70:
        # NOTE (mristin, 2022-09-17):
        # Put the class definition on the single line as it fit by the heuristic.
        super_names_joined = ", ".join(super_names)
        writer.write(f"class {name}({super_names_joined}):\n")
    else:
        writer.write(f"class {name}(\n")
        for i, super_name in enumerate(super_names):
            if i < len(super_names) - 1:
                writer.write(f"{II}{super_name},\n")
            else:
                writer.write(f"{II}{super_name}")
        writer.write("):\n")

    if docstring is not None:
        writer.write(textwrap.indent(docstring, I))
    else:
        writer.write(f"{I}# pylint: disable=missing-class-docstring")

    if len(blocks) == 0:
        # NOTE (mristin, 2022-09-28):
        # We have to add a ``pass`` statement if there was no description. Otherwise,
        # the generated code would be invalid. In cases where description is defined,
        # a ``pass`` statement is redundant.
        if docstring is None:
            writer.write(f"\n{I}pass")
    else:
        for i, code in enumerate(blocks):
            writer.write("\n\n")
            writer.write(textwrap.indent(code, I))

    # endregion

    return Stripped(writer.getvalue()), None


def _generate_abstract_visitor(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate code for the abstract visitor."""
    blocks = [
        Stripped(
            f"""\
def visit(
{II}self,
{II}that: Class
) -> None:
{I}\"\"\"Double-dispatch on :paramref:`that`.\"\"\"
{I}that.accept(self)"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        visit_name = python_naming.method_name(Identifier(f"visit_{cls.name}"))
        cls_name = python_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
@abc.abstractmethod
def {visit_name}(
{II}self,
{II}that: {cls_name}
) -> None:
{I}\"\"\"Visit :paramref:`that`.\"\"\"
{I}raise NotImplementedError()"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class AbstractVisitor:
{I}\"\"\"Visit the instances of the model.\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


def _generate_abstract_visitor_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the abstract visitor with context."""
    blocks = [
        Stripped(
            f"""\
def visit_with_context(
{II}self,
{II}that: Class,
{II}context: ContextT
) -> None:
{I}\"\"\"Double-dispatch on :paramref:`that`.\"\"\"
{I}that.accept_with_context(self, context)"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        visit_with_context_name = python_naming.method_name(
            Identifier(f"visit_{cls.name}_with_context")
        )
        cls_name = python_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
@abc.abstractmethod
def {visit_with_context_name}(
{II}self,
{II}that: {cls_name},
{II}context: ContextT
) -> None:
{I}\"\"\"Visit :paramref:`that` in :paramref:`context`.\"\"\"
{I}raise NotImplementedError()"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class AbstractVisitorWithContext(Generic[ContextT]):
{I}\"\"\"Visit the instances of the model with context.\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


def _generate_pass_through_visitor(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate code for the pass-through visitor."""
    blocks = [
        Stripped(
            f"""\
def visit(
{II}self,
{II}that: Class
) -> None:
{I}\"\"\"Double-dispatch on :paramref:`that`.\"\"\"
{I}that.accept(self)"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        visit_name = python_naming.method_name(Identifier(f"visit_{cls.name}"))
        cls_name = python_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
def {visit_name}(
{II}self,
{II}that: {cls_name}
) -> None:
{I}\"\"\"Visit :paramref:`that`.\"\"\"
{I}for another in that.descend_once():
{II}self.visit(another)"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class PassThroughVisitor(AbstractVisitor):
{I}\"\"\"
{I}Visit the instances of the model without action.

{I}This visitor is not meant to be directly used. Instead, you usually
{I}inherit from it, and implement only the relevant visit methods.
{I}\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


def _generate_pass_through_visitor_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the pass-through visitor with context."""
    blocks = [
        Stripped(
            f"""\
def visit_with_context(
{II}self,
{II}that: Class,
{II}context: ContextT
) -> None:
{I}\"\"\"Double-dispatch on :paramref:`that`.\"\"\"
{I}that.accept_with_context(self, context)"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        visit_with_context_name = python_naming.method_name(
            Identifier(f"visit_{cls.name}_with_context")
        )
        cls_name = python_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
def {visit_with_context_name}(
{II}self,
{II}that: {cls_name},
{II}context: ContextT
) -> None:
{I}\"\"\"Visit :paramref:`that` in :paramref:`context`.\"\"\"
{I}for another in that.descend_once():
{II}self.visit_with_context(another, context)"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class PassThroughVisitorWithContext(
{II}AbstractVisitorWithContext[ContextT]
):
{I}\"\"\"
{I}Visit the instances of the model without action and in context.

{I}This visitor is not meant to be directly used. Instead, you usually
{I}inherit from it, and implement only the relevant visit methods.
{I}\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


def _generate_abstract_transformer(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate code for the abstract transformer."""
    blocks = [
        Stripped(
            f"""\
def transform(
{II}self,
{II}that: Class
) -> T:
{I}\"\"\"Double-dispatch on :paramref:`that`.\"\"\"
{I}return that.transform(self)"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        transform_name = python_naming.method_name(Identifier(f"transform_{cls.name}"))

        cls_name = python_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
@abc.abstractmethod
def {transform_name}(
{II}self,
{II}that: {cls_name}
) -> T:
{I}\"\"\"Transform :paramref:`that`.\"\"\"
{I}raise NotImplementedError()"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class AbstractTransformer(Generic[T]):
{I}\"\"\"Transform the instances of the model.\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


def _generate_abstract_transformer_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the abstract transformer with context."""
    blocks = [
        Stripped(
            f"""\
def transform_with_context(
{II}self,
{II}that: Class,
{II}context: ContextT
) -> T:
{I}\"\"\"Double-dispatch on :paramref:`that`.\"\"\"
{I}return that.transform_with_context(self, context)"""
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        transform_with_context_name = python_naming.method_name(
            Identifier(f"transform_{cls.name}_with_context")
        )

        cls_name = python_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
@abc.abstractmethod
def {transform_with_context_name}(
{II}self,
{II}that: {cls_name},
{II}context: ContextT
) -> T:
{I}\"\"\"Transform :paramref:`that` in :paramref:`context`.\"\"\"
{I}raise NotImplementedError()"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class AbstractTransformerWithContext(
{II}Generic[ContextT, T]
):
{I}\"\"\"Transform the instances of the model in context.\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


def _generate_transformer_with_default(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the transformer with default transformation."""
    blocks = [
        Stripped(
            """\
#: Default value which is returned if no override of the transformation
default: T"""
        ),
        Stripped(
            f"""\
def __init__(self, default: T) -> None:
{I}\"\"\"Initialize with the given :paramref:`default` value.\"\"\"
{I}self.default = default"""
        ),
        Stripped(
            f"""\
def transform(
{II}self,
{II}that: Class
) -> T:
{I}\"\"\"Double-dispatch on :paramref:`that`.\"\"\"
{I}return that.transform(self)"""
        ),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        transform_name = python_naming.method_name(Identifier(f"transform_{cls.name}"))

        cls_name = python_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
def {transform_name}(
{II}self,
{II}that: {cls_name}
) -> T:
{I}\"\"\"Transform :paramref:`that`.\"\"\"
{I}return self.default"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class TransformerWithDefault(AbstractTransformer[T]):
{I}\"\"\"
{I}Transform the instances of the model.

{I}If you do not override the transformation methods, they simply
{I}return :py:attr:`.default`.
{I}\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


def _generate_transformer_with_default_and_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate code for the transformer with default transformation and context."""
    blocks = [
        Stripped(
            """\
#: Default value which is returned if no override of the transformation
default: T"""
        ),
        Stripped(
            f"""\
def __init__(self, default: T) -> None:
{I}\"\"\"Initialize with the given :paramref:`default` value.\"\"\"
{I}self.default = default"""
        ),
        Stripped(
            f"""\
def transform_with_context(
{II}self,
{II}that: Class,
{II}context: ContextT
) -> T:
{I}\"\"\"Double-dispatch on :paramref:`that`.\"\"\"
{I}return that.transform_with_context(self, context)"""
        ),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        transform_with_context_name = python_naming.method_name(
            Identifier(f"transform_{cls.name}_with_context")
        )

        cls_name = python_naming.class_name(cls.name)

        blocks.append(
            Stripped(
                f"""\
def {transform_with_context_name}(
{II}self,
{II}that: {cls_name},
{II}context: ContextT
) -> T:
{I}\"\"\"Transform :paramref:`that` in :paramref:`context`.\"\"\"
{I}return self.default"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
class TransformerWithDefaultAndContext(
{II}AbstractTransformerWithContext[ContextT, T]
):
{I}\"\"\"
{I}Transform the instances of the model in context.

{I}If you do not override the transformation methods, they simply
{I}return :py:attr:`.default`.
{I}\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


def _generate_docstring_for_meta_model(
    description: intermediate.DescriptionOfMetaModel,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the docstring for the given meta-model."""
    text, errors = python_description.generate_summary_remarks_constraints(
        description=description,
        context=python_description.Context(
            qualified_module_name=qualified_module_name,
            module=Identifier("types"),
            cls_or_enum=None,
        ),
    )

    if errors is not None:
        return None, errors

    assert text is not None

    return python_description.docstring(text), None


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
    qualified_module_name: python_common.QualifiedModuleName,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code of the data structures representing the meta-model.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    if symbol_table.meta_model.description is not None:
        # fmt: off
        docstring, docstring_errors = (
            _generate_docstring_for_meta_model(
                description=symbol_table.meta_model.description,
                qualified_module_name=qualified_module_name
            )
        )
        # fmt: on

        if docstring_errors is not None:
            errors.extend(docstring_errors)
        else:
            assert docstring is not None
            blocks.append(docstring)

    blocks.extend(
        [
            python_common.WARNING,
            Stripped(
                f"""\
import abc
import enum
from typing import (
{I}Generic,
{I}Iterator,
{I}Optional,
{I}TypeVar,
{I}List,
{I}Tuple
)"""
            ),
            Stripped(
                """\
T = TypeVar("T")
ContextT = TypeVar("ContextT")"""
            ),
            Stripped(
                f"""\
class Class(abc.ABC):
{I}\"\"\"Represent the most general class of an AAS model.\"\"\"
{I}@abc.abstractmethod
{I}def descend_once(self) -> Iterator["Class"]:
{II}\"\"\"Iterate over all the instances referenced from this one.\"\"\"
{II}raise NotImplementedError()

{I}@abc.abstractmethod
{I}def descend(self) -> Iterator["Class"]:
{II}\"\"\"Iterate recursively over all the instances referenced from this one.\"\"\"
{II}raise NotImplementedError()

{I}@abc.abstractmethod
{I}def accept(
{III}self,
{III}visitor: "AbstractVisitor"
{I}) -> None:
{II}\"\"\"
{II}Dispatch the :paramref:`visitor` on this instance.

{II}:param visitor: to be dispatched
{II}\"\"\"
{II}raise NotImplementedError()

{I}@abc.abstractmethod
{I}def accept_with_context(
{III}self,
{III}visitor: "AbstractVisitorWithContext[ContextT]",
{III}context: ContextT
{I}) -> None:
{II}\"\"\"
{II}Dispatch the :paramref:`visitor` on this instance with :paramref:`context`.

{II}:param visitor: to be dispatched
{II}:param context: of the visitation
{II}\"\"\"
{II}raise NotImplementedError()

{I}@abc.abstractmethod
{I}def transform(
{III}self,
{III}transformer: "AbstractTransformer[T]"
{I}) -> T:
{II}\"\"\"
{II}Dispatch the :paramref:`transformer` on this instance.

{II}:param transformer: to be dispatched
{II}:return: transformed self
{II}\"\"\"
{II}raise NotImplementedError()

{I}@abc.abstractmethod
{I}def transform_with_context(
{III}self,
{III}transformer: "AbstractTransformerWithContext[ContextT, T]",
{III}context: ContextT
{I}) -> T:
{II}\"\"\"
{II}Dispatch the :paramref:`transformer` on this instance with :paramref:`context`.

{II}:param transformer: to be dispatched
{II}:return: transformed self
{II}\"\"\"
{II}raise NotImplementedError()"""
            ),
            Stripped(
                """\
# pylint: disable=redefined-builtin"""
            ),
        ]
    )

    for our_type in symbol_table.our_types:
        error: Optional[Error]

        if isinstance(our_type, intermediate.Enumeration):
            block, error = _generate_enum(
                enum=our_type, qualified_module_name=qualified_module_name
            )
            if error is None:
                assert block is not None
                blocks.append(block)
                continue

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin, 2022-09-28):
            # We do not generate the constrained primitives as types. We only
            # consider them in the verification.
            continue

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Types/{our_type.name}.py"
                )

                block = spec_impls.get(implementation_key, None)
                if block is None:
                    error = Error(
                        our_type.parsed.node,
                        f"The implementation is missing "
                        f"for the implementation-specific "
                        f"class: {implementation_key}",
                    )
                else:
                    blocks.append(block)
                    continue
            else:
                block, error = _generate_class(
                    cls=our_type,
                    spec_impls=spec_impls,
                    qualified_module_name=qualified_module_name,
                    symbol_table=symbol_table,
                )
                if error is None:
                    assert block is not None
                    blocks.append(block)
                    continue
        else:
            assert_never(our_type)

        assert error is not None
        errors.append(
            Error(
                our_type.parsed.node,
                f"Failed to generate the code for {our_type.name!r}",
                [error],
            )
        )

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

    blocks.append(python_common.WARNING)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue(), None


# endregion

assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
