"""Generate the unit tests for Base64-URL functions."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
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
def generate() -> str:
    """Generate the unit tests for Base64-URL functions."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test base64url encoding and decoding.
 */"""
        ),
        Stripped(
            """\
import * as OurCommon from "../src/common";"""
        ),
        Stripped(
            f"""\
function testBase64UrlEncodeDecode(text: string, expectedEncoded: string): void {{
{I}const bytes = Uint8Array.from(text.split("").map((c) => c.charCodeAt(0)));

{I}const encoded = OurCommon.base64UrlEncode(bytes);
{I}expect(encoded).toEqual(expectedEncoded);

{I}const decodedOrError: OurCommon.Either<Uint8Array, string> =
{II}OurCommon.base64UrlDecode(encoded);

{I}expect(decodedOrError.error).toBeNull();
{I}expect(decodedOrError.mustValue()).toEqual(bytes);
}}"""
        ),
        Stripped(
            f"""\
test("empty string", () => {{
{I}testBase64UrlEncodeDecode("", "");
}});"""
        ),
        Stripped(
            f"""\
test("'f' is encoded 'Zg'", () => {{
{I}testBase64UrlEncodeDecode("f", "Zg");
}});"""
        ),
        Stripped(
            f"""\
test("'fo' is encoded 'Zm8'", () => {{
{I}testBase64UrlEncodeDecode("fo", "Zm8");
}});"""
        ),
        Stripped(
            f"""\
test("'foo' is encoded 'Zm9v'", () => {{
{I}testBase64UrlEncodeDecode("foo", "Zm9v");
}});"""
        ),
        Stripped(
            f"""\
test("'foob' is encoded 'Zm9vYg'", () => {{
{I}testBase64UrlEncodeDecode("foob", "Zm9vYg");
}});"""
        ),
        Stripped(
            f"""\
test("'fooba' is encoded 'Zm9vYmE'", () => {{
{I}testBase64UrlEncodeDecode("fooba", "Zm9vYmE");
}});"""
        ),
        Stripped(
            f"""\
test("'foobar' is encoded 'Zm9vYmFy'", () => {{
{I}testBase64UrlEncodeDecode("foobar", "Zm9vYmFy");
}});"""
        ),
        Stripped(
            f"""\
test("RFC 4648 test vectors", () => {{
{I}const testVectors: Array<[string, string]> = [
{II}["", ""],
{II}["f", "Zg"],
{II}["fo", "Zm8"],
{II}["foo", "Zm9v"],
{II}["foob", "Zm9vYg"],
{II}["fooba", "Zm9vYmE"],
{II}["foobar", "Zm9vYmFy"]
{I}];

{I}for (const [input, expected] of testVectors) {{
{II}testBase64UrlEncodeDecode(input, expected);
{I}}}
}});"""
        ),
        Stripped(
            f"""\
test("characters that differ from base64", () => {{
{I}const bytes = new Uint8Array([0x3e, 0x3f, 0xfc, 0xff]);

{I}const base64 = OurCommon.base64Encode(bytes);
{I}const base64url = OurCommon.base64UrlEncode(bytes);

{I}expect(base64).toEqual("Pj/8/w==");
{I}expect(base64url).toEqual("Pj_8_w");
{I}expect(base64url).not.toContain("+");
{I}expect(base64url).not.toContain("/");
{I}expect(base64url).not.toContain("=");
}});"""
        ),
        Stripped(
            f"""\
test("decode with missing padding", () => {{
{I}const testCases = ["Zg", "Zm8", "Zm9vYg", "Zm9vYmE"];

{I}for (const encoded of testCases) {{
{II}const decodedOrError = OurCommon.base64UrlDecode(encoded);
{II}expect(decodedOrError.error).toBeNull();
{I}}}
}});"""
        ),
        Stripped(
            f"""\
test("decode URL-safe characters", () => {{
{I}const encoded = "Pj_8_w";
{I}const decodedOrError = OurCommon.base64UrlDecode(encoded);

{I}expect(decodedOrError.error).toBeNull();
{I}expect(decodedOrError.mustValue()).toEqual(new Uint8Array([0x3e, 0x3f, 0xfc, 0xff]));
}});"""
        ),
        Stripped(
            f"""\
test("round-trip with binary data", () => {{
{I}const bytes = new Uint8Array(256);
{I}for (let i = 0; i < 256; i++) {{
{II}bytes[i] = i;
{I}}}

{I}const encoded = OurCommon.base64UrlEncode(bytes);
{I}const decodedOrError = OurCommon.base64UrlDecode(encoded);

{I}expect(decodedOrError.error).toBeNull();
{I}expect(decodedOrError.mustValue()).toEqual(bytes);
{I}expect(encoded).not.toContain("+");
{I}expect(encoded).not.toContain("/");
{I}expect(encoded).not.toContain("=");
}});"""
        ),
        Stripped(
            f"""\
test("specific byte sequences that produce URL-unsafe characters", () => {{
{I}const testCases: Array<[number[], string]> = [
{II}[[62], "Pg"],
{II}[[63], "Pw"],
{II}[[250], "-g"], // Base64 would start with `+`
{II}[[251], "-w"],
{II}[[252], "_A"], // Base64 would start with `/`
{II}[[253], "_Q"],
{II}[[254], "_g"],
{II}[[255], "_w"],
{II}[[62, 63], "Pj8"],
{II}[[252, 253], "_P0"],
{II}[[254, 255], "_v8"]
{I}];

{I}for (const [numberArray, expectedEncoded] of testCases) {{
{II}const bytes = new Uint8Array(numberArray);
{II}const encoded = OurCommon.base64UrlEncode(bytes);

{II}expect(encoded).toEqual(expectedEncoded);

{II}const decodedOrError = OurCommon.base64UrlDecode(encoded);
{II}expect(decodedOrError.error).toBeNull();
{II}expect(decodedOrError.mustValue()).toEqual(bytes);
{I}}}
}});"""
        ),
        Stripped(
            f"""\
test("invalid characters in input", () => {{
{I}const invalidInputs = ["Zm9v+", "Zm9v/", "Zm9v=", "Zm9v YmFy", "Zm9v\\n", "Zm9v\\t"];

{I}for (const invalid of invalidInputs) {{
{II}const decodedOrError = OurCommon.base64UrlDecode(invalid);
{II}expect(decodedOrError.error).not.toBeNull();
{II}expect(decodedOrError.value).toBeNull();
{I}}}
}});"""
        ),
    ]
    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
