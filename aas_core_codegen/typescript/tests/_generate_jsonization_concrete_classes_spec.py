"""Generate code to test the JSON de/serialization of concrete classes."""

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
    INDENT5 as IIIII,
)


def _tuple_items(
    numeric_place: intermediate.NumericPlace,
) -> "List[intermediate.TypeAnnotationUnion]":
    """Give out the items of the tuple at the ``numeric_place``."""
    type_anno = numeric_place.prop.type_annotation
    assert isinstance(type_anno, intermediate.TupleTypeAnnotation), (
        f"Expected a tuple at the numeric place of "
        f"{numeric_place.cls.name}.{numeric_place.prop.name}, but got: {type_anno}"
    )
    return list(type_anno.items)


def _generate_serialization_failure_tests(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the tests that a number unrepresentable in JSON is refused."""
    result = []  # type: List[Stripped]

    for numeric_place in intermediate.numeric_places(symbol_table):
        if numeric_place.a_type is intermediate.PrimitiveType.FLOAT:
            what = "a non-finite number"
            zero_literal = "0.0"
            values_literal = "[Infinity, -Infinity, NaN]"
        else:
            what = "an integer outside the range representable in JSON"
            zero_literal = "0"
            values_literal = "[9007199254740992, -9007199254740992]"

        prop_name = typescript_naming.property_name(numeric_place.prop.name)

        if numeric_place.index is None:
            mutation = Stripped(f"instance.{prop_name} = value;")
            expected_path = f".{prop_name}"
        else:
            # NOTE (mristin):
            # The value goes to the position indicated by the numeric place so
            # that a serializer which always reports the index 0 does not pass.
            # A tuple is an array in TypeScript, so a list and a tuple are
            # written the same way.
            items_joined = ", ".join(
                "value"
                if i == numeric_place.index
                else (
                    zero_literal
                    if numeric_place.in_list
                    else f"instance.{prop_name}[{i}]"
                )
                for i in range(
                    numeric_place.index + 1
                    if numeric_place.in_list
                    else len(_tuple_items(numeric_place))
                )
            )

            mutation = Stripped(
                f"instance.{prop_name} = [{items_joined}] as typeof instance."
                f"{prop_name};"
            )
            expected_path = f".{prop_name}[{numeric_place.index}]"

        cls_name_json = naming.json_model_type(numeric_place.cls.name)

        deserialization_function = typescript_naming.function_name(
            Identifier(f"{numeric_place.cls.name}_from_jsonable")
        )

        result.append(
            Stripped(
                f"""\
test(
{I}"{numeric_place.cls.name} serialization fails on {what} "
{I}+ "at {expected_path}",
{I}() => {{
{II}for (const value of {values_literal}) {{
{III}const instance = AasJsonization.{deserialization_function}(
{IIII}loadTheFirstExpected({typescript_common.string_literal(cls_name_json)})
{III}).mustValue();

{III}{mutation}

{III}let caught: unknown = null;
{III}try {{
{IIII}AasJsonization.toJsonable(instance);
{III}}} catch (error) {{
{IIII}caught = error;
{III}}}

{III}if (!(caught instanceof AasJsonization.SerializationError)) {{
{IIII}throw new Error(
{IIIII}`Expected a SerializationError, but got: ${{caught}}`
{IIII});
{III}}}

{III}expect(caught.path).toStrictEqual({typescript_common.string_literal(expected_path)});
{II}}}
{I}}}
);"""
            )
        )

    if len(result) > 0:
        result.insert(
            0,
            Stripped(
                f"""\
/**
 * Load the first recorded example of the `modelType`.
 */
function loadTheFirstExpected(modelType: string): AasJsonization.JsonValue {{
{I}const pths = Array.from(
{II}TestCommon.findFilesBySuffixRecursively(
{III}path.join(
{IIII}TestCommon.TEST_DATA_DIR,
{IIII}"Json",
{IIII}"Expected",
{IIII}modelType
{III}),
{III}".json"
{II})
{I});
{I}pths.sort();

{I}if (pths.length === 0) {{
{II}throw new Error(
{III}`Expected at least one recorded example of ${{modelType}}, but got none`
{II});
{I}}}

{I}return TestCommon.readJsonFromFileSync(pths[0]);
}}"""
            ),
        )

    return result


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test the JSON de/serialization of concrete classes."""
    blocks = [
        Stripped(
            """\
/**
 * Test JSON de/serialization of concrete classes.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as fs from "fs";
import * as path from "path";

import * as AasJsonization from "../src/jsonization";
import * as AasTypes from "../src/types";
import * as AasVerification from "../src/verification";

import * as TestCommon from "./common";"""
        ),
        Stripped(
            f"""\
/**
 * Assert that the result of the chain JSON → de-serialize → object → serialize → JSON
 * gives the input.
 */
function assertSerializeDeserializeEqualsOriginal(
{I}originalJsonable: AasJsonization.JsonValue,
{I}instance: AasTypes.Class,
{I}aPath: string
): void {{
{I}let jsonable: AasJsonization.JsonValue | null = null;
{I}try {{
{II}jsonable = AasJsonization.toJsonable(instance);
{I}}} catch (error) {{
{II}throw new Error(
{III}"Expected no exception during JSON serialization " +
{III}`of an instance of ${{instance.constructor.name}} from ${{aPath}}, ` +
{III}`but got: ${{error}}`
{II});
{I}}}

{I}const inequalityError = TestCommon.checkJsonablesEqual(
{II}originalJsonable,
{II}jsonable
{I});
{I}if (inequalityError !== null) {{
{II}throw new Error(
{III}`The original JSON from ${{aPath}} is unequal the serialized JSON: ` +
{III}`${{inequalityError.path}}: ${{inequalityError.message}}`
{II});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Assert that the deserialization error equals the expected golden one,
 * or, if {{@link common.RECORD_MODE}} set, re-record the expected error.
 *
 * @param error - obtained error during the de-serialization
 * @param aPath - to the JSON file which caused the de-serialization error
 * @throws an {{@link Error}} if assertion fails
 */
function assertDeserializationErrorEqualsExpectedOrRecord(
{I}error: AasJsonization.DeserializationError,
{I}aPath: string
): void {{
{I}const errorPath = aPath + ".error";
{I}const got = `${{error.path}}: ${{error.message}}\\n`;

{I}if (TestCommon.RECORD_MODE) {{
{II}fs.writeFileSync(errorPath, got, "utf-8");
{I}}} else {{
{II}if (!fs.existsSync(errorPath)) {{
{III}throw new Error(
{IIII}`The file with the recorded deserialization error does ` +
{IIII}`not exist: ${{errorPath}}; you probably want to set ` +
{IIII}`the environment variable ${{TestCommon.RECORD_MODE_ENVIRONMENT_VARIABLE_NAME}}?`
{III});
{II}}}

{II}const expected =
{III}fs.readFileSync(errorPath, "utf-8")
{III}.replace(/\\r\\n/g, "\\n");
{II}if (expected !== got) {{
{III}throw new Error(
{IIII}`Expected the error:\\n${{JSON.stringify(expected)}}\\n, ` +
{IIII}`but got:\\n${{JSON.stringify(got)}}\\n` +
{IIII}`when de-serializing from ${{aPath}}`
{III});
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Assert that the obtained verification errors equal the expected verification errors,
 * or, if {{@link common.RECORD_MODE}} set, re-record the expected errors.
 *
 * @param errors - obtained verification errors
 * @param aPath - to the JSON file which caused the verification errors
 * @throws an {{@link Error}} if assertion fails
 */
function assertVerificationErrorsEqualExpectedOrRecord(
{I}errors: Array<AasVerification.VerificationError>,
{I}aPath: string
): void {{
{I}const errorsPath = aPath + ".errors";

{I}const lines = new Array<string>();
{I}for (const error of errors) {{
{II}lines.push(`${{error.path}}: ${{error.message}}`);
{I}}}
{I}// NOTE (mristin):
{I}// We add a new line for POSIX systems which prefer a new line
{I}// at the end of the file.
{I}lines.push("");
{I}const got = lines.join("\\n");

{I}if (TestCommon.RECORD_MODE) {{
{II}fs.writeFileSync(errorsPath, got, "utf-8");
{I}}} else {{
{II}if (!fs.existsSync(errorsPath)) {{
{III}throw new Error(
{IIII}`The file with the recorded verification errors ` +
{IIII}`does not exist: ${{errorsPath}}; you probably want to set the environment ` +
{IIII}`variable ${{TestCommon.RECORD_MODE_ENVIRONMENT_VARIABLE_NAME}}?`
{III});
{II}}}

{II}const expected =
{III}fs.readFileSync(errorsPath, "utf-8")
{III}.replace(/\\r\\n/g, "\\n");
{II}if (expected !== got) {{
{III}throw new Error(
{IIII}`Expected the error(s):\\n${{JSON.stringify(expected)}}\\n, ` +
{IIII}`but got:\\n${{JSON.stringify(got)}}\\n` +
{IIII}`when verifying ${{aPath}}`
{III});
{II}}}
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        deserialization_function = typescript_naming.function_name(
            Identifier(f"{concrete_cls.name}_from_jsonable")
        )

        blocks.extend(
            [
                Stripped(
                    f"""\
test("{cls_name_typescript} round-trip OK", () => {{
{I}const pths = Array.from(
{II}TestCommon.findFilesBySuffixRecursively(
{III}path.join(
{IIII}TestCommon.TEST_DATA_DIR,
{IIII}"Json",
{IIII}"Expected",
{IIII}{typescript_common.string_literal(cls_name_json)}
{III}),
{III}".json"
{II})
{I});
{I}pths.sort();

{I}for (const pth of pths) {{
{II}const jsonable = TestCommon.readJsonFromFileSync(pth);

{II}const instanceOrError = AasJsonization.{deserialization_function}(
{III}jsonable
{II});
{II}expect(instanceOrError.error).toBeNull();
{II}const instance = instanceOrError.mustValue();

{II}TestCommon.assertNoVerificationErrors(AasVerification.verify(instance), pth);

{II}assertSerializeDeserializeEqualsOriginal(
{III}jsonable,
{III}instance,
{III}pth
{II});
{I}}}
}});"""
                ),
                Stripped(
                    f"""\
test("{cls_name_typescript} deserialization fail", () => {{
{I}for (
{II}const causeDir of
{II}TestCommon.findImmediateSubdirectories(
{III}path.join(
{IIII}TestCommon.TEST_DATA_DIR,
{IIII}"Json",
{IIII}"Unexpected",
{IIII}"Unserializable"
{III})
{II})
{I}) {{
{II}// NOTE (mristin):
{II}// Unlike other SDKs, we can not be really sure what additional properties
{II}// JavaScript might bring about. Therefore, we leave out the tests with
{II}// the validation of additional properties.
{II}if (path.basename(causeDir) == "UnexpectedAdditionalProperty") {{
{III}continue;
{II}}}

{II}const clsDir = path.join(
{III}causeDir,
{III}{typescript_common.string_literal(cls_name_json)}
{II});
{II}if (!fs.existsSync(clsDir)) {{
{III}// NOTE (mristin):
{III}// Some classes indeed lack the invalid examples.
{III}continue;
{II}}}

{II}const pths = Array.from(
{III}TestCommon.findFilesBySuffixRecursively(
{IIII}clsDir,
{IIII}".json"
{III})
{II});
{II}pths.sort();

{II}for (const pth of pths) {{
{III}const jsonable = TestCommon.readJsonFromFileSync(pth);

{III}const instanceOrError = AasJsonization.{deserialization_function}(
{IIII}jsonable
{III});
{III}if (instanceOrError.error === null) {{
{IIII}throw new Error(`Expected a de-serialization error for ${{pth}}, but got none`);
{III}}}

{III}assertDeserializationErrorEqualsExpectedOrRecord(
{IIII}instanceOrError.error,
{IIII}pth
{III});
{II}}}
{I}}}
}});"""
                ),
                Stripped(
                    f"""\
test("{cls_name_typescript} verification fail", () => {{
{I}for (
{II}const causeDir of
{II}TestCommon.findImmediateSubdirectories(
{III}path.join(
{IIII}TestCommon.TEST_DATA_DIR,
{IIII}"Json",
{IIII}"Unexpected",
{IIII}"Invalid"
{III})
{II})
{I}) {{
{II}const clsDir = path.join(
{III}causeDir,
{III}{typescript_common.string_literal(cls_name_json)}
{II});
{II}if (!fs.existsSync(clsDir)) {{
{III}// NOTE (mristin):
{III}// Some classes indeed lack the invalid examples.
{III}continue;
{II}}}

{II}const pths = Array.from(
{III}TestCommon.findFilesBySuffixRecursively(
{IIII}clsDir,
{IIII}".json"
{III})
{II});
{II}pths.sort();

{II}for (const pth of pths) {{
{III}const jsonable = TestCommon.readJsonFromFileSync(pth);

{III}const instanceOrError = AasJsonization.{deserialization_function}(
{IIII}jsonable
{III});
{III}if (instanceOrError.error !== null) {{
{IIII}throw new Error(
{IIIII}`Expected no de-serialization error for ${{pth}}, ` +
{IIIII}`but got: ${{instanceOrError.error.message}}: ${{instanceOrError.error.path}}`
{IIII});
{III}}}

{III}const instance = instanceOrError.mustValue();

{III}const verificationErrors = Array.from(AasVerification.verify(instance));
{III}assertVerificationErrorsEqualExpectedOrRecord(
{IIII}verificationErrors,
{IIII}pth
{III});
{II}}}
{I}}}
}});"""
                ),
            ]
        )

    blocks.extend(_generate_serialization_failure_tests(symbol_table))

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
