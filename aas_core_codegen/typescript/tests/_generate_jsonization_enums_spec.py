"""Generate code to test the JSON de/serialization of enumerations."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, Identifier
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
    """Generate code to test the JSON de/serialization of enumerations."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test JSON de/serialization of enumeration literals.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as OurJsonization from "../src/jsonization";
import * as OurTypes from "../src/types";"""
        ),
    ]

    for enumeration in symbol_table.enumerations:
        enum_name_typescript = typescript_naming.enum_name(enumeration.name)

        assert (
            len(enumeration.literals) > 0
        ), f"Unexpected enumeration without literals: {enumeration.name}"

        deserialization_function = typescript_naming.function_name(
            Identifier(f"{enumeration.name}_from_jsonable")
        )

        for literal in enumeration.literals:
            literal_name_typescript = typescript_naming.enum_literal_name(literal.name)

            blocks.append(
                Stripped(
                    f"""\
test("{enum_name_typescript} deserializes {literal_name_typescript} OK", () => {{
{I}const jsonable = {typescript_common.string_literal(literal.value)};

{I}const literalOrError = OurJsonization.{deserialization_function}(
{II}jsonable
{I});

{I}expect(literalOrError.error).toBeNull();
{I}const parsedLiteral = literalOrError.mustValue();

{I}expect(parsedLiteral).toStrictEqual(
{II}OurTypes.{enum_name_typescript}.{literal_name_typescript}
{I});
}});"""
                )
            )

        literal_value_set = {literal.value for literal in enumeration.literals}
        invalid_literal_value = "invalid-literal"
        while invalid_literal_value in literal_value_set:
            invalid_literal_value = f"very-{invalid_literal_value}"

        expected_message = (
            f"Not a valid string representation of a literal "
            f"of {enum_name_typescript}: {invalid_literal_value}"
        )

        blocks.append(
            Stripped(
                f"""\
test("{enum_name_typescript} deserialization fail", () => {{
{I}const jsonable = {typescript_common.string_literal(invalid_literal_value)};

{I}const literalOrError = OurJsonization.{deserialization_function}(
{II}jsonable
{I});

{I}expect(literalOrError.error.message).toStrictEqual(
{II}{typescript_common.string_literal(expected_message)}
{I});
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
