/**
 * Test base64url encoding and decoding.
 */

import * as AasCommon from "../src/common";

function testBase64UrlEncodeDecode(text: string, expectedEncoded: string): void {
  const bytes = Uint8Array.from(text.split("").map((c) => c.charCodeAt(0)));

  const encoded = AasCommon.base64UrlEncode(bytes);
  expect(encoded).toEqual(expectedEncoded);

  const decodedOrError: AasCommon.Either<Uint8Array, string> =
    AasCommon.base64UrlDecode(encoded);

  expect(decodedOrError.error).toBeNull();
  expect(decodedOrError.mustValue()).toEqual(bytes);
}

test("empty string", () => {
  testBase64UrlEncodeDecode("", "");
});

test("'f' is encoded 'Zg'", () => {
  testBase64UrlEncodeDecode("f", "Zg");
});

test("'fo' is encoded 'Zm8'", () => {
  testBase64UrlEncodeDecode("fo", "Zm8");
});

test("'foo' is encoded 'Zm9v'", () => {
  testBase64UrlEncodeDecode("foo", "Zm9v");
});

test("'foob' is encoded 'Zm9vYg'", () => {
  testBase64UrlEncodeDecode("foob", "Zm9vYg");
});

test("'fooba' is encoded 'Zm9vYmE'", () => {
  testBase64UrlEncodeDecode("fooba", "Zm9vYmE");
});

test("'foobar' is encoded 'Zm9vYmFy'", () => {
  testBase64UrlEncodeDecode("foobar", "Zm9vYmFy");
});

test("RFC 4648 test vectors", () => {
  const testVectors: Array<[string, string]> = [
    ["", ""],
    ["f", "Zg"],
    ["fo", "Zm8"],
    ["foo", "Zm9v"],
    ["foob", "Zm9vYg"],
    ["fooba", "Zm9vYmE"],
    ["foobar", "Zm9vYmFy"]
  ];

  for (const [input, expected] of testVectors) {
    testBase64UrlEncodeDecode(input, expected);
  }
});

test("characters that differ from base64", () => {
  const bytes = new Uint8Array([0x3e, 0x3f, 0xfc, 0xff]);

  const base64 = AasCommon.base64Encode(bytes);
  const base64url = AasCommon.base64UrlEncode(bytes);

  expect(base64).toEqual("Pj/8/w==");
  expect(base64url).toEqual("Pj_8_w");
  expect(base64url).not.toContain("+");
  expect(base64url).not.toContain("/");
  expect(base64url).not.toContain("=");
});

test("decode with missing padding", () => {
  const testCases = ["Zg", "Zm8", "Zm9vYg", "Zm9vYmE"];

  for (const encoded of testCases) {
    const decodedOrError = AasCommon.base64UrlDecode(encoded);
    expect(decodedOrError.error).toBeNull();
  }
});

test("decode URL-safe characters", () => {
  const encoded = "Pj_8_w";
  const decodedOrError = AasCommon.base64UrlDecode(encoded);

  expect(decodedOrError.error).toBeNull();
  expect(decodedOrError.mustValue()).toEqual(new Uint8Array([0x3e, 0x3f, 0xfc, 0xff]));
});

test("round-trip with binary data", () => {
  const bytes = new Uint8Array(256);
  for (let i = 0; i < 256; i++) {
    bytes[i] = i;
  }

  const encoded = AasCommon.base64UrlEncode(bytes);
  const decodedOrError = AasCommon.base64UrlDecode(encoded);

  expect(decodedOrError.error).toBeNull();
  expect(decodedOrError.mustValue()).toEqual(bytes);
  expect(encoded).not.toContain("+");
  expect(encoded).not.toContain("/");
  expect(encoded).not.toContain("=");
});

test("specific byte sequences that produce URL-unsafe characters", () => {
  const testCases: Array<[number[], string]> = [
    [[62], "Pg"],
    [[63], "Pw"],
    [[250], "-g"], // Base64 would start with `+`
    [[251], "-w"],
    [[252], "_A"], // Base64 would start with `/`
    [[253], "_Q"],
    [[254], "_g"],
    [[255], "_w"],
    [[62, 63], "Pj8"],
    [[252, 253], "_P0"],
    [[254, 255], "_v8"]
  ];

  for (const [numberArray, expectedEncoded] of testCases) {
    const bytes = new Uint8Array(numberArray);
    const encoded = AasCommon.base64UrlEncode(bytes);

    expect(encoded).toEqual(expectedEncoded);

    const decodedOrError = AasCommon.base64UrlDecode(encoded);
    expect(decodedOrError.error).toBeNull();
    expect(decodedOrError.mustValue()).toEqual(bytes);
  }
});

test("invalid characters in input", () => {
  const invalidInputs = ["Zm9v+", "Zm9v/", "Zm9v=", "Zm9v YmFy", "Zm9v\n", "Zm9v\t"];

  for (const invalid of invalidInputs) {
    const decodedOrError = AasCommon.base64UrlDecode(invalid);
    expect(decodedOrError.error).not.toBeNull();
    expect(decodedOrError.value).toBeNull();
  }
});
