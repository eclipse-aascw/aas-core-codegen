"""Generate code to test the XML de/serialization of interfaces."""

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
    Generate code to test the XML de/serialization of interfaces.

    The ``namespace`` indicates the fully-qualified name of the base project.
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

            interface_name_csharp = csharp_naming.interface_name(cls.interface.name)

            implementer_cls_name_csharp = csharp_naming.class_name(implementer_cls.name)

            blocks.append(
                Stripped(
                    f"""\
[Test]
public void Test_round_trip_{interface_name_csharp}_from_{implementer_cls_name_csharp}()
{{
{I}// We load from JSON here just to jump-start the round trip.
{I}// The round-trip goes then over XML.
{I}var instance = Our.Tests.CommonJsonization.LoadMaximal{implementer_cls_name_csharp}();

{I}// The round-trip starts here.
{I}var outputBuilder = new System.Text.StringBuilder();

{I}// Serialize to XML
{I}{{
{II}using var xmlWriter = System.Xml.XmlWriter.Create(
{III}outputBuilder,
{III}new System.Xml.XmlWriterSettings()
{III}{{
{IIII}Encoding = System.Text.Encoding.UTF8,
{IIII}OmitXmlDeclaration = true
{III}}});

{II}Our.Xmlization.Serialize.To(
{III}instance,
{III}xmlWriter);
{I}}}

{I}// De-serialize from XML
{I}string outputText = outputBuilder.ToString();

{I}using var outputReader = new System.IO.StringReader(outputText);

{I}using var xmlReader = System.Xml.XmlReader.Create(
{II}outputReader,
{II}new System.Xml.XmlReaderSettings());

{I}var anotherInstance = Our.Xmlization.Deserialize.{interface_name_csharp}From(
{II}xmlReader);

{I}// Serialize back to XML
{I}var anotherOutputBuilder = new System.Text.StringBuilder();

{I}{{
{II}using var anotherXmlWriter = System.Xml.XmlWriter.Create(
{III}anotherOutputBuilder,
{III}new System.Xml.XmlWriterSettings()
{III}{{
{IIII}Encoding = System.Text.Encoding.UTF8,
{IIII}OmitXmlDeclaration = true
{III}}});

{II}Our.Xmlization.Serialize.To(
{III}anotherInstance,
{III}anotherXmlWriter);
{I}}}

{I}// Compare
{I}Assert.AreEqual(outputText, anotherOutputBuilder.ToString());
}}  // void Test_round_trip_{interface_name_csharp}_from_{implementer_cls_name_csharp}"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}public class TestXmlizationOfInterfaces
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestXmlizationOfInterfaces
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
