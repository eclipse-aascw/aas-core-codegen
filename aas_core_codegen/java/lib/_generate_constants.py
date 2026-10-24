"""Generate code to define the constants of the meta-model."""

import io
import textwrap
from typing import (
    List,
    Optional,
    Set,
    Tuple,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    assert_never,
    Error,
    Stripped,
)
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)


def _byte_array_as_expr(value: bytearray) -> Stripped:
    """Return a multi-line java code representing the ``value''."""
    writer = io.StringIO()

    writer.write("new byte[] {")

    for i, byte in enumerate(value):
        if i > 0:
            if i % 8 == 0:
                writer.write(",\n")
            else:
                writer.write(", ")

        writer.write(f"(byte) 0x{byte:02x}")

    writer.write("\n}")

    return Stripped(writer.getvalue())


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_primitive(
    constant: intermediate.ConstantPrimitive,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant primitive."""
    constant_name = java_naming.property_name(constant.name)

    assert constant.a_type in java_common.PRIMITIVE_TYPE_MAP

    java_type = java_common.PRIMITIVE_TYPE_MAP[constant.a_type]

    literal: Stripped

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        literal = Stripped("true") if constant.value else Stripped("false")

    elif constant.a_type is intermediate.PrimitiveType.INT:
        assert isinstance(constant.value, int)
        literal = Stripped(f"{constant.value}L")

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        # NOTE (empwilli):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.
        literal = Stripped(str(constant.value))

    elif constant.a_type is intermediate.PrimitiveType.STR:
        assert isinstance(constant.value, str)
        literal = java_common.string_literal(constant.value)

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        assert isinstance(constant.value, bytearray)
        literal = _byte_array_as_expr(value=constant.value)

    else:
        assert_never(constant.a_type)

    return (
        Stripped(f"public static final {java_type} {constant_name} = {literal};"),
        None,
    )


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_primitives(
    constant: intermediate.ConstantSetOfPrimitives,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of primitives."""
    constant_name = java_naming.property_name(constant.name)

    writer = io.StringIO()

    java_type = java_common.PRIMITIVE_TYPE_MAP[constant.a_type]

    writer.write(
        f"""\
public static final Set<{java_type}> {constant_name} = Stream.of(
"""
    )

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent("true" if literal.value else "false", II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

    elif constant.a_type is intermediate.PrimitiveType.INT:
        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent(f"{literal.value}L", II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        # NOTE (empwilli):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.

        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent(str(literal.value), II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

    elif constant.a_type is intermediate.PrimitiveType.STR:
        for i, literal in enumerate(constant.literals):
            assert isinstance(literal.value, str)

            writer.write(textwrap.indent(java_common.string_literal(literal.value), II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        for i, literal in enumerate(constant.literals):
            assert isinstance(literal.value, bytearray)

            writer.write(textwrap.indent(_byte_array_as_expr(literal.value), II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

    else:
        assert_never(constant.a_type)

    writer.write(""").collect(_ImmutableCollector.toImmutableSet());""")

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_enumeration_literals(
    constant: intermediate.ConstantSetOfEnumerationLiterals,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of enumeration literals."""
    constant_name = java_naming.property_name(constant.name)
    enum_name = java_naming.enum_name(constant.enumeration.name)

    writer = io.StringIO()

    # NOTE (empwilli):
    # We make the sets of enumeration literals work on nullables to avoid checking
    # nullability all the time in the code. This gives a bit less performant code,
    # but a much more readable one.

    writer.write(
        f"""\
public static final Set<{enum_name}> {constant_name} = Stream.of(
"""
    )

    for i, literal in enumerate(constant.literals):
        literal_name = java_naming.enum_literal_name(literal.name)

        writer.write(textwrap.indent(f"{enum_name}.{literal_name}", II))

        if i < len(constant.literals) - 1:
            writer.write(",\n")
        else:
            writer.write("\n")

    writer.write(""").collect(_ImmutableCollector.toImmutableSet());""")

    return Stripped(writer.getvalue()), None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code to define the constants of the meta-model.
    """
    enum_imports: Set[Stripped] = set()

    for constant in symbol_table.constants:
        if not isinstance(constant, intermediate.ConstantSetOfEnumerationLiterals):
            continue

        enum_name = java_naming.enum_name(constant.enumeration.name)

        enum_imports.add(
            Stripped(f"import {package}.types.{java_common.ENUM_PKG}.{enum_name};")
        )

    enum_imports_block = Stripped("\n".join(sorted(enum_imports)))

    constants_blocks: List[Stripped] = []

    errors: List[Error] = []

    for constant in symbol_table.constants:
        constants_block: Optional[Stripped]
        error: Optional[Error]

        if isinstance(constant, intermediate.ConstantPrimitive):
            constants_block, error = _generate_constant_primitive(constant)
        elif isinstance(constant, intermediate.ConstantSetOfPrimitives):
            constants_block, error = _generate_constant_set_of_primitives(constant)
        elif isinstance(constant, intermediate.ConstantSetOfEnumerationLiterals):
            constants_block, error = _generate_constant_set_of_enumeration_literals(
                constant
            )
        else:
            assert_never(constant)

        if error is not None:
            errors.append(error)
            continue

        assert constants_block is not None
        constants_blocks.append(constants_block)

    if len(errors) > 0:
        return None, errors

    constants_writer = io.StringIO()
    constants_writer.write(
        """\
/**
 * Provide constant values of the meta-model.
 */
public class Constants {
"""
    )

    for i, constants_block in enumerate(constants_blocks):
        assert len(constants_block) > 0

        if i > 0:
            constants_writer.write("\n\n")

        constants_writer.write(textwrap.indent(constants_block, I))

    constants_writer.write("\n}")

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(
            f"""\
package {package}.constants;

import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.stream.Collector;
import java.util.stream.Stream;"""
        ),
        enum_imports_block,
        Stripped(
            f"""\
// Helper to generate read-only collections with less boilerplate.
// See: https://stackoverflow.com/a/37406054
class _ImmutableCollector {{
    public static <T> Collector<T, Set<T>, Set<T>> toImmutableSet() {{
        return Collector.of(HashSet::new, Set::add, (l, r) -> {{
            l.addAll(r);
            return l;
        }}, Collections::unmodifiableSet);
    }}
}}

{constants_writer.getvalue()}"""
        ),
        java_common.WARNING,
    ]

    out = io.StringIO()
    for i, constants_block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(constants_block)

    out.write("\n")

    return [java_common.JavaFile("Constants.java", out.getvalue())], None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
