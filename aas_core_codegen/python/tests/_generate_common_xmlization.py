"""Generate code for common XML de/serialization shared across the tests."""

import io

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.python import (
    common as python_common,
)
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
    Generate code for common XML de/serialization shared across the tests.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            '"""Provide common functionality for XML de/serialization in tests."""',
        ),
        python_common.WARNING,
        Stripped(
            """\
import io
import pathlib
import sys
from typing import Iterator, Optional
import xml.etree.ElementTree as ET"""
        ),
        Stripped(
            """\
if sys.version_info >= (3, 8):
    from typing import Final
else:
    from typing_extensions import Final"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.types as our_types
import {qualified_module_name}.xmlization as our_xmlization"""
        ),
        Stripped(
            f'''\
class Difference:
{I}"""Represent a single difference between two XML documents."""

{I}#: Human-readable description of the difference
{I}message: Final[str]

{I}#: Path to the expected XML element which is different from
{I}#: the obtained XML element
{I}path: Final[our_xmlization.Path]

{I}def __init__(self, message: str) -> None:
{II}"""Initialize with the given message and empty path."""
{II}self.message = message
{II}self.path = our_xmlization.Path()

{I}def __str__(self) -> str:
{II}return f"#{{self.path}}: {{self.message}}"'''
        ),
        Stripped(
            f'''\
def remove_redundant_whitespace(element: ET.Element) -> None:
{I}"""
{I}Remove the whitespace which will be ignored in the XML parsing.

{I}:param element: to remove the whitespace from
{I}"""
{I}if len(element) > 0:
{II}if element.text is not None and len(element.text.strip()) == 0:
{III}element.text = None

{II}for child in element:
{III}if child.tail is not None and len(child.tail.strip()) == 0:
{IIII}child.tail = None

{III}remove_redundant_whitespace(child)'''
        ),
        Stripped(
            f'''\
def check_equal(
{I}expected: ET.Element,
{I}got: ET.Element,
) -> Iterator[Difference]:
{I}"""
{I}Compare recursively two XML elements for equality.

{I}Make sure you called :py:function:`.remove_redundant_whitespace`
{I}so that your comparison does not trip over trivial whitespace.

{I}:param expected: expected XML element
{I}:param got: obtained XML element
{I}:yield: differences
{I}"""
{I}# NOTE (mristin):
{I}# We need to ignore the white-space before the children as it is ignored
{I}# by the XML parser.

{I}stop_recursion = False
{I}if expected.text is not None and got.text is None:
{II}stop_recursion = True
{II}yield Difference(f"Expected text {{expected.text!r}}, but got none")

{I}if expected.text is None and got.text is not None:
{II}stop_recursion = True
{II}yield Difference(f"Expected no text, but got {{got.text!r}}")

{I}if expected.tail is not None and got.tail is None:
{II}stop_recursion = True
{II}yield Difference(f"Expected tail {{expected.tail!r}}, but got none")

{I}if expected.tail is None and got.tail is not None:
{II}stop_recursion = True
{II}yield Difference(f"Expected no tail, but got {{got.tail!r}}")

{I}if expected.text is not None and got.text is not None and expected.text != got.text:
{II}stop_recursion = True
{II}yield Difference(f"Expected text {{expected.text!r}}, but got {{got.text!r}}")

{I}if expected.tail is not None and got.tail is not None and expected.tail != got.tail:
{II}stop_recursion = True
{II}yield Difference(f"Expected tail {{expected.tail!r}}, but got {{got.tail!r}}")

{I}if expected.tag != got.tag:
{II}stop_recursion = True
{II}yield Difference(f"Expected tail {{expected.tag!r}}, but got {{got.tag!r}}")

{I}expected_children = list(expected)
{I}got_children = list(got)

{I}if len(expected_children) != len(got_children):
{II}stop_recursion = True
{II}yield Difference(
{III}f"Expected {{len(expected_children)}} child element(s), "
{III}f"but got {{len(got_children)}} child element(s)"
{II})

{I}children_tag_unique = len({{child.tag for child in expected_children}}) == len(
{II}expected_children
{I})

{I}if stop_recursion:
{II}return

{I}for i, (expected_child, got_child) in enumerate(
{II}zip(expected_children, got_children)
{I}):
{II}for difference in check_equal(expected_child, got_child):
{III}if children_tag_unique:
{IIII}difference.path._prepend(our_xmlization.ElementSegment(expected_child))
{III}else:
{IIII}difference.path._prepend(our_xmlization.IndexSegment(expected_child, i))

{III}yield difference'''
        ),
        Stripped(
            f'''\
def assert_elements_equal(
{I}expected: ET.Element, got: ET.Element, message_if_not_equal: Optional[str] = None
) -> None:
{I}"""
{I}Assert that the two elements are equal.

{I}Make sure you called :py:function:`.remove_redundant_whitespace`
{I}so that your comparison does not trip over trivial whitespace.

{I}:param expected: what you expected
{I}:param got: what you got
{I}:param message_if_not_equal: description or identifier to help debugging
{I}:raise: :py:class:`AssertionError` if the two elements are not equal
{I}"""
{I}findings_text = "\\n".join(
{II}str(difference) for difference in check_equal(expected=expected, got=got)
{I})

{I}if len(findings_text) != 0:
{II}writer = io.StringIO()
{II}writer.write(
{III}f"Expected two elements to be equal, but they are not. "
{III}f"Differences related to the expected element:\\n"
{III}f"{{findings_text}}"
{II})

{II}if message_if_not_equal is not None:
{III}writer.write("\\n\\n")
{III}writer.write(message_if_not_equal)

{II}raise AssertionError(writer.getvalue())'''
        ),
        Stripped(
            f'''\
def must_load(
{I}path: pathlib.Path,
) -> our_types.Class:
{I}"""Load an instance from ``path``."""
{I}try:
{II}instance = our_xmlization.from_file(path)
{I}except Exception as exception:
{II}raise RuntimeError(f"Failed to read from {{path}}") from exception

{I}return instance'''
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
