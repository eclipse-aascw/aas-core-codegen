"""Generate code to execute all common JSONization loader functions once."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier, Stripped
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)
from aas_core_codegen.typescript.common import INDENT as I


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to execute all common JSONization loader functions once."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Execute all common JSONization loader helpers once.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as TestCommonJsonization from "./commonJsonization";"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        load_maximal_name = typescript_naming.function_name(
            Identifier(f"load_maximal_{concrete_cls.name}")
        )
        load_minimal_name = typescript_naming.function_name(
            Identifier(f"load_minimal_{concrete_cls.name}")
        )
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
test("commonJsonization loaders for {cls_name_typescript}", () => {{
{I}expect(TestCommonJsonization.{load_minimal_name}()).not.toBeNull();
{I}expect(TestCommonJsonization.{load_maximal_name}()).not.toBeNull();
}});"""
            )
        )

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert __doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
