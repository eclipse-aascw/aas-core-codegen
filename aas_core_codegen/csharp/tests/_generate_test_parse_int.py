"""Generate code to test ``int`` on strings."""

from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate, tests_common
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import uses as intermediate_uses


# fmt: off
@require(lambda symbol_table: intermediate_uses.int_call(symbol_table))
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
    Generate code to test ``int`` on strings.

    The transpiled ``int`` accepts only the safe integers. We generate the tests
    from the very same cases in all the SDKs, see
    :py:mod:`aas_core_codegen.tests_common`.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = []

    for i, (text, expected_int) in enumerate(tests_common.PARSE_INT_CASES):
        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_ParseSafeInt_{i}()
{{
{I}Assert.AreEqual(
{II}{expected_int}L,
{II}Our.Common.ParseSafeInt({csharp_common.string_literal(text)}));
}}"""
            )
        )

    for i, text in enumerate(tests_common.PARSE_INT_INVALID_CASES):
        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_ParseSafeInt_invalid_{i}()
{{
{I}Assert.Throws<System.ArgumentException>(
{II}() => Our.Common.ParseSafeInt(
{III}{csharp_common.string_literal(text)}));
}}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}/// <summary>
{I}/// Test <c>int</c> on strings as used in the transpiled code.
{I}/// </summary>
{I}/// <remarks>
{I}/// <para>
{I}/// The built-in <c>int</c> is transpiled to <c>Common.ParseSafeInt</c>,
{I}/// which accepts only an optional sign followed by the ASCII digits, and only
{I}/// the safe integers, <em>i.e.</em>, the integers within <c>-(2^53 - 1)</c>
{I}/// and <c>2^53 - 1</c>. Otherwise, it throws.
{I}/// </para>
{I}/// <para>
{I}/// All the SDKs test against the very same cases.
{I}/// </para>
{I}/// </remarks>
{I}public class TestParseInt
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestParseInt
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
