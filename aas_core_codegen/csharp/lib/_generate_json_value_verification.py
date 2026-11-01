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


def _generate_check_json_able_number() -> Stripped:
    """
    Generate the check of a number in a JSON-able value.

    The verification, the de-serialization and the serialization of a JSON-able
    value all use it, so that they agree on what a JSON-able number is.
    """
    return Stripped(
        f"""\
/// <summary>
/// Check that <paramref name="jsonValue" />, if it is a number at all, is
/// a number of a JSON-able value.
/// </summary>
/// <remarks>
/// JSON knows a single numeric type, which all the other SDKs read into
/// a 64-bit floating-point number. Hence a JSON-able number has to be finite,
/// and an integer has to lie in the safe integer range [-2^53 + 1, 2^53 - 1],
/// as for the integer properties of the model -- otherwise a reader might
/// quietly get a different number than the one which was given.
/// </remarks>
/// <param name="jsonValue">JSON value to be checked</param>
/// <returns>
/// Cause why <paramref name="jsonValue" /> is not JSON-able, or <c>null</c>
/// if it is
/// </returns>
internal static string? CheckJsonAbleNumber(Nodes.JsonValue jsonValue)
{{
{I}// NOTE (mristin):
{I}// We can not switch on the kind of the number, since
{I}// ``Nodes.JsonValue.GetValueKind`` arrived only in .NET 8, and the generated
{I}// code has to build against .NET 6.
{I}if (jsonValue.TryGetValue<long>(out long integer))
{I}{{
{II}if (!Common.IsSafeInteger(integer))
{II}{{
{III}return UnsafeIntegerMessage(integer);
{II}}}
{I}}}
{I}else if (jsonValue.TryGetValue<ulong>(out ulong unsignedInteger))
{I}{{
{II}if (!Common.IsSafeInteger(unsignedInteger))
{II}{{
{III}return UnsafeIntegerMessage(unsignedInteger);
{II}}}
{I}}}
{I}else if (jsonValue.TryGetValue<double>(out double number))
{I}{{
{II}// NOTE (mristin):
{II}// JSON knows neither an infinity nor a not-a-number. A conformant parser
{II}// never gives us one, but the node may have been constructed
{II}// programmatically.
{II}if (!System.Double.IsFinite(number))
{II}{{
{III}return $"Expected a JSON-able value, but got the number {{number}}, " +
{IIII}"which is neither finite nor representable in JSON";
{II}}}
{I}}}

{I}return null;
}}"""
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
    (*i.e.*, recursively a null, a boolean, a number, a string, an array of
    JSON-able values or an object of JSON-able values with string keys),
    and, optionally, that it matches a specific top-level shape (an array or
    an object).

    This class does not depend on the meta-model at all, and is invoked from
    the ordinary per-class ``Verification.Verify`` dispatch exactly like
    every other property kind -- constrained-primitive keys of
    a ``JSONObject``-typed property are verified separately, by
    ``Verification.Verify`` reusing the already-generated per-constrained-
    primitive verify method (see ``_generate_verification.py``), not by this
    class.

    The ``namespace`` defines the base C# namespace of the generated code.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
/// <summary>
/// Report that the integer <paramref name="value" /> of a JSON-able value is
/// not a safe integer.
/// </summary>
/// <remarks>
/// See <see cref="Common.IsSafeInteger(long)" /> for what a safe
/// integer is.
/// </remarks>
/// <param name="value">integer outside the safe integer range</param>
/// <returns>the cause of the error</returns>
private static string UnsafeIntegerMessage(System.IFormattable value)
{{
{I}return $"Expected a JSON-able value, but got the integer {{value}}, " +
{II}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]";
}}"""
        ),
        _generate_check_json_able_number(),
        Stripped(
            f"""\
/// <summary>
/// Represent the expected top-level shape of a JSON-able value.
/// </summary>
public enum ExpectedShape
{{
{I}/// <summary>
{I}/// The value may be any JSON-able shape (a null, a boolean, a number,
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
/// Verify that <paramref name="that" /> holds no number anywhere, at any depth,
/// which is not a number of a JSON-able value.
/// </summary>
/// <remarks>
/// See <see cref="CheckJsonAbleNumber" /> for what a JSON-able number is.
/// A <c>null</c> is a JSON null, and hence a JSON-able value.
/// </remarks>
private static IEnumerable<Reporting.Error> VerifyRecursively(
{I}Nodes.JsonNode that)
{{
{I}switch (that)
{I}{{
{II}case Nodes.JsonArray jsonArray:
{III}{{
{IIII}int index = 0;
{IIII}foreach (Nodes.JsonNode? item in jsonArray)
{IIII}{{
{IIIII}if (item != null)
{IIIII}{{
{IIIIII}foreach (var error in VerifyRecursively(item))
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
{IIIII}if (member.Value != null)
{IIIII}{{
{IIIIII}foreach (var error in VerifyRecursively(member.Value))
{IIIIII}{{
{IIIIIII}error.PrependSegment(
{IIIIIIII}new Reporting.KeySegment(member.Key));
{IIIIIII}yield return error;
{IIIIII}}}
{IIIII}}}
{IIII}}}
{III}}}
{III}break;

{II}case Nodes.JsonValue jsonValue:
{III}{{
{IIII}string? cause = CheckJsonAbleNumber(jsonValue);
{IIII}if (cause != null)
{IIII}{{
{IIIII}yield return new Reporting.Error(cause);
{IIII}}}
{III}}}
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
/// a null, a boolean, a number, a string, an array or an object of
/// JSON-able values -- never an infinity, a not-a-number or an integer outside
/// the safe integer range [-2^53 + 1, 2^53 - 1], at any depth) and, if
/// <paramref name="expectedShape" /> is not
/// <see cref="ExpectedShape.Any" />, that its top-level shape matches.
/// </summary>
public static IEnumerable<Reporting.Error> Verify(
{I}Nodes.JsonNode? that,
{I}ExpectedShape expectedShape)
{{
{I}if (that == null)
{I}{{
{II}// NOTE (mristin):
{II}// A JSON null is a JSON-able value, but neither an array nor an object.
{II}if (expectedShape != ExpectedShape.Any)
{II}{{
{III}yield return new Reporting.Error(
{IIII}$"Expected a Json{{expectedShape}}, but got a null");
{II}}}
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

{I}foreach (var error in VerifyRecursively(that))
{I}{{
{II}yield return error;
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

    using_directives: List[Stripped] = []
    using_directives.extend(
        csharp_common.generate_using_our_directive_if_necessary(namespace)
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
