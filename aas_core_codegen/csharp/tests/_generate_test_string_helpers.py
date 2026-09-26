"""Generate the unit tests for the helpers of slicing strings and of ``find``."""

import re
from typing import List

from icontract import ensure

from aas_core_codegen import slicing_and_find_cases
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)


def _method_name(prefix: str, description: str) -> str:
    """Derive the name of a test method from the ``description`` of a case."""
    words = re.split(r"[^a-zA-Z0-9]+", description)
    return f"Test_{prefix}_" + "_".join(word for word in words if word)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(namespace: csharp_common.NamespaceIdentifier) -> str:
    """
    Generate the unit tests for the helpers of slicing strings and of ``find``.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks = []  # type: List[Stripped]

    for slice_case in slicing_and_find_cases.SLICE_CASES:
        description = csharp_common.string_literal(
            f"{slice_case.python_expression()} gives {slice_case.expected!r}: "
            f"{slice_case.description}"
        )

        # NOTE (mristin):
        # We call the helper just as the transpiled code does.
        args = [
            csharp_common.string_literal(slice_case.text),
            "0" if slice_case.start is None else str(slice_case.start),
        ]
        if slice_case.end is not None:
            args.append(str(slice_case.end))

        method_name = _method_name("slice", slice_case.description)

        blocks.append(
            Stripped(
                f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{csharp_common.string_literal(slice_case.expected)},
{II}Aas.Verification.StringHelpers.Slice({", ".join(args)}));
}}  // void {method_name}"""
            )
        )

    for find_case in slicing_and_find_cases.FIND_CASES:
        description = csharp_common.string_literal(
            f"{find_case.python_expression()} gives {find_case.expected}: "
            f"{find_case.description}"
        )

        text = csharp_common.string_literal(find_case.text)
        sub = csharp_common.string_literal(find_case.sub)

        # NOTE (mristin):
        # We call the native ``IndexOf`` or the helper just as the transpiled code
        # does.
        call = (
            f"(long){text}.IndexOf({sub}, System.StringComparison.Ordinal)"
            if find_case.start is None
            else f"Aas.Verification.StringHelpers.Find({text}, {sub}, {find_case.start})"
        )

        method_name = _method_name("find", find_case.description)

        blocks.append(
            Stripped(
                f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{find_case.expected},
{II}{call});
}}  // void {method_name}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Aas = {namespace};  // renamed

using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}/// <summary>
{I}/// Test the slicing of strings and <c>find</c> as used in the transpiled code.
{I}/// </summary>
{I}/// <remarks>
{I}/// The transpiled code follows the Python implementation, since Python is
{I}/// the language of the meta-model specifications. The expected values have
{I}/// been computed with Python.
{I}/// </remarks>
{I}public class TestStringHelpers
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestStringHelpers
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
