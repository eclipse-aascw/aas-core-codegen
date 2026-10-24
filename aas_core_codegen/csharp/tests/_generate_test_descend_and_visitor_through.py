"""Generate code to test the ``Descend`` methods and ``VisitorThrough``."""

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
    Generate code to test the ``Descend`` methods and ``VisitorThrough``.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[str] = [
        Stripped(
            f"""\
class TracingVisitorThrough : Our.Visitation.VisitorThrough
{{
{I}public readonly List<string> Log = new List<string>();

{I}public override void Visit(IClass that)
{I}{{
{II}Log.Add(Our.Tests.Common.Trace(that));
{II}base.Visit(that);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
private static void AssertDescendAndVisitorThroughSame(
{I}Our.IClass instance)
{{
{I}var logFromDescend = new List<string>();
{I}foreach (var subInstance in instance.Descend())
{I}{{
{II}logFromDescend.Add(Our.Tests.Common.Trace(subInstance));
{I}}}

{I}var visitor = new TracingVisitorThrough();
{I}visitor.Visit(instance);
{I}var traceFromVisitor = visitor.Log;

{I}Assert.IsNotEmpty(traceFromVisitor);

{I}Assert.AreEqual(
{II}Our.Tests.Common.Trace(instance),
{II}traceFromVisitor[0]);

{I}traceFromVisitor.RemoveAt(0);

{I}Assert.That(traceFromVisitor, Is.EquivalentTo(logFromDescend));
}}"""
        ),
        Stripped(
            f"""\
private static void CompareOrRerecordTrace(
{I}IClass instance,
{I}string expectedPath)
{{
{I}var writer = new System.IO.StringWriter();
{I}foreach (var descendant in instance.Descend())
{I}{{
{II}writer.WriteLine(Our.Tests.Common.Trace(descendant));
{I}}}

{I}string got = writer.ToString();

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

{II}System.IO.File.WriteAllText(expectedPath, got);
{I}}}
{I}else
{I}{{
{II}if (!System.IO.File.Exists(expectedPath))
{II}{{
{III}throw new System.IO.FileNotFoundException(
{IIII}"The file with the recorded trace does not " +
{IIII}$"exist: {{expectedPath}}; maybe you want to set the environment " +
{IIII}$"variable {{Our.Tests.Common.RecordModeEnvironmentVariableName}}?");
{II}}}

{II}string expected = System.IO.File.ReadAllText(expectedPath);
{II}Assert.AreEqual(
{III}expected.Replace("\\r\\n", "\\n"),
{III}got.Replace("\\r\\n", "\\n"),
{III}$"The expected trace from {{expectedPath}} does not match the actual one");
{I}}}
}}"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_csharp = csharp_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_Descend_of_{cls_name_csharp}()
{{
{I}Our.{cls_name_csharp} instance = (
{II}Our.Tests.CommonJsonization.LoadMaximal{cls_name_csharp}());

{I}CompareOrRerecordTrace(
{II}instance,
{II}Path.Combine(
{III}Our.Tests.Common.TestDataDir,
{III}"Descend",
{III}{csharp_common.string_literal(cls_name_json)},
{III}"maximal.json.trace"));
}}  // public void Test_Descend_of_{cls_name_csharp}

[Test]
public void Test_Descend_against_VisitorThrough_for_{cls_name_csharp}()
{{
{I}Our.{cls_name_csharp} instance = (
{II}Our.Tests.CommonJsonization.LoadMaximal{cls_name_csharp}());

{I}AssertDescendAndVisitorThroughSame(
{II}instance);
}}  // public void Test_Descend_against_VisitorThrough_for_{cls_name_csharp}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using Directory = System.IO.Directory;
using Path = System.IO.Path;

using NUnit.Framework; // can't alias
using System.Collections.Generic;  // can't alias

namespace {namespace}.Tests
{{
{I}public class TestDescendAndVisitorThrough
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestDescendAndVisitorThrough
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
