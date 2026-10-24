"""Generate code to test the JSON de/serialization of enumerations."""

import json
from typing import List

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
)


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the JSON de/serialization of enumerations.
    """
    blocks: List[Stripped] = []

    for enumeration in symbol_table.enumerations:
        enum_name = java_naming.enum_name(enumeration.name)
        enum_name_camel_case = naming.lower_camel_case(enumeration.name)

        assert (
            len(enumeration.literals) > 0
        ), f"Unexpected enumeration without literals: {enumeration.name}"

        literal_value = enumeration.literals[0].value
        literal_value_json_str = json.dumps(literal_value)

        blocks.append(
            Stripped(
                f"""\
@Test
public void testRoundTrip{enum_name}() {{
{I}final JsonNode node = JsonNodeFactory.instance.textNode(
{II}{java_common.string_literal(literal_value)});

{I}final {enum_name} parsed = Jsonization.Deserialize.deserialize{enum_name}(node);

{I}final JsonNode serialized = Jsonization.Serialize.{enum_name_camel_case}ToJsonValue(parsed);

{I}assertEquals(
{II}{java_common.string_literal(literal_value_json_str)},
{II}serialized.toString());
}} // void testRoundTrip{enum_name}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestJsonizationOfEnums.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.jsonization.Jsonization;
import {package}.types.enums.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import org.junit.jupiter.api.Test;

public class TestJsonizationOfEnums {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestJsonizationOfEnums

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
