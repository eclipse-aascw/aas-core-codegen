"""Generate code to test the JSON de/serialization of interfaces."""

from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import INDENT as I, INDENT2 as II, INDENT3 as III


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
    Generate code to test the JSON de/serialization of interfaces.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = []

    for cls in symbol_table.classes:
        if cls.interface is None or len(cls.interface.implementers) == 0:
            continue

        for implementer_cls in cls.interface.implementers:
            if (
                implementer_cls.serialization is None
                or not implementer_cls.serialization.with_model_type
            ):
                continue

            interface_name_csharp = csharp_naming.interface_name(cls.interface.name)
            implementer_cls_name_csharp = csharp_naming.class_name(implementer_cls.name)

            blocks.append(
                Stripped(
                    f"""\
[Test]
public void Test_round_trip_{interface_name_csharp}_from_{implementer_cls_name_csharp}()
{{
{I}var instance = Our.Tests.CommonJsonization.LoadMaximal{implementer_cls_name_csharp}();

{I}var jsonObject = Our.Jsonization.Serialize.ToJsonObject(instance);

{I}var anotherInstance = Our.Jsonization.Deserialize.{interface_name_csharp}From(
{II}jsonObject);

{I}var anotherJsonObject = Our.Jsonization.Serialize.ToJsonObject(
{II}anotherInstance);

{I}Our.Tests.CommonJson.CheckJsonNodesEqual(
{II}jsonObject,
{II}anotherJsonObject,
{II}out Our.Reporting.Error? error);

{I}if (error != null)
{I}{{
{II}Assert.Fail(
{III}"When we serialize the complete instance of {implementer_cls_name_csharp} " +
{III}"as {interface_name_csharp}, we get an error in the round trip: " +
{III}$"{{Reporting.GenerateJsonPath(error.PathSegments)}}: " +
{III}error.Cause
{II});
{I}}}
}}  // void Test_round_trip_{interface_name_csharp}_from_{implementer_cls_name_csharp}"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}public class TestJsonizationOfInterfaces
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestJsonizationOfInterfaces
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
