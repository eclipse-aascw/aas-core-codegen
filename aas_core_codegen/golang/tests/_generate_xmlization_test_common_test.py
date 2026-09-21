"""Generate code for common XML de/serialization shared across the tests."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.golang import common as golang_common
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(repo_url: Stripped) -> str:
    """Generate code for common XML de/serialization shared across the tests."""
    blocks = [
        Stripped(
            """\
package xmlization_test"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"
{I}"os"
{I}"path/filepath"
{I}"regexp"
{I}"strings"
{I}"testing"
{I}aastesting "{repo_url}/aastesting"
{I}aasxmlization "{repo_url}/xmlization"
)"""
        ),
        Stripped(
            f"""\
// Assert that there is no de-serialization error when de-serializing
// from `source`.
func assertNoDeserializationError(
{I}t *testing.T,
{I}err error,
{I}source string,
) (ok bool) {{
{I}ok = true
{I}if err != nil {{
{II}ok = false
{II}t.Fatalf(
{III}"Expected no de-serialization error from %s, but got: %s",
{III}source, err.Error(),
{II})
{II}return
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Assert that there is no serialization error when serializing the instance
// originally coming from `source`.
func assertNoSerializationError(
{I}t *testing.T,
{I}err error,
{I}source string,
) (ok bool) {{
{I}ok = true
{I}if err != nil {{
{II}ok = false
{II}t.Fatalf(
{III}"Expected no serialization error when serializing "+
{IIII}"the instance obtained from %s, but got: %s",
{III}source, err.Error(),
{II})
{II}return
{I}}}
{I}return
}}"""
        ),
        Stripped(
            """\
// NOTE (mristin):
// Currently, Go does not support self-closing tags,
// see: https://github.com/golang/go/issues/21399.
// We apply the following hack to make the tags self-closing even if they are not.
// This is unsafe in general, but works OK for the limited set of test data that we are
// here dealing with.
//
// The code has been taken from: https://github.com/golang/go/issues/21399#issuecomment-1342730174"""
        ),
        Stripped(
            """\
// NOTE (mristin):
// The opening tag, tag name plus an optional attribute list (*e.g.*,
// ``xmlns="..."`` on a root element), is captured in the first (and only)
// submatch group so that we do not lose any attributes when we force
// the tag to be self-closing below.
var emptyTagRe = regexp.MustCompile(`<(\\w+(?:\\s[^>]*)?)></\\w+>`)"""
        ),
        Stripped(
            f"""\
func forceSelfClosingTags(text string) string {{
{I}b := []byte(text)
{I}emptyTagIdxs := emptyTagRe.FindAllSubmatchIndex(b, -1)

{I}if len(emptyTagIdxs) == 0 {{
{II}return text
{I}}}

{I}// NOTE (mristin):
{I}// The matches are walked in order, and the pieces of `b` between them are
{I}// copied over as they are. Mind that `nb` starts out empty and that `b` is
{I}// only ever *read*: an earlier version appended into `b[0:idx[0]]`, which
{I}// writes into `b`'s own backing array, so a document with more than one
{I}// empty tag came out garbled -- every turn of the loop then indexed into
{I}// a `b` which the previous turn had already overwritten.
{I}var nb []byte
{I}previous := 0

{I}for _, idx := range emptyTagIdxs {{
{II}// Copy everything since the previous match, then the tag itself --
{II}// its name and its attributes -- as a self-closing one.
{II}nb = append(nb, b[previous:idx[0]]...)
{II}nb = append(nb, fmt.Sprintf("<%s/>", b[idx[2]:idx[3]])...)

{II}previous = idx[1]
{I}}}

{I}// Finally, copy everything after the last match.
{I}nb = append(nb, b[previous:]...)

{I}return string(nb)
}}"""
        ),
        Stripped(
            """\
var whitespaceBetweenTagsRe = regexp.MustCompile(`>\\s+<`)"""
        ),
        Stripped(
            f"""\
// Remove all whitespace (including newlines, tabs, and spaces) between XML tags
// without parsing the XML.
func removeWhitespaceBetweenTags(text string) string {{
{I}return whitespaceBetweenTagsRe.ReplaceAllString(text, "><")
}}"""
        ),
        Stripped(
            """\
var whitespaceBeforeAngleBracketsRe = regexp.MustCompile(`\\s+>`)
var whitespaceBeforeSelfClosingRe = regexp.MustCompile(`\\s+/>`)
var whitespaceAfterAngleBracketsRe = regexp.MustCompile(`<\\s+`)"""
        ),
        Stripped(
            f"""\
// Remove any whitespace before `>` and `/>` or after `<`
func removeWhitespaceWithinTags(text string) string {{
{I}result := text
{I}result = whitespaceBeforeAngleBracketsRe.ReplaceAllString(result, ">")
{I}result = whitespaceBeforeSelfClosingRe.ReplaceAllString(result, "/>")
{I}result = whitespaceAfterAngleBracketsRe.ReplaceAllString(result, "<")
{I}return result
}}"""
        ),
        Stripped(
            f"""\
// Assert that the serialization `other`, as XML document, equals the original
//
//	XML document `that` read from the `source`.
func assertSerializationEqualsDeserialization(
{I}t *testing.T,
{I}that string,
{I}other string,
{I}source string,
) (ok bool) {{
{I}// Remove carriers to avoid problems between Windows, Posix and MacOS
{I}canonicalThat := strings.ReplaceAll(that, "\\r", "")
{I}canonicalOther := strings.ReplaceAll(other, "\\r", "")

{I}canonicalThat = strings.TrimSpace(canonicalThat)
{I}canonicalOther = strings.TrimSpace(canonicalOther)

{I}canonicalThat = forceSelfClosingTags(canonicalThat)
{I}canonicalOther = forceSelfClosingTags(canonicalOther)

{I}// NOTE (mristin):
{I}// The following hack is SUPER ugly and unsafe! However, it works. Given Go's
{I}// limited support for XML, we gave up on a safer approach :(. We tested
{I}// the following approaches before applying this hack:
{I}//  * A round-trip over `encoding/xml`. Failed due to
{I}//    https://github.com/golang/go/issues/13400.
{I}//  * Using `aqwari.net/xml/xmltree`. Failed as the special characters in the
{I}//    element content still has not been de-escaped or consistently escaped in
{I}//    a round trip.

{I}canonicalThat = strings.ReplaceAll(canonicalThat, "'", "&#39;")
{I}canonicalOther = strings.ReplaceAll(canonicalOther, "'", "&#39;")

{I}canonicalThat = removeWhitespaceBetweenTags(canonicalThat)
{I}canonicalOther = removeWhitespaceBetweenTags(canonicalOther)

{I}canonicalThat = removeWhitespaceWithinTags(canonicalThat)
{I}canonicalOther = removeWhitespaceWithinTags(canonicalOther)

{I}thatLines := strings.Split(canonicalThat, "\\n")
{I}otherLines := strings.Split(canonicalOther, "\\n")

{I}if canonicalThat != canonicalOther {{
{II}b := new(strings.Builder)
{II}minLines := len(thatLines)
{II}if minLines > len(otherLines) {{
{III}minLines = len(otherLines)
{II}}}
{II}for i := 0; i < minLines; i++ {{
{III}if thatLines[i] == otherLines[i] {{
{IIII}b.WriteString(fmt.Sprintf("           %s\\n", thatLines[i]))
{III}}} else {{
{IIII}b.WriteString(fmt.Sprintf("ORIGINAL   %s\\n", thatLines[i]))
{IIII}b.WriteString(fmt.Sprintf("SERIALIZED %s\\n", otherLines[i]))
{IIII}break
{III}}}
{II}}}

{II}ok = false
{II}t.Fatalf(
{III}"The canonicalized XML serialization of the de-serialized instance "+
{IIII}"from %s does not equal the canonicalized original XML document:\\n"+
{IIII}"%s",
{III}source, b.String(),
{II})
{II}return
{I}}}

{I}return
}}"""
        ),
        Stripped(
            f"""\
// Assert that there is a de-serialization error.
//
// If [aastesting.RecordMode] is set, the de-serialization error is re-recorded
// to `expectedPth`. Otherwise, the error is compared against the golden file
// `expectedPth`.
func assertIsDeserializationErrorAndEqualsExpectedOrRecord(
{I}t *testing.T,
{I}err error,
{I}source string,
{I}expectedPth string,
) (ok bool) {{
{I}ok = true

{I}if err == nil {{
{II}ok = false
{II}t.Fatalf("De-serialization error expected from %s, but got none", source)
{II}return
{I}}}

{I}deseriaErr, is := err.(*aasxmlization.DeserializationError)
{I}if !is {{
{II}ok = false
{II}t.Fatalf(
{III}"Expected a de-serialization error, "+
{IIII}"but got an error of type %T from %s: %v",
{III}err, source, err,
{II})
{II}return
{I}}}

{I}// Add a new line for POSIX systems.
{I}got := deseriaErr.Error() + "\\n"

{I}if aastesting.RecordMode {{
{II}parent := filepath.Dir(expectedPth)
{II}err := os.MkdirAll(parent, os.ModePerm)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to create the directory %s: %s", parent, err.Error(),
{IIII}),
{III})
{II}}}

{II}err = os.WriteFile(expectedPth, []byte(got), 0644)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to write to the file %s: %s", expectedPth, err.Error(),
{IIII}),
{III})
{II}}}
{I}}} else {{
{II}_, err := os.Stat(expectedPth)
{II}if err != nil {{
{III}ok = false
{III}t.Fatalf(
{IIII}"Failed to stat the file %s: %s; if the file does not exist, "+
{IIIII}"you probably want to record the test data by "+
{IIIII}"setting the environment variable %s",
{IIII}expectedPth, err.Error(), aastesting.RecordModeEnvironmentVariableName,
{III})
{III}return
{II}}}

{II}bb, err := os.ReadFile(expectedPth)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to read from file %s: %s", expectedPth, err.Error(),
{IIII}),
{III})
{II}}}

{II}expected := string(bb)

{II}// NOTE (mristin):
{II}// Git automatically strips and adds `\\r`, so we have to remove it here
{II}// to obtain a canonical text.
{II}expected = strings.Replace(expected, "\\r", "", -1)

{II}if expected != got {{
{III}ok = false
{III}t.Fatalf(
{IIII}"What we got differs from the expected in %s. "+
{IIIII}"We got:\\n%s\\nWe expected:\\n%s",
{IIII}expectedPth, got, expected,
{III})
{III}return
{II}}}
{I}}}

{I}return
}}"""
        ),
        golang_common.WARNING,
    ]  # type: List[Stripped]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
