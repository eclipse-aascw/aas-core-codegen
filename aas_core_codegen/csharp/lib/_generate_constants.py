"""Generate code to define the constants of the meta-model."""

import io
import textwrap
from typing import (
    Optional,
    List,
    Tuple,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    assert_never,
    Stripped,
    indent_but_first_line,
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


def _byte_array_as_expr(value: bytearray) -> Stripped:
    """Return a multi-line C# code representing the ``value``."""
    writer = io.StringIO()

    writer.write("new byte[]\n{\n")
    for i, byte in enumerate(value):
        if i > 0:
            if i % 8 == 0:
                writer.write(",\n")
            else:
                writer.write(", ")

        writer.write(f"0x{byte:02x}")

    writer.write("\n}")

    return Stripped(writer.getvalue())


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_primitive(
    constant: intermediate.ConstantPrimitive,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant primitive."""
    constant_name = csharp_naming.property_name(constant.name)

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        literal = "true" if constant.value else "false"

        return Stripped(f"public static const bool {constant_name} = {literal};"), None

    elif constant.a_type is intermediate.PrimitiveType.INT:
        literal = str(constant.value)

        return Stripped(f"public static const long {constant_name} = {literal};"), None

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        # NOTE (mristin):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.
        literal = str(constant.value)

        return (
            Stripped(f"public static const double {constant_name} = {literal};"),
            None,
        )

    elif constant.a_type is intermediate.PrimitiveType.STR:
        assert isinstance(constant.value, str)
        literal = csharp_common.string_literal(constant.value)

        return (
            Stripped(f"public static const string {constant_name} = {literal};"),
            None,
        )

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        assert isinstance(constant.value, bytearray)

        literal = _byte_array_as_expr(value=constant.value)

        return (
            Stripped(
                f"""\
public static readonly byte[] {constant_name} = (
{I}{indent_but_first_line(literal, I)});"""
            ),
            None,
        )

    else:
        assert_never(constant.a_type)


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_primitives(
    constant: intermediate.ConstantSetOfPrimitives,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of primitives."""
    constant_name = csharp_naming.property_name(constant.name)

    writer = io.StringIO()

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        writer.write(
            f"""\
public static readonly HashSet<bool> {constant_name} = (
{I}new HashSet<bool>()
{I}{{
"""
        )

        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent("true" if literal.value else "false", II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write(f"{I}}});")

    elif constant.a_type is intermediate.PrimitiveType.INT:
        writer.write(
            f"""\
public static readonly HashSet<long> {constant_name} = (
{I}new HashSet<long>()
{I}{{
"""
        )

        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent(str(literal.value), II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write(f"{I}}});")

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        # NOTE (mristin):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.

        writer.write(
            f"""\
public static readonly HashSet<double> {constant_name} = (
{I}new HashSet<double>()
{I}{{
"""
        )

        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent(str(literal.value), II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write(f"{I}}});")

    elif constant.a_type is intermediate.PrimitiveType.STR:
        writer.write(
            f"""\
public static readonly HashSet<string> {constant_name} = (
{I}new HashSet<string>()
{I}{{
"""
        )

        for i, literal in enumerate(constant.literals):
            assert isinstance(literal.value, str)

            writer.write(
                textwrap.indent(csharp_common.string_literal(literal.value), II)
            )

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write(f"{I}}});")

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        writer.write(
            f"""\
public static readonly HashSet<byte[]> {constant_name} = (
{I}new HashSet<byte[]>(new ByteArrayComparer())
{I}{{
"""
        )

        for i, literal in enumerate(constant.literals):
            assert isinstance(literal.value, bytearray)

            writer.write(textwrap.indent(_byte_array_as_expr(literal.value), II))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write(f"{I}}});")

    else:
        assert_never(constant.a_type)

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_enumeration_literals(
    constant: intermediate.ConstantSetOfEnumerationLiterals,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of enumeration literals."""
    constant_name = csharp_naming.property_name(constant.name)
    enum_name = csharp_naming.enum_name(constant.enumeration.name)

    writer = io.StringIO()

    # NOTE (mristin):
    # We make the sets of enumeration literals work on nullables to avoid checking
    # nullability all the time in the code. This gives a bit less performant code,
    # but a much more readable one.

    writer.write(
        f"""\
public static readonly HashSet<{enum_name}?> {constant_name} = (
{I}new HashSet<{enum_name}?>()
{I}{{
"""
    )

    for i, literal in enumerate(constant.literals):
        literal_name = csharp_naming.enum_literal_name(literal.name)

        writer.write(textwrap.indent(f"{enum_name}.{literal_name}", II))

        if i < len(constant.literals) - 1:
            writer.write(",\n")
        else:
            writer.write("\n")

    writer.write(f"{I}}});")

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
    Generate code to define the constants of the meta-model.

    The ``namespace`` defines the AAS C# namespace.
    """
    constants_blocks = []  # type: List[Stripped]

    needs_byte_array_comparer = False
    for constant in symbol_table.constants:
        if (
            isinstance(constant, intermediate.ConstantSetOfPrimitives)
            and constant.a_type is intermediate.PrimitiveType.BYTEARRAY
        ):
            needs_byte_array_comparer = True
            break

    if needs_byte_array_comparer:
        constants_blocks.append(
            Stripped(
                f"""\
/// <summary>
/// Compare two byte arrays for equality.
/// </summary>
/// <remarks>
/// Based on: https://stackoverflow.com/a/49739848/1600678
/// </remarks>
private class ByteArrayComparer
{{
{I}public bool Equals(byte[] a, byte[] b)
{I}{{
{II}if (a.Length != b.Length) return false;
{II}for (int i = 0; i < a.Length; i++)
{II}{{
{III}if (a[i] != b[i]) return false;
{II}}}

{II}return true;
{I}}}

{I}public int GetHashCode(byte[] a)
{I}{{
{II}uint b = 0;
{II}for (int i = 0; i < a.Length; i++)
{II}{{
{III}b = ((b << 23) | (b >> 9)) ^ a[i];
{II}}}

{II}return unchecked((int)b);
{I}}}
}}"""
            )
        )

    errors = []  # type: List[Error]

    for constant in symbol_table.constants:
        constants_block: Optional[Stripped]
        error: Optional[Error]

        if isinstance(constant, intermediate.ConstantPrimitive):
            constants_block, error = _generate_constant_primitive(constant=constant)
        elif isinstance(constant, intermediate.ConstantSetOfPrimitives):
            constants_block, error = _generate_constant_set_of_primitives(
                constant=constant
            )
        elif isinstance(constant, intermediate.ConstantSetOfEnumerationLiterals):
            constants_block, error = _generate_constant_set_of_enumeration_literals(
                constant=constant
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
/// <summary>
/// Provide constant values of the meta-model.
/// </summary>
public static class Constants
{
"""
    )

    for i, constants_block in enumerate(constants_blocks):
        assert len(constants_block) > 0

        if i > 0:
            constants_writer.write("\n\n")

        constants_writer.write(textwrap.indent(constants_block, I))

    constants_writer.write("\n}  // public static class Constants")

    blocks = [
        csharp_common.WARNING,
        Stripped("using System.Collections.Generic;  // can't alias"),
        Stripped(
            f"""\
namespace {namespace}
{{
{I}{indent_but_first_line(constants_writer.getvalue(), I)}
}}  // namespace {namespace}"""
        ),
        csharp_common.WARNING,
    ]  # type: List[Stripped]

    out = io.StringIO()
    for i, constants_block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(constants_block)

    out.write("\n")

    return out.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__)
