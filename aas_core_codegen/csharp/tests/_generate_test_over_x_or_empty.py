"""Generate code to test the ``OverXOrEmpty`` methods."""

from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line, Identifier
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
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
    Generate code to test the ``OverXOrEmpty`` methods.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = []

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_csharp = csharp_naming.class_name(concrete_cls.name)

        for prop in concrete_cls.properties:
            method_name_csharp = csharp_naming.method_name(
                Identifier(f"Over_{prop.name}_or_empty")
            )

            prop_name_csharp = csharp_naming.property_name(prop.name)

            if isinstance(
                prop.type_annotation, intermediate.OptionalTypeAnnotation
            ) and isinstance(
                prop.type_annotation.value,
                (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
            ):
                # NOTE (mristin):
                # We only count the items, so the test does not depend on
                # the order in which a set is iterated over.
                blocks.append(
                    Stripped(
                        f"""\
[Test]
public void Test_{cls_name_csharp}_{method_name_csharp}()
{{
{I}foreach (Our.{cls_name_csharp} instance in new[]
{I}{{
{II}Our.Tests.CommonJsonization.LoadMinimal{cls_name_csharp}(),
{II}Our.Tests.CommonJsonization.LoadMaximal{cls_name_csharp}()
{I}}})
{I}{{
{II}int count = 0;
{II}foreach (var _ in instance.{method_name_csharp}())
{II}{{
{III}count++;
{II}}}

{II}Assert.AreEqual(
{III}instance.{prop_name_csharp}?.Count ?? 0,
{III}count);
{I}}}
}}  // public void Test_{cls_name_csharp}_{method_name_csharp}"""
                    )
                )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}public class TestOverXOrEmpty
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestOverXOrEmpty
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
