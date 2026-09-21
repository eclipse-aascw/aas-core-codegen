"""Generate code for reporting errors."""

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.golang import (
    common as golang_common,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate() -> str:
    """Generate code for reporting errors."""
    blocks = [
        Stripped(
            """\
// Package reporting provides structures and functions for reporting of errors.
package reporting"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"
{I}"strings"
{I}"strconv"
)"""
        ),
        Stripped(
            f"""\
type NameSegment struct{{
{I}Name string
}}"""
        ),
        Stripped(
            f"""\
type IndexSegment struct{{
{I}Index int
}}"""
        ),
        Stripped(
            f"""\
// Represent a member of an open JSON-able object on a path to
// the erroneous value.
//
// Unlike a [NameSegment], which names a property of one of our classes, a key
// is known only at run time, and can be any string at all.
type KeySegment struct{{
{I}Key string
}}"""
        ),
        Stripped(
            f"""\
type Path struct{{
{I}// A segments is expected to be either a name segment or an index segment.
{I}segments []interface{{}}
{I}start int
}}"""
        ),
        Stripped(
            f"""\
// Prepend the segment to the path.
//
// Grow segments exponentially if there is no place.
func (p *Path) prepend(segment interface{{}}) {{
{I}// See: https://en.wikipedia.org/wiki/Amortized_analysis#Dynamic_array
{I}if len(p.segments) == 0 {{
{II}p.segments = make([]interface{{}}, 1)
{II}p.segments[0] = segment
{II}p.start = 0
{I}}} else if p.start > 0 {{
{II}p.start--
{II}p.segments[p.start] = segment
{I}}} else {{
{II}s := make([]interface{{}}, len(p.segments) * 2)
{II}copy(s[len(p.segments):], p.segments)
{II}p.start = len(p.segments) - 1
{II}p.segments = s
{II}p.segments[p.start] = segment
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Prepend the name segment to the path.
func (p *Path) PrependName(segment *NameSegment) {{
{I}p.prepend(segment)
}}"""
        ),
        Stripped(
            f"""\
// Prepend the index segment to the path.
func (p *Path) PrependIndex(segment *IndexSegment) {{
{I}p.prepend(segment)
}}"""
        ),
        Stripped(
            f"""\
// Prepend the key segment to the path.
func (p *Path) PrependKey(segment *KeySegment) {{
{I}p.prepend(segment)
}}"""
        ),
        Stripped(
            f"""\
// Apply the `callback` on each segment.
//
// The segment object is a [NameSegment], an [IndexSegment] or a [KeySegment].
func (p *Path) OverSegments(callback func(interface{{}})) {{
{I}start := p.start
{I}for i := start; i < len(p.segments); i++ {{
{II}callback(p.segments[i])
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Translate the path to a JSON path.
//
// The name segments are expected to denote the names of the properties
// in JSON property names, not Golang property names.
func ToJSONPath(p *Path) string {{
{I}var b strings.Builder
{I}i := 0
{I}p.OverSegments(func(s interface{{}}) {{
{II}switch v := s.(type) {{
{II}case *NameSegment:
{III}if i == 0 {{
{III}{I}b.WriteString(v.Name)
{III}}} else {{
{III}{I}b.WriteString(".")
{III}{I}b.WriteString(v.Name)
{III}}}
{II}case *IndexSegment:
{III}b.WriteString("[")
{III}b.WriteString(strconv.Itoa(v.Index))
{III}b.WriteString("]")
{II}case *KeySegment:
{III}b.WriteString(`["`)
{III}b.WriteString(escapeForJSONString(v.Key))
{III}b.WriteString(`"]`)
{II}default:
{III}panic(
{III}{I}fmt.Sprintf(
{III}{II}"Unexpected segment of type %T: %v",
{III}{II}s, s,
{III}{I}),
{III})
{II}}}

{II}i++
{I}}})
{I}return b.String()
}}"""
        ),
        Stripped(
            f"""\
// Translate the path to a Golang access path.
//
// The name segments are expected to denote the names of the properties
// in Golang, not JSON property names.
func ToGolangPath(p *Path) string {{
{I}// NOTE(mristin):
{I}// We re-use JSON path formatting as implementation, but introduce
{I}// a separate function to signal to the reader in which form
{I}// the name segments are expected (Golang property names instead
{I}// of JSON property names).
{I}return ToJSONPath(p)
}}"""
        ),
        Stripped(
            f"""\
var replacerForJSONString = strings.NewReplacer(
{I}"\\\\", "\\\\\\\\",
{I}"\\"", "\\\\\\"",
{I}"\\b", "\\\\b",
{I}"\\f", "\\\\f",
{I}"\\n", "\\\\n",
{I}"\\r", "\\\\r",
{I}"\\t", "\\\\t",
)"""
        ),
        Stripped(
            f"""\
// Escape the characters which a JSON string may not hold as they are.
func escapeForJSONString(
{I}text string,
) string {{
{I}return replacerForJSONString.Replace(text)
}}"""
        ),
        Stripped(
            f"""\
var replacerForXPath = strings.NewReplacer(
{I}"/", "&#47;",
{I}"<", "&lt;",
{I}">", "&gt;",
{I}"\\"", "&quot;",
{I}"'", "&apos;",
)"""
        ),
        Stripped(
            f"""\
// Escape special characters for XPath.
func escapeForXPath(
{I}text string,
) string {{
{I}return replacerForXPath.Replace(text)
}}"""
        ),
        Stripped(
            f"""\
// Generate a relative XPath based on the path segments.
//
// Leave out the leading slash (`/`). This is helpful if we
// want to embed the error report in a larger document with a prefix
// *etc.*
func ToRelativeXPath(
{I}p *Path,
) string {{
{I}i := 0
{I}var b strings.Builder
{I}p.OverSegments(func(s interface{{}}) {{
{II}if i > 0 {{
{III}b.WriteString("/")
{II}}}

{II}switch v := s.(type) {{
{III}case *NameSegment:
{IIII}b.WriteString(escapeForXPath(v.Name))
{III}case *IndexSegment:
{IIII}b.WriteString(fmt.Sprintf("*[%d]", v.Index))
{III}case *KeySegment:
{IIII}// NOTE (mristin):
{IIII}// A JSON-able object is written as an XML-RPC `<struct>`, which holds
{IIII}// the key of a member in a `<name>` child element, and not in
{IIII}// an attribute, so the XPath has to match on that child element.
{IIII}b.WriteString(
{IIIII}fmt.Sprintf(`member[name="%s"]`, escapeForXPath(v.Key)),
{IIII})
{III}default:
{IIII}panic(fmt.Sprintf("Unexpected segment of type %T: %v", s, s))
{II}}}
{II}
{II}i++
{I}}})
{I}return b.String()
}}"""
        ),
        golang_common.WARNING,
    ]

    return "\n\n".join(blocks) + "\n"


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
