"""Generate the unit tests for the helpers of ``len``, slicing strings and ``find``."""

import re
from typing import List

from icontract import ensure

from aas_core_codegen import len_slicing_and_find_cases
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
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
    Generate the unit tests for the helpers of ``len``, slicing strings and ``find``.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks = []  # type: List[Stripped]

    for len_case in len_slicing_and_find_cases.LEN_CASES:
        description = csharp_common.string_literal(
            f"{len_case.python_expression()} gives {len_case.expected}: "
            f"{len_case.description}"
        )

        method_name = _method_name("len", len_case.description)

        blocks.append(
            Stripped(
                f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{len_case.expected},
{II}Aas.Verification.StringHelpers.Len(
{III}{csharp_common.string_literal(len_case.text)}));
}}  // void {method_name}"""
            )
        )

    for slice_case in len_slicing_and_find_cases.SLICE_CASES:
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

    for find_case in len_slicing_and_find_cases.FIND_CASES:
        description = csharp_common.string_literal(
            f"{find_case.python_expression()} gives {find_case.expected}: "
            f"{find_case.description}"
        )

        text = csharp_common.string_literal(find_case.text)
        sub = csharp_common.string_literal(find_case.sub)

        # NOTE (mristin):
        # We call the helper just as the transpiled code does.
        args = [text, sub]
        if find_case.start is not None:
            args.append(str(find_case.start))

        call = f"Aas.Verification.StringHelpers.Find({', '.join(args)})"

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
{I}/// Test <c>len</c>, the slicing of strings and <c>find</c> as used in
{I}/// the transpiled code.
{I}/// </summary>
{I}/// <remarks>
{I}/// The transpiled code follows the Python implementation, since Python is
{I}/// the language of the meta-model specifications. Hence, the lengths and
{I}/// the positions count the characters (code points). The expected values have
{I}/// been computed with Python, and all the SDKs test against the very same
{I}/// cases.
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
