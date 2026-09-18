"""Generate code to test the XML de/serialization of concrete classes."""

import io
from typing import Dict, List, Mapping, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    Identifier,
)
from aas_core_codegen.golang import common as golang_common, naming as golang_naming
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_for_cls(cls: intermediate.ConcreteClass) -> List[Stripped]:
    """Generate the tests for a self-contained class."""
    xml_class_name_literal = golang_common.string_literal(
        naming.xml_class_name(cls.name)
    )

    unmarshal_function = golang_naming.function_name(Identifier("unmarshal"))

    blocks = []  # type: List[Stripped]

    interface_name = golang_naming.interface_name(cls.name)

    test_name = golang_naming.function_name(
        Identifier(f"Test_{cls.name}_round_trip_OK")
    )

    blocks.append(
        Stripped(
            f"""\
func {test_name}(t *testing.T) {{
{I}pths := aastesting.FindFilesBySuffixRecursively(
{II}filepath.Join(
{III}aastesting.TestDataDir,
{III}"Xml",
{III}"Expected",
{III}{xml_class_name_literal},
{II}),
{II}".xml",
{I})
{I}sort.Strings(pths)

{I}for _, pth := range pths {{
{II}bb, err := os.ReadFile(pth)
{II}if err != nil {{
{III}t.Fatalf("Failed to read the file %s: %s", pth, err.Error())
{III}return
{II}}}
{II}text := string(bb)

{II}decoder := xml.NewDecoder(strings.NewReader(text))

{II}deserialized, deseriaErr := aasxmlization.{unmarshal_function}(decoder)
{II}ok := assertNoDeserializationError(t, deseriaErr, pth)
{II}if !ok {{
{III}return
{II}}}

{II}if _, ok := deserialized.(aastypes.{interface_name}); !ok {{
{III}t.Fatalf(
{IIII}"Expected an instance of {interface_name}, "+
{IIIII}"but got %T: %v",
{IIII}deserialized, deserialized,
{III})
{III}return
{II}}}

{II}buf := &bytes.Buffer{{}}
{II}encoder := xml.NewEncoder(buf)
{II}encoder.Indent("", "\\t")

{II}seriaErr := aasxmlization.Marshal(encoder, deserialized, true)
{II}ok = assertNoSerializationError(t, seriaErr, pth)
{II}if !ok {{
{III}return
{II}}}

{II}roundTrip := string(buf.Bytes())

{II}ok = assertSerializationEqualsDeserialization(
{III}t,
{III}text,
{III}roundTrip,
{III}pth,
{II})
{II}if !ok {{
{III}return
{II}}}
{I}}}
}}"""
        )
    )

    test_name = golang_naming.function_name(
        Identifier(f"Test_{cls.name}_deserialization_fail")
    )

    blocks.append(
        Stripped(
            f"""\
func {test_name}(t *testing.T) {{
{I}pattern := filepath.Join(
{II}aastesting.TestDataDir,
{II}"Xml",
{II}"Unexpected",
{II}"Unserializable",
{II}"*",  // This asterisk represents the cause.
{II}{xml_class_name_literal},
{I})

{I}causeDirs, err := filepath.Glob(pattern)
{I}if err != nil {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Failed to find cause directories matching %s: %s",
{IIII}pattern, err.Error(),
{III}),
{II})
{I}}}

{I}for _, causeDir := range causeDirs {{
{II}pths := aastesting.FindFilesBySuffixRecursively(
{III}causeDir,
{III}".xml",
{II})
{II}sort.Strings(pths)

{II}for _, pth := range pths {{
{III}relPth, err := filepath.Rel(aastesting.TestDataDir, pth)
{III}if err != nil {{
{IIII}panic(
{IIIII}fmt.Sprintf(
{IIIII}{I}"Failed to compute the relative path of %s to %s: %s",
{IIIII}{I}aastesting.TestDataDir, pth, err.Error(),
{IIIII}),
{IIII})
{III}}}

{III}expectedPth := filepath.Join(
{IIII}aastesting.TestDataDir,
{IIII}"DeserializationError",
{IIII}filepath.Dir(relPth),
{IIII}filepath.Base(relPth)+".error",
{III})

{III}bb, err := os.ReadFile(pth)
{III}if err != nil {{
{IIII}t.Fatalf("Failed to read the file %s: %s", pth, err.Error())
{IIII}return
{III}}}
{III}text := string(bb)

{III}decoder := xml.NewDecoder(strings.NewReader(text))

{III}_, deseriaErr := aasxmlization.Unmarshal(decoder)
{III}ok := assertIsDeserializationErrorAndEqualsExpectedOrRecord(
{IIII}t, deseriaErr, pth, expectedPth,
{III})
{III}if !ok {{
{IIII}return
{III}}}
{II}}}
{I}}}
}}"""
        )
    )

    return blocks


#: The lexical forms which no recorded example can hold, by the primitive they
#: belong to. A recorded example has to serialize back to itself, character for
#: character, so it can hold neither a value written in another form than it
#: was read nor one whose written form the targets spell differently.
_LEXICAL_CASES_BY_PRIMITIVE = {
    intermediate.PrimitiveType.FLOAT: [
        # NOTE:
        # A literal too large for a double is not an error: XSD rounds it to
        # an infinity, and one too small to zero.
        #
        # See: https://www.w3.org/TR/xmlschema11-2/#double
        ("1e400", "math.Inf(1)"),
        ("-1e400", "math.Inf(-1)"),
        ("1e-400", "0.0"),
        ("INF", "math.Inf(1)"),
        ("+INF", "math.Inf(1)"),
        ("-INF", "math.Inf(-1)"),
    ],
    intermediate.PrimitiveType.BYTEARRAY: [
        # NOTE:
        # ``xs:base64Binary`` admits whitespace *between* the characters and
        # not only around them, and an empty value stands for zero bytes.
        # Neither can be a recorded example: the first is written back without
        # the space, and the second as an empty element.
        #
        # See: https://www.w3.org/TR/xmlschema-2/#base64Binary
        ("SGk=", "[]byte{72, 105}"),
        ("SG k=", "[]byte{72, 105}"),
        ("S G k =", "[]byte{72, 105}"),
        ("", "[]byte{}"),
    ],
    intermediate.PrimitiveType.BOOL: [
        # NOTE:
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

    interface_name = golang_naming.interface_name(cls.name)
    cls_name_go = golang_naming.private_function_name(
        Identifier(f"read_{cls.name}_with")
    )
    cls_name_xml = naming.xml_class_name(cls.name)
    unmarshal_function = golang_naming.function_name(Identifier("unmarshal"))

    result = [
        Stripped(
            f"""\
// Read the first recorded example of {interface_name} with the content of
// the element `xmlName` replaced by `text`.
func {cls_name_go}(
{I}t *testing.T,
{I}xmlName string,
{I}text string,
) aastypes.{interface_name} {{
{I}pths := aastesting.FindFilesBySuffixRecursively(
{II}filepath.Join(
{III}aastesting.TestDataDir,
{III}"Xml",
{III}"Expected",
{III}{golang_common.string_literal(cls_name_xml)},
{II}),
{II}".xml",
{I})
{I}sort.Strings(pths)

{I}if len(pths) == 0 {{
{II}t.Fatalf(
{III}"Expected at least one recorded example of %s, but got none",
{III}{golang_common.string_literal(cls_name_xml)},
{II})
{I}}}

{I}bb, err := os.ReadFile(pths[0])
{I}if err != nil {{
{II}t.Fatalf("Failed to read the file %s: %s", pths[0], err.Error())
{I}}}

{I}original := string(bb)

{I}start := strings.Index(original, "<"+xmlName+">") + len(xmlName) + 2
{I}end := strings.Index(original, "</"+xmlName+">")

{I}patched := original[:start] + text + original[end:]

{I}decoder := xml.NewDecoder(strings.NewReader(patched))
{I}deserialized, deseriaErr := aasxmlization.{unmarshal_function}(decoder)
{I}if deseriaErr != nil {{
{II}t.Fatalf(
{III}"Expected no de-serialization error on %v, but got: %s",
{III}patched, deseriaErr.Error(),
{II})
{I}}}

{I}instance, ok := deserialized.(aastypes.{interface_name})
{I}if !ok {{
{II}t.Fatalf("Expected an instance of {interface_name}, but got %T", deserialized)
{I}}}

{I}return instance
}}"""
        )
    ]  # type: List[Stripped]

    for a_type, prop in relevant:
        prop_xml_name = naming.xml_property(prop.name)
        getter_name = golang_naming.getter_name(prop.name)

        # NOTE:
        # A slice is compared element by element; Go refuses to compare one
        # with != at all.
        comparison = (
            "!bytes.Equal(got, expected)"
            if a_type is intermediate.PrimitiveType.BYTEARRAY
            else "got != expected"
        )

        for a_text, expected in _LEXICAL_CASES_BY_PRIMITIVE[a_type]:
            test_name = golang_naming.function_name(
                Identifier(
                    f"Test_{prop.name}_read_from_" f"{_lexical_test_name_chunk(a_text)}"
                )
            )

            result.append(
                Stripped(
                    f"""\
func {test_name}(t *testing.T) {{
{I}instance := {cls_name_go}(
{II}t,
{II}{golang_common.string_literal(prop_xml_name)},
{II}{golang_common.string_literal(a_text)},
{I})

{I}got := instance.{getter_name}()
{I}expected := {expected}
{I}if {comparison} {{
{II}t.Fatalf("Expected %v, but got %v", expected, got)
{I}}}
}}"""
                )
            )

    return result


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to test the XML de/serialization of concrete classes."""
    blocks = [
        Stripped("package xmlization_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"bytes"
{I}"path/filepath"
{I}"fmt"
{I}"os"
{I}"sort"
{I}"strings"
{I}"testing"
{I}"encoding/xml"
{I}"math"
{I}aastesting "{repo_url}/aastesting"
{I}aastypes "{repo_url}/types"
{I}aasxmlization "{repo_url}/xmlization"
)"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        blocks.extend(_generate_for_cls(cls=concrete_cls))

    blocks.extend(_generate_lexical_tests(symbol_table))

    blocks.append(golang_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
