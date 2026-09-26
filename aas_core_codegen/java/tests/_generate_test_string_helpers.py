"""Generate the unit tests for the helpers of slicing strings and of ``find``."""

import re
from typing import List

from aas_core_codegen import slicing_and_find_cases
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common
from aas_core_codegen.java.common import INDENT as I, INDENT2 as II


def _method_name(prefix: str, description: str) -> str:
    """Derive the name of a test method from the ``description`` of a case."""
    words = re.split(r"[^a-zA-Z0-9]+", description)
    return f"test{prefix}" + "".join(word.capitalize() for word in words if word)


def generate(package: java_common.PackageIdentifier) -> List[java_common.JavaFile]:
    """Generate the unit tests for the helpers of slicing strings and of ``find``."""
    blocks = []  # type: List[Stripped]

    for slice_case in slicing_and_find_cases.SLICE_CASES:
        display_name = java_common.string_literal(
            f"{slice_case.python_expression()} gives {slice_case.expected!r}: "
            f"{slice_case.description}"
        )

        # NOTE (mristin):
        # We call the helper just as the transpiled code does.
        args = [
            java_common.string_literal(slice_case.text),
            "0" if slice_case.start is None else str(slice_case.start),
        ]
        if slice_case.end is not None:
            args.append(str(slice_case.end))

        blocks.append(
            Stripped(
                f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Slice", slice_case.description)}() {{
{I}assertEquals(
{II}{java_common.string_literal(slice_case.expected)},
{II}StringHelpers.slice({", ".join(args)}));
}}"""
            )
        )

    for find_case in slicing_and_find_cases.FIND_CASES:
        display_name = java_common.string_literal(
            f"{find_case.python_expression()} gives {find_case.expected}: "
            f"{find_case.description}"
        )

        text = java_common.string_literal(find_case.text)
        sub = java_common.string_literal(find_case.sub)

        # NOTE (mristin):
        # We call the native ``indexOf`` or the helper just as the transpiled code
        # does.
        call = (
            f"{text}.indexOf({sub})"
            if find_case.start is None
            else f"StringHelpers.find({text}, {sub}, {find_case.start})"
        )

        blocks.append(
            Stripped(
                f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Find", find_case.description)}() {{
{I}assertEquals({find_case.expected}, {call});
}}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestStringHelpers.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.common.StringHelpers;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Test the slicing of strings and {{@code find}} as used in the transpiled code.
 *
 * <p>The transpiled code follows the Python implementation, since Python is
 * the language of the meta-model specifications. The expected values have been
 * computed with Python.
 */
public class TestStringHelpers {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestStringHelpers

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
