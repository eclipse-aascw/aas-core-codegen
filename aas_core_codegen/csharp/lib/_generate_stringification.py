"""Generate code for string de/serialization of enumerations."""

import io
import textwrap
import xml.sax.saxutils
from typing import Tuple, Optional, List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Error, Stripped, Identifier
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import INDENT as I, INDENT2 as II, INDENT3 as III


def _generate_enum_to_and_from_string(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the methods for de/serializing enumeration from/to a string."""
    blocks = []  # type: List[Stripped]

    name = csharp_naming.enum_name(enumeration.name)

    # region To-string-map

    # NOTE (mristin):
    # We make the property look "public" by the name since it is a static and read-only.
    to_str_map_name = csharp_naming.property_name(
        Identifier(f"{enumeration.name}_to_string")
    )

    to_str_map_writer = io.StringIO()
    to_str_map_writer.write(
        f"""\
private static readonly Dictionary<Aas.{name}, string> {to_str_map_name} = (
{I}new Dictionary<Aas.{name}, string>()
{I}{{
"""
    )

    for i, literal in enumerate(enumeration.literals):
        literal_name = csharp_naming.enum_literal_name(literal.name)
        to_str_map_writer.write(
            f"{II}{{ Aas.{name}.{literal_name}, "
            f"{csharp_common.string_literal(literal.value)} }}"
        )

        if i < len(enumeration.literals) - 1:
            to_str_map_writer.write(",")

        to_str_map_writer.write("\n")

    to_str_map_writer.write(f"{I}}});")

    blocks.append(Stripped(to_str_map_writer.getvalue()))

    # endregion

    # region To-string-method

    to_str_name = csharp_naming.method_name(Identifier("to_string"))

    to_str_writer = io.StringIO()
    to_str_writer.write(
        f"""\
/// <summary>
/// Retrieve the string representation of <paramref name="that" />.
/// </summary>
/// <remarks>
/// If <paramref name="that" /> is not a valid literal, return <c>null</c>.
/// </remarks>
public static string? {to_str_name}(Aas.{name}? that)
{{
{I}if (!that.HasValue)
{I}{{
{II}return null;
{I}}}
{I}else
{I}{{
{II}if ({to_str_map_name}.TryGetValue(that.Value, out string? value))
{II}{{
{III}return value;
{II}}}
{II}else
{II}{{
{III}return null;
{II}}}
{I}}}
}}"""
    )

    blocks.append(Stripped(to_str_writer.getvalue()))

    # endregion

    # region From-string-map

    from_str_map_name = csharp_naming.private_property_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    from_str_map_writer = io.StringIO()
    from_str_map_writer.write(
        f"""\
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
private static readonly Dictionary<string, Aas.{name}> {from_str_map_name} = (
{I}new Dictionary<string, Aas.{name}>()
{I}{{
"""
    )

    for i, literal in enumerate(enumeration.literals):
        literal_name = csharp_naming.enum_literal_name(literal.name)
        from_str_map_writer.write(
            f"{II}{{ {csharp_common.string_literal(literal.value)}, "
            f"Aas.{name}.{literal_name} }}"
        )

        if i < len(enumeration.literals) - 1:
            from_str_map_writer.write(",")

        from_str_map_writer.write("\n")

    from_str_map_writer.write(f"{I}}});")

    blocks.append(Stripped(from_str_map_writer.getvalue()))

    # endregion

    # region From-string-method

    from_str_name = csharp_naming.method_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    from_str_writer = io.StringIO()
    from_str_writer.write(
        f"""\
/// <summary>
/// Parse the string representation of <see cref={xml.sax.saxutils.quoteattr(name)} />.
/// </summary>
/// <remarks>
/// If <paramref name="text" /> is not a valid string representation
/// of a literal of <see cref={xml.sax.saxutils.quoteattr(name)} />,
/// return <c>null</c>.
/// </remarks>
public static Aas.{name}? {from_str_name}(string text)
{{
{I}if ({from_str_map_name}.TryGetValue(text, out {name} value))
{I}{{
{II}return value;
{I}}}
{I}else
{I}{{
{II}return null;
{I}}}
}}"""
    )

    blocks.append(Stripped(from_str_writer.getvalue()))

    # endregion

    return Stripped("\n\n".join(blocks))


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable, namespace: csharp_common.NamespaceIdentifier
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code for string de/serialization of enumerations.

    The ``namespace`` defines the base C# namespace of the generated code.
    """
    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using CodeAnalysis = System.Diagnostics.CodeAnalysis;

using System.Collections.Generic;  // can't alias"""
        )
    )

    blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
    ]

    stringification_blocks = []  # type: List[Stripped]

    for enum in symbol_table.enumerations:
        stringification_blocks.append(
            _generate_enum_to_and_from_string(enumeration=enum)
        )

    writer = io.StringIO()
    writer.write(
        f"""\
namespace {namespace}
{{
{I}public static class Stringification
{I}{{
"""
    )

    for i, stringification_block in enumerate(stringification_blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(stringification_block, II))

    writer.write(f"\n{I}}}  // public static class Stringification")
    writer.write(f"\n}}  // namespace {namespace}")

    blocks.append(Stripped(writer.getvalue()))

    blocks.append(csharp_common.WARNING)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        out.write(block)

    out.write("\n")

    return out.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
