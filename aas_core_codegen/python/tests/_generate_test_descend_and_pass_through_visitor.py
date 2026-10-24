"""Generate code to test descend and pass-through visitor jointly."""

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
    Generate code to test descend and pass-through visitor jointly.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            f'''\
"""
Test jointly :py:method:`{qualified_module_name}.types.Class.descend` and
:py:method:`{qualified_module_name}.types.PassThroughVisitor`.
"""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped(
            f"""\
from typing import (
{I}List,
{I}Sequence
)
import unittest"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.types as our_types"""
        ),
        Stripped(
            """\
import tests.common
import tests.common_xmlization"""
        ),
        Stripped(
            f'''\
class _TracingVisitor(our_types.PassThroughVisitor):
{I}"""Visit the instances and trace them."""

{I}def __init__(self) -> None:
{II}"""Initialize with an empty log."""
{II}self._log = []  # type: List[str]

{I}@property
{I}def log(self) -> Sequence[str]:
{II}"""Get the tracing log."""
{II}return self._log

{I}def visit(self, that: our_types.Class) -> None:
{II}self._log.append(tests.common.trace(that))
{II}super().visit(that)'''
        ),
        Stripped(
            f'''\
def assert_tracing_logs_from_descend_and_visitor_are_the_same(
{I}that: our_types.Class, test_case: unittest.TestCase
) -> None:
{I}"""
{I}Check that the tracing logs are the same when :paramref:`that` instance
{I}is visited and when :paramref:`that` is ran through
{I}:py:method:`our_types.Class.descend`.

{I}:param that: instance to be iterated over
{I}:param test_case: in which this assertion runs
{I}:raise: :py:class:`AssertionError` if the logs differ
{I}"""
{I}log_from_descend = [tests.common.trace(something) for something in that.descend()]

{I}visitor = _TracingVisitor()
{I}visitor.visit(that)
{I}log_from_visitor = visitor.log

{I}test_case.assertGreater(len(log_from_visitor), 0)
{I}test_case.assertEqual(tests.common.trace(that), log_from_visitor[0])

{I}test_case.assertSequenceEqual(log_from_descend, log_from_visitor[1:])'''
        ),
        Stripped(
            f"""\
class TestWithExpectedMaximal(unittest.TestCase):
{I}def test_descend_against_recorded_trace_log(self) -> None:
{II}xml_expected_dir = tests.common.TEST_DATA_DIR / "Xml" / "Expected"

{II}for path in sorted(xml_expected_dir.glob("**/maximal.xml")):
{III}instance = tests.common_xmlization.must_load(path)

{III}rel_path = path.relative_to(xml_expected_dir)

{III}expected_path = (
{IIII}tests.common.TEST_DATA_DIR
{IIII}/ "descend_and_pass_through_visitor"
{IIII}/ rel_path.parent
{IIII}/ f"{{rel_path.name}}.trace"
{III})

{III}log = [
{IIII}tests.common.trace(something)
{IIII}for something in instance.descend()
{III}]

{III}got_text = tests.common.trace_log_as_text_file_content(log)

{III}tests.common.record_or_check(expected_path, got_text)

{I}def test_descend_against_visitor(self) -> None:
{II}xml_expected_dir = tests.common.TEST_DATA_DIR / "Xml" / "Expected"

{II}for path in sorted(xml_expected_dir.glob("**/maximal.xml")):
{III}instance = tests.common_xmlization.must_load(path)

{III}assert_tracing_logs_from_descend_and_visitor_are_the_same(
{IIII}instance,
{IIII}self
{III})"""
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
