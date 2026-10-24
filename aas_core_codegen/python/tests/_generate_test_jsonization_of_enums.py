"""Generate code to test the JSON de/serialization of enumerations."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.python import common as python_common, naming as python_naming
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
)


def _generate_test_case(symbol_table: intermediate.SymbolTable) -> Stripped:
    test_methods: List[Stripped] = []

    for enumeration in symbol_table.enumerations:
        test_method_name = python_naming.method_name(
            Identifier(f"test_{enumeration.name}")
        )

        from_jsonable = python_naming.function_name(
            Identifier(f"{enumeration.name}_from_jsonable")
        )

        literals_joined = ",\n".join(
            repr(literal.value) for literal in enumeration.literals
        )

        test_methods.append(
            Stripped(
                f"""\
def {test_method_name}(self) -> None:
{I}for jsonable in [
{II}{indent_but_first_line(literals_joined, II)}
{I}]:
{II}enum_literal = our_jsonization.{from_jsonable}(jsonable)

{II}self.assertEqual(enum_literal.value, jsonable)"""
            ),
        )

    body = "\n\n".join(test_methods) if len(test_methods) > 0 else "pass"

    return Stripped(
        f"""\
class TestRoundTrips(unittest.TestCase):
{I}{indent_but_first_line(body, I)}"""
    )


@ensure(
    lambda result: result.endswith("\n"),
    "Trailing newline mandatory for valid end-of-files",
)
def generate(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> str:
    """
    Generate code to test the JSON de/serialization of enumerations.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            '''\
"""Test JSON de/serialization of enumerations."""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped(
            """\
import unittest"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.jsonization as our_jsonization"""
        ),
        _generate_test_case(symbol_table=symbol_table),
        Stripped(
            f"""\
if __name__ == "__main__":
{I}unittest.main()"""
        ),
        python_common.WARNING,
    ]

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue()
