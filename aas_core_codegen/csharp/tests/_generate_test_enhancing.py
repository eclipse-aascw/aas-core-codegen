"""Generate code to test enhancing the model instances."""

from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
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
    Generate code to test enhancing the model instances.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
class Enhancement
{{
{I}public readonly long SomeCustomId;

{I}public Enhancement(long someCustomId)
{I}{{
{II}SomeCustomId = someCustomId;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
private static OurEnhancing.Enhancer<Enhancement> CreateEnhancer()
{{
{I}long lastCustomId = 0;

{I}var enhancementFactory = new System.Func<IClass, Enhancement>(
{II}delegate
{II}{{
{III}lastCustomId++;
{III}return new Enhancement(lastCustomId);
{II}}}
{I});

{I}return new OurEnhancing.Enhancer<Enhancement>(enhancementFactory);
}}"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name = csharp_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{cls_name}()
{{
{I}var instance = (
{II}Our.Tests.CommonJsonization.LoadMaximal{cls_name}()
{I});

{I}var enhancer = CreateEnhancer();

{I}Assert.IsNull(enhancer.Unwrap(instance));

{I}var wrapped = enhancer.Wrap(instance);
{I}Assert.IsNotNull(wrapped);

{I}var idSet = new HashSet<long>();

{I}idSet.Add(enhancer.MustUnwrap(wrapped).SomeCustomId);
{I}idSet.UnionWith(
{II}wrapped
{III}.Descend()
{III}.Select(
{IIII}(descendant) =>
{IIIII}enhancer.MustUnwrap(descendant).SomeCustomId
{IIII})
{I});

{I}Assert.AreEqual(1, idSet.Min());
{I}Assert.AreEqual(idSet.Count, idSet.Max());
}}  // public void Test_{cls_name}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace}; // renamed
using OurEnhancing = {namespace}.Enhancing; // renamed

using System.Collections.Generic; // can't alias
using System.Linq; // can't alias

using NUnit.Framework; // can't alias

namespace {namespace}.Tests
{{
{I}public class TestEnhancing
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestEnhancing
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
