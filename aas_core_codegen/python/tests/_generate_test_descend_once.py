"""Generate code to test ``descend_once`` methods."""

import io

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


@ensure(
    lambda result: result.endswith("\n"),
    "Trailing newline mandatory for valid end-of-files",
)
def generate(qualified_module_name: python_common.QualifiedModuleName) -> str:
    """
    Generate code to unit test ``descend_once`` methods..

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            f'''\
"""Test :py:method:`{qualified_module_name}.types.Class.descend_once`."""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
import unittest"""
        ),
        Stripped(
            """\
import tests.common
import tests.common_xmlization"""
        ),
        Stripped(
            f"""\
class TestWithExpectedMaximal(unittest.TestCase):
{I}def test_descend_once_against_recorded_trace_log(self) -> None:
{II}xml_expected_dir = tests.common.TEST_DATA_DIR / "Xml" / "Expected"

{II}for path in sorted(xml_expected_dir.glob("**/maximal.xml")):
{III}instance = tests.common_xmlization.must_load(path)

{III}rel_path = path.relative_to(xml_expected_dir)

{III}expected_path = (
{IIII}tests.common.TEST_DATA_DIR
{IIII}/ "descend_once"
{IIII}/ rel_path.parent
{IIII}/ f"{{rel_path.name}}.trace"
{III})

{III}log = [
{IIII}tests.common.trace(something)
{IIII}for something in instance.descend_once()
{III}]

{III}got_text = tests.common.trace_log_as_text_file_content(log)

{III}tests.common.record_or_check(expected_path, got_text)"""
        ),
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
