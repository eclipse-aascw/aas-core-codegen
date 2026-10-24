"""Generate the unit tests for the operations on strings."""

import io
import re
from typing import List

from icontract import ensure, require

from aas_core_codegen import string_helper_cases
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
)
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


def _method_name(prefix: str, description: str) -> str:
    """Derive the name of a test method from the ``description`` of a case."""
    return f"test_{prefix}_" + re.sub(r"[^a-z0-9]+", "_", description.lower()).strip(
        "_"
    )


# fmt: off
@require(
    lambda type_inference: intermediate_uses.string_operations(type_inference)
)
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    type_inference: intermediate_type_inference.TypeInference,
) -> str:
    """
    Generate the unit tests for the operations on strings.

    The Python SDK uses the native ``len``, slicing, ``str.find``, comparison
    operators, ``str.lstrip``, ``str.rstrip``, ``str.startswith`` and
    ``str.endswith``, which serve as the reference for the other SDKs. We still
    generate the tests so that the users can inspect the same cases in all
    the SDKs.
    """
    methods: List[Stripped] = []

    if intermediate_uses.string_len_call(type_inference):
        for len_case in string_helper_cases.LEN_CASES:
            name = _method_name("len", len_case.description)
            methods.append(
                Stripped(
                    f"""\
def {name}(self) -> None:
{I}self.assertEqual(
{II}{len_case.expected},
{II}{len_case.python_expression()}
{I})"""
                )
            )

    if intermediate_uses.string_slicing(type_inference):
        for slice_case in string_helper_cases.SLICE_CASES:
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

    if intermediate_uses.string_find_call(type_inference):
        for find_case in string_helper_cases.FIND_CASES:
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

    if intermediate_uses.string_ordering(type_inference):
        for compare_case in string_helper_cases.COMPARE_CASES:
            name = _method_name("compare", compare_case.description)
            left = python_common.string_literal(compare_case.left)
            right = python_common.string_literal(compare_case.right)
            methods.append(
                Stripped(
                    f"""\
def {name}(self) -> None:
{I}self.assertEqual(
{II}{compare_case.expected},
{II}({left} > {right}) - ({left} < {right})
{I})"""
                )
            )

    if intermediate_uses.lstrip_call(type_inference):
        for lstrip_case in string_helper_cases.LSTRIP_CASES:
            name = _method_name("lstrip", lstrip_case.description)
            methods.append(
                Stripped(
                    f"""\
def {name}(self) -> None:
{I}self.assertEqual(
{II}{python_common.string_literal(lstrip_case.expected)},
{II}{python_common.string_literal(lstrip_case.text)}.lstrip(
{III}{python_common.string_literal(lstrip_case.chars)}
{II})
{I})"""
                )
            )

    if intermediate_uses.rstrip_call(type_inference):
        for rstrip_case in string_helper_cases.RSTRIP_CASES:
            name = _method_name("rstrip", rstrip_case.description)
            methods.append(
                Stripped(
                    f"""\
def {name}(self) -> None:
{I}self.assertEqual(
{II}{python_common.string_literal(rstrip_case.expected)},
{II}{python_common.string_literal(rstrip_case.text)}.rstrip(
{III}{python_common.string_literal(rstrip_case.chars)}
{II})
{I})"""
                )
            )

    if intermediate_uses.startswith_call(type_inference):
        for startswith_case in string_helper_cases.STARTSWITH_CASES:
            name = _method_name("startswith", startswith_case.description)
            assertion = "assertTrue" if startswith_case.expected else "assertFalse"
            methods.append(
                Stripped(
                    f"""\
def {name}(self) -> None:
{I}self.{assertion}(
{II}{python_common.string_literal(startswith_case.text)}.startswith(
{III}{python_common.string_literal(startswith_case.prefix)}
{II})
{I})"""
                )
            )

    if intermediate_uses.endswith_call(type_inference):
        for endswith_case in string_helper_cases.ENDSWITH_CASES:
            name = _method_name("endswith", endswith_case.description)
            assertion = "assertTrue" if endswith_case.expected else "assertFalse"
            methods.append(
                Stripped(
                    f"""\
def {name}(self) -> None:
{I}self.{assertion}(
{II}{python_common.string_literal(endswith_case.text)}.endswith(
{III}{python_common.string_literal(endswith_case.suffix)}
{II})
{I})"""
                )
            )

    writer = io.StringIO()
    writer.write(
        """\
class Test_string_helpers(unittest.TestCase):
"""
    )
    for i, method in enumerate(methods):
        if i > 0:
            writer.write("\n\n")

        writer.write(f"{I}{indent_but_first_line(method, I)}")

    blocks: List[Stripped] = [
        Stripped(
            '''\
"""
Test the operations on strings.

The operations follow the Python implementation, since Python is
the language of the meta-model specifications. Hence, they work on
the characters (code points) of the strings. The other SDKs test against
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
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()
