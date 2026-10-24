"""Generate the functions to trace instances for tests."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.golang import common as golang_common
from aas_core_codegen.golang.common import INDENT as I, INDENT2 as II


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(repo_url: Stripped) -> str:
    """Generate the functions to trace instances for tests."""
    blocks: List[Stripped] = [
        Stripped(
            """\
package ourtesting"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}ourstringification "{repo_url}/stringification"
{I}ourtypes "{repo_url}/types"
)"""
        ),
        Stripped(
            f"""\
// Represent `that` instance as a human-readable line of an iteration trace.
func TraceMark(that ourtypes.IClass) string {{
{I}modelTypeText := ourstringification.MustModelTypeToString(
{II}that.ModelType(),
{I})
{I}return modelTypeText
}}"""
        ),
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
