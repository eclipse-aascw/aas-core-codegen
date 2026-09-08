"""Generate code of the data structures representing the meta-model."""

import io
import textwrap
from typing import (
    cast,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen import specific_implementations
from aas_core_codegen.common import (
    assert_never,
    Error,
    Identifier,
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.java import (
    common as java_common,
    description as java_description,
    naming as java_naming,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import (
    construction as intermediate_construction,
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
    """Verify that no member names collide in the Java structure of our type."""
    errors = []  # type: List[Error]

    if isinstance(our_type, intermediate.Enumeration):
        pass

    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        pass

    elif isinstance(our_type, intermediate.Class):
        observed_member_names = {}  # type: Dict[Identifier, str]

        for prop in our_type.properties:
            prop_name = java_naming.property_name(prop.name)
            if prop_name in observed_member_names:
                # BEFORE-RELEASE (mristin, 2021-12-13): test
                errors.append(
                    Error(
                        prop.parsed.node,
                        f"Java property {prop_name!r} corresponding "
                        f"to the meta-model property {prop.name!r} collides with "
                        f"the {observed_member_names[prop_name]}",
                    )
                )
            else:
                observed_member_names[prop_name] = (
                    f"Java property {prop_name!r} corresponding to "
                    f"the meta-model property {prop.name!r}"
                )

        observed_constructor_arg_names = {}  # type: Dict[Identifier, str]
        for constructor_arg in our_type.constructor.arguments:
            arg_name = java_naming.argument_name(constructor_arg.name)

            if arg_name in observed_constructor_arg_names:
                errors.append(
                    Error(
                        constructor_arg.parsed.node,
                        f"Java argument {arg_name!r} corresponding "
                        f"to the meta-model constructor argument {constructor_arg.name!r} "
                        f"collides with the {observed_constructor_arg_names[arg_name]}",
                    )
                )
            else:
                observed_constructor_arg_names[arg_name] = (
                    f"Java argument {arg_name!r} corresponding to "
                    f"the meta-model constructor argument {constructor_arg.name!r}"
                )

        for method in our_type.methods:
            method_name = java_naming.method_name(method.name)

            if method_name in observed_member_names:
                # BEFORE-RELEASE (mristin, 2021-12-13): test
                errors.append(
                    Error(
                        method.parsed.node,
                        f"Java method {method_name!r} corresponding "
                        f"to the meta-model method {method.name!r} collides with "
                        f"the {observed_member_names[method_name]}",
                    )
                )
            else:
                observed_member_names[method_name] = (
                    f"Java method {method_name!r} corresponding to "
                    f"the meta-model method {method.name!r}"
                )

            observed_method_arg_names = {}  # type: Dict[Identifier, str]
            for arg in method.arguments:
                arg_name = java_naming.argument_name(arg.name)

                if arg_name in observed_method_arg_names:
                    errors.append(
                        Error(
                            arg.parsed.node,
                            f"Java argument {arg_name!r} corresponding "
                            f"to the meta-model method argument {arg.name!r} "
                            f"of the method {method.name} "
                            f"collides with the {observed_method_arg_names[arg_name]}",
                        )
                    )
                else:
                    observed_method_arg_names[arg_name] = (
                        f"Java argument {arg_name!r} corresponding to "
                        f"the meta-model method argument {arg.name!r}"
                    )

    else:
        assert_never(our_type)

    if len(errors) > 0:
        return Error(
            our_type.parsed.node,
            f"Naming collision(s) in Java code for our type {our_type.name!r}",
            underlying=errors,
        )

    return None


def _verify_structure_name_collisions(
    symbol_table: intermediate.SymbolTable,
) -> List[Error]:
    """Verify that the Java names of the structures do not collide."""
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

        if isinstance(our_type, intermediate.Enumeration):
            name = java_naming.enum_name(our_type.name)
            other = observed_structure_names.get(name, None)

            if other is not None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"The Java name {name!r} for the enumeration {our_type.name!r} "
                        f"collides with the same Java name "
                        f"coming from the {_human_readable_identifier(other)}",
                    )
                )
            else:
                observed_structure_names[name] = our_type

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            interface_name = java_naming.interface_name(our_type.name)

            other = observed_structure_names.get(interface_name, None)

            if other is not None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"The Java name {interface_name!r} of the interface "
                        f"for the class {our_type.name!r} "
                        f"collides with the same Java name "
                        f"coming from the {_human_readable_identifier(other)}",
                    )
                )
            else:
                observed_structure_names[interface_name] = our_type

            if isinstance(our_type, intermediate.ConcreteClass):
                class_name = java_naming.class_name(our_type.name)

                other = observed_structure_names.get(class_name, None)

                if other is not None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The Java name {class_name!r} "
                            f"for the class {our_type.name!r} "
                            f"collides with the same Java name "
                            f"coming from the {_human_readable_identifier(other)}",
                        )
                    )
                else:
                    observed_structure_names[class_name] = our_type
        else:
            assert_never(our_type)

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
    """Verify that Java code can be generated from the ``symbol_table``."""

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


def _has_descendable_properties(cls: intermediate.Class) -> bool:
    for prop in cls.properties:
        descendability = intermediate.map_descendability(
            type_annotation=prop.type_annotation
        )

        if descendability[prop.type_annotation]:
            return True

    return False


def _generate_descend_body(cls: intermediate.ConcreteClass, recurse: bool) -> Stripped:
    """Generate the iterator function body for recursive and non-recursive descend methods.

    We leverage lazily evaluated streams to iterate over the object stream one by one.
    """
    class_name = java_naming.class_name(cls.name)

    blocks = [
        Stripped("Stream<IClass> memberStream = Stream.empty();")
    ]  # type: List[Stripped]

    # region Streams

    for prop in cls.properties:
        descendability = intermediate.map_descendability(
            type_annotation=prop.type_annotation
        )

        if not descendability[prop.type_annotation]:
            continue

        prop_expr = None  # type: Optional[Stripped]

        prop_name = java_naming.property_name(prop.name)

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
                if not descendability[type_anno] or not recurse:
                    prop_expr = Stripped(
                        f"Stream.<IClass>of({class_name}.this.{prop_name})"
                    )
                else:
                    prop_expr = Stripped(
                        f"""\
Stream.concat(Stream.<IClass>of({class_name}.this.{prop_name}),
{I}StreamSupport.stream({class_name}.this.{prop_name}.descend().spliterator(), false))"""
                    )
            else:
                assert_never(type_anno.our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.OurTypeAnnotation
            ) and isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ), (
                f"We expect only list of classes "
                f"at the moment, but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

            if not recurse:
                prop_expr = Stripped(f"{class_name}.this.{prop_name}.stream()")
            else:
                prop_expr = Stripped(
                    f"""\
{class_name}.this.{prop_name}.stream()
{I}.flatMap(item -> Stream.concat(Stream.<IClass>of(item),
{II}StreamSupport.stream(item.descend().spliterator(), false)))"""
                )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_stream_exprs = []  # type: List[Stripped]

            for i, item_type_anno in enumerate(type_anno.items):
                if not descendability.get(item_type_anno, False):
                    continue

                assert isinstance(
                    item_type_anno, intermediate.OurTypeAnnotation
                ) and isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ), (
                    f"We expect only atomic values (primitives, constrained "
                    f"primitives, enumeration literals) or classes as items "
                    f"of a tuple at the moment, but you specified {type_anno}. "
                    f"Please contact the developers if you need this feature."
                )

                item_access = Stripped(f"{class_name}.this.{prop_name}.item{i + 1}()")

                if not recurse:
                    item_stream_exprs.append(
                        Stripped(f"Stream.<IClass>of({item_access})")
                    )
                else:
                    item_stream_exprs.append(
                        Stripped(
                            f"""\
Stream.concat(Stream.<IClass>of({item_access}),
{I}StreamSupport.stream({item_access}.descend().spliterator(), false))"""
                        )
                    )

            assert len(item_stream_exprs) > 0, (
                "Expected at least one descendable item, since the property "
                "has been determined to be descendable"
            )

            prop_expr = item_stream_exprs[0]
            for item_stream_expr in item_stream_exprs[1:]:
                prop_expr = Stripped(
                    f"""\
Stream.concat(
{I}{indent_but_first_line(prop_expr, I)},
{I}{indent_but_first_line(item_stream_expr, I)})"""
                )

        else:
            assert_never(type_anno)

        stream_stmt = Stripped(
            f"""\
if ({prop_name} != null) {{
{I}memberStream = Stream.concat(memberStream,
{II}{indent_but_first_line(prop_expr, II)});
}}"""
        )

        blocks.append(stream_stmt)

    # endregion

    blocks.append(Stripped("return memberStream;"))

    return Stripped("\n\n".join(blocks))


def _generate_descend_iterable(
    cls: intermediate.ConcreteClass, recursive: bool
) -> Stripped:
    """Generate the iterator for the descend method."""

    cls_name = java_naming.class_name(cls.name)

    iterable_name: Stripped

    if recursive:
        iterable_name = Stripped(f"_{cls_name}RecursiveIterable")
    else:
        iterable_name = Stripped(f"_{cls_name}Iterable")

    iterable_body = _generate_descend_body(cls, recursive)

    iterable = Stripped(
        f"""\
private class {iterable_name} implements Iterable<IClass> {{
{I}@Override
{I}public Iterator<IClass> iterator() {{
{II}Stream<IClass> stream = stream();

{II}return stream.iterator();
{I}}}

{I}@Override
{I}public void forEach(Consumer<? super IClass> action) {{
{II}Stream<IClass> stream = stream();

{II}stream.forEach(action);
{I}}}

{I}@Override
{I}public Spliterator<IClass> spliterator() {{
{II}Stream<IClass> stream = stream();

{II}return stream.spliterator();
{I}}}

{I}private Stream<IClass> stream() {{
{II}{indent_but_first_line(iterable_body, II)}
{I}}}
}}"""
    )

    return iterable


def _generate_descend_method(
    cls: intermediate.ConcreteClass, descendable: bool
) -> Stripped:
    """Generate the recursive ``Descend`` method for the concrete class ``cls``."""

    cls_name = java_naming.class_name(cls.name)

    iterable_name = Stripped(f"_{cls_name}RecursiveIterable")

    descend_body: Stripped

    if descendable:
        descend_body = Stripped(f"return new {iterable_name}();")
    else:
        descend_body = Stripped("return Collections.emptyList();")

    return Stripped(
        f"""\
/**
 * Iterate recursively over all the class instances referenced from this instance.
 */
public Iterable<IClass> descend() {{
{I}{descend_body}
}}"""
    )


def _generate_descend_once_method(
    cls: intermediate.ConcreteClass, descendable: bool
) -> Stripped:
    """Generate the recursive ``Descend`` method for the concrete class ``cls``."""

    cls_name = java_naming.class_name(cls.name)

    iterable_name = Stripped(f"_{cls_name}Iterable")

    descend_body: Stripped
    if descendable:
        descend_body = Stripped(f"return new {iterable_name}();")
    else:
        descend_body = Stripped("return Collections.emptyList();")

    return Stripped(
        f"""\
/**
 * Iterate over all the class instances referenced from this instance.
 */
public Iterable<IClass> descendOnce() {{
{I}{descend_body}
}}"""
    )


def _generate_imports_for_interface(
    cls: intermediate.ClassUnion,
    package: java_common.PackageIdentifier,
) -> Stripped:
    """
    Generate necessary Java Platform imports for the given class ``cls``.

    The ``package`` defines the root Java package.
    """
    imports = [
        Stripped(f"{package}.common.*"),
        Stripped(f"{package}.types.enums.*"),
        Stripped(f"{package}.types.impl.*"),
        Stripped(f"{package}.types.model.*"),
        Stripped("java.util.List"),
    ]  # type: List[Stripped]

    if len(cls.inheritances) == 0:
        import_name = Stripped(f"{package}.types.{java_common.INTERFACE_PKG}.IClass")
        imports.append(import_name)
    else:
        for inheritance in cls.inheritances:
            super_name = java_naming.interface_name(inheritance.name)

            import_name = Stripped(
                f"{package}.types.{java_common.INTERFACE_PKG}.{super_name}"
            )

            imports.append(import_name)

    if any(prop for prop in cls.properties if prop.specified_for is cls):
        imports.append(Stripped("java.util.Optional"))

    return Stripped("\n".join(map(lambda imp: f"import {imp};", imports)))


def _generate_imports_for_class(
    cls: intermediate.Class,
    package: java_common.PackageIdentifier,
) -> Stripped:
    """
    Generate necessary Java Platform imports for the given class ``cls``.

    The ``package`` defines the root Java package.
    """
    if cls.is_implementation_specific:
        return Stripped("")

    imports = [
        Stripped(f"{package}.common.*"),
        Stripped(f"{package}.visitation.IVisitor"),
        Stripped(f"{package}.visitation.IVisitorWithContext"),
        Stripped(f"{package}.visitation.ITransformer"),
        Stripped(f"{package}.visitation.ITransformerWithContext"),
        Stripped(f"{package}.types.enums.*"),
        Stripped(f"{package}.types.impl.*"),
        Stripped(f"{package}.types.model.*"),
        Stripped("java.util.Collections"),
        Stripped("java.util.List"),
        Stripped("java.util.Optional"),
        Stripped("java.util.Objects"),
    ]  # type: List[Stripped]

    if _has_descendable_properties(cls):
        imports.extend(
            [
                Stripped("java.util.Iterator"),
                Stripped("java.util.Spliterator"),
                Stripped("java.util.function.Consumer"),
                Stripped("java.util.stream.Stream"),
                Stripped("java.util.stream.StreamSupport"),
            ]
        )

    interface_name = java_naming.interface_name(cls.name)

    interface_import = Stripped(
        f"{package}.types.{java_common.INTERFACE_PKG}.{interface_name}"
    )

    imports.append(interface_import)

    if any(prop for prop in cls.properties if prop.specified_for is cls):
        imports.extend(
            [
                Stripped("java.util.Collections"),
                Stripped("java.util.List"),
                Stripped("java.util.Objects"),
            ]
        )

    return Stripped("\n".join(map(lambda imp: f"import {imp};", imports)))


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_interface(
    cls: intermediate.ClassUnion, package: java_common.PackageIdentifier
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate Java interface for the given class ``cls``.

    The ``package`` defines the root Java package.
    """
    writer = io.StringIO()

    if cls.description is not None:
        comment, comment_errors = java_description.generate_comment_for_our_type(
            description=cls.description,
            context=java_description.Context(package=package, cls_or_enum=cls),
        )

        if comment_errors is not None:
            return None, Error(
                cls.description.parsed.node,
                "Failed to generate the documentation comment",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    name = java_naming.interface_name(cls.name)

    inheritances = [inheritance.name for inheritance in cls.inheritances]
    if len(inheritances) == 0:
        inheritances = [Identifier("Class")]

    inheritance_names = list(map(java_naming.interface_name, inheritances))

    assert len(inheritances) > 0
    if len(inheritances) == 1:
        writer.write(
            f"""\
public interface {name} extends {inheritance_names[0]} {{\n"""
        )
    else:
        writer.write(
            f"""
public interface {name} extends\n"""
        )
        for i, inheritance_name in enumerate(inheritance_names):
            if i > 0:
                writer.write(",\n")

            writer.write(textwrap.indent(inheritance_name, II))

        writer.write(" {\n")

    # Code blocks separated by double newlines and indented once
    blocks = []  # type: List[Stripped]

    # region Getters and setters

    for prop in cls.properties:
        if prop.specified_for is not cls:
            continue

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_type = java_common.generate_type(type_annotation=prop.type_annotation)
        arg_type = java_common.generate_type(type_annotation=type_anno)

        prop_name = java_naming.property_name(prop.name)

        getter_name = java_naming.getter_name(prop.name)
        setter_name = java_naming.setter_name(prop.name)

        if prop.description is not None:
            (
                prop_comment,
                prop_comment_errors,
            ) = java_description.generate_comment_for_property(
                description=prop.description,
                context=java_description.Context(package=package, cls_or_enum=cls),
            )

            if prop_comment_errors is not None:
                return None, Error(
                    prop.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for the property {prop.name!r}",
                    prop_comment_errors,
                )

            blocks.append(Stripped(f"{prop_comment}\n{prop_type} {getter_name}();"))
        else:
            blocks.append(Stripped(f"{prop_type} {getter_name}();"))

        blocks.append(Stripped(f"void {setter_name}({arg_type} {prop_name});"))

    # endregion

    # region Signatures

    for method in cls.methods:
        if method.specified_for is not cls:
            continue

        signature_blocks = []  # type: List[Stripped]

        if method.description is not None:
            (
                signature_comment,
                signature_comment_errors,
            ) = java_description.generate_comment_for_signature(
                description=method.description,
                context=java_description.Context(package=package, cls_or_enum=cls),
            )

            if signature_comment_errors is not None:
                return None, Error(
                    method.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for the method {method.name!r}",
                    signature_comment_errors,
                )

            assert signature_comment is not None

            signature_blocks.append(signature_comment)

        # fmt: off
        returns = (
            java_common.generate_type(type_annotation=method.returns)
            if method.returns is not None else "void"
        )
        # fmt: on

        arg_codes = []  # type: List[Stripped]
        for arg in method.arguments:
            arg_type = java_common.generate_type(type_annotation=arg.type_annotation)
            arg_name = java_naming.argument_name(arg.name)
            arg_codes.append(Stripped(f"{arg_type} {arg_name}"))

        signature_name = java_naming.method_name(method.name)
        if len(arg_codes) > 2:
            arg_block = ",\n".join(arg_codes)
            arg_block_indented = textwrap.indent(arg_block, I)
            signature_blocks.append(
                Stripped(f"{returns} {signature_name}(\n{arg_block_indented});")
            )
        elif len(arg_codes) == 1:
            signature_blocks.append(
                Stripped(f"{returns} {signature_name}({arg_codes[0]});")
            )
        else:
            assert len(arg_codes) == 0
            signature_blocks.append(Stripped(f"{returns} {signature_name}();"))

        blocks.append(Stripped("\n".join(signature_blocks)))

    for prop in cls.properties:
        if prop.specified_for is not cls:
            continue

        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            prop_name = java_naming.property_name(prop.name)
            method_name = f"over{java_naming.class_name(prop.name)}OrEmpty"
            items_type = java_common.generate_type(prop.type_annotation.value.items)
            blocks.append(
                Stripped(
                    f"""\
/**
 * Iterate over {prop_name}, if set, and otherwise return an empty enumerable.
 */
Iterable<{items_type}> {method_name}();"""
                )
            )

    # endregion

    if len(blocks) == 0:
        blocks = [Stripped("// Intentionally empty.")]

    for i, code in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(code, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


@require(lambda cls: not cls.is_implementation_specific)
@require(lambda cls: not cls.constructor.is_implementation_specific)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_mandatory_constructor(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate a default constructor for the given concrete class ``cls``.

    Return empty string if there is an empty constructor or no default constructor
    can be constructed.
    """
    if (
        len(cls.constructor.arguments) == 0
        and len(cls.constructor.inlined_statements) == 0
    ):
        return Stripped(""), None

    if all(
        isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation)
        for arg in cls.constructor.arguments
    ):
        return Stripped(""), None

    cls_name = java_naming.class_name(cls.name)

    blocks = []  # type: List[str]

    arg_codes = []  # type: List[Stripped]
    for arg in cls.constructor.arguments:
        type_anno = arg.type_annotation

        if isinstance(type_anno, intermediate.OptionalTypeAnnotation):
            continue

        arg_type = java_common.generate_type(type_annotation=type_anno)

        arg_name = java_naming.argument_name(arg.name)

        arg_codes.append(Stripped(f"{arg_type} {arg_name}"))

    assert len(arg_codes) > 0

    if len(arg_codes) == 1:
        blocks.append(f"public {cls_name}({arg_codes[0]}) {{")
    else:
        arg_block = ",\n".join(arg_codes)
        arg_block_indented = textwrap.indent(arg_block, I)
        blocks.append(f"public {cls_name}(\n{arg_block_indented}) {{")

    body = []  # type: List[Stripped]

    for stmt in cls.constructor.inlined_statements:
        if isinstance(stmt, intermediate_construction.AssignArgument):
            if stmt.default is None:
                prop_name = java_naming.property_name(stmt.name)

                arg_name = java_naming.argument_name(stmt.argument)

                if isinstance(
                    cls.properties_by_name[stmt.name].type_annotation,
                    intermediate.OptionalTypeAnnotation,
                ):
                    continue

                assignment = Stripped(
                    f"""\
this.{prop_name} = Objects.requireNonNull(
{I}{arg_name},
{I}"Argument \\"{arg_name}\\" must be non-null.");"""
                )

                body.append(assignment)
            else:
                if isinstance(stmt.default, intermediate_construction.EmptyList):
                    prop = cls.properties_by_name[stmt.name]

                    type_anno = intermediate.beneath_optional(prop.type_annotation)

                    prop_type = java_common.generate_type(
                        type_annotation=type_anno,
                    )

                    prop_name = java_naming.property_name(stmt.name)

                    arg_name = java_naming.argument_name(stmt.argument)

                    # Write the assignment as a ternary operator

                    assignment = Stripped(
                        f"""\
this.{prop_name} = ({arg_name} != null)
{I}? {arg_name}
{I}: new {prop_type}();"""
                    )

                    body.append(assignment)
                elif isinstance(
                    stmt.default, intermediate_construction.DefaultEnumLiteral
                ):
                    enum_name = java_naming.enum_name(stmt.default.enum.name)

                    enum_literal = java_naming.enum_literal_name(
                        stmt.default.literal.name
                    )

                    prop_name = java_naming.property_name(stmt.name)

                    arg_name = java_naming.argument_name(stmt.argument)

                    # Write the assignment as a ternary operator

                    body.append(
                        Stripped(
                            f"""\
this.{prop_name} = ({arg_name} != null)
{I}? {arg_name}
{I}: {enum_name}.{enum_literal};"""
                        )
                    )
                else:
                    assert_never(stmt.default)

        else:
            assert_never(stmt)

    blocks.append("\n".join(textwrap.indent(stmt_code, I) for stmt_code in body))

    blocks.append("}")

    return Stripped("\n".join(blocks)), None


@require(lambda cls: not cls.is_implementation_specific)
@require(lambda cls: not cls.constructor.is_implementation_specific)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_full_constructor(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the constructor functions for the given concrete class ``cls``.

    Return empty string if there is an empty constructor.
    """
    if (
        len(cls.constructor.arguments) == 0
        and len(cls.constructor.inlined_statements) == 0
    ):
        return Stripped(""), None

    if not any(
        isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation)
        for arg in cls.constructor.arguments
    ):
        return Stripped(""), None

    cls_name = java_naming.class_name(cls.name)

    blocks = []  # type: List[str]

    arg_codes = []  # type: List[Stripped]
    for arg in cls.constructor.arguments:
        type_anno = intermediate.beneath_optional(arg.type_annotation)

        arg_type = java_common.generate_type(type_annotation=type_anno)

        arg_name = java_naming.argument_name(arg.name)

        arg_codes.append(Stripped(f"{arg_type} {arg_name}"))

    if len(arg_codes) == 0:
        blocks.append(f"public {cls_name}() {{")
    elif len(arg_codes) == 1:
        blocks.append(f"public {cls_name}({arg_codes[0]}) {{")
    else:
        arg_block = ",\n".join(arg_codes)
        arg_block_indented = textwrap.indent(arg_block, I)
        blocks.append(f"public {cls_name}(\n{arg_block_indented}) {{")

    body = []  # type: List[Stripped]

    for stmt in cls.constructor.inlined_statements:
        if isinstance(stmt, intermediate_construction.AssignArgument):
            if stmt.default is None:
                prop_name = java_naming.property_name(stmt.name)

                arg_name = java_naming.argument_name(stmt.argument)

                if isinstance(
                    cls.properties_by_name[stmt.name].type_annotation,
                    intermediate.OptionalTypeAnnotation,
                ):
                    assignment = Stripped(f"this.{prop_name} = {arg_name};")
                else:
                    assignment = Stripped(
                        f"""\
this.{prop_name} = Objects.requireNonNull(
{I}{arg_name},
{I}"Argument \\"{arg_name}\\" must be non-null.");"""
                    )

                body.append(assignment)
            else:
                if isinstance(stmt.default, intermediate_construction.EmptyList):
                    prop = cls.properties_by_name[stmt.name]

                    type_anno = intermediate.beneath_optional(prop.type_annotation)

                    prop_type = java_common.generate_type(
                        type_annotation=type_anno,
                    )

                    prop_name = java_naming.property_name(stmt.name)

                    arg_name = java_naming.argument_name(stmt.argument)

                    # Write the assignment as a ternary operator

                    assignment = Stripped(
                        f"""\
this.{prop_name} = ({arg_name} != null)
{I}? {arg_name}
{I}: new {prop_type}();"""
                    )

                    body.append(assignment)
                elif isinstance(
                    stmt.default, intermediate_construction.DefaultEnumLiteral
                ):
                    enum_name = java_naming.enum_name(stmt.default.enum.name)

                    enum_literal = java_naming.enum_literal_name(
                        stmt.default.literal.name
                    )

                    prop_name = java_naming.property_name(stmt.name)

                    arg_name = java_naming.argument_name(stmt.argument)

                    # Write the assignment as a ternary operator

                    body.append(
                        Stripped(
                            f"""\
this.{prop_name} = ({arg_name} != null)
{I}? {arg_name}
{I}: {enum_name}.{enum_literal};"""
                        )
                    )
                else:
                    assert_never(stmt.default)

        else:
            assert_never(stmt)

    blocks.append("\n".join(textwrap.indent(stmt_code, I) for stmt_code in body))

    blocks.append(Stripped("}"))

    return Stripped("\n".join(blocks)), None


# fmt: off
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
# fmt: on
def _generate_class(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the class ``cls``.

    The ``package`` defines the root Java package.
    """
    # Code blocks to be later joined by double newlines and indented once

    blocks = []  # type: List[Stripped]

    errors = []  # type: List[Error]

    descendable = _has_descendable_properties(cls)

    # region Properties

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_type = java_common.generate_type(type_annotation=type_anno)

        prop_name = java_naming.property_name(prop.name)

        prop_blocks = []  # type: List[Stripped]

        if prop.description is not None:
            (
                prop_comment,
                prop_comment_errors,
            ) = java_description.generate_comment_for_property(
                description=prop.description,
                context=java_description.Context(package=package, cls_or_enum=cls),
            )
            if prop_comment_errors:
                return None, Error(
                    prop.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for the property {prop.name!r}",
                    prop_comment_errors,
                )

            assert prop_comment is not None

            prop_blocks.append(prop_comment)

        prop_blocks.append(
            Stripped(
                f"""\
private {prop_type} {prop_name};"""
            )
        )

        blocks.append(Stripped("\n".join(prop_blocks)))

    # endregion

    # region Methods

    # region Constructor

    if cls.constructor.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"Types/{cls.name}/{cls.name}.java"
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
        mandatory_constructor_block, error = _generate_mandatory_constructor(cls=cls)

        if error is not None:
            errors.append(error)
        else:
            if mandatory_constructor_block != "":
                assert mandatory_constructor_block is not None
                blocks.append(mandatory_constructor_block)

        full_constructor_block, error = _generate_full_constructor(cls=cls)

        if error is not None:
            errors.append(error)
        else:
            if full_constructor_block != "":
                assert full_constructor_block is not None
                blocks.append(full_constructor_block)

    # endregion

    # region Getters and setters

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_type = java_common.generate_type(type_annotation=prop.type_annotation)

        arg_type = java_common.generate_type(type_annotation=type_anno)

        prop_name = java_naming.property_name(prop.name)

        getter_name = java_naming.getter_name(prop.name)
        setter_name = java_naming.setter_name(prop.name)

        get_set_blocks = []  # type: List[Stripped]

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            get_set_blocks.append(
                Stripped(
                    f"""\
@Override
public {prop_type} {getter_name}() {{
{I}return Optional.ofNullable({prop_name});
}}"""
                )
            )

            get_set_blocks.append(
                Stripped(
                    f"""\
@Override
public void {setter_name}({arg_type} {prop_name}) {{
{I}this.{prop_name} = {prop_name};
}}"""
                )
            )
        else:
            get_set_blocks.append(
                Stripped(
                    f"""\
@Override
public {prop_type} {getter_name}() {{
{I}return {prop_name};
}}"""
                )
            )

            get_set_blocks.append(
                Stripped(
                    f"""\
@Override
public void {setter_name}({arg_type} {prop_name}) {{
{I}this.{prop_name} = Objects.requireNonNull(
{II}{prop_name},
{II}"Argument \\"{prop_name}\\" must be non-null.");
}}"""
                )
            )

        blocks.append(Stripped("\n\n".join(get_set_blocks)))

    # endregion

    # region OverXOrEmpty getter

    cls_name = java_naming.class_name(cls.name)

    for prop in cls.properties:
        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            prop_name = java_naming.property_name(prop.name)
            method_name = f"over{java_naming.class_name(prop.name)}OrEmpty"
            getter_name = java_naming.getter_name(prop.name)
            items_type = java_common.generate_type(prop.type_annotation.value.items)

            blocks.append(
                Stripped(
                    f"""\
/**
 * Iterate over {{@link {cls_name}#{prop_name}}}, if set,
 * and otherwise return an empty iterator.
 */
public Iterable<{items_type}> {method_name}() {{
{I}return {getter_name}().orElseGet(Collections::emptyList);
}}"""
                )
            )

    # endregion

    # region Public methods

    for method in cls.methods:
        if isinstance(method, intermediate.ImplementationSpecificMethod):
            implementation_key = specific_implementations.ImplementationKey(
                f"Types/{method.specified_for.name}/{method.name}.java"
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
                    "At the moment, we do not transpile the method body and "
                    "its contracts. We want to finish the meta-model for the V3 and "
                    "fix de/serialization before taking on this rather hard task.",
                )
            )

    visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))

    blocks.append(_generate_descend_method(cls=cls, descendable=descendable))
    blocks.append(_generate_descend_once_method(cls=cls, descendable=descendable))
    blocks.append(
        Stripped(
            f"""\
/**
 * Accept the {{@code visitor}} to visit this instance for double dispatch.
 **/
@Override
public void accept(IVisitor visitor) {{
{I}visitor.{visit_name}(this);
}}"""
        )
    )

    blocks.append(
        Stripped(
            f"""\
/**
 * Accept the {{@code visitor}} to visit this instance for double dispatch
 * with the {{@code context}}.
 **/
@Override
public <ContextT> void accept(
{II}IVisitorWithContext<ContextT> visitor,
{II}ContextT context) {{
{I}visitor.{visit_name}(this, context);
}}"""
        )
    )

    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
/**
 * Accept the {{@code transformer}} to visit this instance for double dispatch.
 **/
@Override
public <T> T transform(ITransformer<T> transformer) {{
{I}return transformer.{transform_name}(this);
}}"""
        )
    )

    blocks.append(
        Stripped(
            f"""\
/**
 * Accept the {{@code transformer}} to visit this instance for double dispatch
 * with the {{@code context}}.
 **/
@Override
public <ContextT, T> T transform(
{II}ITransformerWithContext<ContextT, T> transformer,
{II}ContextT context) {{
{I}return transformer.{transform_name}(this, context);
}}"""
        )
    )

    # endregion

    # endregion

    # region Inner classes

    if descendable:
        blocks.append(_generate_descend_iterable(cls=cls, recursive=False))

        blocks.append(_generate_descend_iterable(cls=cls, recursive=True))

    # endregion

    if len(errors) > 0:
        return None, Error(
            cls.parsed.node,
            f"Failed to generate the code for the class {cls.name}",
            errors,
        )

    interface_name = java_naming.interface_name(cls.name)

    name = java_naming.class_name(cls.name)

    writer = io.StringIO()

    if cls.description is not None:
        comment, comment_errors = java_description.generate_comment_for_our_type(
            description=cls.description,
            context=java_description.Context(package=package, cls_or_enum=cls),
        )
        if comment_errors is not None:
            return None, Error(
                cls.description.parsed.node,
                "Failed to generate the comment description",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    writer.write(
        f"""\
public class {name} implements {interface_name} {{\n"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_enum(
    enum: intermediate.Enumeration, package: java_common.PackageIdentifier
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the enumeration `enum`.

    The ``package`` defines the root Java package.
    """
    writer = io.StringIO()

    if enum.description is not None:
        comment, comment_errors = java_description.generate_comment_for_our_type(
            description=enum.description,
            context=java_description.Context(package=package, cls_or_enum=enum),
        )
        if comment_errors:
            return None, Error(
                enum.description.parsed.node,
                "Failed to generate the documentation comment",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    name = java_naming.enum_name(enum.name)
    if len(enum.literals) == 0:
        writer.write(
            f"""\
public enum {name} {{\n}}"""
        )
        return Stripped(writer.getvalue()), None

    writer.write(
        f"""\
public enum {name} {{\n"""
    )
    for i, literal in enumerate(enum.literals):
        if i > 0:
            writer.write(",\n")

        if literal.description:
            (
                literal_comment,
                literal_comment_errors,
            ) = java_description.generate_comment_for_enumeration_literal(
                description=literal.description,
                context=java_description.Context(package=package, cls_or_enum=enum),
            )

            if literal_comment_errors:
                return None, Error(
                    literal.description.parsed.node,
                    f"Failed to generate the comment "
                    f"for the enumeration literal {literal.name!r}",
                    literal_comment_errors,
                )

            assert literal_comment is not None

            writer.write(textwrap.indent(literal_comment, I))
            writer.write("\n")

        writer.write(
            textwrap.indent(
                f"{java_naming.enum_literal_name(literal.name)}",
                I,
            )
        )

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


@require(lambda file_name: file_name.endswith(".java"))
def _generate_java_file(
    file_name: Stripped,
    imports: Optional[Stripped],
    code: Stripped,
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    writer = io.StringIO()

    writer.write(
        f"""\
{java_common.WARNING}

package {package};\n\n"""
    )

    if imports is not None and len(imports) > 0:
        writer.write(f"{imports}")
        writer.write("\n\n")

    writer.write(
        f"""\
{code}

{java_common.WARNING}
"""
    )

    file_content = writer.getvalue()

    return java_common.JavaFile(file_name, file_content)


def _generate_no_enumerations_defined(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    """
    Generate a placeholder class for the ``types.enums`` package.

    Interfaces and classes always import ``{package}.types.enums.*`` so that
    package must exist even if the meta-model defines no enumerations at all.
    """
    structure_name = Stripped("NoEnumerationsDefined")
    file_name = java_common.enum_package_path(structure_name)
    file_content = f"""\
{java_common.WARNING}

package {package}.types.enums;

/**
 * Represent a placeholder so that this package is not empty.
 *
 * <p>The meta-model defines no enumerations, but the {{@code types.enums}}
 * package is imported unconditionally throughout the generated code, so we
 * need at least one class in it for the import to resolve.
 */
public class NoEnumerationsDefined {{
}}

{java_common.WARNING}
"""

    return java_common.JavaFile(file_name, file_content)


def _generate_iclass(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    structure_name = Stripped("IClass")
    file_name = java_common.interface_package_path(structure_name)
    file_content = f"""\
{java_common.WARNING}

package {package}.types.model;

import {package}.visitation.ITransformer;
import {package}.visitation.ITransformerWithContext;
import {package}.visitation.IVisitor;
import {package}.visitation.IVisitorWithContext;
import java.lang.Iterable;

/**
 * Represent a general class of an AAS model.
 */
public interface IClass {{
{I}/**
{I} * Iterate over all the class instances referenced from this instance
{I} * without further recursion.
{I} */
{I}Iterable<IClass> descendOnce();

{I}/**
{I} * Iterate recursively over all the class instances referenced from this instance.
{I} */
{I}Iterable<IClass> descend();

{I}/**
{I} * Accept the {{@code visitor}} to visit this instance
{I} * for double dispatch.
{I} */
{I}void accept(IVisitor visitor);

{I}/**
{I} * Accept the visitor to visit this instance for double dispatch
{I} * with the {{@code context}}.
{I} */
{I}<ContextT> void accept(
{III}IVisitorWithContext<ContextT> visitor,
{III}ContextT context);

{I}/**
{I} * Accept the {{@code transformer}} to transform this instance
{I} * for double dispatch.
{I} */
{I}<T> T transform(ITransformer<T> transformer);

{I}/**
{I} * Accept the {{@code transformer}} to visit this instance
{I} * for double dispatch with the {{@code context}}.
{I} */
{I}<ContextT, T> T transform(
{III}ITransformerWithContext<ContextT, T> transformer,
{III}ContextT context);
}}

{java_common.WARNING}\n"""

    return java_common.JavaFile(file_name, file_content)


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _generate_structure(
    our_type: intermediate.OurType,
    package: java_common.PackageIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[Error]]:
    """
    Generate a single structure.

    The ``package`` defines the root Java package.
    """
    assert isinstance(
        our_type,
        (
            intermediate.Enumeration,
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
        ),
    )

    files = []  # List[java_common.JavaFile]

    if isinstance(our_type, intermediate.Class) and our_type.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"Types/{our_type.name}.java"
        )

        imports = _generate_imports_for_class(cls=our_type, package=package)

        code = spec_impls.get(implementation_key, None)
        if code is None:
            return None, Error(
                our_type.parsed.node,
                f"The implementation is missing "
                f"for the implementation-specific class: {implementation_key}",
            )

        structure_name = java_naming.class_name(our_type.name)

        package_name = java_common.PackageIdentifier(
            f"{package}.types.{java_common.CLASS_PKG}"
        )

        java_source = _generate_java_file(
            file_name=structure_name, imports=imports, code=code, package=package_name
        )

        files.append(java_source)
    else:
        if isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            imports = _generate_imports_for_interface(cls=our_type, package=package)

            code, error = _generate_interface(cls=our_type, package=package)
            if error is not None:
                return None, Error(
                    our_type.parsed.node,
                    f"Failed to generate the interface code for "
                    f"the class {our_type.name!r}",
                    [error],
                )

            assert code is not None

            structure_name = java_naming.interface_name(our_type.name)

            file_name = java_common.interface_package_path(structure_name)

            package_name = java_common.PackageIdentifier(
                f"{package}.types.{java_common.INTERFACE_PKG}"
            )

            java_source = _generate_java_file(
                file_name=file_name, imports=imports, code=code, package=package_name
            )

            files.append(java_source)

            if isinstance(our_type, intermediate.ConcreteClass):
                imports = _generate_imports_for_class(cls=our_type, package=package)

                code, error = _generate_class(
                    cls=our_type, spec_impls=spec_impls, package=package
                )
                if error is not None:
                    return None, Error(
                        our_type.parsed.node,
                        f"Failed to generate the class code for "
                        f"the class {our_type.name!r}",
                        [error],
                    )

                assert code is not None

                structure_name = java_naming.class_name(our_type.name)

                file_name = java_common.class_package_path(structure_name)

                package_name = java_common.PackageIdentifier(
                    f"{package}.types.{java_common.CLASS_PKG}"
                )

                java_source = _generate_java_file(
                    file_name=file_name,
                    imports=imports,
                    code=code,
                    package=package_name,
                )

                files.append(java_source)
        elif isinstance(our_type, intermediate.Enumeration):
            code, error = _generate_enum(enum=our_type, package=package)
            if error is not None:
                return None, Error(
                    our_type.parsed.node,
                    f"Failed to generate the code for "
                    f"the enumeration {our_type.name!r}",
                    [error],
                )

            assert code is not None
            structure_name = java_naming.enum_name(our_type.name)

            file_name = java_common.enum_package_path(structure_name)

            package_name = java_common.PackageIdentifier(
                f"{package}.types.{java_common.ENUM_PKG}"
            )

            java_source = _generate_java_file(
                file_name=file_name, imports=None, code=code, package=package_name
            )

            files.append(java_source)
        else:
            assert_never(our_type)

    return files, None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: VerifiedIntermediateSymbolTable,
    package: java_common.PackageIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code of the data structures representing the meta-model.
    """

    files = []  # type: List[java_common.JavaFile]
    errors = []  # type: List[Error]

    files.append(_generate_iclass(package))

    if len(symbol_table.enumerations) == 0:
        files.append(_generate_no_enumerations_defined(package))

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

        new_files, error = _generate_structure(our_type, package, spec_impls)

        if new_files is not None:
            files.extend(new_files)
        elif error is not None:
            errors.append(error)

    if len(errors) > 0:
        return None, errors

    return files, None


# endregion


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
