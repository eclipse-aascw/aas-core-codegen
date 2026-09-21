"""Generate the code for de/serializing JSON-able values to and from XML."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.golang import common as golang_common
from aas_core_codegen.golang.common import (
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

    Only ``ReadValueContent``, ``ReadArrayContent`` and ``ReadObjectContent``
    are exported: they read the *content* of an element which the caller has
    already entered, so that the xmlization can hand over the very decoder it
    reads the enclosing document with.

    The XML-RPC elements live in no namespace at all, as the XML-RPC
    specification prescribes, and not in the namespace of the enclosing
    document, so no namespace is handed down the descent either.

    The path of an error is an XPath into the document which is being read,
    and grows one step per element actually entered. An item of a ``<data>``
    element gets an index and no step of its own, as every such item is
    a ``<value>`` element; a member of a ``<struct>`` gets a key segment,
    which renders as a predicate on the ``<name>`` child element that carries
    the key.
    """
    return [
        Stripped(
            f"""\
// Match a numeral of the `<double>` lexical space.
//
// This is the numeric part of the lexical space of `xs:double`, and
// deliberately not its three named literals -- `INF`, `-INF` and `NaN` --
// since a JSON number can be none of them.
//
// Mind the explicit `[0-9]`: `\\d` would match a digit of any script.
//
// See: https://www.w3.org/TR/xmlschema-2/#double
var doubleRe = regexp.MustCompile(
{I}`^(\\+|-)?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([Ee](\\+|-)?[0-9]+)?$`,
)"""
        ),
        Stripped(
            f"""\
// Read the content of an element holding a JSON-able value.
//
// The content is a single discriminator element -- `<boolean>`, `<double>`,
// `<string>`, `<array>` or `<struct>` -- which says what the value is.
//
// The `current` token is expected to point to the content of the enclosing
// element, and the resulting `next` token points to its end element.
func ReadValueContent(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value aastypes.JsonValue, next xml.Token, err error) {{
{I}return xmlcommon.ReadElementDispatchedInNoNamespace(
{II}decoder, current, readValueByLocal,
{I})
}}"""
        ),
        Stripped(
            f"""\
// Read the content of the discriminator element named `local`.
func readValueByLocal(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (value aastypes.JsonValue, next xml.Token, err error) {{
{I}switch local {{
{II}case "boolean":
{III}value, next, err = readBoolean(decoder, current)
{II}case "double":
{III}value, next, err = readDouble(decoder, current)
{II}case "string":
{III}var text string
{III}text, next, err = xmlcommon.ReadText(decoder, current)
{III}// NOTE (mristin):
{III}// `xs:string` is `preserve` and not `collapse`, so a `<string>` keeps
{III}// its whitespace, unlike a `<boolean>` or a `<double>`.
{III}value = text
{II}case "array":
{III}var items aastypes.JsonArray
{III}items, next, err = ReadArrayContent(decoder, current)
{III}value = items
{II}case "struct":
{III}var members aastypes.JsonObject
{III}members, next, err = ReadObjectContent(decoder, current)
{III}value = members
{II}default:
{III}// NOTE (mristin):
{III}// No element has been entered which could be a step of the path: it is
{III}// this very element which does not belong here.
{III}err = xmlcommon.NewDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a discriminator element (one of boolean, double, "+
{IIIII}"string, array or struct), but got: %s",
{IIIII}local,
{IIII}),
{III})
{III}return
{I}}}

{I}if err != nil {{
{II}xmlcommon.MustDeserializationError(err).PrependName(local)
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Read the content of a `<boolean>` element.
//
// Real XML-RPC tooling writes and expects a strict `1`/`0`, and not
// the `true`/`false` which `xs:boolean` and the rest of this module use.
func readBoolean(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value aastypes.JsonValue, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = xmlcommon.ReadText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}// NOTE (mristin):
{I}// `whiteSpace` is fixed to `collapse` for every atomic XSD type but
{I}// a string, so a pretty-printed `<boolean>` has to be read as well.
{I}text = xmlcommon.CollapseWhitespace(text)

{I}switch text {{
{II}case "1":
{III}value = true
{II}case "0":
{III}value = false
{II}default:
{III}err = xmlcommon.NewDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected \\"0\\" or \\"1\\" as the text of a boolean element, "+
{IIIII}"but got: %s",
{IIIII}text,
{IIII}),
{III})
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Read the content of a `<double>` element.
func readDouble(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value aastypes.JsonValue, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = xmlcommon.ReadText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}// NOTE (mristin):
{I}// See the note in readBoolean on why the whitespace is collapsed.
{I}text = xmlcommon.CollapseWhitespace(text)

{I}// NOTE (mristin):
{I}// The lexical form is matched before the text is converted.
{I}// strconv.ParseFloat reads more than we admit here: a hexadecimal
{I}// literal, an underscore separator, and the spellings "inf",
{I}// "infinity" and "nan".
{I}//
{I}// Mind that the numeral excludes "INF", "-INF" and "NaN" on purpose,
{I}// unlike xs:double, which names all three. A double element carries
{I}// a JSON number, and JSON knows neither an infinity nor
{I}// a not-a-number, so there is no JSON-able value for such a text
{I}// to de-serialize into.
{I}if !doubleRe.MatchString(text) {{
{II}err = xmlcommon.NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a number as the text of a double element, but got: %s",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}var number float64
{I}number, err = strconv.ParseFloat(text, 64)
{I}if err != nil || math.IsInf(number, 0) {{
{II}// NOTE (mristin):
{II}// A literal too large for a float64 gives an infinity, which is no
{II}// JSON-able value either, so it is refused rather than rounded.
{II}err = xmlcommon.NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a number representable as a JSON-able value as the "+
{IIII}"text of a double element, but got: %s",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}value = number
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Read the content of an element holding a JSON-able array.
//
// The content is a single `<data>` element holding a `<value>` per item.
func ReadArrayContent(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value aastypes.JsonArray, next xml.Token, err error) {{
{I}return xmlcommon.ReadElementDispatchedInNoNamespace(decoder, current, readData)
}}"""
        ),
        Stripped(
            f"""\
// Read the content of the `<data>` element of a JSON-able array.
func readData(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (value aastypes.JsonArray, next xml.Token, err error) {{
{I}if local != "data" {{
{II}err = xmlcommon.NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a data element in a JSON-able array, but got: %s",
{IIII}local,
{III}),
{II})
{II}return
{I}}}

{I}// NOTE (mristin):
{I}// An empty data element gives an empty array, and not a nil one, so
{I}// that the value round-trips as the empty array it was.
{I}value = aastypes.JsonArray{{}}

{I}next = current
{I}for {{
{II}next, err = xmlcommon.SkipEmptyTextWhitespaceAndComments(decoder, next)
{II}if err != nil {{
{III}return
{II}}}

{II}if _, ok := next.(xml.StartElement); !ok {{
{III}break
{II}}}

{II}var item aastypes.JsonValue
{II}item, next, err = xmlcommon.ReadElementDispatchedInNoNamespace(
{III}decoder, next, readArrayItem,
{II})
{II}if err != nil {{
{III}// NOTE (mristin):
{III}// Every item of a `<data>` element is a `<value>` element, so the index
{III}// already names the element which was entered, and there is no step of
{III}// its own for it.
{III}xmlcommon.MustDeserializationError(err).
{IIII}PrependIndex(len(value)).
{IIII}PrependName("data")
{III}return
{II}}}

{II}value = append(value, item)
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Read a `<value>` element of a JSON-able array.
func readArrayItem(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (value aastypes.JsonValue, next xml.Token, err error) {{
{I}if local != "value" {{
{II}err = xmlcommon.NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value element in a JSON-able array, but got: %s",
{IIII}local,
{III}),
{II})
{II}return
{I}}}

{I}return ReadValueContent(decoder, current)
}}"""
        ),
        Stripped(
            f"""\
// Read the content of an element holding a JSON-able object.
//
// The content is a `<member>` per key, each holding a `<name>` and
// a `<value>`.
func ReadObjectContent(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value aastypes.JsonObject, next xml.Token, err error) {{
{I}// NOTE (mristin):
{I}// An element with no members gives an empty object, and not a nil one,
{I}// so that the value round-trips as the empty object it was.
{I}value = aastypes.JsonObject{{}}

{I}next = current
{I}for {{
{II}next, err = xmlcommon.SkipEmptyTextWhitespaceAndComments(decoder, next)
{II}if err != nil {{
{III}return
{II}}}

{II}if _, ok := next.(xml.StartElement); !ok {{
{III}break
{II}}}

{II}var aMember member
{II}aMember, next, err = xmlcommon.ReadElementDispatchedInNoNamespace(
{III}decoder, next, readMember,
{II})
{II}if err != nil {{
{III}return
{II}}}

{II}// NOTE (mristin):
{II}// A repeated member name is refused, just as a repeated property element
{II}// is refused elsewhere in this module. Letting the later member win would
{II}// silently accept a document which says two different things about
{II}// the same key.
{II}if _, ok := value[aMember.name]; ok {{
{III}err = xmlcommon.NewDeserializationError(
{IIII}"The member occurred more than once",
{III}).PrependKey(aMember.name)
{III}return
{II}}}

{II}value[aMember.name] = aMember.value
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Represent the name and the value of a single `<member>`.
type member struct {{
{I}name  string
{I}value aastypes.JsonValue
}}"""
        ),
        Stripped(
            f"""\
// Read a `<member>` element of a JSON-able object.
func readMember(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (value member, next xml.Token, err error) {{
{I}if local != "member" {{
{II}err = xmlcommon.NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a member element in a JSON-able object, but got: %s",
{IIII}local,
{III}),
{II})
{II}return
{I}}}

{I}next, err = xmlcommon.SkipEmptyTextWhitespaceAndComments(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}value.name, next, err = xmlcommon.ReadElementDispatchedInNoNamespace(
{II}decoder, next, readMemberName,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}next, err = xmlcommon.SkipEmptyTextWhitespaceAndComments(decoder, next)
{I}if err != nil {{
{II}return
{I}}}

{I}value.value, next, err = xmlcommon.ReadElementDispatchedInNoNamespace(
{II}decoder, next, readMemberValue,
{I})
{I}if err != nil {{
{II}// NOTE (mristin):
{II}// A `<struct>` holds the key of a member in a `<name>` child element
{II}// instead of an attribute, so the key segment renders as a predicate on
{II}// that child element, and the `<value>` element is a step of its own.
{II}xmlcommon.MustDeserializationError(err).
{III}PrependName("value").
{III}PrependKey(value.name)
{II}return
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Read the `<name>` element of a `<member>`.
func readMemberName(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (value string, next xml.Token, err error) {{
{I}if local != "name" {{
{II}err = xmlcommon.NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a name element in a JSON-able member, but got: %s",
{IIII}local,
{III}),
{II})
{II}return
{I}}}

{I}return xmlcommon.ReadText(decoder, current)
}}"""
        ),
        Stripped(
            f"""\
// Read the `<value>` element of a `<member>`.
func readMemberValue(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (value aastypes.JsonValue, next xml.Token, err error) {{
{I}if local != "value" {{
{II}err = xmlcommon.NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value element in a JSON-able member, but got: %s",
{IIII}local,
{III}),
{II})
{II}return
{I}}}

{I}return ReadValueContent(decoder, current)
}}"""
        ),
    ]


def _generate_writers() -> List[Stripped]:
    """
    Generate the writers of the XML-RPC subset.

    These mirror :py:func:`_generate_readers`. They need no namespace: every
    element they write inherits the default namespace which the enclosing
    element has declared.

    The path of an error reports where in the *value* it occurred, and not
    where in a document which was never written, so it stays a path into
    the value.
    """
    return [
        Stripped(
            f"""\
// Write `value` as the content of an element holding a JSON-able value.
//
// The content is a single discriminator element which says what the value is.
//
// Do not flush.
func WriteValueContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonValue,
) (err error) {{
{I}return writeValueContent(encoder, value, true)
}}

// Write `value` as the content of a `<value>` element of this very package,
// which already lives in no namespace.
//
// Do not flush.
func writeNestedValueContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonValue,
) (err error) {{
{I}return writeValueContent(encoder, value, false)
}}

func writeValueContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonValue,
{I}undeclareNamespace bool,
) (err error) {{
{I}if value == nil {{
{II}err = xmlcommon.NewSerializationError(
{III}"Expected a JSON-able value, but got a nil",
{II})
{II}return
{I}}}

{I}switch casted := value.(type) {{
{II}case bool:
{III}// NOTE (mristin):
{III}// Real XML-RPC tooling writes and expects a strict `1`/`0`, and not
{III}// the `true`/`false` which `xs:boolean` and the rest of this module
{III}// use.
{III}text := "0"
{III}if casted {{
{IIII}text = "1"
{III}}}
{III}err = xmlcommon.WriteElementInNoNamespace(
{IIII}encoder, "boolean", undeclareNamespace,
{IIII}text,
{IIII}func(anEncoder *xml.Encoder, aValue string) error {{
{IIIII}return xmlcommon.WriteText(anEncoder, aValue)
{IIII}}},
{III})
{III}return

{II}case float64:
{III}// NOTE (mristin):
{III}// JSON knows neither an infinity nor a not-a-number, so neither is
{III}// a JSON-able value, and readDouble refuses to read either
{III}// back.
{III}if math.IsInf(casted, 0) || math.IsNaN(casted) {{
{IIII}err = xmlcommon.NewSerializationError(
{IIIII}fmt.Sprintf(
{IIIIII}"Expected a JSON-able value, but got the number %v, which "+
{IIIIII}"is neither finite nor representable in JSON",
{IIIIII}casted,
{IIIII}),
{IIII})
{IIII}return
{III}}}
{III}err = xmlcommon.WriteElementInNoNamespace(
{IIII}encoder, "double", undeclareNamespace,
{IIII}casted,
{IIII}xmlcommon.WriteAsText_double,
{III})
{III}return

{II}case string:
{III}err = xmlcommon.WriteElementInNoNamespace(
{IIII}encoder, "string", undeclareNamespace,
{IIII}casted,
{IIII}xmlcommon.WriteAsText_string,
{III})
{III}return

{II}case aastypes.JsonArray:
{III}err = xmlcommon.WriteElementInNoNamespace(
{IIII}encoder, "array", undeclareNamespace,
{IIII}casted,
{IIII}writeNestedArrayContent,
{III})
{III}return

{II}case aastypes.JsonObject:
{III}err = xmlcommon.WriteElementInNoNamespace(
{IIII}encoder, "struct", undeclareNamespace,
{IIII}casted,
{IIII}writeNestedObjectContent,
{III})
{III}return

{II}default:
{III}err = xmlcommon.NewSerializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a JSON-able value (a bool, a float64, a string, "+
{IIIII}"a JsonArray or a JsonObject), but got: %T",
{IIIII}value,
{IIII}),
{III})
{III}return
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Write `value` as the content of an element holding a JSON-able array.
//
// The content is a single `<data>` element holding a `<value>` per item.
//
// Do not flush.
func WriteArrayContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonArray,
) (err error) {{
{I}return writeArrayContent(encoder, value, true)
}}

// Write `value` as the content of an `<array>` element of this very package,
// which already lives in no namespace.
//
// Do not flush.
func writeNestedArrayContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonArray,
) (err error) {{
{I}return writeArrayContent(encoder, value, false)
}}

func writeArrayContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonArray,
{I}undeclareNamespace bool,
) (err error) {{
{I}err = xmlcommon.WriteStartElementInNoNamespace(encoder, "data", undeclareNamespace)
{I}if err != nil {{
{II}return
{I}}}

{I}for i, item := range value {{
{II}err = xmlcommon.WriteElement(encoder, "value", item, writeNestedValueContent)
{II}if err != nil {{
{III}xmlcommon.MustSerializationError(err).PrependIndex(i)
{III}return
{II}}}
{I}}}

{I}err = xmlcommon.WriteEndElement(encoder, "data", false)
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Write `value` as the content of an element holding a JSON-able object.
//
// The content is a `<member>` per key, each holding a `<name>` and a
// `<value>`.
//
// Do not flush.
func WriteObjectContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonObject,
) (err error) {{
{I}return writeObjectContent(encoder, value, true)
}}

// Write `value` as the content of a `<struct>` element of this very package,
// which already lives in no namespace.
//
// Do not flush.
func writeNestedObjectContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonObject,
) (err error) {{
{I}return writeObjectContent(encoder, value, false)
}}

func writeObjectContent(
{I}encoder *xml.Encoder,
{I}value aastypes.JsonObject,
{I}undeclareNamespace bool,
) (err error) {{
{I}// NOTE (mristin):
{I}// The keys are sorted so that the same object always gives the same
{I}// document, as the iteration order of a Go map is deliberately random.
{I}keys := make([]string, 0, len(value))
{I}for key := range value {{
{II}keys = append(keys, key)
{I}}}
{I}sort.Strings(keys)

{I}for _, key := range keys {{
{II}err = xmlcommon.WriteStartElementInNoNamespace(encoder, "member", undeclareNamespace)
{II}if err != nil {{
{III}return
{II}}}

{II}err = xmlcommon.WriteElement(encoder, "name", key, xmlcommon.WriteAsText_string)
{II}if err != nil {{
{III}return
{II}}}

{II}err = xmlcommon.WriteElement(encoder, "value", value[key], writeNestedValueContent)
{II}if err != nil {{
{III}xmlcommon.MustSerializationError(err).PrependKey(key)
{III}return
{II}}}

{II}err = xmlcommon.WriteEndElement(encoder, "member", false)
{II}if err != nil {{
{III}return
{II}}}
{I}}}
{I}return
}}"""
        ),
    ]


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(repo_url: Stripped) -> str:
    """
    Generate the code for de/serializing JSON-able values to and from XML.

    JSON prescribes no XML representation of its own, so a JSON-able value is
    de/serialized over the subset of XML-RPC which covers exactly what such
    a value can be: ``<boolean>``, ``<double>``, ``<string>``, ``<array>`` and
    ``<struct>``, with ``<data>``, ``<member>``, ``<name>`` and ``<value>``
    holding them together.

    The package knows nothing of the meta-model beyond the three JSON-able
    types, and drives no document of its own: the caller passes the decoder or
    the encoder, so the xmlization reads a JSON-able property from the very
    same decoder it reads the enclosing document with, one element at a time.

    The low-level reading -- the skipping of the whitespace and of the
    comments, the check of the XML namespace and the consuming of a start and
    of an end tag -- is not repeated here, but taken from ``xmlcommon``, which
    the xmlization reads the enclosing document with as well.

    The ``repo_url`` is the URL of the repository of the generated module.
    """
    aastypes_url_literal = golang_common.string_literal(f"{repo_url}/types")

    xmlcommon_url_literal = golang_common.string_literal(
        f"{repo_url}/internal/xmlcommon"
    )

    blocks = [
        Stripped(
            """\
// Package xmlrpc de/serializes JSON-able values to and from XML.
//
// JSON prescribes no XML representation of its own, so a JSON-able value is
// de/serialized over the subset of XML-RPC which covers exactly what such
// a value can be: `<boolean>`, `<double>`, `<string>`, `<array>` and
// `<struct>`.
//
// Every function reads from or writes to the decoder or the encoder which
// the caller passes in, and consumes or produces exactly the content of one
// element. This is what lets the xmlization read a JSON-able property from
// the very same decoder it reads the enclosing document with.
package xmlrpc"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"encoding/xml"
{I}"fmt"
{I}"math"
{I}"regexp"
{I}"sort"
{I}"strconv"
{I}xmlcommon {xmlcommon_url_literal}
{I}aastypes {aastypes_url_literal}
)"""
        ),
        Stripped(
            """\
// Represent an error during the de-serialization.
//
// This is the very type which the xmlization reports, so an error raised deep
// inside a JSON-able value keeps its identity, and its path, across the
// hand-over.
type DeserializationError = xmlcommon.DeserializationError"""
        ),
        Stripped(
            """\
// Represent an error during the serialization.
//
// See the note on [DeserializationError] on why this is an alias.
type SerializationError = xmlcommon.SerializationError"""
        ),
    ]  # type: List[Stripped]

    blocks.extend(_generate_readers())
    blocks.extend(_generate_writers())

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
