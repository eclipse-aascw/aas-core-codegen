/**
 * Provide common functionality to be re-used across different tests
 * such as reading of commonly-used environment variables.
 */

import * as fs from "fs";
import * as path from "path";

import * as AasTypes from "../src/types";
import * as AasVerification from "../src/verification";
import * as AasJsonization from "../src/jsonization";
import { Path } from "../src/jsonization";

// NOTE (mristin):
// It is tedious to record manually all the expected error messages. Therefore we include this variable
// to steer the automatic recording. We intentionally inter-twine the recording code with the test code
// to keep them close to each other so that they are easier to maintain.
export const RECORD_MODE_ENVIRONMENT_VARIABLE_NAME =
  "DUMMY_TEST_RECORD_MODE";

const RECORD_MODE_TEXT =
  process.env[RECORD_MODE_ENVIRONMENT_VARIABLE_NAME]?.toLowerCase();
export const RECORD_MODE: boolean =
  RECORD_MODE_TEXT === "true" || RECORD_MODE_TEXT === "1" || RECORD_MODE_TEXT === "on";

export const TEST_DATA_DIR = process.env[
  "DUMMY_TEST_DATA_DIR"
];
if (TEST_DATA_DIR === null || TEST_DATA_DIR === undefined) {
  throw new Error(
    "The path to the test data directory is missing in the environment: " +
      "AAS_CORE3_0_TYPESCRIPT_TEST_DATA_DIR"
  );
}
if (!fs.existsSync(TEST_DATA_DIR)) {
  throw new Error(
    "The path read from environment variable " +
      "AAS_CORE3_0_TYPESCRIPT_TEST_DATA_DIR does not exist: " +
      TEST_DATA_DIR
  );
}
if (!fs.lstatSync(TEST_DATA_DIR).isDirectory()) {
  throw new Error(
    "The path read from environment variable " +
      "AAS_CORE3_0_TYPESCRIPT_TEST_DATA_DIR is not a directory: " +
      TEST_DATA_DIR
  );
}

/**
 * Read a JSON value from a file.
 *
 * @param aPath - to the file
 * @returns a JSON value read from the file
 */
export function readJsonFromFileSync(aPath: string): AasJsonization.JsonValue {
  const text = fs.readFileSync(aPath, "utf-8");
  let jsonable: AasJsonization.JsonValue | null = null;
  try {
    jsonable = JSON.parse(text);
  } catch (error) {
    throw new Error(`Failed to parse JSON from: ${aPath}`);
  }

  if (jsonable === null) {
    throw new Error(`Unexpected null value as JSON from: ${aPath}`);
  }

  return <AasJsonization.JsonValue>jsonable;
}

/**
 * Find the first instance beneath and including the `container` which satisfies
 * `condition`.
 *
 * @param container - where to search
 * @param condition - that needs to be fulfilled
 * @throws an {@link Error} if no instance could be found which satisfies
 * `condition`
 */
export function mustFind(
  container: AasTypes.Class,
  condition: (instance: AasTypes.Class) => boolean
) {
  if (condition(container)) {
    return container;
  }

  for (const instance of container.descend()) {
    if (condition(instance)) {
      return instance;
    }
  }

  throw new Error("No instance could be found which satisfies the condition.");
}

/**
 * Assert that there are no verification errors in the `iterable`.
 *
 * @param errors - iterable of verification errors
 * @param aPath - to the file specifying the instance
 * @throws an {@link Error} with an informative message
 */
export function assertNoVerificationErrors(
  errors: IterableIterator<AasVerification.VerificationError>,
  aPath: string
): void {
  const errorArray = errors instanceof Array ? errors : Array.from(errors);

  if (errorArray.length !== 0) {
    let message =
      "Expected no errors when verifying the instance de-serialized " +
      `from ${aPath}, but got ${errorArray.length} error(s):`;

    for (let i = 0; i < errorArray.length; i++) {
      const error = errorArray[i];

      message += `\n\nError ${i + 1}:\n${error.path}: ${error.message}`;
    }
    throw new Error(message);
  }
}

/**
 * Assert that `errors` either correspond to the errors recorded to the disk,
 * or re-record the errors, if {@link RECORD_MODE} is set.
 *
 * @param errors - iterable of verification errors on an instance
 * @param aPath - to the instance
 * @throws an {@link Error} if {@link RECORD_MODE} unset and the observed and
 * recorded errors do not coincide
 */
export function assertExpectedOrRecordedVerificationErrors(
  errors: IterableIterator<AasVerification.VerificationError>,
  aPath: string
): void {
  const errorArray = errors instanceof Array ? errors : Array.from(errors);

  if (errorArray.length === 0) {
    throw new Error(
      "Expected at least one verification error when " +
        `verifying ${path}, but got none`
    );
  }

  const got = errorArray.map((error) => `${error.path}: ${error.message}`).join(";\n");

  const errorsPath = aPath + ".errors";
  if (RECORD_MODE) {
    fs.writeFileSync(errorsPath, got, "utf-8");
  } else {
    if (!fs.existsSync(errorsPath)) {
      throw new Error(
        `The file with the recorded verification errors does not ` +
          `exist: ${errorsPath}; you probably want to set the environment ` +
          `variable ${RECORD_MODE_ENVIRONMENT_VARIABLE_NAME}?`
      );
    }

    const expected = fs.readFileSync(errorsPath, "utf-8");
    if (expected !== got) {
      throw new Error(
        `Expected verification errors from ${path}:\n` +
          `${expected}\n, but got:\n${got}`
      );
    }
  }
}

/**
 * Represent the `instance` as a human-readable line of an iteration trace.
 *
 * @param instance - to leave a mark in the trace
 * @returns the mark in the trace
 */
export function traceMark(instance: AasTypes.Class): string {
  return instance.constructor.name;
}

/**
 * Iterate over all the files beneath `directory` with the given `suffix` path.
 *
 * @param directory - to iterate through recursively
 * @param suffix - expected suffix of the file name
 */
export function* findFilesBySuffixRecursively(
  directory: string,
  suffix: string
): IterableIterator<string> {
  for (const filename of fs.readdirSync(directory)) {
    const pth = path.join(directory, filename);
    const stat = fs.lstatSync(pth);
    if (stat.isDirectory()) {
      yield* findFilesBySuffixRecursively(pth, suffix);
    } else {
      if (filename.endsWith(suffix)) {
        yield pth;
      }
    }
  }
}

/**
 * Iterate over all the immediate subdirectories `directory`.
 *
 * @param directory - to iterate through
 */
export function* findImmediateSubdirectories(
  directory: string
): IterableIterator<string> {
  for (const filename of fs.readdirSync(directory)) {
    const pth = path.join(directory, filename);
    const stat = fs.lstatSync(pth);
    if (stat.isDirectory()) {
      yield pth;
    }
  }
}

/**
 * Signal that two JSON-able structures are unequal.
 */
export class InequalityError {
  /**
   * Human-readable explanation of the error
   */
  readonly message: string;

  /**
   * Relative path to the erroneous value
   */
  readonly path: AasJsonization.Path;

  constructor(message: string, path: AasJsonization.Path | null = null) {
    this.message = message;
    this.path = path ?? new Path();
  }
}

/**
 * Check that the `expected` JSON-able structure strictly equals `got`
 * JSON-able structure.
 *
 * @param expected - JSON-able structure
 * @param got - JSON-able structure
 */
export function checkJsonablesEqual(
  expected: AasJsonization.JsonValue | null,
  got: AasJsonization.JsonValue | null
): AasJsonization.DeserializationError | null {
  if (
    expected === null ||
    typeof expected === "boolean" ||
    typeof expected === "number" ||
    typeof expected === "string"
  ) {
    if (expected !== got) {
      if (
        got === null ||
        typeof got === "boolean" ||
        typeof got === "number" ||
        typeof got === "string"
      ) {
        return new InequalityError(
          `Expected ${JSON.stringify(expected)}, ` + `but got ${JSON.stringify(got)}`
        );
      } else {
        return new InequalityError(
          `Expected ${JSON.stringify(expected)}, ` +
            `but got an instance of ${got.constructor.name}`
        );
      }
    }
  } else if (
    typeof expected === "object" &&
    typeof expected[Symbol.iterator] === "function"
  ) {
    if (typeof got !== "object") {
      return new InequalityError(
        `Expected an iterable, ` + `but got ${JSON.stringify(got)}`
      );
    }

    if (typeof got[Symbol.iterator] !== "function") {
      return new InequalityError(
        `Expected an iterable, ` + `but got an instance of ${got.constructor.name}`
      );
    }

    const expectedIt = <Iterator<AasJsonization.JsonValue>>expected[Symbol.iterator]();

    const gotIt = <Iterator<AasJsonization.JsonValue>>got[Symbol.iterator]();

    let i = 0;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const expectedResult = expectedIt.next();
      const gotResult = gotIt.next();

      if (expectedResult.done && gotResult.done) {
        break;
      }

      if (expectedResult.done && !gotResult.done) {
        return new InequalityError(
          `Expected an iterable with ${i + 1} items, ` +
            `but got an iterable with more items`
        );
      }

      if (!expectedResult.done && gotResult.done) {
        return new InequalityError(
          `Expected an iterable with more than ${i + 1} item(s), ` +
            `but got an iterable with only ${i + 1} item(s)`
        );
      }

      const expectedItem = expectedResult.value;
      const gotItem = expectedResult.value;

      const error = checkJsonablesEqual(expectedItem, gotItem);
      if (error !== null) {
        error.path.prepend(
          new AasJsonization.IndexSegment(<AasJsonization.JsonArray>expected, i)
        );
        return error;
      }

      i++;
    }
  } else if (typeof expected === "object") {
    const expectedKeys = new Set<string>(
      Object.keys(expected).filter((key) =>
        Object.prototype.hasOwnProperty.call(expected, key)
      )
    );

    const gotKeys = new Set<string>(
      Object.keys(expected).filter((key) =>
        Object.prototype.hasOwnProperty.call(got, key)
      )
    );

    for (const key of expectedKeys) {
      if (!gotKeys.has(key)) {
        return new InequalityError(
          `Expected an object with key ${JSON.stringify(key)}, ` +
            `but got an object without that key`
        );
      }
    }

    for (const key of gotKeys) {
      if (!expectedKeys.has(key)) {
        return new InequalityError(
          `Expected an object without the key ${JSON.stringify(key)}, ` +
            `but got an object with that key`
        );
      }
    }

    for (const key of expectedKeys) {
      const expectedValue = expected[key];
      const gotValue = got[key];

      const error = checkJsonablesEqual(expectedValue, gotValue);
      if (error !== null) {
        error.path.prepend(
          new AasJsonization.PropertySegment(<AasJsonization.JsonObject>expected, key)
        );
        return error;
      }
    }
  } else {
    throw new Error(`Unexpected expected value: ${expected}`);
  }

  return null;
}
