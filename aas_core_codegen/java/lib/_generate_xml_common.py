"""Generate the XML primitives shared by the de/serialization."""

from typing import List

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_reader_interfaces() -> Stripped:
    """Generate the two shapes which every reader has."""
    return Stripped(
        f"""\
/**
 * Read the content of an element which has already been opened.
 *
 * <p>{{isEmpty}} tells whether that element was self-closing.
 */
@FunctionalInterface
public interface ContentReader<T> {{
{I}Reporting.Result<? extends T> read(XMLEventReader reader, boolean isEmpty);
}}

/**
 * Read a whole element, opening and closing it.
 */
@FunctionalInterface
public interface ElementReader<T> {{
{I}Reporting.Result<? extends T> read(XMLEventReader reader);
}}"""
    )


def _generate_text_helpers() -> Stripped:
    """
    Generate the helpers which read and normalize the text of an element.

    The XML-RPC module needs the reading and the collapsing for its
    ``<string>``, ``<boolean>`` and ``<double>``, whatever primitives
    the meta-model itself happens to use, so neither is gated here.
    """
    return Stripped(
        f"""\
/**
 * Match a run of the four characters which XML calls whitespace.
 */
public static final Pattern WHITESPACE_RUN = Pattern.compile("[ \\t\\n\\r]+");

/**
 * Read the text of the element which the caller has opened.
 *
 * <p>The comments in between are skipped, and the pieces of the text are
 * joined, as a reader is free to split it.
 */
public static String readContentAsString(
{I}XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters()
{II}|| reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}return content.toString();
}}

/**
 * Normalize {{@code text}} the way {{@code whiteSpace="collapse"}}
 * prescribes.
 *
 * <p>Every atomic XSD type except a string fixes {{@code whiteSpace}} to
 * {{@code collapse}}, and a schema author can not change it. A tab, a line
 * feed and a carriage return each become a space, a run of spaces becomes
 * one space, and the leading and trailing spaces go.
 *
 * <p>See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace
 */
public static String collapseWhitespace(String text) {{
{I}return WHITESPACE_RUN.matcher(text).replaceAll(" ").trim();
}}"""
    )


def _generate_exceptions() -> Stripped:
    """
    Generate the two exceptions which the caller of the de/serialization sees.

    They live here, and not beside the module which raises them, because both
    the xmlization and the XML-RPC module raise them and the two are separate
    packages. Java has no alias with which the xmlization could go on
    offering them under its own name, the way the Golang backend does.
    """
    return Stripped(
        f"""\
/**
 * Represent a critical error during the deserialization.
 */
@SuppressWarnings("serial")
public static class DeserializeException extends RuntimeException {{
{I}private final String path;
{I}private final String reason;

{I}public DeserializeException(String path, String reason) {{
{II}super(reason + " at: " + ("".equals(path) ? "the beginning" : path));
{II}this.path = path;
{II}this.reason = reason;
{I}}}

{I}public Optional<String> getPath() {{
{II}return Optional.ofNullable(path);
{I}}}

{I}public Optional<String> getReason() {{
{II}return Optional.ofNullable(reason);
{I}}}
}}

/**
 * Represent a critical error during the serialization.
 */
@SuppressWarnings("serial")
public static class SerializeException extends RuntimeException {{
{I}private final String path;
{I}private final String reason;

{I}public SerializeException(String path, String reason) {{
{II}super(reason + " at: " + ("".equals(path) ? "the beginning" : path));
{II}this.path = path;
{II}this.reason = reason;
{I}}}

{I}public Optional<String> getPath() {{
{II}return Optional.ofNullable(path);
{I}}}

{I}public Optional<String> getReason() {{
{II}return Optional.ofNullable(reason);
{I}}}
}}"""
    )


def _generate_serialize_failure() -> Stripped:
    """Generate the exception which carries the path to the culprit."""
    return Stripped(
        f"""\
/**
 * Signal a failure of the serialization, carrying the path to the culprit.
 *
 * <p>The path is built as the stack unwinds -- every container prepends
 * the one segment it knows, the property its name and the list the index
 * of the item -- which is why this can not be the exception which
 * the caller sees already: that one renders its message in its
 * constructor, so its path has to be complete by then. The enclosing
 * serializer renders and converts.
 *
 * <p>This is thrown across a package boundary, from the XML-RPC writers
 * into the xmlization's, so it is public.
 */
@SuppressWarnings("serial")
public static class SerializeFailure extends RuntimeException {{
{I}private final Reporting.Error error;

{I}public SerializeFailure(Reporting.Error error) {{
{II}super(error.getCause());
{II}this.error = error;
{I}}}

{I}public Reporting.Error getError() {{
{II}return error;
{I}}}
}}"""
    )


def _generate_current_event() -> Stripped:
    """Generate the function to a single XML event."""

    return Stripped(
        f"""\
public static XMLEvent currentEvent(XMLEventReader reader) {{
{I}try {{
{II}return reader.peek();
{I}}} catch (XMLStreamException xmlStreamException) {{
{II}throw new DeserializeException("",
{III}"Failed in method peek because of: " +
{III}xmlStreamException.getMessage());
{I}}}
}}"""
    )


def _generate_get_event_type_as_string() -> Stripped:
    """Generate the function to map XML event types to their string representations."""

    return Stripped(
        f"""\
public static String getEventTypeAsString(XMLEvent event) {{
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


def _generate_skip_whitespace_and_comments() -> Stripped:
    """Generate the function to skip whitespace text and XML comments."""
    return Stripped(
        f"""\
public static void skipWhitespaceAndComments(XMLEventReader reader) {{
{I}while (whiteSpaceOrComment(reader)) {{
{II}reader.next();
{I}}}
}}

public static boolean whiteSpaceOrComment(XMLEventReader reader) {{
{I}final XMLEvent currentEvent = currentEvent(reader);
{I}final boolean isComment = (currentEvent != null &&
{II}currentEvent.getEventType() == XMLStreamConstants.COMMENT);
{I}final boolean isWhiteSpace = (currentEvent != null &&
{II}currentEvent.getEventType() == XMLStreamConstants.CHARACTERS &&
{II}currentEvent.asCharacters().isWhiteSpace());
{I}return isComment || isWhiteSpace;
}}"""
    )


def _generate_is_empty_element() -> Stripped:
    """Generate the function to check if an element is empty."""
    return Stripped(
        f"""\
public static boolean isEmptyElement(XMLEventReader reader) {{
{I}// Skip the element node and go to the content
{I}try {{
{II}reader.nextEvent();
{I}}} catch (XMLStreamException xmlStreamException) {{
{II}throw new DeserializeException("",
{III}"Failed in method isEmptyElement because of: " +
{III}xmlStreamException.getMessage());
{I}}}
{I}return currentEvent(reader).isEndElement();
}}"""
    )


def _generate_try_element_name() -> Stripped:
    """Generate the function to strip the prefix and check the namespace."""
    return Stripped(
        f"""\
/**
 * Describe {{@code ns}} for an error message.
 */
private static String describeNamespace(String ns) {{
{I}return ns.isEmpty() ? "no namespace" : "the namespace " + ns;
}}

private static boolean invalidNameSpace(XMLEvent event, String ns) {{
{I}if (event.isStartElement()) {{
{II}return !ns.equals(event.asStartElement().getName().getNamespaceURI());
{I}}} else {{
{II}return !ns.equals(event.asEndElement().getName().getNamespaceURI());
{I}}}
}}

/**
 * Check the namespace and extract the element's name.
 */
private static Reporting.Result<String> tryElementName(
{I}XMLEventReader reader, String ns) {{
{I}final XMLEvent currentEvent = currentEvent(reader);
{I}final boolean precondition = currentEvent.isStartElement() || currentEvent.isEndElement();
{I}if (!precondition) {{
{II}throw new IllegalStateException("Expected to be at a start or an end element "
{IIII}+ "but got: " + getEventTypeAsString(currentEvent));
{I}}}

{I}if (invalidNameSpace(currentEvent, ns)) {{
{II}final String namespace = currentEvent.isStartElement()
{IIII}? currentEvent.asStartElement().getName().getNamespaceURI()
{IIII}: currentEvent.asEndElement().getName().getNamespaceURI();
{II}final Reporting.Error error = new Reporting.Error(
{IIII}"Expected an element within " + describeNamespace(ns) +
{IIII}", but got an element within " + describeNamespace(namespace));
{II}return Reporting.Result.failure(error);
{I}}}
{I}return Reporting.Result.success(currentEvent.isStartElement()
{III}? currentEvent.asStartElement().getName().getLocalPart()
{III}: currentEvent.asEndElement().getName().getLocalPart());
}}"""
    )


def _generate_peek_element_name() -> Stripped:
    """Generate the function to look up the name of the element ahead."""
    return Stripped(
        f"""\
/**
 * Look up the name of the element which {{@code reader}} is positioned at.
 *
 * <p>This is the single primitive answering "we are at an element, and this is
 * its name": {{@link #readNamedElement}} checks that name against the one its
 * container supplied, a dispatcher switches on it, and a property loop uses it
 * to select the property. Nothing is consumed, which is what lets a dispatcher
 * hand the whole element on to the reader it selected.
 */
private static Reporting.Result<String> peekElementNameInNamespace(
{I}XMLEventReader reader, String ns) {{
{I}skipWhitespaceAndComments(reader);

{I}final XMLEvent currentEvent = currentEvent(reader);
{I}if (currentEvent.isEndDocument()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML element, but reached the end-of-file"));
{I}}}

{I}if (!currentEvent.isStartElement()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML element, but got the node of type " +
{III}getEventTypeAsString(currentEvent) + " with the value " + currentEvent));
{I}}}

{I}return tryElementName(reader, ns);
}}"""
    )


def _generate_consume_end_element() -> Stripped:
    """Generate the function to consume the end tag of an element."""
    return Stripped(
        f"""\
/**
 * Consume the end tag concluding the element called {{@code elementName}}.
 */
private static Reporting.Result<XMLEvent> consumeEndElementInNamespace(
{I}XMLEventReader reader, String elementName, String ns) {{
{I}skipWhitespaceAndComments(reader);

{I}final XMLEvent currentEvent = currentEvent(reader);
{I}if (currentEvent.isEndDocument()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML end element to conclude the element " + elementName +
{III}", but got the end-of-file"));
{I}}}

{I}if (!currentEvent.isEndElement()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML end element to conclude the element " + elementName +
{III}", but got the node of type " + getEventTypeAsString(currentEvent) +
{III}" with the value " + currentEvent));
{I}}}

{I}final Reporting.Result<String> tryEndElementName = tryElementName(reader, ns);
{I}if (tryEndElementName.isError()) {{
{II}return tryEndElementName.castTo(XMLEvent.class);
{I}}}

{I}if (!elementName.equals(tryEndElementName.getResult())) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML end element to conclude the element " + elementName +
{III}", but got the end element with the name " + tryEndElementName.getResult()));
{I}}}

{I}try {{
{II}return Reporting.Result.success(reader.nextEvent());
{I}}} catch (XMLStreamException xmlStreamException) {{
{II}throw new DeserializeException("",
{III}"Failed in method consumeEndElement because of: " +
{III}xmlStreamException.getMessage());
{I}}}
}}"""
    )


def _generate_read_named_element() -> Stripped:
    """Generate the framer binding a name to a content reader."""
    return Stripped(
        f"""\
/**
 * Read a whole element which is expected to be called {{@code name}} and to
 * reside in {{@code ns}}, and read its content with {{@code readContent}}.
 *
 * <p>The name is data, not a type: an instance reads the XML name of its own
 * class, a list item reads {{@code "v"}} and a tuple item reads {{@code "v1"}},
 * {{@code "v2"}}, ... by position. One framer therefore serves them all.
 */
private static <T> Reporting.Result<? extends T> readNamedElementInNamespace(
{I}XMLEventReader reader, String name, String ns,
{I}ContentReader<T> readContent) {{
{I}final Reporting.Result<String> tryElementName = peekElementNameInNamespace(reader, ns);
{I}if (tryElementName.isError()) {{
{II}return Reporting.Result.failure(tryElementName.getError());
{I}}}

{I}if (!name.equals(tryElementName.getResult())) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML element " + name + ", but got an XML element " +
{III}tryElementName.getResult()));
{I}}}

{I}final boolean isEmpty = isEmptyElement(reader);

{I}final Reporting.Result<? extends T> result =
{II}readContent.read(reader, isEmpty);
{I}if (result.isError()) {{
{II}return result;
{I}}}

{I}final Reporting.Result<XMLEvent> endResult =
{II}consumeEndElementInNamespace(reader, name, ns);
{I}if (endResult.isError()) {{
{II}return Reporting.Result.failure(endResult.getError());
{I}}}

{I}return result;
}}"""
    )


def _generate_namespace_bound_readers(uses_json_types: bool) -> Stripped:
    """
    Generate the readers which bind the namespace of an element.

    The namespace is no argument of the de-serialization. An element of
    the document resides in {@code NAMESPACE}, and an element of the XML-RPC
    subset in no namespace at all, so each primitive comes in the one or
    the two flavors which are actually called.
    """
    blocks = [
        Stripped(
            f"""\
/**
 * Look up the name of the element in {{@link #NAMESPACE}} which
 * {{@code reader}} is positioned at.
 *
 * <p>This is the single primitive answering "we are at an element, and this is
 * its name": {{@link #readNamedElement}} checks that name against the one its
 * container supplied, a dispatcher switches on it, and a property loop uses it
 * to select the property. Nothing is consumed, which is what lets a dispatcher
 * hand the whole element on to the reader it selected.
 */
public static Reporting.Result<String> peekElementName(XMLEventReader reader) {{
{I}return peekElementNameInNamespace(reader, NAMESPACE);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Consume the end tag concluding the element called {{@code elementName}} in
 * {{@link #NAMESPACE}}.
 */
public static Reporting.Result<XMLEvent> consumeEndElement(
{I}XMLEventReader reader, String elementName) {{
{I}return consumeEndElementInNamespace(reader, elementName, NAMESPACE);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read a whole element in {{@link #NAMESPACE}} which is expected to be called
 * {{@code name}}, and read its content with {{@code readContent}}.
 */
public static <T> Reporting.Result<? extends T> readNamedElement(
{I}XMLEventReader reader, String name, ContentReader<T> readContent) {{
{I}return readNamedElementInNamespace(reader, name, NAMESPACE, readContent);
}}"""
        ),
    ]  # type: List[Stripped]

    if uses_json_types:
        blocks.extend(
            [
                Stripped(
                    f"""\
/**
 * Look up the name of the element in no namespace at all which
 * {{@code reader}} is positioned at.
 */
public static Reporting.Result<String> peekElementNameInNoNamespace(
{I}XMLEventReader reader) {{
{I}return peekElementNameInNamespace(reader, "");
}}"""
                ),
                Stripped(
                    f"""\
/**
 * Consume the end tag concluding the element called {{@code elementName}} in
 * no namespace at all.
 */
public static Reporting.Result<XMLEvent> consumeEndElementInNoNamespace(
{I}XMLEventReader reader, String elementName) {{
{I}return consumeEndElementInNamespace(reader, elementName, "");
}}"""
                ),
                Stripped(
                    f"""\
/**
 * Read a whole element in no namespace at all which is expected to be called
 * {{@code name}}, and read its content with {{@code readContent}}.
 */
public static <T> Reporting.Result<? extends T> readNamedElementInNoNamespace(
{I}XMLEventReader reader, String name, ContentReader<T> readContent) {{
{I}return readNamedElementInNamespace(reader, name, "", readContent);
}}"""
                ),
            ]
        )

    return Stripped("\n\n".join(blocks))


def _generate_read_nested_element() -> Stripped:
    """Generate the reader of a property whose content is one instance element."""
    return Stripped(
        f"""\
/**
 * Read a self-describing element as the content of the property element which
 * {{@code reader}} is already positioned inside.
 *
 * <p>This looks like a needless layer over {{@code read...FromElement}}: the
 * reader sits at the very same position in both cases, just before a start
 * element, whether that element is the only child of a property element or
 * the next item of a list. The layer exists for the error path alone.
 *
 * <p>A property wraps its instance in an element of its own, so the failing
 * node is one step deeper than the property and the discriminator's name has
 * to be prepended: {{@code value/property/idShort}}. A list item is not
 * wrapped -- the item element *is* the indexed child -- so prepending the name
 * there would give {{@code annotations/*[0]/property/idShort}}, which walks one
 * level past the element {{@code *[0]}} already selects and resolves to
 * nothing.
 *
 * <p>The two callers therefore need different segments, which is why the name
 * can not be prepended inside {{@code read...FromElement}}. Unifying them would
 * take a segment carrying a name *and* a position
 * ({{@code annotations/property[1]}}), and that is a change to
 * {{@link Reporting}}, which the verification and the JSON de-serialization
 * share.
 */
public static <T> Reporting.Result<? extends T> readNestedElement(
{I}XMLEventReader reader, boolean isEmpty, ElementReader<T> readInner) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML element representing an instance, " +
{III}"but encountered a self-closing element"));
{I}}}

{I}final Reporting.Result<String> tryElementName = peekElementName(reader);
{I}if (tryElementName.isError()) {{
{II}return Reporting.Result.failure(tryElementName.getError());
{I}}}

{I}final Reporting.Result<? extends T> result = readInner.read(reader);
{I}if (result.isError()) {{
{II}result.getError()
{III}.prependSegment(
{IIII}new Reporting.NameSegment(
{IIIII}tryElementName.getResult()));
{I}}}

{I}return result;
}}"""
    )


def _generate_content_writer_interface() -> Stripped:
    """Generate the single shape which every writer has."""
    return Stripped(
        f"""\
/**
 * Write {{@code that}} where {{@code writer}} already is.
 *
 * <p>Every value is written through this one shape, so that the writing
 * composes: {{@link #writeElement}} frames it in a start and an end tag, and
 * a class's own {{@code write...AsSequence}} already is one.
 *
 * <p>There is deliberately no second shape for a whole element, as there is
 * on the reading side. An element differs from a content only in what it
 * writes, never in its shape; the reading needs the distinction because
 * a content reader has to be told whether its element was self-closing, and
 * a writer has nothing to be told.
 *
 * <p>Use sites take a {{@code ContentWriter<? super T>}} -- Java's spelling
 * of the contravariance -- so that the single writer of an {{@link IClass}}
 * serves wherever the writer of a more specific interface is expected.
 */
@FunctionalInterface
public interface ContentWriter<T> {{
{I}void write(T that, XMLStreamWriter writer) throws XMLStreamException;
}}"""
    )


def _generate_write_element(uses_json_types: bool) -> Stripped:
    """Generate the framer writing a value as a named XML element."""
    blocks = [
        Stripped(
            f"""\
/**
 * Write {{@code that}} as an XML element named {{@code name}}, its content
 * written by {{@code writeContent}}.
 *
 * <p>An element is nothing but a start and an end tag around a content, so
 * there is no writer per property kind: only the content writer differs,
 * and the type of the value alone decides which one it is.
 *
 * <p>{{@code withNamespace}} declares {{@link #NAMESPACE}} on the element,
 * which only the outermost element does.
 */
public static <T> void writeElement(
{I}String name,
{I}T that,
{I}XMLStreamWriter writer,
{I}boolean withNamespace,
{I}ContentWriter<? super T> writeContent) {{
{I}try {{
{II}writer.writeStartElement(name);
{II}if (withNamespace) {{
{III}writer.writeNamespace("xmlns", NAMESPACE);
{II}}}
{II}writeContent.write(that, writer);
{II}writer.writeEndElement();
{I}}} catch (XMLStreamException exception) {{
{II}throw new SerializeFailure(
{III}new Reporting.Error(exception.getMessage()));
{I}}}
}}

/**
 * Write {{@code that}} as an XML element named {{@code name}} nested in
 * another element, so that the XML namespace is not re-declared.
 *
 * <p>This is what an item of a list or of a tuple is written with. It
 * contributes no segment to the error path: its container has already
 * contributed the item's index, and the index selects this very element
 * (see {{@link #writeListOf}} in the generated writers).
 */
public static <T> void writeElement(
{I}String name,
{I}T that,
{I}XMLStreamWriter writer,
{I}ContentWriter<? super T> writeContent) {{
{I}writeElement(name, that, writer, false, writeContent);
}}"""
        )
    ]  # type: List[Stripped]

    if uses_json_types:
        blocks.append(
            Stripped(
                f"""\
/**
 * Write {{@code that}} as an XML element named {{@code name}} which resides
 * in no namespace at all.
 *
 * <p>{{@code undeclareNamespace}} tells whether this is the outermost such
 * element. That one undeclares the default namespace of the enclosing
 * document, and the elements nested in it inherit that and need no
 * declaration of their own.
 */
public static <T> void writeElementInNoNamespace(
{I}String name,
{I}T that,
{I}XMLStreamWriter writer,
{I}boolean undeclareNamespace,
{I}ContentWriter<? super T> writeContent) {{
{I}try {{
{II}writer.writeStartElement(name);
{II}if (undeclareNamespace) {{
{III}writer.writeNamespace("xmlns", "");
{II}}}
{II}writeContent.write(that, writer);
{II}writer.writeEndElement();
{I}}} catch (XMLStreamException exception) {{
{II}throw new SerializeFailure(
{III}new Reporting.Error(exception.getMessage()));
{I}}}
}}"""
            )
        )

    return Stripped("\n\n".join(blocks))


def _generate_write_stringified_content() -> Stripped:
    """Generate the writer rendering a value through its ``toString``."""
    return Stripped(
        f"""\
/**
 * Write {{@code that.toString()}} as XML content.
 *
 * <p>This is the {{@link ContentWriter}} of every {{@code boolean}}/
 * {{@code long}}/{{@code double}}/{{@code String}}-typed value, be it
 * a property, a list item or a tuple item.
 */
public static <T> void writeStringifiedContent(
{I}T that,
{I}XMLStreamWriter writer) throws XMLStreamException {{
{I}writer.writeCharacters(that.toString());
}}"""
    )


def _generate_write_double_content() -> Stripped:
    """Generate the writer rendering a double as ``xs:double``."""
    return Stripped(
        f"""\
/**
 * Write {{@code that}} as XML content in the lexical form of
 * {{@code xs:double}}.
 *
 * <p>This is the {{@link ContentWriter}} of every {{@code double}}-typed
 * value, be it a property, a list item or a tuple item. A double can not
 * share {{@link #writeStringifiedContent}} with the other primitives:
 * {{@code Double.toString}} renders an infinity as {{@code Infinity}}, where
 * {{@code xs:double}} spells it {{@code INF}}. Only the two infinities differ
 * -- {{@code NaN}} is spelled the same way in both, and a finite number is
 * rendered by {{@code Double.toString}} in a form which {{@code xs:double}}
 * accepts.
 *
 * <p>See: https://www.w3.org/TR/xmlschema-2/#double
 */
public static void writeDoubleContent(
{I}Double that,
{I}XMLStreamWriter writer) throws XMLStreamException {{
{I}final String text;
{I}if (that.isInfinite()) {{
{II}text = (that > 0) ? "INF" : "-INF";
{I}}} else {{
{II}text = that.toString();
{I}}}

{I}writer.writeCharacters(text);
}}"""
    )


def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
) -> List[java_common.JavaFile]:
    """
    Generate the XML primitives shared by the de/serialization.

    Two modules read and write XML: the xmlization, which descends through
    the elements of our own classes, and the XML-RPC de/serialization, which
    descends through the elements within a JSON-able value. Neither the
    skipping of what carries no information, nor the check of the XML
    namespace, nor the framing of an element differs between the two, so all
    of it lives here and is defined exactly once.

    The namespace is a constant here, ``NAMESPACE``, and no argument of
    the primitives: ``Xmlization`` re-exports it as ``AAS_NAME_SPACE``, and
    ``XmlRpc`` needs none at all, as the XML-RPC elements reside in no
    namespace. Where a primitive is called for both, it comes in two flavors,
    one of them named ``...InNoNamespace``.

    Java has no visibility which would hide a class from the user of
    the library while showing it to a sibling package, so the class is
    ``public`` and says in its own comment that it is no part of
    the supported API.

    The ``package`` defines the base Java package of the generated code.
    """
    xml_namespace_literal = java_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    # NOTE (mristin):
    # The XML-RPC subset, over which the JSON-able values are de/serialized,
    # writes its elements in no namespace at all, as the XML-RPC specification
    # prescribes. The primitives which deal with such elements are therefore
    # only generated for a meta-model which actually has a JSON-able type.
    uses_json_types = intermediate.uses_json_types(symbol_table)

    blocks = [
        Stripped(
            f"""\
/**
 * The XML namespace in which all the elements of a document reside.
 *
 * <p>The elements of the XML-RPC subset, over which a JSON-able value is
 * de/serialized, are the one exception: they reside in no namespace at all.
 */
public static final String NAMESPACE =
{I}{xml_namespace_literal};"""
        ),
        _generate_reader_interfaces(),
        _generate_content_writer_interface(),
        _generate_text_helpers(),
        _generate_exceptions(),
        _generate_serialize_failure(),
        _generate_current_event(),
        _generate_get_event_type_as_string(),
        _generate_skip_whitespace_and_comments(),
        _generate_is_empty_element(),
        _generate_write_stringified_content(),
        _generate_write_double_content(),
        _generate_try_element_name(),
        _generate_peek_element_name(),
        _generate_consume_end_element(),
        _generate_read_named_element(),
        _generate_namespace_bound_readers(uses_json_types=uses_json_types),
        _generate_read_nested_element(),
        _generate_write_element(uses_json_types=uses_json_types),
    ]  # type: List[Stripped]

    body = "\n\n".join(blocks)

    class_block = Stripped(
        f"""\
/**
 * Provide the XML primitives shared by the de/serialization.
 *
 * <p>The xmlization reads and writes the elements of our own classes, and
 * the XML-RPC de/serialization the elements within a JSON-able value. The
 * skipping of what carries no information, the check of the XML namespace
 * and the framing of an element are the same for both, and live here.
 *
 * <p>Java has no visibility which would show a class to a sibling package
 * and hide it from the user of the library, so everything here is public.
 */
public final class XmlCommon {{
{I}private XmlCommon() {{
{II}// NOTE (mristin):
{II}// The XML primitives are stateless, so there is nothing to
{II}// instantiate.
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
        Stripped("import java.util.Optional;"),
        Stripped("import java.util.regex.Pattern;"),
        Stripped(f"import {package}.reporting.Reporting;"),
    ]  # type: List[Stripped]

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.xmlcommon;"),
        Stripped("\n".join(imports)),
        class_block,
        java_common.WARNING,
    ]

    code = "\n\n".join(blocks)

    return [java_common.JavaFile("XmlCommon.java", f"{code}\n")]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
