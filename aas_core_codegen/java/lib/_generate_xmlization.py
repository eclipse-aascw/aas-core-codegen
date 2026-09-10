"""Generate the code for XML de/serialization."""

import io
import textwrap

from typing import Tuple, Optional, List

from icontract import ensure, require

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    assert_never,
    Error,
    Identifier,
    indent_but_first_line,
    Stripped,
)
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)

# region Generate


def _generate_current_event() -> Stripped:
    """Generate the function to a single XML event."""

    return Stripped(
        f"""\
private static XMLEvent currentEvent(XMLEventReader reader) {{
{I}try {{
{II}return reader.peek();
{I}}} catch (XMLStreamException xmlStreamException) {{
{II}throw new Xmlization.DeserializeException("",
{III}"Failed in method peek because of: " +
{III}xmlStreamException.getMessage());
{I}}}
}}"""
    )


def _generate_try_content_for_primitives() -> Stripped:
    """Generate the function to read textual content."""

    return Stripped(
        f"""\
private static String readContentAsString(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}return content.toString();
}}

private static Boolean readContentAsBool(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}
{I}if(!("true".equals(content.toString()) || "false".equals(content.toString()))){{
{II}throw new IllegalStateException("Content cannot be converted to the type Boolean.");
{I}}}
{I}return Boolean.valueOf(content.toString());
}}

private static Long readContentAsLong(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}return Long.valueOf(content.toString());
}}

private static Double readContentAsDouble(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}return Double.valueOf(content.toString());
}}

/**
 * Read the whole content of an element into memory.
 */
private static byte[] readContentAsBase64(
{I}XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();
{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}String encodedData = content.toString();
{I}final byte[] decodedData;
{I}Base64.Decoder decoder = Base64.getDecoder();

{I}try {{
{II}decodedData = decoder.decode(encodedData);
{I}}} catch (IllegalArgumentException exception) {{
{II}throw new XMLStreamException(
{III}"Failed to read base64 encoded data: " +
{III}exception.getMessage());
{I}}}

{I}return decodedData;
}}"""
    )


def _generate_try_named_start_element() -> Stripped:
    """
    Generate the function to consume a starting element of an expected name.

    The expected local name is passed in as an argument, since it is used both
    for the items of a list (always wrapped in a repeated ``<v>``) and for the
    items of a tuple (each wrapped in its own ``<v1>``, ``<v2>`` *etc.*,
    one-based, matching the position of the item in the tuple).
    """
    return Stripped(
        f"""\
/**
 * Consume a starting element of the {{@code expectedName}} from the reader
 * and return whether it was a self-closing (empty) element.
 */
private static Reporting.Result<Boolean> tryNamedStartElement(
{I}XMLEventReader reader, String expectedName) {{
{I}if (currentEvent(reader).isEndDocument()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a <" + expectedName + "> element, but got an end-of-file.");
{II}return Reporting.Result.failure(error);
{I}}}

{I}if (!currentEvent(reader).isStartElement()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a <" + expectedName + "> start element, but got the node "
{IIII}+ "of type " + getEventTypeAsString(currentEvent(reader)));
{II}return Reporting.Result.failure(error);
{I}}}

{I}final Reporting.Result<String> tryElementName = tryElementName(reader);
{I}if (tryElementName.isError()) {{
{II}return tryElementName.castTo(Boolean.class);
{I}}}

{I}if (!expectedName.equals(tryElementName.getResult())) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a <" + expectedName + "> element, but got an element "
{IIII}+ tryElementName.getResult());
{II}return Reporting.Result.failure(error);
{I}}}

{I}final boolean isEmpty = isEmptyElement(reader);
{I}return Reporting.Result.success(isEmpty);
}}"""
    )


def _generate_try_named_end_element() -> Stripped:
    """Generate the function to consume a closing element of an expected name."""
    return Stripped(
        f"""\
/**
 * Consume a closing element of the {{@code expectedName}} from the reader.
 */
private static Reporting.Result<XMLEvent> tryNamedEndElement(
{I}XMLEventReader reader, String expectedName) {{
{I}skipWhitespaceAndComments(reader);

{I}if (currentEvent(reader).isEndDocument()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a closing element for " + expectedName + ", "
{IIII}+ "but got an end-of-file.");
{II}return Reporting.Result.failure(error);
{I}}}

{I}if (!currentEvent(reader).isEndElement()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a closing element for " + expectedName + ", "
{IIII}+ "but got the node of type " + getEventTypeAsString(currentEvent(reader)));
{II}return Reporting.Result.failure(error);
{I}}}

{I}final Reporting.Result<String> tryElementName = tryElementName(reader);
{I}if (tryElementName.isError()) {{
{II}return tryElementName.castTo(XMLEvent.class);
{I}}}

{I}if (!expectedName.equals(tryElementName.getResult())) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a closing element for " + expectedName + ", "
{IIII}+ "but got an end element " + tryElementName.getResult());
{II}return Reporting.Result.failure(error);
{I}}}

{I}try {{
{II}return Reporting.Result.success(reader.nextEvent());
{I}}} catch (XMLStreamException xmlStreamException) {{
{II}throw new Xmlization.DeserializeException("",
{III}"Failed in method tryNamedEndElement because of: " +
{IIII}xmlStreamException.getMessage());
{I}}}
}}"""
    )


def _generate_try_named_element_as_primitive_functions() -> List[Stripped]:
    """
    Generate the functions to read a named element as a primitive value.

    These are shared between the items of a list (wrapped in a repeated
    ``<v>``) and the items of a tuple (each wrapped in its own ``<v1>``,
    ``<v2>`` *etc.*).
    """
    result = []  # type: List[Stripped]

    for function_name, result_type, deserialization_expr in (
        ("tryNamedElementAsBoolean", "Boolean", "readContentAsBool(reader)"),
        ("tryNamedElementAsLong", "Long", "readContentAsLong(reader)"),
        ("tryNamedElementAsDouble", "Double", "readContentAsDouble(reader)"),
    ):
        result.append(
            Stripped(
                f"""\
/**
 * Read the content of a named element and parse it as {result_type}.
 */
private static Reporting.Result<{result_type}> {function_name}(
{I}XMLEventReader reader, String expectedName) {{
{I}final Reporting.Result<Boolean> tryStart = tryNamedStartElement(reader, expectedName);
{I}if (tryStart.isError()) {{
{II}return tryStart.castTo({result_type}.class);
{I}}}

{I}if (tryStart.getResult()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected an XML content representing {result_type}, " +
{III}"but got a self-closing <" + expectedName + " /> element");
{II}return Reporting.Result.failure(error);
{I}}}

{I}final {result_type} result;
{I}try {{
{II}result = {deserialization_expr};
{I}}} catch (Exception exception) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"The content of a <" + expectedName + "> element could not be "
{IIII}+ "de-serialized as {result_type}: " + exception.getMessage());
{II}return Reporting.Result.failure(error);
{I}}}

{I}final Reporting.Result<XMLEvent> tryEnd = tryNamedEndElement(reader, expectedName);
{I}if (tryEnd.isError()) {{
{II}return tryEnd.castTo({result_type}.class);
{I}}}

{I}return Reporting.Result.success(result);
}}"""
            )
        )

    # A self-closing named element represents an empty string.
    result.append(
        Stripped(
            f"""\
/**
 * Read the content of a named element and parse it as a string.
 */
private static Reporting.Result<String> tryNamedElementAsString(
{I}XMLEventReader reader, String expectedName) {{
{I}final Reporting.Result<Boolean> tryStart = tryNamedStartElement(reader, expectedName);
{I}if (tryStart.isError()) {{
{II}return tryStart.castTo(String.class);
{I}}}

{I}final String result;
{I}if (tryStart.getResult()) {{
{II}result = "";
{I}}} else {{
{II}try {{
{III}result = readContentAsString(reader);
{II}}} catch (Exception exception) {{
{III}final Reporting.Error error = new Reporting.Error(
{IIII}"The content of a <" + expectedName + "> element could not be "
{IIIII}+ "de-serialized as String: " + exception.getMessage());
{III}return Reporting.Result.failure(error);
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// A self-closing named element is represented as a pair of start and end
{I}// events in StAX, so we need to consume the end element even if the
{I}// element was empty.
{I}final Reporting.Result<XMLEvent> tryEnd = tryNamedEndElement(reader, expectedName);
{I}if (tryEnd.isError()) {{
{II}return tryEnd.castTo(String.class);
{I}}}

{I}return Reporting.Result.success(result);
}}"""
        )
    )

    # A self-closing named element represents empty bytes.
    result.append(
        Stripped(
            f"""\
/**
 * Read a named element as base64-encoded bytes.
 */
private static Reporting.Result<byte[]> tryNamedElementAsBytes(
{I}XMLEventReader reader, String expectedName) {{
{I}final Reporting.Result<Boolean> tryStart = tryNamedStartElement(reader, expectedName);
{I}if (tryStart.isError()) {{
{II}return tryStart.castTo(byte[].class);
{I}}}

{I}final byte[] result;
{I}if (tryStart.getResult()) {{
{II}result = new byte[0];
{I}}} else {{
{II}try {{
{III}result = readContentAsBase64(reader);
{II}}} catch (Exception exception) {{
{III}final Reporting.Error error = new Reporting.Error(
{IIII}"The content of a <" + expectedName + "> element could not be "
{IIIII}+ "de-serialized as base64-encoded bytes: " + exception.getMessage());
{III}return Reporting.Result.failure(error);
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// A self-closing named element is represented as a pair of start and end
{I}// events in StAX, so we need to consume the end element even if the
{I}// element was empty.
{I}final Reporting.Result<XMLEvent> tryEnd = tryNamedEndElement(reader, expectedName);
{I}if (tryEnd.isError()) {{
{II}return tryEnd.castTo(byte[].class);
{I}}}

{I}return Reporting.Result.success(result);
}}"""
        )
    )

    return result


def _generate_try_named_element_as_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """
    Generate the function to de-serialize a literal of ``enumeration`` from
    a named element.

    This is shared between the items of a list (always read from a repeated
    ``<v>``) and the items of a tuple (each read from its own ``<v1>``,
    ``<v2>`` *etc.*).
    """
    enum_name = java_naming.enum_name(enumeration.name)
    from_str_name = java_naming.private_property_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    return Stripped(
        f"""\
/**
 * Read a named element and parse its content as a literal
 * of {{@link {enum_name}}}.
 */
private static Reporting.Result<{enum_name}> tryNamedElementAs{enum_name}(
{I}XMLEventReader reader, String expectedName) {{
{I}final Reporting.Result<String> tryText = tryNamedElementAsString(reader, expectedName);
{I}if (tryText.isError()) {{
{II}return tryText.castTo({enum_name}.class);
{I}}}

{I}final Optional<{enum_name}> result = Stringification.{from_str_name}(
{II}tryText.getResult());

{I}if (!result.isPresent()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"The text could not be parsed as a literal of {enum_name}: " +
{III}tryText.getResult());
{II}return Reporting.Result.failure(error);
{I}}}

{I}return Reporting.Result.success(result.get());
}}"""
    )


def _generate_parse_list() -> Stripped:
    """Generate the generic function to de-serialize a list of items."""
    return Stripped(
        f"""\
/**
 * Parse a list of items, each de-serialized by {{@code parseItem}}.
 *
 * <p>Every start element is considered to mark the start of an item. Parsing
 * stops as soon as a non-start element is encountered.
 */
private static <T> Reporting.Result<List<T>> parseList(
{I}XMLEventReader reader,
{I}boolean isEmptyProperty,
{I}Class<T> itemType,
{I}Function<XMLEventReader, Reporting.Result<? extends T>> parseItem) {{
{I}final List<T> result = new ArrayList<>();
{I}if (isEmptyProperty) {{
{II}return Reporting.Result.success(result);
{I}}}

{I}skipWhitespaceAndComments(reader);
{I}int index = 0;
{I}if (!currentEvent(reader).isStartElement()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a start element opening an instance of " + itemType.getSimpleName() +
{IIII}", but got an XML " + getEventTypeAsString(currentEvent(reader)));
{II}error.prependSegment(new Reporting.IndexSegment(index));
{II}return Reporting.Result.failure(error);
{I}}}

{I}while (currentEvent(reader).isStartElement()) {{
{II}final Reporting.Result<? extends T> itemResult = parseItem.apply(reader);
{II}if (itemResult.isError()) {{
{III}itemResult.getError()
{IIII}.prependSegment(
{IIIII}new Reporting.IndexSegment(index));
{III}return Reporting.Result.failure(itemResult.getError());
{II}}}

{II}result.add(itemResult.getResult());
{II}index++;
{II}skipWhitespaceAndComments(reader);
{I}}}

{I}return Reporting.Result.success(result);
}}"""
    )


def _generate_skip_whitespace_and_comments() -> Stripped:
    """Generate the function to skip whitespace text and XML comments."""
    return Stripped(
        f"""\
private static void skipWhitespaceAndComments(XMLEventReader reader) {{
{I}while (whiteSpaceOrComment(reader)) {{
{II}reader.next();
{I}}}
}}

private static boolean whiteSpaceOrComment(XMLEventReader reader) {{
{I}final XMLEvent currentEvent = currentEvent(reader);
{I}final boolean isComment = (currentEvent != null &&
{II}currentEvent.getEventType() == XMLStreamConstants.COMMENT);
{I}final boolean isWhiteSpace = (currentEvent != null &&
{II}currentEvent.getEventType() == XMLStreamConstants.CHARACTERS &&
{II}currentEvent.asCharacters().isWhiteSpace());
{I}return isComment || isWhiteSpace;
}}"""
    )


def _generate_skip_start_document() -> Stripped:
    """Generate the function to skip start document."""
    return Stripped(
        f"""\
private static void skipStartDocument(XMLEventReader reader){{
{I}if (currentEvent(reader).isStartDocument()){{
{II}reader.next();
{I}}}
}}"""
    )


def _generate_is_empty_element() -> Stripped:
    """Generate the function to check if an element is empty."""
    return Stripped(
        f"""\
private static boolean isEmptyElement(XMLEventReader reader) {{
{I}// Skip the element node and go to the content
{I}try {{
{II}reader.nextEvent();
{I}}} catch (XMLStreamException xmlStreamException) {{
{II}throw new Xmlization.DeserializeException("",
{III}"Failed in method isEmptyElement because of: " +
{III}xmlStreamException.getMessage());
{I}}}
{I}return currentEvent(reader).isEndElement();
}}"""
    )


def _generate_deserialize_primitive_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` of primitive type."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    a_type = intermediate.try_primitive_type(type_anno)
    assert a_type is not None, f"Unexpected type annotation: {prop.type_annotation}"

    deserialization_expr: str
    if a_type is intermediate.PrimitiveType.BOOL:
        deserialization_expr = "readContentAsBool(reader)"
    elif a_type is intermediate.PrimitiveType.INT:
        deserialization_expr = "readContentAsLong(reader)"
    elif a_type is intermediate.PrimitiveType.FLOAT:
        deserialization_expr = "readContentAsDouble(reader)"
    elif a_type is intermediate.PrimitiveType.STR:
        deserialization_expr = "readContentAsString(reader)"
    elif a_type is intermediate.PrimitiveType.BYTEARRAY:
        deserialization_expr = "readContentAsBase64(reader)"
    else:
        assert_never(a_type)

    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

    prop_name = java_naming.property_name(prop.name)
    cls_name = java_naming.class_name(cls.name)
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    if a_type is intermediate.PrimitiveType.STR:
        empty_handling_body = Stripped(f'{target_var} = "";')
    else:
        empty_handling_body = Stripped(
            f"""\
final Reporting.Error error = new Reporting.Error(
{I}"The property {prop_name} of an instance of class {cls_name} " +
{I}"can not be de-serialized from a self-closing element " +
{I}"since it needs content");
error.prependSegment(
{I}new Reporting.NameSegment(
{II}{xml_prop_name_literal}));
return Reporting.Result.failure(error);"""
        )

    return Stripped(
        f"""\
if (isEmptyProperty) {{
{I}{indent_but_first_line(empty_handling_body, I)}
}}
else {{
{I}if (currentEvent(reader).isEndDocument()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected an XML content representing " +
{III}"the property {prop_name} of an instance of class {cls_name}, " +
{III}"but reached the end-of-file");
{II}return Reporting.Result.failure(error);
{I}}}

{I}try {{
{II}{target_var} = {deserialization_expr};
{I}}} catch (Exception e) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"The property {prop_name} of an instance of class {cls_name} "
{IIII}+ " could not be de-serialized: " + e.getMessage());
{II}error.prependSegment(
{III}new Reporting.NameSegment(
{IIII}"{prop_name}"));
{II}return Reporting.Result.failure(error);
{I}}}
}}"""
    )


def _generate_get_event_type_as_string() -> Stripped:
    """Generate the function to map XML event types to their string representations."""

    return Stripped(
        f"""\
private static String getEventTypeAsString(XMLEvent event) {{
{I}switch (event.getEventType()) {{
{II}case XMLStreamConstants.START_ELEMENT:
{III}return "Start-Element";
{II}case XMLStreamConstants.END_ELEMENT:
{III}return "End-Element";
{II}case XMLStreamConstants.PROCESSING_INSTRUCTION:
{III}return "Processing-Instruction";
{II}case XMLStreamConstants.CHARACTERS:
{III}return "Characters";
{II}case XMLStreamConstants.COMMENT:
{III}return "Comment";
{II}case XMLStreamConstants.SPACE:
{III}return "Space";
{II}case XMLStreamConstants.START_DOCUMENT:
{III}return "Start-Document";
{II}case XMLStreamConstants.END_DOCUMENT:
{III}return "End-Document";
{II}case XMLStreamConstants.ENTITY_REFERENCE:
{III}return "Entity-Reference";
{II}case XMLStreamConstants.ATTRIBUTE:
{III}return "Attribute";
{II}case XMLStreamConstants.NOTATION_DECLARATION:
{III}return "Notation-Declaration";
{II}default:
{III}return "Unknown-Type";
{I}}}
}}"""
    )


def _generate_try_element_name() -> Stripped:
    """Generate the function to strip the prefix and check the namespace."""
    return Stripped(
        f"""\
private static boolean invalidNameSpace(XMLEvent event) {{
{I}if (event.isStartElement()) {{
{II}return !AAS_NAME_SPACE.equals(event.asStartElement().getName().getNamespaceURI());
{I}}} else {{
{II}return !AAS_NAME_SPACE.equals(event.asEndElement().getName().getNamespaceURI());
{I}}}
}}

/**
 * Check the namespace and extract the element's name.
 */
private static Reporting.Result<String> tryElementName(XMLEventReader reader) {{
{I}final XMLEvent currentEvent = currentEvent(reader);
{I}final boolean precondition = currentEvent.isStartElement() || currentEvent.isEndElement();
{I}if (!precondition) {{
{II}throw new IllegalStateException("Expected to be at a start or an end element "
{IIII}+ "but got: " + getEventTypeAsString(currentEvent));
{I}}}

{I}if (invalidNameSpace(currentEvent)) {{
{II}String namespace = currentEvent.isStartElement()
{IIII}? currentEvent.asStartElement().getName().getNamespaceURI()
{IIII}: currentEvent.asEndElement().getName().getNamespaceURI();
{II}final Reporting.Error error = new Reporting.Error(
{IIII}"Expected an element within a namespace " +
{IIII}AAS_NAME_SPACE + ", " + "but got: " + namespace);
{II}return Reporting.Result.failure(error);
{I}}}
{I}return Reporting.Result.success(currentEvent.isStartElement()
{III}? currentEvent.asStartElement().getName().getLocalPart()
{III}: currentEvent.asEndElement().getName().getLocalPart());
}}"""
    )


def _generate_verify_closing_tag_for_class() -> Stripped:
    return Stripped(
        f"""\
private static Reporting.Result<XMLEvent> verifyClosingTagForClass(
{I}String className,
{I}XMLEventReader reader,
{I}Reporting.Result<String> tryElementName) {{
{I}final XMLEvent currentEvent = currentEvent(reader);
{I}if (currentEvent.isEndDocument()) {{
{II}final Reporting.Error error = new Reporting.Error(
{IIII}"Expected an XML end element to conclude a property of class " + className
{IIIIII}+ " with the element name " + tryElementName.getResult() + ", "
{IIIIII}+ "but got the end-of-file.");
{II}return Reporting.Result.failure(error);
{I}}}

{I}if (!currentEvent.isEndElement()) {{
{II}final Reporting.Error error = new Reporting.Error(
{IIII}"Expected an XML end element to conclude a property of class " + className
{IIIIII}+ " with the element name " + tryElementName.getResult() + ", "
{IIIIII}+ "but got the node of type " + getEventTypeAsString(currentEvent)
{IIIIII}+ " with the value " + currentEvent);
{II}return Reporting.Result.failure(error);
{I}}}
{I}final Reporting.Result<String> tryEndElementName = tryElementName(reader);
{I}if (tryEndElementName.isError()) {{
{II}return tryEndElementName.castTo(XMLEvent.class);
{I}}}
{I}if (!tryElementName.getResult().equals(tryEndElementName.getResult())) {{
{II}final Reporting.Error error = new Reporting.Error(
{IIII}"Expected an XML end element to conclude a property of class " + className
{IIIIII}+ " with the element name " + tryElementName.getResult() + ", "
{IIIIII}+ "but got the end element with the name " + tryEndElementName.getResult());
{II}return Reporting.Result.failure(error);
{I}}}
{I}try {{
{II}return Reporting.Result.success(reader.nextEvent());
{I}}} catch (XMLStreamException xmlStreamException) {{
{II}throw new Xmlization.DeserializeException("",
{III}"Failed in method verifyClosingTagForClass because of: " +
{III}xmlStreamException.getMessage());
{I}}}
}}"""
    )


def _generate_parse_instance_from_element_generic() -> Stripped:
    """Generate the generic function to de-serialize an instance from an element."""
    return Stripped(
        f"""\
/**
 * Deserialize an instance of {{@code T}} from an XML element.
 *
 * <p>{{@code parseAsSequence}} is given the element's local name and whether
 * the element is self-closing, and is expected to consume the properties of
 * the instance, but not the element's closing tag.
 */
private static <T> Reporting.Result<? extends T> parseInstanceFromElement(
{I}XMLEventReader reader,
{I}Class<T> type,
{I}BiFunction<String, Boolean, Reporting.Result<? extends T>> parseAsSequence) {{
{I}skipWhitespaceAndComments(reader);

{I}final XMLEvent currentEvent = currentEvent(reader);
{I}if (currentEvent.getEventType() == XMLStreamConstants.END_DOCUMENT) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML element representing an instance of " + type.getSimpleName() + ", " +
{IIII}"but reached the end-of-file"));
{I}}}

{I}if (currentEvent.getEventType() != XMLStreamConstants.START_ELEMENT) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML element representing an instance of " + type.getSimpleName() + ", " +
{IIII}"but got a node of type " + getEventTypeAsString(currentEvent) +
{IIII}" with value " + currentEvent));
{I}}}

{I}final Reporting.Result<String> tryElementName = tryElementName(reader);
{I}if (tryElementName.isError()) {{
{II}return Reporting.Result.failure(tryElementName.getError());
{I}}}

{I}final String elementName = tryElementName.getResult();
{I}final boolean isEmptyElement = isEmptyElement(reader);

{I}final Reporting.Result<? extends T> result = parseAsSequence.apply(elementName, isEmptyElement);
{I}if (result.isError()) {{
{II}return result;
{I}}}

{I}final Reporting.Result<XMLEvent> checkEndElement = verifyClosingTagForClass(
{II}type.getSimpleName(),
{II}reader,
{II}tryElementName);
{I}if (checkEndElement.isError()) {{
{II}return Reporting.Result.failure(checkEndElement.getError());
{I}}}

{I}return result;
}}"""
    )


def _generate_deserialize_enumeration_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` as an enum."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.OurTypeAnnotation)

    our_type = type_anno.our_type
    assert isinstance(our_type, intermediate.Enumeration)

    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))
    text_target_var = java_naming.variable_name(Identifier(f"text_{prop.name}"))
    optional_target_var = java_naming.variable_name(Identifier(f"optional_{prop.name}"))
    cls_name = java_naming.class_name(cls.name)
    prop_name = java_naming.property_name(prop.name)
    prop_type_name = java_naming.enum_name(our_type.name)
    from_str_name = java_naming.private_property_name(
        Identifier(f"{our_type.name}_from_string")
    )
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    return Stripped(
        f"""\
if (isEmptyProperty) {{
{I}final Reporting.Error error = new Reporting.Error(
{II}"The property {prop_name} of an instance of class {cls_name} " +
{II}"can not be de-serialized from a self-closing element " +
{II}"since it needs content");
{I}error.prependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return Reporting.Result.failure(error);
}}

if (currentEvent(reader).isEndDocument()) {{
{I}final Reporting.Error error = new Reporting.Error(
{III}"Expected an XML content representing "
{IIIII}+ "the property {prop_name} of an instance of class {cls_name}, "
{IIIII}+ "but reached the end-of-file");
{I}return Reporting.Result.failure(error);
}}

String {text_target_var};
try {{
{I}{text_target_var} = readContentAsString(reader);
}} catch (Exception e) {{
{I}final Reporting.Error error = new Reporting.Error(
{III}"The property {prop_name} of an instance of class {cls_name}"
{IIIII}+ " could not be de-serialized: " + e.getMessage());
{I}error.prependSegment(
{III}new Reporting.NameSegment(
{IIIII}"{prop_name}"));
{I}return Reporting.Result.failure(error);
}}

final Optional<{prop_type_name}> {optional_target_var} =
{I}Stringification.{from_str_name}(
{II}{text_target_var});

if ({optional_target_var}.isPresent()) {{
{I}{target_var} = {optional_target_var}.get();
}} else {{
{I}final Reporting.Error error = new Reporting.Error(
{III}"The property {prop_name} of an instance of class {cls_name}" +
{IIIII}" could not be de-serialized from an unexpected enumeration literal: " +
{IIIII}{text_target_var});
{I}error.prependSegment(
{III}new Reporting.NameSegment(
{IIIII}"{prop_name}"));
{I}return Reporting.Result.failure(error);
}}"""
    )


def _generate_deserialize_interface_property(
    prop: intermediate.Property,
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` as an interface."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.OurTypeAnnotation)

    our_type = type_anno.our_type
    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    )
    assert our_type.interface is not None

    prop_name = java_naming.property_name(prop.name)
    cls_name = java_naming.class_name(cls.name)

    interface_name = java_naming.interface_name(our_type.interface.name)

    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))
    try_target_var = java_naming.variable_name(Identifier(f"try_{prop.name}"))
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    return Stripped(
        f"""\
if (isEmptyProperty) {{
{I}final Reporting.Error error = new Reporting.Error(
{II}"Expected an XML element within the element " + tryElementName.getResult() + " representing " +
{II}"the property {prop_name} of an instance of class {cls_name}, " +
{II}"but encountered a self-closing element.");
{I}return Reporting.Result.failure(error);
}}

// We need to skip the whitespace here in order to be able to look ahead
// the discriminator element shortly.
skipWhitespaceAndComments(reader);

if (currentEvent(reader).isEndDocument()) {{
{I}final Reporting.Error error = new Reporting.Error(
{II}"Expected an XML element within the element " + tryElementName.getResult() + " representing " +
{II}"the property {prop_name} of an instance of class {cls_name}, " +
{II}"but reached the end-of-file");
{I}return Reporting.Result.failure(error);
}}

// Try to look ahead the discriminator name;
// we need this name only for the error reporting below.
// {interface_name}FromElement will perform more sophisticated
// checks.
String discriminatorElementName = null;
if (currentEvent(reader).isStartElement()) {{
{I}Reporting.Result<String> tryDiscriminatorElementName = tryElementName(reader);
{I}assert(!tryDiscriminatorElementName.isError());
{I}discriminatorElementName = tryDiscriminatorElementName.getResult();
}}

Reporting.Result<? extends {interface_name}> {try_target_var} = try{interface_name}FromElement(reader);

if ({try_target_var}.isError()) {{
{I}if (discriminatorElementName != null) {{
{II}{try_target_var}.getError().
{III}prependSegment(
{IIII}new Reporting.NameSegment(
{IIIII}discriminatorElementName));
{I}}}

{I}{try_target_var}.getError()
{II}.prependSegment(
{III}new Reporting.NameSegment(
{IIII}{xml_prop_name_literal}));
{I}return {try_target_var}.castTo({cls_name}.class);
}}

{target_var} = {try_target_var}.getResult();"""
    )


def _generate_deserialize_named_union_property(
    prop: intermediate.Property,
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` as a named union."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.OurTypeAnnotation)

    our_type = type_anno.our_type
    assert isinstance(our_type, intermediate.NamedUnion)

    prop_name = java_naming.property_name(prop.name)
    cls_name = java_naming.class_name(cls.name)

    union_name = java_naming.union_name(our_type.name)

    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))
    try_target_var = java_naming.variable_name(Identifier(f"try_{prop.name}"))
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    return Stripped(
        f"""\
if (isEmptyProperty) {{
{I}final Reporting.Error error = new Reporting.Error(
{II}"Expected an XML element within the element " + tryElementName.getResult() + " representing " +
{II}"the property {prop_name} of an instance of class {cls_name}, " +
{II}"but encountered a self-closing element.");
{I}return Reporting.Result.failure(error);
}}

// We need to skip the whitespace here in order to be able to look ahead
// the discriminator element shortly.
skipWhitespaceAndComments(reader);

if (currentEvent(reader).isEndDocument()) {{
{I}final Reporting.Error error = new Reporting.Error(
{II}"Expected an XML element within the element " + tryElementName.getResult() + " representing " +
{II}"the property {prop_name} of an instance of class {cls_name}, " +
{II}"but reached the end-of-file");
{I}return Reporting.Result.failure(error);
}}

// Try to look ahead the discriminator name;
// we need this name only for the error reporting below.
// {union_name}FromElement will perform more sophisticated
// checks.
String discriminatorElementName = null;
if (currentEvent(reader).isStartElement()) {{
{I}Reporting.Result<String> tryDiscriminatorElementName = tryElementName(reader);
{I}assert(!tryDiscriminatorElementName.isError());
{I}discriminatorElementName = tryDiscriminatorElementName.getResult();
}}

Reporting.Result<? extends {union_name}> {try_target_var} = try{union_name}FromElement(reader);

if ({try_target_var}.isError()) {{
{I}if (discriminatorElementName != null) {{
{II}{try_target_var}.getError().
{III}prependSegment(
{IIII}new Reporting.NameSegment(
{IIIII}discriminatorElementName));
{I}}}

{I}{try_target_var}.getError()
{II}.prependSegment(
{III}new Reporting.NameSegment(
{IIII}{xml_prop_name_literal}));
{I}return {try_target_var}.castTo({cls_name}.class);
}}

{target_var} = {try_target_var}.getResult();"""
    )


def _generate_deserialize_cls_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` as a concrete class."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.OurTypeAnnotation)

    our_type = type_anno.our_type
    assert isinstance(our_type, intermediate.ConcreteClass)

    target_cls_name = java_naming.class_name(our_type.name)

    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

    try_target_var = java_naming.variable_name(Identifier(f"try_{prop.name}"))

    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    cls_name = java_naming.class_name(cls.name)

    return Stripped(
        f"""\
Reporting.Result<{target_cls_name}> {try_target_var} = try{target_cls_name}FromSequence(
{I}reader, isEmptyProperty);

if ({try_target_var}.isError()) {{
{I}{try_target_var}.getError()
{II}.prependSegment(
{III}new Reporting.NameSegment(
{IIII}{xml_prop_name_literal}));
{I}return {try_target_var}.castTo({cls_name}.class);
}}

{target_var} = {try_target_var}.getResult();"""
    )


def _xml_deserialize_atomic_item_is_scalar(
    item_type_anno: intermediate.TypeAnnotationUnion,
) -> bool:
    """Determine whether the atomic item is read from a named element."""
    primitive_type = intermediate.try_primitive_type(item_type_anno)

    return primitive_type is not None or (
        isinstance(item_type_anno, intermediate.OurTypeAnnotation)
        and isinstance(item_type_anno.our_type, intermediate.Enumeration)
    )


def _xml_deserialize_atomic_item_method_name(
    item_type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """
    Determine the bare (unqualified) method name for de-serializing a single
    atomic item.

    The item is expected to be atomic: a primitive, a constrained primitive,
    an enumeration literal or a class (dispatched through the interface, if
    the class has concrete descendants). A primitive or an enumeration
    literal is read by a method taking ``(XMLEventReader, String)`` -- the
    element name is a separate positional argument, unlike a class item's
    method, which takes only the ``XMLEventReader`` and dispatches through
    the item's own natural element tag.

    See :py:func:`_xml_deserialize_atomic_item_call` for the call-expression
    counterpart built on top of this, and
    :py:func:`_xml_deserialize_atomic_item_is_scalar` for distinguishing the
    two argument shapes.
    """
    if _xml_deserialize_atomic_item_is_scalar(item_type_anno):
        primitive_type = intermediate.try_primitive_type(item_type_anno)

        if primitive_type is not None:
            if primitive_type is intermediate.PrimitiveType.BOOL:
                return Stripped("tryNamedElementAsBoolean")
            elif primitive_type is intermediate.PrimitiveType.INT:
                return Stripped("tryNamedElementAsLong")
            elif primitive_type is intermediate.PrimitiveType.FLOAT:
                return Stripped("tryNamedElementAsDouble")
            elif primitive_type is intermediate.PrimitiveType.STR:
                return Stripped("tryNamedElementAsString")
            elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                return Stripped("tryNamedElementAsBytes")
            else:
                assert_never(primitive_type)

        assert isinstance(
            item_type_anno, intermediate.OurTypeAnnotation
        ) and isinstance(item_type_anno.our_type, intermediate.Enumeration)
        enum_name = java_naming.enum_name(item_type_anno.our_type.name)
        return Stripped(f"tryNamedElementAs{enum_name}")

    elif isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
        item_type_anno.our_type,
        (intermediate.AbstractClass, intermediate.ConcreteClass),
    ):
        item_our_type = item_type_anno.our_type

        if (
            isinstance(item_our_type, intermediate.AbstractClass)
            or len(item_our_type.concrete_descendants) > 0
        ):
            interface_name = java_naming.interface_name(item_our_type.name)
            return Stripped(f"try{interface_name}FromElement")
        else:
            class_name = java_naming.class_name(item_our_type.name)
            return Stripped(f"try{class_name}FromElement")
    elif isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
        item_type_anno.our_type, intermediate.NamedUnion
    ):
        union_name = java_naming.union_name(item_type_anno.our_type.name)
        return Stripped(f"try{union_name}FromElement")
    else:
        raise NotImplementedError(
            f"We only handle XML de/serialization of atomic items "
            f"(primitives, constrained primitives, enumeration literals) "
            f"or classes, but you want to generate the code for an item of "
            f"type {item_type_anno}. Please contact the developers if you need "
            f"this feature."
        )


def _xml_deserialize_atomic_item_call(
    item_type_anno: intermediate.TypeAnnotationUnion,
    name_literal: Stripped,
    reader_var: str = "reader",
) -> Stripped:
    """
    Generate the call expression for de-serializing a single atomic item.

    ``name_literal`` (*e.g.*, ``"v"`` for the items of a list, or ``"v1"``,
    ``"v2"`` *etc.* for the items of a tuple) is only used for a primitive
    or an enumeration literal; a class is dispatched through its own
    natural element tag, so it is ignored in that case.

    ``reader_var`` names the in-scope ``XMLEventReader`` variable to read
    from. It defaults to ``"reader"``, but callers which embed the call in
    a lambda whose parameter shadows the enclosing ``reader`` (as list-item
    deserialization does) must pass the lambda's own parameter name instead.
    """
    method_name = _xml_deserialize_atomic_item_method_name(item_type_anno)

    if _xml_deserialize_atomic_item_is_scalar(item_type_anno):
        return Stripped(f"{method_name}({reader_var}, {name_literal})")
    else:
        return Stripped(f"{method_name}({reader_var})")


def _generate_deserialize_list_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the code to de-serialize a property ``prop`` as a list."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.ListTypeAnnotation), (
        f"This function is expected to be called only for a property whose "
        f"(optional-stripped) type is a list, since the caller "
        f"(_generate_deserialize_property) already dispatches on "
        f"intermediate.ListTypeAnnotation before invoking us, but the "
        f"property {prop.name!r} has the type {prop.type_annotation}."
    )

    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

    # NOTE (mristin):
    # The item deserializer is passed to ``parseList`` as a lambda, so its
    # parameter has to be named differently than the enclosing method's own
    # ``reader`` parameter to avoid shadowing it.
    item_deserialize_call = _xml_deserialize_atomic_item_call(
        item_type_anno=type_anno.items,
        name_literal=Stripped('"v"'),
        reader_var="itemReader",
    )

    item_type = java_common.generate_type(type_anno.items)

    cls_name = java_naming.class_name(cls.name)

    try_target_var = java_naming.variable_name(Identifier(f"try_{prop.name}"))

    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    return Stripped(
        f"""\
final Reporting.Result<List<{item_type}>> {try_target_var} = parseList(
{I}reader,
{I}isEmptyProperty,
{I}{item_type}.class,
{I}itemReader -> {item_deserialize_call});

if ({try_target_var}.isError()) {{
{I}{try_target_var}.getError()
{II}.prependSegment(
{III}new Reporting.NameSegment(
{IIII}{xml_prop_name_literal}));
{I}return {try_target_var}.castTo({cls_name}.class);
}}

{target_var} = {try_target_var}.getResult();"""
    )


def _generate_parse_tuple_helper(arity: int) -> Stripped:
    """Generate the generic helper to parse an XML sequence as a tuple."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    tuple_type = f"Tuple{arity}<{', '.join(type_params)}>"

    param_lines = [
        f"Function<XMLEventReader, Reporting.Result<? extends T{i + 1}>> parseItem{i + 1}"
        for i in range(arity)
    ]

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Parse a tuple of {arity} item(s) from {{@code reader}}, each de-serialized
 * with the corresponding {{@code parseItemI}}.
 */
private static <{", ".join(type_params)}> Reporting.Result<{tuple_type}> parseTuple{arity}(
{I}XMLEventReader reader,
{I}boolean isEmptyProperty,
"""
    )
    for i, param_line in enumerate(param_lines):
        writer.write(I)
        writer.write(param_line)
        writer.write(",\n" if i < len(param_lines) - 1 else ") {\n")

    writer.write(
        f"""\
{I}if (isEmptyProperty) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected exactly {arity} item(s), but got a self-closing element");
{II}return Reporting.Result.failure(error);
{I}}}

"""
    )

    for i in range(arity):
        writer.write(
            f"""\
{I}final Reporting.Result<? extends T{i + 1}> item{i + 1}Result =
{II}parseItem{i + 1}.apply(reader);
{I}if (item{i + 1}Result.isError()) {{
{II}item{i + 1}Result.getError()
{III}.prependSegment(new Reporting.IndexSegment({i}));
{II}return Reporting.Result.failure(item{i + 1}Result.getError());
{I}}}

"""
        )

    tuple_literal = java_common.generate_tuple_literal(
        item_exprs=[Stripped(f"item{i + 1}Result.getResult()") for i in range(arity)]
    )

    writer.write(
        f"""\
{I}return Reporting.Result.success(
{II}{indent_but_first_line(tuple_literal, II)});
}}"""
    )

    return Stripped(writer.getvalue())


def _generate_as_scalar_tuple_item_reader() -> Stripped:
    """Generate the adapter binding a positional name into a tuple item reader."""
    return Stripped(
        f"""\
/**
 * Adapt {{@code readNamed}} together with {{@code name}} into a tuple item
 * reader.
 *
 * <p>{{@code name}} ({{@code "v1"}}, {{@code "v2"}}, ...) is a plain runtime
 * string, not a type, so it can not be pinned via a generic type parameter --
 * binding it requires an actual closure, built once here.
 */
private static <T> Function<XMLEventReader, Reporting.Result<? extends T>> asScalarTupleItemReader(
{I}String name,
{I}BiFunction<XMLEventReader, String, Reporting.Result<? extends T>> readNamed) {{
{I}return reader -> readNamed.apply(reader, name);
}}"""
    )


def _generate_as_instance_tuple_item_reader() -> Stripped:
    """Generate the adapter binding a class's own reader into a tuple item reader."""
    return Stripped(
        f"""\
/**
 * Adapt {{@code readInstance}} into a tuple item reader, checking first
 * that {{@code reader}} is positioned at a start element, and naming the
 * expected class as {{@code itemTypeName}} if it is not.
 *
 * <p>Unlike a list, whose items all share a single class, each tuple item
 * can have a different class, dispatched through its own natural element
 * tag rather than a positional {{@code v1}}/{{@code v2}} wrapper -- so the
 * "expected a start element" message has to name the expected class itself,
 * and {{@code readInstance}} is a different function value at every call
 * site. Both are runtime values, not types, so binding them requires an
 * actual closure, built once here.
 */
private static <T> Function<XMLEventReader, Reporting.Result<? extends T>> asInstanceTupleItemReader(
{I}String itemTypeName,
{I}Function<XMLEventReader, Reporting.Result<? extends T>> readInstance) {{
{I}return reader -> {{
{II}skipWhitespaceAndComments(reader);
{II}if (!currentEvent(reader).isStartElement()) {{
{III}final Reporting.Error error = new Reporting.Error(
{IIII}"Expected a start element opening an instance of " + itemTypeName +
{IIIII}", but got an XML " + getEventTypeAsString(currentEvent(reader)));
{III}return Reporting.Result.failure(error);
{II}}}
{II}return readInstance.apply(reader);
{I}}};
}}"""
    )


def _generate_deserialize_tuple_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the code to de-serialize a property ``prop`` as a tuple."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.TupleTypeAnnotation), (
        f"This function is expected to be called only for a property whose "
        f"(optional-stripped) type is a tuple, since the caller "
        f"(_generate_deserialize_property) already dispatches on "
        f"intermediate.TupleTypeAnnotation before invoking us, but the "
        f"property {prop.name!r} has the type {prop.type_annotation}."
    )

    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))
    cls_name = java_naming.class_name(cls.name)
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)
    arity = len(type_anno.items)
    tuple_type = java_common.generate_type(type_anno)

    try_target_var = java_naming.variable_name(Identifier(f"try_{prop.name}"))

    item_readers = []  # type: List[Stripped]
    for i, item_type_anno in enumerate(type_anno.items):
        method_name = _xml_deserialize_atomic_item_method_name(item_type_anno)

        if _xml_deserialize_atomic_item_is_scalar(item_type_anno):
            v_name_literal = java_common.string_literal(f"v{i + 1}")
            item_readers.append(
                Stripped(
                    f"asScalarTupleItemReader(\n"
                    f"{I}{v_name_literal},\n"
                    f"{I}_DeserializeImplementation::{method_name})"
                )
            )
        else:
            item_type = java_common.generate_type(item_type_anno)
            item_type_name_literal = java_common.string_literal(item_type)
            item_readers.append(
                Stripped(
                    f"asInstanceTupleItemReader(\n"
                    f"{I}{item_type_name_literal},\n"
                    f"{I}_DeserializeImplementation::{method_name})"
                )
            )

    joined_item_readers = ",\n".join(item_readers)

    return Stripped(
        f"""\
final Reporting.Result<{tuple_type}> {try_target_var} = parseTuple{arity}(
{I}reader,
{I}isEmptyProperty,
{I}{indent_but_first_line(joined_item_readers, I)});

if ({try_target_var}.isError()) {{
{I}{try_target_var}.getError()
{II}.prependSegment(
{III}new Reporting.NameSegment(
{IIII}{xml_prop_name_literal}));
{I}return {try_target_var}.castTo({cls_name}.class);
}}

{target_var} = {try_target_var}.getResult();"""
    )


@require(lambda prop, cls: id(prop) in cls.property_id_set)
def _generate_deserialize_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the snippet to deserialize the property ``prop`` from the content."""
    blocks = []  # type: List[Stripped]

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        blocks.append(_generate_deserialize_primitive_property(prop=prop, cls=cls))
    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(
                _generate_deserialize_enumeration_property(prop=prop, cls=cls)
            )
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # NOTE (empwilli):
            # The constrained primitives are only verified, but not represented as
            # separate classes in the XSD.
            blocks.append(_generate_deserialize_primitive_property(prop=prop, cls=cls))
        elif isinstance(
            our_type, (intermediate.ConcreteClass, intermediate.AbstractClass)
        ):
            if (
                isinstance(our_type, intermediate.AbstractClass)
                or len(our_type.concrete_descendants) > 0
            ):
                blocks.append(
                    _generate_deserialize_interface_property(prop=prop, cls=cls)
                )
            else:
                blocks.append(_generate_deserialize_cls_property(prop=prop, cls=cls))
        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(
                _generate_deserialize_named_union_property(prop=prop, cls=cls)
            )
        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        blocks.append(_generate_deserialize_list_property(prop=prop, cls=cls))

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        blocks.append(_generate_deserialize_tuple_property(prop=prop, cls=cls))

    else:
        assert_never(type_anno)

    return Stripped("\n\n".join(blocks)), None


def _generate_deserialize_impl_cls_from_sequence(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the function to de-serialize the ``cls`` from an XML sequence."""
    name = java_naming.class_name(identifier=cls.name)

    description = Stripped(
        f"""\
/**
 * Deserialize an instance of class {name} from a sequence of XML elements.
 *
 * <p>If {{@code isEmptySequence}} is set, we should try to deserialize
 * the instance from an empty sequence. That is, the parent element
 * was a self-closing element.
 */"""
    )

    # NOTE (empwilli):
    # Hard-wire for the case when no sequence is read
    if len(cls.constructor.arguments) == 0:
        return (
            Stripped(
                f"""\
{description}
private static Reporting.Result<{name}> try{name}FromSequence(
{I}XMLEventReader reader,
{I}boolean isEmptySequence) {{
{I}return Reporting.Result.success(new {name}());
}}"""
            ),
            None,
        )

    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    assert len(cls.constructor.arguments) > 0, "Otherwise expected hard-wiring above"
    init_target_var_stmts = []  # type: List[Stripped]
    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        assert isinstance(
            type_anno,
            (
                intermediate.PrimitiveTypeAnnotation,
                intermediate.OurTypeAnnotation,
                intermediate.ListTypeAnnotation,
                intermediate.TupleTypeAnnotation,
            ),
        )

        target_type = java_common.generate_type(type_anno)
        target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

        init_target_var_stmts.append(Stripped(f"{target_type} {target_var} = null;"))
    blocks.append(Stripped("\n".join(init_target_var_stmts)))

    # noinspection PyListCreation
    blocks_for_non_empty = []  # type: List[Stripped]

    blocks_for_non_empty.append(
        Stripped(
            f"""\
skipWhitespaceAndComments(reader);
if (currentEvent(reader).isEndDocument()) {{
{I}final Reporting.Error error = new Reporting.Error(
{II}"Expected an XML element representing " +
{II}"a property of an instance of class {name}, " +
{II}"but reached the end-of-file");
{I}return Reporting.Result.failure(error);
}}"""
        )
    )

    case_blocks = []  # type: List[Stripped]
    for prop in cls.properties:
        case_body, error = _generate_deserialize_property(prop=prop, cls=cls)
        if error is not None:
            errors.append(error)
            continue

        assert case_body is not None

        xml_prop_name = prop.xml_name
        xml_prop_name_literal = java_common.string_literal(xml_prop_name)
        case_blocks.append(
            Stripped(
                f"""\
case {xml_prop_name_literal}:
{{
{I}{indent_but_first_line(case_body, I)}
{I}break;
}}"""
            )
        )

    if len(errors) > 0:
        return None, errors

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}final Reporting.Error error = new Reporting.Error(
{II}"We expected properties of the class {name}, " +
{II}"but got an unexpected element " +
{II}"with the name " + elementName);
{I}return Reporting.Result.failure(error);"""
        )
    )

    switch_body = "\n".join(case_blocks)

    blocks_for_non_empty.append(
        Stripped(
            f"""\
while (true) {{
{I}skipWhitespaceAndComments(reader);

{I}if (currentEvent(reader).isEndElement() || currentEvent(reader).isEndDocument()) {{
{II}break;
{I}}}

{I}if (!currentEvent(reader).isStartElement()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected an XML start element representing " +
{III}"a property of an instance of class {name}, " +
{III}"but got the node of type " + getEventTypeAsString(currentEvent(reader)) +
{III}" with the value " + currentEvent(reader));
{II}return Reporting.Result.failure(error);
{I}}}

{I}final Reporting.Result<String> tryElementName = tryElementName(reader);
{I}if (tryElementName.isError()) {{
{II}return tryElementName.castTo({name}.class);
{I}}}

{I}final boolean isEmptyProperty = isEmptyElement(reader);
{I}final String elementName = tryElementName.getResult();

{I}switch (tryElementName.getResult()) {{
{II}{indent_but_first_line(switch_body, II)}
{I}}}

{I}skipWhitespaceAndComments(reader);


{I}final Reporting.Result<XMLEvent> checkEndElement = verifyClosingTagForClass(
{II}"{name}",
{II}reader,
{II}tryElementName);
{I}if (checkEndElement.isError()) return checkEndElement.castTo({name}.class);

}}"""
        )
    )

    body_for_non_empty_sequence = "\n".join(blocks_for_non_empty)
    blocks.append(
        Stripped(
            f"""\
if (!isEmptySequence) {{
{I}{indent_but_first_line(body_for_non_empty_sequence, I)}
}}"""
        )
    )

    # region Check that the mandatory properties have been set

    for prop in cls.properties:
        prop_java = java_naming.property_name(prop.name)
        target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            blocks.append(
                Stripped(
                    f"""\
if ({target_var} == null) {{
{I}final Reporting.Error error = new Reporting.Error(
{II}"The required property {prop_java} has not been given " +
{II}"in the XML representation of an instance of class {name}");
{I}return Reporting.Result.failure(error);
}}"""
                )
            )

    # endregion

    # region Pass in properties as arguments to the constructor

    property_names = [prop.name for prop in cls.properties]
    constructor_argument_names = [arg.name for arg in cls.constructor.arguments]

    # fmt: off
    assert (
            set(prop.name for prop in cls.properties)
            == set(arg.name for arg in cls.constructor.arguments)
    ), (
        f"Expected the properties to coincide with constructor arguments, "
        f"but they do not for {cls.name!r}:"
        f"{property_names=}, {constructor_argument_names=}"
    )
    # fmt: on

    init_writer = io.StringIO()
    init_writer.write(f"return Reporting.Result.success(new {name}(\n")

    for i, arg in enumerate(cls.constructor.arguments):
        prop = cls.properties_by_name[arg.name]

        # NOTE (empwilli):
        # The argument to the constructor may be optional while the property might
        # be required, since we can set the default value in the body of the
        # constructor. However, we can not have an optional property and a required
        # constructor argument as we then would not know how to create the instance.

        if not (
            intermediate.type_annotations_equal(
                arg.type_annotation, prop.type_annotation
            )
            or intermediate.type_annotations_equal(
                intermediate.beneath_optional(arg.type_annotation),
                prop.type_annotation,
            )
        ):
            errors.append(
                Error(
                    arg.parsed.node,
                    f"Expected type annotation for property {prop.name!r} "
                    f"and constructor argument {arg.name!r} "
                    f"of the class {cls.name!r} to have matching types, "
                    f"but they do not: "
                    f"property type is {prop.type_annotation} "
                    f"and argument type is {arg.type_annotation}. "
                    f"Hence we do not know how to generate the call "
                    f"to the constructor in the XML de-serialization.",
                )
            )
            continue

        arg_var = java_naming.variable_name(Identifier(f"the_{arg.name}"))

        init_writer.write(f"{I}{arg_var}")

        if i < len(cls.constructor.arguments) - 1:
            init_writer.write(",\n")
        else:
            init_writer.write("));")

    if len(errors) > 0:
        return None, errors

    # endregion

    blocks.append(Stripped(init_writer.getvalue()))

    writer = io.StringIO()
    writer.write(
        f"""\
{description}
private static Reporting.Result<{name}> try{name}FromSequence(
{I}XMLEventReader reader,
{I}boolean isEmptySequence) {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_deserialize_impl_concrete_cls_from_element(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the function to de-serialize a concrete ``cls`` from an XML element."""
    name = java_naming.class_name(cls.name)
    xml_name = naming.xml_class_name(cls.name)
    xml_name_literal = java_common.string_literal(xml_name)

    return Stripped(
        f"""\
/**
 * Deserialize an instance of class {name} from an XML element.
 */
private static Reporting.Result<? extends {name}> try{name}FromElement(
{I}XMLEventReader reader) {{
{I}return parseInstanceFromElement(
{II}reader,
{II}{name}.class,
{II}(elementName, isEmptyElement) -> {{
{III}if (!{xml_name_literal}.equals(elementName)) {{
{IIII}final Reporting.Error error = new Reporting.Error(
{IIIII}"Expected an element representing an instance of class {name} " +
{IIIII}"with element name {xml_name}, but got: " + elementName);
{IIII}return Reporting.Result.failure(error);
{III}}}

{III}return try{name}FromSequence(reader, isEmptyElement);
{II}}});
}}"""
    )


def _generate_deserialize_impl_interface_from_element(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate the function to de-serialize an ``interface`` from an XML element."""
    name = java_naming.interface_name(interface.name)

    case_stmts = []  # type: List[Stripped]
    for implementer in interface.implementers:
        implementer_xml_name_literal = java_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        implementer_name = java_naming.class_name(implementer.name)

        case_stmts.append(
            Stripped(
                f"""\
case {implementer_xml_name_literal}:
{I}return try{implementer_name}FromSequence(reader, isEmptyElement);"""
            )
        )

    case_stmts.append(
        Stripped(
            f"""\
default:
{I}final Reporting.Error error = new Reporting.Error(
{II}"Unexpected element with the name " + elementName);
{I}return Reporting.Result.failure(error);"""
        )
    )

    case_stmts_joined = "\n".join(case_stmts)

    return Stripped(
        f"""\
/**
 * Deserialize an instance of {name} from an XML element.
 */
private static Reporting.Result<? extends {name}> try{name}FromElement(
{I}XMLEventReader reader) {{
{I}return parseInstanceFromElement(
{II}reader,
{II}{name}.class,
{II}(elementName, isEmptyElement) -> {{
{III}switch (elementName) {{
{IIII}{indent_but_first_line(case_stmts_joined, IIII)}
{III}}}
{II}}});
}}"""
    )


def _generate_deserialize_impl_named_union_from_element(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the function to de-serialize the named union ``named_union`` from
    an XML element.

    Dispatch uniformly on the element's own tag over every flattened
    implementer -- XML elements are always self-tagging with the concrete
    class's own name, regardless of whether that implementer is dispatched
    by ``modelType`` on the JSON side.
    """
    name = java_naming.union_name(named_union.name)

    case_stmts = []  # type: List[Stripped]
    for implementer in named_union.implementers:
        implementer_xml_name_literal = java_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        implementer_name = java_naming.class_name(implementer.name)

        case_stmts.append(
            Stripped(
                f"""\
case {implementer_xml_name_literal}: {{
{I}final Reporting.Result<{implementer_name}> result =
{II}try{implementer_name}FromSequence(reader, isEmptyElement);
{I}if (result.isError()) {{
{II}return result.castTo({name}.class);
{I}}}
{I}return Reporting.Result.success({name}.from{implementer_name}(result.getResult()));
}}"""
            )
        )

    case_stmts.append(
        Stripped(
            f"""\
default:
{I}final Reporting.Error error = new Reporting.Error(
{II}"Unexpected element with the name " + elementName);
{I}return Reporting.Result.failure(error);"""
        )
    )

    case_stmts_joined = "\n".join(case_stmts)

    return Stripped(
        f"""\
/**
 * Deserialize an instance of {name} from an XML element.
 */
private static Reporting.Result<? extends {name}> try{name}FromElement(
{I}XMLEventReader reader) {{
{I}return parseInstanceFromElement(
{II}reader,
{II}{name}.class,
{II}(elementName, isEmptyElement) -> {{
{III}switch (elementName) {{
{IIII}{indent_but_first_line(case_stmts_joined, IIII)}
{III}}}
{II}}});
}}"""
    )


def _generate_deserialize_impl(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the implementation for deserialization functions."""
    blocks = [
        _generate_current_event(),
        _generate_get_event_type_as_string(),
        _generate_is_empty_element(),
        _generate_verify_closing_tag_for_class(),
        _generate_parse_instance_from_element_generic(),
        _generate_skip_whitespace_and_comments(),
        _generate_skip_start_document(),
        _generate_try_element_name(),
        _generate_try_content_for_primitives(),
        _generate_try_named_start_element(),
        _generate_try_named_end_element(),
        *_generate_try_named_element_as_primitive_functions(),
        _generate_parse_list(),
    ]  # type: List[Stripped]

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_try_named_element_as_enumeration(enumeration))

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        blocks.append(_generate_as_scalar_tuple_item_reader())
        blocks.append(_generate_as_instance_tuple_item_reader())
        for arity in tuple_arities:
            blocks.append(_generate_parse_tuple_helper(arity=arity))

    errors = []  # type: List[Error]

    # NOTE (empwilli):
    # Enumerations are going to be directly deserialized using
    # ``Stringification``.

    # NOTE (empwilli):
    # Constrained primitives are only verified, but do not represent a C# type.

    for cls in symbol_table.classes:
        if cls.is_implementation_specific:
            implementation_keys = [
                specific_implementations.ImplementationKey(
                    f"Xmlization/DeserializeImplementation/"
                    f"{cls.name}_from_element.java"
                ),
                specific_implementations.ImplementationKey(
                    f"Xmlization/DeserializeImplementation/"
                    f"{cls.name}_from_sequence.java"
                ),
            ]

            for implementation_key in implementation_keys:
                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            cls.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {cls.name}: {implementation_key}",
                        )
                    )
                    continue
                else:
                    blocks.append(spec_impls[implementation_key])
        else:
            if isinstance(cls, intermediate.ConcreteClass):
                (
                    block,
                    generation_errors,
                ) = _generate_deserialize_impl_cls_from_sequence(cls=cls)
                if generation_errors is not None:
                    errors.append(
                        Error(
                            cls.parsed.node,
                            f"Failed to generate the XML deserialization code "
                            f"for the class {cls.name}",
                            generation_errors,
                        )
                    )
                else:
                    assert block is not None
                    blocks.append(block)

            if cls.interface is not None:
                blocks.append(
                    _generate_deserialize_impl_interface_from_element(
                        interface=cls.interface
                    )
                )

            if isinstance(cls, intermediate.ConcreteClass):
                blocks.append(
                    _generate_deserialize_impl_concrete_cls_from_element(cls=cls)
                )

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_deserialize_impl_named_union_from_element(named_union=named_union)
        )

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()

    writer.write(
        """\
/**
 * Implement the deserialization of meta-model classes from XML.
 *
 * <p>The implementation propagates an {@link Reporting.Error} instead of
 * relying on exceptions. Under the assumption that incorrect data is much less
 * frequent than correct data, this makes the deserialization more
 * efficient.
 *
 * <p>However, we do not want to force the client to deal with
 * the {@link Reporting.Error} class as this is not intuitive.
 * Therefore we distinguish the implementation, realized in
 * {@link _DeserializeImplementation}, and the facade given in
 * {@link Deserialize} class.
 */
private static class _DeserializeImplementation
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_deserialize_from(name: Identifier) -> Stripped:
    """Generate the facade method for deserialization of the class or interface."""
    xml_prop_name_literal = java_common.string_literal(naming.xml_property(name))
    writer = io.StringIO()

    writer.write(
        f"""\
/**
 * Deserialize an instance of {name} from {{@code reader}}.
 *
 * @param reader Initialized XML reader with reader.peek() set to the element
 */
"""
    )
    writer.write(
        f"""\
public static {name} deserialize{name}(
{I}XMLEventReader reader) {{

{I}_DeserializeImplementation.skipStartDocument(reader);
{I}_DeserializeImplementation.skipWhitespaceAndComments(reader);

{I}Reporting.Result<? extends {name}> result =
{II}_DeserializeImplementation.try{name}FromElement(
{III}reader);

{I}return result.onError(error -> {{
{II}error.prependSegment(new Reporting.NameSegment({xml_prop_name_literal}));
{II}throw new DeserializeException(
{III}Reporting.generateRelativeXPath(error.getPathSegments()),
{III}error.getCause());
{I}}});
}}"""
    )

    return Stripped(writer.getvalue())


def _generate_deserialize(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the public class ``Deserialize``."""
    blocks = []  # type: List[Stripped]

    # NOTE (empwilli):
    # We use stringification for de-serialization of enumerations.

    # NOTE (empwilli):
    # Constrained primitives are not handled as separate classes, but as
    # primitives, and only verified in the verification.

    for cls in symbol_table.classes:
        if cls.interface is not None:
            blocks.append(
                _generate_deserialize_from(
                    name=java_naming.interface_name(cls.interface.name)
                )
            )

        if isinstance(cls, intermediate.ConcreteClass):
            blocks.append(
                _generate_deserialize_from(name=java_naming.class_name(cls.name))
            )

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_deserialize_from(name=java_naming.union_name(named_union.name))
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Deserialize instances of meta-model classes from XML.
 */
"""
    )

    first_cls = symbol_table.classes[0] if len(symbol_table.classes) > 0 else None

    if first_cls is not None:
        cls_name = None  # type: Optional[str]
        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = java_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = java_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = java_naming.variable_name(Identifier("an_instance"))

        writer.write(
            f"""\
/** <pre>
 * Here is an example how to parse an instance of class {cls_name}:
 * {{@code
 * XMLEventReader reader = xmlFactory.createXMLEventReader(...some arguments...);
 * {cls_name} {an_instance_variable} = Deserialize.deserialize{cls_name}(
 * {I}reader);
 * }}
 * </pre>
 *
 * <pre>
 * If the elements live in a namespace, you have to supply it. For example:
 * {{@code
 * XMLEventReader reader = xmlFactory.createXMLEventReader(...some arguments...);
 * {cls_name} {an_instance_variable} = Deserialize.deserialize{cls_name}(
 * {I}reader,
 * {I}"http://www.example.com/5/12");
 * }}
 * </pre>
 */
"""
        )

    writer.write(
        """\
public static class Deserialize
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_serialize_element() -> Stripped:
    """Generate the generic helper to write a property as a named XML element."""
    return Stripped(
        f"""\
@FunctionalInterface
private interface ElementContentSerializer<T> {{
{I}void serialize(T that, XMLStreamWriter writer) throws XMLStreamException;
}}

/**
 * Write {{@code that}} as an XML element named {{@code name}}, delegating
 * the content in-between the start and the end tag to
 * {{@code serializeContent}}.
 *
 * <p>This is shared by all the property kinds (primitive, enumeration,
 * class, interface, list) as they all wrap their content in exactly the
 * same way.
 */
private <T> void serializeElement(
{I}String name,
{I}T that,
{I}XMLStreamWriter writer,
{I}ElementContentSerializer<T> serializeContent) {{
{I}try {{
{II}writer.writeStartElement(name);
{II}if (topLevel) {{
{III}writer.writeNamespace("xmlns", AAS_NAME_SPACE);
{III}topLevel = false;
{II}}}
{II}serializeContent.serialize(that, writer);
{II}writer.writeEndElement();
{I}}} catch (XMLStreamException exception) {{
{II}throw new SerializeException("", exception.getMessage());
{I}}}
}}"""
    )


def _generate_serialize_items() -> Stripped:
    """Generate the generic helper to write every item of a list property."""
    return Stripped(
        f"""\
/**
 * Adapt {{@code writeItem}} to serialize every item of an iterable.
 *
 * <p>This is shared by all the list-typed properties, which only need to
 * supply how a single item is written.
 */
private <T> ElementContentSerializer<Iterable<T>> serializeItems(
{I}ElementContentSerializer<T> writeItem) {{
{I}return (items, w) -> {{
{II}for (T item : items) {{
{III}writeItem.serialize(item, w);
{II}}}
{I}}};
}}"""
    )


def _generate_as_named_element_serializer() -> Stripped:
    """Generate the adapter binding a name into an item content serializer."""
    return Stripped(
        f"""\
/**
 * Adapt {{@code writeContent}} to serialize a value wrapped in its own
 * {{@code name}} element.
 *
 * <p>This is only needed for a scalar item (a primitive or an enumeration
 * literal), which is wrapped in a positional {{@code v}}/{{@code v1}}/
 * {{@code v2}} *etc.* element; a class item is dispatched through its own
 * natural element tag by {{@code this::visit}} already, so it needs no
 * such wrapping.
 *
 * <p>{{@code name}} is a plain runtime string, not a type, so it can not be
 * pinned via a generic type parameter -- binding it requires an actual
 * closure, built once here.
 */
private <T> ElementContentSerializer<T> asNamedElementSerializer(
{I}String name, ElementContentSerializer<T> writeContent) {{
{I}return (that, w) -> serializeElement(name, that, w, writeContent);
}}"""
    )


def _generate_write_stringified_content() -> Stripped:
    """Generate the helper to write a value's ``toString()`` as XML content."""
    return Stripped(
        f"""\
/**
 * Write {{@code that.toString()}} as XML content.
 *
 * <p>This is shared by every {{@code boolean}}/{{@code long}}/{{@code double}}/
 * {{@code String}}-typed property or list item, standing in for the property-
 * or item-specific {{@link ElementContentSerializer}}.
 */
private <T> void writeStringifiedContent(T that, XMLStreamWriter writer)
{I}throws XMLStreamException {{
{I}writer.writeCharacters(that.toString());
}}"""
    )


def _generate_write_byte_array_content() -> Stripped:
    """Generate the helper to write a byte array as base64-encoded XML content."""
    return Stripped(
        f"""\
/**
 * Write {{@code that}} as base64-encoded XML content.
 *
 * <p>This is shared by every {{@code byte[]}}-typed property or list item,
 * standing in for the property- or item-specific
 * {{@link ElementContentSerializer}}.
 */
private void writeByteArrayContent(byte[] that, XMLStreamWriter writer)
{I}throws XMLStreamException {{
{I}writer.writeCharacters(
{II}Base64.getEncoder().encodeToString(that));
}}"""
    )


def _generate_write_enum_content(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the helper to write a literal of ``enumeration`` as XML content."""
    enum_name = java_naming.enum_name(enumeration.name)
    method_name = java_naming.method_name(
        Identifier(f"write_{enumeration.name}_content")
    )

    return Stripped(
        f"""\
/**
 * Write a literal of {{@link {enum_name}}} as XML content.
 *
 * <p>This is shared by every {enum_name}-typed property or list item,
 * standing in for the property- or item-specific
 * {{@link ElementContentSerializer}}.
 */
private void {method_name}({enum_name} that, XMLStreamWriter writer)
{I}throws XMLStreamException {{
{I}writer.writeCharacters(Stringification.mustToString(that));
}}"""
    )


def _generate_serialize_primitive_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of the primitive-type ``prop`` as XML content."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    a_type = intermediate.try_primitive_type(type_anno)
    assert (
        a_type is not None
    ), f"Unexpected non-primitive type of the property {prop.name!r}: {type_anno}"

    getter_name = java_naming.getter_name(prop.name)
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    content_serializer: Stripped

    if (
        a_type is intermediate.PrimitiveType.BOOL
        or a_type is intermediate.PrimitiveType.INT
        or a_type is intermediate.PrimitiveType.FLOAT
        or a_type is intermediate.PrimitiveType.STR
    ):
        content_serializer = Stripped("this::writeStringifiedContent")
    elif a_type is intermediate.PrimitiveType.BYTEARRAY:
        content_serializer = Stripped("this::writeByteArrayContent")
    else:
        assert_never(a_type)

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return Stripped(
            f"""\
if (that.{getter_name}().isPresent()) {{
{I}serializeElement(
{II}{xml_prop_name_literal},
{II}that.{getter_name}().get(),
{II}writer,
{II}{indent_but_first_line(content_serializer, II)});
}}"""
        )

    return Stripped(
        f"""\
serializeElement(
{I}{xml_prop_name_literal},
{I}that.{getter_name}(),
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )


def _generate_serialize_enumeration_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of an enumeration ``prop`` as XML content."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    ), (
        f"This function is expected to be called only for a property whose "
        f"(optional-stripped) type is an enumeration, since the caller "
        f"(_generate_serialize_property_as_content) already dispatches on "
        f"intermediate.Enumeration before invoking us, but the property "
        f"{prop.name!r} has the type {prop.type_annotation}."
    )

    write_content_method = java_naming.method_name(
        Identifier(f"write_{type_anno.our_type.name}_content")
    )

    getter_name = java_naming.getter_name(prop.name)
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    content_serializer = Stripped(f"this::{write_content_method}")

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return Stripped(
            f"""\
if (that.{getter_name}().isPresent()) {{
{I}serializeElement(
{II}{xml_prop_name_literal},
{II}that.{getter_name}().get(),
{II}writer,
{II}{indent_but_first_line(content_serializer, II)});
}}"""
        )

    return Stripped(
        f"""\
serializeElement(
{I}{xml_prop_name_literal},
{I}that.{getter_name}(),
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )


def _generate_serialize_polymorphic_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """
    Generate the serialization of a polymorphic property as XML content.

    A property is polymorphic here if the element to write is picked at
    run-time from the value itself, dispatched through its own discriminator
    element -- this is the case both for an interface-typed property (either
    an abstract class or a concrete class with concrete descendants) and for
    a named union, so we treat them uniformly.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    # fmt: off
    assert (
        isinstance(type_anno, intermediate.OurTypeAnnotation)
        and (
            isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.NamedUnion),
            )
            or (
                isinstance(type_anno.our_type, intermediate.ConcreteClass)
                and len(type_anno.our_type.concrete_descendants) > 0
            )
        )
    ), (
        f"This function is expected to be called only for a property whose "
        f"(optional-stripped) type requires polymorphic dispatch through "
        f"a Java interface, *i.e.*, either an abstract class, a concrete "
        f"class with concrete descendants, or a named union, since the "
        f"caller (_generate_serialize_property_as_content) already "
        f"dispatches on that before invoking us, but the property "
        f"{prop.name!r} has the type {prop.type_annotation}."
    )
    # fmt: on

    getter_name = java_naming.getter_name(prop.name)
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    # NOTE (mristin):
    # A named union has its own ``visit`` overload in the visitor (see
    # :py:func:`_generate_union_visit_helper`), so ``this::visit`` binds
    # to it exactly as it binds to the inherited ``IClass``-typed overload
    # for a class-typed property.
    content_serializer = Stripped("this::visit")

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return Stripped(
            f"""\
if (that.{getter_name}().isPresent()) {{
{I}serializeElement(
{II}{xml_prop_name_literal},
{II}that.{getter_name}().get(),
{II}writer,
{II}{indent_but_first_line(content_serializer, II)});
}}"""
        )

    return Stripped(
        f"""\
serializeElement(
{I}{xml_prop_name_literal},
{I}that.{getter_name}(),
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )


def _generate_serialize_concrete_class_property_as_sequence(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of the class ``prop`` as a sequence of properties."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.OurTypeAnnotation)
    assert isinstance(type_anno.our_type, intermediate.ConcreteClass)

    cls_to_sequence = java_naming.method_name(
        Identifier(f"{type_anno.our_type.name}_to_sequence")
    )

    getter_name = java_naming.getter_name(prop.name)
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    content_serializer = Stripped(f"(value, w) -> this.{cls_to_sequence}(value, w)")

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return Stripped(
            f"""\
if (that.{getter_name}().isPresent()) {{
{I}serializeElement(
{II}{xml_prop_name_literal},
{II}that.{getter_name}().get(),
{II}writer,
{II}{indent_but_first_line(content_serializer, II)});
}}"""
        )

    return Stripped(
        f"""\
serializeElement(
{I}{xml_prop_name_literal},
{I}that.{getter_name}(),
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )


def _generate_serialize_tuple_helper(arity: int) -> Stripped:
    """Generate the generic helper to serialize a tuple as XML content."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    tuple_type = f"Tuple{arity}<{', '.join(type_params)}>"

    param_lines = [
        f"ElementContentSerializer<T{i + 1}> writeItem{i + 1}" for i in range(arity)
    ]

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Adapt {{@code writeItem1}}, ..., {{@code writeItem{arity}}} to serialize a
 * tuple of {arity} item(s), each writing itself (whether wrapped in its own
 * positional element or dispatched through its own natural element tag, as
 * decided by the caller -- see {{@link #asNamedElementSerializer}}).
 */
private <{", ".join(type_params)}> ElementContentSerializer<{tuple_type}> serializeTuple{arity}(
"""
    )
    for i, param_line in enumerate(param_lines):
        writer.write(I)
        writer.write(param_line)
        writer.write(",\n" if i < len(param_lines) - 1 else ") {\n")

    writer.write(f"{I}return (value, w) -> {{\n")
    for i in range(arity):
        writer.write(f"{II}writeItem{i + 1}.serialize(value.item{i + 1}(), w);\n")
    writer.write(f"{I}}};\n}}")

    return Stripped(writer.getvalue())


def _generate_serialize_tuple_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of a tuple ``prop`` as a sequence of elements."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.TupleTypeAnnotation), (
        f"This function is expected to be called only for a property whose "
        f"(optional-stripped) type is a tuple, since the caller "
        f"(_generate_serialize_property_as_content) already dispatches on "
        f"intermediate.TupleTypeAnnotation before invoking us, but the "
        f"property {prop.name!r} has the type {prop.type_annotation}."
    )

    arity = len(type_anno.items)

    item_content_serializers = []  # type: List[Stripped]

    for i, item_type_anno in enumerate(type_anno.items):
        v_name_literal = java_common.string_literal(f"v{i + 1}")

        primitive_type = intermediate.try_primitive_type(item_type_anno)

        item_content_serializer: Stripped

        if primitive_type is not None:
            write_content_ref: Stripped

            if (
                primitive_type is intermediate.PrimitiveType.BOOL
                or primitive_type is intermediate.PrimitiveType.INT
                or primitive_type is intermediate.PrimitiveType.FLOAT
                or primitive_type is intermediate.PrimitiveType.STR
            ):
                write_content_ref = Stripped("this::writeStringifiedContent")
            elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                write_content_ref = Stripped("this::writeByteArrayContent")
            else:
                assert_never(primitive_type)

            item_content_serializer = Stripped(
                f"asNamedElementSerializer({v_name_literal}, {write_content_ref})"
            )
        elif isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
            item_type_anno.our_type, intermediate.Enumeration
        ):
            write_content_method = java_naming.method_name(
                Identifier(f"write_{item_type_anno.our_type.name}_content")
            )
            item_content_serializer = Stripped(
                f"asNamedElementSerializer({v_name_literal}, this::{write_content_method})"
            )
        elif isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
            item_type_anno.our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            # NOTE (mristin):
            # A class item is dispatched through ``this.visit``, which already
            # matches the shape ``ElementContentSerializer<T>`` expects and
            # writes its own natural element tag, exactly as for a class item
            # of a list -- unlike a scalar item, it must *not* be additionally
            # wrapped in its own ``v{i+1}`` element. A named union item is
            # matched by its own ``visit`` overload (see
            # :py:func:`_generate_union_visit_helper`), so it can be
            # passed on unchanged just like a class item.
            item_content_serializer = Stripped("this::visit")
        else:
            raise NotImplementedError(
                f"We only handle XML de/serialization of atomic tuple items "
                f"(primitives, constrained primitives, enumeration literals) "
                f"or classes, but you want to generate the code for an item of "
                f"type {item_type_anno}. Please contact the developers if you "
                f"need this feature."
            )

        item_content_serializers.append(item_content_serializer)

    joined_item_content_serializers = ",\n".join(item_content_serializers)

    content_serializer = Stripped(
        f"""\
serializeTuple{arity}(
{I}{indent_but_first_line(joined_item_content_serializers, I)})"""
    )

    getter_name = java_naming.getter_name(prop.name)
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return Stripped(
            f"""\
if (that.{getter_name}().isPresent()) {{
{I}serializeElement(
{II}{xml_prop_name_literal},
{II}that.{getter_name}().get(),
{II}writer,
{II}{indent_but_first_line(content_serializer, II)});
}}"""
        )

    return Stripped(
        f"""\
serializeElement(
{I}{xml_prop_name_literal},
{I}that.{getter_name}(),
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )


def _generate_serialize_list_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of a list ``prop`` as a sequence of elements."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.ListTypeAnnotation), (
        f"This function is expected to be called only for a property whose "
        f"(optional-stripped) type is a list, since the caller "
        f"(_generate_serialize_property_as_content) already dispatches on "
        f"intermediate.ListTypeAnnotation before invoking us, but the "
        f"property {prop.name!r} has the type {prop.type_annotation}."
    )

    primitive_type = intermediate.try_primitive_type(type_anno.items)

    content_serializer: Stripped

    if primitive_type is not None:
        item_content_method_ref: Stripped

        if (
            primitive_type is intermediate.PrimitiveType.BOOL
            or primitive_type is intermediate.PrimitiveType.INT
            or primitive_type is intermediate.PrimitiveType.FLOAT
            or primitive_type is intermediate.PrimitiveType.STR
        ):
            item_content_method_ref = Stripped("this::writeStringifiedContent")
        elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
            item_content_method_ref = Stripped("this::writeByteArrayContent")
        else:
            assert_never(primitive_type)

        # NOTE (mristin):
        # An atomic item is wrapped in its own ``v`` element, exactly like a
        # standalone atomic property is wrapped in its own named element --
        # so we reuse ``asNamedElementSerializer`` and the same
        # content-writing method reference for both.
        content_serializer = Stripped(
            f"""\
serializeItems(asNamedElementSerializer("v", {item_content_method_ref}))"""
        )
    elif isinstance(type_anno.items, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.items.our_type, intermediate.Enumeration
    ):
        write_content_method = java_naming.method_name(
            Identifier(f"write_{type_anno.items.our_type.name}_content")
        )

        content_serializer = Stripped(
            f"""\
serializeItems(asNamedElementSerializer("v", this::{write_content_method}))"""
        )
    elif isinstance(type_anno.items, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.items.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    ):
        # NOTE (mristin):
        # A class item is dispatched through ``this.visit``, which already
        # matches the shape ``ElementContentSerializer<T>`` expects, so we
        # pass it directly as a method reference instead of wrapping it in
        # a lambda. A named union item is matched by its own ``visit``
        # overload (see :py:func:`_generate_union_visit_helper`), so it
        # can be passed on unchanged just like a class item.
        content_serializer = Stripped("serializeItems(this::visit)")
    else:
        raise NotImplementedError(
            f"We only handle XML de/serialization of lists containing atomic "
            f"values (primitives, constrained primitives, enumeration literals) "
            f"or classes, but you want to generate the code for a list of "
            f"type {type_anno}. Please contact the developers if you need "
            f"this feature."
        )

    getter_name = java_naming.getter_name(prop.name)
    xml_prop_name_literal = java_common.string_literal(prop.xml_name)

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return Stripped(
            f"""\
if (that.{getter_name}().isPresent()) {{
{I}serializeElement(
{II}{xml_prop_name_literal},
{II}that.{getter_name}().get(),
{II}writer,
{II}{indent_but_first_line(content_serializer, II)});
}}"""
        )

    return Stripped(
        f"""\
serializeElement(
{I}{xml_prop_name_literal},
{I}that.{getter_name}(),
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )


def _generate_serialize_property_as_content(prop: intermediate.Property) -> Stripped:
    """Generate the code to serialize the ``prop`` as content of an XML element."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    body = None  # type: Optional[Stripped]

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        body = _generate_serialize_primitive_property_as_content(prop=prop)
    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            body = _generate_serialize_enumeration_property_as_content(prop=prop)

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            body = _generate_serialize_primitive_property_as_content(prop=prop)

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if (
                isinstance(our_type, intermediate.AbstractClass)
                or len(our_type.concrete_descendants) > 0
            ):
                body = _generate_serialize_polymorphic_property_as_content(prop=prop)
            else:
                body = _generate_serialize_concrete_class_property_as_sequence(
                    prop=prop
                )

        elif isinstance(our_type, intermediate.NamedUnion):
            body = _generate_serialize_polymorphic_property_as_content(prop=prop)

        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        body = _generate_serialize_list_property_as_content(prop=prop)

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = _generate_serialize_tuple_property_as_content(prop=prop)

    else:
        assert_never(type_anno)

    return body


def _generate_class_to_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method to write ``cls`` as a sequence of properties as XML."""
    blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        body = _generate_serialize_property_as_content(prop=prop)
        blocks.append(body)

    interface_name = java_naming.interface_name(cls.name)
    method_name = java_naming.method_name(Identifier(f"{cls.name}_to_sequence"))

    writer = io.StringIO()

    if len(cls.properties) == 0:
        blocks.append(Stripped("// Intentionally empty."))

    writer.write(
        f"""\
private void {method_name}(
{I}{interface_name} that,
{I}XMLStreamWriter writer) {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_visit_for_class(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method to write the ``cls`` as an XML element."""
    interface_name = java_naming.interface_name(cls.name)
    visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))

    cls_to_sequence_name = java_naming.method_name(
        Identifier(f"{cls.name}_to_sequence")
    )

    xml_cls_name_literal = java_common.string_literal(naming.xml_class_name(cls.name))

    writer = io.StringIO()

    writer.write(
        f"""\
@Override
public void {visit_name}(
{I}{interface_name} that,
{I}XMLStreamWriter writer) {{
{I}try {{
{II}writer.writeStartElement(
{III}{xml_cls_name_literal});
{II}if (topLevel) {{
{III}writer.writeNamespace("xmlns", AAS_NAME_SPACE);
{III}topLevel = false;
{II}}}
{II}this.{cls_to_sequence_name}(
{III}that,
{III}writer);
{II}writer.writeEndElement();
{I}}} catch (XMLStreamException exception) {{
{II}throw new SerializeException("", exception.getMessage());
{I}}}
}}"""
    )

    return Stripped(writer.getvalue())


def _generate_union_visit_helper() -> Stripped:
    """
    Generate a single ``visit`` overload shared by every named union.

    A named union is not itself an ``IClass``, so it can not be dispatched by
    the inherited, ``IClass``-typed ``visit(IClass, XMLStreamWriter)``
    overload of ``AbstractVisitorWithContext``. We add this overload,
    single-purpose, so that call sites can keep passing ``this::visit``
    around as a plain method reference or calling it directly, regardless of
    whether the value at hand is a class instance or a named union.

    Dispatching over the common ``IUnion<?>`` (see ``_generate_iunion`` in
    ``_generate_types.py``) instead of the union's own type means we need
    only this one overload for *all* named unions, not one per union.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
private void visit(
{I}IUnion<?> that,
{I}XMLStreamWriter writer) {{
{I}this.visit(
{II}that.getUnderlying(),
{II}writer);
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_visitor(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a visitor which serializes instances of the meta-model to XML."""
    errors = []  # type: List[Error]

    blocks = [
        _generate_serialize_element(),
        _generate_serialize_items(),
        _generate_as_named_element_serializer(),
        _generate_write_stringified_content(),
        _generate_write_byte_array_content(),
    ]  # type: List[Stripped]

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_write_enum_content(enumeration=enumeration))

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_serialize_tuple_helper(arity=arity))

    # The abstract classes are directly dispatched by the transformer,
    # so we do not need to handle them separately.

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_keys = [
                specific_implementations.ImplementationKey(
                    f"Xmlization/VisitorWithWriter/visit_{cls.name}.java"
                ),
                specific_implementations.ImplementationKey(
                    f"Xmlization/VisitorWithWriter/{cls.name}_to_sequence.java"
                ),
            ]

            for implementation_key in implementation_keys:
                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            cls.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {cls.name}: {implementation_key}",
                        )
                    )
                    continue

                blocks.append(spec_impls[implementation_key])
        else:
            blocks.append(_generate_class_to_sequence(cls=cls))

            blocks.append(_generate_visit_for_class(cls=cls))

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_union_visit_helper())

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Serialize recursively the instances as XML elements.
 */
static class _VisitorWithWriter
{I}extends AbstractVisitorWithContext<XMLStreamWriter> {{

{I}private boolean topLevel = true;

"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_serialize(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the static serializer."""
    blocks = [
        Stripped(
            f"""\
/**
 * Serialize an instance of the meta-model to XML.
 */
public static void to(
{I}IClass that,
{I}XMLStreamWriter writer) throws SerializeException {{
{I}_VisitorWithWriter visitor = new _VisitorWithWriter();
{I}visitor.visit(
{II}that, writer);
}}"""
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Serialize instances of meta-model classes to XML.
 */
"""
    )

    first_cls = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )  # type: Optional[intermediate.ClassUnion]

    if first_cls is not None:
        cls_name = None  # type: Optional[str]
        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = java_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = java_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = java_naming.variable_name(Identifier("an_instance"))

        writer.write(
            f"""\
/**
 * <pre>
 * Here is an example how to serialize an instance of {cls_name}:
 * {{@code
 * IClass {an_instance_variable} = new {cls_name}(
 *     ... some constructor arguments ...
 * );
 * XMLStreamWriter writer = xmlWriterFactory.createXMLStreamWriter(...some arguments...);
 * Serialize.to(
 * {I}{an_instance_variable},
 * {I}writer);
 * }}
 * </pre>
 */
"""
        )

    writer.write(
        """\
public static class Serialize
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate the code for XML de/serialization.
    """
    errors = []  # type: List[Error]

    imports = [
        Stripped("import javax.xml.stream.events.XMLEvent;"),
        Stripped("import javax.xml.stream.XMLEventReader;"),
        Stripped("import javax.xml.stream.XMLStreamConstants;"),
        Stripped("import javax.xml.stream.XMLStreamException;"),
        Stripped("import javax.xml.stream.XMLStreamWriter;"),
        Stripped("import java.util.ArrayList;"),
        Stripped("import java.util.Base64;"),
        Stripped("import java.util.function.BiFunction;"),
        Stripped("import java.util.function.Function;"),
        Stripped("import java.util.List;"),
        Stripped("import java.util.Optional;"),
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.reporting.Reporting;"),
        Stripped(f"import {package}.stringification.Stringification;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.impl.*;"),
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.*;"),
    ]  # type: List[Stripped]

    # region Deserialization helpers

    xml_namespace_literal = java_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    # endregion

    # region Deserialization Implementation

    deserialize_impl_block, deserialize_impl_errors = _generate_deserialize_impl(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if deserialize_impl_errors is not None:
        errors.extend(deserialize_impl_errors)

    assert deserialize_impl_block is not None

    # endregion

    # region Deserialization

    deserialize_block = _generate_deserialize(symbol_table=symbol_table)

    # endregion

    # region Visitor

    visitor_block, visitor_errors = _generate_visitor(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if visitor_errors is not None:
        errors.extend(visitor_errors)

    assert visitor_block is not None

    # endregion

    # region Serialization

    serialization_block = _generate_serialize(symbol_table=symbol_table)

    # endregion

    xmlization_blocks = [
        Stripped(
            f"""\
/**
 * Provide de/serialization of meta-model classes to/from XML.
 */
public class Xmlization {{
{I}/**
{I} * Represent a critical error during the deserialization.
{I} */
{I}@SuppressWarnings("serial")
{I}public static class DeserializeException extends RuntimeException {{
{II}private final String path;
{II}private final String reason;

{II}public DeserializeException(String path, String reason) {{
{III}super(reason + " at: " + ("".equals(path) ? "the beginning" : path));
{III}this.path = path;
{III}this.reason = reason;
{II}}}

{II}public Optional<String> getPath() {{
{III}return Optional.ofNullable(path);
{II}}}

{II}public Optional<String> getReason() {{
{III}return Optional.ofNullable(reason);
{II}}}
{I}}}

{I}/**
{I} * Represent a critical error during the serialization.
{I} */
{I}@SuppressWarnings("serial")
{I}public static class SerializeException extends RuntimeException {{
{II}private final String path;
{II}private final String reason;

{II}public SerializeException(String path, String reason) {{
{III}super(reason + " at: " + ("".equals(path) ? "the beginning" : path));
{III}this.path = path;
{III}this.reason = reason;
{II}}}

{II}public Optional<String> getPath() {{
{III}return Optional.ofNullable(path);
{II}}}

{II}public Optional<String> getReason() {{
{III}return Optional.ofNullable(reason);
{II}}}
{I}}}

{I}/**
{I} * The XML namespace of the meta-model
{I} */
{I}public static final String AAS_NAME_SPACE =
{II}{xml_namespace_literal};

{I}{indent_but_first_line(deserialize_impl_block, I)}

{I}{indent_but_first_line(deserialize_block, I)}

{I}{indent_but_first_line(visitor_block, I)}

{I}{indent_but_first_line(serialization_block, I)}
}}"""
        ),
    ]  # type: List[Stripped]

    if len(errors) > 0:
        return None, errors

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.xmlization;"),
        Stripped("\n".join(imports)),
        Stripped("\n\n".join(xmlization_blocks)),
        java_common.WARNING,
    ]  # type: List[Stripped]

    code = "\n\n".join(blocks)

    return [java_common.JavaFile("Xmlization.java", f"{code}\n")], None


# endregion


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
