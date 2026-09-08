"""Generate code to test copying."""

import io
import textwrap
from typing import List, Optional

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    assert_never,
    Identifier,
)
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import INDENT as I, INDENT2 as II, INDENT3 as III


def _generate_shallow_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the code for a static shallow ``Equals`` method."""
    if cls.is_implementation_specific:
        raise AssertionError(
            f"(mristin): "
            f"The class {cls.name!r} is implementation specific. "
            f"At the moment, we assume that all classes are not "
            f"implementation-specific, so that we can automatically generate the "
            f"shallow-equals methods. This way we can dispense of the whole "
            f"snippet/specific-implementation loading logic in "
            f"the unit test generation. Please notify the developers if you see this, "
            f"so that we can add the logic for implementation-specific classes "
            f"to this generation script."
        )

    exprs = []  # type: List[str]
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
{I}Aas.{cls_name_csharp} that,
{I}Aas.{cls_name_csharp} other)
{{
{I}{indent_but_first_line(statement, I)}
}}"""
    )


def _generate_transform_as_deep_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the transform method that checks for deep equality."""
    if cls.is_implementation_specific:
        raise AssertionError(
            f"(mristin): "
            f"The class {cls.name!r} is implementation specific. "
            f"At the moment, we assume that all classes are not "
            f"implementation-specific, so that we can automatically generate the "
            f"shallow-equals methods. This way we can dispense of the whole "
            f"snippet/specific-implementation loading logic in "
            f"the unit test generation. Please notify the developers if you see this, "
            f"so that we can add the logic for implementation-specific classes "
            f"to this generation script."
        )

    cls_name = csharp_naming.class_name(cls.name)

    exprs = []  # type: List[Stripped]

    for prop in cls.properties:
        optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_name = csharp_naming.property_name(prop.name)

        expr = None  # type: Optional[Stripped]

        primitive_type = intermediate.try_primitive_type(type_anno)

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive)
        ):
            assert primitive_type is not None
            if (
                primitive_type is intermediate.PrimitiveType.BOOL
                or primitive_type is intermediate.PrimitiveType.INT
                or primitive_type is intermediate.PrimitiveType.FLOAT
                or primitive_type is intermediate.PrimitiveType.STR
            ):
                expr = Stripped(f"that.{prop_name} == casted.{prop_name}")
            elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                expr = Stripped(
                    f"""\
ByteSpansEqual(
{I}that.{prop_name},
{I}casted.{prop_name})"""
                )
            else:
                # noinspection PyTypeChecker
                assert_never(primitive_type)

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                expr = Stripped(f"that.{prop_name} == casted.{prop_name}")
            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError("Expected to handle this case above")
            elif isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                expr = Stripped(
                    f"""\
Transform(
{I}that.{prop_name},
{I}casted.{prop_name})"""
                )
            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.our_type)
        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            items_primitive_type = intermediate.try_primitive_type(type_anno.items)

            if items_primitive_type is not None:
                # NOTE (mristin):
                # Mypy 2.1.0 still struggled with ``in`` operator.
                # pylint: disable=consider-using-in
                if (
                    items_primitive_type == intermediate.PrimitiveType.BOOL
                    or items_primitive_type == intermediate.PrimitiveType.INT
                    or items_primitive_type == intermediate.PrimitiveType.FLOAT
                    or items_primitive_type == intermediate.PrimitiveType.STR
                ):
                    expr = Stripped(
                        f"""\
that.{prop_name}.SequenceEqual(
{I}casted.{prop_name})"""
                    )
                elif items_primitive_type == intermediate.PrimitiveType.BYTEARRAY:
                    expr = Stripped(
                        f"""\
that.{prop_name}.Count == casted.{prop_name}.Count
&& (
{I}that.{prop_name}
{II}.Zip(
{III}casted.{prop_name},
{III}(left, right) => ByteSpansEqual(left, right))
{II}.All(item => item))"""
                    )
                else:
                    assert_never(items_primitive_type)

            elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                    expr = Stripped(
                        f"""\
that.{prop_name}.SequenceEqual(
{I}casted.{prop_name})"""
                    )
                elif isinstance(
                    type_anno.items.our_type, intermediate.ConstrainedPrimitive
                ):
                    raise AssertionError("Expected to handle this case above")

                elif isinstance(
                    type_anno.items.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    expr = Stripped(
                        f"""\
that.{prop_name}.Count == casted.{prop_name}.Count
&& (
{I}that.{prop_name}
{II}.Zip(
{III}casted.{prop_name},
{III}Transform)
{II}.All(item => item))"""
                    )
                else:
                    assert_never(type_anno.items.our_type)
            else:
                raise NotImplementedError(
                    f"(mristin): We handle only lists of atomic values in the deep "
                    f"equality checks at the moment. The meta-model does not contain "
                    f"any other lists, so we wanted to keep the code as simple as "
                    f"possible, and avoid unrolling. Please contact the developers "
                    f"if you need this feature. The class in question was {cls.name!r} "
                    f"and the property {prop.name!r}."
                )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_exprs = []  # type: List[Stripped]

            for i, item_type_anno in enumerate(type_anno.items):
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    f"Expected an atomic tuple item (a primitive, a constrained "
                    f"primitive, an enumeration or a class), but got {item_type_anno}. "
                    f"This should have already been verified in "
                    f"intermediate._translate._verify_only_simple_type_patterns."
                )

                item_that = f"that.{prop_name}.Item{i + 1}"
                item_casted = f"casted.{prop_name}.Item{i + 1}"

                item_primitive_type = intermediate.try_primitive_type(item_type_anno)

                if item_primitive_type is not None:
                    # NOTE (mristin):
                    # Mypy 2.1.0 still struggled with ``in`` operator.
                    # pylint: disable=consider-using-in
                    if (
                        item_primitive_type == intermediate.PrimitiveType.BOOL
                        or item_primitive_type == intermediate.PrimitiveType.INT
                        or item_primitive_type == intermediate.PrimitiveType.FLOAT
                        or item_primitive_type == intermediate.PrimitiveType.STR
                    ):
                        item_exprs.append(Stripped(f"{item_that} == {item_casted}"))
                    elif item_primitive_type == intermediate.PrimitiveType.BYTEARRAY:
                        item_exprs.append(
                            Stripped(
                                f"""\
ByteSpansEqual(
{I}{item_that},
{I}{item_casted})"""
                            )
                        )
                    else:
                        assert_never(item_primitive_type)
                elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                    if isinstance(item_type_anno.our_type, intermediate.Enumeration):
                        item_exprs.append(Stripped(f"{item_that} == {item_casted}"))
                    elif isinstance(
                        item_type_anno.our_type, intermediate.ConstrainedPrimitive
                    ):
                        raise AssertionError("Expected to handle this case above")
                    elif isinstance(
                        item_type_anno.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    ):
                        item_exprs.append(
                            Stripped(
                                f"""\
Transform(
{I}{item_that},
{I}{item_casted})"""
                            )
                        )
                    else:
                        assert_never(item_type_anno.our_type)
                else:
                    # NOTE (mristin):
                    # This branch is unreachable in practice (``item_type_anno`` is
                    # a ``PrimitiveTypeAnnotation`` here, and ``try_primitive_type``
                    # always resolves those to a non-``None`` primitive type), but
                    # mypy can not correlate the ``try_primitive_type`` call with
                    # the ``isinstance`` narrowing above, so we can not use
                    # ``assert_never`` here.
                    raise AssertionError(
                        f"Expected to handle this case above: {item_type_anno}"
                    )

            item_exprs_writer = io.StringIO()
            item_exprs_writer.write("(")
            for i, item_expr in enumerate(item_exprs):
                item_exprs_writer.write("\n")
                if i > 0:
                    item_exprs_writer.write(
                        f"{I}&& {indent_but_first_line(item_expr, I)}"
                    )
                else:
                    item_exprs_writer.write(f"{I}{indent_but_first_line(item_expr, I)}")
            item_exprs_writer.write(")")

            expr = Stripped(item_exprs_writer.getvalue())

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

        if optional and primitive_type is None:
            expr = Stripped(
                f"""\
(that.{prop_name} != null && casted.{prop_name} != null)
{I}? {indent_but_first_line(expr, II)}
{I}: that.{prop_name} == null && casted.{prop_name} == null"""
            )

        exprs.append(expr)

    body_writer = io.StringIO()
    if len(exprs) == 0:
        # NOTE (mristin):
        # There are no properties to compare, so the instances are trivially
        # deeply equal as soon as we know ``other`` is of the expected concrete
        # type (which we already checked above).
        body_writer.write("return true;")
    else:
        body_writer.write("return (")
        for i, expr in enumerate(exprs):
            body_writer.write("\n")
            if i > 0:
                body_writer.write(f"{I}&& {indent_but_first_line(expr, I)}")
            else:
                body_writer.write(f"{I}{indent_but_first_line(expr, I)}")

        body_writer.write(");")

    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
public override bool {transform_name}(
{I}Aas.{interface_name} that,
{I}Aas.IClass other)
{{
{I}if (!(other is Aas.{cls_name} casted))
{I}{{
{II}return false;
{I}}}

{I}{indent_but_first_line(body_writer.getvalue(), I)}
}}"""
    )


def _generate_deep_equals_transformer(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the transformer that checks for deep equality."""
    blocks = [
        Stripped(
            f"""\
/// <summary>Compare two byte spans for equal content.</summary>
/// <remarks>
/// <c>byte[]</c> implicitly converts to <c>ReadOnlySpan</c>.
/// See: https://stackoverflow.com/a/48599119/1600678
/// </remarks>
private static bool ByteSpansEqual(
{I}System.ReadOnlySpan<byte> that,
{I}System.ReadOnlySpan<byte> other)
{{
{I}return that.SequenceEqual(other);
}}"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        if concrete_cls.is_implementation_specific:
            raise AssertionError(
                f"(mristin): "
                f"The class {concrete_cls.name!r} is implementation specific. "
                f"At the moment, we assume that all classes are not "
                f"implementation-specific, so that we can automatically generate the "
                f"deep-equals methods. This way we can dispense of the whole "
                f"snippet/specific-implementation loading logic in "
                f"the unit test generation. Please notify the developers if you see "
                f"this, so that we can add the logic for implementation-specific "
                f"classes to this generation script."
            )

        blocks.append(_generate_transform_as_deep_equals(cls=concrete_cls))

    writer = io.StringIO()
    writer.write(
        f"""\
internal class DeepEqualiser
{I}: Aas.Visitation.AbstractTransformerWithContext<Aas.IClass, bool>
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal class DeepEqualiser")

    return Stripped(writer.getvalue())


def _generate_deep_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the code for a static deep ``Equals`` method."""
    if cls.is_implementation_specific:
        raise AssertionError(
            f"(mristin): "
            f"The class {cls.name!r} is implementation specific. "
            f"At the moment, we assume that all classes are not "
            f"implementation-specific, so that we can automatically generate the "
            f"shallow-equals methods. This way we can dispense of the whole "
            f"snippet/specific-implementation loading logic in "
            f"the unit test generation. Please notify the developers if you see this, "
            f"so that we can add the logic for implementation-specific classes "
            f"to this generation script."
        )

    cls_name = csharp_naming.class_name(cls.name)

    return Stripped(
        f"""\
private static bool {cls_name}DeepEquals(
{I}Aas.{cls_name} that,
{I}Aas.{cls_name} other)
{{
{I}return DeepEqualiserInstance.Transform(that, other);
}}"""
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
    blocks = [
        _generate_deep_equals_transformer(symbol_table=symbol_table),
        Stripped(
            """\
private static readonly DeepEqualiser DeepEqualiserInstance = new DeepEqualiser();"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_shallow_equals(cls=concrete_cls))

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_deep_equals(cls=concrete_cls))

    for concrete_cls in symbol_table.concrete_classes:
        cls_name = csharp_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name}_shallow_copy()
{{
{I}Aas.{cls_name} instance = (
{II}Aas.Tests.CommonJsonization.LoadMaximal{cls_name}());

{I}var instanceCopy = Aas.Copying.Shallow(instance);

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
{I}Aas.{cls_name} instance = (
{II}Aas.Tests.CommonJsonization.LoadMaximal{cls_name}());

{I}var instanceCopy = Aas.Copying.Deep(instance);

{I}Assert.IsTrue(
{II}{cls_name}DeepEquals(
{III}instance, instanceCopy),
{II}{csharp_common.string_literal(cls_name)});
}}  // public void Test_{cls_name}_deep_copy"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
{csharp_common.WARNING}

using Aas = {namespace};  // renamed

// We need to use System.MemoryExtension.SequenceEqual.
using System;  // can't alias
using System.Linq;  // can't alias

using NUnit.Framework;  // can't alias

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
