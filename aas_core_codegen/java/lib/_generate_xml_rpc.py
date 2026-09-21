"""Generate the code for de/serializing JSON-able values to and from XML."""

from typing import List

from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


def _generate_readers() -> List[Stripped]:
    """
    Generate the readers of the XML-RPC subset.

    Only ``readValueContent``, ``readArrayContent`` and ``readObjectContent``
    are public: they read the *content* of an element which the caller has
    already opened, so that the xmlization can hand over the very reader it
    reads the enclosing document with.
    """
    return [
        Stripped(
            f"""\
/**
 * Match a numeral of the {{@code <double>}} lexical space.
 *
 * <p>This is the numeric part of the lexical space of {{@code xs:double}},
 * and deliberately not its three named literals -- {{@code INF}},
 * {{@code -INF}} and {{@code NaN}} -- since a JSON number can be none of them.
 */
private static final Pattern XML_RPC_DOUBLE = Pattern.compile(
{I}"^(\\\\+|-)?([0-9]+(\\\\.[0-9]*)?|\\\\.[0-9]+)([Ee](\\\\+|-)?[0-9]+)?$");"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of an element holding a JSON-able value.
 *
 * <p>The content is a single discriminator element -- {{@code <boolean>}},
 * {{@code <double>}}, {{@code <string>}}, {{@code <array>}} or
 * {{@code <struct>}} -- which says what the value is.
 */
public static Reporting.Result<JsonNode> readValueContent(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected one of the elements boolean, double, string, array or " +
{III}"struct as the content of the element, but the element was empty"));
{I}}}

{I}final Reporting.Result<String> tryElementName = XmlCommon.peekElementNameInNoNamespace(reader);
{I}if (tryElementName.isError()) {{
{II}return Reporting.Result.failure(tryElementName.getError());
{I}}}

{I}final String local = tryElementName.getResult();
{I}final boolean isEmptyDiscriminator = XmlCommon.isEmptyElement(reader);

{I}final Reporting.Result<JsonNode> result =
{II}readXmlRpcDiscriminator(reader, local, isEmptyDiscriminator);
{I}if (result.isError()) {{
{II}// NOTE (mristin):
{II}// The discriminator element has been entered, so it is a step of
{II}// the path -- unlike the element which is no discriminator at all,
{II}// which readXmlRpcDiscriminator refuses without a step, as naming it
{II}// in the path as well as in the message would say nothing more.
{II}if (!isUnexpectedDiscriminator(local)) {{
{III}result.getError().prependSegment(new Reporting.NameSegment(local));
{II}}}
{II}return result;
{I}}}

{I}final Reporting.Result<XMLEvent> endResult = XmlCommon.consumeEndElementInNoNamespace(reader, local);
{I}if (endResult.isError()) {{
{II}endResult.getError().prependSegment(new Reporting.NameSegment(local));
{II}return Reporting.Result.failure(endResult.getError());
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Tell whether {{@code local}} names no discriminator element at all.
 */
private static boolean isUnexpectedDiscriminator(String local) {{
{I}switch (local) {{
{II}case "boolean":
{II}case "double":
{II}case "string":
{II}case "array":
{II}case "struct":
{III}return false;
{II}default:
{III}return true;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of the discriminator element named {{@code local}}.
 */
private static Reporting.Result<JsonNode> readXmlRpcDiscriminator(
{I}XMLEventReader reader, String local, boolean isEmpty) {{
{I}switch (local) {{
{II}case "boolean":
{III}return readXmlRpcBoolean(reader, isEmpty);
{II}case "double":
{III}return readXmlRpcDouble(reader, isEmpty);
{II}case "string":
{III}return readXmlRpcString(reader, isEmpty);
{II}case "array": {{
{III}final Reporting.Result<ArrayNode> arrayResult =
{IIII}readArrayContent(reader, isEmpty);
{III}return arrayResult.isError()
{IIII}? Reporting.Result.failure(arrayResult.getError())
{IIII}: Reporting.Result.success(arrayResult.getResult());
{II}}}
{II}case "struct": {{
{III}final Reporting.Result<ObjectNode> objectResult =
{IIII}readObjectContent(reader, isEmpty);
{III}return objectResult.isError()
{IIII}? Reporting.Result.failure(objectResult.getError())
{IIII}: Reporting.Result.success(objectResult.getResult());
{II}}}
{II}default:
{III}return Reporting.Result.failure(new Reporting.Error(
{IIII}"Expected a discriminator element (one of boolean, double, " +
{IIII}"string, array or struct), but got: " + local));
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of a {{@code <boolean>}} element.
 *
 * <p>Real XML-RPC tooling writes and expects a strict {{@code 1}}/{{@code 0}},
 * and not the {{@code true}}/{{@code false}} which {{@code xs:boolean}} and
 * the rest of this module use.
 */
private static Reporting.Result<JsonNode> readXmlRpcBoolean(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}final String text = isEmpty ? "" : readXmlRpcCollapsedText(reader);

{I}if ("1".equals(text)) {{
{II}return Reporting.Result.success(
{III}JsonNodeFactory.instance.booleanNode(true));
{I}}}
{I}if ("0".equals(text)) {{
{II}return Reporting.Result.success(
{III}JsonNodeFactory.instance.booleanNode(false));
{I}}}

{I}return Reporting.Result.failure(new Reporting.Error(
{II}"Expected \\"0\\" or \\"1\\" as the text of a boolean element, " +
{II}"but got: " + text));
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of a {{@code <double>}} element.
 */
private static Reporting.Result<JsonNode> readXmlRpcDouble(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}final String text = isEmpty ? "" : readXmlRpcCollapsedText(reader);

{I}// NOTE (mristin):
{I}// The lexical form is matched before the text is converted.
{I}// Double.parseDouble reads more than we admit here: a hexadecimal
{I}// literal, a trailing type suffix, and the spellings "Infinity" and
{I}// "NaN".
{I}//
{I}// Mind that the numeral excludes "INF", "-INF" and "NaN" on purpose,
{I}// unlike xs:double, which names all three. A double element carries
{I}// a JSON number, and JSON knows neither an infinity nor a not-a-number,
{I}// so there is no JSON-able value for such a text to read into.
{I}if (!XML_RPC_DOUBLE.matcher(text).matches()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected a number as the text of a double element, " +
{III}"but got: " + text));
{I}}}

{I}final double value = Double.parseDouble(text);

{I}// NOTE (mristin):
{I}// A literal too large for a double gives an infinity, which is no
{I}// JSON-able value either, so it is refused rather than rounded.
{I}if (Double.isInfinite(value) || Double.isNaN(value)) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected a number representable as a JSON-able value as the text " +
{III}"of a double element, but got: " + text));
{I}}}

{I}// NOTE (mristin):
{I}// A numeral with neither a fraction nor an exponent gives a long node,
{I}// and anything else a double node. Jackson tells the two apart, and so
{I}// does a JSON document, so reading every double element as a double
{I}// node would silently turn the 1 of a document into a 1.0 on the way
{I}// through XML, and back again.
{I}if (text.indexOf('.') < 0
{II}&& text.indexOf('e') < 0
{II}&& text.indexOf('E') < 0) {{
{II}try {{
{III}return Reporting.Result.success(
{IIII}JsonNodeFactory.instance.numberNode(Long.parseLong(text)));
{II}}} catch (NumberFormatException exception) {{
{III}// NOTE (mristin):
{III}// The numeral does not fit a long, so it stays a double -- which
{III}// is what a JSON parser would give for it as well.
{II}}}
{I}}}

{I}return Reporting.Result.success(
{II}JsonNodeFactory.instance.numberNode(value));
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of a {{@code <string>}} element.
 *
 * <p>{{@code xs:string}} is {{@code preserve}} and not {{@code collapse}}, so
 * a {{@code <string>}} keeps its whitespace, unlike a {{@code <boolean>}} or
 * a {{@code <double>}}.
 */
private static Reporting.Result<JsonNode> readXmlRpcString(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.success(
{III}JsonNodeFactory.instance.textNode(""));
{I}}}

{I}try {{
{II}return Reporting.Result.success(
{III}JsonNodeFactory.instance.textNode(XmlCommon.readContentAsString(reader)));
{I}}} catch (XMLStreamException exception) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}exception.getMessage()));
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the text of the element which the caller has opened, collapsed.
 *
 * <p>{{@code whiteSpace}} is fixed to {{@code collapse}} for every atomic XSD
 * type but a string, so a pretty-printed document has to be read as well.
 */
private static String readXmlRpcCollapsedText(XMLEventReader reader) {{
{I}try {{
{II}return XmlCommon.collapseWhitespace(XmlCommon.readContentAsString(reader));
{I}}} catch (XMLStreamException exception) {{
{II}return "";
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of an element holding a JSON-able array.
 *
 * <p>The content is a single {{@code <data>}} element holding a
 * {{@code <value>}} per item.
 */
public static Reporting.Result<ArrayNode> readArrayContent(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected a data element as the content of the element, " +
{III}"but the element was empty"));
{I}}}

{I}final Reporting.Result<? extends ArrayNode> result = XmlCommon.readNamedElementInNoNamespace(
{II}reader, "data", XmlRpc::readXmlRpcData);
{I}if (result.isError()) {{
{II}result.getError().prependSegment(new Reporting.NameSegment("data"));
{II}return Reporting.Result.failure(result.getError());
{I}}}
{I}return Reporting.Result.success(result.getResult());
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of the {{@code <data>}} element of a JSON-able array.
 */
private static Reporting.Result<ArrayNode> readXmlRpcData(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}final ArrayNode result = JsonNodeFactory.instance.arrayNode();
{I}if (isEmpty) {{
{II}return Reporting.Result.success(result);
{I}}}

{I}int index = 0;
{I}XmlCommon.skipWhitespaceAndComments(reader);
{I}while (XmlCommon.currentEvent(reader).isStartElement()) {{
{II}final Reporting.Result<? extends JsonNode> itemResult = XmlCommon.readNamedElementInNoNamespace(
{III}reader, "value", XmlRpc::readValueContent);
{II}if (itemResult.isError()) {{
{III}// NOTE (mristin):
{III}// Every item of a <data> element is a <value> element, so the index
{III}// already names the element which was entered, and there is no step
{III}// of its own for it.
{III}itemResult.getError().prependSegment(
{IIII}new Reporting.IndexSegment(index));
{III}return Reporting.Result.failure(itemResult.getError());
{II}}}

{II}result.add(itemResult.getResult());
{II}index++;
{II}XmlCommon.skipWhitespaceAndComments(reader);
{I}}}

{I}return Reporting.Result.success(result);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of an element holding a JSON-able object.
 *
 * <p>The content is a {{@code <member>}} per key, each holding a
 * {{@code <name>}} and a {{@code <value>}}.
 */
public static Reporting.Result<ObjectNode> readObjectContent(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}final ObjectNode result = JsonNodeFactory.instance.objectNode();
{I}if (isEmpty) {{
{II}return Reporting.Result.success(result);
{I}}}

{I}XmlCommon.skipWhitespaceAndComments(reader);
{I}while (XmlCommon.currentEvent(reader).isStartElement()) {{
{II}final Reporting.Result<? extends ObjectNode> memberResult =
{III}XmlCommon.readNamedElementInNoNamespace(
{IIII}reader, "member",
{IIII}(memberReader, memberIsEmpty) ->
{IIIII}readXmlRpcMember(memberReader, memberIsEmpty, result));
{II}if (memberResult.isError()) {{
{III}return Reporting.Result.failure(memberResult.getError());
{II}}}

{II}XmlCommon.skipWhitespaceAndComments(reader);
{I}}}

{I}return Reporting.Result.success(result);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read a {{@code <member>}} element into {{@code target}}.
 */
private static Reporting.Result<ObjectNode> readXmlRpcMember(
{I}XMLEventReader reader, boolean isEmpty, ObjectNode target) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected a name and a value element in a member, " +
{III}"but the member element was empty"));
{I}}}

{I}final Reporting.Result<? extends JsonNode> nameResult = XmlCommon.readNamedElementInNoNamespace(
{II}reader, "name", XmlRpc::readXmlRpcString);
{I}if (nameResult.isError()) {{
{II}return Reporting.Result.failure(nameResult.getError());
{I}}}
{I}final String key = nameResult.getResult().asText();

{I}// NOTE (mristin):
{I}// A repeated member name is refused, just as a repeated property element
{I}// is refused elsewhere in this module. Letting the later member win would
{I}// silently accept a document which says two different things about
{I}// the same key.
{I}if (target.has(key)) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"The member " + key + " occurred more than once"));
{I}}}

{I}final Reporting.Result<? extends JsonNode> valueResult = XmlCommon.readNamedElementInNoNamespace(
{II}reader, "value", XmlRpc::readValueContent);
{I}if (valueResult.isError()) {{
{II}// NOTE (mristin):
{II}// A <struct> holds the key of a member in a <name> child element
{II}// instead of an attribute, so the key segment renders as a predicate
{II}// on that child element, and the <value> element is a step of its own.
{II}valueResult.getError().prependSegment(
{III}new Reporting.NameSegment("value"));
{II}valueResult.getError().prependSegment(
{III}new Reporting.KeySegment(key));
{II}return Reporting.Result.failure(valueResult.getError());
{I}}}

{I}target.set(key, valueResult.getResult());
{I}return Reporting.Result.success(target);
}}"""
        ),
    ]


def _generate_writers() -> List[Stripped]:
    """
    Generate the writers of the XML-RPC subset.

    These mirror :py:func:`_generate_readers`.

    Every element written here resides in no namespace at all. Only
    the outermost one undeclares the default namespace of the enclosing
    document, though, and which one that is depends on the caller: a public
    entry point writes it, a nested one does not, so each of the three comes
    with a nested twin.
    """
    return [
        Stripped(
            f"""\
/**
 * Write {{@code that}} as the content of an element holding a JSON-able value.
 *
 * <p>The content is a single discriminator element which says what the value
 * is.
 */
public static void writeValueContent(
{I}JsonNode that, XMLStreamWriter writer) {{
{I}writeValueContent(that, writer, true);
}}

/**
 * Write {{@code that}} as the content of a {{@code <value>}} element of this
 * very module, which already resides in no namespace.
 */
private static void writeNestedValueContent(
{I}JsonNode that, XMLStreamWriter writer) {{
{I}writeValueContent(that, writer, false);
}}

private static void writeValueContent(
{I}JsonNode that, XMLStreamWriter writer, boolean undeclareNamespace) {{
{I}if (that == null || that.isNull() || that.isMissingNode()) {{
{II}throw new XmlCommon.SerializeFailure(new Reporting.Error(
{III}"Expected a JSON-able value, but got: " + that));
{I}}}

{I}if (that.isBoolean()) {{
{II}// NOTE (mristin):
{II}// Real XML-RPC tooling writes and expects a strict 1/0, and not
{II}// the true/false which xs:boolean and the rest of this module use.
{II}XmlCommon.writeElementInNoNamespace(
{III}"boolean", that.booleanValue() ? "1" : "0", writer, undeclareNamespace,
{III}XmlCommon::writeStringifiedContent);
{II}return;
{I}}}

{I}if (that.isNumber()) {{
{II}final double value = that.doubleValue();

{II}// NOTE (mristin):
{II}// JSON knows neither an infinity nor a not-a-number, so neither is
{II}// a JSON-able value, and readXmlRpcDouble refuses to read either back.
{II}if (Double.isInfinite(value) || Double.isNaN(value)) {{
{III}throw new XmlCommon.SerializeFailure(new Reporting.Error(
{IIII}"Expected a JSON-able value, but got the number " + value +
{IIII}", which is neither finite nor representable in JSON"));
{II}}}

{II}XmlCommon.writeElementInNoNamespace(
{III}"double", that, writer, undeclareNamespace,
{III}(node, aWriter) -> XmlCommon.writeStringifiedContent(
{IIII}node.asText(), aWriter));
{II}return;
{I}}}

{I}if (that.isTextual()) {{
{II}XmlCommon.writeElementInNoNamespace(
{III}"string", that.textValue(), writer, undeclareNamespace,
{III}XmlCommon::writeStringifiedContent);
{II}return;
{I}}}

{I}if (that.isArray()) {{
{II}XmlCommon.writeElementInNoNamespace(
{III}"array", (ArrayNode) that, writer, undeclareNamespace,
{III}XmlRpc::writeNestedArrayContent);
{II}return;
{I}}}

{I}if (that.isObject()) {{
{II}XmlCommon.writeElementInNoNamespace(
{III}"struct", (ObjectNode) that, writer, undeclareNamespace,
{III}XmlRpc::writeNestedObjectContent);
{II}return;
{I}}}

{I}throw new XmlCommon.SerializeFailure(new Reporting.Error(
{II}"Expected a JSON-able value (a boolean, a number, a string, " +
{II}"an array or an object), but got: " + that.getNodeType()));
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write {{@code that}} as the content of an element holding a JSON-able array.
 *
 * <p>The content is a single {{@code <data>}} element holding a
 * {{@code <value>}} per item.
 */
public static void writeArrayContent(
{I}ArrayNode that, XMLStreamWriter writer) {{
{I}writeArrayContent(that, writer, true);
}}

/**
 * Write {{@code that}} as the content of an {{@code <array>}} element of this
 * very module, which already resides in no namespace.
 */
private static void writeNestedArrayContent(
{I}ArrayNode that, XMLStreamWriter writer) {{
{I}writeArrayContent(that, writer, false);
}}

private static void writeArrayContent(
{I}ArrayNode that, XMLStreamWriter writer, boolean undeclareNamespace) {{
{I}XmlCommon.writeElementInNoNamespace(
{II}"data", that, writer, undeclareNamespace,
{II}(node, aWriter) -> {{
{III}int index = 0;
{III}for (JsonNode item : node) {{
{IIII}try {{
{IIIII}XmlCommon.writeElement(
{IIIIII}"value", item, aWriter,
{IIIIII}XmlRpc::writeNestedValueContent);
{IIII}}} catch (XmlCommon.SerializeFailure failure) {{
{IIIII}failure.getError().prependSegment(
{IIIIII}new Reporting.IndexSegment(index));
{IIIII}throw failure;
{IIII}}}
{IIII}index++;
{III}}}
{II}}});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write {{@code that}} as the content of an element holding a JSON-able
 * object.
 *
 * <p>The content is a {{@code <member>}} per key, each holding a
 * {{@code <name>}} and a {{@code <value>}}.
 */
public static void writeObjectContent(
{I}ObjectNode that, XMLStreamWriter writer) {{
{I}writeObjectContent(that, writer, true);
}}

/**
 * Write {{@code that}} as the content of a {{@code <struct>}} element of this
 * very module, which already resides in no namespace.
 */
private static void writeNestedObjectContent(
{I}ObjectNode that, XMLStreamWriter writer) {{
{I}writeObjectContent(that, writer, false);
}}

private static void writeObjectContent(
{I}ObjectNode that, XMLStreamWriter writer, boolean undeclareNamespace) {{
{I}final Iterator<String> names = that.fieldNames();
{I}while (names.hasNext()) {{
{II}final String key = names.next();
{II}// NOTE (mristin):
{II}// The members are siblings, so each of them is an outermost element
{II}// of its own where the enclosing element is not ours.
{II}XmlCommon.writeElementInNoNamespace(
{III}"member", that.get(key), writer, undeclareNamespace,
{III}(value, aWriter) -> {{
{IIII}XmlCommon.writeElement(
{IIIII}"name", key, aWriter,
{IIIII}XmlCommon::writeStringifiedContent);
{IIII}try {{
{IIIII}XmlCommon.writeElement(
{IIIIII}"value", value, aWriter,
{IIIIII}XmlRpc::writeNestedValueContent);
{IIII}}} catch (XmlCommon.SerializeFailure failure) {{
{IIIII}// NOTE (mristin):
{IIIII}// A member of an open JSON object is no property of one of
{IIIII}// our classes, so it gets a key segment and not a name one.
{IIIII}failure.getError().prependSegment(
{IIIIII}new Reporting.KeySegment(key));
{IIIII}throw failure;
{IIII}}}
{III}}});
{I}}}
}}"""
        ),
    ]


def generate(package: java_common.PackageIdentifier) -> List[java_common.JavaFile]:
    """
    Generate the code for de/serializing JSON-able values to and from XML.

    JSON prescribes no XML representation of its own, so a JSON-able value is
    de/serialized over the subset of XML-RPC which covers exactly what such
    a value can be: ``<boolean>``, ``<double>``, ``<string>``, ``<array>`` and
    ``<struct>``, with ``<data>``, ``<member>``, ``<name>`` and ``<value>``
    holding them together.

    The module knows nothing of the meta-model beyond the JSON-able values,
    and drives no document of its own: the caller passes the reader or
    the writer, so the xmlization reads a JSON-able property from the very
    same reader it reads the enclosing document with, one element at a time.

    The low-level reading -- the skipping of what carries no information,
    the check of the XML namespace and the consuming of a start and of an end
    tag -- is not repeated here, but taken from ``XmlCommon``, which
    the xmlization reads the enclosing document with as well.

    These elements reside in no namespace at all, as the XML-RPC specification
    prescribes, and not in the namespace of the enclosing document, so
    the primitives of ``XmlCommon`` are called in their ``...InNoNamespace``
    flavor throughout.

    The ``package`` defines the base Java package of the generated code.
    """
    blocks = []  # type: List[Stripped]

    blocks.extend(_generate_readers())
    blocks.extend(_generate_writers())

    body = "\n\n".join(blocks)

    class_block = Stripped(
        f"""\
/**
 * De/serialize JSON-able values to and from XML.
 *
 * <p>JSON prescribes no XML representation of its own, so a JSON-able value
 * is de/serialized over the subset of XML-RPC which covers exactly what such
 * a value can be: {{@code <boolean>}}, {{@code <double>}}, {{@code <string>}},
 * {{@code <array>}} and {{@code <struct>}}.
 *
 * <p>Every method reads from or writes to the reader or the writer which
 * the caller passes in, and consumes or produces exactly the content of one
 * element. This is what lets the xmlization read a JSON-able property from
 * the very same reader it reads the enclosing document with.
 */
public final class XmlRpc {{
{I}private XmlRpc() {{
{II}// NOTE (mristin):
{II}// The XML-RPC de/serialization is stateless, so there is nothing
{II}// to instantiate.
{I}}}

{I}{indent_but_first_line(body, I)}
}}"""
    )

    imports = [
        Stripped("import javax.xml.stream.events.XMLEvent;"),
        Stripped("import javax.xml.stream.XMLEventReader;"),
        Stripped("import javax.xml.stream.XMLStreamConstants;"),
        Stripped("import javax.xml.stream.XMLStreamException;"),
        Stripped("import javax.xml.stream.XMLStreamWriter;"),
        Stripped("import java.util.Iterator;"),
        Stripped("import java.util.regex.Pattern;"),
        *(
            Stripped(f"import {json_import};")
            for json_import in java_common.JSON_IMPORTS
        ),
        Stripped("import com.fasterxml.jackson.databind.node.JsonNodeFactory;"),
        Stripped(f"import {package}.reporting.Reporting;"),
        Stripped(f"import {package}.xmlcommon.XmlCommon;"),
    ]  # type: List[Stripped]

    file_blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.xmlrpc;"),
        Stripped("\n".join(imports)),
        class_block,
        java_common.WARNING,
    ]

    code = "\n\n".join(file_blocks)

    return [java_common.JavaFile("XmlRpc.java", f"{code}\n")]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
