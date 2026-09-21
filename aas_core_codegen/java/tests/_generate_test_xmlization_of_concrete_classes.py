"""Generate code to test the XML de/serialization of concrete classes."""

from typing import Dict, List, Mapping, Tuple

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Identifier, Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
    INDENT7 as IIIIIII,
    INDENT8 as IIIIIIII,
    INDENT9 as IIIIIIIII,
    INDENT10 as IIIIIIIIII,
)


#: The lexical forms which no recorded example can hold, by the primitive
#: they belong to.
#:
#: A recorded example under ``Xml/Expected`` has to serialize back to itself,
#: character for character, so it can hold neither a value written in another
#: form than it was read -- ``1`` for a boolean comes back as ``true`` -- nor
#: one whose written form the targets spell differently, which is the case for
#: every interesting double. Both are asserted here on the *value*, and no
#: text is ever compared.
_LEXICAL_CASES_BY_PRIMITIVE = {
    intermediate.PrimitiveType.FLOAT: [
        # NOTE (mristin):
        # A literal too large for a double is not an error: XSD rounds it to
        # an infinity, and one too small to zero.
        #
        # See: https://www.w3.org/TR/xmlschema11-2/#double
        ("1e400", "Double.POSITIVE_INFINITY"),
        ("-1e400", "Double.NEGATIVE_INFINITY"),
        ("1e-400", "0.0"),
        ("INF", "Double.POSITIVE_INFINITY"),
        ("+INF", "Double.POSITIVE_INFINITY"),
        ("-INF", "Double.NEGATIVE_INFINITY"),
    ],
    intermediate.PrimitiveType.BYTEARRAY: [
        # NOTE (mristin):
        # ``xs:base64Binary`` admits whitespace *between* the characters and
        # not only around them, and an empty value stands for zero bytes.
        # Neither can be a recorded example: the first is written back without
        # the space, and the second as an empty element.
        #
        # See: https://www.w3.org/TR/xmlschema-2/#base64Binary
        ("SGk=", "new byte[] {72, 105}"),
        ("SG k=", "new byte[] {72, 105}"),
        ("S G k =", "new byte[] {72, 105}"),
        ("", "new byte[] {}"),
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
        return "Empty"

    mapping = {
        "+": "Plus",
        "-": "Minus",
        ".": "Point",
        " ": "Space",
        "=": "Pad",
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

    cls_name_java = java_naming.class_name(cls.name)
    cls_name_xml = naming.xml_class_name(cls.name)

    result = [
        Stripped(
            f"""\
/**
 * Read the first recorded example of {cls_name_java} with the content of
 * the element {{@code xmlName}} replaced by {{@code text}}.
 */
private static {cls_name_java} readWith(String xmlName, String text)
{I}throws IOException, XMLStreamException {{
{I}final Path searchPath =
{II}Paths.get(Common.TEST_DATA_DIR, "Xml", "Expected", {java_common.string_literal(cls_name_xml)});
{I}final List<Path> paths = Common.findPaths(searchPath, ".xml");

{I}if (paths.isEmpty()) {{
{II}fail(
{III}"Expected at least one recorded example of {cls_name_xml}, but got none");
{I}}}

{I}final String original =
{II}new String(Files.readAllBytes(paths.get(0)), StandardCharsets.UTF_8);

{I}final int start = original.indexOf("<" + xmlName + ">") + xmlName.length() + 2;
{I}final int end = original.indexOf("</" + xmlName + ">");

{I}final String patched =
{II}original.substring(0, start) + text + original.substring(end);

{I}final XMLInputFactory xmlInputFactory = XMLInputFactory.newInstance();
{I}final XMLEventReader xmlReader =
{II}xmlInputFactory.createXMLEventReader(new StringReader(patched));

{I}return Xmlization.Deserialize.deserialize{cls_name_java}(xmlReader);
}}"""
        )
    ]  # type: List[Stripped]

    for a_type, prop in relevant:
        prop_xml_name = naming.xml_property(prop.name)
        getter_name = java_naming.getter_name(prop.name)

        for text, expected in _LEXICAL_CASES_BY_PRIMITIVE[a_type]:
            # NOTE (mristin):
            # A byte array is compared element by element, and not by
            # its identity, which is what assertEquals would do.
            assertion = (
                f"assertArrayEquals(\n{II}{expected},\n{II}instance.{getter_name}())"
                if a_type is intermediate.PrimitiveType.BYTEARRAY
                else f"assertEquals(\n{II}{expected},\n{II}instance.{getter_name}())"
            )

            test_name = java_naming.method_name(
                Identifier(
                    f"test_{prop.name}_read_from_" f"{_lexical_test_name_chunk(text)}"
                )
            )

            result.append(
                Stripped(
                    f"""\
@Test
public void {test_name}() throws IOException, XMLStreamException {{
{I}final {cls_name_java} instance =
{II}readWith({java_common.string_literal(prop_xml_name)}, {java_common.string_literal(text)});

{I}{assertion};
}} // public void {test_name}"""
                )
            )

    return result


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the XML de/serialization of concrete classes.
    """
    # NOTE (mristin):
    # The elements of the XML-RPC subset, over which a JSON-able value is
    # de/serialized, reside in no namespace at all, unlike everything which
    # the meta-model itself prescribes. ``EVENT`` stands for the start or
    # the end element which the condition is checked on.
    namespace_condition = (
        Stripped(
            f"""\
Xmlization.AAS_NAME_SPACE.equals(EVENT.getName().getNamespaceURI())
{I}|| EVENT.getName().getNamespaceURI().isEmpty()"""
        )
        if intermediate.uses_json_types(symbol_table)
        else Stripped(
            "Xmlization.AAS_NAME_SPACE.equals(EVENT.getName().getNamespaceURI())"
        )
    )

    blocks = [
        Stripped(
            f"""\
public static Optional<Reporting.Error> checkElementsEqual(
{I}XMLEvent expected, String expectedContent, Map<XMLEvent, String> outputMap) {{
{I}switch (expected.getEventType()) {{
{II}case XMLStreamConstants.START_ELEMENT:
{III}{{
{IIII}final String expectedName = expected.asStartElement().getName().getLocalPart();
{IIII}final Optional<Map.Entry<XMLEvent, String>> got =
{IIIII}outputMap.entrySet().stream()
{IIIIII}.filter(
{IIIIIII}entry ->
{IIIIIIII}entry.getKey().isStartElement()
{IIIIIIIII}&& entry
{IIIIIIIIII}.getKey()
{IIIIIIIIII}.asStartElement()
{IIIIIIIIII}.getName()
{IIIIIIIIII}.getLocalPart()
{IIIIIIIIII}.equals(expectedName))
{IIIIII}.filter(entry -> entry.getValue().equals(expectedContent))
{IIIIIII}.findAny();
{IIII}if (!got.isPresent()) {{
{IIIII}final Reporting.Error error =
{IIIIII}new Reporting.Error(
{IIIIIII}"Missing start element "
{IIIIIIII}+ expectedName
{IIIIIIII}+ " in with content: "
{IIIIIIII}+ expectedContent);
{IIIII}return Optional.of(error);
{IIII}}}
{IIII}outputMap.remove(got.get().getKey());
{IIII}return Optional.empty();
{III}}}
{II}case XMLStreamConstants.END_ELEMENT:
{III}{{
{IIII}final String expectedName = expected.asEndElement().getName().getLocalPart();
{IIII}final Optional<Map.Entry<XMLEvent, String>> got =
{IIIII}outputMap.entrySet().stream()
{IIIIII}.filter(
{IIIIIII}entry ->
{IIIIIIII}entry.getKey().isEndElement()
{IIIIIIIII}&& entry
{IIIIIIIIII}.getKey()
{IIIIIIIIII}.asEndElement()
{IIIIIIIIII}.getName()
{IIIIIIIIII}.getLocalPart()
{IIIIIIIIII}.equals(expectedName))
{IIIIII}.findAny();
{IIII}if (!got.isPresent()) {{
{IIIII}final Reporting.Error error =
{IIIIII}new Reporting.Error("Missing end element " + expectedName);
{IIIII}return Optional.of(error);
{IIII}}}
{IIII}outputMap.remove(got.get().getKey());
{IIII}return Optional.empty();
{III}}}
{II}default:
{III}{{
{IIII}throw new IllegalStateException("Unexpected event type in check elements equal.");
{III}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
private static String readContent(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();
{I}while (reader.hasNext() && reader.peek().isCharacters()
{III}&& !reader.peek().asCharacters().isWhiteSpace()
{III}|| reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{

{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}
{I}return content.toString();
}}"""
        ),
        Stripped(
            f"""\
private static Map<XMLEvent, String> buildElementsMap(XMLEventReader reader) throws XMLStreamException {{
{I}final Map<XMLEvent, String> result = new LinkedHashMap<>();
{I}while (reader.hasNext()) {{
{II}final XMLEvent current = reader.nextEvent();
{II}if (current.isStartElement()) {{
{III}result.put(current, readContent(reader));
{II}}} else if (current.isEndElement()) {{
{III}result.put(current, "");
{II}}}
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
private static void assertSerializeDeserializeEqualsOriginal(IClass instance, Path path)
{I}throws XMLStreamException, IOException {{
{I}// Serialize
{I}final StringWriter stringOut = new StringWriter();
{I}final XMLOutputFactory outputFactory = XMLOutputFactory.newFactory();
{I}final XMLStreamWriter xmlStreamWriter = outputFactory.createXMLStreamWriter(stringOut);

{I}Xmlization.Serialize.to(instance, xmlStreamWriter);

{I}final String outputText = stringOut.toString();

// Compare expected == output
final XMLInputFactory xmlInputFactory = XMLInputFactory.newInstance();
final XMLEventReader outputReader =
{I}xmlInputFactory.createXMLEventReader(new StringReader(outputText));
final Map<XMLEvent, String> outputMap = buildElementsMap(outputReader);

// check output for aas-name-space
for (XMLEvent event : outputMap.keySet()) {{
{I}if (event.isStartElement()) {{
{II}assertTrue(
{III}{indent_but_first_line(namespace_condition.replace("EVENT", "event.asStartElement()"), III)},
{III}"Unexpected namespace of " + event.asStartElement().getName());
{I}}}
{I}if (event.isEndElement()) {{
{II}assertTrue(
{III}{indent_but_first_line(namespace_condition.replace("EVENT", "event.asEndElement()"), III)},
{III}"Unexpected namespace of " + event.asEndElement().getName());
{I}}}
}}

final XMLEventReader expectedReader =
{I}xmlInputFactory.createXMLEventReader(Files.newInputStream(path));
final Map<XMLEvent, String> expectedMap = buildElementsMap(expectedReader);

if (expectedMap.size() != outputMap.size()) {{
{I}fail(
{II}"Mismatch in element size expected "
{III}+ expectedMap.size()
{III}+ " but got "
{III}+ outputMap.size());
}}

expectedMap.forEach(
{I}(xmlEvent, content) -> {{
{II}final Optional<Reporting.Error> inequalityError =
{IIII}checkElementsEqual(xmlEvent, content, outputMap);
{II}inequalityError.ifPresent(
{III}error ->
{IIII}fail(
{IIIII}"The original XML from "
{IIIIII} + path
{IIIIII} + " is unequal the serialized XML: "
{IIIIII} + error.getCause()));
{I}}});
}}"""
        ),
        Stripped(
            f"""\
private static void assertEqualsExpectedOrRerecordDeserializationException(
{I}Xmlization.DeserializeException exception,
{I}Path path) throws IOException {{
{I}if (exception == null) {{
{II}fail("Expected a Xmlization exception when de-serializing " + path + ", but got none.");
{I}}} else {{
{II}final Path exceptionPath = Paths.get(path + ".exception");
{II}final String got = exception.getMessage();
{II}if (Common.RECORD_MODE) {{
{III}Files.write(exceptionPath, got.getBytes(StandardCharsets.UTF_8));
{II}}} else {{
{III}if (!Files.exists(exceptionPath)) {{
{IIII}throw new FileNotFoundException(
{IIIII}"The file with the recorded exception does not exist: "
{IIIII}+ exceptionPath
{IIIII}+ "; maybe you want to set the environment variable"
{IIIII}+ Common.RECORD_MODE_ENVIRONMENT_VARIABLE_NAME
{IIIII}+ "?");
{III}}}

{III}final String expected = String.join("\\n", Files.readAllLines(exceptionPath));
{III}assertEquals(
{IIII}expected.replace("\\n", ""),
{IIII}got.replace("\\n", ""),
{IIII}"The expected exception does not match the actual one for the file " + path);
{II}}}
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_java = java_naming.class_name(concrete_cls.name)
        cls_name_xml = naming.xml_class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name_java}Ok() throws IOException, XMLStreamException {{
{I}final Path searchPath =
{II}Paths.get(Common.TEST_DATA_DIR, "Xml", "Expected", {java_common.string_literal(cls_name_xml)});
{I}final List<Path> paths = Common.findPaths(searchPath, ".xml");

{I}for (Path path : paths) {{
{II}final XMLInputFactory xmlInputFactory = XMLInputFactory.newInstance();
{II}final XMLEventReader xmlReader =
{III}xmlInputFactory.createXMLEventReader(Files.newInputStream(path));

{II}final {cls_name_java} instance =
{III}Xmlization.Deserialize.deserialize{cls_name_java}(xmlReader);

{II}final Iterable<Reporting.Error> errorIter = Verification.verify(instance);
{II}final List<Reporting.Error> errors = Common.asList(errorIter);
{II}Common.assertNoVerificationErrors(errors, path);

{II}assertSerializeDeserializeEqualsOriginal(instance, path);
{I}}}
}} // public void test{cls_name_java}Ok"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name_java}DeserializationFail() throws IOException, XMLStreamException {{
{I}for (
{II}Path causeDir :
{II}Common.findDirs(
{III}Paths.get(
{IIII}Common.TEST_DATA_DIR,
{IIII}"Xml",
{IIII}"Unexpected",
{IIII}"Unserializable"))) {{
{II}final Path clsDir =
{III}causeDir.resolve({java_common.string_literal(cls_name_xml)});

{II}if (!Files.exists(clsDir)) {{
{III}// No examples of {cls_name_java} for the failure cause.
{III}continue;
{II}}}

{II}final List<Path> paths = Common.findPaths(clsDir, ".xml");
{II}for (Path path : paths) {{
{III}final XMLInputFactory xmlInputFactory = XMLInputFactory.newInstance();
{III}final XMLEventReader xmlReader =
{IIII}xmlInputFactory.createXMLEventReader(Files.newInputStream(path));

{III}Xmlization.DeserializeException exception = null;

{III}try {{
{IIII}Xmlization.Deserialize.deserialize{cls_name_java}(xmlReader);
{III}}} catch (Xmlization.DeserializeException observedException) {{
{IIII}exception = observedException;
{III}}}

{III}assertEqualsExpectedOrRerecordDeserializationException(exception, path);
{II}}}
{I}}}
}}  // public void test{cls_name_java}DeserializationFail"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name_java}VerificationFail() throws IOException, XMLStreamException {{
{I}for (
{II}Path causeDir :
{II}Common.findDirs(
{III}Paths.get(
{IIII}Common.TEST_DATA_DIR,
{IIII}"Xml",
{IIII}"Unexpected",
{IIII}"Invalid"))) {{
{II}final Path clsDir = causeDir.resolve(
{III}{java_common.string_literal(cls_name_xml)});

{II}if (!Files.exists(clsDir)) {{
{III}// No examples of {cls_name_java} for the failure cause.
{III}continue;
{II}}}

{II}final List<Path> paths = Common.findPaths(clsDir, ".xml");
{II}for (Path path : paths) {{
{III}final XMLInputFactory xmlInputFactory = XMLInputFactory.newInstance();
{III}final XMLEventReader xmlReader =
{IIII}xmlInputFactory.createXMLEventReader(Files.newInputStream(path));

{III}final {cls_name_java} instance =
{IIII}Xmlization.Deserialize.deserialize{cls_name_java}(xmlReader);

{III}final Iterable<Reporting.Error> errorIter = Verification.verify(instance);
{III}final List<Reporting.Error> errors = Common.asList(errorIter);
{III}Common.assertEqualsExpectedOrRerecordVerificationErrors(errors, path);
{II}}}
{I}}}
}} // public void test{cls_name_java}VerificationFail"""
            )
        )

    duplicate_candidate = intermediate.first_class_with_a_required_property(
        symbol_table
    )
    if duplicate_candidate is not None:
        duplicate_cls, duplicate_prop = duplicate_candidate

        duplicate_cls_name_java = java_naming.class_name(duplicate_cls.name)
        duplicate_cls_name_xml = naming.xml_class_name(duplicate_cls.name)

        open_tag = f"<{duplicate_prop.xml_name}>"
        close_tag = f"</{duplicate_prop.xml_name}>"
        self_closing_tag = f"<{duplicate_prop.xml_name}/>"
        root_close_tag = f"</{duplicate_cls_name_xml}>"

        blocks.append(
            Stripped(
                f"""\
@Test
public void testDuplicatePropertyFails() throws IOException, XMLStreamException {{
{I}final Path path =
{II}Paths.get(
{III}Common.TEST_DATA_DIR,
{III}"Xml",
{III}"Expected",
{III}{java_common.string_literal(duplicate_cls_name_xml)},
{III}"minimal.xml");

{I}final String text =
{II}new String(Files.readAllBytes(path), StandardCharsets.UTF_8);

{I}// We cut the element of the property out of the recorded example and put it
{I}// in a second time, just before the closing tag of the instance.
{I}final int start = text.indexOf({java_common.string_literal(open_tag)});

{I}final String property;
{I}if (start >= 0) {{
{II}final int end = text.indexOf({java_common.string_literal(close_tag)}, start);
{II}property = text.substring(start, end + {len(close_tag)});
{I}}} else {{
{II}// The element is written self-closing in the example, an empty list being
{II}// the usual reason. We write that very element out ourselves.
{II}property = {java_common.string_literal(self_closing_tag)};
{I}}}

{I}final int insertionIndex =
{II}text.lastIndexOf({java_common.string_literal(root_close_tag)});

{I}if (insertionIndex < 0) {{
{II}throw new IllegalStateException(
{III}"We expect the recorded example to contain the closing tag "
{IIII}+ {java_common.string_literal(root_close_tag)} + ", but it does not: " + path);
{I}}}

{I}final String brokenText =
{II}text.substring(0, insertionIndex) + property + text.substring(insertionIndex);

{I}final XMLInputFactory xmlInputFactory = XMLInputFactory.newInstance();
{I}final XMLEventReader xmlReader =
{II}xmlInputFactory.createXMLEventReader(new StringReader(brokenText));

{I}Xmlization.DeserializeException exception = null;

{I}try {{
{II}Xmlization.Deserialize.deserialize{duplicate_cls_name_java}(xmlReader);
{I}}} catch (Xmlization.DeserializeException observedException) {{
{II}exception = observedException;
{I}}}

{I}if (exception == null) {{
{II}fail(
{III}"Expected an exception when the property "
{IIII}+ {java_common.string_literal(duplicate_prop.xml_name)}
{IIII}+ " is given twice, but got none");
{I}}}
}} // public void testDuplicatePropertyFails"""
            )
        )

    blocks.extend(_generate_lexical_tests(symbol_table))

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestXmlizationOfConcreteClasses.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

import {package}.reporting.Reporting;
import {package}.types.impl.*;
import {package}.types.model.IClass;
import {package}.verification.Verification;
import {package}.xmlization.Xmlization;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import javax.xml.stream.*;
import javax.xml.stream.events.XMLEvent;
import org.junit.jupiter.api.Test;

public class TestXmlizationOfConcreteClasses {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestXmlizationOfConcreteClasses

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
