"""Generate code for common XML de/serialization shared across the tests."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
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
    """Generate code for common XML de/serialization shared across the tests."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Provide functions for loading generated XML examples of model instances.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as fs from "fs";
import * as path from "path";

import * as OurTypes from "../src/types";
import * as OurXmlization from "../src/xmlization";

import * as TestCommon from "./common";"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)
        cls_name_xml = naming.xml_class_name(concrete_cls.name)

        load_maximal_name = typescript_naming.function_name(
            Identifier(f"load_maximal_{concrete_cls.name}")
        )

        load_minimal_name = typescript_naming.function_name(
            Identifier(f"load_minimal_{concrete_cls.name}")
        )

        as_function = typescript_naming.function_name(
            Identifier(f"as_{concrete_cls.name}")
        )

        blocks.append(
            Stripped(
                f"""\
/**
 * Load a maximal XML example of {{@link types.{cls_name_typescript}}}
 * from the test data directory.
 */
export function {load_maximal_name}(
): OurTypes.{cls_name_typescript} {{
{I}const aPath = path.join(
{II}TestCommon.TEST_DATA_DIR,
{II}"Xml",
{II}"Expected",
{II}{typescript_common.string_literal(cls_name_xml)},
{II}"maximal.xml"
{I});

{I}const text = fs.readFileSync(aPath, "utf-8");

{I}const instanceOrError = OurXmlization.fromXmlString(
{II}text
{I});
{I}expect(instanceOrError.error).toBeNull();
{I}const instance = instanceOrError.mustValue();

{I}const casted = OurTypes.{as_function}(instance);
{I}if (casted === null) {{
{II}throw new Error(
{III}`Expected instance of {cls_name_typescript} in ${{aPath}}, ` +
{III}`but got: ${{typeof instance}}`
{II});
{I}}}
{I}return casted;
}}"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
/**
 * Load a minimal XML example of {{@link types.{cls_name_typescript}}}
 * from the test data directory.
 */
export function {load_minimal_name}(
): OurTypes.{cls_name_typescript} {{
{I}const aPath = path.join(
{II}TestCommon.TEST_DATA_DIR,
{II}"Xml",
{II}"Expected",
{II}{typescript_common.string_literal(cls_name_xml)},
{II}"minimal.xml"
{I});

{I}const text = fs.readFileSync(aPath, "utf-8");

{I}const instanceOrError = OurXmlization.fromXmlString(
{II}text
{I});
{I}expect(instanceOrError.error).toBeNull();
{I}const instance = instanceOrError.mustValue();

{I}const casted = OurTypes.{as_function}(instance);
{I}if (casted === null) {{
{II}throw new Error(
{III}`Expected instance of {cls_name_typescript} in ${{aPath}}, ` +
{III}`but got: ${{typeof instance}}`
{II});
{I}}}
{I}return casted;
}}"""
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
