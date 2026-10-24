"""Generate code to test the ``as*`` and ``is*`` functions."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test the ``as*`` and ``is*`` functions."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test `as*` and `is*` functions.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as OurTypes from "../src/types";
import * as TestCommonJsonization from "./commonJsonization";"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)

        load_minimal_name = typescript_naming.function_name(
            Identifier(f"load_minimal_{concrete_cls.name}")
        )

        instance_var = typescript_naming.variable_name(
            Identifier(f"the_{concrete_cls.name}")
        )

        body_blocks: List[Stripped] = [
            Stripped(
                f"""\
const {instance_var} =
{I}TestCommonJsonization.{load_minimal_name}();"""
            )
        ]

        for other_cls in symbol_table.classes:
            is_function_name = typescript_naming.function_name(
                Identifier(f"is_{other_cls.name}")
            )

            as_function_name = typescript_naming.function_name(
                Identifier(f"as_{other_cls.name}")
            )

            if concrete_cls.is_subclass_of(other_cls):
                body_blocks.append(
                    Stripped(
                        f"""\
expect(
{I}OurTypes.{is_function_name}({instance_var})
).toStrictEqual(true);
expect(
{I}OurTypes.{as_function_name}({instance_var})
).toStrictEqual({instance_var});"""
                    )
                )
            else:
                body_blocks.append(
                    Stripped(
                        f"""\
expect(
{I}OurTypes.{is_function_name}({instance_var})
).toStrictEqual(false);
expect(
{I}OurTypes.{as_function_name}({instance_var})
).toBeNull();"""
                    )
                )

        body = "\n\n".join(body_blocks)
        blocks.append(
            Stripped(
                f"""\
test("casts over an instance of {cls_name_typescript}", () => {{
{I}{indent_but_first_line(body, I)}
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
assert generate.__doc__.strip().startswith(__doc__.strip())
