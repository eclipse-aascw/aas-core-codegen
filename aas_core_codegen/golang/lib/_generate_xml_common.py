"""Generate the XML primitives shared by the de/serialization."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped
from aas_core_codegen.golang import common as golang_common
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


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
func NewDeserializationError(message string) *DeserializationError {{
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
        Stripped(
            f"""\
// Prepend the element with the `name` to the path, and return the error back
// for chaining.
func (de *DeserializationError) PrependName(
{I}name string,
) *DeserializationError {{
{I}de.Path.PrependName(
{II}&aasreporting.NameSegment{{Name: name}},
{I})
{I}return de
}}"""
        ),
        Stripped(
            f"""\
// Prepend the element at the `index` to the path, and return the error back
// for chaining.
func (de *DeserializationError) PrependIndex(
{I}index int,
) *DeserializationError {{
{I}de.Path.PrependIndex(
{II}&aasreporting.IndexSegment{{Index: index}},
{I})
{I}return de
}}"""
        ),
        Stripped(
            f"""\
// Prepend the member with the `key` to the path, and return the error back
// for chaining.
func (de *DeserializationError) PrependKey(
{I}key string,
) *DeserializationError {{
{I}de.Path.PrependKey(
{II}&aasreporting.KeySegment{{Key: key}},
{I})
{I}return de
}}"""
        ),
        Stripped(
            f"""\
// Cast `err` to a de-serialization error, or panic.
//
// Every error which the de-serialization raises is
// a [DeserializationError], so the cast can only fail on an error which came
// from somewhere else entirely.
func MustDeserializationError(err error) *DeserializationError {{
{I}deseriaErr, ok := err.(*DeserializationError)
{I}if !ok {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Expected a *DeserializationError, but got %T: %v",
{IIII}err, err,
{III}),
{II})
{I}}}
{I}return deseriaErr
}}"""
        ),
    ]


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
func NewSerializationError(message string) *SerializationError {{
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
        Stripped(
            f"""\
// Prepend the item at the `index` to the path, and return the error back
// for chaining.
func (se *SerializationError) PrependIndex(
{I}index int,
) *SerializationError {{
{I}se.Path.PrependIndex(
{II}&aasreporting.IndexSegment{{Index: index}},
{I})
{I}return se
}}"""
        ),
        Stripped(
            f"""\
// Prepend the member with the `key` to the path, and return the error back
// for chaining.
func (se *SerializationError) PrependKey(
{I}key string,
) *SerializationError {{
{I}se.Path.PrependKey(
{II}&aasreporting.KeySegment{{Key: key}},
{I})
{I}return se
}}"""
        ),
        Stripped(
            f"""\
// Cast `err` to a serialization error, or panic.
//
// See the note on [MustDeserializationError].
func MustSerializationError(err error) *SerializationError {{
{I}seriaErr, ok := err.(*SerializationError)
{I}if !ok {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Expected a *SerializationError, but got %T: %v",
{IIII}err, err,
{III}),
{II})
{I}}}
{I}return seriaErr
}}"""
        ),
    ]


def _generate_is_whitespace() -> Stripped:
    return Stripped(
        f"""\
// Check if the string `s` consists only of whitespace.
//
// An empty string causes panic — please cover that case before.
func IsWhitespace(s string) bool {{
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
// If `current` token is [Eof], return [Eof].
func ReadNext(decoder *xml.Decoder, current xml.Token) (next xml.Token, err error) {{
{I}if _, isEOF := current.(Eof); isEOF {{
{II}next = current
{II}return
{I}}}

{I}var tokenErr error
{I}next, tokenErr = decoder.Token()
{I}if tokenErr != nil {{
{II}if tokenErr == io.EOF {{
{III}next = &Eof{{}}
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
// or [Eof], if we reached the end-of-file.
//
// If we already reached the end-of-file, simply return [Eof].
func SkipEmptyTextWhitespaceAndComments(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (next xml.Token, err error) {{
{I}stop := false
{I}for !stop {{
{II}if _, isEOF := current.(Eof); isEOF {{
{III}break
{II}}}

{II}switch et := current.(type) {{
{II}case xml.CharData:
{III}text := string(et)
{III}if len(text) != 0 && !IsWhitespace(text) {{
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
{III}current, err = ReadNext(decoder, current)
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
// Match a run of the four characters which XML calls whitespace.
var whitespaceRunRe = regexp.MustCompile("[ \\t\\n\\r]+")

// Normalize `text` the way `whiteSpace="collapse"` prescribes.
//
// Every atomic XSD type except a string, and every type derived from one by
// restriction, fixes `whiteSpace` to `collapse`, and a schema author can not
// change it. A tab, a line feed and a carriage return each become a space,
// a run of spaces becomes one space, and the leading and trailing spaces go.
// Only the result of that is a lexical representation to be matched.
//
// Mind that this strips only the whitespace *around* the value: a space
// within it survives as a single space, so "2  3" becomes "2 3", which is
// still no number.
//
// See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace
func CollapseWhitespace(text string) string {{
{I}return strings.Trim(whitespaceRunRe.ReplaceAllString(text, " "), " ")
}}

// Tell whether `text` is a lexical form of `xs:base64Binary`.
//
// The whitespace is expected to be gone already. What is left has to match
// `(B64 B64 B64 B64)* ((B64 B64 B64 B64) | (B64 B64 B16 "=") | (B64 B04 "=="))?`
// -- a length which is a multiple of four, the alphabet and nothing else,
// an equals sign only at the very end, and, easily missed, a constrained
// character *before* the padding, as the bits which the padding drops have to
// be zero.
//
// The decoders do not agree on any of this, so every target does the same
// check of its own and refuses the same texts.
//
// See: https://www.w3.org/TR/xmlschema-2/#base64Binary
func matchesXsBase64Binary(text string) bool {{
{I}if len(text)%4 != 0 {{
{II}return false
{I}}}

{I}if len(text) == 0 {{
{II}return true
{I}}}

{I}pads := 0
{I}if text[len(text)-1] == '=' {{
{II}pads = 1
{II}if text[len(text)-2] == '=' {{
{III}pads = 2
{II}}}
{I}}}

{I}for i := 0; i < len(text)-pads; i++ {{
{II}character := text[i]
{II}inAlphabet := (character >= 'A' && character <= 'Z') ||
{III}(character >= 'a' && character <= 'z') ||
{III}(character >= '0' && character <= '9') ||
{III}character == '+' ||
{III}character == '/'
{II}if !inAlphabet {{
{III}return false
{II}}}
{I}}}

{I}// NOTE:
{I}// Only these sixteen characters leave the two dropped bits at zero, and
{I}// only these four leave the four dropped bits at zero.
{I}if pads == 1 {{
{II}return strings.IndexByte("AEIMQUYcgkosw048", text[len(text)-2]) >= 0
{I}}}

{I}if pads == 2 {{
{II}return strings.IndexByte("AQgw", text[len(text)-3]) >= 0
{I}}}

{I}return true
}}

// Drop every whitespace character of `text`.
//
// This is what `xs:base64Binary` needs: it allows whitespace between
// the characters and not only around them, so collapsing is not enough --
// the decoder accepts none of it.
func RemoveWhitespace(text string) string {{
{I}return whitespaceRunRe.ReplaceAllString(text, "")
}}

// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [Eof] sentinel token.
func ReadText(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (text string, next xml.Token, err error) {{
{I}b := &strings.Builder{{}}

{I}stop := false
{I}for {{
{II}if _, isEOF := current.(Eof); isEOF {{
{III}err = NewDeserializationError(
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
{III}current, err = ReadNext(decoder, current)
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


def _generate_read_text_as_bool() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a representation of a `xs:boolean`.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [Eof] sentinel token.
func ReadTextAs_bool(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value bool, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = ReadText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}
{I}text = CollapseWhitespace(text)

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
{II}err = NewDeserializationError(
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
// If we reached the end-of-file, `next` is an [Eof] sentinel token.
func ReadTextAs_long(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value int64, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = ReadText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}
{I}text = CollapseWhitespace(text)

{I}var parseErr error
{I}value, parseErr = strconv.ParseInt(text, 10, 64)
{I}if parseErr != nil {{
{II}err = NewDeserializationError(
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
{I}// NOTE:
{I}// "+INF" is matched although it is written as "INF": XSD 1.1 admits it,
{I}// its production being (\\+|-)?INF, and being liberal in what we accept
{I}// costs nothing here. strconv.ParseFloat reads it without complaint.
{I}doubleRep := "((\\\\+|-)?([0-9]+(\\\\.[0-9]*)?|\\\\.[0-9]+)([Ee](\\\\+|-)?[0-9]+)?|(\\\\+|-)?INF|NaN)"
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
// If we reached the end-of-file, `next` is an [Eof] sentinel token.
func ReadTextAs_double(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value float64, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = ReadText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}
{I}text = CollapseWhitespace(text)

{I}// We need to check explicitly for the regular expression since
{I}// strconv.ParseFloat is too permissive. For example, it accepts "nan"
{I}// although only "NaN" is valid.
{I}// See: https://www.w3.org/TR/xmlschema-2/#double
{I}if !isValidXsDouble(text) {{
{II}err = NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:double, but got: %s",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}var parseErr error
{I}value, parseErr = strconv.ParseFloat(text, 64)
{I}// NOTE:
{I}// A literal too large for a double is not an error in XSD. It rounds to
{I}// an infinity, which is in the value space of xs:double, and ParseFloat
{I}// hands us exactly that infinity *together* with [strconv.ErrRange]. So
{I}// the range is deliberately let through, and only a syntax error is
{I}// reported -- and the pattern above has already excluded those.
{I}//
{I}// A literal too small rounds to zero, which ParseFloat reports without
{I}// any error at all.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema11-2/#double
{I}if parseErr != nil && !errors.Is(parseErr, strconv.ErrRange) {{
{II}err = NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:double, but it could not be parsed: %s: %s",
{IIII}parseErr.Error(), text,
{III}),
{II})
{II}return
{I}}}

{I}// NOTE:
{I}// We explicitly do not check for loss of precision, as the majority of people will
{I}// use string representation of the floating point numbers ignoring the precision
{I}// issues. For example, the closest double-precision number to the number `359.9` is
{I}// `359.8999999999999772626324556767940521240234375`, but most people will simply
{I}// give `359.9` as the value.

{I}return
}}"""
    )


def _generate_read_text_as_bytes() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a base64-encoded bytes.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [Eof] sentinel token.
func ReadTextAs_bytes(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value []byte, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = ReadText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}
{I}// NOTE:
{I}// xs:base64Binary allows whitespace between the characters, and not only
{I}// around them, while the decoder accepts none of it. So every whitespace
{I}// character is dropped, and not merely collapsed.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#base64Binary
{I}text = RemoveWhitespace(text)

{I}if !matchesXsBase64Binary(text) {{
{II}err = NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a text as base64-encoded bytes, but got: %s",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}var decodingErr error
{I}value, decodingErr = b64.StdEncoding.DecodeString(text)
{I}if decodingErr != nil {{
{II}err = NewDeserializationError(
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
// Check that the `current` token is a valid start element, *i.e.*, lives in
// the `ns` namespace and contains no attributes.
func checkStartElementInNamespace(
{I}current xml.StartElement,
{I}ns string,
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
{II}err = NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected no attributes except 'xmlns' in the start element, "+
{IIIII}"but got %d in the start element %s",
{IIII}unexpectedAttr, current.Name.Local,
{III}),
{II})
{II}return
{I}}}

{I}if current.Name.Space != ns {{
{II}err = NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected only start elements in the namespace %s, "+
{IIIII}"but got a start element %s in the namespace %s",
{IIII}ns, current.Name.Local, current.Name.Space,
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
// Expect a valid start element (as defined in [CheckStartElement]) and extract its
// `local` name.
//
// This function is meant to be called whenever you know the runtime type of a token.
// If you do not know the runtime type, call [ParseAsStartElementAndExtractLocalName]
// so that you can succinctly check the runtime type as well.
func extractLocalNameFromStartElementInNamespace(
{I}current xml.StartElement,
{I}ns string,
) (local string, err error) {{
{I}err = checkStartElementInNamespace(current, ns)
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
// Expect a valid start element (as defined in [CheckStartElement]) and extract its
// local name.
//
// Valid means that we check that the start element lives in the `ns` namespace and
// contains no attributes.
//
// If you know the runtime type of `current` token, call
// [ExtractLocalNameFromStartElement] instead to save a cast.
func parseAsStartElementAndExtractLocalNameInNamespace(
{I}current xml.Token,
{I}ns string,
) (local string, err error) {{
{I}if _, isEOF := current.(Eof); isEOF {{
{II}err = NewDeserializationError(
{III}"Expected a start element, but reached the end-of-file",
{II})
{II}return
{I}}}

{I}et, ok := current.(xml.StartElement)
{I}if !ok {{
{II}switch v := current.(type) {{
{II}case xml.EndElement:
{III}err = NewDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got an end element %s in namespace %s",
{IIIII}v.Name.Local, v.Name.Space,
{IIII}),
{III})
{II}case xml.CharData:
{III}err = NewDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got text %s",
{IIIII}string(v),
{IIII}),
{III})
{II}default:
{III}err = NewDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got %T: %v",
{IIIII}current, current,
{IIII}),
{III})
{II}}}
{II}return
{I}}}

{I}local, err = extractLocalNameFromStartElementInNamespace(et, ns)
{I}return
}}"""
    )


def _generate_check_end_element() -> Stripped:
    return Stripped(
        f"""\
// Check that the `current` token is an end element, living in the `ns` namespace,
// and having the `local` name.
func checkEndElementInNamespace(current xml.Token, local string, ns string) (err error) {{
{I}if _, isEOF := current.(Eof); isEOF {{
{II}err = NewDeserializationError(
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
{III}err = NewDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got a start element %s in namespace %s",
{IIIII}local, v.Name.Local, v.Name.Space,
{IIII}),
{III})
{II}case xml.CharData:
{III}err = NewDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got text %s",
{IIIII}local, string(v),
{IIII}),
{III})
{II}default:
{III}err = NewDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got %T: %v",
{IIIII}local, current, current,
{IIII}),
{III})
{II}}}
{II}return
{I}}}

{I}if et.Name.Space != ns {{
{II}err = NewDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an end element %s in the namespace %s, "+
{IIIII}"but got an end element in the namespace %s",
{IIII}local, ns, et.Name.Space,
{III}),
{II})
{II}return
{I}}}

{I}if et.Name.Local != local {{
{II}err = NewDeserializationError(
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


def _generate_read_element_dispatched() -> Stripped:
    """Generate the function to read a single value wrapped in an XML element."""
    return Stripped(
        f"""\
// Read a value wrapped in a single XML element which lives in the `ns` namespace,
// dispatching on the local name of that element.
//
// The element is read in full: the resulting `next` token points to the first token
// just after the end element.
//
// This is the *only* place which frames an XML element around a value. Every
// container which reads a sequence of elements delegates the framing here, so
// that its items differ only in the given `readByLocal`, and never in
// the container which reads them.
//
// `T` is left unconstrained since this function never invokes any method on it.
// This lets it be reused for an instance, for a scalar and for a JSON-able value
// alike.
func readElementDispatchedInNamespace[T any](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}ns string,
{I}readByLocal func(
{II}aDecoder *xml.Decoder,
{II}aCurrent xml.Token,
{II}aLocal string,
{I}) (value T, aNext xml.Token, anErr error),
) (value T, next xml.Token, err error) {{
{I}current, err = SkipEmptyTextWhitespaceAndComments(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}var local string
{I}local, err = parseAsStartElementAndExtractLocalNameInNamespace(current, ns)
{I}if err != nil {{
{II}return
{I}}}

{I}// Move the current to the content of the XML element
{I}current, err = ReadNext(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}value, current, err = readByLocal(decoder, current, local)
{I}if err != nil {{
{II}return
{I}}}

{I}err = checkEndElementInNamespace(current, local, ns)
{I}if err != nil {{
{II}return
{I}}}

{I}next, err = ReadNext(decoder, current)
{I}return
}}"""
    )


def _generate_namespace_bound_readers(uses_json_types: bool) -> List[Stripped]:
    """
    Generate the readers which bind the namespace of an element.

    The namespace is no argument of the de-serialization. An element of
    the document lives in [Namespace], and an element of the XML-RPC subset in
    no namespace at all, so each primitive comes in the one or the two flavors
    which are actually called.
    """
    result = [
        Stripped(
            f"""\
// Check that the `current` token is a valid start element, *i.e.*, lives in
// the [Namespace] namespace and contains no attributes.
func CheckStartElement(current xml.StartElement) (err error) {{
{I}return checkStartElementInNamespace(current, Namespace)
}}"""
        ),
        Stripped(
            f"""\
// Extract the local name of the given valid start element, which is expected to
// live in the [Namespace] namespace.
func ExtractLocalNameFromStartElement(
{I}current xml.StartElement,
) (local string, err error) {{
{I}return extractLocalNameFromStartElementInNamespace(current, Namespace)
}}"""
        ),
        Stripped(
            f"""\
// Expect a valid start element living in the [Namespace] namespace and extract
// its local name.
func ParseAsStartElementAndExtractLocalName(
{I}current xml.Token,
) (local string, err error) {{
{I}return parseAsStartElementAndExtractLocalNameInNamespace(current, Namespace)
}}"""
        ),
        Stripped(
            f"""\
// Check that the `current` token is an end element, living in the [Namespace]
// namespace, and having the `local` name.
func CheckEndElement(current xml.Token, local string) (err error) {{
{I}return checkEndElementInNamespace(current, local, Namespace)
}}"""
        ),
        Stripped(
            f"""\
// Read a value wrapped in a single XML element living in the [Namespace]
// namespace, dispatching on the local name of that element.
func ReadElementDispatched[T any](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}readByLocal func(
{II}aDecoder *xml.Decoder,
{II}aCurrent xml.Token,
{II}aLocal string,
{I}) (value T, aNext xml.Token, anErr error),
) (value T, next xml.Token, err error) {{
{I}return readElementDispatchedInNamespace(
{II}decoder, current, Namespace, readByLocal,
{I})
}}"""
        ),
    ]  # type: List[Stripped]

    if uses_json_types:
        result.append(
            Stripped(
                f"""\
// Read a value wrapped in a single XML element living in no namespace at all,
// dispatching on the local name of that element.
func ReadElementDispatchedInNoNamespace[T any](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}readByLocal func(
{II}aDecoder *xml.Decoder,
{II}aCurrent xml.Token,
{II}aLocal string,
{I}) (value T, aNext xml.Token, anErr error),
) (value T, next xml.Token, err error) {{
{I}return readElementDispatchedInNamespace(
{II}decoder, current, "", readByLocal,
{I})
}}"""
            )
        )

    return result


def _generate_write_start_element() -> Stripped:
    return Stripped(
        f"""\
// Write the start element with the given `local` name to the encoder.
//
// Do not flush.
//
// If `withNamespace` is set, the element declares [Namespace]. The enclosing
// element is expected to have declared it otherwise.
func WriteStartElement(
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
// If `withNamespace` is set, the element is spelled in [Namespace], which
// the corresponding start element has to have declared.
func WriteEndElement(
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


def _generate_write_start_element_in_no_namespace() -> Stripped:
    return Stripped(
        f"""\
// Write the start element with the given `local` name, which lives in no
// namespace at all, to the encoder.
//
// Do not flush.
//
// If `undeclareNamespace` is set, the element undeclares the default namespace
// of the enclosing document. Only the outermost element in no namespace does
// so; the elements nested in it inherit that.
func WriteStartElementInNoNamespace(
{I}encoder *xml.Encoder,
{I}local string,
{I}undeclareNamespace bool,
) (err error) {{
{I}startElement := xml.StartElement{{Name: xml.Name{{Local: local}}}}
{I}if undeclareNamespace {{
{II}startElement.Attr = []xml.Attr{{
{III}{{Name: xml.Name{{Local: "xmlns"}}, Value: ""}},
{II}}}
{I}}}

{I}err = encoder.EncodeToken(startElement)
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
func WriteText(
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


def _generate_write_as_text_bool() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:boolean` in a text element.
//
// Do not flush.
func WriteAsText_bool(
{I}encoder *xml.Encoder,
{I}value bool,
) (err error) {{
{I}text := "true"
{I}if !value {{
{II}text = "false"
{I}}}
{I}err = WriteText(encoder, text)
{I}return
}}"""
    )


def _generate_write_as_text_long() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:long` in a text element.
//
// Do not flush.
func WriteAsText_long(
{I}encoder *xml.Encoder,
{I}value int64,
) (err error) {{
{I}text := strconv.FormatInt(value, 10)
{I}err = WriteText(encoder, text)
{I}return
}}"""
    )


def _generate_write_as_text_double() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:double` in a text element.
//
// Do not flush.
func WriteAsText_double(
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

{I}err = WriteText(encoder, text)
{I}return
}}"""
    )


def _generate_write_as_text_string() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:string` in a text element.
//
// Do not flush.
func WriteAsText_string(
{I}encoder *xml.Encoder,
{I}value string,
) (err error) {{
{I}err = WriteText(encoder, value)
{I}return
}}"""
    )


def _generate_write_as_text_bytes() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a base64-encoded bytes in a text element.
//
// Do not flush.
func WriteAsText_bytes(
{I}encoder *xml.Encoder,
{I}value []byte,
) (err error) {{
{I}text := b64.StdEncoding.EncodeToString(
{II}value,
{I})

{I}err = WriteText(encoder, text)
{I}return
}}"""
    )


def _generate_write_element() -> Stripped:
    """
    Generate the single function which frames an XML element around a value.

    Everything else in the serialization only decides *what* is written --
    the framing itself lives here, so that a property, a list item and
    a tuple item differ solely in the given content writer.
    """
    return Stripped(
        f"""\
// Write `that` as an XML element with the `local` name, its content written by
// `writeContent`.
//
// Do not flush.
//
// This is the one place which frames an XML element around a *value*: a property,
// a list item, a tuple item and an item of a JSON-able array all go through it,
// and differ only in the given `writeContent`.
//
// The XML namespace is expected to have been defined outside of the resulting XML
// element.
func WriteElement[T any](
{I}encoder *xml.Encoder,
{I}local string,
{I}that T,
{I}writeContent func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}err = WriteStartElement(encoder, local, false)
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeContent(encoder, that)
{I}if err != nil {{
{II}return
{I}}}

{I}err = WriteEndElement(encoder, local, false)
{I}return
}}"""
    )


def _generate_write_element_in_no_namespace() -> Stripped:
    """Generate the framer for an element which lives in no namespace."""
    return Stripped(
        f"""\
// Write `that` as an XML element with the `local` name, which lives in no
// namespace at all, its content written by `writeContent`.
//
// Do not flush.
//
// If `undeclareNamespace` is set, the element undeclares the default namespace
// of the enclosing document, which only the outermost element in no namespace
// does.
func WriteElementInNoNamespace[T any](
{I}encoder *xml.Encoder,
{I}local string,
{I}undeclareNamespace bool,
{I}that T,
{I}writeContent func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}err = WriteStartElementInNoNamespace(encoder, local, undeclareNamespace)
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeContent(encoder, that)
{I}if err != nil {{
{II}return
{I}}}

{I}err = WriteEndElement(encoder, local, false)
{I}return
}}"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """
    Generate the XML primitives shared by the de/serialization.

    Two modules read and write XML: the xmlization, which descends through
    the elements of our own classes, and the XML-RPC de/serialization, which
    descends through the elements within a JSON-able value. Neither the
    skipping of the whitespace and of the comments, nor the check of the XML
    namespace, nor the consuming of a start and of an end tag differs between
    the two, so all of it lives here and is defined exactly once.

    The namespace is a constant here, ``Namespace``, and no argument of these
    functions: the xmlization re-exports it, and the XML-RPC module needs none
    at all, as the XML-RPC elements live in no namespace. Where a primitive is
    called for both, it comes in two flavors, one of them named
    ``...InNoNamespace``.

    The package is private to the generated module, so the public surface of
    the library does not grow. The two error types are the exception -- both
    the xmlization and the XML-RPC module alias them, so that an error which
    the one raised deep inside a JSON-able value is still the very same type
    that the other's caller type-asserts on, and its path survives the hand-over.

    The ``repo_url`` is the URL of the repository of the generated module.
    """
    namespace_literal = golang_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    # NOTE (mristin):
    # The XML-RPC subset, over which the JSON-able values are de/serialized,
    # writes its elements in no namespace at all, as the XML-RPC specification
    # prescribes. The primitives which deal with such elements are therefore
    # only generated for a meta-model which actually has a JSON-able type.
    uses_json_types = intermediate.uses_json_types(symbol_table)

    aascommon_url_literal = golang_common.string_literal(f"{repo_url}/common")

    aasreporting_url_literal = golang_common.string_literal(f"{repo_url}/reporting")

    blocks = [
        Stripped(
            """\
// Package xmlcommon provides the XML primitives shared by the de/serialization.
//
// The xmlization reads and writes the elements of our own classes, and
// the xmlrpc package the elements within a JSON-able value. The whitespace
// skipping, the namespace checks and the framing of an element are the same
// for both, and live here.
package xmlcommon"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}b64 "encoding/base64"
{I}"encoding/xml"
{I}"errors"
{I}"fmt"
{I}"io"
{I}"math"
{I}"regexp"
{I}"strconv"
{I}"strings"
{I}"unicode"
{I}aascommon {aascommon_url_literal}
{I}aasreporting {aasreporting_url_literal}
)"""
        ),
    ]  # type: List[Stripped]

    blocks.append(
        Stripped(
            f"""\
// Namespace is the XML namespace in which all the elements of a document live.
//
// The elements of the XML-RPC subset, over which a JSON-able value is
// de/serialized, are the one exception: they live in no namespace at all.
const Namespace = {namespace_literal}"""
        )
    )

    blocks.extend(_generate_deserialization_error_and_its_methods())
    blocks.extend(_generate_serialization_error())

    blocks.extend(
        [
            Stripped(
                """\
// Represent a sentinel token which signals the end-of-file.
type Eof struct{}"""
            ),
            _generate_is_whitespace(),
            _generate_read_next(),
            _generate_skip_empty_text_whitespace_and_comments(),
            _generate_read_text(),
            _generate_read_text_as_bool(),
            _generate_read_text_as_long(),
            *_generate_is_valid_xs_double(),
            _generate_read_text_as_double(),
            _generate_read_text_as_bytes(),
            _generate_check_start_element(),
            _generate_extract_local_name_from_start_element(),
            _generate_parse_as_start_element_and_extract_local_name(),
            _generate_check_end_element(),
            _generate_read_element_dispatched(),
            *_generate_namespace_bound_readers(uses_json_types=uses_json_types),
            _generate_write_start_element(),
            _generate_write_end_element(),
            _generate_write_text(),
            _generate_write_as_text_bool(),
            _generate_write_as_text_long(),
            _generate_write_as_text_double(),
            _generate_write_as_text_string(),
            _generate_write_as_text_bytes(),
            _generate_write_element(),
        ]
    )

    if uses_json_types:
        blocks.extend(
            [
                _generate_write_start_element_in_no_namespace(),
                _generate_write_element_in_no_namespace(),
            ]
        )

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
