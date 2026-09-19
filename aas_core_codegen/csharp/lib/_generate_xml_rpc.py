"""Generate code for de/serializing JSON-able values to and from XML."""

import io
import textwrap
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.csharp import common as csharp_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(namespace: csharp_common.NamespaceIdentifier) -> str:
    """
    Generate code for de/serializing JSON-able values to and from XML.

    This implements a restricted subset of XML-RPC's own element vocabulary --
    ``<boolean>``, ``<double>``, ``<string>``, ``<array>``, ``<data>``,
    ``<struct>``, ``<member>``, ``<name>`` and ``<value>`` -- to de/serialize
    a ``System.Text.Json.Nodes.JsonNode`` which is JSON-able (*i.e.*,
    recursively a boolean, a number, a string, an array of JSON-able values or
    an object of JSON-able values with string keys; never JSON ``null``).

    This class does not depend on the meta-model at all, and can be used in
    two different ways:

    * Stand-alone, over a whole ``<value>`` element (see
      <see cref="DeserializeValue" /> and <see cref="SerializeValue" />) --
      this is how it is tested in isolation, and how a user could use it
      directly; and
    * Embedded within a larger XML document, one JSON-able property at
      a time (see <see cref="DeserializeValueFrom" />,
      <see cref="DeserializeArrayBodyFrom" /> and
      <see cref="DeserializeStructBodyFrom" />, and their serialization
      counterparts), consuming/producing nodes on the *same*, already-open
      <c>Xml.XmlReader</c>/<c>Xml.XmlWriter</c> that the rest of the document
      is being read from or written to.

    The ``namespace`` defines the AAS C# namespace.
    """
    blocks = [
        Stripped(
            f"""\
/// <summary>
/// Check the namespace and extract the element's name.
/// </summary>
private static string TryElementName(
{I}Xml.XmlReader reader,
{I}string ns,
{I}out Reporting.Error? error)
{{
{I}if (reader.NodeType != Xml.XmlNodeType.Element
{II}&& reader.NodeType != Xml.XmlNodeType.EndElement)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Expected to be at a start or an end element " +
{III}$"in {{nameof(TryElementName)}}, " +
{III}$"but got: {{reader.NodeType}}");
{I}}}

{I}error = null;
{I}if (reader.NamespaceURI != ns)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected an element within a namespace {{ns}}, " +
{III}$"but got: {{reader.NamespaceURI}}");
{II}return "";
{I}}}

{I}return reader.LocalName;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Consume a start element named <paramref name="expectedName" /> from
/// <paramref name="reader" /> and return whether it was a self-closing
/// (empty) element.
/// </summary>
private static bool ReadStartElement(
{I}Xml.XmlReader reader,
{I}string ns,
{I}string expectedName,
{I}out Reporting.Error? error)
{{
{I}if (reader.EOF)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> element, but got an end-of-file.");
{II}return false;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.Element)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> start element, " +
{III}$"but got the node of type {{reader.NodeType}} " +
{III}$"with the value {{reader.Value}}");
{II}return false;
{I}}}

{I}string elementName = TryElementName(
{II}reader, ns, out error);
{I}if (error != null)
{I}{{
{II}return false;
{I}}}
{I}if (elementName != expectedName)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> element, " +
{III}$"but got an element {{elementName}}");
{II}return false;
{I}}}

{I}bool isEmpty = reader.IsEmptyElement;

{I}// We can consume now the start element.
{I}reader.Read();
{I}return isEmpty;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Consume an end element named <paramref name="expectedName" /> from
/// <paramref name="reader" />.
/// </summary>
private static void ReadEndElement(
{I}Xml.XmlReader reader,
{I}string ns,
{I}string expectedName,
{I}out Reporting.Error? error)
{{
{I}if (reader.EOF)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a </{{expectedName}}> element, but got an end-of-file.");
{II}return;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.EndElement)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a </{{expectedName}}> end element, " +
{III}$"but got the node of type {{reader.NodeType}} " +
{III}$"with the value {{reader.Value}}");
{II}return;
{I}}}

{I}string elementName = TryElementName(
{II}reader, ns, out error);
{I}if (error != null)
{I}{{
{II}return;
{I}}}
{I}if (elementName != expectedName)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a </{{expectedName}}> element, " +
{III}$"but got an end element {{elementName}}");
{II}return;
{I}}}

{I}// We can consume now the end element.
{I}reader.Read();
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Read the text content of the current element (assuming its start
/// element has already been consumed) as a <c>&lt;boolean&gt;</c>'s
/// strict <c>"0"</c>/<c>"1"</c> lexical form.
/// </summary>
/// <remarks>
/// We deliberately do *not* use <see cref="Xml.XmlReader.ReadContentAsBoolean" />,
/// as it accepts <c>true</c>/<c>false</c> -- the lexical form expected
/// everywhere else in this code base -- whereas real XML-RPC tooling
/// expects a strict <c>1</c>/<c>0</c>.
/// </remarks>
private static bool? DeserializeBooleanTextFrom(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}string text;
{I}try
{I}{{
{II}text = reader.ReadContentAsString();
{I}}}
{I}catch (System.Exception exception)
{IIII}when (exception is System.FormatException
{IIIII}|| exception is Xml.XmlException)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected \\"0\\" or \\"1\\" as the text of a <boolean> element, " +
{III}$"but the content could not be read: {{exception}}");
{II}return null;
{I}}}

{I}// NOTE (mristin):
{I}// `whiteSpace` is fixed to `collapse` for every atomic XSD type but
{I}// a string, so a pretty-printed <boolean> has to be read as well.
{I}// Only a <string> keeps its whitespace.
{I}text = text.Trim();

{I}if (text == "1")
{I}{{
{II}return true;
{I}}}
{I}if (text == "0")
{I}{{
{II}return false;
{I}}}

{I}error = new Reporting.Error(
{II}"Expected \\"0\\" or \\"1\\" as the text of a <boolean> element, " +
{II}$"but got: {{text}}");
{I}return null;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Read the text content of the current element (assuming its start
/// element has already been consumed) as a <c>&lt;double&gt;</c>.
/// </summary>
private static double? DeserializeDoubleTextFrom(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}double result;
{I}try
{I}{{
{II}result = reader.ReadContentAsDouble();
{I}}}
{I}catch (System.Exception exception)
{IIII}when (exception is System.FormatException
{IIIII}|| exception is System.OverflowException
{IIIII}|| exception is Xml.XmlException)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a number as the text of a <double> element, " +
{III}$"but the content could not be read: {{exception}}");
{II}return null;
{I}}}

{I}// NOTE (mristin):
{I}// ReadContentAsDouble follows the xs:double lexical rules, which name
{I}// "INF", "-INF" and "NaN". A <double> carries a JSON number, and JSON
{I}// knows neither an infinity nor a not-a-number, so there is no
{I}// JSON-able value for such a text to de-serialize into.
{I}if (!System.Double.IsFinite(result))
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a number representable as a JSON-able value as " +
{III}"the text of a <double> element, " +
{III}$"but got: {{result}}");
{II}return null;
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Read the text content of the current element (assuming its start
/// element has already been consumed) as a <c>&lt;string&gt;</c>
/// (or a <c>&lt;name&gt;</c>, which shares the same lexical form).
/// </summary>
private static string? DeserializeStringTextFrom(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}try
{I}{{
{II}return reader.ReadContentAsString();
{I}}}
{I}catch (System.Exception exception)
{IIII}when (exception is System.FormatException
{IIIII}|| exception is Xml.XmlException)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected text as the content of a <string> element, " +
{III}$"but the content could not be read: {{exception}}");
{II}return null;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Deserialize a JSON-able value, embedded within a larger XML document
/// which is already being read through <paramref name="reader" />.
/// </summary>
/// <remarks>
/// <paramref name="reader" /> is expected to be positioned at the start
/// element of the discriminator (<c>&lt;boolean&gt;</c>,
/// <c>&lt;double&gt;</c>, <c>&lt;string&gt;</c>, <c>&lt;array&gt;</c> or
/// <c>&lt;struct&gt;</c>). On success, <paramref name="reader" /> is left
/// positioned at the node right after the discriminator's own end
/// element.
/// </remarks>
public static Nodes.JsonNode? DeserializeValueFrom(
{I}Xml.XmlReader reader,
{I}string ns,
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}if (reader.EOF || reader.NodeType != Xml.XmlNodeType.Element)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected one of the elements <boolean>, <double>, <string>, " +
{III}"<array> or <struct>, but got " +
{III}(
{IIII}reader.EOF
{IIIII}? "an end-of-file"
{IIIII}: $"the node of type {{reader.NodeType}} " +
{IIIIII}$"with the value {{reader.Value}}"
{III}));
{II}return null;
{I}}}

{I}string discriminator = TryElementName(
{II}reader, ns, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}bool isEmpty = reader.IsEmptyElement;
{I}reader.Read();

{I}Nodes.JsonNode? result;
{I}switch (discriminator)
{I}{{
{II}case "boolean":
{III}if (isEmpty)
{III}{{
{IIII}error = new Reporting.Error(
{IIIII}"Expected \\"0\\" or \\"1\\" as the text of a <boolean> " +
{IIIII}"element, but got no content at all");
{IIII}return null;
{III}}}

{III}bool? boolValue = DeserializeBooleanTextFrom(
{IIII}reader, out error);
{III}if (error != null)
{III}{{
{IIII}return null;
{III}}}

{III}result = Nodes.JsonValue.Create(
{IIII}boolValue
{IIIII}?? throw new System.InvalidOperationException(
{IIIIII}"Unexpected boolValue null when error null"));
{III}break;

{II}case "double":
{III}if (isEmpty)
{III}{{
{IIII}error = new Reporting.Error(
{IIIII}"Expected a number as the text of a <double> element, " +
{IIIII}"but got no content at all");
{IIII}return null;
{III}}}

{III}double? doubleValue = DeserializeDoubleTextFrom(
{IIII}reader, out error);
{III}if (error != null)
{III}{{
{IIII}return null;
{III}}}

{III}result = Nodes.JsonValue.Create(
{IIII}doubleValue
{IIIII}?? throw new System.InvalidOperationException(
{IIIIII}"Unexpected doubleValue null when error null"));
{III}break;

{II}case "string":
{III}string stringValue;
{III}if (isEmpty)
{III}{{
{IIII}stringValue = "";
{III}}}
{III}else
{III}{{
{IIII}string? maybeString = DeserializeStringTextFrom(
{IIIII}reader, out error);
{IIII}if (error != null)
{IIII}{{
{IIIII}return null;
{IIII}}}

{IIII}stringValue = maybeString
{IIIII}?? throw new System.InvalidOperationException(
{IIIIII}"Unexpected string value null when error null");
{III}}}

{III}result = Nodes.JsonValue.Create(stringValue);
{III}break;

{II}case "array":
{III}if (isEmpty)
{III}{{
{IIII}error = new Reporting.Error(
{IIIII}"Expected a <data> element as the content of an <array> " +
{IIIII}"element, but got no content at all");
{IIII}return null;
{III}}}

{III}result = DeserializeArrayBodyFrom(
{IIII}reader, ns, out error);
{III}if (error != null)
{III}{{
{IIII}return null;
{III}}}
{III}break;

{II}case "struct":
{III}result = isEmpty
{IIII}? new Nodes.JsonObject()
{IIII}: DeserializeStructBodyFrom(reader, ns, out error);
{III}if (error != null)
{III}{{
{IIII}return null;
{III}}}
{III}break;

{II}default:
{III}error = new Reporting.Error(
{IIII}"Expected one of the elements <boolean>, <double>, <string>, " +
{IIII}$"<array> or <struct>, but got: <{{discriminator}}>");
{III}return null;
{I}}}

{I}if (!isEmpty)
{I}{{
{II}ReadEndElement(reader, ns, discriminator, out error);
{II}if (error != null)
{II}{{
{III}return null;
{II}}}
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Deserialize a single item of a <c>&lt;data&gt;</c> array, positioned
/// at the item's own <c>&lt;value&gt;</c> start element.
/// </summary>
private static Nodes.JsonNode? DeserializeArrayItemFrom(
{I}Xml.XmlReader reader,
{I}string ns,
{I}out Reporting.Error? error)
{{
{I}bool isEmpty = ReadStartElement(
{II}reader, ns, "value", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}if (isEmpty)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected one of the elements <boolean>, <double>, <string>, " +
{III}"<array> or <struct> as the content of a <value> element, " +
{III}"but got no content at all");
{II}return null;
{I}}}

{I}Nodes.JsonNode? result = DeserializeValueFrom(
{II}reader, ns, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}ReadEndElement(reader, ns, "value", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Deserialize a JSON array's body, embedded within a larger XML document
/// which is already being read through <paramref name="reader" />.
/// </summary>
/// <remarks>
/// <paramref name="reader" /> is expected to be positioned at the start
/// element <c>&lt;data&gt;</c>. On success, <paramref name="reader" /> is
/// left positioned at the node right after the <c>&lt;data&gt;</c>
/// element's own end element.
/// </remarks>
public static Nodes.JsonArray? DeserializeArrayBodyFrom(
{I}Xml.XmlReader reader,
{I}string ns,
{I}out Reporting.Error? error)
{{
{I}bool isEmptyData = ReadStartElement(
{II}reader, ns, "data", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}var result = new Nodes.JsonArray();

{I}if (isEmptyData)
{I}{{
{II}return result;
{I}}}

{I}int index = 0;
{I}while (reader.NodeType == Xml.XmlNodeType.Element)
{I}{{
{II}Nodes.JsonNode? item = DeserializeArrayItemFrom(
{III}reader, ns, out error);
{II}if (error != null)
{II}{{
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(index));
{III}return null;
{II}}}

{II}result.Add(item);
{II}index++;
{I}}}

{I}ReadEndElement(reader, ns, "data", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Deserialize a single <c>&lt;member&gt;</c> of a <c>&lt;struct&gt;</c>,
/// positioned at the member's own start element.
/// </summary>
private static Nodes.JsonNode? DeserializeMemberFrom(
{I}Xml.XmlReader reader,
{I}string ns,
{I}out string key,
{I}out Reporting.Error? error)
{{
{I}key = "";

{I}bool isEmptyMember = ReadStartElement(
{II}reader, ns, "member", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}
{I}if (isEmptyMember)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a <name> and a <value> element as the content of " +
{III}"a <member> element, but got no content at all");
{II}return null;
{I}}}

{I}bool isEmptyName = ReadStartElement(
{II}reader, ns, "name", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}if (isEmptyName)
{I}{{
{II}key = "";
{I}}}
{I}else
{I}{{
{II}key = DeserializeStringTextFrom(reader, out error)
{III}?? throw new System.InvalidOperationException(
{IIII}"Unexpected key null when error null");
{II}if (error != null)
{II}{{
{III}return null;
{II}}}

{II}ReadEndElement(reader, ns, "name", out error);
{II}if (error != null)
{II}{{
{III}return null;
{II}}}
{I}}}

{I}bool isEmptyValue = ReadStartElement(
{II}reader, ns, "value", out error);
{I}if (error != null)
{I}{{
{II}error.PrependSegment(
{III}new Reporting.NameSegment(key));
{II}return null;
{I}}}
{I}if (isEmptyValue)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected one of the elements <boolean>, <double>, <string>, " +
{III}"<array> or <struct> as the content of a <value> element, " +
{III}"but got no content at all");
{II}error.PrependSegment(
{III}new Reporting.NameSegment(key));
{II}return null;
{I}}}

{I}Nodes.JsonNode? item = DeserializeValueFrom(
{II}reader, ns, out error);
{I}if (error != null)
{I}{{
{II}error.PrependSegment(
{III}new Reporting.NameSegment(key));
{II}return null;
{I}}}

{I}ReadEndElement(reader, ns, "value", out error);
{I}if (error != null)
{I}{{
{II}error.PrependSegment(
{III}new Reporting.NameSegment(key));
{II}return null;
{I}}}

{I}ReadEndElement(reader, ns, "member", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}return item;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Deserialize a JSON object's body, embedded within a larger XML document
/// which is already being read through <paramref name="reader" />.
/// </summary>
/// <remarks>
/// <paramref name="reader" /> is expected to be positioned either at
/// the first <c>&lt;member&gt;</c> start element, or already at
/// the enclosing element's own end element if there are no members at
/// all. On success, <paramref name="reader" /> is left positioned at
/// that same enclosing element's end element -- unlike
/// <see cref="DeserializeArrayBodyFrom" />, this function does *not*
/// consume a wrapper element of its own, mirroring how a
/// <c>JSONObject</c>-typed property is represented directly as
/// zero or more <c>&lt;member&gt;</c> elements with no enclosing
/// <c>&lt;struct&gt;</c>.
/// </remarks>
public static Nodes.JsonObject? DeserializeStructBodyFrom(
{I}Xml.XmlReader reader,
{I}string ns,
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}var result = new Nodes.JsonObject();

{I}while (reader.NodeType == Xml.XmlNodeType.Element)
{I}{{
{II}Nodes.JsonNode? item = DeserializeMemberFrom(
{III}reader, ns, out string key, out error);
{II}if (error != null)
{II}{{
{III}return null;
{II}}}

{II}// NOTE (mristin):
{II}// A repeated <member> name is refused, just as a repeated property
{II}// element is refused in the xmlization. Letting the later member win
{II}// -- what Nodes.JsonObject's own indexer assignment would do --
{II}// would silently accept a document which says two different things
{II}// about the same key.
{II}if (result.ContainsKey(key))
{II}{{
{III}error = new Reporting.Error(
{IIII}$"The member {{key}} occurred more than once");
{III}return null;
{II}}}

{II}result[key] = item;
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Deserialize a JSON-able value from a stand-alone XML-RPC
/// <c>&lt;value&gt;</c> element.
/// </summary>
/// <remarks>
/// <paramref name="reader" /> is expected to be positioned at
/// the <c>&lt;value&gt;</c> start element itself (as opposed to
/// <see cref="DeserializeValueFrom" />, which expects to be positioned at
/// the discriminator directly).
/// </remarks>
public static Nodes.JsonNode? DeserializeValue(
{I}Xml.XmlReader reader,
{I}string ns,
{I}out Reporting.Error? error)
{{
{I}bool isEmpty = ReadStartElement(
{II}reader, ns, "value", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}if (isEmpty)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected one of the elements <boolean>, <double>, <string>, " +
{III}"<array> or <struct> as the content of a <value> element, " +
{III}"but got no content at all");
{II}return null;
{I}}}

{I}Nodes.JsonNode? result = DeserializeValueFrom(
{II}reader, ns, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}ReadEndElement(reader, ns, "value", out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize <paramref name="that" />, embedded within a larger XML
/// document which is already being written through
/// <paramref name="writer" />.
/// </summary>
/// <remarks>
/// This writes exactly one discriminator element (<c>&lt;boolean&gt;</c>,
/// <c>&lt;double&gt;</c>, <c>&lt;string&gt;</c>, <c>&lt;array&gt;</c> or
/// <c>&lt;struct&gt;</c>). <paramref name="that" /> must be JSON-able
/// (recursively a boolean, a number, a string, an array or an object with
/// string keys), and never <c>null</c>, or a
/// <see cref="System.ArgumentException" /> is thrown -- a well-typed
/// caller (whose value has already been verified) should never hit this.
/// </remarks>
public static void SerializeValueTo(
{I}Nodes.JsonNode? that,
{I}Xml.XmlWriter writer,
{I}string ns)
{{
{I}switch (that)
{I}{{
{II}case null:
{III}throw new System.ArgumentException(
{IIII}"Expected a JSON-able value (a boolean, a number, a string, " +
{IIII}"an array or an object), but got null");

{II}case Nodes.JsonArray jsonArray:
{III}writer.WriteStartElement("array", ns);
{III}SerializeArrayBodyTo(jsonArray, writer, ns);
{III}writer.WriteEndElement();
{III}break;

{II}case Nodes.JsonObject jsonObject:
{III}writer.WriteStartElement("struct", ns);
{III}SerializeStructBodyTo(jsonObject, writer, ns);
{III}writer.WriteEndElement();
{III}break;

{II}case Nodes.JsonValue jsonValue:
{III}if (jsonValue.TryGetValue(out bool boolValue))
{III}{{
{IIII}writer.WriteStartElement("boolean", ns);
{IIII}// NOTE (mristin):
{IIII}// We deliberately do *not* use ``writer.WriteValue(bool)``, as it
{IIII}// writes ``true``/``false`` -- the lexical form expected
{IIII}// everywhere else in this code base -- whereas real XML-RPC
{IIII}// tooling expects a strict ``1``/``0``, which is also what
{IIII}// DeserializeBooleanTextFrom requires.
{IIII}writer.WriteString(boolValue ? "1" : "0");
{IIII}writer.WriteEndElement();
{III}}}
{III}else if (jsonValue.TryGetValue(out double doubleValue))
{III}{{
{IIII}// NOTE (mristin):
{IIII}// JSON knows neither an infinity nor a not-a-number, so neither
{IIII}// is a JSON-able value. XmlWriter would happily write "INF" or
{IIII}// "NaN" -- the xs:double spellings -- which
{IIII}// DeserializeDoubleTextFrom deliberately refuses to read back.
{IIII}if (!System.Double.IsFinite(doubleValue))
{IIII}{{
{IIIII}throw new System.ArgumentException(
{IIIIII}$"Expected a JSON-able value, but got the number " +
{IIIIII}$"{{doubleValue}}, which is neither finite nor " +
{IIIIII}"representable in JSON");
{IIII}}}

{IIII}writer.WriteStartElement("double", ns);
{IIII}writer.WriteValue(doubleValue);
{IIII}writer.WriteEndElement();
{III}}}
{III}else if (jsonValue.TryGetValue(out string? stringValue))
{III}{{
{IIII}writer.WriteStartElement("string", ns);
{IIII}writer.WriteValue(stringValue!);
{IIII}writer.WriteEndElement();
{III}}}
{III}else
{III}{{
{IIII}throw new System.ArgumentException(
{IIIII}"Expected a JSON-able value (a boolean, a number, a string, " +
{IIIII}"an array or an object), but got a value of an unexpected " +
{IIIII}$"underlying type: {{jsonValue}}");
{III}}}
{III}break;

{II}default:
{III}throw new System.ArgumentException(
{IIII}"Expected a JSON-able value (a boolean, a number, a string, " +
{IIII}$"an array or an object), but got: {{that.GetType()}}");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize the JSON array <paramref name="that" />'s body, embedded
/// within a larger XML document which is already being written through
/// <paramref name="writer" />.
/// </summary>
/// <remarks>
/// This writes exactly one <c>&lt;data&gt;</c> element.
/// </remarks>
public static void SerializeArrayBodyTo(
{I}Nodes.JsonArray that,
{I}Xml.XmlWriter writer,
{I}string ns)
{{
{I}writer.WriteStartElement("data", ns);

{I}int index = 0;
{I}foreach (Nodes.JsonNode? item in that)
{I}{{
{II}writer.WriteStartElement("value", ns);
{II}try
{II}{{
{III}SerializeValueTo(item, writer, ns);
{II}}}
{II}catch (System.ArgumentException exception)
{II}{{
{III}throw new System.ArgumentException(
{IIII}$"At the index {{index}}: {{exception.Message}}", exception);
{II}}}
{II}writer.WriteEndElement();
{II}index++;
{I}}}

{I}writer.WriteEndElement();
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize the JSON object <paramref name="that" />'s body, embedded
/// within a larger XML document which is already being written through
/// <paramref name="writer" />.
/// </summary>
/// <remarks>
/// This writes zero or more <c>&lt;member&gt;</c> elements, with no
/// enclosing element of its own -- mirrors
/// <see cref="DeserializeStructBodyFrom" /> on the reading side.
/// </remarks>
public static void SerializeStructBodyTo(
{I}Nodes.JsonObject that,
{I}Xml.XmlWriter writer,
{I}string ns)
{{
{I}foreach (
{II}System.Collections.Generic.KeyValuePair<string, Nodes.JsonNode?> member
{III}in that)
{I}{{
{II}writer.WriteStartElement("member", ns);

{II}writer.WriteStartElement("name", ns);
{II}writer.WriteValue(member.Key);
{II}writer.WriteEndElement();

{II}writer.WriteStartElement("value", ns);
{II}try
{II}{{
{III}SerializeValueTo(member.Value, writer, ns);
{II}}}
{II}catch (System.ArgumentException exception)
{II}{{
{III}throw new System.ArgumentException(
{IIII}$"At the member \\"{{member.Key}}\\": {{exception.Message}}",
{IIII}exception);
{II}}}
{II}writer.WriteEndElement();

{II}writer.WriteEndElement();
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize <paramref name="that" /> to a stand-alone XML-RPC
/// <c>&lt;value&gt;</c> element, written through <paramref name="writer" />.
/// </summary>
public static void SerializeValue(
{I}Nodes.JsonNode? that,
{I}Xml.XmlWriter writer,
{I}string ns)
{{
{I}writer.WriteStartElement("value", ns);
{I}SerializeValueTo(that, writer, ns);
{I}writer.WriteEndElement();
}}"""
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    writer.write(
        f"""\
namespace {namespace}
{{
{I}/// <summary>
{I}/// Provide de/serialization of JSON-able values to/from a restricted
{I}/// subset of XML-RPC's own element vocabulary.
{I}/// </summary>
{I}public static class XmlRpc
{I}{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, II))

    writer.write(f"\n{I}}}  // public static class XmlRpc")
    writer.write(f"\n}}  // namespace {namespace}")

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using Xml = System.Xml;
using Nodes = System.Text.Json.Nodes;"""
        )
    )

    final_blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(writer.getvalue()),
        csharp_common.WARNING,
    ]

    final_writer = io.StringIO()
    for i, block in enumerate(final_blocks):
        if i > 0:
            final_writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        final_writer.write(block)

    final_writer.write("\n")

    return final_writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
