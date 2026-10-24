"""Generate the unit tests for the operations on strings."""

import io
import re
from typing import List

from icontract import ensure, require

from aas_core_codegen import string_helper_cases
from aas_core_codegen.common import Stripped
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
)
from aas_core_codegen.golang import common as golang_common
from aas_core_codegen.golang.common import INDENT as I, INDENT2 as II


def _function_name(prefix: str, description: str) -> str:
    """Derive the name of a test function from the ``description`` of a case."""
    words = re.split(r"[^a-zA-Z0-9]+", description)
    return f"Test{prefix}" + "".join(word.capitalize() for word in words if word)


# fmt: off
@require(
    lambda type_inference: intermediate_uses.string_operations(type_inference)
)
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    repo_url: Stripped,
    type_inference: intermediate_type_inference.TypeInference,
) -> str:
    """Generate the unit tests for the operations on strings."""
    test_blocks: List[Stripped] = []

    if intermediate_uses.string_len_call(type_inference):
        for len_case in string_helper_cases.LEN_CASES:
            explanation = golang_common.string_literal(
                f"Expected {len_case.python_expression()} to give "
                f"{len_case.expected} ({len_case.description}), but got %d"
            )

            # NOTE (mristin):
            # We call the helper just as the transpiled code does.
            test_blocks.append(
                Stripped(
                    f"""\
func {_function_name("Len", len_case.description)}(t *testing.T) {{
{I}got := ourcommon.LenStr({golang_common.string_literal(len_case.text)})
{I}if got != {len_case.expected} {{
{II}t.Errorf({explanation}, got)
{I}}}
}}"""
                )
            )

    if intermediate_uses.string_slicing(type_inference):
        for slice_case in string_helper_cases.SLICE_CASES:
            text = golang_common.string_literal(slice_case.text)
            start = "0" if slice_case.start is None else str(slice_case.start)

            # NOTE (mristin):
            # We call the helper just as the transpiled code does.
            call = (
                f"ourcommon.SliceStrFrom({text}, {start})"
                if slice_case.end is None
                else f"ourcommon.SliceStr({text}, {start}, {slice_case.end})"
            )

            explanation = golang_common.string_literal(
                f"Expected {slice_case.python_expression()} to give "
                f"{slice_case.expected!r} ({slice_case.description}), but got %q"
            )

            test_blocks.append(
                Stripped(
                    f"""\
func {_function_name("Slice", slice_case.description)}(t *testing.T) {{
{I}got := {call}
{I}if got != {golang_common.string_literal(slice_case.expected)} {{
{II}t.Errorf({explanation}, got)
{I}}}
}}"""
                )
            )

    if intermediate_uses.string_find_call(type_inference):
        for find_case in string_helper_cases.FIND_CASES:
            text = golang_common.string_literal(find_case.text)
            sub = golang_common.string_literal(find_case.sub)

            # NOTE (mristin):
            # We call the helper just as the transpiled code does.
            start = "0" if find_case.start is None else str(find_case.start)
            call = f"ourcommon.FindStr({text}, {sub}, {start})"

            explanation = golang_common.string_literal(
                f"Expected {find_case.python_expression()} to give "
                f"{find_case.expected} ({find_case.description}), but got %d"
            )

            test_blocks.append(
                Stripped(
                    f"""\
func {_function_name("Find", find_case.description)}(t *testing.T) {{
{I}got := {call}
{I}if got != {find_case.expected} {{
{II}t.Errorf({explanation}, got)
{I}}}
}}"""
                )
            )

    if intermediate_uses.string_ordering(type_inference):
        for compare_case in string_helper_cases.COMPARE_CASES:
            left = golang_common.string_literal(compare_case.left)
            right = golang_common.string_literal(compare_case.right)

            explanation = golang_common.string_literal(
                f"Expected {compare_case.python_expression()} to give "
                f"{compare_case.expected} ({compare_case.description}), but got %d"
            )

            test_blocks.append(
                Stripped(
                    f"""\
func {_function_name("Compare", compare_case.description)}(t *testing.T) {{
{I}got := strings.Compare({left}, {right})
{I}if got != {compare_case.expected} {{
{II}t.Errorf({explanation}, got)
{I}}}
}}"""
                )
            )

    if intermediate_uses.lstrip_call(type_inference):
        for lstrip_case in string_helper_cases.LSTRIP_CASES:
            explanation = golang_common.string_literal(
                f"Expected {lstrip_case.python_expression()} to give "
                f"{lstrip_case.expected!r} ({lstrip_case.description}), but got %q"
            )

            # NOTE (mristin):
            # We call the native function just as the transpiled code does.
            test_blocks.append(
                Stripped(
                    f"""\
func {_function_name("LStrip", lstrip_case.description)}(t *testing.T) {{
{I}got := strings.TrimLeft(
{II}{golang_common.string_literal(lstrip_case.text)},
{II}{golang_common.string_literal(lstrip_case.chars)},
{I})
{I}if got != {golang_common.string_literal(lstrip_case.expected)} {{
{II}t.Errorf({explanation}, got)
{I}}}
}}"""
                )
            )

    if intermediate_uses.rstrip_call(type_inference):
        for rstrip_case in string_helper_cases.RSTRIP_CASES:
            explanation = golang_common.string_literal(
                f"Expected {rstrip_case.python_expression()} to give "
                f"{rstrip_case.expected!r} ({rstrip_case.description}), but got %q"
            )

            # NOTE (mristin):
            # We call the native function just as the transpiled code does.
            test_blocks.append(
                Stripped(
                    f"""\
func {_function_name("RStrip", rstrip_case.description)}(t *testing.T) {{
{I}got := strings.TrimRight(
{II}{golang_common.string_literal(rstrip_case.text)},
{II}{golang_common.string_literal(rstrip_case.chars)},
{I})
{I}if got != {golang_common.string_literal(rstrip_case.expected)} {{
{II}t.Errorf({explanation}, got)
{I}}}
}}"""
                )
            )

    if intermediate_uses.startswith_call(type_inference):
        for startswith_case in string_helper_cases.STARTSWITH_CASES:
            explanation = golang_common.string_literal(
                f"Expected {startswith_case.python_expression()} to give "
                f"{startswith_case.expected!r} ({startswith_case.description}), "
                f"but got %v"
            )

            # NOTE (mristin):
            # We call the native function just as the transpiled code does.
            test_blocks.append(
                Stripped(
                    f"""\
func {_function_name("StartsWith", startswith_case.description)}(t *testing.T) {{
{I}got := strings.HasPrefix(
{II}{golang_common.string_literal(startswith_case.text)},
{II}{golang_common.string_literal(startswith_case.prefix)},
{I})
{I}if got != {"true" if startswith_case.expected else "false"} {{
{II}t.Errorf({explanation}, got)
{I}}}
}}"""
                )
            )

    if intermediate_uses.endswith_call(type_inference):
        for endswith_case in string_helper_cases.ENDSWITH_CASES:
            explanation = golang_common.string_literal(
                f"Expected {endswith_case.python_expression()} to give "
                f"{endswith_case.expected!r} ({endswith_case.description}), "
                f"but got %v"
            )

            # NOTE (mristin):
            # We call the native function just as the transpiled code does.
            test_blocks.append(
                Stripped(
                    f"""\
func {_function_name("EndsWith", endswith_case.description)}(t *testing.T) {{
{I}got := strings.HasSuffix(
{II}{golang_common.string_literal(endswith_case.text)},
{II}{golang_common.string_literal(endswith_case.suffix)},
{I})
{I}if got != {"true" if endswith_case.expected else "false"} {{
{II}t.Errorf({explanation}, got)
{I}}}
}}"""
                )
            )

    # NOTE (mristin):
    # An unused import does not compile in Go, so we import only what the tests
    # name.
    import_lines: List[str] = []
    if golang_common.names_package(test_blocks, "strings"):
        import_lines.append(f'{I}"strings"')

    import_lines.append(f'{I}"testing"')

    if golang_common.names_package(test_blocks, "ourcommon"):
        import_lines.append(f'{I}ourcommon "{repo_url}/common"')

    import_lines_joined = "\n".join(import_lines)

    blocks: List[Stripped] = [
        Stripped(
            """\
// Test the operations on strings.
//
// The operations follow the Python implementation, since Python is
// the language of the meta-model specifications. Hence, they work on
// the characters (code points) of the strings. The expected values have been
// computed with Python, and all the SDKs test against the very same cases.
package common_string_helpers_test"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{import_lines_joined}
)"""
        ),
        *test_blocks,
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
