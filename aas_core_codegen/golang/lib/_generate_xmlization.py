"""Generate code for XML de/serialization."""

import io
from typing import Tuple, Optional, List, Set, Union

from icontract import ensure, require

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    pointering as golang_pointering,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


# region De-serialization


def _generate_deserialization_error_and_its_methods() -> List[Stripped]:
    """Generate code to represent the deserialization error."""
    return [
        Stripped(
            f"""\
// Represent an error during the de-serialization.
//
// Implements `error`.
type DeserializationError struct{{
{I}Path *aasreporting.Path
{I}Message string
}}"""
        ),
        Stripped(
            f"""\
func newDeserializationError(message string) *DeserializationError {{
{I}return &DeserializationError{{
{II}Path: &aasreporting.Path{{}},
{II}Message: message,
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func (de *DeserializationError) Error() string {{
{I}return fmt.Sprintf(
{II}"%s: %s",
{II}de.PathString(),
{II}de.Message,
{I})
}}"""
        ),
        Stripped(
            f"""\
// Render the path as a string.
func (de *DeserializationError) PathString() string {{
{I}return aasreporting.ToRelativeXPath(de.Path)
}}"""
        ),
    ]


def _generate_is_whitespace() -> Stripped:
    return Stripped(
        f"""\
// Check if the string `s` consists only of whitespace.
//
// An empty string causes panic — please cover that case before.
func isWhitespace(s string) bool {{
{I}if len(s) == 0 {{
{II}panic("Unexpected empty string")
{I}}}
{I}for _, c := range s {{
{II}if !unicode.IsSpace(c) {{
{III}return false
{II}}}
{I}}}
{I}return true
}}"""
    )


def _generate_read_next() -> Stripped:
    return Stripped(
        f"""\
// Read the next token from the `decoder` given the `current` token.
//
// If `current` token is [eof], return [eof].
func readNext(decoder *xml.Decoder, current xml.Token) (next xml.Token, err error) {{
{I}if _, isEOF := current.(eof); isEOF {{
{II}next = current
{II}return
{I}}}

{I}var tokenErr error
{I}next, tokenErr = decoder.Token()
{I}if tokenErr != nil {{
{II}if tokenErr == io.EOF {{
{III}next = &eof{{}}
{III}return
{II}}}

{II}err = tokenErr
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_skip_empty_text_whitespace_and_comments() -> Stripped:
    return Stripped(
        f"""\
// Read all the possible whitespace and comments.
//
// Return the `next` token which is neither empty text, nor whitespace nor comment,
// or [eof], if we reached the end-of-file.
//
// If we already reached the end-of-file, simply return [eof].
func skipEmptyTextWhitespaceAndComments(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (next xml.Token, err error) {{
{I}stop := false
{I}for !stop {{
{II}if _, isEOF := current.(eof); isEOF {{
{III}break
{II}}}

{II}switch et := current.(type) {{
{II}case xml.CharData:
{III}text := string(et)
{III}if len(text) != 0 && !isWhitespace(text) {{
{IIII}stop = true
{III}}} else {{
{IIII}// We should proceed to the next token.
{III}}}
{II}case xml.Comment:
{III}// We should proceed to the next token.
{II}default:
{III}stop = true
{II}}}

{II}if !stop {{
{III}current, err = readNext(decoder, current)
{III}if err != nil {{
{IIII}return
{III}}}
{II}}}
{I}}}

{I}next = current
{I}return
}}"""
    )


def _generate_read_text() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data).
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readText(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (text string, next xml.Token, err error) {{
{I}b := &strings.Builder{{}}

{I}stop := false
{I}for {{
{II}if _, isEOF := current.(eof); isEOF {{
{III}err = newDeserializationError(
{IIII}"Expected to read text, but reached the end-of-file",
{III})
{III}return
{II}}}

{II}switch et := current.(type) {{
{II}case xml.CharData:
{III}b.WriteString(string(et))
{III}// Proceed to the next token.
{II}case xml.Comment:
{III}// Proceed to the next token.
{II}default:
{III}stop = true
{II}}}

{II}if !stop {{
{III}current, err = readNext(decoder, current)
{III}if err != nil {{
{IIII}return
{III}}}
{II}}} else {{
{III}break
{II}}}
{I}}}

{I}next = current
{I}text = b.String()
{I}return
}}"""
    )


def _generate_read_text_as_boolean() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a representation of a `xs:boolean`.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readTextAsBoolean(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value bool, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}switch text {{
{I}case "1":
{II}value = true
{I}case "true":
{II}value = true
{I}case "0":
{II}value = false
{I}case "false":
{II}value = false
{I}default:
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:boolean, but got: %s",
{IIII}text,
{III}),
{II})
{I}}}
{I}if err != nil {{
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_read_text_as_long() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a representation of a `xs:long`.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readTextAsLong(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value int64, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}var parseErr error
{I}value, parseErr = strconv.ParseInt(text, 10, 64)
{I}if parseErr != nil {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:long, but it could not be parsed: %s: %s",
{IIII}parseErr.Error(), text,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_is_valid_xs_double() -> List[Stripped]:
    """
    Generate regular expression to check ``xs:double`` values.

    While there might be a function in the meta-model itself with the same name in
    the verification, we provide a separate function here so that it works for all
    meta-models.
    """
    return [
        Stripped(
            f"""\
func constructXsDoubleRe() *regexp.Regexp {{
{I}doubleRep := "((\\\\+|-)?([0-9]+(\\\\.[0-9]*)?|\\\\.[0-9]+)([Ee](\\\\+|-)?[0-9]+)?|-?INF|NaN)"
{I}pattern := aascommon.Concat(
{II}"^",
{II}doubleRep,
{II}"$",
{I})

{I}return regexp.MustCompile(
{II}pattern,
{I})
}}"""
        ),
        Stripped(
            """\
var xsDoubleRe = constructXsDoubleRe()"""
        ),
        Stripped(
            f"""\
// Check that text conforms to the pattern of an `xs:double`.
//
// See: https://www.w3.org/TR/xmlschema-2/#double
//
//   - `text`: Text to be checked
//   - Return True if the text conforms to the pattern
func isValidXsDouble(text string) bool {{
{I}return xsDoubleRe.MatchString(
{II}text,
{I})
}}"""
        ),
    ]


def _generate_read_text_as_double() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a representation of a `xs:double`.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readTextAsDouble(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value float64, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}// We need to check explicitly for the regular expression since
{I}// strconv.ParseFloat is too permissive. For example, it accepts "nan"
{I}// although only "NaN" is valid.
{I}// See: https://www.w3.org/TR/xmlschema-2/#double
{I}if !isValidXsDouble(text) {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:double, but got: %s",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}var parseErr error
{I}value, parseErr = strconv.ParseFloat(text, 64)
{I}if parseErr != nil {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:double, but it could not be parsed: %s: %s",
{IIII}parseErr.Error(), text,
{III}),
{II})
{II}return
{I}}}

{I}// NOTE (2023-06-14):
{I}// We explicitly do not check for loss of precision, as the majority of people will
{I}// use string representation of the floating point numbers ignoring the precision
{I}// issues. For example, the closest double-precision number to the number `359.9` is
{I}// `359.8999999999999772626324556767940521240234375`, but most people will simply
{I}// give `359.9` as the value.

{I}return
}}"""
    )


def _generate_read_text_as_base64_encoded_bytes() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a base64-encoded bytes.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readTextAsBase64EncodedBytes(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value []byte, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}var decodingErr error
{I}value, decodingErr = b64.StdEncoding.DecodeString(text)
{I}if decodingErr != nil {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Text could not be decoded as base64: %s",
{IIII}decodingErr.Error(),
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_check_start_element() -> Stripped:
    return Stripped(
        f"""\
// Check that the `current` token is a valid start element, *i.e.*, lives in [Namespace]
// and contains no attributes.
func checkStartElement(
{I}current xml.StartElement,
) (err error) {{
{I}unexpectedAttr := 0
{I}for _, attr := range current.Attr {{
{II}if (attr.Name.Space == "" && attr.Name.Local == "xmlns") ||
{III}attr.Name.Space == "xmlns" {{
{III}continue
{II}}}

{II}unexpectedAttr++
{I}}}
{I}if unexpectedAttr != 0 {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected no attributes except 'xmlns' in the start element, "+
{IIIII}"but got %d in the start element %s",
{IIII}unexpectedAttr, current.Name.Local,
{III}),
{II})
{II}return
{I}}}

{I}if current.Name.Space != Namespace {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected only start elements in the namespace %s, "+
{IIIII}"but got a start element %s in the namespace %s",
{IIII}Namespace, current.Name.Local, current.Name.Space,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_extract_local_name_from_start_element() -> Stripped:
    return Stripped(
        f"""\
// Expect a valid start element (as defined in [checkStartElement]) and extract its
// `local` name.
//
// This function is meant to be called whenever you know the runtime type of a token.
// If you do not know the runtime type, call [parseAsStartElementAndExtractLocalName]
// so that you can succinctly check the runtime type as well.
func extractLocalNameFromStartElement(
{I}current xml.StartElement,
) (local string, err error) {{
{I}err = checkStartElement(current)
{I}if err != nil {{
{II}return
{I}}}

{I}local = current.Name.Local
{I}return
}}"""
    )


def _generate_parse_as_start_element_and_extract_local_name() -> Stripped:
    return Stripped(
        f"""\
// Expect a valid start element (as defined in [checkStartElement]) and extract its
// local name.
//
// Valid means that we check that the start element lives in [Namespace] and contains
// no attributes.
//
// If you know the runtime type of `current` token, call
// [parseLocalNameFromStartElement] instead to save a cast.
func parseAsStartElementAndExtractLocalName(
{I}current xml.Token,
) (local string, err error) {{
{I}if _, isEOF := current.(eof); isEOF {{
{II}err = newDeserializationError(
{III}"Expected a start element, but reached the end-of-file",
{II})
{II}return
{I}}}

{I}et, ok := current.(xml.StartElement)
{I}if !ok {{
{II}switch v := current.(type) {{
{II}case xml.EndElement:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got an end element %s in namespace %s",
{IIIII}v.Name.Local, v.Name.Space,
{IIII}),
{III})
{II}case xml.CharData:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got text %s",
{IIIII}string(v),
{IIII}),
{III})
{II}default:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got %T: %v",
{IIIII}current, current,
{IIII}),
{III})
{II}}}
{II}return
{I}}}

{I}local, err = extractLocalNameFromStartElement(et)
{I}return
}}"""
    )


def _generate_check_end_element() -> Stripped:
    return Stripped(
        f"""\
// Check that the `current` token is an end element, living in [Namespace], and
// having the `local` name.
func checkEndElement(current xml.Token, local string) (err error) {{
{I}if _, isEOF := current.(eof); isEOF {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an end element %s, but reached the end-of-file",
{IIII}local,
{III}),
{II})
{II}return
{I}}}

{I}et, ok := current.(xml.EndElement)
{I}if !ok {{
{II}switch v := current.(type) {{
{II}case xml.StartElement:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got a start element %s in namespace %s",
{IIIII}local, v.Name.Local, v.Name.Space,
{IIII}),
{III})
{II}case xml.CharData:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got text %s",
{IIIII}local, string(v),
{IIII}),
{III})
{II}default:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got %T: %v",
{IIIII}local, current, current,
{IIII}),
{III})
{II}}}
{II}return
{I}}}

{I}if et.Name.Space != Namespace {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an end element %s in the namespace %s, "+
{IIIII}"but got an end element in the namespace %s",
{IIII}local, Namespace, et.Name.Space,
{III}),
{II})
{II}return
{I}}}

{I}if et.Name.Local != local {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an end element %s, but got an end element %s",
{IIII}local, et.Name.Local,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_scalar_definition() -> Stripped:
    return Stripped(
        f"""\
type Scalar interface {{
{I}~bool |
{I}~int |
{I}~int64 |
{I}~float64 |
{I}~string |
{I}~[]byte
}}"""
    )


def _generate_error_constructors() -> List[Stripped]:
    """Generate the constructors of the recurring de-serialization errors."""
    return [
        Stripped(
            f"""\
// Report that the required property with the given `name` has not been observed.
func missingProperty(name string) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"The required property '%s' is missing",
{III}name,
{II}),
{I})
}}"""
        ),
        Stripped(
            f"""\
// Report that we got a start element with the `local` name, but expected a start
// element with the `expectedLocal` name.
func unexpectedStartElement(local string, expectedLocal string) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected a start element with local name %s, "+
{IIII}"but got a start element with local name %s",
{III}expectedLocal, local,
{II}),
{I})
}}"""
        ),
        Stripped(
            f"""\
// Report that the start element with the `local` name does not discriminate any of
// the alternatives of `expectedType`.
func unexpectedDiscriminator(local string, expectedType string) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Unexpected start element %s as discriminator for %s",
{III}local, expectedType,
{II}),
{I})
}}"""
        ),
        Stripped(
            f"""\
// Report that we got an item delimited by a start element with the `local` name,
// but expected the delimiter with the `expectedLocal` name.
func unexpectedItemElement(local string, expectedLocal string) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected start element %s as an item delimiter, "+
{IIII}"but got %s",
{III}expectedLocal, local,
{II}),
{I})
}}"""
        ),
    ]


def _generate_read_element_dispatched() -> Stripped:
    """Generate the function to read a single value wrapped in an XML element."""
    return Stripped(
        f"""\
// Read a value wrapped in a single XML element, dispatching on the local name of
// that element.
//
// The element is read in full: the resulting `next` token points to the first token
// just after the end element.
//
// This is the *only* place which frames an XML element around a value. Both
// [readListOf] and the `readTuple*` functions delegate the framing here, so that
// a scalar item and an instance item differ only in the given `readByLocal`, and
// never in the container which reads them.
//
// `T` is left unconstrained (instead of `aastypes.IClass`) since this
// function never invokes any `aastypes.IClass` method on `T` -- this lets it
// be reused for a scalar and for a named union as well, the latter being
// deliberately not an `aastypes.IClass` itself.
func readElementDispatched[T any](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}readByLocal func(
{II}aDecoder *xml.Decoder,
{II}aCurrent xml.Token,
{II}aLocal string,
{I}) (value T, aNext xml.Token, anErr error),
) (value T, next xml.Token, err error) {{
{I}current, err = skipEmptyTextWhitespaceAndComments(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}var local string
{I}local, err = parseAsStartElementAndExtractLocalName(current)
{I}if err != nil {{
{II}return
{I}}}

{I}// Move the current to the content of the XML element
{I}current, err = readNext(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}value, current, err = readByLocal(decoder, current, local)
{I}if err != nil {{
{II}return
{I}}}

{I}err = checkEndElement(current, local)
{I}if err != nil {{
{II}return
{I}}}

{I}next, err = readNext(decoder, current)
{I}return
}}"""
    )


def _generate_read_list_of() -> Stripped:
    """Generate the function to read a list of values as a sequence of XML elements."""
    return Stripped(
        f"""\
// Read a list of values as a sequence of XML elements.
//
// Every start element is considered to mark the start of an item serialization. We
// stop the reading as soon as we encounter a non-start element.
//
// That last non-start element is returned as `next` element.
//
// An item is read with [readElementDispatched], so `readItem` decides on its own
// which local names it accepts. A list of instances and a list of scalars therefore
// share this one function: an instance is discriminated by its own element name,
// while a scalar is expected in an element named `v`.
//
// `T` is left unconstrained (instead of `aastypes.IClass`) since this
// function never invokes any `aastypes.IClass` method on `T` -- this lets it
// be reused for a list of scalars and for a list of a named union as well,
// the latter being deliberately not an `aastypes.IClass` itself.
func readListOf[T any](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}readItem func(
{II}aDecoder *xml.Decoder,
{II}aCurrent xml.Token,
{II}aLocal string,
{I}) (value T, aNext xml.Token, anErr error),
) (values []T, next xml.Token, err error) {{
{I}i := 0
{I}for {{
{II}current, err = skipEmptyTextWhitespaceAndComments(decoder, current)
{II}if err != nil {{
{III}return
{II}}}

{II}if _, ok := current.(xml.StartElement); !ok {{
{III}break
{II}}}

{II}var value T
{II}var valueErr error
{II}value, current, valueErr = readElementDispatched(
{III}decoder, current, readItem,
{II})
{II}if valueErr != nil {{
{III}if deseriaErr, ok := valueErr.(*DeserializationError); ok {{
{IIII}deseriaErr.Path.PrependIndex(
{IIIII}&aasreporting.IndexSegment{{Index: i}},
{IIII})
{III}}}
{III}err = valueErr
{III}return
{II}}}

{II}values = append(values, value)

{II}i++
{I}}}

{I}next = current
{I}return
}}"""
    )


def _generate_read_optional() -> Stripped:
    """Generate the function to turn a just-read value into a pointer."""
    return Stripped(
        f"""\
// Turn a just-read value into a pointer, so that it can be stored in an optional
// property.
//
// An optional is represented as a pointer, so the value has to live outside the
// caller's frame. This allocates exactly the one value that the caller would
// otherwise allocate by taking the address of its own local variable, and no more.
//
// The arguments are the *results* of a read, not the reader itself. Go passes
// a multi-valued call on as a complete argument list, so this composes with any read,
// no matter how many arguments that read takes on its own --
// `readOptional(readTextAsLong(decoder, current))` just as much as
// `readOptional(readTuple2(decoder, current, readXAtV1, readYAtV2))`, which no
// reader-taking signature could express, since the item readers of a tuple vary in
// number and in type.
func readOptional[T any](
{I}value T,
{I}current xml.Token,
{I}err error,
) (*T, xml.Token, error) {{
{I}if err != nil {{
{II}return nil, current, err
{I}}}

{I}return &value, current, nil
}}"""
    )


def _generate_next_property() -> Stripped:
    """Generate the function to advance to the next property of an instance."""
    return Stripped(
        f"""\
// Advance to the next property of an instance serialized as a sequence of XML
// elements, and return the `local` name of the corresponding start element.
//
// The resulting `next` token points to the content of that element.
//
// If there are no more properties, `ok` is false and `next` points to the token
// which stopped the reading, be it a non-start element or [eof].
//
// `interfaceName` is only used for error reporting.
func nextProperty(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}interfaceName string,
) (local string, next xml.Token, ok bool, err error) {{
{I}current, err = skipEmptyTextWhitespaceAndComments(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}if _, isEOF := current.(eof); isEOF {{
{II}next = current
{II}return
{I}}}

{I}startElement, isStartElement := current.(xml.StartElement)
{I}if !isStartElement {{
{II}if charData, isCharData := current.(xml.CharData); isCharData {{
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a sequence of XML elements representing properties "+
{IIIIII}"of %s, but got text: %s",
{IIIII}interfaceName, string(charData),
{IIII}),
{III})
{III}return
{II}}}

{II}next = current
{II}return
{I}}}

{I}local, err = extractLocalNameFromStartElement(startElement)
{I}if err != nil {{
{II}return
{I}}}

{I}// Move the current to the content of the XML element
{I}next, err = readNext(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}ok = true
{I}return
}}"""
    )


def _generate_conclude_property() -> Stripped:
    """Generate the function to conclude the reading of a single property."""
    return Stripped(
        f"""\
// Conclude the reading of the property delimited by the element with the `local`
// name.
//
// If `valueErr` is set, report it in the context of that property. Otherwise,
// consume the end element, so that the resulting `next` token points to the first
// token just after it.
func concludeProperty(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
{I}valueErr error,
) (next xml.Token, err error) {{
{I}if valueErr != nil {{
{II}if deseriaErr, ok := valueErr.(*DeserializationError); ok {{
{III}deseriaErr.Path.PrependName(
{IIII}&aasreporting.NameSegment{{Name: local}},
{III})
{II}}}
{II}err = valueErr
{II}return
{I}}}

{I}current, err = skipEmptyTextWhitespaceAndComments(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}err = checkEndElement(current, local)
{I}if err != nil {{
{II}return
{I}}}

{I}next, err = readNext(decoder, current)
{I}return
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_read_tuple_helper(arity: int) -> Stripped:
    """Generate a generic function to read a tuple of the given ``arity``."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    type_params_joined = ", ".join(f"{t} any" for t in type_params)

    tuple_type = f"aascommon.Tuple{arity}[{', '.join(type_params)}]"

    params_joined = ",\n".join(
        f"readItem{i + 1} func(\n"
        f"{I}aDecoder *xml.Decoder,\n"
        f"{I}aCurrent xml.Token,\n"
        f"{I}aLocal string,\n"
        f") ({type_params[i]}, xml.Token, error)"
        for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
var item{i + 1} {type_params[i]}
item{i + 1}, current, err = readElementDispatched(
{I}decoder, current, readItem{i + 1},
)
if err != nil {{
{I}if deseriaErr, ok := err.(*DeserializationError); ok {{
{II}deseriaErr.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{Index: {i}}},
{II})
{I}}}
{I}return
}}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    item_fields_joined = "\n".join(f"Item{i + 1}: item{i + 1}," for i in range(arity))

    function_name = f"readTuple{arity}"

    return Stripped(
        f"""\
// Read a tuple of {arity} item(s) with `readItem1`, `readItem2`, *etc.* on
// the correspondingly positioned item, or return an error.
//
// Each item is framed by [readElementDispatched], so an item reader accepts or
// rejects the positional element name (`v1`, `v2`, *etc.*) on its own for a scalar
// item, and discriminates on the class element name for an instance item.
func {function_name}[{type_params_joined}](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}{indent_but_first_line(params_joined, I)},
) (result {tuple_type}, next xml.Token, err error) {{
{I}{indent_but_first_line(item_blocks_joined, I)}

{I}result = {tuple_type}{{
{II}{indent_but_first_line(item_fields_joined, II)}
{I}}}
{I}next = current
{I}return
}}"""
    )


def _generate_read_text_as_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    enum_name = golang_naming.enum_name(enumeration.name)
    from_string_name = golang_naming.function_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    function_name = golang_naming.private_function_name(
        Identifier(f"read_text_as_{enumeration.name}")
    )

    return Stripped(
        f"""\
// Consume the text tokens (char data) as a string-encoded literal of
// [aastypes.{enum_name}].
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func {function_name}(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value aastypes.{enum_name},
{I}next xml.Token,
{I}err error,
) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}var ok bool
{I}value, ok = aasstringification.{from_string_name}(text)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Unexpected literal of {enum_name}: %v",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


_READ_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "readTextAsBoolean",
    intermediate.PrimitiveType.INT: "readTextAsLong",
    intermediate.PrimitiveType.FLOAT: "readTextAsDouble",
    intermediate.PrimitiveType.STR: "readText",
    intermediate.PrimitiveType.BYTEARRAY: "readTextAsBase64EncodedBytes",
}
assert all(
    literal in _READ_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


_SCALAR_NAME_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "boolean",
    intermediate.PrimitiveType.INT: "long",
    intermediate.PrimitiveType.FLOAT: "double",
    intermediate.PrimitiveType.STR: "string",
    intermediate.PrimitiveType.BYTEARRAY: "base64_encoded_bytes",
}
assert all(
    literal in _SCALAR_NAME_BY_PRIMITIVE_TYPE for literal in intermediate.PrimitiveType
)


def _read_text_function(type_anno: intermediate.AtomicTypeAnnotation) -> Stripped:
    """Determine the function which reads the text of a scalar ``type_anno``."""
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return Stripped(_READ_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type])

    assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    ), (
        f"Expected a scalar type annotation, but got {type_anno}; "
        f"the instances are read by dispatch on their own element name instead"
    )

    return Stripped(
        golang_naming.private_function_name(
            Identifier(f"read_text_as_{type_anno.our_type.name}")
        )
    )


class _ScalarItemReader:
    """
    Specify a function which reads a scalar item wrapped in a fixed element name.

    A scalar element is not self-describing: its name denotes its *position*, ``v``
    in a list and ``v1``, ``v2``, *etc.* in a tuple, and never its type. The expected
    name is therefore checked by the item reader itself, so that a container such as
    :py:func:`_generate_read_list_of` needs to know nothing about its items. See
    :py:func:`_generate_read_scalar_item` for the generated code.
    """

    def __init__(
        self,
        function_name: Identifier,
        value_type: Stripped,
        element_name: str,
        read_text_function: Stripped,
    ) -> None:
        """Initialize with the given values."""
        self.function_name = function_name
        self.value_type = value_type
        self.element_name = element_name
        self.read_text_function = read_text_function


def _to_scalar_item_reader(
    type_anno: intermediate.AtomicTypeAnnotation, element_name: str
) -> _ScalarItemReader:
    """Determine the reader of a scalar ``type_anno`` wrapped in ``element_name``."""
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        scalar_name = _SCALAR_NAME_BY_PRIMITIVE_TYPE[primitive_type]
    else:
        assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.our_type, intermediate.Enumeration
        ), (
            f"Expected a scalar type annotation, but got {type_anno}; "
            f"the instances are read by dispatch on their own element name instead"
        )

        scalar_name = type_anno.our_type.name

    return _ScalarItemReader(
        function_name=golang_naming.private_function_name(
            Identifier(f"read_{scalar_name}_at_{element_name}")
        ),
        value_type=golang_common.generate_type(
            type_annotation=type_anno, types_package=Identifier("aastypes")
        ),
        element_name=element_name,
        read_text_function=_read_text_function(type_anno),
    )


def _item_reader_name(
    type_anno: intermediate.AtomicTypeAnnotation, element_name: str
) -> Stripped:
    """
    Determine the reader of an item of ``type_anno`` wrapped in ``element_name``.

    An instance is read by dispatch on its own element name, so ``element_name`` is
    disregarded in that case.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    ):
        return Stripped(
            golang_naming.private_function_name(
                Identifier(f"read_{type_anno.our_type.name}_dispatched")
            )
        )

    return Stripped(_to_scalar_item_reader(type_anno, element_name).function_name)


def _requires_dispatch(type_anno: intermediate.TypeAnnotation) -> bool:
    """
    Check whether a *single* property of ``type_anno`` is read by dispatch.

    A single property of a concrete class without concrete descendants is wrapped in
    an element named after the *property*, not after the class, so there is no
    discriminator to dispatch on. Everything else polymorphic -- an abstract class,
    a concrete class with concrete descendants, and a named union -- is wrapped twice,
    the inner element naming the concrete alternative.
    """
    if not isinstance(type_anno, intermediate.OurTypeAnnotation):
        return False

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.ConcreteClass):
        return len(our_type.concrete_descendants) > 0

    return isinstance(our_type, (intermediate.AbstractClass, intermediate.NamedUnion))


class _ReadRequirements:
    """Specify which of the optional read functions are actually needed."""

    def __init__(
        self,
        dispatched_type_ids: Set[int],
        scalar_item_readers: List[_ScalarItemReader],
    ) -> None:
        """Initialize with the given values."""
        #: IDs of our types for which a ``read*Dispatched`` function must be generated
        self.dispatched_type_ids = dispatched_type_ids

        #: Scalar item readers to be generated, in the order of the first occurrence
        self.scalar_item_readers = scalar_item_readers


def _collect_read_requirements(
    symbol_table: intermediate.SymbolTable,
) -> _ReadRequirements:
    """
    Collect the read functions which are actually reachable from ``Unmarshal``.

    ``Unmarshal`` dispatches to ``read*AsSequence`` of *every* concrete class, so
    every concrete class is reachable, and it suffices to look at the properties of
    the concrete classes: a ``read*Dispatched`` and a scalar item reader are called
    only from a property read.
    """
    dispatched_type_ids = set()  # type: Set[int]

    scalar_item_readers = []  # type: List[_ScalarItemReader]
    observed_scalar_item_readers = set()  # type: Set[Identifier]

    def require_item_reader(
        item_type_anno: intermediate.AtomicTypeAnnotation, element_name: str
    ) -> None:
        """Require the reader of an item of ``item_type_anno`` in ``element_name``."""
        if isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
            item_type_anno.our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            dispatched_type_ids.add(id(item_type_anno.our_type))
            return

        scalar_item_reader = _to_scalar_item_reader(item_type_anno, element_name)
        if scalar_item_reader.function_name not in observed_scalar_item_readers:
            observed_scalar_item_readers.add(scalar_item_reader.function_name)
            scalar_item_readers.append(scalar_item_reader)

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(type_anno, intermediate.ListTypeAnnotation):
                assert isinstance(
                    type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
                )
                require_item_reader(type_anno.items, "v")

            elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
                for i, item_type_anno in enumerate(type_anno.items):
                    assert isinstance(
                        item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                    )
                    require_item_reader(item_type_anno, f"v{i + 1}")

            elif _requires_dispatch(type_anno):
                assert isinstance(type_anno, intermediate.OurTypeAnnotation)
                dispatched_type_ids.add(id(type_anno.our_type))

    return _ReadRequirements(
        dispatched_type_ids=dispatched_type_ids,
        scalar_item_readers=scalar_item_readers,
    )


def _generate_read_scalar_item(scalar_item_reader: _ScalarItemReader) -> Stripped:
    """Generate the function to read a scalar item at a fixed element name."""
    element_name_literal = golang_common.string_literal(scalar_item_reader.element_name)

    return Stripped(
        f"""\
// Read a scalar item expected in the element `{scalar_item_reader.element_name}`.
//
// The `current` token is expected to point to the content of that element, and
// the resulting `next` token points to its end element.
func {scalar_item_reader.function_name}(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (value {scalar_item_reader.value_type},
{I}next xml.Token,
{I}err error,
) {{
{I}if local != {element_name_literal} {{
{II}err = unexpectedItemElement(local, {element_name_literal})
{II}return
{I}}}

{I}return {scalar_item_reader.read_text_function}(decoder, current)
}}"""
    )


def _generate_snippet_to_switch_on_property_deserialization(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the switch block to dispatch how to read a property.

    The start element is expected to have been read. The variable ``local`` denotes
    the local name of the start element.

    The decoder points to the first token of the property content.

    The variables ``the*`` and ``found*`` will be set as well as ``valueErr``.
    """
    case_blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        xml_prop_literal = golang_common.string_literal(prop.xml_name)

        case_body = None  # type: Optional[Stripped]

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and isinstance(
                type_anno.our_type,
                (intermediate.ConstrainedPrimitive, intermediate.Enumeration),
            )
        ):
            read_text_function = _read_text_function(type_anno)

            if golang_pointering.is_pointer_type(prop.type_annotation):
                case_body = Stripped(
                    f"""\
{prop_var}, current, valueErr = readOptional(
{I}{read_text_function}(decoder, current),
)"""
                )
            else:
                case_body = Stripped(
                    f"""\
{prop_var}, current, valueErr = {read_text_function}(
{I}decoder, current,
)"""
                )

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type

            if isinstance(
                our_type, (intermediate.Enumeration, intermediate.ConstrainedPrimitive)
            ):
                raise AssertionError("Must have been handled before")

            elif isinstance(
                our_type,
                (
                    intermediate.AbstractClass,
                    intermediate.ConcreteClass,
                    intermediate.NamedUnion,
                ),
            ):
                if _requires_dispatch(type_anno):
                    read_dispatched = golang_naming.private_function_name(
                        Identifier(f"read_{our_type.name}_dispatched")
                    )

                    case_body = Stripped(
                        f"""\
{prop_var}, current, valueErr = readElementDispatched(
{I}decoder, current, {read_dispatched},
)"""
                    )
                else:
                    # NOTE (mristin):
                    # The property is wrapped in an element named after the property
                    # itself, and there is only a single alternative, so there is no
                    # discriminating element in-between to dispatch on.
                    read_as_sequence = golang_naming.private_function_name(
                        Identifier(f"read_{our_type.name}_as_sequence")
                    )

                    case_body = Stripped(
                        f"""\
{prop_var}, current, valueErr = {read_as_sequence}(
{I}decoder, current,
)"""
                    )

            else:
                assert_never(our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"NOTE (mristin): We expect only lists of atomic values "
                f"at the moment, but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

            read_item = _item_reader_name(type_anno.items, "v")

            case_body = Stripped(
                f"""\
{prop_var}, current, valueErr = readListOf(
{I}decoder, current, {read_item},
)"""
            )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            arity = len(type_anno.items)

            item_readers = []  # type: List[Stripped]
            for i, item_type_anno in enumerate(type_anno.items):
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    f"NOTE (mristin): We expect only tuples of atomic values "
                    f"at the moment, but you specified {type_anno}. "
                    f"Please contact the developers if you need this feature."
                )

                item_readers.append(_item_reader_name(item_type_anno, f"v{i + 1}"))

            item_readers_joined = "\n".join(
                f"{item_reader}," for item_reader in item_readers
            )

            read_tuple = Stripped(
                f"""\
readTuple{arity}(
{I}decoder, current,
{I}{indent_but_first_line(item_readers_joined, I)}
)"""
            )

            if golang_pointering.is_pointer_type(prop.type_annotation):
                # NOTE (mristin):
                # A tuple is represented as a Go struct, which is not nilable, so
                # an optional tuple is a pointer, just like an optional scalar, and
                # goes through the very same ``readOptional``.
                case_body = Stripped(
                    f"""\
{prop_var}, current, valueErr = readOptional(
{I}{indent_but_first_line(read_tuple, I)},
)"""
                )
            else:
                case_body = Stripped(f"{prop_var}, current, valueErr = {read_tuple}")

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

        assert case_body is not None

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))
            case_body = Stripped(f"{case_body}\n{found_var} = true")

        case_blocks.append(
            Stripped(
                f"""\
case {xml_prop_literal}:
{I}{indent_but_first_line(case_body, I)}"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}valueErr = newDeserializationError(
{II}"Unexpected property",
{I})"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
var valueErr error
switch local {{
{case_blocks_joined}
}}"""
    )


def _generate_read_as_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    interface_name = golang_naming.interface_name(cls.name)
    interface_name_literal = golang_common.string_literal(interface_name)

    # region Initialize

    initialization_blocks = []  # type: List[Stripped]

    prop_var_initializations = []  # type: List[Stripped]
    for prop in cls.properties:
        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        prop_var_type = golang_common.generate_type(
            type_annotation=prop.type_annotation, types_package=Identifier("aastypes")
        )

        prop_var_initializations.append(Stripped(f"var {prop_var} {prop_var_type}"))

    if len(prop_var_initializations) > 0:
        initialization_blocks.append(Stripped("\n".join(prop_var_initializations)))

    found_var_initializations = []  # type: List[Stripped]
    for prop in cls.properties:
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))

        found_var_initializations.append(Stripped(f"{found_var} := false"))

    if len(found_var_initializations) > 0:
        initialization_blocks.append(Stripped("\n".join(found_var_initializations)))

    if len(initialization_blocks) == 0:
        initialization_blocks.append(
            Stripped(
                f"""\
// No initialization as there are no properties
// in {interface_name}."""
            )
        )

    initialization = "\n\n".join(initialization_blocks)

    # endregion

    switch_snippet = _generate_snippet_to_switch_on_property_deserialization(cls=cls)

    # region Construct

    construct_blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))

        xml_prop_literal = golang_common.string_literal(prop.xml_name)

        construct_blocks.append(
            Stripped(
                f"""\
if !{found_var} {{
{I}err = missingProperty({xml_prop_literal})
{I}return
}}"""
            )
        )

    constructing_statements = []  # type: List[Stripped]

    constructor_arguments = [
        golang_naming.variable_name(Identifier(f"the_{arg.name}"))
        for arg in cls.constructor.arguments
        if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation)
    ]  # type: List[Stripped]

    new_function = golang_naming.function_name(Identifier(f"new_{cls.name}"))

    if len(constructor_arguments) > 0:
        constructor_arguments_joined = "\n".join(
            f"{arg}," for arg in constructor_arguments
        )

        constructing_statements.append(
            Stripped(
                f"""\
instance = aastypes.{new_function}(
{I}{indent_but_first_line(constructor_arguments_joined, I)}
)"""
            )
        )
    else:
        constructing_statements.append(
            Stripped(f"instance = aastypes.{new_function}()")
        )

    for arg in cls.constructor.arguments:
        if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        setter_name = golang_naming.setter_name(arg.name)
        prop_var = golang_naming.variable_name(Identifier(f"the_{arg.name}"))

        constructing_statements.append(Stripped(f"instance.{setter_name}({prop_var})"))

    construct_blocks.append(Stripped("\n".join(constructing_statements)))

    construct = "\n\n".join(construct_blocks)

    # endregion

    function_name = golang_naming.private_function_name(
        Identifier(f"read_{cls.name}_as_sequence")
    )

    return Stripped(
        f"""\
// De-serialize the instance of [aastypes.{interface_name}]
// as a sequence of XML elements, each representing a property
// of [aastypes.{interface_name}].
//
// The reading stops as soon as we encounter a non-start element, and we return
// that token as the `next` token.
func {function_name}(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (instance aastypes.{interface_name},
{I}next xml.Token,
{I}err error,
) {{
{I}{indent_but_first_line(initialization, I)}

{I}for {{
{II}var local string
{II}var ok bool
{II}local, current, ok, err = nextProperty(decoder, current, {interface_name_literal})
{II}if err != nil {{
{III}return
{II}}}
{II}if !ok {{
{III}break
{II}}}

{II}{indent_but_first_line(switch_snippet, II)}

{II}current, err = concludeProperty(decoder, current, local, valueErr)
{II}if err != nil {{
{III}return
{II}}}
{I}}}

{I}next = current

{I}{indent_but_first_line(construct, I)}
{I}return
}}"""
    )


def _generate_read_dispatched(
    our_type: Union[intermediate.ClassUnion, intermediate.NamedUnion]
) -> Stripped:
    """
    Generate the function to read an instance of ``our_type`` by its element name.

    An instance element is self-describing: its local name *is* its type. This one
    function covers every such case -- an abstract class dispatches over its concrete
    descendants, a concrete class over its concrete descendants and itself, and
    a named union over its implementers. A concrete class without concrete descendants
    thus degenerates to a single alternative, which is still worth a function: it is
    what lets [readListOf] and the ``readTuple*`` functions read an item without
    knowing anything about it.

    The element framing is deliberately *not* part of the generated function. It lives
    in ``readElementDispatched`` alone (see
    :py:func:`_generate_read_element_dispatched`), which every container delegates to.
    """
    if isinstance(our_type, intermediate.NamedUnion):
        alternatives = list(
            our_type.implementers
        )  # type: List[intermediate.ConcreteClass]
        union_name = golang_naming.union_name(our_type.name)
        value_type = Stripped(f"*aastypes.{union_name}")
        doc_reference = Stripped(f"aastypes.{union_name}")
        default_error = Stripped(
            f"unexpectedDiscriminator(local, "
            f"{golang_common.string_literal(f'the union {union_name}')})"
        )
    else:
        alternatives = list(our_type.concrete_descendants)
        if isinstance(our_type, intermediate.ConcreteClass):
            alternatives.append(our_type)

        interface_name = golang_naming.interface_name(our_type.name)
        value_type = Stripped(f"aastypes.{interface_name}")
        doc_reference = Stripped(f"aastypes.{interface_name}")

        if isinstance(our_type, intermediate.ConcreteClass) and (
            len(our_type.concrete_descendants) == 0
        ):
            # NOTE (mristin):
            # There is only a single alternative, so naming it in the error message
            # is more informative than pointing at a discriminator which does not
            # actually discriminate anything.
            default_error = Stripped(
                f"unexpectedStartElement(local, "
                f"{golang_common.string_literal(naming.xml_class_name(our_type.name))})"
            )
        else:
            default_error = Stripped(
                f"unexpectedDiscriminator(local, "
                f"{golang_common.string_literal(interface_name)})"
            )

    case_blocks = []  # type: List[Stripped]

    for alternative in alternatives:
        xml_class_name_literal = golang_common.string_literal(
            naming.xml_class_name(alternative.name)
        )
        read_as_sequence = golang_naming.private_function_name(
            Identifier(f"read_{alternative.name}_as_sequence")
        )

        if isinstance(our_type, intermediate.NamedUnion):
            alternative_interface_name = golang_naming.interface_name(alternative.name)
            from_function_name = golang_naming.function_name(
                Identifier(f"new_{our_type.name}_from_{alternative.name}")
            )

            case_blocks.append(
                Stripped(
                    f"""\
case {xml_class_name_literal}:
{I}var casted aastypes.{alternative_interface_name}
{I}casted, next, err = {read_as_sequence}(decoder, current)
{I}if err == nil {{
{II}instance = aastypes.{from_function_name}(casted)
{I}}}"""
                )
            )
        else:
            case_blocks.append(
                Stripped(
                    f"""\
case {xml_class_name_literal}:
{I}instance, next, err = {read_as_sequence}(decoder, current)"""
                )
            )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = {default_error}"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    function_name = golang_naming.private_function_name(
        Identifier(f"read_{our_type.name}_dispatched")
    )

    return Stripped(
        f"""\
// De-serialize an instance of [{doc_reference}] based on the `local` name
// of its start element.
//
// The `current` token is expected to point to the content of that start element, and
// the resulting `next` token points to its end element.
func {function_name}(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (instance {value_type},
{I}next xml.Token,
{I}err error,
) {{
{I}switch local {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}
{I}return
}}"""
    )


def _generate_read_class_dispatched(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the function to read any instance by its element name."""
    case_blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        read_as_sequence = golang_naming.private_function_name(
            Identifier(f"read_{cls.name}_as_sequence")
        )

        xml_class_name_literal = golang_common.string_literal(
            naming.xml_class_name(cls.name)
        )

        case_blocks.append(
            Stripped(
                f"""\
case {xml_class_name_literal}:
{I}instance, next, err = {read_as_sequence}(decoder, current)"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = newDeserializationError(
{II}fmt.Sprintf(
{III}"Unexpected XML element name %s as class discriminator",
{III}local,
{II}),
{I})"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
// De-serialize an instance of [aastypes.IClass] based on the `local` name
// of its start element.
//
// The `current` token is expected to point to the content of that start element, and
// the resulting `next` token points to its end element.
func readClassDispatched(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (instance aastypes.IClass,
{I}next xml.Token,
{I}err error,
) {{
{I}switch local {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}
{I}return
}}"""
    )


def _generate_unmarshal() -> Stripped:
    return Stripped(
        f"""\
// Unmarshal an instance of [aastypes.IClass] serialized as an XML element.
//
// The XML element must live in the [Namespace] space.
func Unmarshal(
{I}decoder *xml.Decoder,
) (instance aastypes.IClass, err error) {{
{I}var current xml.Token
{I}current, err = readNext(decoder, nil)
{I}if err != nil {{
{II}return
{I}}}

{I}instance, _, err = readElementDispatched(
{II}decoder, current, readClassDispatched,
{I})
{I}return
}}"""
    )


# endregion

# region Serialization


def _generate_serialization_error() -> List[Stripped]:
    return [
        Stripped(
            f"""\
// Represent an error during the serialization.
//
// Implements `error`.
type SerializationError struct {{
{I}Path    *aasreporting.Path
{I}Message string
}}"""
        ),
        Stripped(
            f"""\
func newSerializationError(message string) *SerializationError {{
{I}return &SerializationError{{
{II}Path:    &aasreporting.Path{{}},
{II}Message: message,
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func (se *SerializationError) Error() string {{
{I}return fmt.Sprintf(
{II}"%s: %s",
{II}se.PathString(),
{II}se.Message,
{I})
}}"""
        ),
        Stripped(
            f"""\
// Render the path as a string.
func (se *SerializationError) PathString() string {{
{I}return aasreporting.ToGolangPath(se.Path)
}}"""
        ),
    ]


def _generate_write_start_element() -> Stripped:
    return Stripped(
        f"""\
// Write the start element with the given `local` name to the encoder.
//
// Do not flush.
//
// If the `withNamespace` is set, set the [xml.Name.Space] property in the element
// accordingly.
func writeStartElement(
{I}encoder *xml.Encoder,
{I}local string,
{I}withNamespace bool,
) (err error) {{
{I}startElement := xml.StartElement{{Name: xml.Name{{Local: local}}}}
{I}if withNamespace {{
{II}startElement.Name.Space = Namespace
{I}}}

{I}err = encoder.EncodeToken(startElement)
{I}return
}}"""
    )


def _generate_write_end_element() -> Stripped:
    return Stripped(
        f"""\
// Write the end element with the given `local` name to the encoder.
//
// Do not flush.
//
// If the `withNamespace` is set, set the [xml.Name.Space] property in the element
// accordingly.
func writeEndElement(
{I}encoder *xml.Encoder,
{I}local string,
{I}withNamespace bool,
) (err error) {{
{I}endElement := xml.EndElement{{Name: xml.Name{{Local: local}}}}
{I}if withNamespace {{
{II}endElement.Name.Space = Namespace
{I}}}

{I}err = encoder.EncodeToken(endElement)
{I}return
}}"""
    )


def _generate_write_text() -> Stripped:
    return Stripped(
        f"""\
// Write the `text` to the encoder.
//
// Do not flush.
//
// If `text` is empty, do nothing.
func writeText(
{I}encoder *xml.Encoder,
{I}text string,
) (err error) {{
{I}if len(text) > 0 {{
{II}err = encoder.EncodeToken(
{III}xml.CharData([]byte(text)),
{II})
{I}}}
{I}return
}}"""
    )


def _generate_write_boolean_as_text() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:boolean` in a text element.
//
// Do not flush.
func writeBooleanAsText(
{I}encoder *xml.Encoder,
{I}value bool,
) (err error) {{
{I}text := "true"
{I}if !value {{
{II}text = "false"
{I}}}
{I}err = writeText(encoder, text)
{I}return
}}"""
    )


def _generate_write_long_as_text() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:long` in a text element.
//
// Do not flush.
func writeLongAsText(
{I}encoder *xml.Encoder,
{I}value int64,
) (err error) {{
{I}text := strconv.FormatInt(value, 10)
{I}err = writeText(encoder, text)
{I}return
}}"""
    )


def _generate_write_double_as_text() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:double` in a text element.
//
// Do not flush.
func writeDoubleAsText(
{I}encoder *xml.Encoder,
{I}value float64,
) (err error) {{
{I}var text string

{I}// See: https://www.w3.org/TR/xmlschema-2/#double
{I}// for the exact literals.
{I}if math.IsInf(value, 0) {{
{II}if value < 0 {{
{III}text = "-INF"
{II}}} else {{
{III}text = "INF"
{II}}}
{I}}} else if math.IsNaN(value) {{
{II}text = "NaN"
{I}}} else {{
{II}text = strconv.FormatFloat(value, 'g', -1, 64)
{I}}}

{I}err = writeText(encoder, text)
{I}return
}}"""
    )


def _generate_write_string_as_text() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:string` in a text element.
//
// Do not flush.
func writeStringAsText(
{I}encoder *xml.Encoder,
{I}value string,
) (err error) {{
{I}err = writeText(encoder, value)
{I}return
}}"""
    )


def _generate_write_bytes_as_text() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a base64-encoded bytes in a text element.
//
// Do not flush.
func writeBytesAsText(
{I}encoder *xml.Encoder,
{I}value []byte,
) (err error) {{
{I}text := b64.StdEncoding.EncodeToString(
{II}value,
{I})

{I}err = writeText(encoder, text)
{I}return
}}"""
    )


# NOTE (mristin):
# We provide wrapper function for scalar values to reduce
# the already copious amounts of generated code. While it might seem like unnecessary
# abstraction (basically just a start element, a call to writeXxxAsText, and an end
# element), it still reduces the lines of generated code substantially.
#
# In addition, we also re-use the writeXxxAsText in writeListOfScalarsProperty.


def _generate_write_scalar_property() -> Stripped:
    return Stripped(
        f"""\
// Write the scalar `value` of a property enclosed in an XML element.
//
// Do not flush.
//
// The XML namespace is expected to have been defined outside of the resulting XML
// element.
func writeScalarProperty[T Scalar](
{I}encoder *xml.Encoder,
{I}local string,
{I}value T,
{I}writeTAsText func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}err = writeStartElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeTAsText(encoder, value)
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeEndElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_as_scalar_tuple_item_writer() -> Stripped:
    """
    Generate the adapter to bind a scalar writer's name for a tuple item.

    ``writeTupleN`` (see :py:func:`_generate_write_tuple_helper`) expects a
    uniform ``func(encoder, value T) error`` per item, so that a single
    generic function can be shared by *every* tuple-typed property of a
    given arity, regardless of which mix of scalar and instance items
    appears at each position (an instance item is adapted instead by
    :py:func:`_generate_as_instance_tuple_item_writer`). A scalar item,
    unlike a list item, is wrapped in a positional element name (``v1``,
    ``v2``, *etc.*) instead of always the fixed ``v`` -- this name is a
    runtime string that differs at every call site, so it must be bound in
    via a closure (Go has no partial-application syntax); this adapter
    builds that closure once, instead of repeating it inline at every such
    tuple item.
    """
    return Stripped(
        f"""\
// Adapt `writeTAsText` together with `name` into a tuple item writer.
//
// `name` (`v1`, `v2`, ...) is a plain runtime string, not a type, so it
// can not be pinned via a generic type parameter the way
// `asInstanceTupleItemWriter` pins its own type parameter -- binding it
// requires an actual closure, built once here.
func asScalarTupleItemWriter[T Scalar](
{I}name string,
{I}writeTAsText func(anEncoder *xml.Encoder, aValue T) (anErr error),
) func(encoder *xml.Encoder, value T) error {{
{I}return func(encoder *xml.Encoder, value T) error {{
{II}return writeScalarProperty(encoder, name, value, writeTAsText)
{I}}}
}}"""
    )


def _generate_as_instance_tuple_item_writer() -> Stripped:
    """
    Generate the adapter so an instance can be written as a tuple item writer.

    See :py:func:`_generate_as_scalar_tuple_item_writer` for why
    ``writeTupleN`` needs this uniform shape. Unlike the scalar adapter
    above -- and unlike the read side, which needs no adapter whatsoever,
    as every item reader there is a generated top-level function (see
    :py:func:`_generate_read_dispatched` and
    :py:func:`_generate_read_scalar_item`) -- no closure is needed here at
    all: every class shares the very same
    ``Marshal`` function (there is no per-class function value to bind in),
    so the only thing that varies per tuple item is the *type* parameter
    ``T``. ``Marshal`` itself takes the wide ``aastypes.IClass``, which can
    not be used as a ``func(encoder, value T) error`` for a tuple item's own
    (more specific) interface type -- Go function values are invariant in
    their parameter type (no contravariance, verified against the
    compiler) -- so this plain generic function exists solely to narrow
    the parameter type to ``T``. Go can not infer ``T`` for it from
    context, so every call site instantiates it explicitly, *e.g.*,
    ``asInstanceTupleItemWriter[ISomeItem]`` -- passed on as that
    instantiated function value directly (no call, no closure), since
    Go allows referencing a generic function this way without invoking it.
    """
    return Stripped(
        f"""\
// Adapt `Marshal` into a tuple item writer for instances of `T`.
func asInstanceTupleItemWriter[T aastypes.IClass](encoder *xml.Encoder, value T) error {{
{I}return Marshal(encoder, value, false)
}}"""
    )


def _generate_named_union_constraint() -> Stripped:
    """
    Generate the constraint interface shared by the named-union writers.

    A named union is deliberately not an ``aastypes.IClass``, but every
    named union exposes its underlying instance through ``Underlying`` --
    constraining a generic type parameter to that single method lets one
    writer serve every named union, instead of generating one dedicated,
    non-generic writer per union.
    """
    return Stripped(
        f"""\
// Constrain a generic type to a named union, giving access to its
// underlying instance for serialization.
type namedUnion interface {{
{I}Underlying() aastypes.IClass
}}"""
    )


def _generate_write_list_of_union_instances_property() -> Stripped:
    """
    Generate a list writer for named-union items.

    Unlike :py:func:`_generate_write_list_of_instances_property`, this
    writer calls ``Marshal`` on each item's *underlying* instance -- through
    the :py:func:`_generate_named_union_constraint` constraint -- since a
    named union is deliberately not an ``aastypes.IClass`` itself. This
    avoids first copying the list into a fresh ``[]aastypes.IClass`` slice
    just to satisfy that constraint.
    """
    return Stripped(
        f"""\
// Serialize the list of named-union instances as a sequence of XML elements
// enclosed in a parent XML element with the `local` name.
func writeListOfUnionInstancesProperty[T namedUnion](
{I}encoder *xml.Encoder,
{I}local string,
{I}list []T,
) (err error) {{
{I}err = writeStartElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}for i, item := range list {{
{II}err = Marshal(
{III}encoder,
{III}item.Underlying(),
{III}false,
{II})
{II}if err != nil {{
{III}if seriaErr, ok := err.(*SerializationError); ok {{
{IIII}seriaErr.Path.PrependIndex(
{IIIII}&aasreporting.IndexSegment{{
{IIIIII}Index: i,
{IIIII}}},
{IIII})
{III}}}
{III}return
{II}}}
{I}}}

{I}err = writeEndElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_write_union_as_tuple_item() -> Stripped:
    """
    Generate the adapter so a named union can be written as a tuple item writer.

    See :py:func:`_generate_as_instance_tuple_item_writer` for why
    ``writeTupleN`` needs this uniform shape. ``Marshal`` requires an
    ``aastypes.IClass``, which a named union is deliberately not, so this
    adapter narrows through the :py:func:`_generate_named_union_constraint`
    constraint instead -- one generic adapter thus covers every named union.
    """
    return Stripped(
        f"""\
// Adapt `Marshal` into a tuple item writer for a named union.
func writeUnionAsTupleItem[T namedUnion](encoder *xml.Encoder, value T) error {{
{I}return Marshal(encoder, value.Underlying(), false)
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_write_tuple_helper(arity: int) -> Stripped:
    """Generate a generic function to write a tuple of the given ``arity``."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    type_params_joined = ", ".join(f"{t} any" for t in type_params)

    tuple_type = f"aascommon.Tuple{arity}[{', '.join(type_params)}]"

    params_joined = ",\n".join(
        f"writeItem{i + 1} func(encoder *xml.Encoder, value {type_params[i]}) error"
        for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
err = writeItem{i + 1}(encoder, that.Item{i + 1})
if err != nil {{
{I}if seriaErr, ok := err.(*SerializationError); ok {{
{II}seriaErr.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{Index: {i}}},
{II})
{I}}}
{I}return
}}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    function_name = f"writeTuple{arity}"

    return Stripped(
        f"""\
// Write `that` with `writeItem1`, `writeItem2`, *etc.* on the
// correspondingly positioned item, or return an error.
func {function_name}[{type_params_joined}](
{I}encoder *xml.Encoder,
{I}that {tuple_type},
{I}{indent_but_first_line(params_joined, I)},
) (err error) {{
{I}{indent_but_first_line(item_blocks_joined, I)}

{I}return
}}"""
    )


def _generate_write_embedded_instance_property() -> Stripped:
    return Stripped(
        f"""\
// Serialize the `instance` as a sequence of elements directly embedded
// in an XML element with `local` name representing the property.
//
// Do not flush.
func writeEmbeddedInstanceProperty[T aastypes.IClass](
{I}encoder *xml.Encoder,
{I}local string,
{I}instance T,
{I}writeTAsSequence func(anEncoder *xml.Encoder, that T) (anErr error),
) (err error) {{
{I}err = writeStartElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeTAsSequence(
{II}encoder,
{II}instance,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeEndElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}return
}}"""
    )


def _generate_write_instance_property_with_discriminator() -> Stripped:
    return Stripped(
        f"""\
// Serialize the `instance` as a sequence of elements within a discriminator
// element which is then embedded in an XML element with `local` name
// representing the property.
//
// Do not flush.
func writeDiscriminatedInstanceProperty(
{I}encoder *xml.Encoder,
{I}local string,
{I}instance aastypes.IClass,
) (err error) {{
{I}err = writeStartElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}err = Marshal(
{II}encoder,
{II}instance,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeEndElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_write_list_of_instances_property() -> Stripped:
    return Stripped(
        f"""\
// Serialize the list of instances as a sequence of XML elements enclosed in a parent
// XML element with the `local` name.
func writeListOfInstancesProperty[T aastypes.IClass](
{I}encoder *xml.Encoder,
{I}local string,
{I}list []T,
) (err error) {{
{I}err = writeStartElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}for i, item := range list {{
{II}err = Marshal(
{III}encoder,
{III}item,
{III}false,
{II})
{II}if err != nil {{
{III}if seriaErr, ok := err.(*SerializationError); ok {{
{IIII}seriaErr.Path.PrependIndex(
{IIIII}&aasreporting.IndexSegment{{
{IIIIII}Index: i,
{IIIII}}},
{IIII})
{III}}}
{III}return
{II}}}
{I}}}

{I}err = writeEndElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_write_list_of_scalars_property() -> Stripped:
    return Stripped(
        f"""\
// Serialize the list of scalars as a sequence of XML `<v>` elements
// enclosed in a parent XML element with the `local` name.
func writeListOfScalarsProperty[T Scalar](
{I}encoder *xml.Encoder,
{I}local string,
{I}list []T,
{I}writeTAsText func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}err = writeStartElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}for i, item := range list {{
{II}err = writeStartElement(
{III}encoder,
{III}"v",
{III}false,
{II})
{II}if err != nil {{
{III}return
{II}}}

{II}err = writeTAsText(encoder, item)
{II}if err != nil {{
{III}if seriaErr, ok := err.(*SerializationError); ok {{
{IIII}seriaErr.Path.PrependIndex(
{IIIII}&aasreporting.IndexSegment{{
{IIIIII}Index: i,
{IIIII}}},
{IIII})
{III}}}
{III}return
{II}}}

{II}err = writeEndElement(
{III}encoder,
{III}"v",
{III}false,
{II})
{II}if err != nil {{
{III}return
{II}}}
{I}}}

{I}err = writeEndElement(
{II}encoder,
{II}local,
{II}false,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_write_enumeration_as_text(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    enum_name = golang_naming.enum_name(enumeration.name)
    function_name = golang_naming.private_function_name(
        Identifier(f"write_{enumeration.name}_as_text")
    )
    to_string_name = golang_naming.function_name(
        Identifier(f"{enumeration.name}_to_string")
    )

    return Stripped(
        f"""\
// Write the `value` of a property as string representation
// of [aastypes.{enum_name}]
// in a text element.
//
// Do not flush.
func {function_name}(
{I}encoder *xml.Encoder,
{I}value aastypes.{enum_name},
) (err error) {{
{I}text, ok := aasstringification.{to_string_name}(
{II}value,
{I})
{I}if !ok {{
{II}err = newSerializationError(
{III}fmt.Sprintf(
{IIII}"Unexpected literal of {enum_name}: %v",
{IIII}value,
{III}),
{II})
{II}return
{I}}}

{I}err = writeText(encoder, text)
{I}return
}}"""
    )


_WRITE_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "writeBooleanAsText",
    intermediate.PrimitiveType.INT: "writeLongAsText",
    intermediate.PrimitiveType.FLOAT: "writeDoubleAsText",
    intermediate.PrimitiveType.STR: "writeStringAsText",
    intermediate.PrimitiveType.BYTEARRAY: "writeBytesAsText",
}
assert all(
    literal in _WRITE_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


def _generate_snippet_to_serialize_property(prop: intermediate.Property) -> Stripped:
    blocks = []  # type: List[Stripped]

    local_literal = golang_common.string_literal(prop.xml_name)

    segment_name_literal = golang_common.string_literal(
        f"{golang_naming.getter_name(prop.name)}()"
    )

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    getter_name = golang_naming.getter_name(prop.name)
    access_expr = f"that.{getter_name}()"
    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))
        access_expr = prop_var

        blocks.append(
            Stripped(
                f"""\
{prop_var} := that.{getter_name}()"""
            )
        )

    if_err_nil_prepend_name_if_serialization_error_return = Stripped(
        f"""\
if err != nil {{
{I}if seriaErr, ok := err.(*SerializationError); ok {{
{II}seriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {segment_name_literal},
{III}}},
{II})
{I}}}
{I}return
}}"""
    )

    write_block = None  # type: Optional[Stripped]

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
        isinstance(type_anno, intermediate.OurTypeAnnotation)
        and isinstance(
            type_anno.our_type,
            (intermediate.ConstrainedPrimitive, intermediate.Enumeration),
        )
    ):
        primitive_type = intermediate.try_primitive_type(type_anno)

        if primitive_type is not None:
            write_function = _WRITE_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type]
        else:
            assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
                type_anno.our_type, intermediate.Enumeration
            )
            write_function = golang_naming.private_function_name(
                Identifier(f"write_{type_anno.our_type.name}_as_text")
            )

        pointer = golang_pointering.is_pointer_type(prop.type_annotation)

        if pointer:
            write_block = Stripped(
                f"""\
err = writeScalarProperty(
{I}encoder,
{I}{local_literal},
{I}*{access_expr},
{I}{write_function},
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
            )
        else:
            write_block = Stripped(
                f"""\
err = writeScalarProperty(
{I}encoder,
{I}{local_literal},
{I}{access_expr},
{I}{write_function},
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
            )

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            raise AssertionError("Must have been handled before")

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("Must have been handled before")

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if (
                isinstance(our_type, intermediate.ConcreteClass)
                and len(our_type.concrete_descendants) == 0
            ):
                write_as_sequence_function = golang_naming.private_function_name(
                    Identifier(f"write_{our_type.name}_as_sequence")
                )
                write_block = Stripped(
                    f"""\
err = writeEmbeddedInstanceProperty(
{I}encoder,
{I}{local_literal},
{I}{access_expr},
{I}{write_as_sequence_function},
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
                )
            else:
                write_block = Stripped(
                    f"""\
err = writeDiscriminatedInstanceProperty(
{I}encoder,
{I}{local_literal},
{I}{access_expr},
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
                )

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union always takes the discriminator-nesting code
            # path, exactly like a polymorphic class, so this branch mirrors
            # the polymorphic-class branch above -- we keep it separate, as
            # its own branch, so that it can diverge independently, *e.g.*,
            # if primitive alternatives are ever allowed into a named union.
            write_block = Stripped(
                f"""\
err = writeDiscriminatedInstanceProperty(
{I}encoder,
{I}{local_literal},
{I}{access_expr}.Underlying(),
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
            )

        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            f"NOTE (mristin): We expect only lists of atomic values "
            f"at the moment, but you specified {type_anno}. "
            f"Please contact the developers if you need this feature."
        )

        if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation) or (
            isinstance(type_anno.items, intermediate.OurTypeAnnotation)
            and isinstance(
                type_anno.items.our_type,
                (intermediate.ConstrainedPrimitive, intermediate.Enumeration),
            )
        ):
            items_primitive_type = intermediate.try_primitive_type(type_anno.items)

            if items_primitive_type is not None:
                write_function = _WRITE_FUNCTION_BY_PRIMITIVE_TYPE[items_primitive_type]
            else:
                assert isinstance(
                    type_anno.items, intermediate.OurTypeAnnotation
                ) and isinstance(type_anno.items.our_type, intermediate.Enumeration)
                write_function = golang_naming.private_function_name(
                    Identifier(f"write_{type_anno.items.our_type.name}_as_text")
                )

            write_block = Stripped(
                f"""\
err = writeListOfScalarsProperty(
{I}encoder,
{I}{local_literal},
{I}{access_expr},
{I}{write_function},
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
            )
        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.items.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            write_block = Stripped(
                f"""\
err = writeListOfInstancesProperty(
{I}encoder,
{I}{local_literal},
{I}{access_expr},
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
            )

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.items.our_type, intermediate.NamedUnion
        ):
            write_block = Stripped(
                f"""\
err = writeListOfUnionInstancesProperty(
{I}encoder,
{I}{local_literal},
{I}{access_expr},
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
            )

        else:
            raise AssertionError(
                f"Unexpected list item type annotation: {type_anno.items}"
            )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        arity = len(type_anno.items)

        item_writer_exprs = []  # type: List[Stripped]

        for i, item_type_anno in enumerate(type_anno.items):
            if isinstance(
                item_type_anno, intermediate.OurTypeAnnotation
            ) and isinstance(
                item_type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                item_type = golang_common.generate_type(
                    type_annotation=item_type_anno, types_package=Identifier("aastypes")
                )

                item_writer_exprs.append(
                    Stripped(f"asInstanceTupleItemWriter[{item_type}],")
                )

            elif isinstance(
                item_type_anno, intermediate.OurTypeAnnotation
            ) and isinstance(item_type_anno.our_type, intermediate.NamedUnion):
                item_type = golang_common.generate_type(
                    type_annotation=item_type_anno, types_package=Identifier("aastypes")
                )

                item_writer_exprs.append(
                    Stripped(f"writeUnionAsTupleItem[{item_type}],")
                )

            else:
                if isinstance(
                    item_type_anno, intermediate.OurTypeAnnotation
                ) and isinstance(item_type_anno.our_type, intermediate.Enumeration):
                    write_function = golang_naming.private_function_name(
                        Identifier(f"write_{item_type_anno.our_type.name}_as_text")
                    )
                else:
                    items_primitive_type = intermediate.try_primitive_type(
                        item_type_anno
                    )
                    assert items_primitive_type is not None
                    write_function = _WRITE_FUNCTION_BY_PRIMITIVE_TYPE[
                        items_primitive_type
                    ]

                v_name_literal = golang_common.string_literal(f"v{i + 1}")

                item_writer_exprs.append(
                    Stripped(
                        f"asScalarTupleItemWriter({v_name_literal}, {write_function}),"
                    )
                )

        item_writer_exprs_joined = "\n".join(item_writer_exprs)

        write_block = Stripped(
            f"""\
err = writeStartElement(
{I}encoder,
{I}{local_literal},
{I}false,
)
if err != nil {{
{I}return
}}

err = writeTuple{arity}(
{I}encoder,
{I}{access_expr},
{I}{indent_but_first_line(item_writer_exprs_joined, I)}
)
if err != nil {{
{I}return
}}

err = writeEndElement(
{I}encoder,
{I}{local_literal},
{I}false,
)
{if_err_nil_prepend_name_if_serialization_error_return}"""
        )

    else:
        assert_never(type_anno)

    assert write_block is not None

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        blocks.append(
            Stripped(
                f"""\
if {access_expr} != nil {{
{I}{indent_but_first_line(write_block, I)}
}}"""
            )
        )
    else:
        blocks.append(write_block)

    blocks.append(
        Stripped(
            f"""\
err = encoder.Flush()
if err != nil {{
{I}return err
}}"""
        )
    )

    blocks.insert(0, Stripped(f"// region {getter_name}"))
    blocks.append(Stripped("// endregion"))

    return Stripped("\n\n".join(blocks))


def _generate_write_as_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    function_name = golang_naming.private_function_name(
        Identifier(f"write_{cls.name}_as_sequence")
    )

    interface_name = golang_naming.interface_name(cls.name)

    prop_blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        prop_blocks.append(_generate_snippet_to_serialize_property(prop=prop))

    if len(prop_blocks) == 0:
        prop_blocks.append(Stripped("// Intentionally empty."))

    prop_blocks_joined = "\n\n".join(prop_blocks)

    return Stripped(
        f"""\
// Serialize the instance
// of [aastypes.{interface_name}]
// as a sequence of properties, each represented as an XML element.
//
// The XML namespace is expected to be set in the one of the parent elements
// enclosing the sequence.
//
// Flush at the end element of each property.
func {function_name}(
{I}encoder *xml.Encoder,
{I}that aastypes.{interface_name},
) (err error) {{
{I}{indent_but_first_line(prop_blocks_joined, I)}

{I}return
}}"""
    )


def _generate_write_for(cls: intermediate.ConcreteClass) -> Stripped:
    interface_name = golang_naming.interface_name(cls.name)

    if len(cls.concrete_descendants) == 0:
        function_name = golang_naming.private_function_name(
            Identifier(f"write_{cls.name}")
        )
        doc_comment = Stripped(
            f"""\
// Serialize the instance of [aastypes.{interface_name}]
// enclosed in an XML element which represents the model type.
//
// If `withNamespace` is set, the `xmlns` attribute is set in the outer XML element.
//
// Flush once the closing end element has been written."""
        )
    else:
        model_type_literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=cls.name
        )

        doc_comment = Stripped(
            f"""\
// Serialize the instance of [aastypes.{interface_name}]
// enclosed in an XML element which represents the model type.
//
// Do not dispatch on the runtime model type, *i.e.*, assume that the runtime model type
// is exactly [aastypes.{model_type_literal}]. If you need dispatch,
// call [Marshal].
//
// If `withNamespace` is set, the `xmlns` attribute is set in the outer XML element.
//
// Flush once the closing end element has been written."""
        )

        function_name = golang_naming.private_function_name(
            Identifier(f"write_{cls.name}_without_dispatch")
        )

    xml_class_name_literal = golang_common.string_literal(
        naming.xml_class_name(cls.name)
    )

    write_as_sequence_name = golang_naming.private_function_name(
        Identifier(f"write_{cls.name}_as_sequence")
    )

    return Stripped(
        f"""\
{doc_comment}
func {function_name}(
{I}encoder *xml.Encoder,
{I}that aastypes.{interface_name},
{I}withNamespace bool,
) (err error) {{
{I}local := {xml_class_name_literal}
{I}
{I}err = writeStartElement(
{II}encoder,
{II}local,
{II}withNamespace,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}err = {write_as_sequence_name}(
{II}encoder,
{II}that,
{I})
{I}if err != nil {{
{II}return
{I}}}
{I}
{I}err = writeEndElement(
{II}encoder,
{II}local,
{II}withNamespace,
{I})
{I}if err != nil {{
{II}return
{I}}}

{I}err = encoder.Flush()
{I}return
}}"""
    )


def _generate_marshal(symbol_table: intermediate.SymbolTable) -> Stripped:
    case_blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        model_type_literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=cls.name
        )

        interface_name = golang_naming.interface_name(cls.name)

        if len(cls.concrete_descendants) == 0:
            write_function = golang_naming.private_function_name(
                Identifier(f"write_{cls.name}")
            )
        else:
            write_function = golang_naming.private_function_name(
                Identifier(f"write_{cls.name}_without_dispatch")
            )

        case_blocks.append(
            Stripped(
                f"""\
case aastypes.{model_type_literal}:
{I}err = {write_function}(
{II}encoder,
{II}that.(aastypes.{interface_name}),
{II}withNamespace,
{I})"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = newSerializationError(
{II}fmt.Sprintf(
{III}"Unexpected model type: %v",
{III}that.ModelType(),
{II}),
{I})"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)
    model_type_getter = golang_naming.getter_name(Identifier("model_type"))

    return Stripped(
        f"""\
// Serialize `that` instance as an XML element.
//
// If `withNamespace` is set, the `xmlns` attribute is set in the XML element
// to [Namespace].
func Marshal(
{I}encoder *xml.Encoder,
{I}that aastypes.IClass,
{I}withNamespace bool,
) (err error) {{
{I}switch that.{model_type_getter}() {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}
{I}return
}}"""
    )


# endregion

# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for XML de/serialization."""
    aascommon_url_literal = golang_common.string_literal(f"{repo_url}/common")

    aastypes_url_literal = golang_common.string_literal(f"{repo_url}/types")

    aasreporting_url_literal = golang_common.string_literal(f"{repo_url}/reporting")

    aasstringification_url_literal = golang_common.string_literal(
        f"{repo_url}/stringification"
    )

    namespace_literal = golang_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    blocks = [
        Stripped(
            """\
// Package xmlization de/serializes model instances to and from XML.
//
// To de-serialize, call one of the `Unmarshal*` functions.
//
// To serialize, call the [Marshal] function.
package xmlization"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}b64 "encoding/base64"
{I}"encoding/xml"
{I}"fmt"
{I}"io"
{I}"math"
{I}"regexp"
{I}"strconv"
{I}"strings"
{I}"unicode"
{I}aascommon {aascommon_url_literal}
{I}aasreporting {aasreporting_url_literal}
{I}aasstringification {aasstringification_url_literal}
{I}aastypes {aastypes_url_literal}
)"""
        ),
        Stripped("// region De-serialization"),
    ]

    blocks.extend(_generate_deserialization_error_and_its_methods())

    blocks.extend(
        [
            Stripped(
                """\
// This is class for a sentinel token to signal the end-of-file.
type eof struct{}"""
            ),
            _generate_is_whitespace(),
            _generate_read_next(),
            _generate_skip_empty_text_whitespace_and_comments(),
            _generate_read_text(),
            _generate_read_text_as_boolean(),
            _generate_read_text_as_long(),
            *_generate_is_valid_xs_double(),
            _generate_read_text_as_double(),
            _generate_read_text_as_base64_encoded_bytes(),
            Stripped(
                f"""\
const Namespace = {namespace_literal}"""
            ),
            _generate_check_start_element(),
            _generate_extract_local_name_from_start_element(),
            _generate_parse_as_start_element_and_extract_local_name(),
            _generate_check_end_element(),
            *_generate_error_constructors(),
            _generate_scalar_definition(),
            _generate_read_element_dispatched(),
            _generate_read_list_of(),
            _generate_read_optional(),
            _generate_next_property(),
            _generate_conclude_property(),
        ]
    )

    read_requirements = _collect_read_requirements(symbol_table)

    for scalar_item_reader in read_requirements.scalar_item_readers:
        blocks.append(_generate_read_scalar_item(scalar_item_reader=scalar_item_reader))

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_read_tuple_helper(arity))

    errors = []  # type: List[Error]

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_read_text_as_enumeration(enumeration=our_type))

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            pass
        elif isinstance(our_type, intermediate.AbstractClass):
            if id(our_type) in read_requirements.dispatched_type_ids:
                blocks.append(_generate_read_dispatched(our_type=our_type))

        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Xmlization/read_{our_type.name}_as_sequence.go"
                )

                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {our_type.name}: {implementation_key}",
                        )
                    )
                    continue
            else:
                blocks.append(_generate_read_as_sequence(cls=our_type))

            if id(our_type) in read_requirements.dispatched_type_ids:
                blocks.append(_generate_read_dispatched(our_type=our_type))

        elif isinstance(our_type, intermediate.NamedUnion):
            if id(our_type) in read_requirements.dispatched_type_ids:
                blocks.append(_generate_read_dispatched(our_type=our_type))

        else:
            assert_never(our_type)

    blocks.append(_generate_read_class_dispatched(symbol_table=symbol_table))

    blocks.append(_generate_unmarshal())

    blocks.append(Stripped("// endregion"))

    blocks.append(Stripped("// region Serialization"))

    blocks.extend(_generate_serialization_error())

    blocks.extend(
        [
            _generate_write_start_element(),
            _generate_write_end_element(),
            _generate_write_text(),
            _generate_write_boolean_as_text(),
            _generate_write_long_as_text(),
            _generate_write_double_as_text(),
            _generate_write_string_as_text(),
            _generate_write_bytes_as_text(),
            _generate_write_scalar_property(),
            _generate_write_embedded_instance_property(),
            _generate_write_instance_property_with_discriminator(),
            _generate_write_list_of_instances_property(),
            _generate_write_list_of_scalars_property(),
        ]
    )

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_named_union_constraint())
        blocks.append(_generate_write_list_of_union_instances_property())

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        blocks.append(_generate_as_scalar_tuple_item_writer())
        blocks.append(_generate_as_instance_tuple_item_writer())
        if len(symbol_table.named_unions) > 0:
            blocks.append(_generate_write_union_as_tuple_item())
        for arity in tuple_arities:
            blocks.append(_generate_write_tuple_helper(arity))

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_write_enumeration_as_text(enumeration=our_type))

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin, 2023-06-18):
            # We will serialize constrained primitives as primitives.
            pass

        elif isinstance(our_type, intermediate.AbstractClass):
            # NOTE (mristin, 2023-06-18):
            # We will use general ``write`` function.
            pass

        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Xmlization/write_{our_type.name}_as_sequence.go"
                )

                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {our_type.name}: {implementation_key}",
                        )
                    )
                    continue
            else:
                blocks.append(_generate_write_as_sequence(cls=our_type))

            blocks.append(_generate_write_for(cls=our_type))

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is serialized at its call sites through
            # ``Marshal`` on its underlying instance, so it has no write
            # function of its own.
            pass

        else:
            assert_never(our_type)

    blocks.append(_generate_marshal(symbol_table=symbol_table))

    blocks.append(Stripped("// endregion"))

    if len(errors) > 0:
        return None, errors

    blocks.append(golang_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
