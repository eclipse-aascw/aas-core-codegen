"""Generate code to test the arithmetic operations used in the verification."""

from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate, tests_common
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)
from aas_core_codegen.intermediate import uses as intermediate_uses


def _long_literal(value: int) -> str:
    """Render the 64-bit signed integer as a C# literal."""
    if value == tests_common.INT64_MIN:
        return "long.MinValue"

    if value == tests_common.INT64_MAX:
        return "long.MaxValue"

    if value == -tests_common.INT64_MAX:
        return "-long.MaxValue"

    return f"{value}L"


def _double_literal(value: float) -> str:
    """Render the floating-point number as a C# literal."""
    return f"{value!r}d"


# fmt: off
@require(
    lambda symbol_table:
    intermediate_uses.modulo(symbol_table) or intermediate_uses.abs_call(symbol_table)
)
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
    Generate code to test the arithmetic operations used in the verification.

    The meta-model is written in Python, so the invariants follow the Python semantics
    of the modulo and ``abs``. These tests document how the generated code behaves,
    and make sure it matches the Python semantics, see
    :py:mod:`aas_core_codegen.tests_common`.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = []

    if intermediate_uses.modulo(symbol_table):
        for i, case in enumerate(tests_common.FLOOR_MOD_CASES):
            blocks.append(
                Stripped(
                    f"""\
[Test]
public void Test_FloorMod_{i}()
{{
{I}// {case.explanation}
{I}Assert.AreEqual(
{II}{_long_literal(case.expected)},
{II}Our.Common.FloorMod({_long_literal(case.dividend)}, {_long_literal(case.divisor)}));
}}"""
                )
            )

    if intermediate_uses.abs_call(symbol_table):
        for i, (int_argument, int_expected) in enumerate(tests_common.ABS_INT_CASES):
            blocks.append(
                Stripped(
                    f"""\
[Test]
public void Test_Abs_of_long_{i}()
{{
{I}Assert.AreEqual(
{II}{_long_literal(int_expected)},
{II}System.Math.Abs({_long_literal(int_argument)}));
}}"""
                )
            )

        for i, (float_argument, float_expected) in enumerate(
            tests_common.ABS_FLOAT_CASES
        ):
            blocks.append(
                Stripped(
                    f"""\
[Test]
public void Test_Abs_of_double_{i}()
{{
{I}Assert.AreEqual(
{II}{_double_literal(float_expected)},
{II}System.Math.Abs({_double_literal(float_argument)}));
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
{I}/// Test the arithmetic operations used in the verification.
{I}/// </summary>
{I}/// <remarks>
{I}/// The meta-model is written in Python, so the invariants follow the Python
{I}/// semantics. In particular, the remainder of the modulo takes the sign of
{I}/// the divisor in Python (<c>-7 % 3 == 2</c>), while the native C# operator
{I}/// <c>%</c> gives the remainder with the sign of the dividend
{I}/// (<c>-7 % 3 == -1</c>). Therefore, we transpile the modulo to
{I}/// <c>Common.FloorMod</c> instead of the native operator.
{I}/// </remarks>
{I}public class TestArithmetic
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestArithmetic
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
