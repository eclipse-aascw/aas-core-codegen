"""Generate code for copying instances in memory."""

import io
import textwrap
from typing import Tuple, Optional, List, Set

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    indent_but_first_line,
    assert_never,
)
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)


# region Generate


def _generate_union_deep_copy_helper() -> Stripped:
    """
    Generate a single ``deep`` overload shared by every named union.

    A named union is not itself an ``IClass``, so it can not be passed to
    the generic ``<T extends IClass> T deep(T that)``. We add this second
    generic overload, next to it, so that call sites can keep calling
    ``deep`` directly, regardless of whether the value at hand is a class
    instance or a named union.

    ``T`` is bounded by ``IUnion<T>`` (see ``_generate_iunion`` in
    ``_generate_types.py``) instead of by the union's own type, so we need
    only this one overload for *all* named unions, not one per union --
    while ``T.withUnderlying(...)`` still lets the result come back as the
    caller's own concrete union type, with no downcast needed at any
    property/list-item/tuple-item call site.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
/**
 * Make a recursively a deep copy of {{@code that}}.
 *
 * @param that to be deeply copied in a recursive manner
 */
public static <T extends IUnion<T>> T deep(T that) {{
{I}return that.withUnderlying(
{II}deep(that.getUnderlying()));
}}"""
    )


def _generate_shallow_copy_transform_method(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the method in the transformer to make a shallow copy of ``cls''."""
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

    cls_name = java_naming.class_name(cls.name)

    if len(cls.constructor.arguments) == 0:
        return_statement = Stripped(f"return new {cls_name}();")
    else:
        constructor_arg_exprs: List[str] = []
        for arg in cls.constructor.arguments:
            if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
                getter_name = java_naming.getter_name(arg.name)
                constructor_arg_exprs.append(f"that.{getter_name}().orElse(null)")
            else:
                getter_name = java_naming.getter_name(arg.name)
                constructor_arg_exprs.append(f"that.{getter_name}()")

        args_joined = ", ".join(constructor_arg_exprs)
        return_statement = Stripped(f"return new {cls_name}({args_joined});")

        if len(return_statement) > 70:
            args_joined = ",\n".join(constructor_arg_exprs)
            return_statement = Stripped(
                f"""\
return new {cls_name}(
{I}{indent_but_first_line(args_joined, I)});"""
            )

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
@Override
public IClass {transform_name}(
{I}{interface_name} that
) {{
{I}{indent_but_first_line(return_statement, I)}
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_shallow_copier(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transformer which makes shallow copies."""
    blocks: List[Stripped] = []

    for cls in symbol_table.concrete_classes:
        blocks.append(_generate_shallow_copy_transform_method(cls=cls))
    writer = io.StringIO()
    writer.write(
        """\
/**
 * Dispatch the making of shallow copies.
 */
private static class _ShallowCopier extends AbstractTransformer<IClass> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _copies_by_sharing(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether a value of ``type_anno`` is deeply copied by sharing it.

    The primitives, the constrained primitives and the enumeration literals are
    immutable, and so is a tuple record of them -- except for the byte arrays,
    which are mutable in Java.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return primitive_type is not intermediate.PrimitiveType.BYTEARRAY

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        return isinstance(type_anno.our_type, intermediate.Enumeration)

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return all(_copies_by_sharing(item) for item in type_anno.items)

    return False


def _has_deep_copy_method(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether ``type_anno`` is deeply copied through a method of its own.

    A list or a set of values which are copied by sharing needs only a copy of
    the container, so it gets no method of its own.
    """
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        return not _copies_by_sharing(type_anno.items)

    return isinstance(
        type_anno, intermediate.TupleTypeAnnotation
    ) and not _copies_by_sharing(type_anno)


def _deep_copy_method_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the method of ``Copying`` deeply copying ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.java.common.type_moniker`), so two different
    containers never share a method. The moniker contains an underscore, so
    the name never collides with ``deep`` or ``shallow``.
    """
    return Identifier(f"deep{java_common.type_moniker(type_anno)}")


def _generate_deep_copy_expr(
    expr: str, type_anno: intermediate.TypeAnnotationUnion
) -> Stripped:
    """
    Generate the expression deeply copying the value at ``expr``.

    A container with a method of its own is delegated to it, which copies only
    one level and calls the method of its items by name. This way the deep copy
    is composed of plain functions, to any depth.
    """
    if _copies_by_sharing(type_anno):
        return Stripped(expr)

    if intermediate.try_primitive_type(type_anno) is not None:
        # NOTE (mristin):
        # Only a byte array is a primitive which is not copied by sharing.
        # The ``clone`` of an array gives back the array's own type, so no cast
        # is needed.
        return Stripped(f"{expr}.clone()")

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        assert isinstance(
            type_anno.our_type, (intermediate.Class, intermediate.NamedUnion)
        ), f"Unexpected our type not copied by sharing: {type_anno}"

        # NOTE (mristin):
        # A named union has its own ``deep`` overload (see
        # :py:func:`_generate_union_deep_copy_helper`), so it is deep-copied
        # exactly like a class instance.
        return Stripped(f"deep({expr})")

    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        # NOTE (mristin):
        # A Jackson node is mutable, unlike the other leaves, so sharing it
        # would let the copy see every later change to the original's node, and
        # the other way around. ``deepCopy`` is Jackson's own deep copy.
        return Stripped(f"{expr}.deepCopy()")

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        if _has_deep_copy_method(type_anno):
            return Stripped(f"{_deep_copy_method_name(type_anno)}({expr})")

        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            return Stripped(f"new ArrayList<>({expr})")

        if isinstance(type_anno, intermediate.SetTypeAnnotation):
            return Stripped(f"new HashSet<>({expr})")

    raise AssertionError(
        f"Unexpected type annotation to be deeply copied: {type_anno}. "
        f"The optionals nested in the containers should have been refused in "
        f"parse._translate._verify_symbol_table."
    )


@require(lambda type_anno: _has_deep_copy_method(type_anno))
def _generate_deep_copy_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the method of ``Copying`` deeply copying ``type_anno``."""
    value_type = java_common.generate_type(type_anno)

    body: Stripped
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        container_class = (
            "ArrayList"
            if isinstance(type_anno, intermediate.ListTypeAnnotation)
            else "HashSet"
        )
        item_type = java_common.generate_type(type_anno.items)
        item_copy = _generate_deep_copy_expr("item", type_anno.items)

        body = Stripped(
            f"""\
{value_type} result = new {container_class}<>(that.size());
for ({item_type} item : that) {{
{I}result.add({indent_but_first_line(item_copy, I)});
}}
return result;"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        tuple_literal = java_common.generate_tuple_literal(
            item_exprs=[
                _generate_deep_copy_expr(f"that.item{i + 1}()", item_type_anno)
                for i, item_type_anno in enumerate(type_anno.items)
            ]
        )

        body = Stripped(f"return {tuple_literal};")

    else:
        assert_never(type_anno)

    return Stripped(
        f"""\
/**
 * Make a deep copy of {{@code that}}, copying its items recursively.
 */
private static {value_type} {_deep_copy_method_name(type_anno)}(
{I}{indent_but_first_line(value_type, I)} that) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_deep_copy_transform_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method in the transformer to make a deep copy of ``cls''."""
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

    cls_name = java_naming.class_name(cls.name)

    return_statement: Stripped
    if len(cls.constructor.arguments) == 0:
        return_statement = Stripped(f"return new {cls_name}();")
    else:
        constructor_arg_exprs: List[str] = []
        for arg in cls.constructor.arguments:
            getter_name = java_naming.getter_name(arg.name)
            type_anno = intermediate.beneath_optional(arg.type_annotation)

            if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
                constructor_arg_exprs.append(
                    _generate_deep_copy_expr(f"that.{getter_name}()", type_anno)
                )
            elif _copies_by_sharing(type_anno):
                constructor_arg_exprs.append(f"that.{getter_name}().orElse(null)")
            else:
                value_copy = _generate_deep_copy_expr(
                    f"that.{getter_name}().get()", type_anno
                )
                constructor_arg_exprs.append(
                    f"""\
that.{getter_name}().isPresent()
{I}? {indent_but_first_line(value_copy, I)}
{I}: null"""
                )

        args_joined = ",\n".join(constructor_arg_exprs)
        return_statement = Stripped(
            f"""\
return new {cls_name}(
{I}{indent_but_first_line(args_joined, I)}
);"""
        )

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
@Override
public IClass {transform_name} (
{I}{interface_name} that
) {{
{I}{indent_but_first_line(return_statement, I)}
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_deep_copier(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transformer which makes deep copies."""
    blocks: List[Stripped] = []

    for cls in symbol_table.concrete_classes:
        blocks.append(_generate_deep_copy_transform_method(cls=cls))
    writer = io.StringIO()
    writer.write(
        """\
/** Dispatch the making of deep copies. */
private static class _DeepCopier extends AbstractTransformer<IClass> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code for copying instances in memory.
    """
    errors: List[Error] = []

    imports: List[Stripped] = [
        Stripped("import java.util.List;"),
        Stripped("import java.util.ArrayList;"),
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.types.{java_common.INTERFACE_PKG}.IClass;"),
        Stripped(f"import {package}.visitation.AbstractTransformer;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.impl.*;"),
        Stripped(f"import {package}.types.model.*;"),
    ]

    if java_common.has_set_properties(symbol_table):
        imports.append(Stripped("import java.util.HashSet;"))

    # NOTE (mristin):
    # We deeply copy the containers through methods of their own, one per
    # type moniker.
    deep_copy_container_methods: List[Stripped] = []
    observed_monikers: Set[str] = set()
    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ) or not _has_deep_copy_method(type_anno):
                    continue

                moniker = java_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)

                # NOTE (mristin):
                # The method spells out the type of the container, so we need to
                # import the sets nested in it as well.
                if Stripped("import java.util.Set;") not in imports and any(
                    isinstance(nested, intermediate.SetTypeAnnotation)
                    for nested in intermediate.over_type_annotation_and_nested_type_annotations(
                        type_anno
                    )
                ):
                    imports.append(Stripped("import java.util.Set;"))

                deep_copy_container_methods.append(
                    _generate_deep_copy_container(type_anno=type_anno)
                )

    # NOTE (mristin):
    # A JSON-able value is a Jackson node, and only the models which use one
    # pay for the import.
    if intermediate_uses.json_types(symbol_table):
        imports.extend(
            Stripped(f"import {json_import};")
            for json_import in java_common.JSON_IMPORTS
        )

    # NOTE (empwilli):
    # We wrap the shallow and deep copying in generic methods to allow for easier
    # enforcement of runtime type safety for the client. Otherwise, if we directly
    # provided the transformer, the client would always need to make the casts, which
    # is cumbersome.

    copy_blocks: List[Stripped] = [
        Stripped(
            """private static final _ShallowCopier shallowCopierInstance = new _ShallowCopier();"""
        ),
        Stripped(
            """private static final _DeepCopier deepCopierInstance = new _DeepCopier();"""
        ),
        Stripped(
            f"""\
/**
 * Make a shallow copy of {{@code that}}.
 *
 * <p>All the properties are copied by reference. This includes also the lists.
 * Hence, a list property is copied by reference, and not, as sometimes might be
 * expected, as a new list of underlying references.
 *
 * @param that to be copied in a shallow manner
 */
@SuppressWarnings("unchecked")
public static <T extends IClass> T shallow(T that) {{
{I}return (T) shallowCopierInstance.transform(that);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Make a recursively a deep copy of {{@code that}}.
 *
 * @param that to be deeply copied in a recursive manner
 */
@SuppressWarnings("unchecked")
public static <T extends IClass> T deep(T that) {{
{I}return (T) deepCopierInstance.transform(that);
}}"""
        ),
    ]

    if len(symbol_table.named_unions) > 0:
        copy_blocks.append(_generate_union_deep_copy_helper())

    copy_blocks.extend(deep_copy_container_methods)

    shallow_copier_block, shallow_errors = _generate_shallow_copier(
        symbol_table=symbol_table
    )
    if shallow_errors is not None:
        errors.extend(shallow_errors)
    else:
        assert shallow_copier_block is not None
        copy_blocks.append(shallow_copier_block)

    deep_copier_block, deep_errors = _generate_deep_copier(symbol_table=symbol_table)
    if deep_errors is not None:
        errors.extend(deep_errors)
    else:
        assert deep_copier_block is not None
        copy_blocks.append(deep_copier_block)

    if len(errors) > 0:
        return None, errors

    copying_writer = io.StringIO()
    copying_writer.write(
        """\
/**
 * Allow for making shallow and deep copies of model instances.
 */
public class Copying
{
"""
    )

    for i, copy_block in enumerate(copy_blocks):
        if i > 0:
            copying_writer.write("\n\n")

        copying_writer.write(textwrap.indent(copy_block, I))

    copying_writer.write("\n}")

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.copying;"),
        Stripped("\n".join(imports)),
        Stripped(f"{copying_writer.getvalue()}"),
        java_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return [java_common.JavaFile("Copying.java", writer.getvalue())], None


# endregion


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
