"""Generate the unit tests for Base64 functions."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
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
def generate() -> str:
    """Generate the unit tests for Base64 functions."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test base64 encoding and decoding.
 */"""
        ),
        Stripped(
            """\
import * as OurCommon from "../src/common";"""
        ),
        Stripped(
            f"""\
function testEncodeDecode(text: string, expectedEncoded: string): void {{
{I}const bytes = Uint8Array.from(text.split("").map((c) => c.charCodeAt(0)));

{I}const encoded = OurCommon.base64Encode(bytes);
{I}expect(encoded).toEqual(expectedEncoded);

{I}const decodedOrError: OurCommon.Either<Uint8Array, string> =
{II}OurCommon.base64Decode(encoded);

{I}expect(decodedOrError.error).toBeNull();
{I}expect(decodedOrError.mustValue()).toEqual(bytes);
}}"""
        ),
        Stripped(
            """\
// NOTE (mristin):
// The following tests come from:
// https://www.rfc-editor.org/rfc/rfc4648#section-10"""
        ),
        Stripped(
            f"""\
test("empty", () => {{
{I}testEncodeDecode("", "");
}});"""
        ),
        Stripped(
            f"""\
test("Uint8Array from 'f' is encoded 'Zg=='", () => {{
{I}testEncodeDecode("f", "Zg==");
}});"""
        ),
        Stripped(
            f"""\
test("Uint8Array from 'fo' is encoded 'Zm8='", () => {{
{I}testEncodeDecode("fo", "Zm8=");
}});"""
        ),
        Stripped(
            f"""\
test("Uint8Array from 'foo' is encoded 'Zm9v'", () => {{
{I}testEncodeDecode("foo", "Zm9v");
}});"""
        ),
        Stripped(
            f"""\
test("Uint8Array from 'foob' is encoded 'Zm9vYg=='", () => {{
{I}testEncodeDecode("foob", "Zm9vYg==");
}});"""
        ),
        Stripped(
            f"""\
test("Uint8Array from 'fooba' is encoded 'Zm9vYmE='", () => {{
{I}testEncodeDecode("fooba", "Zm9vYmE=");
}});"""
        ),
        Stripped(
            f"""\
test("Uint8Array from 'foobar' is encoded 'Zm9vYmFy'", () => {{
{I}testEncodeDecode("foobar", "Zm9vYmFy");
}});"""
        ),
        Stripped(
            f"""\
test("unexpected padding in the middle", () => {{
{I}const encoded = "Zm9vYmFy";

{I}for (let i = 0; i < encoded.length - 1; i++) {{
{II}const badEncoded =
{III}encoded.substring(0, i) + "=" + encoded.substring(i + 1, encoded.length);

{II}// Test the test
{II}expect(badEncoded.length).toEqual(encoded.length);

{II}const decodedOrError = OurCommon.base64Decode(badEncoded);
{II}expect(decodedOrError.error).toEqual(
{III}"Expected a valid character from " +
{IIII}"base64-encoded string, but got at " +
{IIII}`index ${{i}}: = (code: 61)`
{II});
{I}}}
}});"""
        ),
        Stripped(
            f"""\
test("Bytes representing an invalid UTF-8 sequence encode OK", () => {{
{I}// NOTE (mristin):
{I}// We simply add a test to make sure our implementation does not suffer from
{I}// issues raised in:
{I}// https://stackoverflow.com/questions/30106476/using-javascripts-atob-to-decode-base64-doesnt-properly-decode-utf-8-strings

{I}// From:
{I}// https://stackoverflow.com/questions/1301402/example-invalid-utf8-string
{I}const bytes = new Uint8Array([0xc3, 0x28]);

{I}// NOTE (mristin):
{I}// This encoding was obtained by Python `base64` module.
{I}const expectedEncoded = "wyg=";

{I}const encoded = OurCommon.base64Encode(bytes);
{I}expect(encoded).toEqual(expectedEncoded);

{I}const decodedOrError: OurCommon.Either<Uint8Array, string> =
{II}OurCommon.base64Decode(encoded);

{I}expect(decodedOrError.error).toBeNull();
{I}expect(decodedOrError.mustValue()).toEqual(bytes);
}});"""
        ),
        Stripped(
            """\
// NOTE (mristin):
// The following checks come from: https://eprint.iacr.org/2022/361.pdf"""
        ),
        Stripped(
            f"""\
test("'Hello' as 'SGVsbG8=' OK", () => {{
{I}testEncodeDecode("Hello", "SGVsbG8=");
}});"""
        ),
        Stripped(
            f"""\
test("our implementation suffers from padding inconsistency of 'Hello' as 'SGVsbG9='", () => {{
{I}// NOTE (mristin):
{I}// This is not a test case, but we merely document that there is a possible
{I}// attack vector where different strings encode the *same* byte sequence.

{I}const badEncoded = "SGVsbG9=";

{I}const decodedOrError = OurCommon.base64Decode(badEncoded);
{I}expect(decodedOrError.mustValue()).toEqual(
{II}new Uint8Array(
{III}// "Hello"
{III}[72, 101, 108, 108, 111]
{II})
{I});
{I}expect(decodedOrError.error).toBeNull();
}});"""
        ),
        Stripped(
            f"""\
test("table from rickkas7/Base64RK", () => {{
{I}// NOTE (mristin):
{I}// The following tests have been scraped from:
{I}// https://github.com/rickkas7/Base64RK/blob/183d20e62b96ef9b0230c80c7a172715ca6f661e/test/unit-test/unit-test.cpp

{I}const arraysExpectedEncodeds: Array<[Array<number>, string]> = [
{II}[[28], "HA=="],
{II}[[174, 208], "rtA="],
{II}[[50, 224, 208], "MuDQ"],
{II}[[45, 18, 235, 6], "LRLrBg=="],
{II}[[117, 199, 153, 221, 160], "dceZ3aA="],
{II}[[141, 12, 188, 48, 173, 45], "jQy8MK0t"],
{II}[[69, 143, 148, 125, 213, 3, 148], "RY+UfdUDlA=="],
{II}[[251, 162, 166, 60, 129, 131, 46, 13], "+6KmPIGDLg0="],
{II}[[207, 40, 204, 254, 77, 71, 61, 8, 128], "zyjM/k1HPQiA"],
{II}[[156, 150, 213, 174, 117, 59, 70, 220, 210, 63], "nJbVrnU7RtzSPw=="],
{II}[[192, 54, 173, 19, 126, 84, 26, 250, 167, 5, 50], "wDatE35UGvqnBTI="],
{II}[[20, 1, 15, 77, 224, 141, 153, 47, 186, 170, 200, 227], "FAEPTeCNmS+6qsjj"],
{II}[
{III}[85, 166, 130, 169, 193, 117, 194, 81, 238, 64, 180, 228, 127],
{III}"VaaCqcF1wlHuQLTkfw=="
{II}],
{II}[
{III}[65, 130, 145, 17, 247, 99, 158, 36, 117, 8, 192, 1, 193, 234],
{III}"QYKREfdjniR1CMABweo="
{II}],
{II}[
{III}[9, 55, 253, 179, 203, 93, 237, 58, 252, 200, 168, 145, 115, 53, 31],
{III}"CTf9s8td7Tr8yKiRczUf"
{II}],
{II}[
{III}[
{IIII}254, 76, 140, 77, 16, 52, 119, 229, 186, 225, 109, 181, 134, 34, 229, 153, 235,
{IIII}1, 16, 126, 17, 14, 13, 12, 138, 248, 230, 60, 73, 128, 116, 204, 207
{III}],
{III}"/kyMTRA0d+W64W21hiLlmesBEH4RDg0MivjmPEmAdMzP"
{II}],
{II}[
{III}[
{IIII}155, 159, 208, 168, 221, 216, 113, 8, 58, 136, 77, 93, 86, 50, 80, 91, 14, 102,
{IIII}10, 54, 2, 158, 195, 75, 40, 245, 84, 177, 116, 54, 235, 217, 124, 232, 205,
{IIII}113, 111, 33, 231, 251, 246, 136, 41, 167, 201, 234, 20, 83, 225, 67, 131, 210,
{IIII}97, 194, 1, 252, 158, 253, 84, 135, 119, 1, 254, 11, 182, 208
{III}],
{III}"m5/QqN3YcQg6iE1dVjJQWw5mCjYCnsNLKPVUsXQ269l86M1xbyHn+/aIKafJ6hRT4UOD0mHCAfye/VSHdwH+C7bQ"
{II}],
{II}[
{III}[
{IIII}101, 43, 33, 221, 108, 128, 221, 221, 52, 11, 40, 166, 120, 198, 79, 0, 141,
{IIII}127, 183, 226, 197, 232, 52, 29, 136, 1, 16, 27, 216, 71, 149, 251, 131, 94, 22,
{IIII}118, 25, 255, 214, 119, 91, 182, 203, 228, 67, 22, 88, 180, 161, 42, 182, 125,
{IIII}183, 239, 186, 216, 23, 11, 17, 144, 124, 201, 177, 3, 83, 68, 131, 249, 52,
{IIII}189, 2, 28, 74, 172, 214, 117, 126, 249, 239, 90, 22, 204, 161, 243, 232, 166,
{IIII}103, 150, 20, 240, 60, 93, 187, 67, 57, 231, 1, 102, 221, 194, 76, 162, 8, 89,
{IIII}72, 150, 146, 247, 181, 134, 242, 205, 179, 19, 155, 68, 94, 82, 214, 56, 1,
{IIII}111, 109, 78, 155, 216, 73, 7, 80, 243
{III}],
{III}"ZSsh3WyA3d00CyimeMZPAI1/t+LF6DQdiAEQG9hHlfuDXhZ2Gf/Wd1u2y+RDFli0oSq2fbfvutgXCxGQfMmxA1NEg/k0vQIcSqzWdX7571oWzKHz6KZnlhTwPF27QznnAWbdwkyiCFlIlpL3tYbyzbMTm0ReUtY4AW9tTpvYSQdQ8w=="
{II}],
{II}[
{III}[
{IIII}177, 224, 149, 210, 54, 194, 123, 141, 157, 224, 99, 1, 189, 114, 37, 230, 250,
{IIII}149, 161, 158, 138, 226, 5, 18, 131, 169, 202, 130, 46, 109, 102, 35, 113, 199,
{IIII}109, 178, 98, 137, 249, 69, 227, 130, 232, 246, 105, 101, 97, 234, 120, 151, 31,
{IIII}41, 90, 20, 15, 246, 90, 214, 39, 139, 86, 52, 78, 174, 35, 95, 63, 226, 241,
{IIII}127, 164, 219, 174, 140, 255, 17, 120, 118, 97, 131, 133, 35, 231, 117, 215, 74,
{IIII}14, 110, 70, 42, 110, 7, 37, 234, 139, 210, 224, 36, 71, 227, 68, 155, 236, 191,
{IIII}61, 83, 11, 189, 88, 60, 208, 3, 109, 121, 32, 71, 169, 58, 125, 112, 116, 16,
{IIII}153, 200, 74, 242, 89, 141, 143, 25, 211, 92, 179, 227, 223, 183, 219, 18, 54,
{IIII}208, 80, 253, 11, 76, 69, 150, 4, 48, 238, 73, 165, 25, 133, 200, 80, 207, 84,
{IIII}182, 64, 251, 156, 76, 255, 112, 227, 235, 154, 29, 191, 86, 217, 118, 219, 51,
{IIII}38, 173, 6, 111, 14, 55, 195, 13, 45, 236, 66, 180, 39, 109, 110, 7, 47, 61,
{IIII}103, 100, 117, 55, 89, 35, 64, 106, 106, 42, 238, 37, 70, 20, 8, 128, 34, 131,
{IIII}56, 120, 103, 125, 149, 182, 130, 217, 38, 102, 24, 170, 111, 47, 113, 79, 142,
{IIII}4, 167, 80, 12, 174, 102, 74, 129, 109, 204, 12, 252, 200, 95, 97, 51, 215, 169,
{IIII}148, 191, 113, 155, 228, 145, 235, 35, 252, 53, 177
{III}],
{III}"seCV0jbCe42d4GMBvXIl5vqVoZ6K4gUSg6nKgi5tZiNxx22yYon5ReOC6PZpZWHqeJcfKVoUD/Za1ieLVjROriNfP+Lxf6Tbroz/EXh2YYOFI+d110oObkYqbgcl6ovS4CRH40Sb7L89Uwu9WDzQA215IEepOn1wdBCZyEryWY2PGdNcs+Pft9sSNtBQ/QtMRZYEMO5JpRmFyFDPVLZA+5xM/3Dj65odv1bZdtszJq0Gbw43ww0t7EK0J21uBy89Z2R1N1kjQGpqKu4lRhQIgCKDOHhnfZW2gtkmZhiqby9xT44Ep1AMrmZKgW3MDPzIX2Ez16mUv3Gb5JHrI/w1sQ=="
{II}]
{I}];

{I}for (const [array, expectedEncoded] of arraysExpectedEncodeds) {{
{II}const bytes = new Uint8Array(array);

{II}const encoded = OurCommon.base64Encode(bytes);
{II}expect(encoded).toEqual(expectedEncoded);

{II}const decodedOrError: OurCommon.Either<Uint8Array, string> =
{III}OurCommon.base64Decode(encoded);

{II}expect(decodedOrError.error).toBeNull();
{II}expect(decodedOrError.mustValue()).toEqual(bytes);
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
