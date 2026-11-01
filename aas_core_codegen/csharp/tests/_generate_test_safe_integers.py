"""Generate code to test that the integers are refused outside the safe integer range."""

from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Identifier, Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)
from aas_core_codegen.csharp.tests import (
    _generate_test_jsonization_of_concrete_classes as csharp_tests_jsonization,
)
from aas_core_codegen.intermediate import uses as intermediate_uses


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
    Generate code to test that the integers are refused outside the safe integer range.

    We test the predicate ``Common.IsSafeInteger`` directly. Then we set
    an integer, or an integer in a JSON-able value, from outside, and
    check that the verification, the JSON serialization and the XML
    serialization all refuse it with the same message, and that they all
    accept the integers at the bounds of the range. We also check that
    the de-serialization from JSON and from XML refuses the integers right
    beyond the bounds.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
[Test]
public void Test_IsSafeInteger()
{{
{I}foreach (var value in new long[]
{I}{{
{II}0L, 9007199254740991L, -9007199254740991L
{I}}})
{I}{{
{II}Assert.IsTrue(Our.Common.IsSafeInteger(value), $"for {{value}}");
{I}}}

{I}foreach (var value in new long[]
{I}{{
{II}9007199254740992L, -9007199254740992L, long.MaxValue, long.MinValue
{I}}})
{I}{{
{II}Assert.IsFalse(Our.Common.IsSafeInteger(value), $"for {{value}}");
{I}}}

{I}Assert.IsTrue(Our.Common.IsSafeInteger(9007199254740991UL));
{I}Assert.IsFalse(Our.Common.IsSafeInteger(9007199254740992UL));
{I}Assert.IsFalse(Our.Common.IsSafeInteger(ulong.MaxValue));

{I}foreach (var value in new double[]
{I}{{
{II}0.0, 9007199254740991.0, -9007199254740991.0
{I}}})
{I}{{
{II}Assert.IsTrue(Our.Common.IsSafeInteger(value), $"for {{value}}");
{I}}}

{I}foreach (var value in new double[]
{I}{{
{II}9007199254740992.0,
{II}-9007199254740992.0,
{II}double.PositiveInfinity,
{II}double.NegativeInfinity,
{II}double.NaN
{I}}})
{I}{{
{II}Assert.IsFalse(Our.Common.IsSafeInteger(value), $"for {{value}}");
{I}}}
}}  // public void Test_IsSafeInteger"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Read the first recorded example of the <paramref name="modelType" />.
/// </summary>
private static Nodes.JsonNode LoadTheFirstExpected(string modelType)
{{
{I}var paths = Directory.GetFiles(
{II}Path.Combine(
{III}Our.Tests.Common.TestDataDir,
{III}"Json",
{III}"Expected",
{III}modelType),
{II}"*.json",
{II}System.IO.SearchOption.AllDirectories).ToList();
{I}paths.Sort();

{I}Assert.IsNotEmpty(
{II}paths,
{II}$"Expected at least one recorded example of {{modelType}}, but got none");

{I}return Our.Tests.CommonJson.ReadFromFile(paths[0]);
}}"""
        ),
        Stripped(
            f"""\
private static string SerializeToXml(Our.IClass instance)
{{
{I}var builder = new System.Text.StringBuilder();
{I}using (var writer = System.Xml.XmlWriter.Create(
{II}builder,
{II}new System.Xml.XmlWriterSettings()
{II}{{
{III}Encoding = System.Text.Encoding.UTF8,
{III}OmitXmlDeclaration = true
{II}}}))
{I}{{
{II}Our.Xmlization.Serialize.To(instance, writer);
{I}}}
{I}return builder.ToString();
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Assert that the verification, the JSON serialization and the XML
/// serialization all refuse <paramref name="instance" /> with
/// <paramref name="expectedCause" />.
/// </summary>
private static void AssertRefused(
{I}Our.IClass instance,
{I}string expectedCause,
{I}string expectedJsonPath)
{{
{I}var errors = Our.Verification.Verify(instance).ToList();
{I}Assert.IsTrue(
{II}errors.Any(
{III}error =>
{IIII}error.Cause == expectedCause
{IIII}&& Reporting.GenerateJsonPath(error.PathSegments) == expectedJsonPath),
{II}$"Expected the verification error {{expectedCause}} " +
{II}$"at {{expectedJsonPath}}, but got: " +
{II}string.Join(
{III}"; ",
{III}errors.Select(
{IIII}error => $"{{Reporting.GenerateJsonPath(error.PathSegments)}}: {{error.Cause}}")));

{I}var jsonException = Assert.Throws<Our.Jsonization.SerializationException>(
{II}() => Our.Jsonization.Serialize.ToJsonObject(instance));
{I}Assert.AreEqual(expectedCause, jsonException!.Cause);

{I}var xmlException = Assert.Throws<Our.SerializationException>(
{II}() => SerializeToXml(instance));
{I}Assert.AreEqual(expectedCause, xmlException!.Cause);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Assert that neither the verification, nor the JSON serialization nor
/// the XML serialization refuses an integer of <paramref name="instance" />
/// as outside the safe integer range.
/// </summary>
private static void AssertAccepted(Our.IClass instance)
{{
{I}var errors = Our.Verification.Verify(instance)
{II}.Where(error => error.Cause.Contains("safe integer range"))
{II}.Select(
{III}error => $"{{Reporting.GenerateJsonPath(error.PathSegments)}}: {{error.Cause}}")
{II}.ToList();
{I}Assert.IsEmpty(errors);

{I}Assert.DoesNotThrow(
{II}() => Our.Jsonization.Serialize.ToJsonObject(instance));

{I}Assert.DoesNotThrow(
{II}() => SerializeToXml(instance));
}}"""
        ),
    ]

    numeric_places = [
        numeric_place
        for numeric_place in intermediate.numeric_places(symbol_table)
        if numeric_place.a_type is intermediate.PrimitiveType.INT
    ]

    if len(numeric_places) > 0:
        blocks.append(
            Stripped(
                f"""\
private static Our.IClass DeserializeFromXml(
{I}string text,
{I}System.Func<System.Xml.XmlReader, Our.IClass> fromXml)
{{
{I}using var stringReader = new System.IO.StringReader(text);
{I}using var xmlReader = System.Xml.XmlReader.Create(stringReader);
{I}xmlReader.MoveToContent();
{I}return fromXml(xmlReader);
}}"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
/// <summary>
/// Assert that the de-serialization from JSON and from XML accepts
/// <paramref name="instance" />, which holds the bound
/// <paramref name="safeValue" /> of the safe integer range, but refuses it
/// once the bound is moved by one out of the range.
/// </summary>
private static void AssertDeserializationChecksTheRange(
{I}Our.IClass instance,
{I}long safeValue,
{I}System.Func<Nodes.JsonNode, Our.IClass> fromJson,
{I}System.Func<System.Xml.XmlReader, Our.IClass> fromXml)
{{
{I}long unsafeValue = safeValue > 0 ? safeValue + 1 : safeValue - 1;
{I}string expectedCause =
{II}$"Expected an integer, but got {{unsafeValue}}, " +
{II}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]";

{I}string jsonText = Our.Jsonization.Serialize.ToJsonObject(instance).ToJsonString();
{I}Assert.IsTrue(jsonText.Contains("9007199254740991"));
{I}Assert.DoesNotThrow(
{II}() => fromJson(Nodes.JsonNode.Parse(jsonText)!));

{I}var jsonException = Assert.Throws<Our.Jsonization.Exception>(
{II}() => fromJson(
{III}Nodes.JsonNode.Parse(
{IIII}jsonText.Replace("9007199254740991", "9007199254740992"))!));
{I}Assert.AreEqual(expectedCause, jsonException!.Cause);

{I}string xmlText = SerializeToXml(instance);
{I}Assert.IsTrue(xmlText.Contains("9007199254740991"));
{I}Assert.DoesNotThrow(
{II}() => DeserializeFromXml(xmlText, fromXml));

{I}var xmlException = Assert.Throws<Our.Xmlization.Exception>(
{II}() => DeserializeFromXml(
{III}xmlText.Replace("9007199254740991", "9007199254740992"),
{III}fromXml));
{I}Assert.AreEqual(expectedCause, xmlException!.Cause);
}}"""
            )
        )

    for numeric_place in numeric_places:
        cls_name = csharp_naming.class_name(numeric_place.cls.name)
        cls_name_json = naming.json_model_type(numeric_place.cls.name)

        mutation = csharp_tests_jsonization.generate_numeric_place_mutation(
            numeric_place
        )

        expected_json_path = (
            numeric_place.prop.json_name
            if numeric_place.index is None
            else f"{numeric_place.prop.json_name}[{numeric_place.index}]"
        )

        test_name_prefix = f"Test_{numeric_place.cls.name}_{numeric_place.prop.name}"

        test_name = csharp_naming.method_name(
            Identifier(f"{test_name_prefix}_outside_the_safe_range")
        )
        blocks.append(
            Stripped(
                f"""\
[Test]
public void {test_name}()
{{
{I}foreach (var value in new long[] {{ 9007199254740992L, -9007199254740992L }})
{I}{{
{II}var instance = Our.Jsonization.Deserialize.{cls_name}From(
{III}LoadTheFirstExpected({csharp_common.string_literal(cls_name_json)}));

{II}{indent_but_first_line(mutation, II)}

{II}AssertRefused(
{III}instance,
{III}$"Expected an integer, but got {{value}}, " +
{III}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]",
{III}{csharp_common.string_literal(expected_json_path)});
{I}}}
}}  // public void {test_name}"""
            )
        )

        test_name = csharp_naming.method_name(
            Identifier(f"{test_name_prefix}_at_the_bounds_of_the_safe_range")
        )
        blocks.append(
            Stripped(
                f"""\
[Test]
public void {test_name}()
{{
{I}foreach (var value in new long[] {{ 9007199254740991L, -9007199254740991L }})
{I}{{
{II}var instance = Our.Jsonization.Deserialize.{cls_name}From(
{III}LoadTheFirstExpected({csharp_common.string_literal(cls_name_json)}));

{II}{indent_but_first_line(mutation, II)}

{II}AssertAccepted(instance);

{II}AssertDeserializationChecksTheRange(
{III}instance,
{III}value,
{III}Our.Jsonization.Deserialize.{cls_name}From,
{III}Our.Xmlization.Deserialize.{cls_name}From);
{I}}}
}}  // public void {test_name}"""
            )
        )

    # NOTE (mristin):
    # We put the integer into an array or an object, as an integer nested in
    # a JSON-able value has to be found at any depth.
    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(
                type_anno,
                (
                    intermediate.JsonValueTypeAnnotation,
                    intermediate.JsonArrayTypeAnnotation,
                ),
            ):
                construction = "new Nodes.JsonArray(Nodes.JsonValue.Create(value))"
                expected_json_path = f"{prop.json_name}[0]"

            elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
                construction = (
                    'new Nodes.JsonObject { ["key"] = Nodes.JsonValue.Create(value) }'
                )
                expected_json_path = f'{prop.json_name}["key"]'

            else:
                continue

            cls_name = csharp_naming.class_name(cls.name)
            cls_name_json = naming.json_model_type(cls.name)
            prop_name = csharp_naming.property_name(prop.name)

            test_name_prefix = f"Test_{cls.name}_{prop.name}"

            test_name = csharp_naming.method_name(
                Identifier(f"{test_name_prefix}_with_an_integer_outside_the_safe_range")
            )
            blocks.append(
                Stripped(
                    f"""\
[Test]
public void {test_name}()
{{
{I}foreach (var value in new long[] {{ 9007199254740992L, -9007199254740992L }})
{I}{{
{II}var instance = Our.Jsonization.Deserialize.{cls_name}From(
{III}LoadTheFirstExpected({csharp_common.string_literal(cls_name_json)}));

{II}instance.{prop_name} = {construction};

{II}AssertRefused(
{III}instance,
{III}$"Expected a JSON-able value, but got the integer {{value}}, " +
{III}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]",
{III}{csharp_common.string_literal(expected_json_path)});
{I}}}
}}  // public void {test_name}"""
                )
            )

            test_name = csharp_naming.method_name(
                Identifier(
                    f"{test_name_prefix}_with_integers_at_the_bounds_of_the_safe_range"
                )
            )
            blocks.append(
                Stripped(
                    f"""\
[Test]
public void {test_name}()
{{
{I}foreach (var value in new long[] {{ 9007199254740991L, -9007199254740991L }})
{I}{{
{II}var instance = Our.Jsonization.Deserialize.{cls_name}From(
{III}LoadTheFirstExpected({csharp_common.string_literal(cls_name_json)}));

{II}instance.{prop_name} = {construction};

{II}AssertAccepted(instance);
{I}}}
}}  // public void {test_name}"""
                )
            )

    if intermediate_uses.json_types(symbol_table):
        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_JsonValueFrom_checks_the_safe_integer_range()
{{
{I}foreach (var value in new long[] {{ 9007199254740992L, -9007199254740992L }})
{I}{{
{II}var exception = Assert.Throws<Our.Jsonization.Exception>(
{III}() => Our.Jsonization.Deserialize.JsonValueFrom(
{IIII}new Nodes.JsonArray(Nodes.JsonValue.Create(value))));
{II}Assert.AreEqual(
{III}$"Expected a JSON-able value, but got the integer {{value}}, " +
{III}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]",
{III}exception!.Cause);
{II}Assert.AreEqual("[0]", exception!.Path);
{I}}}

{I}foreach (var value in new long[] {{ 9007199254740991L, -9007199254740991L }})
{I}{{
{II}Assert.DoesNotThrow(
{III}() => Our.Jsonization.Deserialize.JsonValueFrom(
{IIII}new Nodes.JsonArray(Nodes.JsonValue.Create(value))));
{I}}}
}}  // public void Test_JsonValueFrom_checks_the_safe_integer_range"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using Directory = System.IO.Directory;
using Nodes = System.Text.Json.Nodes;
using Path = System.IO.Path;

using System.Collections.Generic;  // can't alias
using System.Linq;  // can't alias
using NUnit.Framework; // can't alias

namespace {namespace}.Tests
{{
{I}public class TestSafeIntegers
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestSafeIntegers
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
