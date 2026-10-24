"""Generate code of the data structures representing the meta-model."""

import io
import itertools
import textwrap
from typing import (
    Optional,
    Dict,
    List,
    Mapping,
    Set,
    Tuple,
    cast,
    Union,
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
    NOTE_ON_INVARIANTS_OF_MUTATING_METHODS,
)
from aas_core_codegen.intermediate import (
    construction as intermediate_construction,
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.parse import tree as parse_tree
from aas_core_codegen.python import (
    common as python_common,
    naming as python_naming,
    description as python_description,
    transpilation as python_transpilation,
)
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


# region Checks


def _human_readable_identifier(
    something: Union[
        intermediate.Enumeration,
        intermediate.AbstractClass,
        intermediate.ConcreteClass,
        intermediate.NamedUnion,
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
    elif isinstance(something, intermediate.NamedUnion):
        result = f"meta-model named union {something.name!r}"
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

    elif isinstance(our_type, intermediate.NamedUnion):
        # A named union has no members of its own to collide.
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
            intermediate.NamedUnion,
        ],
    ] = dict()

    errors = []  # type: List[Error]

    # region Inter-structure collisions

    for enum_or_cls_or_union in itertools.chain(
        symbol_table.enumerations, symbol_table.classes, symbol_table.named_unions
    ):
        name = python_naming.name_of(enum_or_cls_or_union)

        other = observed_structure_names.get(name, None)

        if other is not None:
            errors.append(
                Error(
                    enum_or_cls_or_union.parsed.node,
                    f"The Python name {name!r} "
                    f"of the {_human_readable_identifier(enum_or_cls_or_union)} "
                    f"collides with the Python name "
                    f"of the {_human_readable_identifier(other)}",
                )
            )
        else:
            observed_structure_names[name] = enum_or_cls_or_union

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


@require(
    lambda enumeration, literal: intermediate.runtime_id(literal)
    in enumeration.literal_id_set
)
@require(lambda literal: literal.description is not None)
def _generate_comment_for_enumeration_literal(
    enumeration: intermediate.Enumeration,
    literal: intermediate.EnumerationLiteral,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given enumeration literal."""
    # NOTE (mristin):
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
    # NOTE (mristin):
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


def _descend_into_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the module-level function descending into ``type_anno``.

    We follow the grammar of the monikers of the composed de/serializers, see
    :py:func:`aas_core_codegen.python.common.type_moniker`, so two different
    containers never share a function.
    """
    return Identifier(f"_descend_{python_common.type_moniker(type_anno)}")


@require(
    lambda type_anno, descendability: (
        type_anno in descendability and descendability[type_anno]
    )
)
def _generate_descend_into(
    expr: str,
    type_anno: intermediate.TypeAnnotationUnion,
    descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
) -> Stripped:
    """
    Generate the code yielding the instances held by the value at ``expr``.

    An instance is yielded in-line. A container is delegated to its module-level
    function, which descends only one level and calls the function of its items
    by name. This way the descent is composed of plain functions, to any depth.

    The generated code recurses only if the Python variable ``recurse`` is set.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        # NOTE (mristin):
        # A named union is a plain ``Union[...]`` alias in Python, so its values
        # are already instances of the member classes, and we descend into them
        # exactly as we do into the instances of a class.
        return Stripped(
            f"""\
yield {expr}

if recurse:
{I}yield from {expr}.descend()"""
        )

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        name = _descend_into_container_name(type_anno)

        call = f"{name}({expr}, recurse)"
        # Heuristic to break the lines, very rudimentary
        if len(call) > 70:
            call = f"""\
{name}(
{I}{expr},
{I}recurse
)"""

        return Stripped(f"yield from {call}")

    raise AssertionError(
        f"Unexpected type annotation holding instances: {type_anno}. "
        f"The optionals nested in the containers should have been refused in "
        f"parse._translate._verify_symbol_table."
    )


@require(
    lambda type_anno, descendability: (
        type_anno in descendability and descendability[type_anno]
    )
)
def _generate_descend_into_container(
    type_anno: intermediate.ContainerTypeAnnotation,
    descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
) -> Stripped:
    """
    Generate the module-level function descending into ``type_anno``.

    The ``descendability`` maps ``type_anno`` and its nested type annotations,
    see :py:func:`aas_core_codegen.intermediate.map_descendability`.
    """
    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        if isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            # NOTE (mristin):
            # We yield the instances directly in the non-recursive case, so that
            # we do not check the flag for every single item.
            body = Stripped(
                f"""\
if not recurse:
{I}yield from that
{I}return

for item in that:
{I}yield item

{I}yield from item.descend()"""
            )
        else:
            item_code = _generate_descend_into(
                expr="item", type_anno=type_anno.items, descendability=descendability
            )

            body = Stripped(
                f"""\
for item in that:
{I}{indent_but_first_line(item_code, I)}"""
            )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        raise AssertionError(
            f"A set holds only primitives and enumeration literals, never "
            f"a reference to one of our own classes, so it can not have been "
            f"determined descendable: {type_anno}"
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = Stripped(
            "\n\n".join(
                _generate_descend_into(
                    expr=f"that[{i}]",
                    type_anno=item_type_anno,
                    descendability=descendability,
                )
                for i, item_type_anno in enumerate(type_anno.items)
                if descendability[item_type_anno]
            )
        )

    else:
        assert_never(type_anno)

    name = _descend_into_container_name(type_anno)
    value_type = python_common.generate_type(type_anno)

    return Stripped(
        f"""\
def {name}(
{II}that: {indent_but_first_line(value_type, II)},
{II}recurse: bool
) -> Iterator[Class]:
{I}\"\"\"
{I}Iterate over the instances held by :paramref:`that`.

{I}If :paramref:`recurse` is set, descend recursively into the instances
{I}as well.
{I}\"\"\"
{I}{indent_but_first_line(body, I)}"""
    )


def _generate_descend_methods(cls: intermediate.ConcreteClass) -> List[Stripped]:
    """
    Generate the ``descend_once``, ``descend`` and ``_descend`` methods.

    The public methods are thin wrappers around ``_descend``, which recurses
    only if instructed so at run-time.
    """
    blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        descendability = intermediate.map_descendability(prop.type_annotation)

        if not descendability[prop.type_annotation]:
            continue

        prop_name = python_naming.property_name(prop.name)

        block = _generate_descend_into(
            expr=f"self.{prop_name}",
            type_anno=intermediate.beneath_optional(prop.type_annotation),
            descendability=descendability,
        )

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            block = Stripped(
                f"""\
if self.{prop_name} is not None:
{I}{indent_but_first_line(block, I)}"""
            )

        blocks.append(block)

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

    body = Stripped("\n\n".join(blocks))

    return [
        Stripped(
            f"""\
def descend_once(self) -> Iterator[Class]:
{I}\"\"\"
{I}Iterate over the instances referenced from this instance.

{I}We do not recurse into the referenced instance.

{I}:yield: instances directly referenced from this instance
{I}\"\"\"
{I}return self._descend(recurse=False)"""
        ),
        Stripped(
            f"""\
def descend(self) -> Iterator[Class]:
{I}\"\"\"
{I}Iterate recursively over the instances referenced from this one.

{I}:yield: instances recursively referenced from this instance
{I}\"\"\"
{I}return self._descend(recurse=True)"""
        ),
        Stripped(
            f"""\
def _descend(self, recurse: bool) -> Iterator[Class]:
{I}\"\"\"
{I}Iterate over the instances referenced from this one, and recursively
{I}over their descendants if :paramref:`recurse` is set.

{I}:param recurse: if set, descend recursively into the referenced instances
{I}:yield: instances referenced from this instance
{I}\"\"\"
{I}{indent_but_first_line(body, I)}"""
        ),
    ]


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
    elif len(arg_codes) == 1:
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


@require(lambda cls, prop: intermediate.runtime_id(prop) in cls.property_id_set)
@require(lambda prop: prop.description is not None)
def _generate_comment_for_property(
    cls: intermediate.ClassUnion,
    prop: intermediate.Property,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given property."""
    # NOTE (mristin):
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


class _MethodTranspiler(python_transpilation.Transpiler):
    """Transpile the body of a :py:class:`intermediate.UnderstoodMethod`."""

    def __init__(
        self,
        inference: intermediate_type_inference.InferenceOfFunction,
        method: intermediate.UnderstoodMethod,
    ) -> None:
        """Initialize with the given values."""
        python_transpilation.Transpiler.__init__(
            self,
            type_map=inference.type_map,
            environment=inference.environment_with_args,
            types_module=None,
        )

        self._argument_name_set = frozenset(arg.name for arg in method.arguments)

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(python_naming.variable_name(node.identifier)), None

        if node.identifier == "self":
            return Stripped("self"), None

        if node.identifier in self._argument_name_set:
            return Stripped(python_naming.argument_name(node.identifier)), None

        our_type = self._environment.find_our_type(node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(python_naming.enum_name(node.identifier)), None

        # NOTE (mristin):
        # The intermediate stage refuses the references to the constants and
        # to the verification functions in the methods, as they would introduce
        # a cyclic dependency between the modules.
        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to Python. We could not find it neither in the local variables, "
            f"nor in the arguments, nor as an enumeration. If you expect this name "
            f"to be transpilable, please contact the developers.",
        )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_method(
    method: intermediate.UnderstoodMethod,
    cls: intermediate.ClassUnion,
    type_inference: intermediate_type_inference.TypeInference,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Transpile the ``method`` as a member of the class ``cls``."""
    # NOTE (mristin):
    # We deliberately do not check the invariants of the instance after a method
    # call, as that would be too inefficient. The invariants are verified only in
    # the verification module, on the explicit request of the user. We note that
    # in the docstring of the mutating methods.
    extra_remarks = (
        [] if method.non_mutating else [NOTE_ON_INVARIANTS_OF_MUTATING_METHODS]
    )

    docstring = None  # type: Optional[Stripped]
    if method.description is not None:
        (
            docstring,
            docstring_errors,
        ) = python_description.generate_docstring_for_signature(
            description=method.description,
            context=python_description.Context(
                qualified_module_name=qualified_module_name,
                module=Identifier("types"),
                cls_or_enum=cls,
            ),
            extra_remarks=extra_remarks,
        )
        if docstring_errors is not None:
            return None, Error(
                method.description.parsed.node,
                f"Failed to generate the docstring for the method {method.name!r}",
                docstring_errors,
            )
    elif len(extra_remarks) > 0:
        docstring = python_description.docstring(Stripped("\n\n".join(extra_remarks)))

    transpiler = _MethodTranspiler(
        inference=type_inference.by_method[method], method=method
    )

    body = []  # type: List[Stripped]
    for node in method.body:
        stmt, error = transpiler.transform(node)
        if error is not None:
            return None, Error(
                method.parsed.node,
                f"Failed to transpile the method {method.name!r} "
                f"of the class {cls.name!r}",
                [error],
            )

        assert stmt is not None
        body.append(stmt)

    method_name = python_naming.method_name(method.name)

    returns = (
        python_common.generate_type(type_annotation=method.returns)
        if method.returns is not None
        else "None"
    )

    arg_codes = [Stripped("self")] + [
        Stripped(
            f"{python_naming.argument_name(arg.name)}: "
            f"{python_common.generate_argument_type(arg)}"
        )
        for arg in method.arguments
    ]

    writer = io.StringIO()
    if len(arg_codes) == 1:
        writer.write(f"def {method_name}(self) -> {returns}:")
    else:
        arg_block = ",\n".join(arg_codes)
        writer.write(
            f"""\
def {method_name}(
{I}{indent_but_first_line(arg_block, I)}
) -> {returns}:"""
        )

    if docstring is not None:
        writer.write("\n")
        writer.write(textwrap.indent(docstring, I))

    # NOTE (mristin):
    # The transpiled code is not idiomatic Python, so we do not lint it, as is
    # the case with the verification functions.
    writer.write(f"\n{I}# pylint: disable=all")

    if len(body) == 0:
        writer.write(f"\n{I}pass")
    else:
        for stmt in body:
            writer.write("\n")
            writer.write(textwrap.indent(stmt, I))

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_class(
    cls: intermediate.ClassUnion,
    spec_impls: specific_implementations.SpecificImplementations,
    qualified_module_name: python_common.QualifiedModuleName,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate Python code for the given concrete class ``cls``.

    The ``type_inference`` gives the inferred types of the understood methods.
    """
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
        ) and isinstance(
            prop.type_annotation.value,
            (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
        ):
            # NOTE (mristin):
            # The order of the items of a set is undefined, and the caller must
            # not depend on it.
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
        elif isinstance(method, intermediate.UnderstoodMethod):
            # NOTE (mristin):
            # Python inherits the methods, so we transpile each method only once,
            # in the class which specified it.
            method_code, method_error = _transpile_method(
                method=method,
                cls=cls,
                type_inference=type_inference,
                qualified_module_name=qualified_module_name,
            )
            if method_error is not None:
                errors.append(method_error)
                continue

            assert method_code is not None
            blocks.append(method_code)
        else:
            assert_never(method)

    if isinstance(cls, intermediate.ConcreteClass):
        blocks.extend(_generate_descend_methods(cls=cls))

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

    constructor_block, error = _generate_constructor(cls=cls, symbol_table=symbol_table)

    if error is not None:
        errors.append(error)
    else:
        assert constructor_block is not None

        # NOTE (mristin):
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

    # NOTE (mristin):
    # Every class in the meta-model inherits from the most general abstract class
    # ``Class`.

    super_names = []  # type: List[str]

    if len(cls.inheritances) == 0:
        # NOTE (mristin):
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
        # NOTE (mristin):
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
        # NOTE (mristin):
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
{I}raise NotImplementedError"""
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
{I}raise NotImplementedError"""
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
{I}raise NotImplementedError"""
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
{I}raise NotImplementedError"""
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


def _generate_named_union_alias(named_union: intermediate.NamedUnion) -> Stripped:
    """Generate the type alias for the named union ``named_union``."""
    name = python_naming.union_name(named_union.name)

    # NOTE (mristin):
    # We list the roots of the union, not its implementers, so that the alias
    # mirrors the meta-model. Abstract classes and concrete classes with
    # descendants are Python classes as well, so their descendants are covered
    # by the ``Union[...]`` through sub-typing.
    root_literals = [
        repr(python_naming.class_name(root.name)) for root in named_union.roots
    ]

    one_liner = f"{name} = Union[{', '.join(root_literals)}]"
    if len(one_liner) <= 70:
        assignment = one_liner
    else:
        joined_root_literals = ",\n".join(root_literals)
        assignment = f"""\
{name} = Union[
{I}{indent_but_first_line(joined_root_literals, I)},
]"""

    return Stripped(
        f"""\
#: Represent a union of classes.
{assignment}"""
    )


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


def _generate_json_aliases(uses_json_types: bool) -> List[Stripped]:
    """
    Generate the aliases of the JSON-able types, if the model uses them.

    They live here, next to the classes whose properties are annotated with
    them, and not in the jsonization: a property's type belongs to the types
    module, and the jsonization already imports it.
    """
    if not uses_json_types:
        return []

    return [
        Stripped(
            f"""\
# NOTE (mristin):
# A JSON-able value is, recursively, exactly as JSON itself is defined:
# a boolean, a number, a string, an array of JSON-able values or an object
# of JSON-able values with string keys -- never a ``None``, and never
# an infinity or a not-a-number, neither of which JSON can represent.
#
# JSON knows a single numeric type. Python tells an ``int`` from a ``float``,
# and a caller will naturally write either, so both are admitted here -- but
# an ``int`` only so long as a ``float`` can hold it exactly. The
# de-serialization converts every number it reads to a ``float``, and both
# the verification and the serialization refuse an ``int`` which that
# conversion would round.
#
# Recursive type aliases are not yet available in mypy
# (see https://github.com/python/mypy/issues/731), so the item and the value
# types have to be spelled ``Any`` instead of ``JsonValue``.
JsonValue = Union[
{I}bool,
{I}int,
{I}float,
{I}str,
{I}Sequence[Any],
{I}Mapping[str, Any]
]"""
        ),
        Stripped(
            """\
#: Represent a JSON-able value which is known to be an array
JsonArray = Sequence[Any]"""
        ),
        Stripped(
            """\
#: Represent a JSON-able value which is known to be an object
JsonObject = Mapping[str, Any]"""
        ),
    ]


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
    type_inference: intermediate_type_inference.TypeInference,
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

    typing_imports = [
        Identifier("Generic"),
        Identifier("Iterator"),
        Identifier("Optional"),
        Identifier("TypeVar"),
        Identifier("List"),
        Identifier("Tuple"),
    ]  # type: List[Identifier]

    if len(symbol_table.named_unions) > 0:
        typing_imports.append(Identifier("Union"))

    uses_json_types = intermediate_uses.json_types(symbol_table)
    if uses_json_types:
        typing_imports.extend(
            [
                Identifier("Any"),
                Identifier("Mapping"),
                Identifier("Sequence"),
            ]
        )

        if len(symbol_table.named_unions) == 0:
            typing_imports.append(Identifier("Union"))

    specified_methods = [
        method
        for cls in symbol_table.classes
        for method in cls.methods
        if method.specified_for is cls
    ]  # type: List[intermediate.Method]

    set_imports = python_common.typing_imports_for_sets(specified_methods)

    # NOTE (mristin):
    # The set properties and the corresponding arguments of the constructors are
    # always mutable, so they are annotated as ``Set``.
    if Identifier("Set") not in set_imports and intermediate_uses.set_properties(
        symbol_table
    ):
        set_imports.append(Identifier("Set"))

    typing_imports.extend(set_imports)

    # NOTE (mristin):
    # We spell out the final local lists as ``Final[Sequence[...]]``, and the lists
    # of the read-only arguments as ``Sequence[...]``, so we need to import ``Final``
    # and ``Sequence`` only if the methods declare them.
    final_annotations = [
        annotation
        for method in specified_methods
        for annotation in intermediate.local_declaration_annotations(method)
        if intermediate_type_inference.is_final_annotation(annotation)
    ]  # type: List[parse_tree.Expression]

    if Identifier("Sequence") not in typing_imports and (
        any(
            isinstance(node, parse_tree.Name) and node.identifier == "Sequence"
            for annotation in final_annotations
            for node in parse_tree.over_nodes(annotation)
        )
        or any(
            isinstance(type_anno, intermediate.ListTypeAnnotation)
            for method in specified_methods
            for argument in method.arguments
            if not argument.mutable
            for type_anno in intermediate.over_type_annotation_and_nested_type_annotations(
                argument.type_annotation
            )
        )
    ):
        typing_imports.append(Identifier("Sequence"))

    typing_imports_joined = ",\n".join(f"{I}{name}" for name in typing_imports)

    # NOTE (mristin):
    # We transpile ``int`` to a helper in the common module. We import the module
    # only if an understood method calls ``int`` so that the import is never unused.
    methods_call_int = any(
        isinstance(node, parse_tree.FunctionCall) and node.name.identifier == "int"
        for cls in symbol_table.classes
        for method in cls.methods
        if isinstance(method, intermediate.UnderstoodMethod)
        for body_node in method.body
        for node in parse_tree.over_nodes(body_node)
    )

    maybe_import_sys = "\nimport sys" if len(final_annotations) > 0 else ""

    import_blocks = [
        Stripped(
            f"""\
import abc
import enum{maybe_import_sys}
from typing import (
{typing_imports_joined}
)"""
        )
    ]  # type: List[Stripped]

    if len(final_annotations) > 0:
        import_blocks.append(
            Stripped(
                f"""\
if sys.version_info >= (3, 8):
{I}from typing import Final
else:
{I}from typing_extensions import Final"""
            )
        )

    if methods_call_int:
        import_blocks.append(
            Stripped(f"import {qualified_module_name}.common as our_common")
        )

    imports = Stripped("\n\n".join(import_blocks))

    blocks.extend(
        [
            python_common.WARNING,
            imports,
            Stripped(
                """\
T = TypeVar("T")
ContextT = TypeVar("ContextT")"""
            ),
            *_generate_json_aliases(uses_json_types=uses_json_types),
            Stripped(
                f"""\
class Class(abc.ABC):
{I}\"\"\"Represent the most general class of the meta-model.\"\"\"
{I}@abc.abstractmethod
{I}def descend_once(self) -> Iterator["Class"]:
{II}\"\"\"Iterate over all the instances referenced from this one.\"\"\"
{II}raise NotImplementedError

{I}@abc.abstractmethod
{I}def descend(self) -> Iterator["Class"]:
{II}\"\"\"Iterate recursively over all the instances referenced from this one.\"\"\"
{II}raise NotImplementedError

{I}@abc.abstractmethod
{I}def accept(
{III}self,
{III}visitor: "AbstractVisitor"
{I}) -> None:
{II}\"\"\"
{II}Dispatch the :paramref:`visitor` on this instance.

{II}:param visitor: to be dispatched
{II}\"\"\"
{II}raise NotImplementedError

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
{II}raise NotImplementedError

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
{II}raise NotImplementedError

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
{II}raise NotImplementedError"""
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
            # NOTE (mristin):
            # We do not generate the constrained primitives as types. We only
            # consider them in the verification.
            continue

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            block, error = _generate_class(
                cls=our_type,
                spec_impls=spec_impls,
                qualified_module_name=qualified_module_name,
                symbol_table=symbol_table,
                type_inference=type_inference,
            )
            if error is None:
                assert block is not None
                blocks.append(block)
                continue
        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(_generate_named_union_alias(named_union=our_type))
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

    observed_container_names = set()  # type: Set[Identifier]

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            descendability = intermediate.map_descendability(prop.type_annotation)

            for type_anno, descendable in descendability.items():
                if not descendable or not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ):
                    continue

                name = _descend_into_container_name(type_anno)
                if name in observed_container_names:
                    continue

                observed_container_names.add(name)

                blocks.append(
                    _generate_descend_into_container(
                        type_anno=type_anno, descendability=descendability
                    )
                )

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
