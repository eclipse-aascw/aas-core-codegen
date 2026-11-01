"""Generate code to test the predicates of the safe integer range."""

from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.golang import common as golang_common
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import uses as intermediate_uses


def _generate_test(
    function_name: str, value_type: str, safe: str, unsafe: str
) -> Stripped:
    """
    Generate the test of the predicate ``function_name`` over ``value_type``.

    The ``safe`` and the ``unsafe`` are the values, joined over lines, which
    the predicate has to accept and to refuse, respectively.
    """
    return Stripped(
        f"""\
func Test{function_name}(t *testing.T) {{
{I}for _, value := range []{value_type}{{
{II}{indent_but_first_line(safe, II)},
{I}}} {{
{II}if !ourcommon.{function_name}(value) {{
{III}t.Errorf("Expected %v to be a safe integer, but it is not", value)
{II}}}
{I}}}

{I}for _, value := range []{value_type}{{
{II}{indent_but_first_line(unsafe, II)},
{I}}} {{
{II}if ourcommon.{function_name}(value) {{
{III}t.Errorf("Expected %v not to be a safe integer, but it is", value)
{II}}}
{I}}}
}}"""
    )


# fmt: off
@require(
    lambda symbol_table:
    intermediate_uses.safe_integer_checks(symbol_table)
)
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """
    Generate code to test the predicates of the safe integer range.

    The bounds of the range [-2^53 + 1, 2^53 - 1] are accepted, and the integers
    just outside are refused.
    """
    blocks: List[Stripped] = [
        Stripped("package common_safe_integer_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"math"
{I}"testing"
{I}ourcommon "{repo_url}/common"
)"""
        ),
        _generate_test(
            function_name="IsSafeInteger",
            value_type="int64",
            safe="0,\n9007199254740991,\n-9007199254740991",
            unsafe=(
                "9007199254740992,\n-9007199254740992,\n"
                "math.MaxInt64,\nmath.MinInt64"
            ),
        ),
    ]

    # NOTE (mristin):
    # The predicate over a float64 serves only the de-serialization of
    # the integer properties, so it is generated only for them.
    if intermediate_uses.integers(symbol_table):
        blocks.append(
            _generate_test(
                function_name="IsSafeIntegerFloat64",
                value_type="float64",
                safe="0,\n9007199254740991,\n-9007199254740991",
                unsafe="9007199254740992,\n-9007199254740992,\n1e300,\n-1e300",
            )
        )

    blocks.append(golang_common.WARNING)

    return "\n\n".join(blocks) + "\n"


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
