"""Generate code to test the arithmetic helpers used in the transpiled code."""

import io
from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate, tests_common
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.golang import (
    common as golang_common,
    transpilation as golang_transpilation,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)
from aas_core_codegen.intermediate import uses as intermediate_uses


def _int64_literal(value: int) -> str:
    """Render the 64-bit signed integer as a Go expression."""
    if value == tests_common.INT64_MIN:
        return "math.MinInt64"

    if value == tests_common.INT64_MAX:
        return "math.MaxInt64"

    if value == -tests_common.INT64_MAX:
        return "-math.MaxInt64"

    return str(value)


def _float64_literal(value: float) -> str:
    """Render the floating-point number as a Go expression."""
    if value == 0.0 and str(value).startswith("-"):
        # NOTE (mristin):
        # The constant expression ``-0.0`` is a positive zero in Go, since
        # the constants are exact. We need to compute the negative zero at run time.
        return "math.Copysign(0, -1)"

    return repr(value)


def _generate_test_floor_mod() -> Stripped:
    """Generate the table-driven test of the modulo."""
    case_blocks: List[str] = []
    for case in tests_common.FLOOR_MOD_CASES:
        case_blocks.append(
            f"""\
// {case.explanation}
{{{_int64_literal(case.dividend)}, {_int64_literal(case.divisor)}, \
{_int64_literal(case.expected)}}},"""
        )

    cases_joined = "\n".join(case_blocks)

    function_name = golang_transpilation.FLOOR_MOD_FUNCTION_NAME

    return Stripped(
        f"""\
// Test that the modulo follows the Python semantics, *i.e.*, the remainder takes
// the sign of the divisor.
func Test{function_name}(t *testing.T) {{
{I}cases := []struct {{
{II}dividend int64
{II}divisor  int64
{II}expected int64
{I}}}{{
{II}{indent_but_first_line(cases_joined, II)}
{I}}}

{I}for _, c := range cases {{
{II}got := ourcommon.{function_name}(c.dividend, c.divisor)
{II}if got != c.expected {{
{III}t.Errorf(
{IIII}"Expected {function_name}(%d, %d) to be %d, but got %d",
{IIII}c.dividend, c.divisor, c.expected, got,
{III})
{II}}}
{I}}}
}}"""
    )


def _generate_test_abs_int64() -> Stripped:
    """Generate the table-driven test of the absolute value of integers."""
    case_blocks: List[str] = []
    for argument, expected in tests_common.ABS_INT_CASES:
        case_blocks.append(
            f"{{{_int64_literal(argument)}, {_int64_literal(expected)}}},"
        )

    cases_joined = "\n".join(case_blocks)

    function_name = golang_transpilation.ABS_INT64_FUNCTION_NAME

    return Stripped(
        f"""\
// Test the absolute value of 64-bit integers.
//
// Mind that the absolute value of the smallest 64-bit integer overflows,
// so we do not test it.
func Test{function_name}(t *testing.T) {{
{I}cases := []struct {{
{II}argument int64
{II}expected int64
{I}}}{{
{II}{indent_but_first_line(cases_joined, II)}
{I}}}

{I}for _, c := range cases {{
{II}got := ourcommon.{function_name}(c.argument)
{II}if got != c.expected {{
{III}t.Errorf(
{IIII}"Expected {function_name}(%d) to be %d, but got %d",
{IIII}c.argument, c.expected, got,
{III})
{II}}}
{I}}}
}}"""
    )


def _generate_test_abs_float64() -> Stripped:
    """Generate the table-driven test of the absolute value of floating-point numbers."""
    case_blocks: List[str] = []
    for argument, expected in tests_common.ABS_FLOAT_CASES:
        case_blocks.append(
            f"{{{_float64_literal(argument)}, {_float64_literal(expected)}}},"
        )

    cases_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
// Test the absolute value of floating-point numbers, for which we use
// the standard library.
func TestAbsFloat64(t *testing.T) {{
{I}cases := []struct {{
{II}argument float64
{II}expected float64
{I}}}{{
{II}{indent_but_first_line(cases_joined, II)}
{I}}}

{I}for _, c := range cases {{
{II}got := math.Abs(c.argument)
{II}if got != c.expected {{
{III}t.Errorf(
{IIII}"Expected math.Abs(%v) to be %v, but got %v",
{IIII}c.argument, c.expected, got,
{III})
{II}}}
{I}}}
}}"""
    )


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
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """
    Generate code to test the arithmetic helpers used in the transpiled code.

    The meta-model is written in Python, so the invariants follow the Python semantics
    of the modulo and ``abs``. These tests document how the generated code behaves,
    and make sure it matches the Python semantics, see
    :py:mod:`aas_core_codegen.tests_common`.
    """
    test_blocks: List[Stripped] = []

    if intermediate_uses.modulo(symbol_table):
        test_blocks.append(_generate_test_floor_mod())

    if intermediate_uses.abs_call(symbol_table):
        test_blocks.append(_generate_test_abs_int64())
        test_blocks.append(_generate_test_abs_float64())

    import_lines: List[str] = []
    if golang_common.names_package(test_blocks, "math"):
        import_lines.append(f'{I}"math"')

    import_lines.append(f'{I}"testing"')
    import_lines.append(f'{I}ourcommon "{repo_url}/common"')

    import_lines_joined = "\n".join(import_lines)

    # NOTE (mristin):
    # We explain the semantics in a detached comment instead of the package
    # documentation to keep the package clause at the top as in the other tests.
    blocks: List[Stripped] = [
        Stripped("package common_arithmetic_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{import_lines_joined}
)"""
        ),
        Stripped(
            f"""\
// The meta-model is written in Python, so the invariants follow the Python
// semantics of the arithmetic operations. In particular, the remainder of
// the modulo takes the sign of the divisor in Python (`-7 % 3 == 2`), while
// the native Go operator `%` gives the remainder with the sign of the dividend
// (`-7 % 3 == -1`). Therefore, we transpile the modulo to
// ourcommon.{golang_transpilation.FLOOR_MOD_FUNCTION_NAME} instead of the native operator.
//
// The tests in this file document how the generated code behaves, and make sure
// that it matches the Python semantics."""
        ),
        *test_blocks,
        golang_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
