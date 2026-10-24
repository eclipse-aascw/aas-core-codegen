"""Generate code to test the JSON de/serialization of interfaces."""

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
    INDENT3 as III,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test the JSON de/serialization of interfaces."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test JSON de/serialization of interfaces.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as OurJsonization from "../src/jsonization";
import * as TestCommon from "./common";
import * as TestCommonJsonization from "./commonJsonization";"""
        ),
    ]

    for cls in symbol_table.classes:
        if cls.interface is None or len(cls.interface.implementers) == 0:
            continue

        interface_name_typescript = typescript_naming.interface_name(cls.name)

        deserialization_function = typescript_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        for implementer_cls in cls.interface.implementers:
            if (
                implementer_cls.serialization is None
                or not implementer_cls.serialization.with_model_type
            ):
                continue

            cls_name_typescript = typescript_naming.class_name(implementer_cls.name)

            load_minimal_name = typescript_naming.function_name(
                Identifier(f"load_minimal_{implementer_cls.name}")
            )

            blocks.append(
                Stripped(
                    f"""\
test(
{I}"{interface_name_typescript} round-trip " +
{I}"starting from {cls_name_typescript} OK",
{I}() => {{
{I}const instance = TestCommonJsonization.{load_minimal_name}();

{I}const jsonable = OurJsonization.toJsonable(instance);

{I}const anotherInstanceOrError = OurJsonization.{deserialization_function}(
{II}jsonable
{I});
{I}expect(anotherInstanceOrError.error).toBeNull();
{I}const anotherInstance = anotherInstanceOrError.mustValue();

{I}const anotherJsonable = OurJsonization.toJsonable(anotherInstance);

{I}const inequalityError = TestCommon.checkJsonablesEqual(
{II}jsonable,
{II}anotherJsonable
{I});
{I}if (inequalityError !== null) {{
{II}throw new Error(
{III}"The minimal example of {interface_name_typescript} " +
{III}"as an instance of {cls_name_typescript} serialized " +
{III}"to JSON, then de-serialized and serialized again does not match " +
{III}`the first JSON: ${{inequalityError.path}}: ${{inequalityError.message}}`
{II});
{I}}}
}});"""
                )
            )

        blocks.append(
            Stripped(
                f"""\
test("{interface_name_typescript} deserialization fail", () => {{
{I}const jsonable = "This is not a {interface_name_typescript}.";

{I}const instanceOrError = OurJsonization.{deserialization_function}(
{II}jsonable
{I});
{I}expect(instanceOrError.error.message).toStrictEqual(
{II}"Expected a JSON object, but got: string"
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
