"""Generate code to test the JSON de/serialization of enumerations."""
import json
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
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
    Generate code to test the JSON de/serialization of enumerations.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = []

    for enumeration in symbol_table.enumerations:
        enum_name = csharp_naming.enum_name(enumeration.name)

        assert (
            len(enumeration.literals) > 0
        ), f"Unexpected enumeration without literals: {enumeration.name}"

        literal_value = enumeration.literals[0].value
        literal_value_json_str = json.dumps(literal_value)

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_round_trip_{enum_name}()
{{
{I}var node = Nodes.JsonValue.Create(
{II}{csharp_common.string_literal(literal_value)})
{III}?? throw new System.InvalidOperationException(
{IIII}"Unexpected null node");

{I}var parsed = Our.Jsonization.Deserialize.{enum_name}From(
{II}node);

{I}var serialized = Our.Jsonization.Serialize.{enum_name}ToJsonValue(
{II}parsed);

{I}Assert.AreEqual(
{II}{csharp_common.string_literal(literal_value_json_str)},
{II}serialized.ToJsonString());
}}  // void Test_round_trip_{enum_name}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using Nodes = System.Text.Json.Nodes;

using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}public class TestJsonizationOfEnums
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestJsonizationOfEnums
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
