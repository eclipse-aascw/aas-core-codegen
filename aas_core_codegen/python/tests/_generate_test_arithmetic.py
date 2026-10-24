"""Generate code to test the arithmetic operations used in the verification."""

from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate, tests_common
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
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
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """
    Generate code to test the arithmetic operations used in the verification.

    The meta-model is written in Python, so the invariants follow the Python semantics
    of the modulo and ``abs``, and Python SDK uses the native operators. We still
    generate the tests so that the clients can look up the behavior, and compare it
    against the other SDKs, see :py:mod:`aas_core_codegen.tests_common`.
    """
    methods: List[Stripped] = []

    if intermediate_uses.modulo(symbol_table):
        for i, case in enumerate(tests_common.FLOOR_MOD_CASES):
            methods.append(
                Stripped(
                    f"""\
def test_modulo_{i}(self) -> None:
{I}# {case.explanation}
{I}self.assertEqual({case.expected}, {case.dividend} % {case.divisor})"""
                )
            )

    if intermediate_uses.abs_call(symbol_table):
        for i, (int_argument, int_expected) in enumerate(tests_common.ABS_INT_CASES):
            methods.append(
                Stripped(
                    f"""\
def test_abs_of_int_{i}(self) -> None:
{I}self.assertEqual({int_expected}, abs({int_argument}))"""
                )
            )

        for i, (float_argument, float_expected) in enumerate(
            tests_common.ABS_FLOAT_CASES
        ):
            methods.append(
                Stripped(
                    f"""\
def test_abs_of_float_{i}(self) -> None:
{I}self.assertEqual({float_expected!r}, abs({float_argument!r}))"""
                )
            )

    methods_joined = "\n\n".join(methods)

    blocks = [
        Stripped(
            '''\
"""
Test the arithmetic operations used in the verification.

The meta-model is written in Python, so the invariants follow the Python semantics
of the modulo and ``abs``. In particular, the remainder of the modulo takes
the sign of the divisor (``-7 % 3 == 2``). Mind that the native modulo in many
other languages, such as C#, C++, Go, Java and TypeScript, takes the sign of
the dividend instead (``-7 % 3 == -1``). Hence, the other SDKs follow the Python
semantics with dedicated helper functions, and test the very same cases.
"""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped("import unittest"),
        Stripped(
            f"""\
class TestArithmetic(unittest.TestCase):
{I}{indent_but_first_line(methods_joined, I)}"""
        ),
        Stripped(
            f"""\
if __name__ == "__main__":
{I}unittest.main()"""
        ),
        python_common.WARNING,
    ]

    return "\n\n\n".join(blocks) + "\n"


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
