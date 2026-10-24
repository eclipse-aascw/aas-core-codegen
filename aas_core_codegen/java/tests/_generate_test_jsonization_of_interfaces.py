"""Generate code to test the JSON de/serialization of interfaces."""

from typing import List

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import INDENT as I, INDENT2 as II


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the JSON de/serialization of interfaces.
    """
    blocks: List[Stripped] = []

    for cls in symbol_table.classes:
        if cls.interface is None or len(cls.interface.implementers) == 0:
            continue

        for implementer_cls in cls.interface.implementers:
            if (
                implementer_cls.serialization is None
                or not implementer_cls.serialization.with_model_type
            ):
                continue

            interface_name_java = java_naming.interface_name(cls.interface.name)
            implementer_cls_name_java = java_naming.class_name(implementer_cls.name)

            blocks.append(
                Stripped(
                    f"""\
@Test
public void testRoundTrip{interface_name_java}From{implementer_cls_name_java}()
{I}throws IOException, JsonProcessingException {{
{I}final ObjectMapper objectMapper = new ObjectMapper();

{I}{implementer_cls_name_java} instance = CommonJsonization.loadMaximal{implementer_cls_name_java}();
{I}final JsonNode jsonObject = Jsonization.Serialize.toJsonObject(instance);

{I}{interface_name_java} anotherInstance = Jsonization.Deserialize.deserialize{interface_name_java}(
{II}jsonObject);
{I}final JsonNode anotherJsonObject = Jsonization.Serialize.toJsonObject(anotherInstance);

{I}assertEquals(
{II}objectMapper.readTree(jsonObject.toString()), objectMapper.readTree(anotherJsonObject.toString()));
}} // void testRoundTrip{interface_name_java}From{implementer_cls_name_java}"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestJsonizationOfInterfaces.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.jsonization.Jsonization;
import {package}.reporting.*;
import {package}.types.impl.*;
import {package}.types.model.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import org.junit.jupiter.api.Test;

public class TestJsonizationOfInterfaces {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestJsonizationOfInterfaces

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
