"""Generate the unit tests for the helpers of ``len``, slicing strings and ``find``."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import len_slicing_and_find_cases
from aas_core_codegen.common import Stripped
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(library_namespace: Stripped) -> str:
    """Generate the unit tests for the helpers of ``len``, slicing strings and ``find``."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            """\
/**
 * Test `len`, the slicing of strings and `find` as used in the transpiled code.
 *
 * The transpiled code follows the Python implementation, since Python is
 * the language of the meta-model specifications. Hence, the lengths and
 * the positions count the characters (code points). The expected values have
 * been computed with Python, and all the SDKs test against the very same cases.
 */"""
        ),
        Stripped(f'#include "{include_prefix_path}/common.hpp"'),
        Stripped(
            """\
#define CATCH_CONFIG_MAIN
#include <catch2/catch.hpp>"""
        ),
        Stripped(f"namespace aas = {library_namespace};"),
    ]  # type: List[Stripped]

    for len_case in len_slicing_and_find_cases.LEN_CASES:
        name = cpp_common.string_literal(
            f"{len_case.python_expression()} gives {len_case.expected}: "
            f"{len_case.description}"
        )

        blocks.append(
            Stripped(
                f"""\
TEST_CASE({name}) {{
{I}REQUIRE(
{II}aas::common::LenStr({cpp_common.wstring_literal(len_case.text)})
{II}== {len_case.expected}U
{I});
}}"""
            )
        )

    for slice_case in len_slicing_and_find_cases.SLICE_CASES:
        name = cpp_common.string_literal(
            f"{slice_case.python_expression()} gives {slice_case.expected!r}: "
            f"{slice_case.description}"
        )

        # NOTE (mristin):
        # We call the helper just as the transpiled code does.
        args = [
            cpp_common.wstring_literal(slice_case.text),
            "0" if slice_case.start is None else str(slice_case.start),
        ]
        if slice_case.end is not None:
            args.append(str(slice_case.end))

        blocks.append(
            Stripped(
                f"""\
TEST_CASE({name}) {{
{I}REQUIRE(
{II}aas::common::SliceStr({", ".join(args)})
{II}== {cpp_common.wstring_literal(slice_case.expected)}
{I});
}}"""
            )
        )

    for find_case in len_slicing_and_find_cases.FIND_CASES:
        name = cpp_common.string_literal(
            f"{find_case.python_expression()} gives {find_case.expected}: "
            f"{find_case.description}"
        )

        args = [
            cpp_common.wstring_literal(find_case.text),
            cpp_common.wstring_literal(find_case.sub),
        ]
        if find_case.start is not None:
            args.append(str(find_case.start))

        blocks.append(
            Stripped(
                f"""\
TEST_CASE({name}) {{
{I}REQUIRE(
{II}aas::common::FindStr({", ".join(args)})
{II}== {find_case.expected}
{I});
}}"""
            )
        )

    blocks.append(cpp_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate_implementation.__doc__ is not None
assert generate_implementation.__doc__.strip().startswith(__doc__.strip())
