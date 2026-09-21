"""Generate code to test the XML de/serialization of concrete classes."""

from typing import Dict, List, Mapping, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Identifier, Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


#: The lexical forms which no recorded example can hold, by the primitive
#: they belong to. See the Java generator for why they can not be fixtures.
_LEXICAL_CASES_BY_PRIMITIVE = {
    intermediate.PrimitiveType.FLOAT: [
        # NOTE (mristin):
        # A literal too large for a double is not an error: XSD rounds it to
        # an infinity, and one too small to zero.
        #
        # See: https://www.w3.org/TR/xmlschema11-2/#double
        ("1e400", "System.Double.PositiveInfinity"),
        ("-1e400", "System.Double.NegativeInfinity"),
        ("1e-400", "0.0"),
        ("INF", "System.Double.PositiveInfinity"),
        ("+INF", "System.Double.PositiveInfinity"),
        ("-INF", "System.Double.NegativeInfinity"),
    ],
    intermediate.PrimitiveType.BYTEARRAY: [
        # NOTE (mristin):
        # ``xs:base64Binary`` admits whitespace *between* the characters and
        # not only around them, and an empty value stands for zero bytes.
        # Neither can be a recorded example: the first is written back without
        # the space, and the second as an empty element.
        #
        # See: https://www.w3.org/TR/xmlschema-2/#base64Binary
        ("SGk=", "new byte[] { 72, 105 }"),
        ("SG k=", "new byte[] { 72, 105 }"),
        ("S G k =", "new byte[] { 72, 105 }"),
        ("", "new byte[] { }"),
    ],
    intermediate.PrimitiveType.BOOL: [
        # NOTE (mristin):
        # ``xs:boolean`` spells the two values in four ways, not two.
        ("1", "true"),
        ("0", "false"),
        ("true", "true"),
        ("false", "false"),
    ],
}  # type: Mapping[intermediate.PrimitiveType, List[Tuple[str, str]]]


def _lexical_test_name_chunk(text: str) -> str:
    """
    Make a chunk of a test name out of ``text``.

    The result has to satisfy :py:attr:`aas_core_codegen.common.IDENTIFIER_RE`,
    so every character which is not a letter or a digit is spelled out, and
    an empty text is named as such.
    """
    if text == "":
        return "empty"

    mapping = {
        "+": "plus_",
        "-": "minus_",
        ".": "point_",
        " ": "space_",
        "=": "pad",
    }
    return "".join(mapping.get(character, character) for character in text)


def _generate_lexical_tests(symbol_table: intermediate.SymbolTable) -> List[Stripped]:
    """Generate the tests over the lexical forms which no example can hold."""
    cls = intermediate.first_class_of_only_required_primitives(symbol_table)
    if cls is None:
        return []

    prop_by_a_type = (
        dict()
    )  # type: Dict[intermediate.PrimitiveType, intermediate.Property]
    for prop in cls.properties:
        assert isinstance(prop.type_annotation, intermediate.PrimitiveTypeAnnotation)
        prop_by_a_type.setdefault(prop.type_annotation.a_type, prop)

    relevant = [
        (a_type, prop_by_a_type[a_type])
        for a_type in (
            intermediate.PrimitiveType.FLOAT,
            intermediate.PrimitiveType.BOOL,
            intermediate.PrimitiveType.BYTEARRAY,
        )
        if a_type in prop_by_a_type
    ]

    if len(relevant) == 0:
        return []

    cls_name_csharp = csharp_naming.class_name(cls.name)
    cls_name_xml = naming.xml_class_name(cls.name)

    result = [
        Stripped(
            f"""\
/// <summary>
/// Read the first recorded example of {cls_name_csharp} with the content of
/// the element <paramref name="xmlName" /> replaced by
/// <paramref name="text" />.
/// </summary>
private static Aas.{cls_name_csharp} ReadWith(string xmlName, string text)
{{
{I}var paths = Directory.GetFiles(
{II}Path.Combine(
{III}Aas.Tests.Common.TestDataDir,
{III}"Xml",
{III}"Expected",
{III}{csharp_common.string_literal(cls_name_xml)}
{II}),
{II}"*.xml",
{II}System.IO.SearchOption.AllDirectories).ToList();
{I}paths.Sort();

{I}Assert.IsNotEmpty(
{II}paths,
{II}$"Expected at least one recorded example of {cls_name_xml}, but got none");

{I}string original = System.IO.File.ReadAllText(paths[0]);

{I}int start = original.IndexOf($"<{{xmlName}}>") + xmlName.Length + 2;
{I}int end = original.IndexOf($"</{{xmlName}}>");

{I}string patched =
{II}original.Substring(0, start) + text + original.Substring(end);

{I}using var xmlReader = System.Xml.XmlReader.Create(
{II}new System.IO.StringReader(patched));

{I}return Aas.Xmlization.Deserialize.{cls_name_csharp}From(xmlReader);
}}"""
        )
    ]  # type: List[Stripped]

    for a_type, prop in relevant:
        prop_xml_name = naming.xml_property(prop.name)
        prop_name = csharp_naming.property_name(prop.name)

        for a_text, expected in _LEXICAL_CASES_BY_PRIMITIVE[a_type]:
            test_name = csharp_naming.method_name(
                Identifier(
                    f"Test_{prop.name}_read_from_" f"{_lexical_test_name_chunk(a_text)}"
                )
            )

            result.append(
                Stripped(
                    f"""\
[Test]
public void {test_name}()
{{
{I}var instance = ReadWith(
{II}{csharp_common.string_literal(prop_xml_name)},
{II}{csharp_common.string_literal(a_text)});

{I}Assert.AreEqual(
{II}{expected},
{II}instance.{prop_name});
}}  // public void {test_name}"""
                )
            )

    return result


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
    Generate code to test the XML de/serialization of concrete classes.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    xml_namespace_literal = csharp_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    # NOTE (mristin):
    # The elements of the XML-RPC subset, over which a JSON-able value is
    # de/serialized, reside in no namespace at all, unlike everything which
    # the meta-model itself prescribes.
    descendant_namespace_condition = (
        Stripped(
            f"""\
child.GetDefaultNamespace().NamespaceName == {xml_namespace_literal}
{I}|| child.GetDefaultNamespace().NamespaceName.Length == 0"""
        )
        if intermediate.uses_json_types(symbol_table)
        else Stripped(
            f"child.GetDefaultNamespace().NamespaceName == {xml_namespace_literal}"
        )
    )

    blocks = [
        Stripped(
            f"""\
private static void CheckElementsEqual(
{I}XElement expected,
{I}XElement got,
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}if (expected.Name.LocalName != got.Name.LocalName)
{I}{{
{II}error = new Reporting.Error(
{III}"Mismatch in element names: " +
{III}$"{{expected}} != {{got}}"
{II});
{II}return;
{I}}}

{I}string? expectedContent = (expected.FirstNode as XText)?.Value;
{I}string? gotContent = (got.FirstNode as XText)?.Value;

{I}if (expectedContent != gotContent)
{I}{{
{II}error = new Reporting.Error(
{III}$"Mismatch in element contents: {{expected}} != {{got}}"
{II});
{II}return;
{I}}}

{I}var expectedChildren = expected.Elements().ToList();
{I}var gotChildren = got.Elements().ToList();

{I}if (expectedChildren.Count != gotChildren.Count)
{I}{{
{II}error = new Reporting.Error(
{III}$"Mismatch in child elements: {{expected}} != {{got}}"
{II});
{II}return;
{I}}}

{I}for (int i = 0; i < expectedChildren.Count; i++)
{I}{{
{II}CheckElementsEqual(
{III}expectedChildren[i],
{III}gotChildren[i],
{III}out error);

{II}if (error != null)
{II}{{
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(i));

{III}error.PrependSegment(
{IIII}new Reporting.NameSegment(
{IIIII}expected.Name.ToString()));
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
private static void AssertSerializeDeserializeEqualsOriginal(
{I}Aas.IClass instance, string path)
{{
{I}// Serialize
{I}var outputBuilder = new System.Text.StringBuilder();

{I}{{
{II}using var writer = System.Xml.XmlWriter.Create(
{III}outputBuilder,
{III}new System.Xml.XmlWriterSettings()
{III}{{
{IIII}Encoding = System.Text.Encoding.UTF8,
{IIII}OmitXmlDeclaration = true
{III}}}
{II});
{II}Aas.Xmlization.Serialize.To(
{III}instance,
{III}writer);
{I}}}

{I}string outputText = outputBuilder.ToString();

{I}// Compare input == output
{I}{{
{II}using var outputReader = new System.IO.StringReader(outputText);
{II}var gotDoc = XDocument.Load(outputReader);

{II}Assert.AreEqual(
{III}gotDoc.Root?.Name.Namespace.ToString(),
{III}{xml_namespace_literal});

{II}foreach (var child in gotDoc.Descendants())
{II}{{
{III}Assert.IsTrue(
{IIII}{indent_but_first_line(descendant_namespace_condition, IIII)},
{IIII}$"Unexpected namespace of {{child.Name}}: " +
{IIIII}$"{{child.GetDefaultNamespace().NamespaceName}}");
{II}}}

{II}var expectedDoc = XDocument.Load(path);

{II}CheckElementsEqual(
{III}expectedDoc.Root!,
{III}gotDoc.Root!,
{III}out Reporting.Error? inequalityError);

{II}if (inequalityError != null)
{II}{{
{III}Assert.Fail(
{IIII}$"The original XML from {{path}} is unequal the serialized XML: " +
{IIII}$"#/{{Reporting.GenerateRelativeXPath(inequalityError.PathSegments)}}: " +
{IIII}inequalityError.Cause
{III});
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
private static void AssertEqualsExpectedOrRerecordDeserializationException(
{I}Aas.Xmlization.Exception? exception,
{I}string path)
{{
{I}if (exception == null)
{I}{{
{II}Assert.Fail(
{III}$"Expected a Xmlization exception when de-serializing {{path}}, but got none."
{II});
{I}}}
{I}else
{I}{{
{II}string exceptionPath = path + ".exception";
{II}string got = exception.Message;
{II}if (Aas.Tests.Common.RecordMode)
{II}{{
{III}System.IO.File.WriteAllText(exceptionPath, got);
{II}}}
{II}else
{II}{{
{III}if (!System.IO.File.Exists(exceptionPath))
{III}{{
{IIII}throw new System.IO.FileNotFoundException(
{IIIII}"The file with the recorded exception does not " +
{IIIII}$"exist: {{exceptionPath}}; maybe you want to set the environment " +
{IIIII}$"variable {{Aas.Tests.Common.RecordModeEnvironmentVariableName}}?");
{III}}}

{III}string expected = System.IO.File.ReadAllText(exceptionPath);
{III}Assert.AreEqual(
{IIII}expected.Replace("\\r\\n", "\\n"),
{IIII}got.Replace("\\r\\n", "\\n"),
{IIII}$"The expected exception does not match the actual one for the file {{path}}");
{II}}}
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_csharp = csharp_naming.class_name(concrete_cls.name)
        cls_name_xml = naming.xml_class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name_csharp}_ok()
{{
{I}var paths = Directory.GetFiles(
{II}Path.Combine(
{III}Aas.Tests.Common.TestDataDir,
{III}"Xml",
{III}"Expected",
{III}{csharp_common.string_literal(cls_name_xml)}
{II}),
{II}"*.xml",
{II}System.IO.SearchOption.AllDirectories).ToList();
{I}paths.Sort();

{I}foreach (var path in paths)
{I}{{
{II}using var xmlReader = System.Xml.XmlReader.Create(path);

{II}var instance = Aas.Xmlization.Deserialize.{cls_name_csharp}From(
{III}xmlReader);

{II}var errors = Aas.Verification.Verify(instance).ToList();
{II}Aas.Tests.Common.AssertNoVerificationErrors(errors, path);

{II}AssertSerializeDeserializeEqualsOriginal(
{III}instance, path);
{I}}}
}}  // public void Test_{cls_name_csharp}_ok"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name_csharp}_deserialization_fail()
{{
{I}foreach (
{II}string causeDir in
{II}Directory.GetDirectories(
{III}Path.Combine(
{IIII}Aas.Tests.Common.TestDataDir,
{IIII}"Xml",
{IIII}"Unexpected",
{IIII}"Unserializable"
{III})
{II})
{I})
{I}{{
{II}string clsDir = Path.Combine(
{III}causeDir,
{III}{csharp_common.string_literal(cls_name_xml)}
{II});

{II}if (!Directory.Exists(clsDir))
{II}{{
{III}// No examples of {cls_name_csharp} for the failure cause.
{III}continue;
{II}}}

{II}var paths = Directory.GetFiles(
{III}clsDir,
{III}"*.xml",
{III}System.IO.SearchOption.AllDirectories).ToList();
{II}paths.Sort();

{II}foreach (var path in paths)
{II}{{
{III}using var xmlReader = System.Xml.XmlReader.Create(path);

{III}Aas.Xmlization.Exception? exception = null;

{III}try
{III}{{
{IIII}_ = Aas.Xmlization.Deserialize.{cls_name_csharp}From(
{IIIII}xmlReader);
{III}}}
{III}catch (Aas.Xmlization.Exception observedException)
{III}{{
{IIII}exception = observedException;
{III}}}

{III}AssertEqualsExpectedOrRerecordDeserializationException(
{IIII}exception, path);
{II}}}
{I}}}
}}  // public void Test_{cls_name_csharp}_deserialization_fail"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name_csharp}_verification_fail()
{{
{I}foreach (
{II}string causeDir in
{II}Directory.GetDirectories(
{III}Path.Combine(
{IIII}Aas.Tests.Common.TestDataDir,
{IIII}"Xml",
{IIII}"Unexpected",
{IIII}"Invalid"
{III})
{II})
{I})
{I}{{
{II}string clsDir = Path.Combine(
{III}causeDir,
{III}{csharp_common.string_literal(cls_name_xml)}
{II});

{II}if (!Directory.Exists(clsDir))
{II}{{
{III}// No examples of {cls_name_csharp} for the failure cause.
{III}continue;
{II}}}

{II}var paths = Directory.GetFiles(
{III}clsDir,
{III}"*.xml",
{III}System.IO.SearchOption.AllDirectories).ToList();
{II}paths.Sort();

{II}foreach (var path in paths)
{II}{{
{III}using var xmlReader = System.Xml.XmlReader.Create(path);

{III}var instance = Aas.Xmlization.Deserialize.{cls_name_csharp}From(
{IIII}xmlReader);

{III}var errors = Aas.Verification.Verify(instance).ToList();
{III}Aas.Tests.Common.AssertEqualsExpectedOrRerecordVerificationErrors(
{IIII}errors, path);
{II}}}
{I}}}
}}  // public void Test_{cls_name_csharp}_verification_fail"""
            )
        )

    blocks.extend(_generate_lexical_tests(symbol_table))

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Aas = {namespace};  // renamed

using Directory = System.IO.Directory;
using Path = System.IO.Path;

using NUnit.Framework; // can't alias
using System.Linq;  // can't alias
using System.Xml.Linq; // can't alias

namespace {namespace}.Tests
{{
{I}public class TestXmlizationOfConcreteClasses
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestXmlizationOfConcreteClasses
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
