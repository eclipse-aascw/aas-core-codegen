"""Generate code to test the ``xOrDefault`` methods."""

import io
from typing import List, Optional

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test the ``xOrDefault`` methods."""
    uses_json_types = intermediate_uses.json_types(symbol_table)

    # NOTE (mristin):
    # The JSON-able types are defined in the types module only if the meta-model
    # uses them, so we represent them only in that case.
    maybe_json_types = (
        " | OurTypes.JsonArray | OurTypes.JsonObject" if uses_json_types else ""
    )

    maybe_json_branch = (
        f"""\
 else if (typeof value === "object") {{
{II}got = stringifyJsonWithSortedKeys(value);
{I}}}"""
        if uses_json_types
        else ""
    )

    blocks = [
        Stripped(
            """\
/**
 * Test `*OrDefault` functions.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as path from "path";
import * as fs from "fs";

import * as OurStringification from "../src/stringification";
import * as OurTypes from "../src/types";
import * as TestCommon from "./common";
import * as TestCommonJsonization from "./commonJsonization";"""
        ),
        Stripped(
            f"""\
/**
 * Represent explicitly a literal of an enumeration.
 */
class EnumerationLiteral {{
{I}constructor(public enumerationName: string, public literalName) {{
{II}// Intentionally empty.
{I}}}

{I}toString(): string {{
{II}return `${{this.enumerationName}}.${{this.literalName}}`;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent a value such that we can immediately check whether it is the default value
 * or the set one.
 *
 * @remark
 * We compare it against the recorded golden file, if not {{@link common.RECORD_MODE}}.
 * Otherwise, when {{@link common.RECORD_MODE}} is set, we re-record the golden file.
 *
 * @param value - to be represented
 * @param expectedPath - to the golden file
 */
function compareOrRecordValue(
{I}value: boolean | number | string | null | EnumerationLiteral | OurTypes.Class{maybe_json_types},
{I}expectedPath: string
): void {{
{I}let got = "";
{I}if (
{II}typeof value === "boolean"
{II}|| typeof value === "number"
{II}|| typeof value === "string"
{II}|| value === null
{I}) {{
{II}got = JSON.stringify(value);
{I}}} else if (value instanceof EnumerationLiteral) {{
{II}got = value.toString();
{I}}} else if (value instanceof OurTypes.Class) {{
{II}got = TestCommon.traceMark(value);
{I}}}{maybe_json_branch} else {{
{II}throw new Error(`We do not know how to represent the value ${{value}}`);
{I}}}

{I}// NOTE (mristin):
{I}// We add a new line for POSIX systems which prefer a new line
{I}// at the end of the file.
{I}got += "\\n";

{I}if (TestCommon.RECORD_MODE) {{
{II}const parent = path.dirname(expectedPath);
{II}if (!fs.existsSync(parent)) {{
{III}fs.mkdirSync(parent, {{recursive: true}});
{II}}}
{II}fs.writeFileSync(expectedPath, got, "utf-8");
{I}}} else {{
{II}if (!fs.existsSync(expectedPath)) {{
{III}throw new Error(
{IIII}`The file with the recorded value does not exist: ${{expectedPath}}; ` +
{IIII}`you probably want to set the environment ` +
{IIII}`variable ${{TestCommon.RECORD_MODE_ENVIRONMENT_VARIABLE_NAME}}?`
{III});
{II}}}

{II}const expected =
{III}fs.readFileSync(expectedPath, "utf-8")
{III}.replace(/\\r\\n/g, "\\n");
{II}expect(got).toStrictEqual(expected);
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    if uses_json_types:
        blocks.insert(
            len(blocks) - 1,
            Stripped(
                f"""\
/**
 * Stringify the JSON-able value with the keys of the objects sorted so that
 * the result does not depend on their order.
 *
 * @param value - to be stringified
 * @returns JSON text of `value`
 */
function stringifyJsonWithSortedKeys(
{I}value: OurTypes.JsonArray | OurTypes.JsonObject
): string {{
{I}return JSON.stringify(value, (_key: string, nested: unknown): unknown => {{
{II}if (
{III}nested === null
{III}|| typeof nested !== "object"
{III}|| Array.isArray(nested)
{II}) {{
{III}return nested;
{II}}}

{II}const anObject = nested as {{ [key: string]: unknown }};
{II}const sorted: {{ [key: string]: unknown }} = {{}};
{II}for (const key of Object.keys(anObject).sort()) {{
{III}sorted[key] = anObject[key];
{II}}}
{II}return sorted;
{I}}});
}}"""
            ),
        )

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        x_or_default_methods = []  # type: List[intermediate.MethodUnion]
        for method in concrete_cls.methods:
            if (
                method.name.endswith("_or_default")
                and method.visibility is intermediate.Visibility.PUBLIC
            ):
                x_or_default_methods.append(method)

        for method in x_or_default_methods:
            method_name_typescript = typescript_naming.method_name(method.name)

            result_enum = None  # type: Optional[intermediate.Enumeration]

            assert method.returns is not None, (
                f"Expected all X_or_default to return something, "
                f"but got None for {concrete_cls}.{method.name}"
            )

            if isinstance(
                method.returns, intermediate.OurTypeAnnotation
            ) and isinstance(method.returns.our_type, intermediate.Enumeration):
                result_enum = method.returns.our_type

            if result_enum is None:
                value_assignment_snippet = Stripped(
                    f"const value = instance.{method_name_typescript}();"
                )
            else:
                enum_to_string_name = typescript_naming.function_name(
                    Identifier(f"must_{result_enum.name}_to_string")
                )

                value_assignment_snippet = Stripped(
                    f"""\
const value = new EnumerationLiteral(
{I}{typescript_common.string_literal(typescript_naming.enum_name(result_enum.name))},
{I}OurStringification.{enum_to_string_name}(
{II}instance.{method_name_typescript}()
{I})
);"""
                )

            load_maximal_name = typescript_naming.function_name(
                Identifier(f"load_maximal_{concrete_cls.name}")
            )

            # noinspection SpellCheckingInspection
            blocks.append(
                Stripped(
                    f"""\
test("{cls_name_typescript}.{method_name_typescript} on maximal", () => {{
{I}const instance = TestCommonJsonization.{load_maximal_name}();

{I}{indent_but_first_line(value_assignment_snippet, I)}

{I}compareOrRecordValue(
{II}value,
{II}path.join(
{III}TestCommon.TEST_DATA_DIR,
{III}"xOrDefault",
{III}{typescript_common.string_literal(cls_name_json)},
{III}"{method_name_typescript}.on_maximal.json"
{II})
{I});
}});"""
                )
            )

            load_minimal_name = typescript_naming.function_name(
                Identifier(f"load_minimal_{concrete_cls.name}")
            )

            blocks.append(
                Stripped(
                    f"""\
test("{cls_name_typescript}.{method_name_typescript} on minimal", () => {{
{I}const instance = TestCommonJsonization.{load_minimal_name}();

{I}{indent_but_first_line(value_assignment_snippet, I)}

{I}compareOrRecordValue(
{II}value,
{II}path.join(
{III}TestCommon.TEST_DATA_DIR,
{III}"xOrDefault",
{III}{typescript_common.string_literal(cls_name_json)},
{III}"{method_name_typescript}.on_minimal.json"
{II})
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
