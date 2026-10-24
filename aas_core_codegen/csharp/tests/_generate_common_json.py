"""Generate code for shared JSON functionality across unit tests."""

from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import (
    common as csharp_common,
)
from aas_core_codegen.csharp.common import (
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
def generate(namespace: csharp_common.NamespaceIdentifier) -> str:
    """
    Generate code for shared JSON functionality across unit tests.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
public static Nodes.JsonNode ReadFromFile(string path)
{{
{I}using var stream = new FileStream(path, FileMode.Open);
{I}Nodes.JsonNode? node;
{I}try
{I}{{
{II}node = Nodes.JsonNode.Parse(stream);
{I}}}
{I}catch (JsonException exception)
{I}{{
{II}throw new System.InvalidOperationException(
{III}$"Expected the file to be a valid JSON, but it was not: {{path}}; "
{IIII}+ $"exception was: {{exception}}"
{II});
{I}}}

{I}if (node is null)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Expected the file to be a non-null JSON value, " + $"but it was null: {{path}}"
{II});
{I}}}

{I}return node;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize <paremref name="something" /> to a uniform JSON text
/// such that we can use it for comparisons in the tests.
/// </summary>
public static Nodes.JsonNode ToJson(object something)
{{
{I}switch (something)
{I}{{
{II}case bool aBool:
{III}return Nodes.JsonValue.Create(aBool);
{II}case long aLong:
{III}return Nodes.JsonValue.Create(aLong);
{II}case double aDouble:
{III}return Nodes.JsonValue.Create(aDouble);
{II}case string aString:
{III}return Nodes.JsonValue.Create(aString)
{IIII}?? throw new System.InvalidOperationException(
{IIIII}$"Could not convert {{something}} " + "to a JSON string"
{IIII});
{II}case byte[] someBytes:
{III}return Nodes.JsonValue.Create(System.Convert.ToBase64String(someBytes))
{IIII}?? throw new System.InvalidOperationException(
{IIIII}$"Could not convert {{something}} to " + "a base64-encoded JSON string"
{IIII});
{II}case Our.IClass instance:
{III}return Our.Jsonization.Serialize.ToJsonObject(instance);
{II}case Nodes.JsonNode aNode:
{III}// NOTE (mristin):
{III}// A JSON node remembers its parent, so we copy it before handing it
{III}// out. ``DeepClone`` arrived only in .NET 8, so we serialize instead.
{III}return System.Text.Json.JsonSerializer.SerializeToNode(aNode)
{IIII}?? throw new System.InvalidOperationException(
{IIIII}$"Could not copy the JSON node {{aNode.ToJsonString()}}"
{IIII});
{II}default:
{III}throw new System.ArgumentException(
{IIII}$"The conversion of type {{something.GetType()}} "
{IIIII}+ $"to a JSON node has not been defined: {{something}}"
{III});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Infer the node kind of the JSON node.
/// </summary>
/// <remarks>
/// This function is necessary since NET6 does not fully support node kinds yet.
/// See:
/// <ul>
/// <li>https://github.com/dotnet/runtime/issues/53406</li>
/// <li>https://github.com/dotnet/runtime/issues/55827</li>
/// <li>https://github.com/dotnet/runtime/issues/56592</li>
/// </ul>
/// </remarks>
private static string GetNodeKind(Nodes.JsonNode node)
{{
{I}switch (node)
{I}{{
{II}case Nodes.JsonArray _:
{III}return "array";
{II}case Nodes.JsonObject _:
{III}return "object";
{II}case Nodes.JsonValue _:
{III}return "value";
{II}default:
{III}throw new System.InvalidOperationException(
{IIII}$"Unhandled JsonNode: {{node.GetType()}}"
{III});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
public static void CheckJsonNodesEqual(
{I}Nodes.JsonNode that,
{I}Nodes.JsonNode other,
{I}out Reporting.Error? error
)
{{
{I}error = null;

{I}var thatNodeKind = GetNodeKind(that);
{I}var otherNodeKind = GetNodeKind(other);

{I}if (thatNodeKind != otherNodeKind)
{I}{{
{II}error = new Reporting.Error(
{III}$"Mismatch in node kinds : {{thatNodeKind}} != {{otherNodeKind}}"
{II});
{II}return;
{I}}}

{I}switch (that)
{I}{{
{II}case Nodes.JsonArray thatArray:
{III}{{
{IIII}var otherArray = (other as Nodes.JsonArray)!;
{IIII}if (thatArray.Count != otherArray.Count)
{IIII}{{
{IIIII}error = new Reporting.Error(
{IIIII}    $"Unequal array lengths: {{thatArray.Count}} != {{otherArray.Count}}"
{IIIII});
{IIIII}return;
{IIII}}}

{IIII}for (int i = 0; i < thatArray.Count; i++)
{IIII}{{
{IIIII}CheckJsonNodesEqual(thatArray[i]!, otherArray[i]!, out error);
{IIIII}if (error != null)
{IIIII}{{
{IIIII}    error.PrependSegment(new Reporting.IndexSegment(i));
{IIIII}    return;
{IIIII}}}
{IIII}}}

{IIII}break;
{III}}}
{II}case Nodes.JsonObject thatObject:
{III}{{
{IIII}var thatDictionary = thatObject as IDictionary<string, Nodes.JsonNode>;
{IIII}var otherDictionary = (other as IDictionary<string, Nodes.JsonNode>)!;

{IIII}var thatKeys = thatDictionary.Keys.ToList();
{IIII}thatKeys.Sort();

{IIII}var otherKeys = otherDictionary.Keys.ToList();
{IIII}otherKeys.Sort();

{IIII}if (!thatKeys.SequenceEqual(otherKeys))
{IIII}{{
{IIIII}error = new Reporting.Error(
{IIIII}    "Objects with different properties: "
{IIIII}        + $"{{string.Join(", ", thatKeys)}} != "
{IIIII}        + $"{{string.Join(", ", otherKeys)}}"
{IIIII});
{IIIII}return;
{IIII}}}

{IIII}foreach (var key in thatKeys)
{IIII}{{
{IIIII}CheckJsonNodesEqual(thatDictionary[key], otherDictionary[key], out error);
{IIIII}if (error != null)
{IIIII}{{
{IIIII}    error.PrependSegment(new Reporting.NameSegment(key));
{IIIII}    return;
{IIIII}}}
{IIII}}}

{IIII}break;
{III}}}
{II}case Nodes.JsonValue thatValue:
{III}{{
{IIII}string thatAsJsonString = thatValue.ToJsonString();

{IIII}// NOTE (mristin):
{IIII}// This is slow, but there is no way around it at the moment with NET6.
{IIII}// See:
{IIII}// * https://github.com/dotnet/runtime/issues/56592
{IIII}// * https://github.com/dotnet/runtime/issues/55827
{IIII}// * https://github.com/dotnet/runtime/issues/53406
{IIII}var otherValue = (other as Nodes.JsonValue)!;
{IIII}string otherAsJsonString = otherValue.ToJsonString();

{IIII}if (thatAsJsonString != otherAsJsonString)
{IIII}{{
{IIIII}error = new Reporting.Error(
{IIIII}    $"Unequal values: {{thatAsJsonString}} != {{otherAsJsonString}}"
{IIIII});
{IIIII}// ReSharper disable once RedundantJumpStatement
{IIIII}return;
{IIII}}}

{IIII}break;
{III}}}
{II}default:
{III}throw new System.InvalidOperationException(
{IIII}$"Unhandled JSON node: {{that.GetType()}}"
{III});
{I}}}
}}"""
        ),
    ]

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace}; // renamed

using FileMode = System.IO.FileMode;
using FileStream = System.IO.FileStream;
using JsonException = System.Text.Json.JsonException;
using Nodes = System.Text.Json.Nodes;

using System.Collections.Generic; // can't alias
using System.Linq; // can't alias

namespace {namespace}.Tests
{{
{I}public static class CommonJson
{I}{{
{I}{indent_but_first_line(blocks_joined, I)}
{I}}}  // public static class CommonJson
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
