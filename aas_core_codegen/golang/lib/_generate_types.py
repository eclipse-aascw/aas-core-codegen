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
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    description as golang_description,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
)


# region Checks


def _human_readable_identifier(
    something: Union[
        intermediate.Enumeration,
        intermediate.AbstractClass,
        intermediate.ConcreteClass,
        intermediate.EnumerationLiteral,
    ]
) -> str:
    """
    Represent ``something`` in a human-readable text.

    The reader should be able to trace ``something`` back to the meta-model.
    """
    # NOTE (mristin, 2023-03-29):
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
    else:
        # noinspection PyTypeChecker
        assert_never(something)

    assert result is not None
    return result


def _verify_intra_structure_collisions(
    our_type: intermediate.OurType,
) -> Optional[Error]:
    """Verify that no member names collide in the Golang structure of our type."""
    errors = []  # type: List[Error]

    if isinstance(our_type, intermediate.Enumeration):
        # NOTE (mristin, 2023-03-29):
        # We already checked for collisions of enumeration literals in
        # the inter-structure collision checks.
        pass
    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        pass

    elif isinstance(our_type, intermediate.Class):
        observed_member_names = {}  # type: Dict[Identifier, str]

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

        observed_constructor_arg_names = {}  # type: Dict[Identifier, str]
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

            observed_method_arg_names = {}  # type: Dict[Identifier, str]
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
        ],
    ] = dict()

    errors = []  # type: List[Error]

    # region Inter-structure collisions

    # noinspection PyTypeChecker
    for enum_or_cls in itertools.chain(symbol_table.enumerations, symbol_table.classes):
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
        else:
            # noinspection PyTypeChecker
            assert_never(enum_or_cls)

        for name in names:
            other = observed_structure_names.get(name, None)

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

    # NOTE (mristin, 2023-03-29):
    # Enumeration literals are global constants in Go, so we have to consider them
    # for collisions as well.
    for enum in symbol_table.enumerations:
        for literal in enum.literals:
            name = golang_naming.enum_literal_name(enum.name, literal.name)

            other = observed_structure_names.get(name, None)

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
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given enumeration literal."""
    # NOTE (mristin, 2023-03-29):
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
    # NOTE (mristin, 2023-03-29):
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

            # NOTE (mristin, 2023-03-29):
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

    literal_specs = []  # type: List[Stripped]
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


def _generate_descend_body(
    cls: intermediate.ConcreteClass, recurse: bool, receiver: Identifier
) -> Stripped:
    """
    Generate the body of the `descend and descend-once methods.
    """
    blocks = []  # type: List[Stripped]

    generator_for_loop_variables = golang_common.GeneratorForLoopVariables()

    for prop in cls.properties:
        prop_name = golang_naming.private_property_name(prop.name)

        prop_blocks = []  # type: List[Stripped]

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            continue
        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                continue
            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                continue
            elif isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                prop_blocks.append(
                    Stripped(
                        f"""\
abort = action(
{I}{receiver}.{prop_name},
)
if abort {{
{I}return
}}"""
                    )
                )

                if recurse:
                    prop_blocks.append(
                        Stripped(
                            f"""\
abort = {receiver}.{prop_name}.Descend(
{I}action,
)
if abort {{
{I}return
}}"""
                        )
                    )

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"NOTE (mristin): We currently generate only the code to descend into "
                f"lists of atomic values, but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

            if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
                continue

            elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                if isinstance(
                    type_anno.items.our_type,
                    (intermediate.Enumeration, intermediate.ConstrainedPrimitive),
                ):
                    continue

                elif isinstance(
                    type_anno.items.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    loop_var = next(generator_for_loop_variables)

                    if not recurse:
                        prop_blocks.append(
                            Stripped(
                                f"""\
for _, {loop_var} := range {receiver}.{prop_name} {{
{I}abort = action({loop_var});
{I}if abort {{
{II}return
{I}}}
}}"""
                            )
                        )
                    else:
                        prop_blocks.append(
                            Stripped(
                                f"""\
for _, {loop_var} := range {receiver}.{prop_name} {{
{I}abort = action({loop_var});
{I}if abort {{
{II}return
{I}}}

{I}abort = {loop_var}.Descend(
{II}action,
{I});
{I}if abort {{
{II}return
{I}}}
}}"""
                            )
                        )

                else:
                    # noinspection PyTypeChecker
                    assert_never(type_anno.items)
            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.items)

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            for i, item_type_anno in enumerate(type_anno.items):
                if not (
                    isinstance(item_type_anno, intermediate.OurTypeAnnotation)
                    and isinstance(
                        item_type_anno.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    )
                ):
                    continue

                item_expr = f"{receiver}.{prop_name}.Item{i + 1}"

                prop_blocks.append(
                    Stripped(
                        f"""\
abort = action(
{I}{item_expr},
)
if abort {{
{I}return
}}"""
                    )
                )

                if recurse:
                    prop_blocks.append(
                        Stripped(
                            f"""\
abort = {item_expr}.Descend(
{I}action,
)
if abort {{
{I}return
}}"""
                        )
                    )

            if len(prop_blocks) == 0:
                continue

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

        block = Stripped("\n".join(prop_blocks))
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            block = Stripped(
                f"""\
if {receiver}.{prop_name} != nil {{
{I}{indent_but_first_line(block, I)}
}}"""
            )

        blocks.append(block)

    if len(blocks) == 0:
        blocks.append(Stripped("// No descendable properties"))

    blocks.append(Stripped("return"))

    return Stripped("\n\n".join(blocks))


def _generate_descend_once_method(
    cls: intermediate.ConcreteClass, receiver: Identifier
) -> Stripped:
    """Generate the descend-once method for the concrete class ``cls``."""
    body = _generate_descend_body(cls=cls, recurse=False, receiver=receiver)

    struct_name = golang_naming.struct_name(cls.name)

    return Stripped(
        f"""\
// Apply the action on the instances referenced from {receiver}.
//
// If any of the actions returns abort `true`, the descent is immediately
// stopped,  and abort `true` is also returned. Otherwise, return abort `false`.
//
// We do not recurse into the referenced instances.
//
// The action is not applied on {receiver}.
func ({receiver} *{struct_name}) DescendOnce(
{I}action func(IClass) bool,
) (abort bool) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_descend_method(
    cls: intermediate.ConcreteClass, receiver: Identifier
) -> Stripped:
    """Generate the recursive ``descend`` method for the concrete class ``cls``."""
    body = _generate_descend_body(cls=cls, recurse=True, receiver=receiver)

    struct_name = golang_naming.struct_name(cls.name)

    return Stripped(
        f"""\
// Apply the action recursively on the instances referenced from {receiver}.
//
// If any of the actions returns abort `true`, the descent is immediately
// stopped,  and abort `true` is also returned. Otherwise, return abort `false`.
//
// The action is not applied on {receiver}.
func ({receiver} *{struct_name}) Descend(
{I}action func(IClass) bool,
) (abort bool) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


@require(lambda cls: not cls.is_implementation_specific)
@require(lambda cls: not cls.constructor.is_implementation_specific)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_constructor(
    cls: intermediate.ClassUnion,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the constructor function for the given concrete class ``cls``."""
    property_names = [prop.name for prop in cls.properties]
    constructor_argument_names = [arg.name for arg in cls.constructor.arguments]

    # fmt: off
    assert (
            set(prop.name for prop in cls.properties)
            == set(arg.name for arg in cls.constructor.arguments)
    ), (
        f"Expected the properties to coincide with constructor arguments, "
        f"but they do not for {cls.name!r}:"
        f"{property_names=}, {constructor_argument_names=}"
    )
    # fmt: on

    # NOTE (mristin, 2023-03-31):
    # Golang is peculiar, so we do not transpile the in-lined statements, but simply set
    # the required properties to argument values and optional values to default argument
    # values, if any were specified.
    #
    # It is not clear at this moment whether the SDK clients would really appreciate
    # the added complexity of the code, so we wait till we get some feedback on it.

    blocks = []  # type: List[str]

    struct_specs = []  # type: List[Stripped]

    for arg in cls.constructor.arguments:
        if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        arg_name = golang_naming.argument_name(arg.name)
        private_prop_name = golang_naming.private_property_name(arg.name)

        struct_specs.append(Stripped(f"{private_prop_name}: {arg_name}"))

        if arg.default is not None:
            return None, Error(
                arg.default.parsed.node,
                f"(mristin, 2023-03-31): "
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

        # NOTE (mristin, 2023-03-31):
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
{private_prop_name}: aascommon.NewBool(
{I}{literal}
)"""
                    )
                )
            elif isinstance(arg.default.value, int):
                literal = Stripped(str(arg.default.value))
                struct_specs.append(
                    Stripped(
                        f"""\
{private_prop_name}: aascommon.NewInt64(
{I}{literal}
)"""
                    )
                )
            elif isinstance(arg.default.value, float):
                literal = golang_common.float_literal(arg.default.value)
                struct_specs.append(
                    Stripped(
                        f"""\
{private_prop_name}: aascommon.NewFloat64(
{I}{literal}
)"""
                    )
                )
            elif isinstance(arg.default.value, str):
                literal = golang_common.string_literal(arg.default.value)
                struct_specs.append(
                    Stripped(
                        f"""\
{private_prop_name}: aascommon.NewString(
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
            enum_name = golang_naming.enum_name(arg.default.enumeration.name)
            struct_specs.append(
                Stripped(
                    f"""\
{private_prop_name}: (*{enum_name})(
{I}aascommon.NewInt(
{II}int({literal})
{I})
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

    arg_codes = []  # type: List[str]
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


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_interface(
    cls: intermediate.ClassUnion,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the Golang code of the interface corresponding to ``cls``."""
    # Code blocks separated by double newlines and indented once
    blocks = []  # type: List[Stripped]

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

        prop_comment = None  # type: Optional[Stripped]
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
        method_blocks = []  # type: List[Stripped]

        if method.description is not None:
            (
                method_comment,
                method_comment_errors,
            ) = golang_description.generate_comment_for_signature(
                method.description,
                context=golang_description.Context(
                    package=golang_common.TYPES_PACKAGE, cls_or_enum=cls
                ),
            )

            if method_comment_errors is not None:
                return None, Error(
                    method.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for method {method.name!r}",
                    method_comment_errors,
                )

            assert method_comment is not None

            method_blocks.append(method_comment)

        # fmt: off
        # noinspection PyTypeChecker
        returns = (
            f" {golang_common.generate_type(type_annotation=method.returns)}"
            if method.returns is not None else ""
        )
        # fmt: on

        arg_codes = []  # type: List[Stripped]
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

    comment = None  # type: Optional[Stripped]
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
        case_statements = []  # type: List[Stripped]

        for another_cls in symbol_table.concrete_classes:
            model_type_literal = golang_naming.enum_literal_name(
                Identifier("Model_type"), another_cls.name
            )

            if id(another_cls) in cls.concrete_descendant_id_set or another_cls is cls:
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
// Check whether the instance corresponds to [aastypes.{interface_name}]
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


@require(lambda cls: not cls.is_implementation_specific)
def _generate_struct(cls: intermediate.ConcreteClass) -> Stripped:
    blocks = []  # type: List[Stripped]

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


@require(lambda cls: not cls.is_implementation_specific)
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_struct_methods(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[Stripped]], Optional[Error]]:
    """Generate the Golang methods for the struct corresponding to ``cls``."""
    methods = []  # type: List[Stripped]

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

    errors = []  # type: List[Error]

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
        else:
            errors.append(
                Error(
                    cls.parsed.node,
                    "(mristin, 2023-03-31) "
                    "At the moment, we do not transpile the method body and "
                    "its contracts. We want to finish the meta-model for the V3, "
                    "fix de/serialization and generate SDKs for a couple of languages "
                    "before taking on this rather hard task.",
                )
            )

    methods.append(_generate_descend_once_method(cls=cls, receiver=receiver))

    methods.append(_generate_descend_method(cls=cls, receiver=receiver))

    # endregion

    # region Constructor

    if cls.constructor.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"Types/{cls.name}/{cls.name}.go"
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
            methods.append(implementation)
    else:
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
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code of the data structures representing the meta-model."""
    errors = []  # type: List[Error]

    common_url_literal = golang_common.string_literal(f"{repo_url}/common")

    blocks = []  # type: List[Stripped]

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
            Stripped(
                f"""\
import (
{I}aascommon {common_url_literal}
)"""
            ),
            _generate_definition_for_model_type(symbol_table=symbol_table),
            Stripped(
                f"""\
// Represent the most general interface of an AAS model.
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
{I}// stopped,  and abort `true` is also returned. Otherwise, return abort `false`.
{I}//
{I}// We do not recurse into the referenced instances.
{I}//
{I}// The action is not applied on this instance.
{I}DescendOnce(action func(IClass) bool) (abort bool)

{I}// Apply the action recursively on the instances referenced from this instance.
{I}//
{I}// If any of the actions returns abort `true`, the descent is immediately
{I}// stopped,  and abort `true` is also returned. Otherwise, return abort `false`.
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
            # NOTE (mristin, 2023-03-31):
            # We do not generate the constrained primitives as types. We only
            # consider them in the verification.
            continue

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Types/{our_type.name}.go"
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
                        cls=our_type, spec_impls=spec_impls
                    )
                    if error is not None:
                        errors.append(error)
                    else:
                        assert methods is not None
                        blocks.extend(methods)
        else:
            # noinspection PyTypeChecker
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    blocks.append(golang_common.WARNING)

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
