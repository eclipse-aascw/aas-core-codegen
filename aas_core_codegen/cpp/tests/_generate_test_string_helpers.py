"""Generate the unit tests for the helpers of the operations on strings."""

import io
from typing import List

from icontract import ensure, require

from aas_core_codegen import string_helper_cases
from aas_core_codegen.common import Stripped
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
)
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


# fmt: off
@require(
    lambda type_inference: intermediate_uses.string_operations(type_inference)
)
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    library_namespace: Stripped,
    type_inference: intermediate_type_inference.TypeInference,
) -> str:
    """Generate the unit tests for the helpers of the operations on strings."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            """\
/**
 * Test the operations on strings.
 *
 * The operations follow the Python implementation, since Python is
 * the language of the meta-model specifications. Hence, they work on
 * the characters (code points) of the strings. The expected values have been
 * computed with Python, and all the SDKs test against the very same cases.
 */"""
        ),
        Stripped(f'#include "{include_prefix_path}/common.hpp"'),
        Stripped(
            """\
#include <catch2/catch.hpp>"""
        ),
        Stripped(f"namespace our = {library_namespace};"),
    ]

    if intermediate_uses.string_len_call(type_inference):
        for len_case in string_helper_cases.LEN_CASES:
            name = cpp_common.string_literal(
                f"{len_case.python_expression()} gives {len_case.expected}: "
                f"{len_case.description}"
            )

            blocks.append(
                Stripped(
                    f"""\
TEST_CASE({name}) {{
{I}REQUIRE(
{II}our::common::LenStr({cpp_common.wstring_literal(len_case.text)})
{II}== {len_case.expected}U
{I});
}}"""
                )
            )

    if intermediate_uses.string_slicing(type_inference):
        for slice_case in string_helper_cases.SLICE_CASES:
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
{II}our::common::SliceStr({", ".join(args)})
{II}== {cpp_common.wstring_literal(slice_case.expected)}
{I});
}}"""
                )
            )

    if intermediate_uses.string_find_call(type_inference):
        for find_case in string_helper_cases.FIND_CASES:
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
{II}our::common::FindStr({", ".join(args)})
{II}== {find_case.expected}
{I});
}}"""
                )
            )

    if intermediate_uses.string_ordering(type_inference):
        for compare_case in string_helper_cases.COMPARE_CASES:
            name = cpp_common.string_literal(
                f"{compare_case.python_expression()} gives {compare_case.expected}: "
                f"{compare_case.description}"
            )

            left = cpp_common.wstring_literal(compare_case.left)
            right = cpp_common.wstring_literal(compare_case.right)

            blocks.append(
                Stripped(
                    f"""\
TEST_CASE({name}) {{
{I}REQUIRE(
{II}our::common::CompareByCodePoints({left}, {right})
{II}== {compare_case.expected}
{I});
}}"""
                )
            )

    if intermediate_uses.lstrip_call(type_inference):
        for lstrip_case in string_helper_cases.LSTRIP_CASES:
            name = cpp_common.string_literal(
                f"{lstrip_case.python_expression()} gives "
                f"{lstrip_case.expected!r}: {lstrip_case.description}"
            )

            blocks.append(
                Stripped(
                    f"""\
TEST_CASE({name}) {{
{I}REQUIRE(
{II}our::common::LStrip(
{III}{cpp_common.wstring_literal(lstrip_case.text)},
{III}{cpp_common.wstring_literal(lstrip_case.chars)}
{II})
{II}== {cpp_common.wstring_literal(lstrip_case.expected)}
{I});
}}"""
                )
            )

    if intermediate_uses.rstrip_call(type_inference):
        for rstrip_case in string_helper_cases.RSTRIP_CASES:
            name = cpp_common.string_literal(
                f"{rstrip_case.python_expression()} gives "
                f"{rstrip_case.expected!r}: {rstrip_case.description}"
            )

            blocks.append(
                Stripped(
                    f"""\
TEST_CASE({name}) {{
{I}REQUIRE(
{II}our::common::RStrip(
{III}{cpp_common.wstring_literal(rstrip_case.text)},
{III}{cpp_common.wstring_literal(rstrip_case.chars)}
{II})
{II}== {cpp_common.wstring_literal(rstrip_case.expected)}
{I});
}}"""
                )
            )

    if intermediate_uses.startswith_call(type_inference):
        for startswith_case in string_helper_cases.STARTSWITH_CASES:
            name = cpp_common.string_literal(
                f"{startswith_case.python_expression()} gives "
                f"{startswith_case.expected!r}: {startswith_case.description}"
            )

            assertion = "REQUIRE" if startswith_case.expected else "REQUIRE_FALSE"

            blocks.append(
                Stripped(
                    f"""\
TEST_CASE({name}) {{
{I}{assertion}(
{II}our::common::StartsWith(
{III}{cpp_common.wstring_literal(startswith_case.text)},
{III}{cpp_common.wstring_literal(startswith_case.prefix)}
{II})
{I});
}}"""
                )
            )

    if intermediate_uses.endswith_call(type_inference):
        for endswith_case in string_helper_cases.ENDSWITH_CASES:
            name = cpp_common.string_literal(
                f"{endswith_case.python_expression()} gives "
                f"{endswith_case.expected!r}: {endswith_case.description}"
            )

            assertion = "REQUIRE" if endswith_case.expected else "REQUIRE_FALSE"

            blocks.append(
                Stripped(
                    f"""\
TEST_CASE({name}) {{
{I}{assertion}(
{II}our::common::EndsWith(
{III}{cpp_common.wstring_literal(endswith_case.text)},
{III}{cpp_common.wstring_literal(endswith_case.suffix)}
{II})
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
