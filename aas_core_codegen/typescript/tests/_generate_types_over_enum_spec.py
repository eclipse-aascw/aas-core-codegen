"""Generate code to test the ``over{Enum}`` methods."""


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
    """Generate code to test the ``over{Enum}`` methods."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test `over{Enum}` functions.
 */"""
        ),
        typescript_common.WARNING,
        Stripped('import * as OurTypes from "../src/types";'),
    ]

    for enumeration in symbol_table.enumerations:
        name = typescript_naming.enum_name(enumeration.name)

        body_writer = io.StringIO()
        body_writer.write(
            f"""\
const expected: Array<OurTypes.{name}> = [
"""
        )
        for i, literal in enumerate(enumeration.literals):
            literal_name = typescript_naming.enum_literal_name(literal.name)
            body_writer.write(f"{I}OurTypes.{name}.{literal_name}")

            if i < len(enumeration.literals) - 1:
                body_writer.write(",")

            body_writer.write("\n")

        body_writer.write("];\n\n")

        over_enum_name = typescript_naming.function_name(
            Identifier(f"over_{enumeration.name}")
        )

        body_writer.write(
            f"""\
const got = new Array<OurTypes.{name}>();
for (const literal of OurTypes.{over_enum_name}()) {{
{I}got.push(literal);
}}

expect(got).toStrictEqual(expected);"""
        )

        blocks.append(
            Stripped(
                f"""\
test("over {name}", () => {{
{I}{indent_but_first_line(body_writer.getvalue(), I)}
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
