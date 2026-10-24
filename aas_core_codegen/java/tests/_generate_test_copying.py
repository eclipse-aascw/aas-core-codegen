"""Generate code to test copying."""

import io
import textwrap
from typing import List, Sequence, Set, Union

from icontract import require

from aas_core_codegen import intermediate
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    assert_never,
    Identifier,
)
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import INDENT as I, INDENT2 as II


def _generate_shallow_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the code for a static shallow ``Equals`` method."""
    exprs: List[str] = []
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


def _compares_by_equals(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether the ``equals`` of a value of ``type_anno`` compares it deeply.

    The primitives, the constrained primitives and the enumeration literals
    compare by value -- except for the byte arrays, which compare by reference.
    Jackson's nodes compare by value all the way down. ``List.equals``,
    ``Set.equals`` and the ``equals`` of a tuple record compare their items with
    the items' own ``equals``, so they compare deeply as long as their items do.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return primitive_type is not intermediate.PrimitiveType.BYTEARRAY

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        return isinstance(type_anno.our_type, intermediate.Enumeration)

    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return True

    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        return _compares_by_equals(type_anno.items)

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return all(_compares_by_equals(item) for item in type_anno.items)

    return False


def _deep_equals_method_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the method of ``_DeepEqualiser`` comparing deeply ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.java.common.type_moniker`), so two different
    containers never share a method.
    """
    return Identifier(f"deepEquals{java_common.type_moniker(type_anno)}")


def _generate_deep_equals_expr(
    that: str, other: str, type_anno: intermediate.TypeAnnotationUnion
) -> Stripped:
    """
    Generate the expression comparing deeply the values at ``that`` and ``other``.

    A container which can not be compared by ``equals`` is delegated to a method
    of its own, which compares only one level and calls the method of its items
    by name. This way the deep equality is composed of plain functions, to any
    depth.
    """
    if _compares_by_equals(type_anno):
        return Stripped(f"{that}.equals({other})")

    if intermediate.try_primitive_type(type_anno) is not None:
        # NOTE (mristin):
        # Only a byte array is a primitive which is not compared by ``equals``.
        return Stripped(f"Arrays.equals({that}, {other})")

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        assert isinstance(
            type_anno.our_type, (intermediate.Class, intermediate.NamedUnion)
        ), f"Unexpected our type not compared by equals: {type_anno}"

        # NOTE (mristin):
        # A named union has its own ``transform`` overload (see
        # :py:func:`_generate_union_transform_helper`), so it is compared
        # exactly like a class instance.
        return Stripped(f"transform({that}, {other})")

    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation)
    ):
        return Stripped(f"{_deep_equals_method_name(type_anno)}({that}, {other})")

    raise AssertionError(
        f"Unexpected type annotation to be compared deeply: {type_anno}. "
        f"The sets hold only values compared by ``equals``, and the optionals "
        f"nested in the containers should have been refused in "
        f"parse._translate._verify_symbol_table."
    )


@require(
    lambda type_anno: isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation)
    )
    and not _compares_by_equals(type_anno)
)
def _generate_deep_equals_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the method of ``_DeepEqualiser`` comparing deeply ``type_anno``."""
    value_type = java_common.generate_type(type_anno)

    body: Stripped
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_equals = _generate_deep_equals_expr(
            "that.get(i)", "other.get(i)", type_anno.items
        )

        body = Stripped(
            f"""\
if (that.size() != other.size()) {{
{I}return false;
}}

for (int i = 0; i < that.size(); i++) {{
{I}if (!{indent_but_first_line(item_equals, I)}) {{
{II}return false;
{I}}}
}}

return true;"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_equals_joined = "\n&& ".join(
            _generate_deep_equals_expr(
                f"that.item{i + 1}()", f"other.item{i + 1}()", item_type_anno
            )
            for i, item_type_anno in enumerate(type_anno.items)
        )

        body = Stripped(
            f"""\
return (
{I}{indent_but_first_line(item_equals_joined, I)});"""
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        raise AssertionError(f"Unexpected set not compared by equals: {type_anno}")

    else:
        assert_never(type_anno)

    return Stripped(
        f"""\
private Boolean {_deep_equals_method_name(type_anno)}(
{I}{indent_but_first_line(value_type, I)} that,
{I}{indent_but_first_line(value_type, I)} other) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_transform_as_deep_equals(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the transform method that checks for deep equality."""
    cls_name = java_naming.class_name(cls.name)

    exprs: List[Stripped] = []

    for prop in cls.properties:
        getter_name = java_naming.getter_name(prop.name)
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        if not isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) or _compares_by_equals(type_anno):
            # NOTE (mristin):
            # ``Optional.equals`` compares the values with their own ``equals``,
            # so the optionals compared by ``equals`` need no unwrapping.
            exprs.append(
                _generate_deep_equals_expr(
                    f"that.{getter_name}()", f"casted.{getter_name}()", type_anno
                )
            )
        else:
            value_equals = _generate_deep_equals_expr(
                f"that.{getter_name}().get()",
                f"casted.{getter_name}().get()",
                type_anno,
            )
            exprs.append(
                Stripped(
                    f"""\
(that.{getter_name}().isPresent()
{I}? casted.{getter_name}().isPresent()
{II}&& {indent_but_first_line(value_equals, II)}
{I}: !casted.{getter_name}().isPresent())"""
                )
            )

    body: Stripped
    if len(exprs) == 0:
        # NOTE (mristin):
        # There are no properties to compare, so the instances are trivially
        # deeply equal as soon as we know ``other`` is of the expected concrete
        # type (which we already checked above).
        body = Stripped("return true;")
    else:
        exprs_joined = "\n&& ".join(exprs)
        body = Stripped(
            f"""\
return (
{I}{indent_but_first_line(exprs_joined, I)});"""
        )

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
@Override
public Boolean {transform_name}({interface_name} that, IClass other) {{
{I}if (!(other instanceof {cls_name})) {{
{II}return false;
{I}}}

{I}{cls_name} casted = ({cls_name}) other;

{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_union_transform_helper() -> Stripped:
    """
    Generate a single ``transform`` overload shared by every named union.

    A named union is not itself an ``IClass``, so it can not be dispatched
    by the inherited, ``IClass``-typed ``transform`` overload. We add this
    overload, single-purpose, so that call sites can keep passing
    ``transform`` around or calling it directly, regardless of whether the
    value at hand is a class instance or a named union.

    Dispatching over the common ``IUnion<?>`` (see ``_generate_iunion`` in
    ``_generate_types.py``) instead of the union's own type means we need
    only this one overload for *all* named unions, not one per union -- the
    result is a plain ``Boolean``, so there is no return type to preserve.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
private Boolean transform(IUnion<?> that, IUnion<?> other) {{
{I}return transform(that.getUnderlying(), other.getUnderlying());
}}"""
    )


def _containers_compared_deeply(
    symbol_table: intermediate.SymbolTable,
) -> List[Union[intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation]]:
    """
    List the containers which are compared deeply by methods of their own.

    The containers are de-duplicated by their type moniker.
    """
    result: List[
        Union[intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation]
    ] = []

    observed_monikers: Set[str] = set()
    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if not isinstance(
                    type_anno,
                    (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
                ) or _compares_by_equals(type_anno):
                    continue

                moniker = java_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)
                result.append(type_anno)

    return result


def _generate_deep_equals_transformer(
    symbol_table: intermediate.SymbolTable,
    containers: Sequence[
        Union[intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation]
    ],
) -> Stripped:
    """
    Generate the transformer that checks for deep equality.

    The ``containers`` are compared deeply by methods of their own.
    """
    blocks: List[Stripped] = []

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_transform_as_deep_equals(cls=concrete_cls))

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_union_transform_helper())

    blocks.extend(
        _generate_deep_equals_container(type_anno=container) for container in containers
    )

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
    containers = _containers_compared_deeply(symbol_table)

    blocks: List[Stripped] = [
        _generate_deep_equals_transformer(
            symbol_table=symbol_table, containers=containers
        ),
        Stripped(
            """\
private static final _DeepEqualiser DeepEqualiserInstance = new _DeepEqualiser();"""
        ),
    ]

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

    imports: List[Stripped] = [
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.copying.Copying;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.impl.*;"),
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.types.model.IClass;"),
        Stripped(f"import {package}.visitation.AbstractTransformerWithContext;"),
        Stripped("import java.io.IOException;"),
        Stripped("import java.util.Arrays;"),
        Stripped("import java.util.List;"),
        Stripped("import org.junit.jupiter.api.Test;"),
    ]

    # NOTE (mristin):
    # The methods comparing the containers spell out their types, so we need to
    # import the sets nested in them.
    if any(
        isinstance(nested, intermediate.SetTypeAnnotation)
        for container in containers
        for nested in intermediate.over_type_annotation_and_nested_type_annotations(
            container
        )
    ):
        imports.append(Stripped("import java.util.Set;"))

    # NOTE (mristin):
    # The methods comparing the containers spell out the Jackson nodes in their
    # signatures, and only the models which use one pay for the import.
    if intermediate_uses.json_types(symbol_table):
        imports.extend(
            Stripped(f"import {json_import};")
            for json_import in java_common.JSON_IMPORTS
        )

    imports_joined = "\n".join(imports)

    writer = io.StringIO()
    writer.write(
        f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertTrue;

{imports_joined}

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
