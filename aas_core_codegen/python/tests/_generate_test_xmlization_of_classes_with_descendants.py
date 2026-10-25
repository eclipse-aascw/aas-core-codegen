"""Generate code to test XML de/serialization of classes with descendants."""

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

        test_method_name = python_naming.method_name(Identifier(f"test_{cls.name}"))

        from_iterparse = python_naming.function_name(
            Identifier(f"{cls.name}_from_iterparse")
        )

        from_stream = python_naming.function_name(Identifier(f"{cls.name}_from_stream"))

        from_file = python_naming.function_name(Identifier(f"{cls.name}_from_file"))

        from_str = python_naming.function_name(Identifier(f"{cls.name}_from_str"))

        xml_class_names_of_descendants = ",\n".join(
            sorted(
                repr(naming.xml_class_name(concrete_cls.name))
                for concrete_cls in cls.concrete_descendants
            )
        )

        test_methods.append(
            Stripped(
                f"""\
def {test_method_name}(self) -> None:
{I}for xml_class_name_of_descendant in [
{II}{indent_but_first_line(xml_class_names_of_descendants, II)}
{I}]:
{II}for path in sorted(
{III}(
{IIII}tests.common.TEST_DATA_DIR
{IIII}/ "Xml"
{IIII}/ "Expected"
{IIII}/ xml_class_name_of_descendant
{III}).glob("**/*.xml")
{II}):
{III}text = path.read_text(encoding="utf-8")
{III}et_concrete = ET.fromstring(text)
{III}tests.common_xmlization.remove_redundant_whitespace(et_concrete)

{III}# region From iterparse
{III}iterator = ET.iterparse(source=io.StringIO(text), events=["start", "end"])
{III}got_from_iterparse = our_xmlization.{from_iterparse}(iterator)

{III}et_from_iterparse = ET.fromstring(our_xmlization.to_str(got_from_iterparse))
{III}tests.common_xmlization.remove_redundant_whitespace(et_from_iterparse)
{III}tests.common_xmlization.assert_elements_equal(et_concrete, et_from_iterparse)
{III}# endregion

{III}# region From stream
{III}got_from_stream = our_xmlization.{from_stream}(io.StringIO(text))
{III}et_from_stream = ET.fromstring(our_xmlization.to_str(got_from_stream))
{III}tests.common_xmlization.remove_redundant_whitespace(et_from_stream)
{III}tests.common_xmlization.assert_elements_equal(et_concrete, et_from_stream)
{III}# endregion

{III}# region From file
{III}with tempfile.TemporaryDirectory() as tmp_dir:
{IIII}tmp_path = pathlib.Path(tmp_dir) / "something.xml"
{IIII}tmp_path.write_text(text, encoding="utf-8")

{IIII}got_from_file = our_xmlization.{from_file}(tmp_path)
{III}et_from_file = ET.fromstring(our_xmlization.to_str(got_from_file))
{III}tests.common_xmlization.remove_redundant_whitespace(et_from_file)
{III}tests.common_xmlization.assert_elements_equal(et_concrete, et_from_file)
{III}# endregion

{III}# region From string
{III}got_from_str = our_xmlization.{from_str}(text)
{III}et_from_str = ET.fromstring(our_xmlization.to_str(got_from_str))
{III}tests.common_xmlization.remove_redundant_whitespace(et_from_str)
{III}tests.common_xmlization.assert_elements_equal(et_concrete, et_from_str)
{III}# endregion"""
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
    Generate code to test XML de/serialization of classes with descendants.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            '''\
"""Test XML de/serialization of classes with descendants."""'''
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
import io
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET"""
                ),
                Stripped(
                    f"""\
import {qualified_module_name}.xmlization as our_xmlization"""
                ),
                Stripped(
                    """\
import tests.common
import tests.common_xmlization"""
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
