"""Generate the unit tests for slicing strings and for ``find``."""

import io
import re
from typing import List

from icontract import ensure

from aas_core_codegen import slicing_and_find_cases
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
)


def _method_name(prefix: str, description: str) -> str:
    """Derive the name of a test method from the ``description`` of a case."""
    return f"test_{prefix}_" + re.sub(r"[^a-z0-9]+", "_", description.lower()).strip(
        "_"
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate() -> str:
    """
    Generate the unit tests for slicing strings and for ``find``.

    The Python SDK uses the native slicing and ``str.find``, which serve as
    the reference for the other SDKs. We still generate the tests so that
    the users can inspect the same cases in all the SDKs.
    """
    methods = []  # type: List[Stripped]

    for slice_case in slicing_and_find_cases.SLICE_CASES:
        name = _method_name("slice", slice_case.description)
        methods.append(
            Stripped(
                f"""\
def {name}(self) -> None:
{I}self.assertEqual(
{II}{python_common.string_literal(slice_case.expected)},
{II}{slice_case.python_expression()}
{I})"""
            )
        )

    for find_case in slicing_and_find_cases.FIND_CASES:
        name = _method_name("find", find_case.description)
        methods.append(
            Stripped(
                f"""\
def {name}(self) -> None:
{I}self.assertEqual(
{II}{find_case.expected},
{II}{find_case.python_expression()}
{I})"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
class Test_slicing_and_find(unittest.TestCase):
"""
    )
    for i, method in enumerate(methods):
        if i > 0:
            writer.write("\n\n")

        writer.write(f"{I}{indent_but_first_line(method, I)}")

    blocks = [
        Stripped(
            '''\
"""
Test the slicing of strings and ``find`` as used in the transpiled code.

The transpiled code follows the Python implementation, since Python is
the language of the meta-model specifications. The other SDKs test against
the very same cases.
"""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped("import unittest"),
        Stripped(writer.getvalue()),
        Stripped(
            """\
if __name__ == "__main__":
    unittest.main()"""
        ),
        python_common.WARNING,
    ]  # type: List[Stripped]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()
