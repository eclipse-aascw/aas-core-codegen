"""Generate code to test the ``modelType()`` methods."""


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
    """Generate code to test the ``modelType()`` methods."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test `modelType()` methods.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as OurTypes from "../src/types";
import * as OurStringification from "../src/stringification";
import * as TestCommonJsonization from "./commonJsonization";"""
        ),
    ]

    from_string = typescript_naming.function_name(Identifier("model_type_from_string"))

    must_to_string = typescript_naming.function_name(
        Identifier("must_model_type_to_string")
    )

    model_type_enum = typescript_naming.enum_name(Identifier("Model_type"))

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)

        load_minimal_name = typescript_naming.function_name(
            Identifier(f"load_minimal_{concrete_cls.name}")
        )

        model_type_literal = typescript_naming.enum_literal_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
test("model type of {cls_name_typescript}", () => {{
{I}const instance = TestCommonJsonization.{load_minimal_name}();

{I}expect(instance.modelType()).toStrictEqual(
{II}OurTypes.{model_type_enum}.{model_type_literal}
{I});
}});"""
            )
        )

        string_literal = typescript_common.string_literal(
            typescript_naming.enum_literal_name(concrete_cls.name)
        )

        blocks.append(
            Stripped(
                f"""\
test("model type from string of {cls_name_typescript}", () => {{
{I}const text = {string_literal};
{I}const literal = OurStringification.{from_string}(
{II}text
{I});

{I}expect(literal).toStrictEqual(
{II}OurTypes.{model_type_enum}.{model_type_literal}
{I});
}});"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
test("model type to string of {cls_name_typescript}", () => {{
{I}const text = OurStringification.{must_to_string}(
{II}OurTypes.{model_type_enum}.{model_type_literal}
{I});

{I}expect(text).toStrictEqual(
{II}{string_literal}
{I});
}});"""
            )
        )

    blocks.append(
        Stripped(
            f"""\
test("model type from invalid string", () => {{
{I}const text = "This is definitely not a valid model type.";
{I}const literal = OurStringification.{from_string}(
{II}text
{I});

{I}expect(literal).toBeNull();
}});"""
        )
    )

    to_string = typescript_naming.function_name(Identifier("model_type_to_string"))

    blocks.append(
        Stripped(
            f"""\
test("invalid model type to string", () => {{
{I}// The number 9007199254740991 is the maximum safe integer.
{I}const literal = <OurTypes.{model_type_enum}>9007199254740991;
{I}const text = OurStringification.{to_string}(
{II}literal
{I});

{I}expect(text).toBeNull();
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
