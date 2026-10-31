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
from aas_core_codegen.csharp import (
    common as csharp_common,
    naming as csharp_naming,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import uses as intermediate_uses


def _generate_union_deep_copy_helper() -> Stripped:
    """
    Generate a single ``Deep`` overload shared by every named union.

    A named union is not itself an ``Our.IClass``, so it can not be passed
    to the generic ``Deep<T>() where T : Our.IClass``. We add this second
    generic overload, next to it, so that call sites can keep calling
    ``Deep`` directly, regardless of whether the value at hand is a class
    instance or a named union.

    ``T`` is bounded by ``Our.IUnion<T>`` (see ``generate()`` in
    ``_generate_types.py``) instead of by the union's own type, so we need
    only this one overload for *all* named unions, not one per union --
    while ``T.WithUnderlying(...)`` still lets the result come back as the
    caller's own concrete union type, with no downcast needed at any
    property/list-item/tuple-item call site.

    .. note::

        The parameter is typed as ``Our.IUnion<T>``, not bare ``T``. C# does
        *not* allow overloading a generic method solely by its type
        parameter's constraint -- ``Deep<T>(T that) where T : Our.IUnion<T>``
        would be flagged as a duplicate member of the existing
        ``Deep<T>(T that) where T : Our.IClass`` above (confirmed with a
        real ``dotnet build``: CS0111). Typing the parameter itself as
        ``Our.IUnion<T>`` gives the two overloads genuinely different formal
        parameter types, which C# *does* allow, while type inference still
        resolves ``T`` to the caller's own concrete union type from the
        argument (confirmed with a real ``dotnet run``, including through a
        bare ``.Select(Deep)`` method-group conversion).

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
public static T Deep<T>(Our.IUnion<T> that) where T : Our.IUnion<T>
{{
{I}return that.WithUnderlying(
{II}Deep(that.Underlying));
}}"""
    )


def _generate_shallow_copy_transform_method(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the method in the transformer to make a shallow copy of ``cls``."""
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

    cls_name = csharp_naming.class_name(cls.name)

    if len(cls.constructor.arguments) == 0:
        return_statement = Stripped(f"return new Our.{cls_name}();")
    else:
        constructor_arg_exprs: List[str] = []
        for arg in cls.constructor.arguments:
            prop_name = csharp_naming.property_name(arg.name)
            constructor_arg_exprs.append(f"that.{prop_name}")

        # NOTE (mristin):
        # This is poor man's heuristic for line breaking, but it works fairly well
        # in practice.
        args_joined = ", ".join(constructor_arg_exprs)
        return_statement = Stripped(f"return new Our.{cls_name}({args_joined});")

        if len(return_statement) > 70:
            args_joined = ",\n".join(constructor_arg_exprs)
            return_statement = Stripped(
                f"""\
return new Our.{cls_name}(
{I}{indent_but_first_line(args_joined, I)});"""
            )

    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
public override Our.IClass {transform_name}(
{I}Our.{interface_name} that
)
{{
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
/// <summary>Dispatch the making of shallow copies.</summary>
internal class ShallowCopier : Visitation.AbstractTransformer<Our.IClass>
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal class ShallowCopier")

    return Stripped(writer.getvalue()), None


def _json_deep_copy_expr(
    type_anno: intermediate.TypeAnnotationUnion, source_expr: str
) -> Stripped:
    """
    Generate the expression deep-copying the JSON-able ``source_expr``.

    A ``System.Text.Json.Nodes.JsonNode`` can not be shared by the deep copy,
    because it remembers its parent, and attaching a node which already has
    one throws "System.InvalidOperationException: The node already has
    a parent". Sharing it would therefore make the deep copy and the original
    fight over the same node the first time either of them is put into
    a JSON document::

        var copy = Copying.Deep(instance);
        someJsonObject["a"] = instance.Value;  // attaches
        someJsonObject["b"] = copy.Value;      // throws

    ``DeepClone`` would say this in one call, but it arrived only in .NET 8
    and the generated code has to build against .NET 6, where
    ``SerializeToNode`` is the spelling of the same thing. Its return type is
    nullable only because it serializes an arbitrary value, and a null one
    gives a null node. An array and an object are known not to be null here, so
    the ``throw`` can not be reached. A JSON-able value might be a JSON null,
    which is copied as such.
    """
    item_type = csharp_common.generate_type(type_anno)

    # NOTE (mristin):
    # A JSON-able value might be a JSON null, which ``SerializeToNode`` copies
    # as a null node, so there is nothing to throw.
    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return Stripped(
            f"""\
System.Text.Json.JsonSerializer.SerializeToNode(
{I}{source_expr})"""
        )

    return Stripped(
        f"""\
({item_type})(
{I}System.Text.Json.JsonSerializer.SerializeToNode(
{II}{source_expr})
{I}?? throw new System.InvalidOperationException(
{II}"Expected SerializeToNode to copy a non-null value, "
{III}+ "but it returned null"))"""
    )


def _copied_by_sharing(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether the deep copy can share a value of ``type_anno`` with the original.

    A string, a number, a boolean and an enumeration literal are immutable,
    and a value tuple of them is copied by value. A byte array is mutable, and
    hence has to be cloned.
    """
    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return all(_copied_by_sharing(item) for item in type_anno.items)

    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return primitive_type is not intermediate.PrimitiveType.BYTEARRAY

    return isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    )


def _deep_copied_by_method(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether ``type_anno`` is deep-copied by its own method in ``Copying``.

    A list or a set of values shared by the deep copy is copied in-line by
    the copy constructor of the collection.
    """
    if not isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        return False

    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        return not _copied_by_sharing(type_anno.items)

    return not _copied_by_sharing(type_anno)


def _deep_copy_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the method of the static class ``Copying`` deep-copying ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.csharp.common.type_moniker`), so two different
    containers never share a method.
    """
    return Identifier(f"Deep_{csharp_common.type_moniker(type_anno)}")


@require(
    lambda type_anno: not isinstance(type_anno, intermediate.OptionalTypeAnnotation),
    "The optionals are unwrapped at the properties, and nested optionals "
    "have been refused in parse._translate._verify_symbol_table",
)
def _generate_deep_copy_expr(
    expr: str, type_anno: intermediate.TypeAnnotationUnion
) -> Stripped:
    """
    Generate the expression deep-copying the value at ``expr``.

    A container is delegated to its method in the static class ``Copying``,
    which copies only one level and calls the methods of its items by name.
    This way the deep copy is composed of plain functions, to any depth.
    """
    if _copied_by_sharing(type_anno):
        return Stripped(expr)

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    ):
        # NOTE (mristin):
        # A named union has its own ``Deep`` overload (see
        # :py:func:`_generate_union_deep_copy_helper`), so it can be deep-copied
        # exactly like a class instance.
        return Stripped(f"Deep({expr})")

    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return _json_deep_copy_expr(type_anno=type_anno, source_expr=expr)

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        if _deep_copied_by_method(type_anno):
            return Stripped(f"{_deep_copy_container_name(type_anno)}({expr})")

        return Stripped(f"new {csharp_common.generate_type(type_anno)}({expr})")

    assert (
        intermediate.try_primitive_type(type_anno)
        is intermediate.PrimitiveType.BYTEARRAY
    ), (
        f"Only a byte array is expected to be left to be deep-copied, "
        f"but got: {type_anno}"
    )
    return Stripped(f"(byte[]){expr}.Clone()")


@require(lambda type_anno: _deep_copied_by_method(type_anno))
def _generate_deep_copy_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the method of the static class ``Copying`` for ``type_anno``."""
    value_type = csharp_common.generate_type(type_anno)

    body: Stripped
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        item_copy_expr = _generate_deep_copy_expr(
            expr="item", type_anno=type_anno.items
        )

        add_stmt = f"result.Add({item_copy_expr});"
        if "\n" in item_copy_expr:
            add_stmt = f"""\
result.Add(
{I}{indent_but_first_line(item_copy_expr, I)});"""

        body = Stripped(
            f"""\
var result = new {value_type}(that.Count);
foreach (var item in that)
{{
{I}{indent_but_first_line(add_stmt, I)}
}}

return result;"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        tuple_literal = csharp_common.generate_tuple_literal(
            [
                _generate_deep_copy_expr(expr=f"that.Item{i + 1}", type_anno=item)
                for i, item in enumerate(type_anno.items)
            ]
        )

        body = Stripped(f"return {tuple_literal};")

    else:
        assert_never(type_anno)

    return Stripped(
        f"""\
/// <summary>
/// Make a deep copy of <paramref name="that" />.
/// </summary>
private static {value_type} {_deep_copy_container_name(type_anno)}(
{I}{value_type} that)
{{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_deep_copy_transform_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method in the transformer to make a deep copy of ``cls``."""
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

    cls_name = csharp_naming.class_name(cls.name)

    return_statement: Stripped
    if len(cls.constructor.arguments) == 0:
        return_statement = Stripped(f"return new Our.{cls_name}();")
    else:
        constructor_arg_exprs: List[str] = []
        for arg in cls.constructor.arguments:
            prop_name = csharp_naming.property_name(arg.name)

            if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
                constructor_arg_exprs.append(
                    _generate_deep_copy_expr(
                        expr=f"that.{prop_name}", type_anno=arg.type_annotation
                    )
                )
                continue

            type_anno = arg.type_annotation.value

            if _copied_by_sharing(type_anno):
                constructor_arg_exprs.append(f"that.{prop_name}")

            elif csharp_common.is_value_type(type_anno):
                # NOTE (mristin):
                # An optional of a value type, such as a tuple, is
                # a ``System.Nullable`` which has to be unwrapped. The ``null`` has
                # to be cast explicitly. Otherwise, the C# compiler can not find
                # a common type of the two branches unless the language version is
                # 9.0 or above, which we do not want to require.
                copy_expr = _generate_deep_copy_expr(
                    expr=f"that.{prop_name}.Value", type_anno=type_anno
                )
                nullable_type = csharp_common.generate_type(arg.type_annotation)

                constructor_arg_exprs.append(
                    f"""\
(that.{prop_name}.HasValue)
{I}? {indent_but_first_line(copy_expr, I)}
{I}: ({nullable_type})null"""
                )

            else:
                copy_expr = _generate_deep_copy_expr(
                    expr=f"that.{prop_name}", type_anno=type_anno
                )

                constructor_arg_exprs.append(
                    f"""\
(that.{prop_name} != null)
{I}? {indent_but_first_line(copy_expr, I)}
{I}: null"""
                )

        args_joined = ",\n".join(constructor_arg_exprs)
        return_statement = Stripped(
            f"""\
return new Our.{cls_name}(
{I}{indent_but_first_line(args_joined, I)}
);"""
        )

    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
public override Our.IClass {transform_name}(
{I}Our.{interface_name} that
)
{{
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
/// <summary>Dispatch the making of deep copies.</summary>
internal class DeepCopier : Visitation.AbstractTransformer<Our.IClass>
{"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal class DeepCopier")

    return Stripped(writer.getvalue()), None


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
    namespace: csharp_common.NamespaceIdentifier,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code for copying instances in memory.

    The ``namespace`` defines the base C# namespace of the generated code.
    """
    errors: List[Error] = []

    using_directives: List[Stripped] = []
    using_directives.extend(
        csharp_common.generate_using_our_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using System.Collections.Generic;  // can't alias"""
        )
    )

    if intermediate_uses.json_types(symbol_table):
        using_directives.append(Stripped("using Nodes = System.Text.Json.Nodes;"))

    # NOTE (mristin):
    # We wrap the shallow and deep copying in generic methods to allow for easier
    # enforcement of runtime type safety for the client. Otherwise, if we directly
    # provided the transformer, the client would always need to make the casts, which
    # is cumbersome.

    copy_blocks: List[Stripped] = [
        Stripped(
            f"""\
private static readonly ShallowCopier ShallowCopierInstance = (
{I}new ShallowCopier());"""
        ),
        Stripped(
            f"""\
private static readonly DeepCopier DeepCopierInstance = (
{I}new DeepCopier());"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Make a shallow copy of <paramref name="that" />.
/// </summary>
/// <remarks>
/// All the properties are copied by reference. This includes also the lists.
/// Hence, a list property is copied by reference, and not, as sometimes might be
/// expected, as a new list of underlying references.
/// </remarks>.
/// <param name="that">to be copied in a shallow manner</param>
/// <typeparam name="T">type to cast the result to</typeparam>
public static T Shallow<T>(T that) where T : Our.IClass
{{
{I}return (T)ShallowCopierInstance.Transform(that);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Make a recursively a deep copy of <paramref name="that" />.
/// </summary>
/// <param name="that">to be deeply copied in a recursive manner</param>
/// <typeparam name="T">type to cast the result to</typeparam>
public static T Deep<T>(T that) where T : Our.IClass
{{
{I}return (T)DeepCopierInstance.Transform(that);
}}"""
        ),
    ]

    if len(symbol_table.named_unions) > 0:
        copy_blocks.append(_generate_union_deep_copy_helper())

    observed_monikers: Set[str] = set()
    for cls in symbol_table.concrete_classes:
        for arg in cls.constructor.arguments:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                arg.type_annotation
            ):
                if not _deep_copied_by_method(type_anno):
                    continue

                assert isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                )

                moniker = csharp_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)

                copy_blocks.append(_generate_deep_copy_container(type_anno))

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
/// <summary>
/// Allow for making shallow and deep copies of model instances.
/// </summary>
public static class Copying
{
"""
    )

    for i, copy_block in enumerate(copy_blocks):
        if i > 0:
            copying_writer.write("\n\n")

        copying_writer.write(textwrap.indent(copy_block, I))

    copying_writer.write("\n}  // public static class Copying")

    blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(
            f"""\
namespace {namespace}
{{
{I}{indent_but_first_line(copying_writer.getvalue(), I)}
}}  // namespace {namespace}"""
        ),
        csharp_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
