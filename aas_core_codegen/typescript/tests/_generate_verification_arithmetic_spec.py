"""Generate code to test the arithmetic operations used in the verification."""

import io
from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate, tests_common
from aas_core_codegen.common import Stripped
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.typescript import common as typescript_common
from aas_core_codegen.typescript.common import INDENT as I


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
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """
    Generate code to test the arithmetic operations used in the verification.

    The meta-model is written in Python, so the invariants follow the Python semantics
    of the modulo and ``abs``. These tests document how the generated code behaves,
    and make sure it matches the Python semantics, see
    :py:mod:`aas_core_codegen.tests_common`.

    The numbers in TypeScript are double-precision floating-point numbers, so that
    the integers are exact only up to ``Number.MAX_SAFE_INTEGER``. Hence, we skip
    the cases with the extreme 64-bit integers which can not be exactly represented.
    """
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test the arithmetic operations used in the verification.
 *
 * @remarks
 *
 * The meta-model is written in Python, so the invariants follow the Python
 * semantics. In particular, the remainder of the modulo takes the sign of
 * the divisor in Python (`-7 % 3 == 2`), while the native TypeScript operator
 * `%` gives the remainder with the sign of the dividend (`-7 % 3 === -1`).
 * Therefore, we transpile the modulo to `OurCommon.floorMod` instead of
 * the native operator.
 *
 * The numbers in TypeScript are double-precision floating-point numbers, so
 * the integers are exact only up to `Number.MAX_SAFE_INTEGER`. Hence, we skip
 * the test cases with the extreme 64-bit integers.
 */"""
        ),
        typescript_common.WARNING,
    ]

    if intermediate_uses.modulo(symbol_table):
        blocks.append(Stripped('import * as OurCommon from "../src/common";'))

        blocks.append(
            Stripped(
                """\
// NOTE (mristin):
// We compare the results with `toBe`, which uses `Object.is`, so that we also
// make sure that `floorMod` never returns a negative zero."""
            )
        )

        for case in tests_common.FLOOR_MOD_CASES:
            # NOTE (mristin):
            # We skip the cases which can not be exactly represented as doubles,
            # since the integers are represented as double-precision
            # floating-point numbers in TypeScript.
            if not case.is_safe_integer():
                continue

            dividend = typescript_common.numeric_literal(case.dividend)
            divisor = typescript_common.numeric_literal(case.divisor)
            expected = typescript_common.numeric_literal(case.expected)

            title = typescript_common.string_literal(
                f"floorMod({dividend}, {divisor}) is {expected}: {case.explanation}"
            )

            blocks.append(
                Stripped(
                    f"""\
test({title}, () => {{
{I}expect(OurCommon.floorMod({dividend}, {divisor})).toBe({expected});
}});"""
                )
            )

    if intermediate_uses.abs_call(symbol_table):
        for int_argument, int_expected in tests_common.ABS_INT_CASES:
            # NOTE (mristin):
            # We skip the cases which can not be exactly represented as doubles,
            # since the integers are represented as double-precision
            # floating-point numbers in TypeScript.
            if (
                abs(int_argument) > tests_common.MAX_SAFE_INTEGER
                or abs(int_expected) > tests_common.MAX_SAFE_INTEGER
            ):
                continue

            argument = typescript_common.numeric_literal(int_argument)
            expected = typescript_common.numeric_literal(int_expected)

            title = typescript_common.string_literal(
                f"Math.abs({argument}) is {expected} for an integer"
            )

            blocks.append(
                Stripped(
                    f"""\
test({title}, () => {{
{I}expect(Math.abs({argument})).toBe({expected});
}});"""
                )
            )

        for float_argument, float_expected in tests_common.ABS_FLOAT_CASES:
            argument = typescript_common.numeric_literal(float_argument)
            expected = typescript_common.numeric_literal(float_expected)

            title = typescript_common.string_literal(
                f"Math.abs({argument}) is {expected} for a floating-point number"
            )

            # NOTE (mristin):
            # The ``toBe`` uses ``Object.is``, which distinguishes ``-0`` from ``0``.
            # This is what we want, as ``Math.abs(-0)`` gives ``0`` in TypeScript
            # just as ``abs(-0.0)`` gives ``0.0`` in Python.
            blocks.append(
                Stripped(
                    f"""\
test({title}, () => {{
{I}expect(Math.abs({argument})).toBe({expected});
}});"""
                )
            )

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
