"""Generate code for reporting errors."""

import io
import textwrap
from typing import List

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.csharp import (
    common as csharp_common,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(namespace: csharp_common.NamespaceIdentifier) -> str:
    """
    Generate code for reporting errors.

    The ``namespace`` defines the base C# namespace of the generated code.
    """
    blocks = [
        Stripped(
            f"""\
/// <summary>
/// Capture a path segment of a value in a model.
/// </summary>
public abstract class Segment
{{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
public class NameSegment : Segment
{{
{I}public readonly string Name;
{I}public NameSegment(string name)
{I}{{
{II}Name = name;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
public class IndexSegment : Segment
{{
{I}public readonly int Index;
{I}public IndexSegment(int index)
{I}{{
{II}Index = index;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Capture a member of an open JSON-able object on a path to
/// the erroneous value.
/// </summary>
/// <remarks>
/// Unlike a <see cref="NameSegment" />, which names a property of one of
/// our classes, a key is known only at run time, and can be any string
/// at all.
/// </remarks>
public class KeySegment : Segment
{{
{I}public readonly string Key;
{I}public KeySegment(string key)
{I}{{
{II}Key = key;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Escape the characters which a JSON string may not hold as they are.
/// </summary>
private static string EscapeForJsonString(
{I}string text)
{{
{I}return (
{II}text
{III}.Replace("\\\\", "\\\\\\\\")
{III}.Replace("\\"", "\\\\\\"")
{III}.Replace("\\b", "\\\\b")
{III}.Replace("\\f", "\\\\f")
{III}.Replace("\\n", "\\\\n")
{III}.Replace("\\r", "\\\\r")
{III}.Replace("\\t", "\\\\t")
{I});
}}"""
        ),
        Stripped(
            f"""\
private static readonly System.Text.RegularExpressions.Regex VariableNameRe = (
{I}new System.Text.RegularExpressions.Regex(
{II}@"^[a-zA-Z_][a-zA-Z_0-9]*$"));"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Generate a JSON Path based on the path segments.
/// </summary>
/// <remarks>
/// See, for example, this page for more information on JSON path:
/// https://support.smartbear.com/alertsite/docs/monitors/api/endpoint/jsonpath.html
/// </remarks>
public static string GenerateJsonPath(
{I}ICollection<Segment> segments)
{{
{I}var parts = new List<string>(segments.Count);
{I}int i = 0;
{I}foreach (var segment in segments)
{I}{{
{II}string? part;
{II}switch (segment)
{II}{{
{III}case NameSegment nameSegment:
{IIII}if (VariableNameRe.IsMatch(nameSegment.Name))
{IIII}{{
{IIIII}part = (i == 0) ? nameSegment.Name : $".{{nameSegment.Name}}";
{IIII}}}
{IIII}else
{IIII}{{
{IIIII}part = (
{IIIIII}$"[\\"{{EscapeForJsonString(nameSegment.Name)}}\\"]");
{IIII}}}
{IIII}break;
{III}case IndexSegment indexSegment:
{IIII}part = $"[{{indexSegment.Index}}]";
{IIII}break;
{III}case KeySegment keySegment:
{IIII}// A key is no name of a property of one of our classes, so it is
{IIII}// always bracketed, whatever it looks like.
{IIII}part = (
{IIIII}$"[\\"{{EscapeForJsonString(keySegment.Key)}}\\"]");
{IIII}break;
{III}default:
{IIII}throw new System.InvalidOperationException(
{IIIII}$"Unexpected segment type: {{segment.GetType()}}");
{II}}}
{II}parts.Add(part);
{II}i++;
{I}}}
{I}return string.Join("", parts);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Generate a C# access path based on the path segments.
/// </summary>
/// <remarks>
/// The name segments are expected to denote the names of the properties in
/// C#, not the JSON property names. This is the path to report where in
/// an *instance* something went wrong -- on the serialization, say, where
/// the caller holds the instance and not a document.
///
/// A key and an index segment need no spelling of their own: a JSON-able
/// value is a <see cref="System.Text.Json.Nodes.JsonNode" />, which indexes
/// by both, so the path reads as a C# expression on the instance, *e.g.*,
/// <c>.SomeProperty["some key"][2]</c>.
/// </remarks>
public static string GenerateCSharpPath(
{I}ICollection<Segment> segments)
{{
{I}// NOTE (mristin):
{I}// We re-use the JSON path formatting as the implementation, but introduce
{I}// a separate function to signal to the reader in which form the name
{I}// segments are expected.
{I}return GenerateJsonPath(segments);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Escape special characters for XPath.
/// </summary>
private static string EscapeForXPath(
    string text)
{{
{I}// Mind the order, as we need to replace '&' first.
{I}//
{I}// For some benchmarks, see:
{I}// https://stackoverflow.com/questions/1321331/replace-multiple-string-elements-in-c-sharp
{I}return (
{II}text
{III}// Even though ampersand, less-then etc. can not occur in valid element names,
{III}// we escape them here for easier debugging and better bug reports.
{III}.Replace("&", "&amp;")
{III}.Replace("/", "&#47;")
{III}.Replace("<", "&lt;")
{III}.Replace(">", "&gt;")
{III}.Replace("\\"", "&quot;")
{III}.Replace("'", "&apos;")
{I});
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Generate a relative XPath based on the path segments.
/// </summary>
/// <remarks>
/// This method leaves out the leading slash ('/'). This is helpful if
/// to embed the error report in a larger document with a prefix etc.
/// </remarks>
public static string GenerateRelativeXPath(
{I}ICollection<Segment> segments)
{{
{I}var parts = new List<string>(segments.Count);
{I}foreach (var segment in segments)
{I}{{
{II}string? part;
{II}switch (segment)
{II}{{
{III}case NameSegment nameSegment:
{IIII}part = EscapeForXPath(nameSegment.Name);
{IIII}break;
{III}case IndexSegment indexSegment:
{IIII}part = $"*[{{indexSegment.Index}}]";
{IIII}break;
{III}case KeySegment keySegment:
{IIII}// A JSON-able object is written as an XML-RPC <struct>, which
{IIII}// holds the key of a member in a <name> child element, and not in
{IIII}// an attribute, so the XPath has to match on that child element.
{IIII}part = (
{IIIII}$"member[name=\\"{{EscapeForXPath(keySegment.Key)}}\\"]");
{IIII}break;
{III}default:
{IIII}throw new System.InvalidOperationException(
{IIIII}$"Unexpected segment type: {{segment.GetType()}}");
{II}}}
{II}parts.Add(part);
{I}}}
{I}return string.Join("/", parts);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Represent an error during the deserialization or the verification.
/// </summary>
public class Error
{{
{I}[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
{I}internal readonly LinkedList<Segment> _pathSegments = new LinkedList<Segment>();
{I}public readonly string Cause;
{I}public ICollection<Segment> PathSegments => _pathSegments;
{I}public Error(string cause)
{I}{{
{II}Cause = cause;
{I}}}

{I}public void PrependSegment(Segment segment)
{I}{{
{II}_pathSegments.AddFirst(segment);
{I}}}
}}"""
        ),
    ]

    writer = io.StringIO()
    writer.write(
        f"""\
namespace {namespace}
{{
{I}/// <summary>
{I}/// Provide reporting for de/serialization and verification.
{I}/// </summary>
{I}public static class Reporting
{I}{{
"""
    )

    for i, deserialize_block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(deserialize_block, II))

    writer.write(f"\n{I}}}  // public static class Reporting")
    writer.write(f"\n}}  // namespace {namespace}")

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using CodeAnalysis = System.Diagnostics.CodeAnalysis;

using System.Collections.Generic;  // can't alias"""
        )
    )

    # pylint: disable=line-too-long
    blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(writer.getvalue()),
        csharp_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
