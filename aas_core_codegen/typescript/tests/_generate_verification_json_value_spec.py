"""Generate code for the tests of the verification of a JSON-able value."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import common as typescript_common
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
def generate() -> str:
    """Generate code for the tests of the verification of a JSON-able value."""
    blocks = [
        Stripped(
            """\
/**
 * Test the verification of a JSON-able value in isolation.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasTypes from "../src/types";
import * as AasVerification from "../src/verification";"""
        ),
        Stripped(
            f"""\
/**
 * Collect the path and the message of every error of `errors`.
 */
function pathsAndMessages(
{I}errors: IterableIterator<AasVerification.VerificationError>
): Array<[string, string]> {{
{I}const result = new Array<[string, string]>();
{I}for (const error of errors) {{
{II}result.push([error.path.toString(), error.message]);
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
test("a deeply nested value is JSON-able", () => {{
{I}const value: AasTypes.JsonValue = {{
{II}a: [1, 1.5, "x", true, [2], {{ b: "text" }}],
{II}c: {{ d: {{ e: [] }} }}
{I}}};

{I}expect(pathsAndMessages(AasVerification.verifyJsonValue(value))).toStrictEqual(
{II}[]
{I});
}});"""
        ),
        Stripped(
            f"""\
test("the walk of a JSON-able value is depth first", () => {{
{I}// NOTE (mristin):
{I}// A breadth-first walk would report the shallow `["z"]` before the deeper
{I}// `["a"]["deep"]`, although the latter comes first in the value.
{I}const value: AasTypes.JsonValue = {{
{II}a: {{ deep: Number.NaN }},
{II}z: Number.POSITIVE_INFINITY
{I}}};

{I}const paths = pathsAndMessages(AasVerification.verifyJsonValue(value)).map(
{II}([path]) => path
{I});

{I}expect(paths).toStrictEqual(['["a"]["deep"]', '["z"]']);
}});"""
        ),
        Stripped(
            f"""\
test("an index and a key render as a subscript", () => {{
{I}const value: AasTypes.JsonValue = {{ "a b": [0, {{ "c'd": Number.NaN }}] }};

{I}const pathsAndCauses = pathsAndMessages(
{II}AasVerification.verifyJsonValue(value)
{I});

{I}expect(pathsAndCauses.length).toStrictEqual(1);
{I}expect(pathsAndCauses[0][0]).toStrictEqual('["a b"][1]["c\\'d"]');
}});"""
        ),
        Stripped(
            f"""\
test("the segments of a JSON-able path carry their container", () => {{
{I}const inner = {{ deep: Number.NaN }};
{I}const value: AasTypes.JsonValue = {{ a: inner }};

{I}const errors = Array.from(AasVerification.verifyJsonValue(value));
{I}expect(errors.length).toStrictEqual(1);

{I}const segments = errors[0].path.segments;
{I}expect(segments.length).toStrictEqual(2);

{I}const outer = segments[0];
{I}expect(outer).toBeInstanceOf(AasVerification.KeySegment);
{I}expect((outer as AasVerification.KeySegment).object).toBe(value);
{I}expect((outer as AasVerification.KeySegment).key).toStrictEqual("a");

{I}const nested = segments[1];
{I}expect(nested).toBeInstanceOf(AasVerification.KeySegment);
{I}expect((nested as AasVerification.KeySegment).object).toBe(inner);
{I}expect((nested as AasVerification.KeySegment).key).toStrictEqual("deep");
}});"""
        ),
        Stripped(
            f"""\
test("neither an infinity nor a not-a-number is JSON-able", () => {{
{I}for (const number of [
{II}Number.POSITIVE_INFINITY,
{II}Number.NEGATIVE_INFINITY,
{II}Number.NaN
{I}]) {{
{II}const pathsAndCauses = pathsAndMessages(
{III}AasVerification.verifyJsonValue([number])
{II});

{II}expect(pathsAndCauses.length).toStrictEqual(1);
{II}expect(pathsAndCauses[0][0]).toStrictEqual("[0]");
{II}expect(pathsAndCauses[0][1]).toContain(
{III}"neither finite nor representable in JSON"
{II});
{I}}}
}});"""
        ),
        Stripped(
            f"""\
test("a value of an unexpected type is refused", () => {{
{I}// NOTE (mristin):
{I}// `JsonValue` rules a function out, but a JavaScript caller can hand one
{I}// over all the same, which is the very reason this verification exists.
{I}const value = {{ a: () => 1 }} as unknown as AasTypes.JsonValue;

{I}const pathsAndCauses = pathsAndMessages(
{II}AasVerification.verifyJsonValue(value)
{I});

{I}expect(pathsAndCauses.length).toStrictEqual(1);
{I}expect(pathsAndCauses[0][0]).toStrictEqual('["a"]');
{I}expect(pathsAndCauses[0][1]).toContain("but got: function");
}});"""
        ),
        Stripped(
            f"""\
test("a null is refused at any depth", () => {{
{I}const value = {{ a: [null] }} as unknown as AasTypes.JsonValue;

{I}const pathsAndCauses = pathsAndMessages(
{II}AasVerification.verifyJsonValue(value)
{I});

{I}expect(pathsAndCauses.length).toStrictEqual(1);
{I}expect(pathsAndCauses[0][0]).toStrictEqual('["a"][0]');
{I}expect(pathsAndCauses[0][1]).toContain("but got: null");
}});"""
        ),
        Stripped(
            f"""\
test("a JSON-able array has to be an array", () => {{
{I}const value = {{ a: 1 }} as unknown as AasTypes.JsonArray;

{I}const pathsAndCauses = pathsAndMessages(
{II}AasVerification.verifyJsonArray(value)
{I});

{I}expect(pathsAndCauses.length).toStrictEqual(1);
{I}expect(pathsAndCauses[0][0]).toStrictEqual("");
{I}expect(pathsAndCauses[0][1]).toContain("Expected a JSON-able array");
}});"""
        ),
        Stripped(
            f"""\
test("a JSON-able object has to be an object", () => {{
{I}const value = [1, 2] as unknown as AasTypes.JsonObject;

{I}const pathsAndCauses = pathsAndMessages(
{II}AasVerification.verifyJsonObject(value)
{I});

{I}expect(pathsAndCauses.length).toStrictEqual(1);
{I}expect(pathsAndCauses[0][0]).toStrictEqual("");
{I}expect(pathsAndCauses[0][1]).toContain("Expected a JSON-able object");
}});"""
        ),
        Stripped(
            f"""\
test("the content is verified beneath the shape", () => {{
{I}const value: AasTypes.JsonObject = {{ a: [{{ b: Number.NaN }}] }};

{I}const pathsAndCauses = pathsAndMessages(
{II}AasVerification.verifyJsonObject(value)
{I});

{I}expect(pathsAndCauses.length).toStrictEqual(1);
{I}expect(pathsAndCauses[0][0]).toStrictEqual('["a"][0]["b"]');
}});"""
        ),
        typescript_common.WARNING,
    ]  # type: List[Stripped]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
