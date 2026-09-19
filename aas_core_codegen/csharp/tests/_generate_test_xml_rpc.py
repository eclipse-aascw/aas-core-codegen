"""Generate code to test the ``XmlRpc`` module in isolation."""

from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common
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
def generate(namespace: csharp_common.NamespaceIdentifier) -> str:
    """
    Generate code to test the ``XmlRpc`` module in isolation.

    This does not depend on the meta-model at all -- ``XmlRpc`` de/serializes
    a generic ``System.Text.Json.Nodes.JsonNode``, never a meta-model class,
    so it can (and should) be tested against hand-crafted values directly,
    independent of whatever meta-model happens to be given.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    ns_value = "https://example.com/xml-rpc"
    other_ns_value = "https://example.com/xml-rpc/other"

    ns_literal = csharp_common.string_literal(ns_value)

    blocks = [
        Stripped(
            f"""\
private const string Ns = {ns_literal};"""
        ),
        Stripped(
            f"""\
private static string SerializeToString(Nodes.JsonNode? that)
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
{II}Aas.XmlRpc.SerializeValue(that, writer, Ns);
{I}}}
{I}return builder.ToString();
}}"""
        ),
        Stripped(
            f"""\
private static Nodes.JsonNode? DeserializeFromString(
{I}string text,
{I}string ns,
{I}out Aas.Reporting.Error? error)
{{
{I}using var stringReader = new System.IO.StringReader(text);
{I}using var xmlReader = System.Xml.XmlReader.Create(stringReader);
{I}xmlReader.MoveToContent();
{I}return Aas.XmlRpc.DeserializeValue(xmlReader, ns, out error);
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_round_trip_boolean()
{{
{I}foreach (bool value in new[] {{ true, false }})
{I}{{
{II}Nodes.JsonNode original = Nodes.JsonValue.Create(value);
{II}string text = SerializeToString(original);

{II}Nodes.JsonNode? roundTripped = DeserializeFromString(
{III}text, Ns, out Aas.Reporting.Error? error);

{II}Assert.IsNull(error);
{II}Assert.IsNotNull(roundTripped);
{II}Assert.AreEqual(
{III}original.ToJsonString(),
{III}roundTripped!.ToJsonString());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_round_trip_double()
{{
{I}foreach (double value in new[]
{I}{{
{II}0.0, -0.0, 1.5, -123.456, 1.2345678901234567
{I}}})
{I}{{
{II}Nodes.JsonNode original = Nodes.JsonValue.Create(value);
{II}string text = SerializeToString(original);

{II}Nodes.JsonNode? roundTripped = DeserializeFromString(
{III}text, Ns, out Aas.Reporting.Error? error);

{II}Assert.IsNull(error);
{II}Assert.IsNotNull(roundTripped);

{II}bool ok = roundTripped!.AsValue().TryGetValue(out double gotValue);
{II}Assert.IsTrue(ok);
{II}Assert.AreEqual(value, gotValue);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_round_trip_string()
{{
{I}foreach (string value in new[]
{I}{{
{II}"",
{II}"hello",
{II}"a < b & c > d \\" e ' f"
{I}}})
{I}{{
{II}Nodes.JsonNode original = Nodes.JsonValue.Create(value);
{II}string text = SerializeToString(original);

{II}Nodes.JsonNode? roundTripped = DeserializeFromString(
{III}text, Ns, out Aas.Reporting.Error? error);

{II}Assert.IsNull(error);
{II}Assert.IsNotNull(roundTripped);
{II}Assert.AreEqual(
{III}value,
{III}roundTripped!.AsValue().GetValue<string>());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_round_trip_empty_array()
{{
{I}Nodes.JsonNode original = new Nodes.JsonArray();
{I}string text = SerializeToString(original);

{I}Nodes.JsonNode? roundTripped = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(error);
{I}Assert.IsNotNull(roundTripped);
{I}Assert.AreEqual(
{II}original.ToJsonString(),
{II}roundTripped!.ToJsonString());
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_round_trip_nested_array()
{{
{I}Nodes.JsonNode original = new Nodes.JsonArray(
{II}Nodes.JsonValue.Create(true),
{II}new Nodes.JsonArray(
{III}Nodes.JsonValue.Create("nested"),
{III}Nodes.JsonValue.Create(42.5)),
{II}new Nodes.JsonObject
{II}{{
{III}["key"] = Nodes.JsonValue.Create("value")
{II}}});

{I}string text = SerializeToString(original);

{I}Nodes.JsonNode? roundTripped = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(error);
{I}Assert.IsNotNull(roundTripped);
{I}Assert.AreEqual(
{II}original.ToJsonString(),
{II}roundTripped!.ToJsonString());
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_round_trip_empty_object()
{{
{I}Nodes.JsonNode original = new Nodes.JsonObject();
{I}string text = SerializeToString(original);

{I}Nodes.JsonNode? roundTripped = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(error);
{I}Assert.IsNotNull(roundTripped);
{I}Assert.AreEqual(
{II}original.ToJsonString(),
{II}roundTripped!.ToJsonString());
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_round_trip_nested_object()
{{
{I}Nodes.JsonNode original = new Nodes.JsonObject
{I}{{
{II}["aBoolean"] = Nodes.JsonValue.Create(false),
{II}["anArray"] = new Nodes.JsonArray(
{III}Nodes.JsonValue.Create(1.0),
{III}Nodes.JsonValue.Create(2.0)),
{II}["anObject"] = new Nodes.JsonObject
{II}{{
{III}["nested"] = Nodes.JsonValue.Create("value")
{II}}}
{I}}};

{I}string text = SerializeToString(original);

{I}Nodes.JsonNode? roundTripped = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(error);
{I}Assert.IsNotNull(roundTripped);
{I}Assert.AreEqual(
{II}original.ToJsonString(),
{II}roundTripped!.ToJsonString());
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_serialize_rejects_null()
{{
{I}System.ArgumentException? caught = null;
{I}try
{I}{{
{II}SerializeToString(null);
{I}}}
{I}catch (System.ArgumentException exception)
{I}{{
{II}caught = exception;
{I}}}

{I}Assert.IsNotNull(caught);
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_serialize_reports_index_on_nested_invalid_value()
{{
{I}Nodes.JsonNode original = new Nodes.JsonArray(
{II}Nodes.JsonValue.Create(1.0),
{II}Nodes.JsonValue.Create(2.0),
{II}null);

{I}System.ArgumentException? caught = null;
{I}try
{I}{{
{II}SerializeToString(original);
{I}}}
{I}catch (System.ArgumentException exception)
{I}{{
{II}caught = exception;
{I}}}

{I}Assert.IsNotNull(caught);
{I}Assert.IsTrue(
{II}caught!.Message.Contains("At the index 2"),
{II}$"Unexpected message: {{caught.Message}}");
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_deserialize_reports_path_on_nested_error()
{{
{I}string text = (
{II}$"<value xmlns=\\"{{Ns}}\\">"
{III}+ "<array><data>"
{IIII}+ "<value><boolean>1</boolean></value>"
{IIII}+ "<value><nil/></value>"
{III}+ "</data></array>"
{II}+ "</value>");

{I}Nodes.JsonNode? result = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(result);
{I}Assert.IsNotNull(error);
{I}Assert.AreEqual(
{II}"[1]",
{II}Aas.Reporting.GenerateJsonPath(error!.PathSegments));
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_deserialize_rejects_unexpected_element()
{{
{I}string text = $"<value xmlns=\\"{{Ns}}\\"><nil/></value>";

{I}Nodes.JsonNode? result = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(result);
{I}Assert.IsNotNull(error);
{I}Assert.IsTrue(
{II}error!.Cause.Contains("nil"),
{II}$"Unexpected cause: {{error.Cause}}");
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_deserialize_rejects_non_strict_boolean_lexical_form()
{{
{I}string text = $"<value xmlns=\\"{{Ns}}\\"><boolean>true</boolean></value>";

{I}Nodes.JsonNode? result = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(result);
{I}Assert.IsNotNull(error);
{I}Assert.IsTrue(
{II}error!.Cause.Contains("\\"0\\" or \\"1\\""),
{II}$"Unexpected cause: {{error.Cause}}");
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_deserialize_rejects_repeated_member_key()
{{
{I}string text = (
{II}$"<value xmlns=\\"{{Ns}}\\">"
{III}+ "<struct>"
{IIII}+ "<member><name>k</name><value><string>first</string></value></member>"
{IIII}+ "<member><name>k</name><value><string>second</string></value></member>"
{III}+ "</struct>"
{II}+ "</value>");

{I}// NOTE (mristin):
{I}// A repeated <member> name is refused, just as a repeated property
{I}// element is refused in the xmlization -- letting the later member win
{I}// would silently accept a document which says two different things
{I}// about the same key.
{I}DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNotNull(error);
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_serialize_rejects_non_finite_number()
{{
{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so neither is
{I}// a JSON-able value, even though Nodes.JsonValue holds one happily.
{I}foreach (double value in new[]
{I}{{
{II}double.PositiveInfinity, double.NegativeInfinity, double.NaN
{I}}})
{I}{{
{II}System.ArgumentException? caught = null;
{II}try
{II}{{
{III}SerializeToString(Nodes.JsonValue.Create(value));
{II}}}
{II}catch (System.ArgumentException exception)
{II}{{
{III}caught = exception;
{II}}}

{II}Assert.IsNotNull(caught, $"Unexpectedly serialized {{value}}");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_deserialize_rejects_non_finite_number()
{{
{I}// NOTE (mristin):
{I}// The xs:double spellings of the three special values are read by
{I}// ReadContentAsDouble, but none of them is a JSON-able value.
{I}foreach (string numeral in new[] {{ "INF", "-INF", "NaN" }})
{I}{{
{II}string text = (
{III}$"<value xmlns=\\"{{Ns}}\\">"
{IIII}+ $"<double>{{numeral}}</double>"
{III}+ "</value>");

{II}DeserializeFromString(
{III}text, Ns, out Aas.Reporting.Error? error);

{II}Assert.IsNotNull(error, $"Unexpectedly accepted <double>{{numeral}}</double>");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_deserialize_collapses_the_whitespace_of_a_boolean_and_a_double()
{{
{I}// NOTE (mristin):
{I}// `whiteSpace` is fixed to `collapse` for every atomic XSD type but
{I}// a string, so a pretty-printed document has to be read as well.
{I}string booleanText = (
{II}$"<value xmlns=\\"{{Ns}}\\">"
{III}+ "<boolean>\\n  1\\n  </boolean>"
{II}+ "</value>");

{I}Nodes.JsonNode? booleanResult = DeserializeFromString(
{II}booleanText, Ns, out Aas.Reporting.Error? booleanError);

{I}Assert.IsNull(booleanError);
{I}Assert.IsNotNull(booleanResult);
{I}Assert.IsTrue(booleanResult!.AsValue().GetValue<bool>());

{I}string doubleText = (
{II}$"<value xmlns=\\"{{Ns}}\\">"
{III}+ "<double>\\n  3.14\\n  </double>"
{II}+ "</value>");

{I}Nodes.JsonNode? doubleResult = DeserializeFromString(
{II}doubleText, Ns, out Aas.Reporting.Error? doubleError);

{I}Assert.IsNull(doubleError);
{I}Assert.IsNotNull(doubleResult);
{I}Assert.AreEqual(3.14, doubleResult!.AsValue().GetValue<double>());
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_deserialize_preserves_the_whitespace_of_a_string()
{{
{I}// NOTE (mristin):
{I}// `xs:string` is `preserve` and not `collapse`, so a <string> keeps
{I}// its whitespace, unlike a <boolean> or a <double>.
{I}string text = (
{II}$"<value xmlns=\\"{{Ns}}\\">"
{III}+ "<string>  keep  me  </string>"
{II}+ "</value>");

{I}Nodes.JsonNode? result = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(error);
{I}Assert.IsNotNull(result);
{I}Assert.AreEqual(
{II}"  keep  me  ",
{II}result!.AsValue().GetValue<string>());
}}"""
        ),
        Stripped(
            f"""\
[Test]
public void Test_deserialize_rejects_namespace_mismatch()
{{
{I}string text = (
{II}"<value xmlns=\\"{other_ns_value}\\">"
{III}+ "<boolean>1</boolean>"
{II}+ "</value>");

{I}Nodes.JsonNode? result = DeserializeFromString(
{II}text, Ns, out Aas.Reporting.Error? error);

{I}Assert.IsNull(result);
{I}Assert.IsNotNull(error);
{I}Assert.IsTrue(
{II}error!.Cause.Contains("namespace"),
{II}$"Unexpected cause: {{error.Cause}}");
}}"""
        ),
    ]  # type: List[Stripped]

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Aas = {namespace};  // renamed

using Nodes = System.Text.Json.Nodes;

using NUnit.Framework; // can't alias

namespace {namespace}.Tests
{{
{I}public class TestXmlRpc
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestXmlRpc
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
