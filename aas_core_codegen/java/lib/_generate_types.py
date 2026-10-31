"""Generate code of the data structures representing the meta-model."""

import io
import textwrap
from typing import (
    cast,
    Dict,
    List,
    Mapping,
    Optional,
    Set,
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
    NOTE_ON_INVARIANTS_OF_MUTATING_METHODS,
)
from aas_core_codegen.java import (
    common as java_common,
    description as java_description,
    naming as java_naming,
    optional as java_optional,
    transpilation as java_transpilation,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)
from aas_core_codegen.intermediate import (
    construction as intermediate_construction,
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.parse import tree as parse_tree


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
    """Verify that no member names collide in the Java structure of our type."""
    errors: List[Error] = []

    if isinstance(our_type, intermediate.Enumeration):
        pass

    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        pass

    elif isinstance(our_type, intermediate.Class):
        observed_member_names: Dict[Identifier, str] = {}

        for prop in our_type.properties:
            prop_name = java_naming.property_name(prop.name)
            if prop_name in observed_member_names:
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

        observed_constructor_arg_names: Dict[Identifier, str] = {}
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

            observed_method_arg_names: Dict[Identifier, str] = {}
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

    elif isinstance(our_type, intermediate.NamedUnion):
        pass

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
            intermediate.NamedUnion,
        ],
    ] = dict()

    errors: List[Error] = []

    # region Inter-structure collisions

    for our_type in symbol_table.our_types:
        if not isinstance(
            our_type,
            (
                intermediate.Enumeration,
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            continue

        if isinstance(our_type, intermediate.Enumeration):
            name = java_naming.enum_name(our_type.name)
            other = observed_structure_names.get(name)

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

            other = observed_structure_names.get(interface_name)

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

                other = observed_structure_names.get(class_name)

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

        elif isinstance(our_type, intermediate.NamedUnion):
            union_name = java_naming.union_name(our_type.name)

            other = observed_structure_names.get(union_name)

            if other is not None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"The Java name {union_name!r} "
                        f"for the named union {our_type.name!r} "
                        f"collides with the same Java name "
                        f"coming from the {_human_readable_identifier(other)}",
                    )
                )
            else:
                observed_structure_names[union_name] = our_type

        else:
            assert_never(our_type)

    # NOTE (mristin):
    # The descent into the containers lives in a class in the package of
    # the classes as well, and the classes refer to it unqualified.
    other = observed_structure_names.get(Identifier("Descent"))
    if other is not None:
        errors.append(
            Error(
                other.parsed.node,
                "The Java name 'Descent' "
                f"of the {_human_readable_identifier(other)} collides with "
                f"the class of the descent into the containers",
            )
        )

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


def _has_descendable_properties(cls: intermediate.Class) -> bool:
    for prop in cls.properties:
        descendability = intermediate.map_descendability(
            type_annotation=prop.type_annotation
        )

        if descendability[prop.type_annotation]:
            return True

    return False


def _descend_into_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the method of the class ``Descent`` descending into ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.java.common.type_moniker`), so two different
    containers never share a method.
    """
    return Identifier(f"descend{java_common.type_moniker(type_anno)}")


@require(
    lambda type_anno, descendability: (
        type_anno in descendability and descendability[type_anno]
    )
)
def _generate_descend_into(
    expr: str,
    type_anno: intermediate.TypeAnnotationUnion,
    recurse: bool,
    recurse_expr: str,
    descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
) -> Stripped:
    """
    Generate the stream of the instances held by the value at ``expr``.

    An instance is streamed in-line. A container is delegated to its method in
    the class ``Descent``, which descends only one level and calls the method
    of its items by name. This way the descent is composed of plain functions,
    to any depth.

    The ``recurse_expr`` is the Java expression passed on to the methods of
    the containers, and has to evaluate to ``recurse``.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        # NOTE (mristin):
        # A named union is not itself an ``IClass``, so we descend into
        # the underlying instance instead.
        instance_expr = (
            f"{expr}.getUnderlying()"
            if isinstance(type_anno.our_type, intermediate.NamedUnion)
            else expr
        )

        if not recurse:
            return Stripped(f"Stream.<IClass>of({instance_expr})")

        return Stripped(
            f"""\
Stream.concat(Stream.<IClass>of({instance_expr}),
{I}StreamSupport.stream({instance_expr}.descend().spliterator(), false))"""
        )

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        name = _descend_into_container_name(type_anno)
        call = f"Descent.{name}({expr}, {recurse_expr})"
        # Heuristic to break the lines, very rudimentary
        if len(call) > 70:
            call = f"""\
Descent.{name}(
{I}{expr},
{I}{recurse_expr})"""

        return Stripped(call)

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
    Generate the method of the class ``Descent`` for ``type_anno``.

    The ``descendability`` maps ``type_anno`` and its nested type annotations,
    see :py:func:`aas_core_codegen.intermediate.map_descendability`.
    """
    stream_by_recurse: Dict[bool, Stripped] = dict()

    for recurse in (False, True):
        stream: Stripped

        if isinstance(
            type_anno,
            (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
        ):
            if not recurse and isinstance(
                type_anno.items, intermediate.OurTypeAnnotation
            ):
                # NOTE (mristin):
                # We map the instances directly instead of flat-mapping them,
                # so that we do not create a stream for every single item.
                instance_expr = (
                    "item.getUnderlying()"
                    if isinstance(type_anno.items.our_type, intermediate.NamedUnion)
                    else "item"
                )

                stream = Stripped(f"that.stream().<IClass>map(item -> {instance_expr})")
            else:
                item_stream = _generate_descend_into(
                    expr="item",
                    type_anno=type_anno.items,
                    recurse=recurse,
                    recurse_expr="recurse",
                    descendability=descendability,
                )

                stream = Stripped(
                    f"""\
that.stream().flatMap(item ->
{I}{indent_but_first_line(item_stream, I)})"""
                )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_streams = [
                _generate_descend_into(
                    expr=f"that.item{i + 1}()",
                    type_anno=item_type_anno,
                    recurse=recurse,
                    recurse_expr="recurse",
                    descendability=descendability,
                )
                for i, item_type_anno in enumerate(type_anno.items)
                if descendability[item_type_anno]
            ]

            stream = item_streams[0]
            for item_stream in item_streams[1:]:
                stream = Stripped(
                    f"""\
Stream.concat(
{I}{indent_but_first_line(stream, I)},
{I}{indent_but_first_line(item_stream, I)})"""
                )

        else:
            assert_never(type_anno)

        stream_by_recurse[recurse] = stream

    body: Stripped

    # NOTE (mristin):
    # The streams coincide if the container holds only other containers, as
    # ``recurse`` is simply passed on to their methods.
    if stream_by_recurse[False] == stream_by_recurse[True]:
        body = Stripped(f"return {stream_by_recurse[True]};")
    else:
        body = Stripped(
            f"""\
if (!recurse) {{
{I}return {indent_but_first_line(stream_by_recurse[False], I)};
}}

return {stream_by_recurse[True]};"""
        )

    name = _descend_into_container_name(type_anno)
    value_type = java_common.generate_type(type_anno)

    return Stripped(
        f"""\
/**
 * Iterate over the class instances held by {{@code that}}.
 *
 * <p>If {{@code recurse}} is set, descend recursively into the instances
 * as well.
 */
static Stream<IClass> {name}(
{I}{indent_but_first_line(value_type, I)} that,
{I}boolean recurse) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_descend_body(cls: intermediate.ConcreteClass, recurse: bool) -> Stripped:
    """Generate the iterator function body for recursive and non-recursive descend methods.

    We leverage lazily evaluated streams to iterate over the object stream one by one.
    """
    class_name = java_naming.class_name(cls.name)

    blocks: List[Stripped] = [Stripped("Stream<IClass> memberStream = Stream.empty();")]

    for prop in cls.properties:
        descendability = intermediate.map_descendability(
            type_annotation=prop.type_annotation
        )

        if not descendability[prop.type_annotation]:
            continue

        prop_name = java_naming.property_name(prop.name)

        prop_stream = _generate_descend_into(
            expr=f"{class_name}.this.{prop_name}",
            type_anno=intermediate.beneath_optional(prop.type_annotation),
            recurse=recurse,
            recurse_expr="true" if recurse else "false",
            descendability=descendability,
        )

        blocks.append(
            Stripped(
                f"""\
if ({prop_name} != null) {{
{I}memberStream = Stream.concat(memberStream,
{II}{indent_but_first_line(prop_stream, II)});
}}"""
            )
        )

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
    imports: List[Stripped] = [
        Stripped(f"{package}.common.*"),
        Stripped(f"{package}.types.enums.*"),
        Stripped(f"{package}.types.impl.*"),
        Stripped(f"{package}.types.model.*"),
        Stripped("java.util.List"),
    ]

    imports.extend(
        java_common.json_imports_if_necessary(
            prop.type_annotation for prop in cls.properties
        )
    )

    imports.extend(java_common.set_imports_if_necessary(cls, with_bodies=False))

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

    if any(prop for prop in cls.properties if prop.specified_for is cls) or any(
        isinstance(method.returns, intermediate.OptionalTypeAnnotation)
        for method in cls.methods
    ):
        imports.append(Stripped("java.util.Optional"))

    return Stripped("\n".join(f"import {imp};" for imp in imports))


def _generate_imports_for_class(
    cls: intermediate.Class,
    package: java_common.PackageIdentifier,
) -> Stripped:
    """
    Generate necessary Java Platform imports for the given class ``cls``.

    The ``package`` defines the root Java package.
    """
    imports: List[Stripped] = [
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
    ]

    imports.extend(
        java_common.json_imports_if_necessary(
            prop.type_annotation for prop in cls.properties
        )
    )

    imports.extend(java_common.set_imports_if_necessary(cls, with_bodies=True))

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

    return Stripped("\n".join(f"import {imp};" for imp in imports))


@ensure(lambda result: not (result[1] is not None) or (result[0] is None))
def _generate_comment_for_method(
    method: intermediate.MethodUnion,
    cls: intermediate.ClassUnion,
    package: java_common.PackageIdentifier,
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
            java_description.documentation_comment(
                Stripped("\n\n".join(extra_remarks))
            ),
            None,
        )

    comment, comment_errors = java_description.generate_comment_for_signature(
        description=method.description,
        context=java_description.Context(package=package, cls_or_enum=cls),
        extra_remarks=extra_remarks,
    )

    if comment_errors is not None:
        return None, Error(
            method.description.parsed.node,
            f"Failed to generate the documentation comment "
            f"for the method {method.name!r}",
            comment_errors,
        )

    assert comment is not None
    return comment, None


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
    blocks: List[Stripped] = []

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
        if (
            method.specified_for is not cls
            or method.visibility is not intermediate.Visibility.PUBLIC
        ):
            continue

        signature_blocks: List[Stripped] = []

        signature_comment, signature_comment_error = _generate_comment_for_method(
            method=method, cls=cls, package=package
        )
        if signature_comment_error is not None:
            return None, signature_comment_error

        if signature_comment is not None:
            signature_blocks.append(signature_comment)

        # fmt: off
        returns = (
            java_common.generate_type(type_annotation=method.returns)
            if method.returns is not None else "void"
        )
        # fmt: on

        arg_codes: List[Stripped] = []
        for arg in method.arguments:
            arg_type = java_common.generate_type(type_annotation=arg.type_annotation)
            arg_name = java_naming.argument_name(arg.name)
            arg_codes.append(Stripped(f"{arg_type} {arg_name}"))

        signature_name = java_naming.method_name(method.name)
        if len(arg_codes) > 1:
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
        ) and isinstance(
            prop.type_annotation.value,
            (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
        ):
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

    blocks: List[str] = []

    arg_codes: List[Stripped] = []
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

    body: List[Stripped] = []

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

    blocks: List[str] = []

    arg_codes: List[Stripped] = []
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

    body: List[Stripped] = []

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


class _MethodTranspiler(java_transpilation.Transpiler):
    """Transpile the body of a :py:class:`intermediate.UnderstoodMethod`."""

    def __init__(
        self,
        inference: intermediate_type_inference.InferenceOfFunction,
        is_optional_map: Mapping[parse_tree.Node, bool],
        method: intermediate.UnderstoodMethod,
    ) -> None:
        """Initialize with the given values."""
        java_transpilation.Transpiler.__init__(
            self,
            type_map=inference.type_map,
            optional_map=is_optional_map,
            environment=inference.environment_with_args,
            downcast_map=inference.downcast_map,
        )

        self._argument_name_set = frozenset(arg.name for arg in method.arguments)

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return (
                self._unwrap_if_optional(
                    node=node,
                    variable=Stripped(java_naming.variable_name(node.identifier)),
                ),
                None,
            )

        if node.identifier == "self":
            return Stripped("this"), None

        if node.identifier in self._argument_name_set:
            return (
                self._unwrap_if_optional(
                    node=node,
                    variable=Stripped(java_naming.argument_name(node.identifier)),
                ),
                None,
            )

        our_type = self._environment.find_our_type(node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(java_naming.enum_name(node.identifier)), None

        # NOTE (mristin):
        # The intermediate stage refuses the references to the constants and
        # to the verification functions in the methods, as they would introduce
        # a cyclic dependency between the modules in the other targets.
        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to Java. We could not find it neither in the local variables, "
            f"nor in the arguments, nor as an enumeration. If you expect this name "
            f"to be transpilable, please contact the developers.",
        )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_method(
    method: intermediate.UnderstoodMethod,
    cls: intermediate.ConcreteClass,
    type_inference: intermediate_type_inference.TypeInference,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Transpile the ``method`` as a member of the concrete class ``cls``.

    The ``package`` defines the root Java package.
    """
    inference = type_inference.by_method[method]

    # NOTE (mristin):
    # We deliberately do not check the invariants of the instance after a method
    # call, as that would be too inefficient. The invariants are verified only in
    # the verification, on the explicit request of the user. We note that in
    # the documentation of the mutating methods, see
    # :py:func:`_generate_comment_for_method`.

    optional_inferrer = java_optional.OptionalInferrer(
        environment=inference.environment_with_args,
        type_map=inference.type_map,
    )

    for node in method.body:
        _ = optional_inferrer.transform(node)

    if len(optional_inferrer.errors) > 0:
        return None, Error(
            method.parsed.node,
            f"Failed to infer whether the types are optional "
            f"in the method {method.name!r} of the class {cls.name!r}",
            optional_inferrer.errors,
        )

    transpiler = _MethodTranspiler(
        inference=inference,
        is_optional_map=optional_inferrer.is_optional_map,
        method=method,
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

    comment, comment_error = _generate_comment_for_method(
        method=method, cls=cls, package=package
    )
    if comment_error is not None:
        return None, comment_error

    if comment is not None:
        writer.write(comment)
        writer.write("\n")

    if method.visibility is intermediate.Visibility.PUBLIC:
        writer.write("@Override\npublic ")
    elif method.visibility is intermediate.Visibility.PROTECTED:
        writer.write("protected ")
    elif method.visibility is intermediate.Visibility.PRIVATE:
        writer.write("private ")
    else:
        raise AssertionError(
            f"Unexpected visibility of the method {method.name!r}: "
            f"{method.visibility}"
        )

    returns = (
        java_common.generate_type(type_annotation=method.returns)
        if method.returns is not None
        else "void"
    )

    method_name = java_naming.method_name(method.name)

    arg_defs = [
        Stripped(
            f"{java_common.generate_type(arg.type_annotation)} "
            f"{java_naming.argument_name(arg.name)}"
        )
        for arg in method.arguments
    ]

    if len(arg_defs) == 0:
        writer.write(f"{returns} {method_name}() {{")
    else:
        arg_block = ",\n".join(arg_defs)
        writer.write(
            f"""\
{returns} {method_name}(
{I}{indent_but_first_line(arg_block, I)}
) {{"""
        )

    for stmt in body:
        writer.write("\n")
        writer.write(textwrap.indent(stmt, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


# fmt: off
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
# fmt: on
def _generate_class(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
    package: java_common.PackageIdentifier,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the class ``cls``.

    The ``package`` defines the root Java package.

    ``type_inference`` holds the type inference of all the understood methods.
    """
    # Code blocks to be later joined by double newlines and indented once

    blocks: List[Stripped] = []

    errors: List[Error] = []

    descendable = _has_descendable_properties(cls)

    # region Properties

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_type = java_common.generate_type(type_annotation=type_anno)

        prop_name = java_naming.property_name(prop.name)

        prop_blocks: List[Stripped] = []

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

        get_set_blocks: List[Stripped] = []

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            # NOTE (mristin):
            # An optional JSON-able property which is a JSON null is treated as
            # absent in all the SDKs, as most of them can not tell the two apart.
            # We normalize it here, once, so that the serialization, the copying
            # and the verification all see it as absent.
            getter_body = (
                f"""\
return Optional.ofNullable({prop_name})
{I}.filter(value -> !value.isNull());"""
                if isinstance(
                    prop.type_annotation.value, intermediate.JsonValueTypeAnnotation
                )
                else f"return Optional.ofNullable({prop_name});"
            )

            get_set_blocks.append(
                Stripped(
                    f"""\
@Override
public {prop_type} {getter_name}() {{
{I}{indent_but_first_line(getter_body, I)}
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
        ) and isinstance(
            prop.type_annotation.value,
            (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
        ):
            prop_name = java_naming.property_name(prop.name)
            method_name = f"over{java_naming.class_name(prop.name)}OrEmpty"
            getter_name = java_naming.getter_name(prop.name)
            items_type = java_common.generate_type(prop.type_annotation.value.items)

            empty_factory: str
            if isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
                empty_factory = "emptyList"
            elif isinstance(prop.type_annotation.value, intermediate.SetTypeAnnotation):
                empty_factory = "emptySet"
            else:
                assert_never(prop.type_annotation.value)

            blocks.append(
                Stripped(
                    f"""\
/**
 * Iterate over {{@link {cls_name}#{prop_name}}}, if set,
 * and otherwise return an empty iterator.
 */
public Iterable<{items_type}> {method_name}() {{
{I}return {getter_name}().orElseGet(Collections::{empty_factory});
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
        elif isinstance(method, intermediate.UnderstoodMethod):
            method_code, method_error = _transpile_method(
                method=method,
                cls=cls,
                type_inference=type_inference,
                package=package,
            )
            if method_error is not None:
                errors.append(method_error)
                continue

            assert method_code is not None
            blocks.append(method_code)
        else:
            assert_never(method)

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

    # NOTE (mristin):
    # The literal carries its own string representation, instead of the text
    # living only in a look-up table in the stringification. See
    # :py:func:`_generate_ienum` for what that buys.
    text_name = java_naming.property_name(Identifier("literal_text"))

    members = Stripped(
        f"""\
private final String {text_name};

{name}(String {text_name}) {{
{I}this.{text_name} = {text_name};
}}

@Override
public String {java_naming.method_name(Identifier("literal_text"))}() {{
{I}return {text_name};
}}"""
    )

    if len(enum.literals) == 0:
        # NOTE (mristin):
        # An enumeration without a single literal still has to implement
        # the interface, and a member of an enumeration has to be preceded by
        # a semicolon closing the -- here empty -- list of the literals.
        writer.write(
            f"""\
public enum {name} implements IEnum {{
{I};

{textwrap.indent(members, I)}
}}"""
        )
        return Stripped(writer.getvalue()), None

    writer.write(
        f"""\
public enum {name} implements IEnum {{\n"""
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
                f"{java_naming.enum_literal_name(literal.name)}"
                f"({java_common.string_literal(literal.value)})",
                I,
            )
        )

    writer.write(";\n\n")
    writer.write(textwrap.indent(members, I))
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


def _generate_ienum(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    """
    Generate the common interface implemented by every enumeration.

    A literal carries its own string representation, so that a single
    non-generic method can render any literal of any enumeration -- see,
    *e.g.*, the xmlization ``writeEnum`` -- instead of needing one method per
    enumeration. Neither a generic parameter nor a ``Class`` token could
    achieve that: what is missing is the *function* attached to the type, and
    only the literal itself can carry it.

    Implementing an interface leaves an enumeration a perfectly ordinary Java
    enumeration: ``switch``, ``values()``, ``valueOf(String)``, ``name()``,
    ``ordinal()``, ``EnumSet``, ``EnumMap`` and the built-in serialization all
    keep working, exactly as they do for ``java.time.DayOfWeek``.

    Interfaces and classes always import ``{package}.types.enums.*``, so this
    file doubles as the reason that package is never empty, even for a
    meta-model which defines no enumeration at all.
    """
    structure_name = Stripped("IEnum")
    file_name = java_common.enum_package_path(structure_name)
    file_content = f"""\
{java_common.WARNING}

package {package}.types.enums;

/**
 * Represent a literal of an enumeration of the meta-model.
 */
public interface IEnum {{
{I}/**
{I} * Get the string representation of this literal.
{I} *
{I} * <p>This is the text the literal is de/serialized as, which is in general
{I} * not its {{@link Enum#name()}}.
{I} */
{I}String literalText();
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
 * Represent a general class of the meta-model.
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


def _generate_iunion(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    """
    Generate the common interface implemented by every named union.

    ``T`` is self-bounded (``T extends IUnion<T>``) so that a single generic
    dispatch method (see, *e.g.*, ``Copying.deep`` or the enhancing
    ``_Wrapper.transform``) can accept and return any named union's own
    concrete type with no downcast at the call site, instead of needing one
    dispatch overload per named union.
    """
    structure_name = Stripped("IUnion")
    file_name = java_common.interface_package_path(structure_name)
    file_content = f"""\
{java_common.WARNING}

package {package}.types.model;

/**
 * Represent an instance of a named union of one or more classes.
 */
public interface IUnion<T extends IUnion<T>> {{
{I}/**
{I} * Get the underlying instance regardless of the concrete case.
{I} */
{I}IClass getUnderlying();

{I}/**
{I} * Wrap {{@code that}} as an instance of the same union type as this
{I} * instance, based on its run-time type.
{I} */
{I}T withUnderlying(IClass that);
}}

{java_common.WARNING}\n"""

    return java_common.JavaFile(file_name, file_content)


def _generate_named_union_class(named_union: intermediate.NamedUnion) -> Stripped:
    """
    Generate the class representing the named union ``named_union``.

    Represent the union as a closed, plain Java class, not an interface,
    since a union does not need to allow custom enhancements or wrappings
    the way our model classes do. Store the single active alternative
    behind a private discriminant enum, in its own separately-typed field
    per root of the union, so that adding an alternative later never
    requires an open, shared field.

    The alternatives are the roots of the union, not the flattened
    implementers, so that the union mirrors the meta-model. Each root is
    typed with its interface, so that a root which is an abstract class, or
    a concrete class with descendants, holds the instances of its descendants
    as well.
    """
    name = java_naming.union_name(named_union.name)

    roots = named_union.roots

    interface_names = [java_naming.interface_name(root.name) for root in roots]
    root_class_names = [java_naming.class_name(root.name) for root in roots]
    value_kinds = [java_naming.enum_literal_name(root.name) for root in roots]
    field_names = [
        Stripped(f"as{root_class_name}") for root_class_name in root_class_names
    ]

    # region Doc comment

    if len(interface_names) == 1:
        listing = f"{{@link {interface_names[0]}}}"
    elif len(interface_names) == 2:
        listing = f"{{@link {interface_names[0]}}} and {{@link {interface_names[1]}}}"
    else:
        listing = (
            ", ".join(
                f"{{@link {interface_name}}}" for interface_name in interface_names[:-1]
            )
            + f", and {{@link {interface_names[-1]}}}"
        )

    # endregion

    # region Value kind

    value_kind_lines = ",\n".join(value_kinds)
    value_kind_enum = Stripped(
        f"""\
private enum ValueKind {{
{I}{indent_but_first_line(value_kind_lines, I)}
}}"""
    )

    # endregion

    # region Fields and constructor

    field_decls = [Stripped("private final ValueKind valueKind;")] + [
        Stripped(f"private final {interface_name} {field_name};")
        for interface_name, field_name in zip(interface_names, field_names, strict=True)
    ]
    fields_block = Stripped("\n".join(field_decls))

    ctor_params = ["ValueKind valueKind"] + [
        f"{interface_name} {field_name}"
        for interface_name, field_name in zip(interface_names, field_names, strict=True)
    ]
    ctor_params_joined = ",\n".join(ctor_params)

    ctor_body_lines = ["this.valueKind = valueKind;"] + [
        f"this.{field_name} = {field_name};" for field_name in field_names
    ]
    ctor_body = "\n".join(ctor_body_lines)

    constructor = Stripped(
        f"""\
private {name}(
{I}{indent_but_first_line(ctor_params_joined, I)}) {{
{I}{indent_but_first_line(ctor_body, I)}
}}"""
    )

    # endregion

    # region Factory methods, one per root

    factory_methods: List[Stripped] = []
    for i, (interface_name, root_class_name, value_kind) in enumerate(
        zip(interface_names, root_class_names, value_kinds, strict=True)
    ):
        args = [f"ValueKind.{value_kind}"] + [
            "that" if j == i else "null" for j in range(len(field_names))
        ]
        args_joined = ",\n".join(args)

        factory_methods.append(
            Stripped(
                f"""\
/**
 * Wrap {{@code that}} as an instance of {{@link {name}}}.
 */
public static {name} from{root_class_name}({interface_name} that) {{
{I}return new {name}(
{II}{indent_but_first_line(args_joined, II)});
}}"""
            )
        )

    # endregion

    # region Underlying

    switch_case_lines: List[str] = []
    for value_kind, field_name in zip(value_kinds, field_names, strict=True):
        switch_case_lines.append(f"case {value_kind}:")
        switch_case_lines.append(f"{I}return {field_name};")

    switch_body = "\n".join(switch_case_lines)

    get_underlying = Stripped(
        f"""\
/**
 * Get the underlying instance regardless of the concrete case.
 */
@Override
public IClass getUnderlying() {{
{I}switch (valueKind) {{
{II}{indent_but_first_line(switch_body, II)}
{II}default:
{III}throw new IllegalStateException(
{IIII}String.format("Unexpected value kind: %s", valueKind));
{I}}}
}}"""
    )

    # endregion

    # region From underlying

    # NOTE (mristin):
    # The roots may overlap, so we test the most specific root first.
    from_underlying_lines: List[str] = []
    for i, root in enumerate(named_union.roots_most_specific_first()):
        interface_name = java_naming.interface_name(root.name)
        root_class_name = java_naming.class_name(root.name)

        keyword = "if" if i == 0 else "} else if"
        from_underlying_lines.append(f"{keyword} (that instanceof {interface_name}) {{")
        from_underlying_lines.append(
            f"{I}return from{root_class_name}(({interface_name}) that);"
        )

    from_underlying_lines.append("} else {")
    from_underlying_lines.append(f"{I}throw new IllegalArgumentException(")
    from_underlying_lines.append(f"{II}String.format(")
    from_underlying_lines.append(
        f'{III}"Unexpected run-time type for the union {name}: %s",'
    )
    from_underlying_lines.append(f"{III}that.getClass()));")
    from_underlying_lines.append("}")

    from_underlying_body = "\n".join(from_underlying_lines)

    from_underlying = Stripped(
        f"""\
/**
 * Wrap {{@code that}} as an instance of {{@link {name}}} based on its run-time type.
 */
public static {name} fromUnderlying(IClass that) {{
{I}{indent_but_first_line(from_underlying_body, I)}
}}"""
    )

    # endregion

    # region With underlying

    with_underlying = Stripped(
        f"""\
/**
 * Wrap {{@code that}} as an instance of {{@link {name}}} based on its run-time type.
 *
 * <p>This is the instance-level counterpart of {{@link {name}#fromUnderlying}},
 * needed so that a generic method dispatching on {{@link IUnion}} can re-wrap
 * a transformed or copied value without knowing the concrete union type at
 * compile time.
 */
@Override
public {name} withUnderlying(IClass that) {{
{I}return {name}.fromUnderlying(that);
}}"""
    )

    # endregion

    blocks = [value_kind_enum, fields_block, constructor]
    blocks.extend(factory_methods)
    blocks.append(get_underlying)
    blocks.append(from_underlying)
    blocks.append(with_underlying)

    body = "\n\n".join(blocks)

    return Stripped(
        f"""\
/**
 * Represent a union of {listing}.
 */
public class {name} implements IUnion<{name}> {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _generate_structure(
    our_type: intermediate.OurType,
    package: java_common.PackageIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[Error]]:
    """
    Generate a single structure.

    The ``package`` defines the root Java package.

    ``type_inference`` holds the type inference of all the understood methods.
    """
    assert isinstance(
        our_type,
        (
            intermediate.Enumeration,
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    )

    files = []  # List[java_common.JavaFile]

    if isinstance(our_type, intermediate.NamedUnion):
        structure_name = java_naming.union_name(our_type.name)

        file_name = java_common.interface_package_path(structure_name)

        package_name = java_common.PackageIdentifier(
            f"{package}.types.{java_common.INTERFACE_PKG}"
        )

        java_source = _generate_java_file(
            file_name=file_name,
            imports=None,
            code=_generate_named_union_class(named_union=our_type),
            package=package_name,
        )

        files.append(java_source)

        return files, None

    if isinstance(our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)):
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
                cls=our_type,
                spec_impls=spec_impls,
                package=package,
                type_inference=type_inference,
            )
            if error is not None:
                return None, Error(
                    our_type.parsed.node,
                    f"Failed to generate the class code for "
                    f"the class {our_type.name!r}",
                    [error],
                )

            assert code is not None

            # NOTE (mristin):
            # The transpiled methods might iterate over the ranges with streams.
            for stream_class in ("IntStream", "LongStream"):
                if f"{stream_class}." in code:
                    imports = Stripped(
                        f"{imports}\nimport java.util.stream.{stream_class};"
                    )

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
    type_inference: intermediate_type_inference.TypeInference,
    package: java_common.PackageIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code of the data structures representing the meta-model.
    """
    files: List[java_common.JavaFile] = []
    errors: List[Error] = []

    files.append(_generate_iclass(package))
    files.append(_generate_ienum(package))

    if len(symbol_table.named_unions) > 0:
        files.append(_generate_iunion(package))

    for our_type in symbol_table.our_types:
        if not isinstance(
            our_type,
            (
                intermediate.Enumeration,
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            continue

        new_files, error = _generate_structure(
            our_type=our_type,
            package=package,
            spec_impls=spec_impls,
            type_inference=type_inference,
        )

        if new_files is not None:
            files.extend(new_files)
        elif error is not None:
            errors.append(error)

    if len(errors) > 0:
        return None, errors

    descent_methods: List[Stripped] = []
    observed_monikers: Set[str] = set()
    descent_imports: Set[Stripped] = {
        Stripped(f"{package}.common.*"),
        Stripped(f"{package}.types.enums.*"),
        Stripped(f"{package}.types.model.*"),
        Stripped("java.util.stream.Stream"),
        Stripped("java.util.stream.StreamSupport"),
    }

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            descendability = intermediate.map_descendability(prop.type_annotation)

            for type_anno, descendable in descendability.items():
                if not descendable or not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ):
                    continue

                moniker = java_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)

                if isinstance(type_anno, intermediate.ListTypeAnnotation):
                    descent_imports.add(Stripped("java.util.List"))

                # NOTE (mristin):
                # The method spells out the type of the container, so we need to
                # import the sets nested in it as well.
                if any(
                    isinstance(nested, intermediate.SetTypeAnnotation)
                    for nested in intermediate.over_type_annotation_and_nested_type_annotations(
                        type_anno
                    )
                ):
                    descent_imports.add(Stripped("java.util.Set"))

                descent_methods.append(
                    _generate_descend_into_container(
                        type_anno=type_anno, descendability=descendability
                    )
                )

    if len(descent_methods) > 0:
        descent_methods_joined = "\n\n".join(descent_methods)

        files.append(
            _generate_java_file(
                file_name=java_common.class_package_path(Stripped("Descent")),
                imports=Stripped(
                    "\n".join(f"import {imp};" for imp in sorted(descent_imports))
                ),
                code=Stripped(
                    f"""\
/**
 * Descend into the containers which hold class instances.
 *
 * <p>Each method descends only one level, and calls the method of the items
 * by name, so that the descent is composed of plain functions to any depth.
 */
final class Descent {{
{I}private Descent() {{
{II}// Prevent instantiation
{I}}}

{I}{indent_but_first_line(descent_methods_joined, I)}
}}"""
                ),
                package=java_common.PackageIdentifier(
                    f"{package}.types.{java_common.CLASS_PKG}"
                ),
            )
        )

    return files, None


# endregion


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
