"""Generate code to test the ``descend`` methods and ``PassThroughVisitor``."""

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
    INDENT4 as IIII,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test the ``descend`` methods and ``PassThroughVisitor``."""
    blocks = [
        Stripped(
            """\
/**
 * Test `descend*` functions and `PassThroughVisitor`.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as path from "path";
import * as fs from "fs";

import * as AasTypes from "../src/types";
import * as TestCommon from "./common";
import * as TestCommonJsonization from "./commonJsonization";"""
        ),
        Stripped(
            f"""\
/**
 * Record a human-readable trace of a descent over an object tree.
 */
class TracingVisitor extends AasTypes.PassThroughVisitor {{
{I}readonly log = new Array<string>();

{I}visit(that: AasTypes.Class) {{
{II}this.log.push(TestCommon.traceMark(that));
{II}super.visit(that);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Expect that the trace from {{@link types.Class.descend}} and
 * {{@link TracingVisitor}} are equal.
 *
 * @param instance - to be descended through
 * @throws an {{@link Error}} if the two traces are not equal
 */
function expectDescendAndPassThroughVisitorSame(
{I}instance: AasTypes.Class
): void {{
{I}const traceFromDescend = new Array<string>();
{I}for (const subInstance of instance.descend()) {{
{II}traceFromDescend.push(TestCommon.traceMark(subInstance));
{I}}}

{I}const visitor = new TracingVisitor();
{I}visitor.visit(instance);
{I}const traceFromVisitor = visitor.log;

{I}expect(traceFromVisitor.length).toBeGreaterThan(0);
{I}expect(TestCommon.traceMark(instance)).toStrictEqual(traceFromVisitor[0]);

{I}traceFromVisitor.shift();

{I}expect(traceFromVisitor).toStrictEqual(traceFromDescend);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Compare the trace against the golden one from the test data,
 * or re-record the trace if {{@link common.RECORD_MODE}}.
 *
 * @param instance - to be traced
 * @param expectedPath - path to the golden trace
 */
function compareOrRecordTrace(
{I}instance: AasTypes.Class,
{I}expectedPath: string
) {{
{I}const lines = new Array<string>();
{I}for (const descendant of instance.descend()) {{
{II}lines.push(TestCommon.traceMark(descendant));
{I}}}
{I}// NOTE (mristin):
{I}// We add a new line for POSIX systems which prefer a new line
{I}// at the end of the file.
{I}lines.push("");
{I}const got = lines.join("\\n");

{I}if (TestCommon.RECORD_MODE) {{
{II}const parent = path.dirname(expectedPath);
{II}if (!fs.existsSync(parent)) {{
{III}fs.mkdirSync(parent, {{recursive: true}});
{II}}}
{II}fs.writeFileSync(expectedPath, got, "utf-8");
{I}}} else {{
{II}if (!fs.existsSync(expectedPath)) {{
{III}throw new Error(
{IIII}`The file with the recorded trace does not exist: ${{expectedPath}}; ` +
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

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        load_maximal_name = typescript_naming.function_name(
            Identifier(f"load_maximal_{concrete_cls.name}")
        )

        blocks.append(
            Stripped(
                f"""\
test("descend of {cls_name_typescript}", () => {{
{I}const instance = TestCommonJsonization.{load_maximal_name}();

{I}compareOrRecordTrace(
{II}instance,
{II}path.join(
{III}TestCommon.TEST_DATA_DIR,
{III}"descend",
{III}{typescript_common.string_literal(cls_name_json)},
{III}"maximal.json.trace"
{II})
{I});
}});"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
test("descend against PassThroughVisitor", () => {{
{I}const instance = TestCommonJsonization.{load_maximal_name}();

{I}expectDescendAndPassThroughVisitorSame(instance);
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
