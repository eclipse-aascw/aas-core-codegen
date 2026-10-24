"""Generate code to test the arithmetic operations used in the verification."""

from typing import List

from icontract import require

from aas_core_codegen import intermediate, tests_common
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.java import common as java_common
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
)


def _long_literal(value: int) -> str:
    """Render the 64-bit signed integer as a Java literal."""
    if value == tests_common.INT64_MIN:
        return "Long.MIN_VALUE"

    if value == tests_common.INT64_MAX:
        return "Long.MAX_VALUE"

    if value == -tests_common.INT64_MAX:
        return "-Long.MAX_VALUE"

    return f"{value}L"


def _double_literal(value: float) -> str:
    """Render the floating-point number as a Java literal."""
    return f"{value!r}d"


# fmt: off
@require(
    lambda symbol_table:
    intermediate_uses.modulo(symbol_table) or intermediate_uses.abs_call(symbol_table)
)
# fmt: on
def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the arithmetic operations used in the verification.

    The meta-model is written in Python, so the invariants follow the Python semantics
    of the modulo and ``abs``. These tests document how the generated code behaves,
    and make sure it matches the Python semantics, see
    :py:mod:`aas_core_codegen.tests_common`.
    """
    blocks: List[Stripped] = []

    if intermediate_uses.modulo(symbol_table):
        for i, case in enumerate(tests_common.FLOOR_MOD_CASES):
            blocks.append(
                Stripped(
                    f"""\
@Test
public void testFloorMod{i}() {{
{I}// {case.explanation}
{I}assertEquals(
{II}{_long_literal(case.expected)},
{II}Math.floorMod({_long_literal(case.dividend)}, {_long_literal(case.divisor)}));
}} // public void testFloorMod{i}"""
                )
            )

    if intermediate_uses.abs_call(symbol_table):
        for i, (int_argument, int_expected) in enumerate(tests_common.ABS_INT_CASES):
            blocks.append(
                Stripped(
                    f"""\
@Test
public void testAbsOfLong{i}() {{
{I}assertEquals(
{II}{_long_literal(int_expected)},
{II}Math.abs({_long_literal(int_argument)}));
}} // public void testAbsOfLong{i}"""
                )
            )

        for i, (float_argument, float_expected) in enumerate(
            tests_common.ABS_FLOAT_CASES
        ):
            blocks.append(
                Stripped(
                    f"""\
@Test
public void testAbsOfDouble{i}() {{
{I}assertEquals(
{II}{_double_literal(float_expected)},
{II}Math.abs({_double_literal(float_argument)}));
}} // public void testAbsOfDouble{i}"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestArithmetic.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

/**
 * Test the arithmetic operations used in the verification.
 *
 * <p>The meta-model is written in Python, so the invariants follow the Python
 * semantics. In particular, the remainder of the modulo takes the sign of
 * the divisor in Python ({{@code -7 % 3 == 2}}), while the native Java operator
 * {{@code %}} gives the remainder with the sign of the dividend
 * ({{@code -7 % 3 == -1}}). The two differ for the operands of different signs.
 * Therefore, the verification uses {{@link Math#floorMod(long, long)}}, which
 * computes the floored remainder as in Python, instead of the native operator.
 */
public class TestArithmetic {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestArithmetic

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
