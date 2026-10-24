"""Generate code to test copying."""

import io
import textwrap
from typing import List, Set

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    assert_never,
    Identifier,
)
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import INDENT as I, INDENT2 as II, INDENT3 as III
from aas_core_codegen.intermediate import uses as intermediate_uses


def _generate_shallow_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the code for a static shallow ``Equals`` method."""
    exprs: List[str] = []
    for prop in cls.properties:
        prop_name = csharp_naming.property_name(prop.name)
        exprs.append(f"that.{prop_name} == other.{prop_name}")

    if len(exprs) == 0:
        # NOTE (mristin):
        # There are no properties to compare, so the instances are trivially
        # shallowly equal.
        statement = Stripped("return true;")
    # NOTE (mristin):
    # This is a poor man's line re-flowing.
    elif len(" && ".join(exprs)) < 70:
        statement = Stripped(f"return {' && '.join(exprs)};")
    else:
        exprs_joined = "\n&& ".join(exprs)
        statement = Stripped(
            f"""\
return (
{I}{indent_but_first_line(exprs_joined, I)});"""
        )

    cls_name_csharp = csharp_naming.class_name(cls.name)

    return Stripped(
        f"""\
private static bool {cls_name_csharp}ShallowEquals(
{I}Our.{cls_name_csharp} that,
{I}Our.{cls_name_csharp} other)
{{
{I}{indent_but_first_line(statement, I)}
}}"""
    )


def _check_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the method of the ``DeepCopyChecker`` checking the copy of ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.csharp.common.type_moniker`), so two different
    containers never share a method.
    """
    return Identifier(f"Check_{csharp_common.type_moniker(type_anno)}")


@require(
    lambda type_anno: not isinstance(type_anno, intermediate.OptionalTypeAnnotation),
    "The optionals are unwrapped at the properties, and nested optionals "
    "have been refused in parse._translate._verify_symbol_table",
)
def _generate_check_expr(
    that_expr: str, other_expr: str, type_anno: intermediate.TypeAnnotationUnion
) -> Stripped:
    """
    Generate the expression checking that ``other_expr`` is a deep copy of ``that_expr``.

    A container is delegated to its method in the ``DeepCopyChecker``, which
    checks only one level and calls the checks of its items by name.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Stripped(
            f"""\
BytesEqualButDistinct(
{I}{that_expr},
{I}{other_expr})"""
        )

    if primitive_type is not None or (
        isinstance(type_anno, intermediate.OurTypeAnnotation)
        and isinstance(type_anno.our_type, intermediate.Enumeration)
    ):
        return Stripped(f"{that_expr} == {other_expr}")

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        # NOTE (mristin):
        # Only the classes and the named unions are left here. A named union has
        # its own ``Transform`` overload (see
        # :py:func:`_generate_union_transform_helper`), so it is checked exactly
        # like a class instance.
        return Stripped(
            f"""\
Transform(
{I}{that_expr},
{I}{other_expr})"""
        )

    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return Stripped(
            f"""\
JsonNodesEqualButDistinct(
{I}{that_expr},
{I}{other_expr})"""
        )

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        return Stripped(
            f"""\
{_check_container_name(type_anno)}(
{I}{that_expr},
{I}{other_expr})"""
        )

    raise AssertionError(f"Unexpected type annotation: {type_anno}")


def _generate_check_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the method of the ``DeepCopyChecker`` for ``type_anno``."""
    body: Stripped
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_check = _generate_check_expr(
            that_expr="that[i]", other_expr="other[i]", type_anno=type_anno.items
        )

        body = Stripped(
            f"""\
if (ReferenceEquals(that, other) || that.Count != other.Count)
{{
{I}return false;
}}

for (int i = 0; i < that.Count; i++)
{{
{I}if (!(
{II}{indent_but_first_line(item_check, II)}))
{I}{{
{II}return false;
{I}}}
}}

return true;"""
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        # NOTE (mristin):
        # A set holds only primitives, constrained primitives and enumeration
        # literals, which all compare by value.
        assert (
            intermediate.try_primitive_type(type_anno.items)
            is not intermediate.PrimitiveType.BYTEARRAY
        ), f"Unexpected set of byte arrays: {type_anno}"

        body = Stripped(
            "return !ReferenceEquals(that, other) && that.SetEquals(other);"
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # A tuple is a ``System.ValueTuple``, which is always copied by value, so
        # we check only its items.
        item_checks = "\n&& ".join(
            _generate_check_expr(
                that_expr=f"that.Item{i + 1}",
                other_expr=f"other.Item{i + 1}",
                type_anno=item,
            )
            for i, item in enumerate(type_anno.items)
        )

        body = Stripped(
            f"""\
return (
{I}{indent_but_first_line(item_checks, I)});"""
        )

    else:
        assert_never(type_anno)

    value_type = csharp_common.generate_type(
        type_anno, our_type_qualifier=Stripped("Our")
    )

    return Stripped(
        f"""\
private bool {_check_container_name(type_anno)}(
{I}{value_type} that,
{I}{value_type} other)
{{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_transform_as_check(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the transform method checking the deep copy of ``cls``."""
    exprs: List[Stripped] = []

    for prop in cls.properties:
        prop_name = csharp_naming.property_name(prop.name)

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            exprs.append(
                _generate_check_expr(
                    that_expr=f"that.{prop_name}",
                    other_expr=f"casted.{prop_name}",
                    type_anno=prop.type_annotation,
                )
            )
            continue

        type_anno = prop.type_annotation.value

        # NOTE (mristin):
        # An optional of a value type is a ``System.Nullable``, which is probed
        # with ``HasValue`` and unwrapped with ``Value``.
        if csharp_common.is_value_type(type_anno):
            if not isinstance(type_anno, intermediate.TupleTypeAnnotation):
                # NOTE (mristin):
                # A ``System.Nullable`` of a primitive or an enumeration compares by
                # value, including the absence.
                exprs.append(Stripped(f"that.{prop_name} == casted.{prop_name}"))
                continue

            that_present = f"that.{prop_name}.HasValue"
            casted_present = f"casted.{prop_name}.HasValue"
            that_absent = f"!that.{prop_name}.HasValue"
            casted_absent = f"!casted.{prop_name}.HasValue"
            that_value = f"that.{prop_name}.Value"
            casted_value = f"casted.{prop_name}.Value"
        else:
            that_present = f"that.{prop_name} != null"
            casted_present = f"casted.{prop_name} != null"
            that_absent = f"that.{prop_name} == null"
            casted_absent = f"casted.{prop_name} == null"
            that_value = f"that.{prop_name}"
            casted_value = f"casted.{prop_name}"

        check = _generate_check_expr(
            that_expr=that_value, other_expr=casted_value, type_anno=type_anno
        )

        # NOTE (mristin):
        # The conditional has to be parenthesized. Otherwise, it would swallow
        # the conjunction of all the preceding properties into its condition
        # as the conditional operator binds weaker than the conjunction.
        exprs.append(
            Stripped(
                f"""\
(({that_present} && {casted_present})
{I}? {indent_but_first_line(check, I)}
{I}: {that_absent} && {casted_absent})"""
            )
        )

    if len(exprs) == 0:
        # NOTE (mristin):
        # There are no properties to compare, so the copy is trivially deep as soon
        # as it is a distinct instance of the expected concrete type.
        return_statement = Stripped("return true;")
    else:
        exprs_joined = "\n&& ".join(exprs)
        return_statement = Stripped(
            f"""\
return (
{I}{indent_but_first_line(exprs_joined, I)});"""
        )

    cls_name = csharp_naming.class_name(cls.name)
    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
public override bool {transform_name}(
{I}Our.{interface_name} that,
{I}Our.IClass other)
{{
{I}if (!(other is Our.{cls_name} casted) || ReferenceEquals(that, other))
{I}{{
{II}return false;
{I}}}

{I}{indent_but_first_line(return_statement, I)}
}}"""
    )


def _generate_union_transform_helper() -> Stripped:
    """
    Generate a single ``Transform`` overload shared by every named union.

    A named union is not itself an ``Our.IClass``, so it can not be dispatched
    by the inherited, ``Our.IClass``-typed ``Transform`` overload. We add
    this overload, single-purpose and non-virtual, so that call sites can
    keep calling ``Transform`` directly, regardless of whether the value at
    hand is a class instance or a named union.

    Dispatching over the common, non-generic ``Our.IUnion`` (see ``generate()``
    in ``_generate_types.py``) instead of the union's own type means we need
    only this one overload for *all* named unions, not one per union -- the
    result is a plain ``bool``, so there is no return type to preserve.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
private bool Transform(Our.IUnion that, Our.IUnion other)
{{
{I}return Transform(that.Underlying, other.Underlying);
}}"""
    )


def _generate_deep_copy_checker(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """
    Generate the transformer checking that a deep copy holds its own objects.

    The copy has to equal the original by value, while it must share none of
    the mutable objects with it, *i.e.*, no instance, list, set, byte array
    or JSON node.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
private static bool BytesEqualButDistinct(
{I}byte[] that,
{I}byte[] other)
{{
{I}// NOTE (mristin):
{I}// A byte[] implicitly converts to a ReadOnlySpan, which compares by content.
{I}// See: https://stackoverflow.com/a/48599119/1600678
{I}return (
{II}!ReferenceEquals(that, other)
{II}&& ((System.ReadOnlySpan<byte>)that).SequenceEqual(other));
}}"""
        ),
    ]

    if intermediate_uses.json_types(symbol_table):
        blocks.append(
            Stripped(
                f"""\
private static bool JsonNodesEqualButDistinct(
{I}Nodes.JsonNode that,
{I}Nodes.JsonNode other)
{{
{I}// NOTE (mristin):
{I}// A JsonNode compares only by reference, so we compare the canonical
{I}// JSON text.
{I}return (
{II}!ReferenceEquals(that, other)
{II}&& that.ToJsonString() == other.ToJsonString());
}}"""
            )
        )

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_transform_as_check(cls=concrete_cls))

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_union_transform_helper())

    observed_monikers: Set[str] = set()
    for concrete_cls in symbol_table.concrete_classes:
        for prop in concrete_cls.properties:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ):
                    continue

                moniker = csharp_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)

                blocks.append(_generate_check_container(type_anno))

    blocks_joined = "\n\n".join(blocks)

    return Stripped(
        f"""\
/// <summary>
/// Check that the context is a deep copy of the visited instance.
/// </summary>
/// <remarks>
/// The copy has to equal the original by value, while it must share none
/// of the mutable objects with it.
/// </remarks>
internal class DeepCopyChecker
{I}: Our.Visitation.AbstractTransformerWithContext<Our.IClass, bool>
{{
{I}{indent_but_first_line(blocks_joined, I)}
}}  // internal class DeepCopyChecker"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    namespace: csharp_common.NamespaceIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> str:
    """
    Generate code to test copying.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = [
        _generate_deep_copy_checker(symbol_table=symbol_table),
        Stripped(
            f"""\
private static readonly DeepCopyChecker DeepCopyCheckerInstance = (
{I}new DeepCopyChecker());"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_shallow_equals(cls=concrete_cls))

    for concrete_cls in symbol_table.concrete_classes:
        cls_name = csharp_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name}_shallow_copy()
{{
{I}Our.{cls_name} instance = (
{II}Our.Tests.CommonJsonization.LoadMaximal{cls_name}());

{I}var instanceCopy = Our.Copying.Shallow(instance);

{I}Assert.IsTrue(
{II}{cls_name}ShallowEquals(
{III}instance, instanceCopy),
{II}{csharp_common.string_literal(cls_name)});
}}  // public void Test_{cls_name}_shallow_copy"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name}_deep_copy()
{{
{I}Our.{cls_name} instance = (
{II}Our.Tests.CommonJsonization.LoadMaximal{cls_name}());

{I}var instanceCopy = Our.Copying.Deep(instance);

{I}Assert.IsTrue(
{II}DeepCopyCheckerInstance.Transform(
{III}instance, instanceCopy),
{II}{csharp_common.string_literal(cls_name)});
}}  // public void Test_{cls_name}_deep_copy"""
            )
        )

    using_directives: List[Stripped] = [
        Stripped(f"using Our = {namespace};  // renamed"),
        Stripped(
            """\
// We need to use System.MemoryExtension.SequenceEqual.
using System;  // can't alias
using System.Collections.Generic;  // can't alias"""
        ),
    ]

    if intermediate_uses.json_types(symbol_table):
        using_directives.append(Stripped("using Nodes = System.Text.Json.Nodes;"))

    using_directives.append(Stripped("using NUnit.Framework;  // can't alias"))

    using_directives_joined = "\n\n".join(using_directives)

    writer = io.StringIO()
    writer.write(
        f"""\
{csharp_common.WARNING}

{using_directives_joined}

namespace {namespace}.Tests
{{
{I}public class TestCopying
{I}{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, II))

    writer.write(
        f"""
{I}}}  // class TestCopying
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""
    )

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
