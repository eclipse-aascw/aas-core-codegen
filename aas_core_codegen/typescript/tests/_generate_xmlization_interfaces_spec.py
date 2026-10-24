"""Generate code to test the XML de/serialization of interfaces."""

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
    """Generate code to test the XML de/serialization of interfaces."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test XML de/serialization of interfaces.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as OurXmlization from "../src/xmlization";
import * as OurTypes from "../src/types";

import * as TestCommonXmlization from "./commonXmlization";"""
        ),
    ]

    for cls in symbol_table.classes:
        if cls.interface is None or len(cls.interface.implementers) == 0:
            continue

        interface_name_typescript = typescript_naming.interface_name(cls.name)
        as_function = typescript_naming.function_name(Identifier(f"as_{cls.name}"))
        from_xml_string_function = typescript_naming.function_name(
            Identifier(f"{cls.name}_from_xml_string")
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
{I}"{interface_name_typescript} XML round-trip " +
{I}"starting from {cls_name_typescript} OK",
{I}() => {{
{II}const instance = TestCommonXmlization.{load_minimal_name}();

{II}const xmlText = OurXmlization.toXmlString(instance);
{II}const anotherInstanceOrError = OurXmlization.fromXmlString(xmlText);
{II}expect(anotherInstanceOrError.error).toBeNull();
{II}const anotherInstance = anotherInstanceOrError.mustValue();

{II}const asInterface = OurTypes.{as_function}(anotherInstance);
{II}expect(asInterface).not.toBeNull();
{I}}}
);"""
                )
            )

            blocks.append(
                Stripped(
                    f"""\
test(
{I}"{interface_name_typescript} XML round-trip via " +
{I}"{from_xml_string_function} starting from {cls_name_typescript} OK",
{I}() => {{
{II}const instance = TestCommonXmlization.{load_minimal_name}();

{II}const xmlText = OurXmlization.toXmlString(instance);
{II}const anotherInstanceOrError = OurXmlization.{from_xml_string_function}(
{III}xmlText
{II});
{II}expect(anotherInstanceOrError.error).toBeNull();
{I}}}
);"""
                )
            )

        blocks.append(
            Stripped(
                f"""\
test("{interface_name_typescript} XML deserialization fail", () => {{
{I}const instanceOrError = OurXmlization.fromXmlString("This is not XML.");
{I}expect(instanceOrError.error).not.toBeNull();
}});"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
test(
{I}"{interface_name_typescript} XML deserialization fail via " +
{I}"{from_xml_string_function}",
{I}() => {{
{II}const instanceOrError = OurXmlization.{from_xml_string_function}(
{III}"This is not XML."
{II});
{II}expect(instanceOrError.error).not.toBeNull();
{I}}}
);"""
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
