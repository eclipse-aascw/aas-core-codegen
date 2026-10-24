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
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    description as golang_description,
    pointering as golang_pointering,
    transpilation as golang_transpilation,
)
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.parse import tree as parse_tree
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


# region Checks


def _human_readable_identifier(
    something: Union[
        intermediate.Enumeration,
        intermediate.AbstractClass,
        intermediate.ConcreteClass,
        intermediate.EnumerationLiteral,
        intermediate.NamedUnion,
    ]
) -> str:
    """
    Represent ``something`` in a human-readable text.

    The reader should be able to trace ``something`` back to the meta-model.
    """
    # NOTE (mristin):
    # This function has been copy-pasted from
    # :py:mod:`aas_core_codegen.python.structure._generate`. We tried to refactor it to
    # :py:mod:`aas_core_codegen.intermediate`, but it turned out that the refactored
    # code was nigh unreadable. So we preferred a little bit of copying to a little
    # bit of complexity.

    result: str

    if isinstance(something, intermediate.Enumeration):
        result = f"meta-model enumeration {something.name!r}"
    elif isinstance(something, intermediate.EnumerationLiteral):
        result = f"meta-model enumeration literal {something.name!r}"
    elif isinstance(something, intermediate.AbstractClass):
        result = f"meta-model abstract class {something.name!r}"
    elif isinstance(something, intermediate.ConcreteClass):
        result = f"meta-model concrete class {something.name!r}"
    elif isinstance(something, intermediate.NamedUnion):
        result = f"meta-model named union {something.name!r}"
    else:
        # noinspection PyTypeChecker
        assert_never(something)

    assert result is not None
    return result


def _verify_intra_structure_collisions(
    our_type: intermediate.OurType,
) -> Optional[Error]:
    """Verify that no member names collide in the Golang structure of our type."""
    errors: List[Error] = []

    if isinstance(our_type, intermediate.Enumeration):
        # NOTE (mristin):
        # We already checked for collisions of enumeration literals in
        # the inter-structure collision checks.
        pass
    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        pass

    elif isinstance(our_type, intermediate.NamedUnion):
        # NOTE (mristin):
        # A named union has no members of its own, so there is nothing to
        # check for collisions here.
        pass

    elif isinstance(our_type, intermediate.Class):
        observed_member_names: Dict[Identifier, str] = {}

        for prop in our_type.properties:
            name = golang_naming.getter_name(prop.name)
            if name in observed_member_names:
                errors.append(
                    Error(
                        prop.parsed.node,
                        f"Golang getter {name!r} corresponding "
                        f"to the meta-model property {prop.name!r} collides with "
                        f"the {observed_member_names[name]}",
                    )
                )
            else:
                observed_member_names[name] = (
                    f"Golang getter {name!r} corresponding to "
                    f"the meta-model property {prop.name!r}"
                )

            name = golang_naming.setter_name(prop.name)
            if name in observed_member_names:
                errors.append(
                    Error(
                        prop.parsed.node,
                        f"Golang setter {name!r} corresponding "
                        f"to the meta-model property {prop.name!r} collides with "
                        f"the {observed_member_names[name]}",
                    )
                )
            else:
                observed_member_names[name] = (
                    f"Golang setter {name!r} corresponding to "
                    f"the meta-model property {prop.name!r}"
                )

            name = golang_naming.private_property_name(prop.name)

            if name in observed_member_names:
                errors.append(
                    Error(
                        prop.parsed.node,
                        f"Golang private property {name!r} corresponding "
                        f"to the meta-model property {prop.name!r} collides with "
                        f"the {observed_member_names[name]}",
                    )
                )
            else:
                observed_member_names[name] = (
                    f"Golang private property {name!r} corresponding to "
                    f"the meta-model property {prop.name!r}"
                )

        observed_constructor_arg_names: Dict[Identifier, str] = {}
        for constructor_arg in our_type.constructor.arguments:
            arg_name = golang_naming.argument_name(constructor_arg.name)

            if arg_name in observed_constructor_arg_names:
                errors.append(
                    Error(
                        constructor_arg.parsed.node,
                        f"Golang argument {arg_name!r} corresponding "
                        f"to the meta-model constructor argument {constructor_arg.name!r} "
                        f"collides with the {observed_constructor_arg_names[arg_name]}",
                    )
                )
            else:
                observed_constructor_arg_names[arg_name] = (
                    f"Golang argument {arg_name!r} corresponding to "
                    f"the meta-model constructor argument {constructor_arg.name!r}"
                )

        for method in our_type.methods:
            method_name = golang_naming.method_name(method.name)

            if method_name in observed_member_names:
                errors.append(
                    Error(
                        method.parsed.node,
                        f"Golang method {method_name!r} corresponding "
                        f"to the meta-model method {method.name!r} collides with "
                        f"the {observed_member_names[method_name]}",
                    )
                )
            else:
                observed_member_names[method_name] = (
                    f"Golang method {method_name!r} corresponding to "
                    f"the meta-model method {method.name!r}"
                )

            observed_method_arg_names: Dict[Identifier, str] = {}
            for arg in method.arguments:
                arg_name = golang_naming.argument_name(arg.name)

                if arg_name in observed_method_arg_names:
                    errors.append(
                        Error(
                            arg.parsed.node,
                            f"Golang argument {arg_name!r} corresponding "
                            f"to the meta-model method argument {arg.name!r} "
                            f"of the method {method.name} "
                            f"collides with the {observed_method_arg_names[arg_name]}",
                        )
                    )
                else:
                    observed_method_arg_names[arg_name] = (
                        f"Golang argument {arg_name!r} corresponding to "
                        f"the meta-model method argument {arg.name!r}"
                    )

    else:
        # noinspection PyTypeChecker
        assert_never(our_type)

    if len(errors) > 0:
        return Error(
            our_type.parsed.node,
            f"Naming collision(s) in Golang code for our type {our_type.name!r}",
            underlying=errors,
        )

    return None


def _verify_structure_name_collisions(
    symbol_table: intermediate.SymbolTable,
) -> List[Error]:
    """Verify that the Golang names of the structures do not collide."""
    observed_structure_names: Dict[
        Identifier,
        Union[
            intermediate.Enumeration,
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.EnumerationLiteral,
            intermediate.NamedUnion,
        ],
    ] = dict()

    errors: List[Error] = []

    # region Inter-structure collisions

    # noinspection PyTypeChecker
    for enum_or_cls in itertools.chain(
        symbol_table.enumerations, symbol_table.classes, symbol_table.named_unions
    ):
        names: List[Identifier]

        if isinstance(enum_or_cls, intermediate.Enumeration):
            names = [golang_naming.enum_name(enum_or_cls.name)]
        elif isinstance(enum_or_cls, intermediate.AbstractClass):
            names = [golang_naming.interface_name(enum_or_cls.name)]
        elif isinstance(enum_or_cls, intermediate.ConcreteClass):
            names = [
                golang_naming.interface_name(enum_or_cls.name),
                golang_naming.struct_name(enum_or_cls.name),
            ]
        elif isinstance(enum_or_cls, intermediate.NamedUnion):
            names = [golang_naming.union_name(enum_or_cls.name)]
        else:
            # noinspection PyTypeChecker
            assert_never(enum_or_cls)

        for name in names:
            other = observed_structure_names.get(name)

            if other is not None:
                errors.append(
                    Error(
                        enum_or_cls.parsed.node,
                        f"The Golang name {name!r} "
                        f"of the {_human_readable_identifier(enum_or_cls)} "
                        f"collides with the Golang name "
                        f"of the {_human_readable_identifier(other)}",
                    )
                )
            else:
                observed_structure_names[name] = enum_or_cls

    # NOTE (mristin):
    # Enumeration literals are global constants in Go, so we have to consider them
    # for collisions as well.
    for enum in symbol_table.enumerations:
        for literal in enum.literals:
            name = golang_naming.enum_literal_name(enum.name, literal.name)

            other = observed_structure_names.get(name)

            if other is not None:
                errors.append(
                    Error(
                        literal.parsed.node,
                        f"The Golang name {name!r} "
                        f"of the {_human_readable_identifier(literal)} "
                        f"collides with the Golang name "
                        f"of the {_human_readable_identifier(other)}",
                    )
                )
            else:
                observed_structure_names[name] = literal

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
    """Verify that Golang code can be generated from the ``symbol_table``."""
    errors: List[Error] = []

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
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given enumeration literal."""
    # NOTE (mristin):
    # We need to state the pre-condition for the second time for mypy.
    assert literal.description is not None

    # fmt: off
    comment, errors = (
        golang_description.generate_comment_for_summary_remarks(
            description=literal.description,
            context=golang_description.Context(
                package=golang_common.TYPES_PACKAGE,
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
    """Generate the documentation comment for our type."""
    # NOTE (mristin):
    # We need to state the pre-condition for the second time for mypy.
    assert cls_or_enum.description is not None

    # fmt: off
    comment, errors = (
        golang_description
        .generate_comment_for_summary_remarks_constraints(
            description=cls_or_enum.description,
            context=golang_description.Context(
                package=golang_common.TYPES_PACKAGE, cls_or_enum=None
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
    """Generate the Golang code for the enum."""
    writer = io.StringIO()

    errors: List[Error] = []

    comment: Optional[Stripped] = None
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

    name = golang_naming.enum_name(enum.name)

    writer.write(f"type {name} int;")
    if len(enum.literals) > 0:
        writer.write("const (\n")

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

            literal_name = golang_naming.enum_literal_name(enum.name, literal.name)

            # NOTE (mristin):
            # We optimize for comparisons instead of stringification.
            # The stringification is delegated to a separate module.

            if i == 0:
                writer.write(textwrap.indent(f"{literal_name} {name} = iota", I))
            else:
                writer.write(textwrap.indent(literal_name, I))

            writer.write("\n")

        writer.write(")")

    if len(errors) > 0:
        return None, Error(
            enum.parsed.node,
            f"Failed to generate the Golang code for the enumeration {enum.name!r}",
            errors,
        )

    return Stripped(writer.getvalue()), None


def _literals_of_enum(enum: intermediate.Enumeration) -> Stripped:
    """Generate the Golang code for the constant array listing the literals."""
    name = golang_naming.enum_name(enum.name)
    array_name = golang_naming.constant_name(Identifier(f"literals_of_{enum.name}"))

    literals = []
    for literal in enum.literals:
        literals.append(golang_naming.enum_literal_name(enum.name, literal.name))

    literals_joined = "\n".join(f"{literal}," for literal in literals)

    return Stripped(
        f"""\
// List the literals of [{name}].
//
// Golang does not provide an elegant way to iterate over the literals, so
// this array helps you avoid common errors and pitfalls.
//
// Please do not modify the array in the caller's code.
var {array_name} = [...]{name} {{
{I}{indent_but_first_line(literals_joined, I)}
}}"""
    )


def _generate_definition_for_model_type(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """
    Generate the enumeration corresponding to the model types.

    This is necessary so that we can have fast switches on instance types.
    """
    enum_name = golang_naming.enum_name(Identifier("Model_type"))

    literal_specs: List[Stripped] = []
    for i, cls in enumerate(symbol_table.concrete_classes):
        literal_name = golang_naming.enum_literal_name(
            Identifier("Model_type"), cls.name
        )

        if i == 0:
            literal_specs.append(Stripped(f"{literal_name} {enum_name} = iota"))
        else:
            literal_specs.append(literal_name)

    literal_specs_joined = "\n".join(literal_specs)

    if len(literal_specs) == 0:
        return Stripped(f"type {enum_name} int")

    return Stripped(
        f"""\
// Enumerate the model types for faster type switches.
//
// For example, you can use an array of function pointers to
// implement such a switch.
type {enum_name} int
const (
{I}{indent_but_first_line(literal_specs_joined, I)}
)"""
    )


def _descend_into_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the function descending into ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.golang.common.type_moniker`), so two different
    containers never share a function.
    """
    return Identifier(f"descend_{golang_common.type_moniker(type_anno)}")


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
    Generate the statements applying the action on the instances held at ``expr``.

    An instance is handled in-line. A container is delegated to its function,
    which descends only one level and calls the function of its items by name.
    This way the descent is composed of plain functions, to any depth.

    The generated code recurses only if the Golang variable ``recurse`` is set.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        # NOTE (mristin):
        # A named union is not itself an ``IClass``, so we descend into
        # the underlying instance instead.
        instance_expr = (
            f"{expr}.Underlying()"
            if isinstance(type_anno.our_type, intermediate.NamedUnion)
            else expr
        )

        return Stripped(
            f"""\
abort = action(
{I}{instance_expr},
)
if abort {{
{I}return
}}

if recurse {{
{I}abort = {instance_expr}.Descend(
{II}action,
{I})
{I}if abort {{
{II}return
{I}}}
}}"""
        )

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        name = _descend_into_container_name(type_anno)

        return Stripped(
            f"""\
abort = {name}(
{I}{expr},
{I}action,
{I}recurse,
)
if abort {{
{I}return
}}"""
        )

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
    Generate the function descending into ``type_anno``.

    The ``descendability`` maps ``type_anno`` and its nested type annotations,
    see :py:func:`aas_core_codegen.intermediate.map_descendability`.
    """
    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_stmts = _generate_descend_into(
            expr="item",
            type_anno=type_anno.items,
            descendability=descendability,
        )

        body = Stripped(
            f"""\
for _, item := range that {{
{I}{indent_but_first_line(item_stmts, I)}
}}"""
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        # NOTE (mristin):
        # A set is a Golang map, which we can only iterate in a random order,
        # so the descent would not be deterministic. Since no set holds
        # instances at the moment, we refuse to generate the descent for now.
        raise AssertionError(
            f"Unexpected set holding instances: {type_anno}. We do not generate "
            f"the descent into sets, since the order of iteration over a Golang map "
            f"is random. Please contact the developers if you need this feature."
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = Stripped(
            "\n\n".join(
                _generate_descend_into(
                    expr=f"that.Item{i + 1}",
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
    value_type = golang_common.generate_type(type_anno)

    return Stripped(
        f"""\
// Apply the action on the instances held by that, and recursively on their
// descendants if recurse is set.
//
// If any of the actions returns abort `true`, the descent is immediately
// stopped, and abort `true` is also returned. Otherwise, return abort `false`.
func {name}(
{I}that {value_type},
{I}action func(IClass) bool,
{I}recurse bool,
) (abort bool) {{
{I}{indent_but_first_line(body, I)}

{I}return
}}"""
    )


def _generate_descend_methods(
    cls: intermediate.ConcreteClass, receiver: Identifier
) -> List[Stripped]:
    """
    Generate the ``DescendOnce`` and ``Descend`` methods for ``cls``.

    Both methods delegate to a single function, which takes the recursion as
    a run-time flag, so that we do not generate the same body twice.
    """
    blocks: List[Stripped] = []

    for prop in cls.properties:
        descendability = intermediate.map_descendability(prop.type_annotation)

        if not descendability[prop.type_annotation]:
            continue

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_name = golang_naming.private_property_name(prop.name)

        # NOTE (mristin):
        # An optional of a non-nilable type, such as a tuple, is a pointer,
        # but we pass the containers by value.
        access_expr = (
            f"*that.{prop_name}"
            if golang_pointering.is_pointer_type(prop.type_annotation)
            else f"that.{prop_name}"
        )

        block = _generate_descend_into(
            expr=access_expr,
            type_anno=type_anno,
            descendability=descendability,
        )

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            block = Stripped(
                f"""\
if that.{prop_name} != nil {{
{I}{indent_but_first_line(block, I)}
}}"""
            )

        blocks.append(block)

    if len(blocks) == 0:
        blocks.append(Stripped("// No descendable properties"))

    blocks.append(Stripped("return"))

    body = "\n\n".join(blocks)

    struct_name = golang_naming.struct_name(cls.name)

    # NOTE (mristin):
    # We name the function with an underscore so that it can not collide with
    # any of the other names in the package, which never contain one.
    function_name = Identifier(f"descend_{struct_name}")

    return [
        Stripped(
            f"""\
// Apply the action on the instances referenced from {receiver}.
//
// If any of the actions returns abort `true`, the descent is immediately
// stopped, and abort `true` is also returned. Otherwise, return abort `false`.
//
// We do not recurse into the referenced instances.
//
// The action is not applied on {receiver}.
func ({receiver} *{struct_name}) DescendOnce(
{I}action func(IClass) bool,
) (abort bool) {{
{I}return {function_name}({receiver}, action, false)
}}"""
        ),
        Stripped(
            f"""\
// Apply the action recursively on the instances referenced from {receiver}.
//
// If any of the actions returns abort `true`, the descent is immediately
// stopped, and abort `true` is also returned. Otherwise, return abort `false`.
//
// The action is not applied on {receiver}.
func ({receiver} *{struct_name}) Descend(
{I}action func(IClass) bool,
) (abort bool) {{
{I}return {function_name}({receiver}, action, true)
}}"""
        ),
        Stripped(
            f"""\
// Apply the action on the instances referenced from that, and recursively
// on their descendants if recurse is set.
//
// If any of the actions returns abort `true`, the descent is immediately
// stopped, and abort `true` is also returned. Otherwise, return abort `false`.
//
// The action is not applied on that.
func {function_name}(
{I}that *{struct_name},
{I}action func(IClass) bool,
{I}recurse bool,
) (abort bool) {{
{I}{indent_but_first_line(body, I)}
}}"""
        ),
    ]


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_constructor(
    cls: intermediate.ClassUnion,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the constructor function for the given concrete class ``cls``."""
    property_names = [prop.name for prop in cls.properties]
    constructor_argument_names = [arg.name for arg in cls.constructor.arguments]

    # fmt: off
    assert (
            {prop.name for prop in cls.properties}
            == {arg.name for arg in cls.constructor.arguments}
    ), (
        f"Expected the properties to coincide with constructor arguments, "
        f"but they do not for {cls.name!r}:"
        f"{property_names=}, {constructor_argument_names=}"
    )
    # fmt: on

    # NOTE (mristin):
    # Golang is peculiar, so we do not transpile the in-lined statements, but simply set
    # the required properties to argument values and optional values to default argument
    # values, if any were specified.
    #
    # It is not clear at this moment whether the SDK clients would really appreciate
    # the added complexity of the code, so we wait till we get some feedback on it.

    blocks: List[str] = []

    struct_specs: List[Stripped] = []

    for arg in cls.constructor.arguments:
        if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        arg_name = golang_naming.argument_name(arg.name)
        private_prop_name = golang_naming.private_property_name(arg.name)

        struct_specs.append(Stripped(f"{private_prop_name}: {arg_name}"))

        if arg.default is not None:
            return None, Error(
                arg.default.parsed.node,
                f"(mristin): "
                f"The argument {arg.name!r} is a required argument, "
                f"but the default value is also specified. At the moment when we "
                f"wrote the generator, we did not know how this use case should "
                f"work out in Golang. Please contact the developers and "
                f"discuss how this should be implemented.",
            )

    for arg in cls.constructor.arguments:
        if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        if arg.default is None:
            continue

        private_prop_name = golang_naming.private_property_name(arg.name)

        # NOTE (mristin):
        # We have to be careful: an optional property will be generated with a pointer
        # type.

        if isinstance(arg.default, intermediate.DefaultPrimitive):
            if arg.default.value is None:
                struct_specs.append(Stripped(f"{private_prop_name}: nil"))
            elif isinstance(arg.default.value, bool):
                literal = golang_common.boolean_literal(arg.default.value)
                struct_specs.append(
                    Stripped(
                        f"""\
{private_prop_name}: ourcommon.NewAndPointTo(
{I}{literal}
)"""
                    )
                )
            elif isinstance(arg.default.value, int):
                literal = Stripped(str(arg.default.value))
                struct_specs.append(
                    Stripped(
                        f"""\
{private_prop_name}: ourcommon.NewAndPointTo(
{I}int64({literal})
)"""
                    )
                )
            elif isinstance(arg.default.value, float):
                literal = golang_common.float_literal(arg.default.value)
                struct_specs.append(
                    Stripped(
                        f"""\
{private_prop_name}: ourcommon.NewAndPointTo(
{I}float64({literal})
)"""
                    )
                )
            elif isinstance(arg.default.value, str):
                literal = golang_common.string_literal(arg.default.value)
                struct_specs.append(
                    Stripped(
                        f"""\
{private_prop_name}: ourcommon.NewAndPointTo(
{I}{literal}
)"""
                    )
                )
            else:
                # noinspection PyTypeChecker
                assert_never(arg.default.value)
        elif isinstance(arg.default, intermediate.DefaultEnumerationLiteral):
            literal = golang_naming.enum_literal_name(
                arg.default.enumeration.name, arg.default.literal.name
            )
            struct_specs.append(
                Stripped(
                    f"""\
{private_prop_name}: ourcommon.NewAndPointTo(
{I}{literal}
)"""
                )
            )
        else:
            # noinspection PyTypeChecker
            assert_never(arg.default)

    struct_name = golang_naming.struct_name(cls.name)

    if len(struct_specs) == 0:
        blocks.append(
            Stripped(
                f"""\
// Intentionally empty.
return &{struct_name}{{}}"""
            )
        )
    else:
        struct_specs_joined = "\n".join(
            f"{struct_spec}," for struct_spec in struct_specs
        )

        blocks.append(
            Stripped(
                f"""\
return &{struct_name}{{
{I}{indent_but_first_line(struct_specs_joined, I)}
}}"""
            )
        )

    body = "\n\n".join(blocks)

    arg_codes: List[str] = []
    for arg in cls.constructor.arguments:
        if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        arg_type = golang_common.generate_type(type_annotation=arg.type_annotation)
        arg_name = golang_naming.argument_name(arg.name)

        arg_codes.append(Stripped(f"{arg_name} {arg_type}"))

    function_name = golang_naming.function_name(Identifier(f"new_{cls.name}"))

    comment = f"""\
// Create a new instance of {struct_name} with
// the given properties."""

    if len(arg_codes) == 0:
        return (
            Stripped(
                f"""\
{comment}
func {function_name}() *{struct_name} {{
{I}{indent_but_first_line(body, I)}
}}"""
            ),
            None,
        )

    arg_codes_joined = "\n".join(f"{arg_code}," for arg_code in arg_codes)
    return (
        Stripped(
            f"""\
{comment}
func {function_name}(
{I}{indent_but_first_line(arg_codes_joined, I)}
) *{struct_name} {{
{I}{indent_but_first_line(body, I)}
}}"""
        ),
        None,
    )


@require(lambda cls, prop: intermediate.runtime_id(prop) in cls.property_id_set)
@require(lambda prop: prop.description is not None)
def _generate_comment_for_property(
    cls: intermediate.ClassUnion,
    prop: intermediate.Property,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given property."""
    # NOTE (mristin):
    # We need to write a double assertion for mypy.
    assert prop.description is not None

    # fmt: off
    comment, errors = (
        golang_description
        .generate_comment_for_summary_remarks_constraints(
            description=prop.description,
            context=golang_description.Context(
                package=golang_common.TYPES_PACKAGE,
                cls_or_enum=cls,
            )
        )
    )
    # fmt: on

    if errors is not None:
        return None, errors

    assert comment is not None

    return comment, None


@ensure(lambda result: not (result[1] is not None) or (result[0] is None))
def _generate_comment_for_method(
    method: intermediate.MethodUnion, cls: intermediate.ClassUnion
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the documentation comment for the ``method``, if any.

    We note in the documentation of the transpiled mutating methods that
    the invariants are not enforced after the call.
    """
    extra_remarks = (
        [NOTE_ON_INVARIANTS_OF_MUTATING_METHODS]
        if isinstance(method, intermediate.UnderstoodMethod) and not method.non_mutating
        else []
    )

    if method.description is None:
        if len(extra_remarks) == 0:
            return None, None

        return (
            golang_description.documentation_comment(
                Stripped("\n\n".join(extra_remarks))
            ),
            None,
        )

    comment, comment_errors = golang_description.generate_comment_for_signature(
        method.description,
        context=golang_description.Context(
            package=golang_common.TYPES_PACKAGE, cls_or_enum=cls
        ),
        extra_remarks=extra_remarks,
    )

    if comment_errors is not None:
        return None, Error(
            method.description.parsed.node,
            f"Failed to generate the documentation comment "
            f"for method {method.name!r}",
            comment_errors,
        )

    assert comment is not None
    return comment, None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_interface(
    cls: intermediate.ClassUnion,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the Golang code of the interface corresponding to ``cls``."""
    # Code blocks separated by double newlines and indented once
    blocks: List[Stripped] = []

    # region Inheritance

    if len(cls.inheritances) > 0:
        for inheritance in cls.inheritances:
            inheritance_name = golang_naming.interface_name(inheritance.name)
            blocks.append(inheritance_name)
    else:
        blocks.append(Stripped("IClass"))

    # endregion

    # region Getters and Setters

    for prop in cls.properties:
        if prop.specified_for is not cls:
            continue

        prop_type = golang_common.generate_type(type_annotation=prop.type_annotation)

        prop_comment: Optional[Stripped] = None
        if prop.description is not None:
            (
                prop_comment,
                prop_comment_errors,
            ) = _generate_comment_for_property(cls=cls, prop=prop)

            if prop_comment_errors is not None:
                return None, Error(
                    prop.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for the property {prop.name!r}",
                    prop_comment_errors,
                )

            assert prop_comment is not None

        getter_name = golang_naming.getter_name(prop.name)
        if prop_comment:
            blocks.append(
                Stripped(
                    f"""\
{prop_comment}
{getter_name}() {prop_type};"""
                )
            )
        else:
            blocks.append(Stripped(f"{getter_name}() {prop_type};"))

        setter_name = golang_naming.setter_name(prop.name)
        blocks.append(
            Stripped(
                f"""\
{setter_name}(
{I}value {prop_type},
);"""
            )
        )

    # endregion

    # region Methods

    for method in cls.methods:
        if method.visibility is not intermediate.Visibility.PUBLIC:
            continue

        method_blocks: List[Stripped] = []

        method_comment, method_comment_error = _generate_comment_for_method(
            method=method, cls=cls
        )
        if method_comment_error is not None:
            return None, method_comment_error

        if method_comment is not None:
            method_blocks.append(method_comment)

        # fmt: off
        # noinspection PyTypeChecker
        returns = (
            f" {golang_common.generate_type(type_annotation=method.returns)}"
            if method.returns is not None else ""
        )
        # fmt: on

        arg_codes: List[Stripped] = []
        for arg in method.arguments:
            arg_type = golang_common.generate_type(type_annotation=arg.type_annotation)
            arg_name = golang_naming.argument_name(arg.name)
            arg_codes.append(Stripped(f"{arg_name} {arg_type}"))

        method_name = golang_naming.method_name(method.name)

        if len(arg_codes) == 0:
            method_blocks.append(Stripped(f"{method_name}(){returns};"))
        else:
            arg_codes_joined = "\n".join(f"{arg_code}," for arg_code in arg_codes)
            method_blocks.append(
                Stripped(
                    f"""\
{method_name}(
{I}{indent_but_first_line(arg_codes_joined, I)}
){returns};"""
                )
            )

        blocks.append(Stripped("\n".join(method_blocks)))

    comment: Optional[Stripped] = None
    if cls.description is not None:
        # fmt: off
        comment, comment_errors = (
            golang_description
            .generate_comment_for_summary_remarks_constraints(
                cls.description,
                context=golang_description.Context(
                    package=golang_common.TYPES_PACKAGE,
                    cls_or_enum=cls
                )
            )
        )
        # fmt: on

        if comment_errors is not None:
            return None, Error(
                cls.description.parsed.node,
                "Failed to generate the documentation comment",
                comment_errors,
            )

        assert comment is not None

    if len(blocks) == 0:
        blocks = [Stripped("// Intentionally empty.")]

    writer = io.StringIO()
    if comment is not None:
        writer.write(comment)
        writer.write("\n")

    interface_name = golang_naming.interface_name(cls.name)

    blocks_joined = "\n\n".join(blocks)

    writer.write(
        f"""\
type {interface_name} interface {{
{I}{indent_but_first_line(blocks_joined, I)}
}}"""
    )

    return Stripped(writer.getvalue()), None


def _generate_is_interface(
    cls: intermediate.ClassUnion, symbol_table: intermediate.SymbolTable
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the function to check the model type against ``cls``."""
    interface_name = golang_naming.interface_name(cls.name)
    function_name = golang_naming.function_name(Identifier(f"is_{cls.name}"))

    if len(cls.concrete_descendants) == 0:
        if isinstance(cls, intermediate.AbstractClass):
            return None, Error(
                cls.parsed.node,
                f"Unexpected abstract class with no concrete descendants: {cls.name!r}",
            )

        model_type_literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=cls.name
        )
        body = Stripped(f"ok = that.ModelType() == {model_type_literal}")
    else:
        case_statements: List[Stripped] = []

        for another_cls in symbol_table.concrete_classes:
            model_type_literal = golang_naming.enum_literal_name(
                Identifier("Model_type"), another_cls.name
            )

            if (
                intermediate.runtime_id(another_cls) in cls.concrete_descendant_id_set
                or another_cls is cls
            ):
                case_statements.append(
                    Stripped(
                        f"""\
case {model_type_literal}:
{I}ok = true"""
                    )
                )

        case_statements_joined = "\n".join(case_statements)
        body = Stripped(
            f"""\
switch that.ModelType() {{
{case_statements_joined}
}}"""
        )

    return (
        Stripped(
            f"""\
// Check whether the instance corresponds to [ourtypes.{interface_name}]
// based on its run-time model type.
//
// The implementation uses a switch statements which is
// most probably compiled as an efficient jump table by the compiler.
func {function_name}(
{I}that IClass,
) (ok bool) {{
{I}{indent_but_first_line(body, I)}
{I}return
}}"""
        ),
        None,
    )


def _generate_struct(cls: intermediate.ConcreteClass) -> Stripped:
    blocks: List[Stripped] = []

    for prop in cls.properties:
        prop_type = golang_common.generate_type(type_annotation=prop.type_annotation)
        private_prop_name = golang_naming.private_property_name(prop.name)

        blocks.append(Stripped(f"{private_prop_name} {prop_type}"))

    body = "\n".join(blocks)

    struct_name = golang_naming.struct_name(cls.name)
    interface_name = golang_naming.interface_name(cls.name)

    return Stripped(
        f"""\
// Implements {interface_name}.
type {struct_name} struct {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


class _MethodTranspiler(golang_transpilation.Transpiler):
    """Transpile the body of a :py:class:`intermediate.UnderstoodMethod`."""

    def __init__(
        self,
        inference: intermediate_type_inference.InferenceOfFunction,
        is_pointer_map: Mapping[parse_tree.Node, bool],
        method: intermediate.UnderstoodMethod,
        receiver: Identifier,
    ) -> None:
        """Initialize with the given values."""
        golang_transpilation.Transpiler.__init__(
            self,
            type_map=inference.type_map,
            is_pointer_map=is_pointer_map,
            downcast_map=inference.downcast_map,
            environment=inference.environment_with_args,
        )

        self._argument_name_set = frozenset(arg.name for arg in method.arguments)
        self._receiver = receiver

    def _transform_enumeration_literal(
        self, enumeration_name: Identifier, literal_name: Identifier
    ) -> Stripped:
        return Stripped(
            golang_naming.enum_literal_name(
                enumeration_name=enumeration_name, literal_name=literal_name
            )
        )

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(golang_naming.variable_name(node.identifier)), None

        if node.identifier == "self":
            return Stripped(self._receiver), None

        if node.identifier in self._argument_name_set:
            return Stripped(golang_naming.argument_name(node.identifier)), None

        our_type = self._environment.find_our_type(node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(golang_naming.enum_name(node.identifier)), None

        # NOTE (mristin):
        # The intermediate stage refuses the references to the constants and
        # to the verification functions in the methods, as they would introduce
        # a cyclic dependency between the packages.
        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to Golang. We could not find it neither in the local variables, "
            f"nor in the arguments, nor as an enumeration. If you expect this name "
            f"to be transpilable, please contact the developers.",
        )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_method(
    method: intermediate.UnderstoodMethod,
    cls: intermediate.ConcreteClass,
    type_inference: intermediate_type_inference.TypeInference,
    receiver: Identifier,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Transpile the ``method`` as a method of the struct of ``cls``."""
    # NOTE (mristin):
    # We deliberately do not check the invariants of the instance after a method
    # call, as that would be too inefficient. The invariants are verified only in
    # the verification package, on the explicit request of the user. We note that
    # in the documentation of the mutating methods, see
    # :py:func:`_generate_comment_for_method`.

    inference = type_inference.by_method[method]

    pointer_inferrer = golang_pointering.Inferrer(
        environment=inference.environment_with_args,
        type_map=inference.type_map,
    )

    for node in method.body:
        _ = pointer_inferrer.transform(node)

    if len(pointer_inferrer.errors) > 0:
        return None, Error(
            method.parsed.node,
            f"Failed to infer whether a node is a Golang pointer "
            f"in the method {method.name!r} of the class {cls.name!r}",
            pointer_inferrer.errors,
        )

    transpiler = _MethodTranspiler(
        inference=inference,
        is_pointer_map=pointer_inferrer.is_pointer_map,
        method=method,
        receiver=receiver,
    )

    body: List[Stripped] = []
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

    writer = io.StringIO()

    comment, comment_error = _generate_comment_for_method(method=method, cls=cls)
    if comment_error is not None:
        return None, comment_error

    if comment is not None:
        writer.write(comment)
        writer.write("\n")

    struct_name = golang_naming.struct_name(cls.name)

    method_name = golang_naming.method_name(method.name)

    returns = (
        f" {golang_common.generate_type(type_annotation=method.returns)}"
        if method.returns is not None
        else ""
    )

    arg_defs = [
        Stripped(
            f"{golang_naming.argument_name(arg.name)} "
            f"{golang_common.generate_type(arg.type_annotation)}"
        )
        for arg in method.arguments
    ]

    if len(arg_defs) == 0:
        writer.write(f"func ({receiver} *{struct_name}) {method_name}(){returns} {{")
    else:
        arg_defs_joined = "\n".join(f"{arg_def}," for arg_def in arg_defs)
        writer.write(
            f"""\
func ({receiver} *{struct_name}) {method_name}(
{I}{indent_but_first_line(arg_defs_joined, I)}
){returns} {{"""
        )

    for stmt in body:
        writer.write("\n")
        writer.write(textwrap.indent(stmt, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_struct_methods(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[List[Stripped]], Optional[Error]]:
    """
    Generate the Golang methods for the struct corresponding to ``cls``.

    ``type_inference`` holds the type inference of all the understood methods.
    """
    methods: List[Stripped] = []

    receiver = golang_naming.receiver_name(cls)

    # region Setter and getter implementations

    struct_name = golang_naming.struct_name(cls.name)

    for prop in cls.properties:
        prop_type = golang_common.generate_type(prop.type_annotation)
        private_prop_name = golang_naming.private_property_name(prop.name)

        getter_name = golang_naming.getter_name(prop.name)

        methods.append(
            Stripped(
                f"""\
func ({receiver} *{struct_name}) {getter_name}(
) {prop_type} {{
{I}return {receiver}.{private_prop_name}
}}"""
            )
        )

        setter_name = golang_naming.setter_name(prop.name)

        methods.append(
            Stripped(
                f"""\
func ({receiver} *{struct_name}) {setter_name}(
{I}value {prop_type},
) {{
{I}{receiver}.{private_prop_name} = value
}}"""
            )
        )

    # endregion

    # region Getter of Model Type

    model_type_literal = golang_naming.enum_literal_name(
        enumeration_name=Identifier("Model_type"), literal_name=cls.name
    )

    model_type_enum = golang_naming.enum_name(Identifier("Model_type"))
    model_type_getter = golang_naming.getter_name(Identifier("model_type"))

    methods.append(
        Stripped(
            f"""\
func ({receiver} *{struct_name}) {model_type_getter}(
) {model_type_enum} {{
{I}return {model_type_literal}
}}"""
        )
    )

    # endregion

    # region Methods

    errors: List[Error] = []

    for method in cls.methods:
        if isinstance(method, intermediate.ImplementationSpecificMethod):
            implementation_key = specific_implementations.ImplementationKey(
                f"Types/{method.specified_for.name}/{method.name}.go"
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

            # fmt: off
            methods.append(
                Stripped(
                    implementation
                    .replace("_RECEIVER_", receiver)
                    .replace("_STRUCT_NAME_", struct_name)
                )
            )
            # fmt: on
        elif isinstance(method, intermediate.UnderstoodMethod):
            method_code, method_error = _transpile_method(
                method=method,
                cls=cls,
                type_inference=type_inference,
                receiver=receiver,
            )
            if method_error is not None:
                errors.append(method_error)
                continue

            assert method_code is not None
            methods.append(method_code)
        else:
            assert_never(method)

    methods.extend(_generate_descend_methods(cls=cls, receiver=receiver))

    # endregion

    # region Constructor

    constructor_block, error = _generate_constructor(cls=cls)

    if error is not None:
        errors.append(error)
    else:
        assert constructor_block is not None

        methods.append(constructor_block)
    # endregion

    if len(errors) > 0:
        return None, Error(
            cls.parsed.node,
            f"Failed to generate the methods for the class {cls.name}",
            errors,
        )

    return methods, None


def _generate_comment_for_meta_model(
    description: intermediate.DescriptionOfMetaModel,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the docstring for the given meta-model."""
    # fmt: off
    comment, errors = (
        golang_description
        .generate_comment_for_summary_remarks_constraints(
            description=description,
            context=golang_description.Context(
                package=golang_common.TYPES_PACKAGE, cls_or_enum=None
            )
        )
    )
    # fmt: on

    if errors is not None:
        return None, errors

    assert comment is not None

    return comment, None


def _generate_named_union_struct(named_union: intermediate.NamedUnion) -> Stripped:
    """
    Generate the struct representing ``named_union``.

    Unlike a class, a named union is a closed set of alternatives, so we do
    not want to allow custom enhancements or wrappings around it. Hence we
    represent it as a plain struct storing exactly one of its roots, tagged by
    a private discriminant, so that the struct mirrors the meta-model. This keeps
    every alternative in its own, separately typed field, so that a future
    primitive alternative (which can not implement `IClass`) would still fit
    the same shape.

    Go interfaces are structural, so a type switch on the interfaces can not tell
    the roots apart (*e.g.*, an abstract class without properties is satisfied by
    any :py:class:`IClass`). Hence we dispatch on the model type of each implementer
    instead, and wrap it in its most specific root.
    """
    name = golang_naming.union_name(named_union.name)
    receiver = Identifier(name[0].lower())

    value_kind = golang_naming.private_struct_name(
        Identifier(f"{named_union.name}_value_kind")
    )

    interface_names = [
        golang_naming.interface_name(root.name) for root in named_union.roots
    ]

    crefs = [f"[{interface_name}]" for interface_name in interface_names]
    if len(crefs) == 1:
        crefs_joined = crefs[0]
    else:
        crefs_joined = ", ".join(crefs[:-1]) + " and " + crefs[-1]

    discriminant_cases: List[Stripped] = []
    field_decls: List[Stripped] = []
    underlying_cases: List[Stripped] = []
    from_methods: List[Stripped] = []
    from_underlying_cases: List[Stripped] = []

    field_names = [
        golang_naming.private_property_name(Identifier(f"as_{root.name}"))
        for root in named_union.roots
    ]

    for root, interface_name, field_name in zip(
        named_union.roots, interface_names, field_names, strict=True
    ):
        discriminant_case = golang_naming.private_constant_name(
            Identifier(f"{named_union.name}_value_kind_{root.name}")
        )

        if len(discriminant_cases) == 0:
            discriminant_cases.append(
                Stripped(f"{discriminant_case} {value_kind} = iota")
            )
        else:
            discriminant_cases.append(Stripped(discriminant_case))

        field_decls.append(Stripped(f"{field_name} {interface_name}"))

        underlying_cases.append(
            Stripped(
                f"""\
case {discriminant_case}:
{I}return {receiver}.{field_name}"""
            )
        )

        from_method_name = golang_naming.function_name(
            Identifier(f"new_{named_union.name}_from_{root.name}")
        )

        from_methods.append(
            Stripped(
                f"""\
// Wrap `that` as an instance of [{name}].
func {from_method_name}(that {interface_name}) *{name} {{
{I}return &{name}{{
{II}valueKind: {discriminant_case},
{II}{field_name}: that,
{I}}}
}}"""
            )
        )

    for implementer in named_union.implementers:
        root = named_union.most_specific_root_of(implementer)

        model_type_literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=implementer.name
        )

        from_method_name = golang_naming.function_name(
            Identifier(f"new_{named_union.name}_from_{root.name}")
        )

        from_underlying_cases.append(
            Stripped(
                f"""\
case {model_type_literal}:
{I}return {from_method_name}(
{II}that.({golang_naming.interface_name(root.name)}),
{I})"""
            )
        )

    discriminant_cases_joined = "\n".join(discriminant_cases)
    field_decls_joined = "\n".join(field_decls)
    underlying_cases_joined = "\n".join(underlying_cases)
    from_methods_joined = "\n\n".join(from_methods)
    from_underlying_cases_joined = "\n".join(from_underlying_cases)

    from_underlying_name = golang_naming.function_name(
        Identifier(f"{named_union.name}_from_underlying")
    )

    return Stripped(
        f"""\
type {value_kind} int

const (
{I}{indent_but_first_line(discriminant_cases_joined, I)}
)

// Represent a union of {crefs_joined}.
type {name} struct {{
{I}valueKind {value_kind}
{I}{indent_but_first_line(field_decls_joined, I)}
}}

{from_methods_joined}

// Get the underlying instance regardless of the concrete case.
func ({receiver} *{name}) Underlying() IClass {{
{I}switch {receiver}.valueKind {{
{I}{indent_but_first_line(underlying_cases_joined, I)}
{I}default:
{II}panic(
{III}fmt.Sprintf(
{IIII}"Unexpected value kind: %v",
{IIII}{receiver}.valueKind,
{III}),
{II})
{I}}}
}}

// Wrap `that` as an instance of [{name}] based on its run-time type.
func {from_underlying_name}(that IClass) *{name} {{
{I}switch that.ModelType() {{
{I}{indent_but_first_line(from_underlying_cases_joined, I)}
{I}default:
{II}panic(
{III}fmt.Sprintf(
{IIII}"Unexpected run-time type for the union {name}: %T",
{IIII}that,
{III}),
{II})
{I}}}
}}

// Wrap `that` as an instance of [{name}] based on its run-time type.
//
// This is the method-level counterpart of [{from_underlying_name}], needed
// so that a generic function constrained to a self-referential union
// interface can re-wrap a transformed value without knowing the concrete
// union type at compile time.
func ({receiver} *{name}) WithUnderlying(that IClass) *{name} {{
{I}return {from_underlying_name}(that)
}}"""
    )


def _generate_json_aliases(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the aliases of the JSON-able types, if the model uses them.

    They live here, next to the structs whose fields are typed with them:
    a field's type belongs to the types package, and every other package
    already imports it.

    All three are nilable on their own, so an optional one needs no pointer --
    see :py:func:`aas_core_codegen.golang.pointering.is_pointer_type`.
    """
    if not intermediate_uses.json_types(symbol_table):
        return []

    return [
        Stripped(
            """\
// Represent a value which JSON can carry.
//
// This is, recursively, exactly as JSON itself is defined: a bool, a float64,
// a string, a [JsonArray] of JSON-able values or a [JsonObject] of JSON-able
// values with string keys -- never a nil, and never an infinity or
// a not-a-number, which JSON can not represent at all.
//
// Go has no sum type, so this is an `any`, and what it actually holds is
// checked at run-time -- by the verification, and again by the de/serialization.
type JsonValue = interface{}"""
        ),
        Stripped(
            """\
// Represent a JSON-able value which is known to be an array.
type JsonArray = []JsonValue"""
        ),
        Stripped(
            """\
// Represent a JSON-able value which is known to be an object.
type JsonObject = map[string]JsonValue"""
        ),
    ]


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
    symbol_table: VerifiedIntermediateSymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
    spec_impls: specific_implementations.SpecificImplementations,
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code of the data structures representing the meta-model."""
    errors: List[Error] = []

    common_url_literal = golang_common.string_literal(f"{repo_url}/common")

    blocks: List[Stripped] = []

    package_description_comment = golang_description.documentation_comment(
        Stripped(
            """\
Package types provides the data structures corresponding to the meta-model."""
        )
    )

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
            blocks.append(
                Stripped(
                    f"""\
{package_description_comment}
//
{comment}
package types"""
                )
            )
    else:
        blocks.append(
            Stripped(
                f"""\
{package_description_comment}
package types"""
            )
        )

    model_type_getter = golang_naming.getter_name(Identifier("model_type"))
    model_type_enum = golang_naming.enum_name(Identifier("Model_type"))

    blocks.extend(
        [
            golang_common.WARNING,
            _IMPORT_PLACEHOLDER,
            *_generate_json_aliases(symbol_table=symbol_table),
            _generate_definition_for_model_type(symbol_table=symbol_table),
            Stripped(
                f"""\
// Represent the most general interface of the meta-model.
type IClass interface {{
{I}// Return the concrete model type at run-time.
{I}//
{I}// Use the model type if you want to switch on the concrete model type
{I}// in efficient manner, as the compiler will most probably implement
{I}// the switch in form of a jump table.
{I}{model_type_getter}() {model_type_enum}

{I}// Apply the action on the instances referenced from this instance.
{I}//
{I}// If any of the actions returns abort `true`, the descent is immediately
{I}// stopped, and abort `true` is also returned. Otherwise, return abort `false`.
{I}//
{I}// We do not recurse into the referenced instances.
{I}//
{I}// The action is not applied on this instance.
{I}DescendOnce(action func(IClass) bool) (abort bool)

{I}// Apply the action recursively on the instances referenced from this instance.
{I}//
{I}// If any of the actions returns abort `true`, the descent is immediately
{I}// stopped, and abort `true` is also returned. Otherwise, return abort `false`.
{I}//
{I}// The action is not applied on this instance.
{I}Descend(action func(IClass) bool) (abort bool)
}}"""
            ),
        ]
    )

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            block, error = _generate_enum(enum=our_type)
            if error is not None:
                errors.append(error)
                continue
            else:
                assert block is not None
                blocks.append(block)
                blocks.append(_literals_of_enum(enum=our_type))

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin):
            # We do not generate the constrained primitives as types. We only
            # consider them in the verification.
            continue

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            block, error = _generate_interface(cls=our_type)
            if error is not None:
                errors.append(error)
            else:
                assert block is not None
                blocks.append(block)

            block, error = _generate_is_interface(
                cls=our_type, symbol_table=symbol_table
            )
            if error is not None:
                errors.append(error)
            else:
                assert block is not None
                blocks.append(block)

            if isinstance(our_type, intermediate.ConcreteClass):
                block = _generate_struct(cls=our_type)
                blocks.append(block)

                methods, error = _generate_struct_methods(
                    cls=our_type,
                    spec_impls=spec_impls,
                    type_inference=type_inference,
                )
                if error is not None:
                    errors.append(error)
                else:
                    assert methods is not None
                    blocks.extend(methods)
        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(_generate_named_union_struct(named_union=our_type))

        else:
            # noinspection PyTypeChecker
            assert_never(our_type)

    observed_monikers: Set[str] = set()

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            descendability = intermediate.map_descendability(prop.type_annotation)

            for type_anno, descendable in descendability.items():
                if not descendable or not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ):
                    continue

                moniker = golang_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)

                blocks.append(
                    _generate_descend_into_container(
                        type_anno=type_anno, descendability=descendability
                    )
                )

    if len(errors) > 0:
        return None, errors

    blocks.append(golang_common.WARNING)

    import_index = blocks.index(_IMPORT_PLACEHOLDER)

    import_lines: List[str] = []
    if golang_common.names_package(blocks, "fmt"):
        import_lines.append(f'{I}"fmt"')

    # NOTE (mristin):
    # We transpile ``str.lstrip``, ``str.rstrip``, ``str.startswith`` and
    # ``str.endswith`` in the methods to ``strings.TrimLeft``,
    # ``strings.TrimRight``, ``strings.HasPrefix`` and ``strings.HasSuffix``,
    # respectively.
    if golang_common.names_package(blocks, "strings"):
        import_lines.append(f'{I}"strings"')

    if golang_common.names_package(blocks, "ourcommon"):
        import_lines.append(f"{I}ourcommon {common_url_literal}")

    if len(import_lines) == 0:
        del blocks[import_index]
    else:
        blocks[import_index] = Stripped("import (\n" + "\n".join(import_lines) + "\n)")

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
