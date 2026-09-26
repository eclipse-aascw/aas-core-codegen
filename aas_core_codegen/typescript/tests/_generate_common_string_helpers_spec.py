"""Generate the unit tests for the helpers of ``len``, slicing strings and ``find``."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import len_slicing_and_find_cases
from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import common as typescript_common
from aas_core_codegen.typescript.common import INDENT as I


def _generate_len_test(case: len_slicing_and_find_cases.LenCase) -> Stripped:
    """Generate the test of a single ``len`` ``case``."""
    name = typescript_common.string_literal(
        f"{case.python_expression()} gives {case.expected}: {case.description}"
    )

    text = typescript_common.string_literal(case.text)

    return Stripped(
        f"""\
test({name}, () => {{
{I}expect(AasCommon.lenStr({text})).toStrictEqual({case.expected});
}});"""
    )


def _generate_slice_test(case: len_slicing_and_find_cases.SliceCase) -> Stripped:
    """Generate the test of a single slicing ``case``."""
    name = typescript_common.string_literal(
        f"{case.python_expression()} gives {case.expected!r}: {case.description}"
    )

    # NOTE (mristin):
    # We call the helper just as the transpiled code does.
    args = [
        typescript_common.string_literal(case.text),
        "0" if case.start is None else str(case.start),
    ]
    if case.end is not None:
        args.append(str(case.end))

    expected = typescript_common.string_literal(case.expected)

    return Stripped(
        f"""\
test({name}, () => {{
{I}expect(AasCommon.sliceStr({", ".join(args)})).toStrictEqual({expected});
}});"""
    )


def _generate_find_test(case: len_slicing_and_find_cases.FindCase) -> Stripped:
    """Generate the test of a single ``find`` ``case``."""
    name = typescript_common.string_literal(
        f"{case.python_expression()} gives {case.expected}: {case.description}"
    )

    text = typescript_common.string_literal(case.text)
    sub = typescript_common.string_literal(case.sub)

    # NOTE (mristin):
    # We call the helper just as the transpiled code does.
    args = [text, sub]  # type: List[str]
    if case.start is not None:
        args.append(str(case.start))

    call = f"AasCommon.findStr({', '.join(args)})"

    return Stripped(
        f"""\
test({name}, () => {{
{I}expect({call}).toStrictEqual({case.expected});
}});"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate() -> str:
    """Generate the unit tests for the helpers of ``len``, slicing strings and ``find``."""
    blocks = [
        Stripped(
            """\
/**
 * Test `len`, the slicing of strings and `find` as used in the transpiled code.
 *
 * @remarks
 * The transpiled code follows the Python implementation, since Python is
 * the language of the meta-model specifications. Hence, the lengths and
 * the positions count the characters (code points). The expected values have
 * been computed with Python, and all the SDKs test against the very same cases.
 */"""
        ),
        typescript_common.WARNING,
        Stripped('import * as AasCommon from "../src/common";'),
    ]  # type: List[Stripped]

    for len_case in len_slicing_and_find_cases.LEN_CASES:
        blocks.append(_generate_len_test(len_case))

    for slice_case in len_slicing_and_find_cases.SLICE_CASES:
        blocks.append(_generate_slice_test(slice_case))

    for find_case in len_slicing_and_find_cases.FIND_CASES:
        blocks.append(_generate_find_test(find_case))

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()
