"""Generate code to test ``int`` on strings."""

import io
from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate, tests_common
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.golang import (
    common as golang_common,
    transpilation as golang_transpilation,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)
from aas_core_codegen.intermediate import uses as intermediate_uses


def _generate_test_parse_safe_int() -> List[Stripped]:
    """Generate the table-driven tests of parsing the integers."""
    function_name = golang_transpilation.PARSE_SAFE_INT_FUNCTION_NAME

    case_blocks: List[str] = []
    for text, expected in tests_common.PARSE_INT_CASES:
        case_blocks.append(f"{{{golang_common.string_literal(text)}, {expected}}},")

    cases_joined = "\n".join(case_blocks)

    invalid_blocks = [
        f"{golang_common.string_literal(text)},"
        for text in tests_common.PARSE_INT_INVALID_CASES
    ]

    invalid_joined = "\n".join(invalid_blocks)

    return [
        Stripped(
            f"""\
// Test parsing the valid safe integers.
func Test{function_name}(t *testing.T) {{
{I}cases := []struct {{
{II}text     string
{II}expected int64
{I}}}{{
{II}{indent_but_first_line(cases_joined, II)}
{I}}}

{I}for _, c := range cases {{
{II}got := ourcommon.{function_name}(c.text)
{II}if got != c.expected {{
{III}t.Errorf(
{IIII}"Expected {function_name}(%q) to be %d, but got %d",
{IIII}c.text, c.expected, got,
{III})
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Check that {function_name} panics on text.
func mustPanicOn{function_name}(t *testing.T, text string) {{
{I}defer func() {{
{II}if r := recover(); r == nil {{
{III}t.Errorf("Expected {function_name}(%q) to panic, but it did not", text)
{II}}}
{I}}}()

{I}ourcommon.{function_name}(text)
}}"""
        ),
        Stripped(
            f"""\
// Test that parsing the texts which are not safe integers panics.
func Test{function_name}Invalid(t *testing.T) {{
{I}texts := []string{{
{II}{indent_but_first_line(invalid_joined, II)}
{I}}}

{I}for _, text := range texts {{
{II}mustPanicOn{function_name}(t, text)
{I}}}
}}"""
        ),
    ]


# fmt: off
@require(lambda symbol_table: intermediate_uses.int_call(symbol_table))
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """
    Generate code to test ``int`` on strings.

    The expected values have been computed with Python, and all the SDKs test
    against the very same cases, see :py:mod:`aas_core_codegen.tests_common`.
    """
    # NOTE (mristin):
    # We explain the semantics in a detached comment instead of the package
    # documentation to keep the package clause at the top as in the other tests.
    blocks: List[Stripped] = [
        Stripped("package common_parse_int_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"testing"
{I}ourcommon "{repo_url}/common"
)"""
        ),
        Stripped(
            f"""\
// The built-in `int` is transpiled to
// ourcommon.{golang_transpilation.PARSE_SAFE_INT_FUNCTION_NAME}, which is stricter than
// the Python `int`. It accepts only an optional sign followed by the ASCII digits,
// and only the safe integers, i.e., the integers within -(2^53 - 1) and 2^53 - 1.
// Otherwise, it panics.
//
// The expected values have been computed with Python, and all the SDKs test
// against the very same cases."""
        ),
        *_generate_test_parse_safe_int(),
        golang_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
