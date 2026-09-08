"""Generate code to test copying."""

import io
import textwrap
from typing import List, Optional

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    assert_never,
    Identifier,
)
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import INDENT as I, INDENT2 as II, INDENT3 as III


def _generate_shallow_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the code for a static shallow ``Equals`` method."""
    if cls.is_implementation_specific:
        raise AssertionError(
            f"(empwilli):"
            f"the class {cls.name!r} is implementation specific. "
            f"at the moment, we assume that all classes are not "
            f"implementation-specific, so that we can automatically generate the "
            f"shallow-equals methods. this way we can dispense of the whole "
            f"snippet/specific-implementation loading logic in "
            f"the unit test generation. please notify the developers if you see this, "
            f"so that we can add the logic for implementation-specific classes "
            f"to this generation script."
        )

    exprs = []  # type: List[str]
    for prop in cls.properties:
        prop_name = java_naming.method_name(Identifier(f"get_{prop.name}"))
        exprs.append(f"that.{prop_name}().equals(other.{prop_name}())")

    if len(exprs) == 0:
        # NOTE (mristin):
        # There are no properties to compare, so the instances are trivially
        # shallowly equal.
        statement = Stripped("return true;")
    # NOTE (empwilli):
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

    cls_name_java = java_naming.class_name(cls.name)

    return Stripped(
        f"""\
private static Boolean {cls_name_java}ShallowEquals(
{I}{cls_name_java} that,
{I}{cls_name_java} other) {{
{I}{indent_but_first_line(statement, I)}
}}"""
    )


def _generate_transform_as_deep_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the transform method that checks for deep equality."""
    if cls.is_implementation_specific:
        raise AssertionError(
            f"(empwilli): "
            f"The class {cls.name!r} is implementation specific. "
            f"At the moment, we assume that all classes are not "
            f"implementation-specific, so that we can automatically generate the "
            f"shallow-equals methods. This way we can dispense of the whole "
            f"snippet/specific-implementation loading logic in "
            f"the unit test generation. Please notify the developers if you see this, "
            f"so that we can add the logic for implementation-specific classes "
            f"to this generation script."
        )

    cls_name = java_naming.class_name(cls.name)

    exprs = []  # type: List[Stripped]

    for prop in cls.properties:
        optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        type_anno = intermediate.beneath_optional(prop.type_annotation)
        getter_name = java_naming.getter_name(prop.name)
        primitive_type = intermediate.try_primitive_type(type_anno)

        expr = None  # type: Optional[Stripped]

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
                expr = Stripped(
                    f"""\
that.{getter_name}().equals(casted.{getter_name}())"""
                )
            elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                if optional:
                    expr = Stripped(
                        f"""\
Arrays.equals(
{I}that.{getter_name}().get(),
{I}casted.{getter_name}().get())"""
                    )
                else:
                    expr = Stripped(
                        f"""\
Arrays.equals(
{I}that.{getter_name}(),
{I}casted.{getter_name}())"""
                    )
            else:
                assert_never(primitive_type)

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                expr = Stripped(
                    f"""\
that.{getter_name}().equals(casted.{getter_name}())"""
                )
            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError("Expected to handle this case above")
            elif isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                if optional:
                    expr = Stripped(
                        f"""\
(that.{getter_name}().isPresent()
{I}? casted.{getter_name}().isPresent()
{I}&& transform( that.{getter_name}().get(), casted.{getter_name}().get())
{I}: ! casted.{getter_name}().isPresent())"""
                    )
                else:
                    expr = Stripped(
                        f"""\
transform(
{I}that.{getter_name}(),
{I}casted.{getter_name}())"""
                    )
        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert not isinstance(
                type_anno.items,
                (intermediate.OptionalTypeAnnotation, intermediate.ListTypeAnnotation),
            ), (
                f"(mristin): We handle only lists of atomic values (primitives, "
                f"constrained primitives, enumeration literals) or lists of "
                f"classes in the deep equality checks at the moment. Lists of "
                f"lists or lists of optionals are not supported. Please contact "
                f"the developers if you need this feature. The class in "
                f"question was {cls.name!r} and the property {prop.name!r}."
            )

            item_primitive_type = intermediate.try_primitive_type(type_anno.items)

            if item_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                # NOTE (mristin):
                # ``byte[]`` does not override ``equals`` to compare content, so
                # ``List.equals`` would compare the arrays by reference. We zip
                # the two lists and compare each pair of byte arrays with
                # ``Arrays.equals`` instead.
                expr = Stripped(
                    f"""\
(that.{getter_name}().size() == casted.{getter_name}().size()
{I}&& zip(that.{getter_name}().stream(), casted.{getter_name}().stream())
{II}.allMatch(pair -> Arrays.equals(pair.getFirst(), pair.getSecond())))"""
                )
            else:
                # NOTE (mristin):
                # For lists of other primitives, constrained primitives or
                # enumeration literals, the items are compared by value with
                # their own ``equals`` method, so ``List.equals`` is sufficient.
                expr = Stripped(
                    f"""\
that.{getter_name}().equals(casted.{getter_name}())"""
                )
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_exprs = []  # type: List[Stripped]

            for i, item_type_anno in enumerate(type_anno.items):
                that_item = f"that.{getter_name}().item{i + 1}()"
                casted_item = f"casted.{getter_name}().item{i + 1}()"

                if optional:
                    that_item = f"that.{getter_name}().get().item{i + 1}()"
                    casted_item = f"casted.{getter_name}().get().item{i + 1}()"

                item_primitive_type = intermediate.try_primitive_type(item_type_anno)

                if isinstance(
                    item_type_anno, intermediate.OurTypeAnnotation
                ) and isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    item_exprs.append(
                        Stripped(
                            f"""\
transform(
{I}{that_item},
{I}{casted_item})"""
                        )
                    )
                elif item_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                    item_exprs.append(
                        Stripped(
                            f"""\
Arrays.equals(
{I}{that_item},
{I}{casted_item})"""
                        )
                    )
                else:
                    item_exprs.append(Stripped(f"{that_item}.equals({casted_item})"))

            items_joined = "\n&& ".join(item_exprs)

            tuple_expr = Stripped(
                f"""\
({indent_but_first_line(items_joined, I)})"""
            )

            if optional:
                expr = Stripped(
                    f"""\
(that.{getter_name}().isPresent()
{I}? casted.{getter_name}().isPresent()
{I}&& {indent_but_first_line(tuple_expr, I)}
{I}: ! casted.{getter_name}().isPresent())"""
                )
            else:
                expr = tuple_expr
        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

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

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
@Override
public Boolean {transform_name}({interface_name} that, IClass other) {{
{I}if (!(other instanceof {cls_name})) {{
{II}return false;
{I}}}

{I}{cls_name} casted = ({cls_name}) that;

{I}{indent_but_first_line(body_writer.getvalue(), I)}
}}"""
    )


def _generate_deep_equals_transformer(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the transformer that checks for deep equality."""
    blocks = []  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        if concrete_cls.is_implementation_specific:
            raise AssertionError(
                f"(empwilli): "
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
        """\
private static class _DeepEqualiser extends AbstractTransformerWithContext<IClass, Boolean> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n} // class _DeepEqualiser")

    return Stripped(writer.getvalue())


def _generate_deep_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the code for a static deep ``Equals`` method."""
    if cls.is_implementation_specific:
        raise AssertionError(
            f"(empwilli): "
            f"The class {cls.name!r} is implementation specific. "
            f"At the moment, we assume that all classes are not "
            f"implementation-specific, so that we can automatically generate the "
            f"shallow-equals methods. This way we can dispense of the whole "
            f"snippet/specific-implementation loading logic in "
            f"the unit test generation. Please notify the developers if you see this, "
            f"so that we can add the logic for implementation-specific classes "
            f"to this generation script."
        )

    cls_name = java_naming.class_name(cls.name)

    return Stripped(
        f"""\
private static Boolean {cls_name}DeepEquals({cls_name} that, {cls_name} other) {{
{I}return DeepEqualiserInstance.transform(that, other);
}}"""
    )


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test copying.
    """
    blocks = [
        _generate_deep_equals_transformer(symbol_table=symbol_table),
        Stripped(
            """\
private static final _DeepEqualiser DeepEqualiserInstance = new _DeepEqualiser();"""
        ),
        Stripped(
            f"""\
/**
 * Compare two byte spans for equal content.
 */
private static Boolean byteSpansEqual(byte[] that, byte[] other) {{
{I}return that.equals(other);
}}"""
        ),
        Stripped(
            f"""\
private static class _Pair<A, B> {{
{I}private final A first;
{I}private final B second;
{I}
{I}public _Pair(A first, B second) {{
{II}this.first = first;
{II}this.second = second;
{I}}}
{I}
{I}public A getFirst() {{
{II}return first;
{I}}}
{I}
{I}public B getSecond() {{
{II}return second;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Java 8 doesn't provide a zip operation out of the box, so we have to ship our own.
// Adapted from: https://stackoverflow.com/a/23529010
private static <A, B> Stream<_Pair<A, B>> zip(
{I}Stream<? extends A> a,
{I}Stream<? extends B> b) {{
{I}Spliterator<? extends A> aSplit = Objects.requireNonNull(a).spliterator();
{I}Spliterator<? extends B> bSplit = Objects.requireNonNull(b).spliterator();
{I}
{I}int characteristics = aSplit.characteristics() & bSplit.characteristics() &
{II}~(Spliterator.DISTINCT | Spliterator.SORTED);
{I}
{I}long zipSize = ((characteristics & Spliterator.SIZED) != 0)
{II}? Math.min(aSplit.getExactSizeIfKnown(), bSplit.getExactSizeIfKnown())
{II}: -1;
{I}
{I}Iterator<A> aIter = Spliterators.iterator(aSplit);
{I}Iterator<B> bIter = Spliterators.iterator(bSplit);
{I}Iterator<_Pair<A, B>> cIter = new Iterator<_Pair<A, B>>() {{
{II}@Override
{II}public boolean hasNext() {{
{III}return aIter.hasNext() && bIter.hasNext();
{II}}}
{II}
{II}@Override
{II}public _Pair<A, B> next() {{
{III}return new _Pair<>(aIter.next(), bIter.next());
{II}}}
{I}}};
{I}
{I}Spliterator<_Pair<A, B>> split = Spliterators.spliterator(cIter, zipSize, characteristics);
{I}return StreamSupport.stream(split, false);
}}"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_shallow_equals(cls=concrete_cls))

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_deep_equals(cls=concrete_cls))

    for concrete_cls in symbol_table.concrete_classes:
        cls_name = java_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name}ShallowCopy() throws IOException {{
{I}final {cls_name} instance = CommonJsonization.loadMaximal{cls_name}();
{I}final {cls_name} instanceCopy = Copying.shallow(instance);

{I}assertTrue(
{II}{cls_name}ShallowEquals(instance, instanceCopy),
{II}{java_common.string_literal(cls_name)});
}} // public void test{cls_name}ShallowCopy"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name}DeepCopy() throws IOException {{
{I}final {cls_name} instance = CommonJsonization.loadMaximal{cls_name}();
{I}final {cls_name} instanceCopy = Copying.deep(instance);

{I}assertTrue(
{II}{cls_name}DeepEquals(instance, instanceCopy),
{II}{java_common.string_literal(cls_name)});
}} // public void test{cls_name}DeepCopy"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    writer = io.StringIO()
    writer.write(
        f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertTrue;

import {package}.common.*;
import {package}.copying.Copying;
import {package}.types.impl.*;
import {package}.types.model.*;
import {package}.types.model.IClass;
import {package}.visitation.AbstractTransformerWithContext;
import java.io.IOException;
import java.util.*;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;
import org.junit.jupiter.api.Test;

public class TestCopying {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestCopying

// package {package}.tests

{java_common.WARNING}
"""
    )

    return [java_common.JavaFile("TestCopying.java", writer.getvalue())]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
