"""Generate code to test stringification of enumerations."""

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
    """Generate code to test stringification of enumerations."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test string de/serialization of enumeration literals.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as OurStringification from "../src/stringification";
import * as OurTypes from "../src/types";"""
        ),
    ]

    for enumeration in symbol_table.enumerations:
        enum_name_typescript = typescript_naming.enum_name(enumeration.name)

        from_str_name = typescript_naming.function_name(
            Identifier(f"{enumeration.name}_from_string")
        )
        to_str_name = typescript_naming.function_name(
            Identifier(f"{enumeration.name}_to_string")
        )
        must_to_str_name = typescript_naming.function_name(
            Identifier(f"must_{enumeration.name}_to_string")
        )

        for literal in enumeration.literals:
            literal_name_typescript = typescript_naming.enum_literal_name(literal.name)
            literal_value_literal = typescript_common.string_literal(literal.value)

            blocks.append(
                Stripped(
                    f"""\
test("{enum_name_typescript} stringification round-trip {literal_name_typescript}", () => {{
{I}const literal = OurTypes.{enum_name_typescript}.{literal_name_typescript};

{I}const text = OurStringification.{must_to_str_name}(literal);
{I}expect(text).toStrictEqual({literal_value_literal});

{I}const nullableText = OurStringification.{to_str_name}(literal);
{I}expect(nullableText).toStrictEqual({literal_value_literal});

{I}const parsed = OurStringification.{from_str_name}(text);
{I}expect(parsed).toStrictEqual(literal);
}});"""
                )
            )

        literal_value_set = {literal.value for literal in enumeration.literals}
        invalid_literal_value = "invalid-literal"
        while invalid_literal_value in literal_value_set:
            invalid_literal_value = f"very-{invalid_literal_value}"

        blocks.append(
            Stripped(
                f"""\
test("{enum_name_typescript} from invalid string", () => {{
{I}const parsed = OurStringification.{from_str_name}(
{I}{I}{typescript_common.string_literal(invalid_literal_value)}
{I});

{I}expect(parsed).toBeNull();
}});"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
test("{enum_name_typescript} invalid literal to string", () => {{
{I}// The number 9007199254740991 is the maximum safe integer.
{I}const invalidLiteral = <OurTypes.{enum_name_typescript}>9007199254740991;

{I}expect(OurStringification.{to_str_name}(invalidLiteral)).toBeNull();
{I}expect(() => OurStringification.{must_to_str_name}(invalidLiteral)).toThrow();
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
