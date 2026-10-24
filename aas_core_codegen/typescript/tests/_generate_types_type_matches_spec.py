"""Generate code to test the ``typesMatch`` function."""

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
    INDENT2 as II,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test the ``typesMatch`` function."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test `typesMatch`.
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
        load_minimal_name = typescript_naming.function_name(
            Identifier(f"load_minimal_{concrete_cls.name}")
        )

        instance_var = typescript_naming.constant_name(
            Identifier(f"the_{concrete_cls.name}")
        )

        blocks.append(
            Stripped(
                f"""\
const {instance_var} = TestCommonJsonization.{load_minimal_name}();"""
            )
        )

    for concrete_cls in symbol_table.concrete_classes:
        body_blocks: List[Stripped] = []

        that_var = typescript_naming.constant_name(
            Identifier(f"the_{concrete_cls.name}")
        )

        for other_cls in symbol_table.concrete_classes:
            other_var = typescript_naming.constant_name(
                Identifier(f"the_{other_cls.name}")
            )

            if other_cls.is_subclass_of(concrete_cls):
                body_blocks.append(
                    Stripped(
                        f"""\
expect(
{I}OurTypes.typesMatch(
{II}{that_var},
{II}{other_var}
{I})
).toStrictEqual(true);"""
                    )
                )
            else:
                body_blocks.append(
                    Stripped(
                        f"""\
expect(
{I}OurTypes.typesMatch(
{II}{that_var},
{II}{other_var}
{I})
).toStrictEqual(false);"""
                    )
                )

        body = "\n\n".join(body_blocks)

        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)
        blocks.append(
            Stripped(
                f"""\
test("type matches for {cls_name_typescript}", () => {{
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
