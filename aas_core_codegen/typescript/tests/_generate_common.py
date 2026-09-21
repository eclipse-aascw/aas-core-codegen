"""Generate code for common functionality shared across the tests."""

import io
from typing import List, Optional, Tuple

from icontract import ensure

from aas_core_codegen import specific_implementations
from aas_core_codegen.common import Stripped, Error
from aas_core_codegen.typescript import common as typescript_common
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


# fmt: off
@ensure(
    lambda result: not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for common functionality shared across the tests."""
    package_identifier_key = specific_implementations.ImplementationKey(
        "package_identifier.txt"
    )

    package_identifier = spec_impls.get(package_identifier_key, None)
    if package_identifier is None:
        return None, [
            Error(
                None,
                f"The package identifier snippet is missing "
                f"in the specific implementations: {package_identifier_key}",
            )
        ]

    assert package_identifier is not None

    environment_variable_prefix = typescript_common.environment_variable_prefix(
        package_identifier
    )

    blocks = [
        Stripped(
            """\
/**
 * Provide common functionality to be re-used across different tests
 * such as reading of commonly-used environment variables.
 */"""
        ),
        Stripped(
            """\
import * as fs from "fs";
import * as path from "path";"""
        ),
        Stripped(
            """\
import * as AasTypes from "../src/types";
import * as AasVerification from "../src/verification";
import * as AasJsonization from "../src/jsonization";
import { Path } from "../src/jsonization";"""
        ),
        Stripped(
            f"""\
// NOTE (mristin):
// It is tedious to record manually all the expected error messages. Therefore we include this variable
// to steer the automatic recording. We intentionally inter-twine the recording code with the test code
// to keep them close to each other so that they are easier to maintain.
export const RECORD_MODE_ENVIRONMENT_VARIABLE_NAME =
{I}"{environment_variable_prefix}_TEST_RECORD_MODE";"""
        ),
        Stripped(
            f"""\
const RECORD_MODE_TEXT =
{I}process.env[RECORD_MODE_ENVIRONMENT_VARIABLE_NAME]?.toLowerCase();
export const RECORD_MODE: boolean =
{I}RECORD_MODE_TEXT === "true" || RECORD_MODE_TEXT === "1" || RECORD_MODE_TEXT === "on";"""
        ),
        Stripped(
            f"""\
export const TEST_DATA_DIR = process.env[
{I}"{environment_variable_prefix}_TEST_DATA_DIR"
];
if (TEST_DATA_DIR === null || TEST_DATA_DIR === undefined) {{
{I}throw new Error(
{II}"The path to the test data directory is missing in the environment: " +
{III}"{environment_variable_prefix}_TEST_DATA_DIR"
{I});
}}
if (!fs.existsSync(TEST_DATA_DIR)) {{
{I}throw new Error(
{II}"The path read from environment variable " +
{III}"{environment_variable_prefix}_TEST_DATA_DIR does not exist: " +
{III}TEST_DATA_DIR
{I});
}}
if (!fs.lstatSync(TEST_DATA_DIR).isDirectory()) {{
{I}throw new Error(
{II}"The path read from environment variable " +
{III}"{environment_variable_prefix}_TEST_DATA_DIR is not a directory: " +
{III}TEST_DATA_DIR
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read a JSON value from a file.
 *
 * @param aPath - to the file
 * @returns a JSON value read from the file
 */
export function readJsonFromFileSync(aPath: string): AasJsonization.JsonValue {{
{I}const text = fs.readFileSync(aPath, "utf-8");
{I}let jsonable: AasJsonization.JsonValue | null = null;
{I}try {{
{II}jsonable = JSON.parse(text);
{I}}} catch (error) {{
{II}throw new Error(`Failed to parse JSON from: ${{aPath}}`);
{I}}}

{I}if (jsonable === null) {{
{II}throw new Error(`Unexpected null value as JSON from: ${{aPath}}`);
{I}}}

{I}return <AasJsonization.JsonValue>jsonable;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Find the first instance beneath and including the `container` which satisfies
 * `condition`.
 *
 * @param container - where to search
 * @param condition - that needs to be fulfilled
 * @throws an {{@link Error}} if no instance could be found which satisfies
 * `condition`
 */
export function mustFind(
{I}container: AasTypes.Class,
{I}condition: (instance: AasTypes.Class) => boolean
) {{
{I}if (condition(container)) {{
{II}return container;
{I}}}

{I}for (const instance of container.descend()) {{
{II}if (condition(instance)) {{
{III}return instance;
{II}}}
{I}}}

{I}throw new Error("No instance could be found which satisfies the condition.");
}}"""
        ),
        Stripped(
            f"""\
/**
 * Assert that there are no verification errors in the `iterable`.
 *
 * @param errors - iterable of verification errors
 * @param aPath - to the file specifying the instance
 * @throws an {{@link Error}} with an informative message
 */
export function assertNoVerificationErrors(
{I}errors: IterableIterator<AasVerification.VerificationError>,
{I}aPath: string
): void {{
{I}const errorArray = errors instanceof Array ? errors : Array.from(errors);

{I}if (errorArray.length !== 0) {{
{II}let message =
{III}"Expected no errors when verifying the instance de-serialized " +
{III}`from ${{aPath}}, but got ${{errorArray.length}} error(s):`;

{II}for (let i = 0; i < errorArray.length; i++) {{
{III}const error = errorArray[i];

{III}message += `\\n\\nError ${{i + 1}}:\\n${{error.path}}: ${{error.message}}`;
{II}}}
{II}throw new Error(message);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Assert that `errors` either correspond to the errors recorded to the disk,
 * or re-record the errors, if {{@link RECORD_MODE}} is set.
 *
 * @param errors - iterable of verification errors on an instance
 * @param aPath - to the instance
 * @throws an {{@link Error}} if {{@link RECORD_MODE}} unset and the observed and
 * recorded errors do not coincide
 */
export function assertExpectedOrRecordedVerificationErrors(
{I}errors: IterableIterator<AasVerification.VerificationError>,
{I}aPath: string
): void {{
{I}const errorArray = errors instanceof Array ? errors : Array.from(errors);

{I}if (errorArray.length === 0) {{
{II}throw new Error(
{III}"Expected at least one verification error when " +
{IIII}`verifying ${{path}}, but got none`
{II});
{I}}}

{I}const got = errorArray.map((error) => `${{error.path}}: ${{error.message}}`).join(";\\n");

{I}const errorsPath = aPath + ".errors";
{I}if (RECORD_MODE) {{
{II}fs.writeFileSync(errorsPath, got, "utf-8");
{I}}} else {{
{II}if (!fs.existsSync(errorsPath)) {{
{III}throw new Error(
{IIII}`The file with the recorded verification errors does not ` +
{IIIII}`exist: ${{errorsPath}}; you probably want to set the environment ` +
{IIIII}`variable ${{RECORD_MODE_ENVIRONMENT_VARIABLE_NAME}}?`
{III});
{II}}}

{II}const expected = fs.readFileSync(errorsPath, "utf-8");
{II}if (expected !== got) {{
{III}throw new Error(
{IIII}`Expected verification errors from ${{path}}:\\n` +
{IIIII}`${{expected}}\\n, but got:\\n${{got}}`
{III});
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent the `instance` as a human-readable line of an iteration trace.
 *
 * @param instance - to leave a mark in the trace
 * @returns the mark in the trace
 */
export function traceMark(instance: AasTypes.Class): string {{
{I}return instance.constructor.name;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Iterate over all the files beneath `directory` with the given `suffix` path.
 *
 * @param directory - to iterate through recursively
 * @param suffix - expected suffix of the file name
 */
export function* findFilesBySuffixRecursively(
{I}directory: string,
{I}suffix: string
): IterableIterator<string> {{
{I}for (const filename of fs.readdirSync(directory)) {{
{II}const pth = path.join(directory, filename);
{II}const stat = fs.lstatSync(pth);
{II}if (stat.isDirectory()) {{
{III}yield* findFilesBySuffixRecursively(pth, suffix);
{II}}} else {{
{III}if (filename.endsWith(suffix)) {{
{IIII}yield pth;
{III}}}
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Iterate over all the immediate subdirectories `directory`.
 *
 * @param directory - to iterate through
 */
export function* findImmediateSubdirectories(
{I}directory: string
): IterableIterator<string> {{
{I}for (const filename of fs.readdirSync(directory)) {{
{II}const pth = path.join(directory, filename);
{II}const stat = fs.lstatSync(pth);
{II}if (stat.isDirectory()) {{
{III}yield pth;
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Signal that two JSON-able structures are unequal.
 */
export class InequalityError {{
{I}/**
{I} * Human-readable explanation of the error
{I} */
{I}readonly message: string;

{I}/**
{I} * Relative path to the erroneous value
{I} */
{I}readonly path: AasJsonization.Path;

{I}constructor(message: string, path: AasJsonization.Path | null = null) {{
{II}this.message = message;
{II}this.path = path ?? new Path();
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Check that the `expected` JSON-able structure strictly equals `got`
 * JSON-able structure.
 *
 * @param expected - JSON-able structure
 * @param got - JSON-able structure
 */
export function checkJsonablesEqual(
{I}expected: AasJsonization.JsonValue | null,
{I}got: AasJsonization.JsonValue | null
): AasJsonization.DeserializationError | null {{
{I}if (
{II}expected === null ||
{II}typeof expected === "boolean" ||
{II}typeof expected === "number" ||
{II}typeof expected === "string"
{I}) {{
{II}if (expected !== got) {{
{III}if (
{IIII}got === null ||
{IIII}typeof got === "boolean" ||
{IIII}typeof got === "number" ||
{IIII}typeof got === "string"
{III}) {{
{IIII}return new InequalityError(
{IIIII}`Expected ${{JSON.stringify(expected)}}, ` + `but got ${{JSON.stringify(got)}}`
{IIII});
{III}}} else {{
{IIII}return new InequalityError(
{IIIII}`Expected ${{JSON.stringify(expected)}}, ` +
{IIIIII}`but got an instance of ${{got.constructor.name}}`
{IIII});
{III}}}
{II}}}
{I}}} else if (
{II}typeof expected === "object" &&
{II}typeof expected[Symbol.iterator] === "function"
{I}) {{
{II}if (typeof got !== "object") {{
{III}return new InequalityError(
{IIII}`Expected an iterable, ` + `but got ${{JSON.stringify(got)}}`
{III});
{II}}}

{II}if (typeof got[Symbol.iterator] !== "function") {{
{III}return new InequalityError(
{IIII}`Expected an iterable, ` + `but got an instance of ${{got.constructor.name}}`
{III});
{II}}}

{II}const expectedIt = <Iterator<AasJsonization.JsonValue>>expected[Symbol.iterator]();

{II}const gotIt = <Iterator<AasJsonization.JsonValue>>got[Symbol.iterator]();

{II}let i = 0;
{II}// eslint-disable-next-line no-constant-condition
{II}while (true) {{
{III}const expectedResult = expectedIt.next();
{III}const gotResult = gotIt.next();

{III}if (expectedResult.done && gotResult.done) {{
{IIII}break;
{III}}}

{III}if (expectedResult.done && !gotResult.done) {{
{IIII}return new InequalityError(
{IIIII}`Expected an iterable with ${{i + 1}} items, ` +
{IIIIII}`but got an iterable with more items`
{IIII});
{III}}}

{III}if (!expectedResult.done && gotResult.done) {{
{IIII}return new InequalityError(
{IIIII}`Expected an iterable with more than ${{i + 1}} item(s), ` +
{IIIIII}`but got an iterable with only ${{i + 1}} item(s)`
{IIII});
{III}}}

{III}const expectedItem = expectedResult.value;
{III}const gotItem = expectedResult.value;

{III}const error = checkJsonablesEqual(expectedItem, gotItem);
{III}if (error !== null) {{
{IIII}error.path.prepend(
{IIIII}new AasJsonization.IndexSegment(<AasJsonization.JsonArray>expected, i)
{IIII});
{IIII}return error;
{III}}}

{III}i++;
{II}}}
{I}}} else if (typeof expected === "object") {{
{II}const expectedKeys = new Set<string>(
{III}Object.keys(expected).filter((key) =>
{IIII}Object.prototype.hasOwnProperty.call(expected, key)
{III})
{II});

{II}const gotKeys = new Set<string>(
{III}Object.keys(expected).filter((key) =>
{IIII}Object.prototype.hasOwnProperty.call(got, key)
{III})
{II});

{II}for (const key of expectedKeys) {{
{III}if (!gotKeys.has(key)) {{
{IIII}return new InequalityError(
{IIIII}`Expected an object with key ${{JSON.stringify(key)}}, ` +
{IIIIII}`but got an object without that key`
{IIII});
{III}}}
{II}}}

{II}for (const key of gotKeys) {{
{III}if (!expectedKeys.has(key)) {{
{IIII}return new InequalityError(
{IIIII}`Expected an object without the key ${{JSON.stringify(key)}}, ` +
{IIIIII}`but got an object with that key`
{IIII});
{III}}}
{II}}}

{II}for (const key of expectedKeys) {{
{III}const expectedValue = expected[key];
{III}const gotValue = got[key];

{III}const error = checkJsonablesEqual(expectedValue, gotValue);
{III}if (error !== null) {{
{IIII}error.path.prepend(
{IIIII}new AasJsonization.PropertySegment(<AasJsonization.JsonObject>expected, key)
{IIII});
{IIII}return error;
{III}}}
{II}}}
{I}}} else {{
{II}throw new Error(`Unexpected expected value: ${{expected}}`);
{I}}}

{I}return null;
}}"""
        ),
    ]  # type: List[Stripped]
    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
