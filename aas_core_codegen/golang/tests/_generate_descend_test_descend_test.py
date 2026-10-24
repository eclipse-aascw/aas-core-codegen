"""Generate code to test ``Descend*`` functions."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    Identifier,
)
from aas_core_codegen.golang import common as golang_common, naming as golang_naming
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
)


def _generate_for_cls(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the test function."""
    test_function_name = golang_naming.function_name(
        Identifier(f"test_descend_on_an_instance_of_{cls.name}")
    )

    must_load_maximal_name = golang_naming.function_name(
        Identifier(f"must_load_maximal_{cls.name}")
    )

    model_type_literal = golang_common.string_literal(naming.json_model_type(cls.name))

    return Stripped(
        f"""\
func {test_function_name}(
{I}t *testing.T,
) {{
{I}instance := ourtesting.{must_load_maximal_name}()

{I}expectedPth := filepath.Join(
{II}ourtesting.TestDataDir,
{II}"Descend",
{II}{model_type_literal},
{II}"maximal.json.trace",
{I})

{I}onlyOnce := false

{I}message := compareOrRerecordTrace(
{II}instance,
{II}expectedPth,
{II}onlyOnce,
{I})
{I}if message != nil {{
{II}t.Fatal(*message)
{I}}}
}}"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to test ``Descend*`` functions."""
    blocks: List[Stripped] = [
        Stripped("package types_descend_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"path/filepath"
{I}"testing"
{I}ourtesting "{repo_url}/ourtesting"
)"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_for_cls(cls=concrete_cls))

    blocks.append(golang_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
