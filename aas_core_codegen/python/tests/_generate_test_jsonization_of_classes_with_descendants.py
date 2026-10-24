"""Generate code to test JSON de/serialization of classes with descendants."""

import io
from typing import List, Optional

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.python import common as python_common, naming as python_naming
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_test_case(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Stripped]:
    """Generate the test case, or return None if there is nothing to test."""
    test_methods: List[Stripped] = []

    for cls in symbol_table.classes:
        if len(cls.concrete_descendants) == 0:
            continue

        # NOTE (mristin):
        # We can not round-trip instances of classes in JSON which do not store
        # model type.
        if not cls.serialization.with_model_type:
            continue

        test_method_name = python_naming.method_name(Identifier(f"test_{cls.name}"))

        from_jsonable = python_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        descendant_model_types = ",\n".join(
            sorted(
                repr(naming.json_model_type(concrete_cls.name))
                for concrete_cls in cls.concrete_descendants
            )
        )

        test_methods.append(
            Stripped(
                f"""\
def {test_method_name}(self) -> None:
{I}for descendant_model_type in [
{II}{indent_but_first_line(descendant_model_types, II)}
{I}]:
{II}for path in sorted(
{III}(
{IIII}tests.common.TEST_DATA_DIR
{IIII}/ "Json"
{IIII}/ "Expected"
{IIII}/ descendant_model_type
{III}).glob("**/*.json")
{II}):
{III}with path.open("rt") as fid:
{IIII}original_jsonable = json.load(fid)

{III}instance = our_jsonization.{from_jsonable}(
{IIII}original_jsonable
{III})

{III}another_jsonable = our_jsonization.to_jsonable(instance)

{III}mismatch = tests.common_jsonization.check_equal(
{IIII}original_jsonable,
{IIII}another_jsonable
{III})

{III}self.assertListEqual([], list(map(str, mismatch)))"""
            ),
        )

    if len(test_methods) == 0:
        return None

    body = "\n\n".join(test_methods)

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
    Generate code to test JSON de/serialization of classes with descendants.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            '''\
"""Test JSON de/serialization of classes with descendants."""'''
        ),
        python_common.WARNING,
    ]

    # NOTE (mristin):
    # We import the modules only if there is anything to test so that
    # the imports are never unused.
    test_case = _generate_test_case(symbol_table=symbol_table)
    if test_case is None:
        blocks.extend(
            [
                Stripped("import unittest"),
                Stripped(
                    f"""\
class TestRoundTrips(unittest.TestCase):
{I}# There are no classes with concrete descendants.
{I}pass"""
                ),
            ]
        )
    else:
        blocks.extend(
            [
                Stripped(
                    """\
import json
import unittest"""
                ),
                Stripped(
                    f"""\
import {qualified_module_name}.jsonization as our_jsonization"""
                ),
                Stripped(
                    """\
import tests.common
import tests.common_jsonization"""
                ),
                test_case,
            ]
        )

    blocks.extend(
        [
            Stripped(
                f"""\
if __name__ == "__main__":
{I}unittest.main()"""
            ),
            python_common.WARNING,
        ]
    )

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue()
