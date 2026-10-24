"""Generate code to test the ``XOrDefault`` methods."""

from typing import List, Optional

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
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
    Generate code to test the ``XOrDefault`` methods.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
private static void CompareOrRerecordValue(
{I}object value,
{I}string expectedPath)
{{
{I}Nodes.JsonNode got = Our.Tests.CommonJson.ToJson(
{II}value);

{I}if (Our.Tests.Common.RecordMode)
{I}{{
{II}string? parent = Path.GetDirectoryName(expectedPath);
{II}if (parent != null)
{II}{{
{III}if (!Directory.Exists(parent))
{III}{{
{IIII}Directory.CreateDirectory(parent);
{III}}}
{II}}}

{II}System.IO.File.WriteAllText(
{III}expectedPath, got.ToJsonString());
{I}}}
{I}else
{I}{{
{II}if (!System.IO.File.Exists(expectedPath))
{II}{{
{III}throw new System.IO.FileNotFoundException(
{IIII}$"The file with the recorded value does not exist: {{expectedPath}}; " +
{IIII}"maybe you want to set the environment " +
{IIII}$"variable {{Our.Tests.Common.RecordModeEnvironmentVariableName}}?");
{II}}}

{II}Nodes.JsonNode expected = Our.Tests.CommonJson.ReadFromFile(
{III}expectedPath);

{II}Our.Tests.CommonJson.CheckJsonNodesEqual(
{III}expected, got, out Our.Reporting.Error? error);

{II}if (error != null)
{II}{{
{III}Assert.Fail(
{IIII}$"The original value from {{expectedPath}} is unequal the obtain value " +
{IIII}"when serialized to JSON: " +
{IIII}$"{{Reporting.GenerateJsonPath(error.PathSegments)}}: " +
{IIII}error.Cause
{III});
{II}}}
{I}}}
}}"""
        )
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_csharp = csharp_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        x_or_default_methods: List[intermediate.MethodUnion] = []
        for method in concrete_cls.methods:
            if (
                method.name.endswith("_or_default")
                and method.visibility is intermediate.Visibility.PUBLIC
            ):
                x_or_default_methods.append(method)

        for method in x_or_default_methods:
            method_name_csharp = csharp_naming.method_name(method.name)

            result_enum: Optional[intermediate.Enumeration] = None
            assert method.returns is not None, (
                f"Expected all X_or_default to return something, "
                f"but got None for {concrete_cls.name}.{method.name}"
            )

            if isinstance(
                method.returns, intermediate.OurTypeAnnotation
            ) and isinstance(method.returns.our_type, intermediate.Enumeration):
                result_enum = method.returns.our_type

            if result_enum is None:
                value_assignment_snippet = Stripped(
                    f"var value = instance.{method_name_csharp}();"
                )
            else:
                value_assignment_snippet = Stripped(
                    f"""\
string value = Our.Stringification.ToString(
{I}instance.{method_name_csharp}())
{II}?? throw new System.InvalidOperationException(
{III}"Failed to stringify the enum");"""
                )

            # noinspection SpellCheckingInspection
            blocks.append(
                Stripped(
                    f"""\
[Test]
public void Test_{cls_name_csharp}_{method_name_csharp}_non_default()
{{
{I}Our.{cls_name_csharp} instance = (
{II}Our.Tests.CommonJsonization.LoadMaximal{cls_name_csharp}());

{I}{indent_but_first_line(value_assignment_snippet, I)}

{I}CompareOrRerecordValue(
{II}value,
{II}Path.Combine(
{III}Our.Tests.Common.TestDataDir,
{III}"XOrDefault",
{III}{csharp_common.string_literal(cls_name_json)},
{III}"{method_name_csharp}.non-default.json"));
}}  // public void Test_{cls_name_csharp}_{method_name_csharp}_non_default

[Test]
public void Test_{cls_name_csharp}_{method_name_csharp}_default()
{{
{I}Our.{cls_name_csharp} instance = (
{II}Our.Tests.CommonJsonization.LoadMinimal{cls_name_csharp}());

{I}{indent_but_first_line(value_assignment_snippet, I)}

{I}CompareOrRerecordValue(
{II}value,
{II}Path.Combine(
{III}Our.Tests.Common.TestDataDir,
{III}"XOrDefault",
{III}{csharp_common.string_literal(cls_name_json)},
{III}"{method_name_csharp}.default.json"));
}}  // public void Test_{cls_name_csharp}_{method_name_csharp}_default"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using Directory = System.IO.Directory;
using Nodes = System.Text.Json.Nodes;
using Path = System.IO.Path;

using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}public class TestXOrDefault
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestXOrDefault
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
