"""Generate the code for XML de/serialization."""

import io
import textwrap

from typing import Final, List, Mapping, MutableMapping, Optional, Set, Tuple

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
)

# region Generate

# region Names of the generated readers

# NOTE (mristin):
# A Java primitive is not a valid part of an identifier as it is spelled
# (``byte[]``), so the primitives need monikers of their own. The monikers are
# *lower-case* on purpose: every one of our types is named through
# :py:func:`aas_core_codegen.naming.capitalized_camel_case`, which always
# yields an upper-case initial, so a primitive moniker can never be confused
# for one of our types -- not even for an enumeration which somebody named
# ``String``.
_PRIMITIVE_TYPE_TO_MONIKER: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.BOOL: "bool",
    intermediate.PrimitiveType.INT: "long",
    intermediate.PrimitiveType.FLOAT: "double",
    intermediate.PrimitiveType.STR: "string",
    intermediate.PrimitiveType.BYTEARRAY: "bytes",
}
assert all(
    primitive_type in _PRIMITIVE_TYPE_TO_MONIKER
    for primitive_type in intermediate.PrimitiveType
)
assert all(
    moniker.islower() for moniker in _PRIMITIVE_TYPE_TO_MONIKER.values()
), "The primitive monikers have to be lower-case, see the note above"

#: Name the function converting the text content, and the type as it is called
#: in the error messages, for each primitive
_CONTENT_CONVERTER_BY_PRIMITIVE: Final[
    Mapping[intermediate.PrimitiveType, Tuple[str, str]]
] = {
    intermediate.PrimitiveType.BOOL: ("readContentAsBool", "Boolean"),
    intermediate.PrimitiveType.INT: ("readContentAsLong", "Long"),
    intermediate.PrimitiveType.FLOAT: ("readContentAsDouble", "Double"),
    intermediate.PrimitiveType.STR: ("readContentAsString", "String"),
    intermediate.PrimitiveType.BYTEARRAY: (
        "readContentAsBase64",
        "base64-encoded bytes",
    ),
}
assert all(
    primitive_type in _CONTENT_CONVERTER_BY_PRIMITIVE
    for primitive_type in intermediate.PrimitiveType
)

#: Give the value of a primitive read from a self-closing element. A primitive
#: which is absent from this mapping can not be read from one at all.
_EMPTY_VALUE_BY_PRIMITIVE: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.STR: '""',
    intermediate.PrimitiveType.BYTEARRAY: "new byte[0]",
}


@ensure(lambda result: "_" not in result)
def _leaf_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name a type which is neither a list nor a tuple.

    The result must not contain an underscore, since the underscore is what
    separates the tokens of a compound moniker. See :py:func:`_type_moniker`.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return _PRIMITIVE_TYPE_TO_MONIKER[primitive_type]

    assert isinstance(type_anno, intermediate.OurTypeAnnotation), (
        f"Expected a primitive, a constrained primitive or one of our types, "
        f"but got: {type_anno}"
    )

    # NOTE (mristin):
    # We name our types by ``generate_type`` so that the name of a reader can
    # not drift apart from the type of that very reader.
    return java_common.generate_type(type_anno)


def _type_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name the type in a way usable as a part of a Java identifier.

    The monikers are a Polish notation over ``_``-separated tokens: ``ListOf``
    takes exactly one argument, ``TupleOf{N}`` exactly ``N`` of them, and
    everything else is a leaf. A leaf token never contains an underscore
    (see :py:func:`_leaf_moniker`), so the encoding is injective -- two
    different types can not be given the same moniker, and hence two different
    readers can not be given the same name.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ListOf_{_type_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        joined = "_".join(_type_moniker(item) for item in type_anno.items)
        return f"TupleOf{len(type_anno.items)}_{joined}"

    return _leaf_moniker(type_anno)


def _is_instance_type(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether ``type_anno`` de-serializes from a self-describing element.

    An instance element carries its own type in its local name, whereas
    everything else is read from an element whose name its container supplies.
    """
    return isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    )


def _is_dispatched(our_type: intermediate.OurType) -> bool:
    """
    Check whether an element of ``our_type`` is dispatched on its own name.

    A concrete class without any descendant has a single admissible element
    name, so a property of that type wraps its properties directly. Everything
    else needs the discriminator element nested within the property element.
    """
    if isinstance(our_type, intermediate.NamedUnion):
        return True

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class or a named union, but got: {our_type}"

    return (
        isinstance(our_type, intermediate.AbstractClass)
        or len(our_type.concrete_descendants) > 0
    )


def _from_element_name(our_type: intermediate.OurType) -> Identifier:
    """
    Name the function reading a whole element of ``our_type``.

    Mind that this is *not* the moniker of the type: a concrete class without
    any descendant is referred to by its interface, but reads through
    a function named after the class itself.
    """
    if isinstance(our_type, intermediate.NamedUnion):
        return Identifier(f"read{java_naming.union_name(our_type.name)}FromElement")

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class or a named union, but got: {our_type}"

    if _is_dispatched(our_type):
        return Identifier(f"read{java_naming.interface_name(our_type.name)}FromElement")

    return Identifier(f"read{java_naming.class_name(our_type.name)}FromElement")


def _from_sequence_name(cls: intermediate.ClassUnion) -> Identifier:
    """Name the function reading the properties of ``cls`` from their sequence."""
    return Identifier(f"read{java_naming.class_name(cls.name)}FromSequence")


@require(lambda type_anno: not _is_instance_type(type_anno))
def _content_reader_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """Name the function reading the content of an element as ``type_anno``."""
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation)
    ):
        return Identifier(f"read{_type_moniker(type_anno)}")

    return Identifier(f"readTextAs_{_leaf_moniker(type_anno)}")


@require(lambda v_name: v_name.startswith("v"))
@require(lambda type_anno: not _is_instance_type(type_anno))
def _at_v_reader_name(
    type_anno: intermediate.TypeAnnotationUnion, v_name: str
) -> Identifier:
    """Name the function reading ``type_anno`` from an element called ``v_name``."""
    return Identifier(f"readAtV{v_name[1:]}_{_type_moniker(type_anno)}")


def _element_reader_name(
    type_anno: intermediate.TypeAnnotationUnion, v_name: str
) -> Identifier:
    """
    Name the function reading a single element holding ``type_anno``.

    This is what a list item and a tuple item are read with. An instance reads
    its own, self-describing element, whereas everything else is wrapped in
    an element which the container names -- ``v`` in a list, ``v1``, ``v2``,
    ... by position in a tuple.
    """
    if _is_instance_type(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)
        return _from_element_name(type_anno.our_type)

    return _at_v_reader_name(type_anno, v_name)


# endregion

# region Gating


class _Needed:
    """Track which shared helpers and which readers the meta-model reaches."""

    def __init__(self) -> None:
        """Initialize with nothing needed."""
        self.primitive_types = set()  # type: Set[intermediate.PrimitiveType]
        self.enumerations = False
        self.lists = False
        self.nested_elements = False

        #: Content readers to emit, keyed and de-duplicated by the moniker
        self.content_readers = (
            dict()
        )  # type: MutableMapping[str, intermediate.TypeAnnotationUnion]

        #: Positional item readers to emit, keyed by their function name
        self.at_v_readers = (
            dict()
        )  # type: MutableMapping[str, Tuple[intermediate.TypeAnnotationUnion, str]]


def _collect_needed(symbol_table: intermediate.SymbolTable) -> _Needed:
    """
    Determine which shared helpers and which readers have to be generated.

    The pass recurses into the items of a list and of a tuple: an item is read
    by the same readers, only one nesting level deeper, and the reader it needs
    may occur nowhere else in the model. Without the recursion, a model whose
    only ``str`` sits in a ``List[List[str]]`` would emit a reader composed of
    helpers which were never generated.

    Only the properties of the concrete classes matter, as they are the only
    thing de-serialized as a sequence of XML elements.
    """
    needed = _Needed()

    def register_item(type_anno: intermediate.TypeAnnotationUnion, v_name: str) -> None:
        """Register the reader of a single element holding ``type_anno``."""
        if _is_instance_type(type_anno):
            # NOTE (mristin):
            # An instance reads its own, self-describing element, so it needs
            # neither a positional reader nor a content reader.
            return

        register_content(type_anno)

        name = _at_v_reader_name(type_anno, v_name)
        if name not in needed.at_v_readers:
            needed.at_v_readers[name] = (type_anno, v_name)

    @require(lambda type_anno: not _is_instance_type(type_anno))
    def register_content(type_anno: intermediate.TypeAnnotationUnion) -> None:
        """Register the reader of the content of an element as ``type_anno``."""
        moniker = _type_moniker(type_anno)
        if moniker in needed.content_readers:
            return

        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            needed.lists = True
            register_item(type_anno.items, "v")
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            for i, item_type_anno in enumerate(type_anno.items):
                register_item(item_type_anno, f"v{i + 1}")
        else:
            primitive_type = intermediate.try_primitive_type(type_anno)
            if primitive_type is not None:
                needed.primitive_types.add(primitive_type)
            else:
                assert isinstance(type_anno, intermediate.OurTypeAnnotation) and (
                    isinstance(type_anno.our_type, intermediate.Enumeration)
                ), f"Expected an enumeration, but got: {type_anno}"

                needed.enumerations = True

                # NOTE (mristin):
                # ``readEnum`` is built on the text path.
                needed.primitive_types.add(intermediate.PrimitiveType.STR)

        needed.content_readers[moniker] = type_anno

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if _is_instance_type(type_anno):
                assert isinstance(type_anno, intermediate.OurTypeAnnotation)
                if _is_dispatched(type_anno.our_type):
                    needed.nested_elements = True
                continue

            register_content(type_anno)

    return needed


# endregion

# region Shared helpers


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


_CONTENT_CONVERTER_BODY_BY_PRIMITIVE: Final[
    Mapping[intermediate.PrimitiveType, Stripped]
] = {
    intermediate.PrimitiveType.STR: Stripped(
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
}}"""
    ),
    intermediate.PrimitiveType.BOOL: Stripped(
        f"""\
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
}}"""
    ),
    intermediate.PrimitiveType.INT: Stripped(
        f"""\
private static Long readContentAsLong(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}return Long.valueOf(content.toString());
}}"""
    ),
    intermediate.PrimitiveType.FLOAT: Stripped(
        f"""\
private static Double readContentAsDouble(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}return Double.valueOf(content.toString());
}}"""
    ),
    intermediate.PrimitiveType.BYTEARRAY: Stripped(
        f"""\
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
    ),
}
assert all(
    primitive_type in _CONTENT_CONVERTER_BODY_BY_PRIMITIVE
    for primitive_type in intermediate.PrimitiveType
)


def _generate_content_converters(
    primitive_types: Set[intermediate.PrimitiveType],
) -> List[Stripped]:
    """Generate the functions converting the text content of an element."""
    return [
        _CONTENT_CONVERTER_BODY_BY_PRIMITIVE[primitive_type]
        for primitive_type in intermediate.PrimitiveType
        if primitive_type in primitive_types
    ]


def _generate_reader_interfaces() -> Stripped:
    """Generate the two shapes which every reader has."""
    return Stripped(
        f"""\
/**
 * Read the content of an element which has already been opened.
 *
 * <p>{{@code isEmpty}} tells whether that element was self-closing.
 */
@FunctionalInterface
private interface ContentReader<T> {{
{I}Reporting.Result<? extends T> read(XMLEventReader reader, boolean isEmpty);
}}

/**
 * Read a whole element, opening and closing it.
 */
@FunctionalInterface
private interface ElementReader<T> {{
{I}Reporting.Result<? extends T> read(XMLEventReader reader);
}}

/**
 * Convert the text content of an element which has already been opened.
 */
@FunctionalInterface
private interface ContentConverter<T> {{
{I}T convert(XMLEventReader reader) throws XMLStreamException;
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
private static Reporting.Result<String> peekElementName(XMLEventReader reader) {{
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

{I}return tryElementName(reader);
}}"""
    )


def _generate_consume_end_element() -> Stripped:
    """Generate the function to consume the end tag of an element."""
    return Stripped(
        f"""\
/**
 * Consume the end tag concluding the element called {{@code elementName}}.
 */
private static Reporting.Result<XMLEvent> consumeEndElement(
{I}XMLEventReader reader, String elementName) {{
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

{I}final Reporting.Result<String> tryEndElementName = tryElementName(reader);
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
{II}throw new Xmlization.DeserializeException("",
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
 * Read a whole element which is expected to be called {{@code name}}, and read
 * its content with {{@code readContent}}.
 *
 * <p>The name is data, not a type: an instance reads the XML name of its own
 * class, a list item reads {{@code "v"}} and a tuple item reads {{@code "v1"}},
 * {{@code "v2"}}, ... by position. One framer therefore serves them all.
 */
private static <T> Reporting.Result<? extends T> readNamedElement(
{I}XMLEventReader reader, String name, ContentReader<T> readContent) {{
{I}final Reporting.Result<String> tryElementName = peekElementName(reader);
{I}if (tryElementName.isError()) {{
{II}return Reporting.Result.failure(tryElementName.getError());
{I}}}

{I}if (!name.equals(tryElementName.getResult())) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML element " + name + ", but got an XML element " +
{III}tryElementName.getResult()));
{I}}}

{I}final boolean isEmpty = isEmptyElement(reader);

{I}final Reporting.Result<? extends T> result = readContent.read(reader, isEmpty);
{I}if (result.isError()) {{
{II}return result;
{I}}}

{I}final Reporting.Result<XMLEvent> endResult = consumeEndElement(reader, name);
{I}if (endResult.isError()) {{
{II}return Reporting.Result.failure(endResult.getError());
{I}}}

{I}return result;
}}"""
    )


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
private static <T> Reporting.Result<? extends T> readNestedElement(
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


def _generate_read_text(
    primitive_types: Set[intermediate.PrimitiveType],
) -> List[Stripped]:
    """Generate the readers of the text content of an element."""
    result = [
        Stripped(
            f"""\
/**
 * Read the text content of an element and convert it with
 * {{@code convert}}.
 *
 * <p>A self-closing element is an error, since there is no text to convert.
 */
private static <T> Reporting.Result<T> readText(
{I}XMLEventReader reader,
{I}boolean isEmpty,
{I}ContentConverter<T> convert,
{I}String typeName) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML content representing " + typeName +
{III}", but encountered a self-closing element"));
{I}}}

{I}if (currentEvent(reader).isEndDocument()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML content representing " + typeName +
{III}", but reached the end-of-file"));
{I}}}

{I}try {{
{II}return Reporting.Result.success(convert.convert(reader));
{I}}} catch (Exception exception) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"The XML content could not be de-serialized as " + typeName + ": " +
{III}exception.getMessage()));
{I}}}
}}"""
        )
    ]  # type: List[Stripped]

    if (
        intermediate.PrimitiveType.STR in primitive_types
        or intermediate.PrimitiveType.BYTEARRAY in primitive_types
    ):
        result.append(
            Stripped(
                f"""\
/**
 * Read the text content of an element and convert it with
 * {{@code convert}}, giving {{@code whenEmpty}} for a self-closing element.
 */
private static <T> Reporting.Result<T> readText(
{I}XMLEventReader reader,
{I}boolean isEmpty,
{I}ContentConverter<T> convert,
{I}String typeName,
{I}T whenEmpty) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.success(whenEmpty);
{I}}}

{I}return readText(reader, isEmpty, convert, typeName);
}}"""
            )
        )

    return result


def _generate_read_enum() -> Stripped:
    """Generate the reader of an enumeration literal."""
    return Stripped(
        f"""\
/**
 * Read the text content of an element and parse it as a literal of
 * the enumeration called {{@code enumName}}.
 */
private static <T> Reporting.Result<T> readEnum(
{I}XMLEventReader reader,
{I}boolean isEmpty,
{I}Function<String, Optional<T>> parseLiteral,
{I}String enumName) {{
{I}final Reporting.Result<String> tryText = readText(
{II}reader, isEmpty, _DeserializeImplementation::readContentAsString, enumName);
{I}if (tryText.isError()) {{
{II}return Reporting.Result.failure(tryText.getError());
{I}}}

{I}final Optional<T> literal = parseLiteral.apply(tryText.getResult());
{I}if (!literal.isPresent()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"The text could not be parsed as a literal of " + enumName + ": " +
{III}tryText.getResult()));
{I}}}

{I}return Reporting.Result.success(literal.get());
}}"""
    )


def _generate_read_list() -> Stripped:
    """Generate the reader of the items of a list."""
    return Stripped(
        f"""\
/**
 * Read the items of a list, each with {{@code readItem}}.
 *
 * <p>Every start element is considered to mark the start of an item. Reading
 * stops as soon as a non-start element is encountered.
 */
private static <T> Reporting.Result<List<T>> readList(
{I}XMLEventReader reader, boolean isEmpty, ElementReader<T> readItem) {{
{I}final List<T> result = new ArrayList<>();
{I}if (isEmpty) {{
{II}return Reporting.Result.success(result);
{I}}}

{I}skipWhitespaceAndComments(reader);
{I}int index = 0;
{I}if (!currentEvent(reader).isStartElement()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a start element opening an item of the list, " +
{III}"but got an XML " + getEventTypeAsString(currentEvent(reader)));
{II}error.prependSegment(new Reporting.IndexSegment(index));
{II}return Reporting.Result.failure(error);
{I}}}

{I}while (currentEvent(reader).isStartElement()) {{
{II}final Reporting.Result<? extends T> itemResult = readItem.read(reader);
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


@require(lambda arity: arity > 0)
def _generate_read_tuple_helper(arity: int) -> Stripped:
    """Generate the reader of the items of a tuple of ``arity`` items."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    tuple_type = f"Tuple{arity}<{', '.join(type_params)}>"

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Read a tuple of {arity} item(s), each with the corresponding
 * {{@code readItemI}}.
 */
private static <{", ".join(type_params)}> Reporting.Result<{tuple_type}> readTuple{arity}(
{I}XMLEventReader reader,
{I}boolean isEmpty,
"""
    )

    for i in range(arity):
        writer.write(f"{I}ElementReader<T{i + 1}> readItem{i + 1}")
        writer.write(",\n" if i < arity - 1 else ") {\n")

    writer.write(
        f"""\
{I}if (isEmpty) {{
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
{II}readItem{i + 1}.read(reader);
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


def _generate_at_end_of_sequence() -> Stripped:
    """Generate the predicate telling whether the sequence of properties ended."""
    return Stripped(
        f"""\
/**
 * Check whether the sequence of the properties has ended.
 *
 * <p>Only the end tag of the enclosing element concludes a sequence. Reaching
 * the end-of-file does not -- that is an error, which
 * {{@link #peekElementName}} reports when the caller goes on to read the next
 * property.
 */
private static boolean atEndOfSequence(XMLEventReader reader) {{
{I}skipWhitespaceAndComments(reader);
{I}return currentEvent(reader).isEndElement();
}}"""
    )


def _generate_unexpected_property() -> Stripped:
    """Generate the error for a property which the class does not have."""
    return Stripped(
        f"""\
/**
 * Report an element which is not a property of the class {{@code className}}.
 */
private static <T> Reporting.Result<T> unexpectedProperty(
{I}String className, String elementName) {{
{I}return Reporting.Result.failure(new Reporting.Error(
{II}"We expected properties of the class " + className + ", " +
{II}"but got an unexpected element " +
{II}"with the name " + elementName));
}}"""
    )


def _generate_missing_required_property() -> Stripped:
    """Generate the error for a required property which the sequence omitted."""
    return Stripped(
        f"""\
/**
 * Report a required property of the class {{@code className}} which the
 * sequence of the properties did not give.
 */
private static <T> Reporting.Result<T> missingRequiredProperty(
{I}String propertyName, String className) {{
{I}return Reporting.Result.failure(new Reporting.Error(
{II}"The required property " + propertyName + " has not been given " +
{II}"in the XML representation of an instance of class " + className));
}}"""
    )


# endregion

# region Readers of a single type


def _concrete_from_element_name(cls: intermediate.ConcreteClass) -> Identifier:
    """
    Name the function reading a whole element of the concrete class ``cls``.

    Unlike :py:func:`_from_element_name`, this never dispatches: it is what
    a dispatcher dispatches *to*, so a concrete class which itself has
    descendants must resolve to its own reader here and not back to
    the dispatcher.
    """
    return Identifier(f"read{java_naming.class_name(cls.name)}FromElement")


@require(lambda type_anno: not _is_instance_type(type_anno))
def _generate_content_reader(type_anno: intermediate.TypeAnnotationUnion) -> Stripped:
    """Generate the function reading the content of an element as ``type_anno``."""
    name = _content_reader_name(type_anno)
    value_type = java_common.generate_type(type_anno)

    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_reader = _element_reader_name(type_anno.items, "v")
        body = Stripped(
            f"""\
return readList(
{I}reader, isEmpty, _DeserializeImplementation::{item_reader});"""
        )
    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_readers = ",\n".join(
            f"_DeserializeImplementation::"
            f"{_element_reader_name(item_type_anno, f'v{i + 1}')}"
            for i, item_type_anno in enumerate(type_anno.items)
        )
        body = Stripped(
            f"""\
return readTuple{len(type_anno.items)}(
{I}reader,
{I}isEmpty,
{I}{indent_but_first_line(item_readers, I)});"""
        )
    else:
        primitive_type = intermediate.try_primitive_type(type_anno)
        if primitive_type is not None:
            converter, display_name = _CONTENT_CONVERTER_BY_PRIMITIVE[primitive_type]
            display_name_literal = java_common.string_literal(display_name)
            empty_value = _EMPTY_VALUE_BY_PRIMITIVE.get(primitive_type, None)

            arguments = [
                Stripped("reader"),
                Stripped("isEmpty"),
                Stripped(f"_DeserializeImplementation::{converter}"),
                Stripped(display_name_literal),
            ]
            if empty_value is not None:
                arguments.append(Stripped(empty_value))

            joined_arguments = ",\n".join(arguments)
            body = Stripped(
                f"""\
return readText(
{I}{indent_but_first_line(joined_arguments, I)});"""
            )
        else:
            assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
                type_anno.our_type, intermediate.Enumeration
            ), f"Expected an enumeration, but got: {type_anno}"

            enum_name = java_naming.enum_name(type_anno.our_type.name)
            from_str_name = java_naming.private_property_name(
                Identifier(f"{type_anno.our_type.name}_from_string")
            )
            enum_name_literal = java_common.string_literal(enum_name)

            body = Stripped(
                f"""\
return readEnum(
{I}reader,
{I}isEmpty,
{I}Stringification::{from_str_name},
{I}{enum_name_literal});"""
            )

    return Stripped(
        f"""\
private static Reporting.Result<{value_type}> {name}(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


@require(lambda type_anno: not _is_instance_type(type_anno))
def _generate_at_v_reader(
    type_anno: intermediate.TypeAnnotationUnion, v_name: str
) -> Stripped:
    """Generate the function reading ``type_anno`` from a ``v``-element."""
    name = _at_v_reader_name(type_anno, v_name)
    value_type = java_common.generate_type(type_anno)
    v_name_literal = java_common.string_literal(v_name)
    content_reader = _content_reader_name(type_anno)

    return Stripped(
        f"""\
private static Reporting.Result<? extends {value_type}> {name}(
{I}XMLEventReader reader) {{
{I}return readNamedElement(
{II}reader,
{II}{v_name_literal},
{II}_DeserializeImplementation::{content_reader});
}}"""
    )


# endregion

# region De-serialization of a class


@require(lambda prop, cls: id(prop) in cls.property_id_set)
def _generate_deserialize_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the snippet to deserialize the property ``prop`` from the content."""
    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    result_type: str
    read_expr: Stripped

    if _is_instance_type(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)
        our_type = type_anno.our_type

        if _is_dispatched(our_type):
            result_type = f"? extends {java_common.generate_type(type_anno)}"
            read_expr = Stripped(
                f"""\
readNestedElement(
{I}reader,
{I}isEmptyProperty,
{I}_DeserializeImplementation::{_from_element_name(our_type)})"""
            )
        else:
            assert isinstance(our_type, intermediate.ConcreteClass), (
                f"Expected a concrete class without any descendant, "
                f"but got: {our_type}"
            )
            result_type = java_naming.class_name(our_type.name)
            read_expr = Stripped(
                f"{_from_sequence_name(our_type)}(reader, isEmptyProperty)"
            )
    else:
        result_type = java_common.generate_type(type_anno)
        read_expr = Stripped(
            f"{_content_reader_name(type_anno)}(reader, isEmptyProperty)"
        )

    return Stripped(
        f"""\
final Reporting.Result<{result_type}> value =
{I}{indent_but_first_line(read_expr, I)};
if (value.isError()) {{
{I}valueError = value.getError();
}} else {{
{I}{target_var} = value.getResult();
}}"""
    )


def _generate_deserialize_impl_cls_from_sequence(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the function to de-serialize the ``cls`` from an XML sequence."""
    name = java_naming.class_name(identifier=cls.name)
    function_name = _from_sequence_name(cls)

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
private static Reporting.Result<{name}> {function_name}(
{I}XMLEventReader reader,
{I}boolean isEmptySequence) {{
{I}return Reporting.Result.success(new {name}());
}}"""
            ),
            None,
        )

    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    init_target_var_stmts = []  # type: List[Stripped]
    for prop in cls.properties:
        target_type = java_common.generate_type(
            intermediate.beneath_optional(prop.type_annotation)
        )
        target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

        init_target_var_stmts.append(Stripped(f"{target_type} {target_var} = null;"))
    blocks.append(Stripped("\n".join(init_target_var_stmts)))

    case_blocks = []  # type: List[Stripped]
    for prop in cls.properties:
        case_body = _generate_deserialize_property(prop=prop, cls=cls)

        xml_prop_name_literal = java_common.string_literal(prop.xml_name)
        case_blocks.append(
            Stripped(
                f"""\
case {xml_prop_name_literal}: {{
{I}{indent_but_first_line(case_body, I)}
{I}break;
}}"""
            )
        )

    class_name_literal = java_common.string_literal(name)

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}return unexpectedProperty({class_name_literal}, elementName);"""
        )
    )

    switch_body = "\n".join(case_blocks)

    # NOTE (mristin):
    # Every property is read in this very loop, so we mark the error with
    # the property's own element name here, once, instead of at every single
    # case above. For a matched case, ``elementName`` *is* that name.
    blocks.append(
        Stripped(
            f"""\
if (!isEmptySequence) {{
{I}while (!atEndOfSequence(reader)) {{
{II}final Reporting.Result<String> tryElementName = peekElementName(reader);
{II}if (tryElementName.isError()) {{
{III}return Reporting.Result.failure(tryElementName.getError());
{II}}}

{II}final String elementName = tryElementName.getResult();
{II}final boolean isEmptyProperty = isEmptyElement(reader);

{II}Reporting.Error valueError = null;

{II}switch (elementName) {{
{III}{indent_but_first_line(switch_body, III)}
{II}}}

{II}if (valueError != null) {{
{III}valueError.prependSegment(
{IIII}new Reporting.NameSegment(
{IIIII}elementName));
{III}return Reporting.Result.failure(valueError);
{II}}}

{II}final Reporting.Result<XMLEvent> endResult = consumeEndElement(reader, elementName);
{II}if (endResult.isError()) {{
{III}return Reporting.Result.failure(endResult.getError());
{II}}}
{I}}}
}}"""
        )
    )

    # region Check that the mandatory properties have been set

    for prop in cls.properties:
        prop_java = java_naming.property_name(prop.name)
        target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            prop_java_literal = java_common.string_literal(prop_java)

            blocks.append(
                Stripped(
                    f"""\
if ({target_var} == null) {{
{I}return missingRequiredProperty({prop_java_literal}, {class_name_literal});
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
private static Reporting.Result<{name}> {function_name}(
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
    xml_name_literal = java_common.string_literal(naming.xml_class_name(cls.name))

    return Stripped(
        f"""\
/**
 * Deserialize an instance of class {name} from an XML element.
 */
private static Reporting.Result<? extends {name}> {_concrete_from_element_name(cls)}(
{I}XMLEventReader reader) {{
{I}return readNamedElement(
{II}reader,
{II}{xml_name_literal},
{II}_DeserializeImplementation::{_from_sequence_name(cls)});
}}"""
    )


def _generate_dispatch_from_element(
    function_name: Identifier,
    value_type: str,
    description: Stripped,
    case_blocks: List[Stripped],
) -> Stripped:
    """Generate a dispatcher on the element's own name."""
    case_blocks = list(case_blocks)
    case_blocks.append(
        Stripped(
            f"""\
default:
{I}return Reporting.Result.failure(new Reporting.Error(
{II}"Unexpected element with the name " + tryElementName.getResult()));"""
        )
    )

    joined_case_blocks = "\n".join(case_blocks)

    return Stripped(
        f"""\
{description}
private static Reporting.Result<? extends {value_type}> {function_name}(
{I}XMLEventReader reader) {{
{I}// NOTE (mristin):
{I}// We only peek the name, so that the whole element can be handed on to
{I}// the reader which we select below.
{I}final Reporting.Result<String> tryElementName = peekElementName(reader);
{I}if (tryElementName.isError()) {{
{II}return Reporting.Result.failure(tryElementName.getError());
{I}}}

{I}switch (tryElementName.getResult()) {{
{II}{indent_but_first_line(joined_case_blocks, II)}
{I}}}
}}"""
    )


def _generate_deserialize_impl_interface_from_element(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate the function to de-serialize an ``interface`` from an XML element."""
    name = java_naming.interface_name(interface.name)

    case_blocks = []  # type: List[Stripped]
    for implementer in interface.implementers:
        implementer_xml_name_literal = java_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        case_blocks.append(
            Stripped(
                f"""\
case {implementer_xml_name_literal}:
{I}return {_concrete_from_element_name(implementer)}(reader);"""
            )
        )

    return _generate_dispatch_from_element(
        function_name=Identifier(f"read{name}FromElement"),
        value_type=name,
        description=Stripped(
            f"""\
/**
 * Deserialize an instance of {name} from an XML element.
 */"""
        ),
        case_blocks=case_blocks,
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

    case_blocks = []  # type: List[Stripped]
    for implementer in named_union.implementers:
        implementer_xml_name_literal = java_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        implementer_name = java_naming.class_name(implementer.name)

        case_blocks.append(
            Stripped(
                f"""\
case {implementer_xml_name_literal}: {{
{I}final Reporting.Result<? extends {implementer_name}> result =
{II}{_concrete_from_element_name(implementer)}(reader);
{I}if (result.isError()) {{
{II}return Reporting.Result.failure(result.getError());
{I}}}
{I}return Reporting.Result.success({name}.from{implementer_name}(result.getResult()));
}}"""
            )
        )

    return _generate_dispatch_from_element(
        function_name=Identifier(f"read{name}FromElement"),
        value_type=name,
        description=Stripped(
            f"""\
/**
 * Deserialize an instance of {name} from an XML element.
 */"""
        ),
        case_blocks=case_blocks,
    )


# endregion


def _generate_deserialize_impl(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the implementation for deserialization functions."""
    needed = _collect_needed(symbol_table)

    blocks = [
        _generate_current_event(),
        _generate_get_event_type_as_string(),
        _generate_is_empty_element(),
        _generate_skip_whitespace_and_comments(),
        _generate_skip_start_document(),
        _generate_try_element_name(),
        _generate_reader_interfaces(),
        _generate_peek_element_name(),
        _generate_consume_end_element(),
        _generate_read_named_element(),
    ]  # type: List[Stripped]

    if needed.nested_elements:
        blocks.append(_generate_read_nested_element())

    blocks.extend(_generate_content_converters(needed.primitive_types))

    if len(needed.primitive_types) > 0:
        blocks.extend(_generate_read_text(needed.primitive_types))

    if needed.enumerations:
        blocks.append(_generate_read_enum())

    if needed.lists:
        blocks.append(_generate_read_list())

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_read_tuple_helper(arity=arity))

    if any(len(cls.constructor.arguments) > 0 for cls in symbol_table.concrete_classes):
        blocks.append(_generate_at_end_of_sequence())
        blocks.append(_generate_unexpected_property())

    if any(
        not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.append(_generate_missing_required_property())

    for type_anno in needed.content_readers.values():
        blocks.append(_generate_content_reader(type_anno))

    for type_anno, v_name in needed.at_v_readers.values():
        blocks.append(_generate_at_v_reader(type_anno, v_name))

    errors = []  # type: List[Error]

    # NOTE (empwilli):
    # Enumerations are going to be directly deserialized using
    # ``Stringification``.

    # NOTE (empwilli):
    # Constrained primitives are only verified, but do not represent a Java type.

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.ConcreteClass):
            if cls.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Xmlization/DeserializeImplementation/"
                    f"{cls.name}_from_sequence.java"
                )

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
                else:
                    blocks.append(implementation)
            else:
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
            blocks.append(_generate_deserialize_impl_concrete_cls_from_element(cls=cls))

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
{II}_DeserializeImplementation.read{name}FromElement(
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
