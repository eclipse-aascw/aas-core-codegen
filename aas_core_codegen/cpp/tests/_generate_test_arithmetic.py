"""Generate code to test the arithmetic operations used in the verification."""

from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate, tests_common
from aas_core_codegen.common import Stripped
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
)
from aas_core_codegen.intermediate import uses as intermediate_uses

#: Smallest 32-bit signed integer, the smallest ``int`` literal on all our platforms
_INT32_MIN = -(2**31)

#: Largest 32-bit signed integer, the largest ``int`` literal on all our platforms
_INT32_MAX = 2**31 - 1


def _int64_literal(value: int) -> str:
    """
    Render the 64-bit signed integer as a C++ expression.

    Mind that ``-9223372036854775808`` is not a valid literal in C++, as it is
    parsed as the negation of a literal which does not fit into ``int64_t``.
    """
    if value == tests_common.INT64_MIN:
        return "std::numeric_limits<int64_t>::min()"

    if value == tests_common.INT64_MAX:
        return "std::numeric_limits<int64_t>::max()"

    if value == -tests_common.INT64_MAX:
        return "-std::numeric_limits<int64_t>::max()"

    if _INT32_MIN <= value <= _INT32_MAX:
        return str(value)

    return f"INT64_C({value})"


def _double_literal(value: float) -> str:
    """Render the floating-point number as a C++ literal."""
    return repr(value)


# fmt: off
@require(
    lambda symbol_table:
    intermediate_uses.modulo(symbol_table) or intermediate_uses.abs_call(symbol_table)
)
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """
    Generate code to test the arithmetic operations used in the verification.

    The meta-model is written in Python, so the invariants follow the Python semantics
    of the modulo and ``abs``. These tests document how the generated code behaves,
    and make sure it matches the Python semantics, see
    :py:mod:`aas_core_codegen.tests_common`.
    """
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            """\
/**
 * Test the arithmetic operations used in the verification.
 *
 * The meta-model is written in Python, so the invariants follow the Python
 * semantics. In particular, the remainder of the modulo takes the sign of
 * the divisor in Python (<code>-7 % 3 == 2</code>), while the native C++ operator
 * <code>%</code> truncates the division towards zero so that the remainder takes
 * the sign of the dividend (<code>-7 % 3 == -1</code>). Therefore, we transpile
 * the modulo to <code>common::FloorMod</code> instead of the native
 * operator.
 */"""
        ),
        Stripped(
            f"""\
#include "{include_prefix_path}/common.hpp"

#pragma warning(push, 0)
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <limits>
#pragma warning(pop)

#include <catch2/catch.hpp>

namespace our = {library_namespace};"""
        ),
    ]

    if intermediate_uses.modulo(symbol_table):
        for case in tests_common.FLOOR_MOD_CASES:
            blocks.append(
                Stripped(
                    f"""\
TEST_CASE("Test FloorMod of {case.dividend} by {case.divisor}") {{
{I}// {case.explanation}
{I}const int64_t dividend = {_int64_literal(case.dividend)};
{I}const int64_t divisor = {_int64_literal(case.divisor)};
{I}const int64_t expected = {_int64_literal(case.expected)};

{I}REQUIRE(
{II}our::common::FloorMod(dividend, divisor)
{II}== expected
{I});
}}"""
                )
            )

    if intermediate_uses.abs_call(symbol_table):
        for int_argument, int_expected in tests_common.ABS_INT_CASES:
            blocks.append(
                Stripped(
                    f"""\
TEST_CASE("Test std::abs of the 64-bit integer {int_argument}") {{
{I}const int64_t argument = {_int64_literal(int_argument)};
{I}const int64_t expected = {_int64_literal(int_expected)};

{I}REQUIRE(std::abs(argument) == expected);
}}"""
                )
            )

        for float_argument, float_expected in tests_common.ABS_FLOAT_CASES:
            blocks.append(
                Stripped(
                    f"""\
TEST_CASE("Test std::abs of the double {float_argument!r}") {{
{I}const double argument = {_double_literal(float_argument)};
{I}const double expected = {_double_literal(float_expected)};

{I}REQUIRE(std::abs(argument) == expected);
}}"""
                )
            )

    blocks.append(cpp_common.WARNING)

    return "\n\n".join(blocks) + "\n"
