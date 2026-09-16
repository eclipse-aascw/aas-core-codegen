"""Generate code to test the JSON de/serialization of concrete classes."""

from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
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
def generate(
    namespace: csharp_common.NamespaceIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> str:
    """
    Generate code to test the JSON de/serialization of concrete classes.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks = [
        Stripped(
            f"""\
private static void AssertSerializeDeserializeEqualsOriginal(
{I}Nodes.JsonNode originalNode, Aas.IClass instance, string path)
{{
{I}Nodes.JsonObject? serialized = null;
{I}try
{I}{{
{II}serialized = Aas.Jsonization.Serialize.ToJsonObject(instance);
{I}}}
{I}catch (System.Exception exception)
{I}{{
{II}Assert.Fail(
{III}"Expected no exception upon serialization of an instance " +
{III}$"de-serialized from {{path}}, but got: {{exception}}"
{II});
{I}}}

{I}if (serialized == null)
{I}{{
{II}Assert.Fail(
{III}$"Unexpected null serialization of an instance from {{path}}"
{II});
{I}}}
{I}else
{I}{{
{II}Aas.Tests.CommonJson.CheckJsonNodesEqual(
{III}originalNode,
{III}serialized,
{III}out Reporting.Error? inequalityError);
{II}if (inequalityError != null)
{II}{{
{III}Assert.Fail(
{IIII}$"The original JSON from {{path}} is unequal the serialized JSON: " +
{IIII}$"{{Reporting.GenerateJsonPath(inequalityError.PathSegments)}}: " +
{IIII}inequalityError.Cause
{III});
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
private static void AssertEqualsExpectedOrRerecordDeserializationException(
{I}Aas.Jsonization.Exception? exception,
{I}string path)
{{
{I}if (exception == null)
{I}{{
{II}Assert.Fail(
{III}$"Expected a Jsonization exception when de-serializing {{path}}, but got none."
{II});
{I}}}
{I}else
{I}{{
{II}string exceptionPath = path + ".exception";
{II}string got = exception.Message;
{II}if (Aas.Tests.Common.RecordMode)
{II}{{
{III}System.IO.File.WriteAllText(exceptionPath, got);
{II}}}
{II}else
{II}{{
{III}if (!System.IO.File.Exists(exceptionPath))
{III}{{
{IIII}throw new System.IO.FileNotFoundException(
{IIIII}$"The file with the recorded exception does not exist: {{exceptionPath}}; " +
{IIIII}"maybe you want to set the environment " +
{IIIII}$"variable {{Aas.Tests.Common.RecordModeEnvironmentVariableName}}?");
{III}}}

{III}string expected = System.IO.File.ReadAllText(exceptionPath);
{III}Assert.AreEqual(
{IIII}expected.Replace("\\r\\n", "\\n"),
{IIII}got.Replace("\\r\\n", "\\n"),
{IIII}$"The expected exception does not match the actual one for the file {{path}}");
{II}}}
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_csharp = csharp_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name_csharp}_ok()
{{
{I}var paths = Directory.GetFiles(
{II}Path.Combine(
{III}Aas.Tests.Common.TestDataDir,
{III}"Json",
{III}"Expected",
{III}{csharp_common.string_literal(cls_name_json)}
{II}),
{II}"*.json",
{II}System.IO.SearchOption.AllDirectories).ToList();
{I}paths.Sort();

{I}foreach (var path in paths)
{I}{{
{II}var node = Aas.Tests.CommonJson.ReadFromFile(path);

{II}var instance = Aas.Jsonization.Deserialize.{cls_name_csharp}From(
{III}node);

{II}var errors = Aas.Verification.Verify(instance).ToList();
{II}Aas.Tests.Common.AssertNoVerificationErrors(errors, path);

{II}AssertSerializeDeserializeEqualsOriginal(
{III}node, instance, path);
{I}}}
}}  // public void Test_{cls_name_csharp}_ok"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name_csharp}_deserialization_from_non_object_fail()
{{
{I}var node = Nodes.JsonValue.Create("INVALID")
{II}?? throw new System.InvalidOperationException(
{III}"Unexpected failure of the node creation");

{I}Aas.Jsonization.Exception? exception = null;
{I}try
{I}{{
{II}var _ = Aas.Jsonization.Deserialize.{cls_name_csharp}From(
{III}node);
{I}}}
{I}catch (Aas.Jsonization.Exception observedException)
{I}{{
{II}exception = observedException;
{I}}}

{I}if (exception == null)
{I}{{
{II}throw new AssertionException("Expected an exception, but got none");
{I}}}

{I}if (
{II}!exception.Message.StartsWith(
{III}"Expected a JsonObject representing {cls_name_csharp}, but got "))
{I}{{
{II}throw new AssertionException(
{III}$"Unexpected exception message: {{exception.Message}}");
{I}}}
}}  // public void Test_{cls_name_csharp}_deserialization_from_non_object_fail"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name_csharp}_deserialization_fail()
{{
{I}foreach (
{II}string causeDir in
{II}Directory.GetDirectories(
{III}Path.Combine(
{IIII}Aas.Tests.Common.TestDataDir,
{IIII}"Json",
{IIII}"Unexpected",
{IIII}"Unserializable"
{III})
{II})
{I})
{I}{{
{II}string clsDir = Path.Combine(
{III}causeDir,
{III}{csharp_common.string_literal(cls_name_json)}
{II});

{II}if (!Directory.Exists(clsDir))
{II}{{
{III}// No examples of {cls_name_csharp} for the failure cause.
{III}continue;
{II}}}

{II}var paths = Directory.GetFiles(
{III}clsDir,
{III}"*.json",
{III}System.IO.SearchOption.AllDirectories).ToList();
{II}paths.Sort();

{II}foreach (var path in paths)
{II}{{
{III}var node = Aas.Tests.CommonJson.ReadFromFile(path);

{III}Aas.Jsonization.Exception? exception = null;
{III}try
{III}{{
{IIII}var _ = Aas.Jsonization.Deserialize.{cls_name_csharp}From(
{IIIII}node);
{III}}}
{III}catch (Aas.Jsonization.Exception observedException)
{III}{{
{IIII}exception = observedException;
{III}}}

{III}AssertEqualsExpectedOrRerecordDeserializationException(
{IIII}exception, path);
{II}}}
{I}}}
}}  // public void Test_{cls_name_csharp}_deserialization_fail"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name_csharp}_verification_fail()
{{
{I}foreach (
{II}string causeDir in
{II}Directory.GetDirectories(
{III}Path.Combine(
{IIII}Aas.Tests.Common.TestDataDir,
{IIII}"Json",
{IIII}"Unexpected",
{IIII}"Invalid"
{III})
{II})
{I})
{I}{{
{II}string clsDir = Path.Combine(
{III}causeDir,
{III}{csharp_common.string_literal(cls_name_json)}
{II});

{II}if (!Directory.Exists(clsDir))
{II}{{
{III}// No examples of {cls_name_csharp} for the failure cause.
{III}continue;
{II}}}

{II}var paths = Directory.GetFiles(
{III}clsDir,
{III}"*.json",
{III}System.IO.SearchOption.AllDirectories).ToList();
{II}paths.Sort();

{II}foreach (var path in paths)
{II}{{
{III}var node = Aas.Tests.CommonJson.ReadFromFile(path);

{III}var instance = Aas.Jsonization.Deserialize.{cls_name_csharp}From(
{IIII}node);

{III}var errors = Aas.Verification.Verify(instance).ToList();
{III}Aas.Tests.Common.AssertEqualsExpectedOrRerecordVerificationErrors(
{IIII}errors, path);
{II}}}
{I}}}
}}  // public void Test_{cls_name_csharp}_verification_fail"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Aas = {namespace};  // renamed

using Directory = System.IO.Directory;
using Nodes = System.Text.Json.Nodes;
using Path = System.IO.Path;

using System.Linq;  // can't alias
using NUnit.Framework; // can't alias

namespace {namespace}.Tests
{{
{I}public class TestJsonizationOfConcreteClasses
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestJsonizationOfConcreteClasses
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
