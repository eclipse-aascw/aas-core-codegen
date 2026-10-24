"""Generate code to test the XML de/serialization of interfaces."""

from typing import List

from aas_core_codegen import intermediate
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
    Generate code to test the XML de/serialization of interfaces.
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
{I}throws IOException, XMLStreamException {{
{I}// We load from JSON here just to jump-start the round trip.
{I}// The round-trip goes then over XML.
{I}final {interface_name_java} instance =
{II}CommonJsonization.loadMaximal{implementer_cls_name_java}();

{I}// The round-trip starts here.
{I}final StringWriter stringOut = new StringWriter();
{I}final XMLOutputFactory outputFactory = XMLOutputFactory.newFactory();
{I}final XMLStreamWriter xmlWriter = outputFactory.createXMLStreamWriter(stringOut);

{I}Xmlization.Serialize.to(instance, xmlWriter);
{I}String outputText = stringOut.toString();

{I}// De-serialize from XML
{I}final XMLInputFactory xmlInputFactory = XMLInputFactory.newInstance();
{I}final XMLEventReader xmlReader =
{II}xmlInputFactory.createXMLEventReader(new StringReader(outputText));
{I}final {interface_name_java} anotherInstance =
{II}Xmlization.Deserialize.deserialize{interface_name_java}(xmlReader);

{I}// Serialize back to XML
{I}final StringWriter anotherStringOut = new StringWriter();
{I}final XMLStreamWriter anotherXmlWriter = outputFactory.createXMLStreamWriter(anotherStringOut);
{I}Xmlization.Serialize.to(anotherInstance, anotherXmlWriter);

{I}// Compare
{I}assertEquals(outputText, anotherStringOut.toString());
}} // void testRoundTrip{interface_name_java}From{implementer_cls_name_java}"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestXmlizationOfInterfaces.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.types.impl.*;
import {package}.types.model.*;
import {package}.xmlization.Xmlization;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.stream.*;
import org.junit.jupiter.api.Test;

public class TestXmlizationOfInterfaces {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestXmlizationOfInterfaces

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
