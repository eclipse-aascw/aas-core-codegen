"""Generate the common functions to de/serialize instances of a class."""


import io
import textwrap
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import INDENT as I, INDENT2 as II


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    namespace: csharp_common.NamespaceIdentifier, symbol_table: intermediate.SymbolTable
) -> str:
    """
    Generate the common functions to de/serialize instances of a class.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[str] = []

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_csharp = csharp_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
public static Our.{cls_name_csharp} LoadMaximal{cls_name_csharp}()
{{
{I}string path = Path.Combine(
{II}Our.Tests.Common.TestDataDir,
{II}"Json",
{II}"Expected",
{II}{csharp_common.string_literal(cls_name_json)},
{II}"maximal.json");

{I}var node = Our.Tests.CommonJson.ReadFromFile(path);

{I}var instance = Our.Jsonization.Deserialize.{cls_name_csharp}From(
{II}node);

{I}return instance;
}}  // public static Our.{cls_name_csharp} LoadMaximal{cls_name_csharp}

public static Our.{cls_name_csharp} LoadMinimal{cls_name_csharp}()
{{
{I}string path = Path.Combine(
{II}Our.Tests.Common.TestDataDir,
{II}"Json",
{II}"Expected",
{II}{csharp_common.string_literal(cls_name_json)},
{II}"minimal.json");

{I}var node = Our.Tests.CommonJson.ReadFromFile(path);

{I}var instance = Our.Jsonization.Deserialize.{cls_name_csharp}From(
{II}node);

{I}return instance;
}}  // public static Our.{cls_name_csharp} LoadMinimal{cls_name_csharp}"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using Path = System.IO.Path;

namespace {namespace}.Tests
{{
{I}/// <summary>
{I}/// Provide methods to load instances from JSON test data.
{I}/// </summary>
{I}public static class CommonJsonization
{I}{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, II))

    writer.write(
        f"""
{I}}}  // class CommonJsonization
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""
    )

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
