"""Generate code to test the JSON de/serialization of concrete classes."""

from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Identifier, Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_serialization_failure_tests(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the tests that a number unrepresentable in JSON is refused."""
    result = []  # type: List[Stripped]

    for numeric_place in intermediate.numeric_places(symbol_table):
        if numeric_place.a_type is intermediate.PrimitiveType.FLOAT:
            value_type = "double"
            zero_literal = "0.0"
            what = "non_finite"
            values_literal = (
                "{ System.Double.PositiveInfinity, "
                "System.Double.NegativeInfinity, System.Double.NaN }"
            )
        else:
            value_type = "long"
            zero_literal = "0L"
            what = "out_of_range"
            values_literal = "{ 9007199254740992L, -9007199254740992L }"

        prop_name = csharp_naming.property_name(numeric_place.prop.name)

        json_name = numeric_place.prop.json_name

        if numeric_place.index is None:
            mutation = Stripped(f"instance.{prop_name} = value;")
            expected_path = f"{json_name}"
        elif numeric_place.in_list:
            # NOTE (mristin):
            # The value goes to the position indicated by the numeric place so
            # that a serializer which always reports the index 0 does not pass.
            items_joined = ", ".join(
                "value" if i == numeric_place.index else zero_literal
                for i in range(numeric_place.index + 1)
            )

            mutation = Stripped(
                f"instance.{prop_name} = "
                f"new List<{value_type}>() {{ {items_joined} }};"
            )
            expected_path = f"{json_name}[{numeric_place.index}]"
        else:
            tuple_type_anno = numeric_place.prop.type_annotation
            assert isinstance(tuple_type_anno, intermediate.TupleTypeAnnotation), (
                f"Expected a tuple at the numeric place of "
                f"{numeric_place.cls.name}.{numeric_place.prop.name}, "
                f"but got: {tuple_type_anno}"
            )

            items_joined = ",\n".join(
                "value"
                if i == numeric_place.index
                else f"instance.{prop_name}.Item{i + 1}"
                for i in range(len(tuple_type_anno.items))
            )

            mutation = Stripped(
                f"""\
instance.{prop_name} = (
{I}{indent_but_first_line(items_joined, I)});"""
            )
            expected_path = f"{json_name}[{numeric_place.index}]"

        cls_name_json = naming.json_model_type(numeric_place.cls.name)

        from_name = csharp_naming.method_name(
            Identifier(f"{numeric_place.cls.name}_from")
        )

        test_name = csharp_naming.method_name(
            Identifier(
                f"Test_{numeric_place.cls.name}_{numeric_place.prop.name}"
                f"_serialization_{what}"
            )
        )

        result.append(
            Stripped(
                f"""\
[Test]
public void {test_name}()
{{
{I}foreach (var value in new {value_type}[] {values_literal})
{I}{{
{II}var node = LoadTheFirstExpected(
{III}{csharp_common.string_literal(cls_name_json)});

{II}var instance = Aas.Jsonization.Deserialize.{from_name}(
{III}node);

{II}{indent_but_first_line(mutation, II)}

{II}Aas.Jsonization.SerializationException? exception = null;
{II}try
{II}{{
{III}var _ = Aas.Jsonization.Serialize.ToJsonObject(instance);
{II}}}
{II}catch (Aas.Jsonization.SerializationException observedException)
{II}{{
{III}exception = observedException;
{II}}}

{II}Assert.IsNotNull(
{III}exception,
{III}"Expected the serialization to fail at " +
{IIII}{csharp_common.string_literal(expected_path)} +
{IIII}", but it succeeded");

{II}Assert.AreEqual(
{III}{csharp_common.string_literal(expected_path)},
{III}exception!.Path);
{I}}}
}}  // public void {test_name}"""
            )
        )

    if len(result) > 0:
        result.insert(
            0,
            Stripped(
                f"""\
/// <summary>
/// Read the first recorded example of the <paramref name="modelType" />.
/// </summary>
private static Nodes.JsonNode LoadTheFirstExpected(string modelType)
{{
{I}var paths = Directory.GetFiles(
{II}Path.Combine(
{III}Aas.Tests.Common.TestDataDir,
{III}"Json",
{III}"Expected",
{III}modelType),
{II}"*.json",
{II}System.IO.SearchOption.AllDirectories).ToList();
{I}paths.Sort();

{I}Assert.IsNotEmpty(
{II}paths,
{II}$"Expected at least one recorded example of {{modelType}}, but got none");

{I}return Aas.Tests.CommonJson.ReadFromFile(paths[0]);
}}"""
            ),
        )

    return result


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

    blocks.extend(_generate_serialization_failure_tests(symbol_table))

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Aas = {namespace};  // renamed

using Directory = System.IO.Directory;
using Nodes = System.Text.Json.Nodes;
using Path = System.IO.Path;

using System.Collections.Generic;  // can't alias
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
