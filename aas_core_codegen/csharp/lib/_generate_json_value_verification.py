"""Generate code to verify JSON-able values."""

import io
import textwrap
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.csharp import common as csharp_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
    INDENT7 as IIIIIII,
    INDENT8 as IIIIIIII,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(namespace: csharp_common.NamespaceIdentifier) -> str:
    """
    Generate code to verify JSON-able values.

    This checks that a ``System.Text.Json.Nodes.JsonNode`` is JSON-able
    (*i.e.*, recursively a boolean, a number, a string, an array of
    JSON-able values or an object of JSON-able values with string keys --
    never a ``null``, at any depth), and, optionally, that it matches
    a specific top-level shape (an array or an object).

    This class does not depend on the meta-model at all, and is invoked from
    the ordinary per-class ``Verification.Verify`` dispatch exactly like
    every other property kind -- constrained-primitive keys of
    a ``JSONObject``-typed property are verified separately, by
    ``Verification.Verify`` reusing the already-generated per-constrained-
    primitive verify method (see ``_generate_verification.py``), not by this
    class.

    The ``namespace`` defines the AAS C# namespace.
    """
    blocks = [
        Stripped(
            f"""\
/// <summary>
/// Represent the expected top-level shape of a JSON-able value.
/// </summary>
public enum ExpectedShape
{{
{I}/// <summary>
{I}/// The value may be any JSON-able shape (a boolean, a number,
{I}/// a string, an array or an object).
{I}/// </summary>
{I}Any,

{I}/// <summary>
{I}/// The value must be a JSON-able array.
{I}/// </summary>
{I}Array,

{I}/// <summary>
{I}/// The value must be a JSON-able object.
{I}/// </summary>
{I}Object
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Verify that <paramref name="that" /> does not contain a <c>null</c>
/// anywhere, at any depth -- a JSON <c>null</c> has no representation as
/// a JSON-able value.
/// </summary>
private static IEnumerable<Reporting.Error> VerifyNoNullRecursively(
{I}Nodes.JsonNode that)
{{
{I}switch (that)
{I}{{
{II}case Nodes.JsonArray jsonArray:
{III}{{
{IIII}int index = 0;
{IIII}foreach (Nodes.JsonNode? item in jsonArray)
{IIII}{{
{IIIII}if (item == null)
{IIIII}{{
{IIIIII}var error = new Reporting.Error(
{IIIIIII}"Expected a JSON-able value, but got a null");
{IIIIII}error.PrependSegment(
{IIIIIII}new Reporting.IndexSegment(index));
{IIIIII}yield return error;
{IIIII}}}
{IIIII}else
{IIIII}{{
{IIIIII}foreach (var error in VerifyNoNullRecursively(item))
{IIIIII}{{
{IIIIIII}error.PrependSegment(
{IIIIIIII}new Reporting.IndexSegment(index));
{IIIIIII}yield return error;
{IIIIII}}}
{IIIII}}}
{IIIII}index++;
{IIII}}}
{III}}}
{III}break;

{II}case Nodes.JsonObject jsonObject:
{III}{{
{IIII}foreach (
{IIIII}KeyValuePair<string, Nodes.JsonNode?> member
{IIIIII}in jsonObject)
{IIII}{{
{IIIII}if (member.Value == null)
{IIIII}{{
{IIIIII}var error = new Reporting.Error(
{IIIIIII}"Expected a JSON-able value, but got a null");
{IIIIII}error.PrependSegment(
{IIIIIII}new Reporting.NameSegment(member.Key));
{IIIIII}yield return error;
{IIIII}}}
{IIIII}else
{IIIII}{{
{IIIIII}foreach (var error in VerifyNoNullRecursively(member.Value))
{IIIIII}{{
{IIIIIII}error.PrependSegment(
{IIIIIIII}new Reporting.NameSegment(member.Key));
{IIIIIII}yield return error;
{IIIIII}}}
{IIIII}}}
{IIII}}}
{III}}}
{III}break;

{II}case Nodes.JsonValue _:
{III}break;

{II}default:
{III}throw new System.InvalidOperationException(
{IIII}$"Unexpected node type: {{that.GetType()}}");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Verify that <paramref name="that" /> is JSON-able (recursively
/// a boolean, a number, a string, an array or an object of JSON-able
/// values -- never a <c>null</c>, at any depth) and, if
/// <paramref name="expectedShape" /> is not
/// <see cref="ExpectedShape.Any" />, that its top-level shape matches.
/// </summary>
public static IEnumerable<Reporting.Error> Verify(
{I}Nodes.JsonNode? that,
{I}ExpectedShape expectedShape)
{{
{I}if (that == null)
{I}{{
{II}yield return new Reporting.Error(
{III}"Expected a JSON-able value, but got a null");
{II}yield break;
{I}}}

{I}switch (expectedShape)
{I}{{
{II}case ExpectedShape.Array:
{III}if (!(that is Nodes.JsonArray))
{III}{{
{IIII}yield return new Reporting.Error(
{IIIII}$"Expected a JsonArray, but got {{that.GetType()}}");
{IIII}yield break;
{III}}}
{III}break;
{II}case ExpectedShape.Object:
{III}if (!(that is Nodes.JsonObject))
{III}{{
{IIII}yield return new Reporting.Error(
{IIIII}$"Expected a JsonObject, but got {{that.GetType()}}");
{IIII}yield break;
{III}}}
{III}break;
{II}case ExpectedShape.Any:
{III}break;
{II}default:
{III}throw new System.InvalidOperationException(
{IIII}$"Unexpected expectedShape: {{expectedShape}}");
{I}}}

{I}foreach (var error in VerifyNoNullRecursively(that))
{I}{{
{II}yield return error;
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    writer.write(
        f"""\
namespace {namespace}
{{
{I}/// <summary>
{I}/// Verify that a JSON-able value is well-formed.
{I}/// </summary>
{I}public static class JsonValueVerification
{I}{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, II))

    writer.write(f"\n{I}}}  // public static class JsonValueVerification")
    writer.write(f"\n}}  // namespace {namespace}")

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using Nodes = System.Text.Json.Nodes;

using System.Collections.Generic;  // can't alias"""
        )
    )

    final_blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(writer.getvalue()),
        csharp_common.WARNING,
    ]

    final_writer = io.StringIO()
    for i, block in enumerate(final_blocks):
        if i > 0:
            final_writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        final_writer.write(block)

    final_writer.write("\n")

    return final_writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
