"""Generate code of common functionality."""

import io

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.typescript import (
    common as typescript_common,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate() -> str:
    """Generate code of common functionality."""
    blocks = [
        Stripped(
            """\
/**
 * Provide common functions shared among the modules.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            f"""\
/**
 * Create an iterator over the given range of numbers.
 *
 * @param start - inclusive start of the range
 * @param end - exclusive end of the range
 * @returns iterator over the range
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function *range(start: number, end: number): IterableIterator<number> {{
{I}for (let i = start; i < end; i++) {{
{II}yield i;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Retrieve the `index`-th item from the `array`.
 *
 * @remarks
 * This is a fill for `Array.prototype.at`.
 * See: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/at
 *
 * @param array - to get the element from
 * @param index - zero-based index of the `array`. Negative index counts back.
 * @returns item, or `undefined` if `index` out-of-bound
 * @typeParam T - type of the array items
 */
export function at<T>(
{I}array: Array<T>,
{I}index: number
) {{
{I}if (index < 0) {{
{II}return array[array.length + index];
{I}}} else {{
{II}return array[index];
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Check that all the values of the iterable are `true`.
 *
 * @param iterable - to iterate over
 * @returns `true` if all values in `iterable` are set
 */
export function every<T>(
{I}iterable: Iterable<T>
): boolean {{
{I}// NOTE (mristin):
{I}// We introduce this function so that we can keep the constraint verification
{I}// purely functional. Unfortunately, `every` and `some` are only available
{I}// in arrays and not in `IterableIterator`.

{I}for (const item of iterable) {{
{II}if (!item) {{
{III}return false;
{II}}}
{I}}}

{I}return true;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Check that at least one value of the iterable is `true`.
 *
 * @param iterable - to iterate over
 * @returns `true` if at least one value in `iterable` is set
 */
export function some<T>(
{I}iterable: Iterable<T>
): boolean {{
{I}// NOTE (mristin):
{I}// We introduce this function so that we can keep the constraint verification
{I}// purely functional. Unfortunately, `every` and `some` are only available
{I}// in arrays and not in `IterableIterator`.

{I}for (const item of iterable) {{
{II}if (item) {{
{III}return true;
{II}}}
{I}}}

{I}return false;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Map the items of an iterable.
 *
 * @param iterable - to be mapped
 * @param mappingFunction - to be applied on `iterable`
 * @returns mapped items of `iterable`
 * @typeParam S - type of an item of the `iterable`
 * @typeParam T - type of the transformed item of the `iterable`
 */
export function *map<S, T>(
{I}iterable: Iterable<S>,
{I}mappingFunction: (item: S) => T
): IterableIterator<T> {{
{I}// NOTE (mristin):
{I}// We introduce this function so that we can keep the constraint verification
{I}// purely functional.

{I}for (const item of iterable) {{
{II}yield mappingFunction(item);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent either a result, or an error.
 *
 * @typeParam ValueT - type of the resulting value
 * @typeParam ErrorT - type of the error
 */
export class Either<ValueT, ErrorT> {{
{I}/**
{I} * value if something successful
{I} */
{I}readonly value: ValueT | null;

{I}/**
{I} * error if something failed
{I} */
{I}readonly error: ErrorT | null;

{I}/**
{I} * Assert that value is set and return it.
{I} *
{I} * @returns {{@link value}}, or throw if `null`
{I} */
{I}mustValue(): ValueT {{
{II}if (this.value === null) {{
{III}throw new Error("Expected value to be set, but it was null");
{II}}}
{II}return this.value;
{I}}}

{I}constructor(value: ValueT | null, error: ErrorT | null) {{
{II}if (value === null && error === null) {{
{III}throw new Error("Unexpected both value and error null in an Either");
{II}}}

{II}if (value !== null && error !== null) {{
{III}throw new Error("Unexpected both value and error non-null in an Either");
{II}}}

{II}this.value = value;
{II}this.error = error;
{I}}}
}}"""
        ),
        # pylint: disable=line-too-long
        Stripped(
            f"""\
const BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const BASE64_LOOKUP = new Uint8Array(256);

// NOTE (mristin):
// Initialize to 255 so that we can detect invalid values in the input during decoding.
for (let i = 0; i < BASE64_LOOKUP.length; i++) {{
{I}BASE64_LOOKUP[i] = 255;
}}

// NOTE (mristin):
// Initialize valid values to the corresponding decoding points.
for (let i = 0; i < BASE64_CHARS.length; i++) {{
{I}BASE64_LOOKUP[BASE64_CHARS.charCodeAt(i)] = i;
}}

/**
 * Encode a byte array in base64.
 *
 * @remarks
 * We provide our own implementation so that we do not run into compatibility
 * issues with node.js, different browsers etc.
 * See:
 * https://stackoverflow.com/questions/21797299/convert-base64-string-to-arraybuffer
 *
 * @param bytes - to be encoded
 * @returns `bytes` encoded as base64 text
 */
export function base64Encode(bytes: Uint8Array): string {{
{I}// NOTE (mristin):
{I}// This implementation is vaguely based on:
{I}// https://github.com/danguer/blog-examples/blob/master/js/base64-binary.js,
{I}// https://github.com/niklasvh/base64-arraybuffer/blob/master/src/index.ts and
{I}// https://github.com/beatgammit/base64-js/blob/master/index.js.

{I}// NOTE (mristin):
{I}// We assume that string concatenation is actually *faster* than joining an array
{I}// of strings, see:
{I}// https://stackoverflow.com/questions/51185/are-javascript-strings-immutable-do-i-need-a-string-builder-in-javascript

{I}if (bytes.length === 0) {{
{II}return "";
{I}}}

{I}let encoded = '';
{I}const len = bytes.length;

{I}for (let i = 0; i < len; i += 3) {{
{II}encoded += BASE64_CHARS[bytes[i] >> 2];
{II}encoded += BASE64_CHARS[((bytes[i] & 3) << 4) | (bytes[i + 1] >> 4)];
{II}encoded += BASE64_CHARS[((bytes[i + 1] & 15) << 2) | (bytes[i + 2] >> 6)];
{II}encoded += BASE64_CHARS[bytes[i + 2] & 63];
{I}}}

{II}// NOTE (mristin):
{II}// We assume here that `substring` will be optimized for cases where we do not keep
{II}// the original reference to the string. We tested a bit with
{II}// https://www.measurethat.net/.

{I}if (len % 3 === 2) {{
{II}encoded = encoded.substring(0, encoded.length - 1) + '=';
{I}}} else if (len % 3 === 1) {{
{II}encoded = encoded.substring(0, encoded.length - 2) + '==';
{I}}} else {{
{II}// No padding is necessary.
{I}}}

{I}return encoded;
}}"""
        ),
        # pylint: enable=line-too-long
        Stripped(
            f"""\
/**
 * Decode a base64-encoded byte array.
 *
 * @remarks
 * We provide our own implementation so that we do not run into compatibility
 * issues with node.js, different browsers etc.
 * See:
 * https://stackoverflow.com/questions/21797299/convert-base64-string-to-arraybuffer
 *
 * @param text - to be decoded
 * @returns either the array or an error, if `text` is not a valid base64 encoding
 */
export function base64Decode(text: string): Either<Uint8Array, string> {{
{I}// NOTE (mristin):
{I}// This implementation is vaguely based on:
{I}// https://github.com/danguer/blog-examples/blob/master/js/base64-binary.js,
{I}// https://github.com/niklasvh/base64-arraybuffer/blob/master/src/index.ts and
{I}// https://github.com/beatgammit/base64-js/blob/master/index.js.

{I}const len = text.length;
{I}let lenWoPad = len;

{I}// NOTE (mristin):
{I}// Some implementations forget the padding, so we try to be robust and check
{I}// for the padding manually.
{I}let bytesLength = text.length * 0.75;
{I}if (text[len - 1] === '=') {{
{II}bytesLength--;
{II}lenWoPad--;
{II}if (text[len - 2] === '=') {{
{III}bytesLength--;
{III}lenWoPad--;
{II}}}
{I}}}

{I}const bytes = new Uint8Array(bytesLength);

{I}const base64LookupLen = BASE64_LOOKUP.length;

{I}let pointer = 0;

{I}for (let i = 0; i < len; i += 4) {{
{II}// NOTE (mristin):
{II}// Admittedly, this is very verbose code, but we want to be efficient, so we
{II}// opted for performance over readability here.

{II}const charCode0 = text.charCodeAt(i);
{II}if (charCode0 >= base64LookupLen) {{
{III}return new Either<Uint8Array, string>(
{IIII}null,
{IIII}"Expected a valid character from base64-encoded string, " +
{IIIII}`but got at index ${{i}}: ${{text[i]}} (code: ${{charCode0}})`
{III});
{II}}}
{II}const encoded0 = BASE64_LOOKUP[charCode0];
{II}if (encoded0 === 255) {{
{III}return new Either<Uint8Array, string>(
{IIII}null,
{IIII}"Expected a valid character from base64-encoded string, " +
{IIIII}`but got at index ${{i}}: ${{text[i]}} (code: ${{charCode0}})`
{III});
{II}}}

{II}const charCode1 = text.charCodeAt(i + 1);
{II}if (charCode1 >= base64LookupLen) {{
{III}return new Either<Uint8Array, string>(
{IIII}null,
{IIII}"Expected a valid character from base64-encoded string, " +
{IIIII}`but got at index ${{i + 1}}: ${{text[i + 1]}} (code: ${{charCode1}})`
{III});
{II}}}
{II}const encoded1 = BASE64_LOOKUP[charCode1];
{II}if (encoded1 === 255) {{
{III}return new Either<Uint8Array, string>(
{IIII}null,
{IIII}"Expected a valid character from base64-encoded string, " +
{IIIII}`but got at index ${{i + 1}}: ${{text[i + 1]}} (code: ${{charCode1}})`
{III});
{II}}}

{II}// We map padding to 65, which is the value of "A".
{II}const charCode2 = i + 2 < lenWoPad ? text.charCodeAt(i + 2) : 65;
{II}if (charCode2 >= base64LookupLen) {{
{III}return new Either<Uint8Array, string>(
{IIII}null,
{IIII}"Expected a valid character from base64-encoded string, " +
{IIIII}`but got at index ${{i + 2}}: ${{text[i + 2]}} (code: ${{charCode2}})`
{III});
{II}}}
{II}const encoded2 = BASE64_LOOKUP[charCode2];
{II}if (encoded2 === 255) {{
{III}return new Either<Uint8Array, string>(
{IIII}null,
{IIII}"Expected a valid character from base64-encoded string, " +
{IIIII}`but got at index ${{i + 2}}: ${{text[i + 2]}} (code: ${{charCode2}})`
{III});
{II}}}

{II}// We map padding to 65, which is the value of "A".
{II}const charCode3 = i + 3 < lenWoPad ? text.charCodeAt(i + 3) : 65;
{II}if (charCode3 >= base64LookupLen) {{
{III}return new Either<Uint8Array, string>(
{IIII}null,
{IIII}"Expected a valid character from base64-encoded string, " +
{IIIII}`but got at index ${{i + 3}}: ${{text[i + 3]}} (code: ${{charCode3}})`
{III});
{II}}}
{II}const encoded3 = BASE64_LOOKUP[charCode3];
{II}if (encoded3 === 255) {{
{III}return new Either<Uint8Array, string>(
{IIII}null,
{IIII}"Expected a valid character from base64-encoded string, " +
{IIIII}`but got at index ${{i + 3}}: ${{text[i + 3]}} (code: ${{charCode3}})`
{III});
{II}}}

{II}bytes[pointer] = (encoded0 << 2) | (encoded1 >> 4);
{II}pointer++;

{II}bytes[pointer] = ((encoded1 & 15) << 4) | (encoded2 >> 2);
{II}pointer++;

{II}bytes[pointer] = ((encoded2 & 3) << 6) | (encoded3 & 63);
{II}pointer++;
{I}}}

// NOTE (mristin):
// We expect Uint8Array to silently ignore writes outside of the buffer,
// but we still want to check here in case the underlying platform was flaky about it.
{I}if (bytes.length !== bytesLength) {{
{II}throw new Error(
{III}`Expected bytes to have length ${{bytesLength}}, but got ${{bytes.length}}`
{II});
{I}}}

{I}return new Either<Uint8Array, string>(bytes, null);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Encode a byte array in base64url.
 *
 * This encoding differs from base64 in so far that the characters `+` and `/` are
 * replaced with `-` and `_` and the padding (`=`) is removed, so that the encoded
 * value can be inserted into URIs without escaping.
 *
 * See RFC 4648 for more details:
 * https://www.rfc-editor.org/rfc/rfc4648#section-5
 *
 * @param bytes - to be encoded
 * @returns `bytes` encoded as base64url text
 */
export function base64UrlEncode(bytes: Uint8Array): string {{
{I}return base64Encode(bytes)
{II}.replace(
{III}/[+/=]/g,
{III}m =>
{IIII}m === '+'  ? '-' :
{IIII}m === '/'  ? '_' :
{IIII}'' // The padding `=` is removed.
{II});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Decode a base64url-encoded byte array.
 *
 * This encoding differs from base64 in so far that the characters `+` and `/` are
 * replaced with `-` and `_` and the padding (`=`) is removed, so that the encoded
 * value can be inserted into URIs without escaping.
 *
 * @param text - to be decoded
 * @returns either the array or an error, if `text` is not a valid base64url encoding
 */
export function base64UrlDecode(text: string): Either<Uint8Array, string> {{
{I}let base64Text = text.replace(/[-_]/g, m => m === '-' ? '+' : '/');
{I}const pad = base64Text.length % 4;
{I}if (pad > 0) {{
{II}base64Text += '='.repeat(4 - pad);
{I}}}

{I}return base64Decode(base64Text);
}}"""
        ),
        typescript_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
