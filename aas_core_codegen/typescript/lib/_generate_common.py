"""Generate code of common functionality."""

import io
from typing import Final, List, Sequence

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
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


#: Helper to compute the remainder of the floored division as in Python.
#:
#: We deliberately do not transpile the modulo to the native TypeScript operator
#: ``%``. JavaScript truncates the division towards zero so that its remainder
#: takes the sign of the dividend (``-7 % 3 == -1``). The meta-model is written in
#: Python where the division is floored so that the remainder takes the sign of
#: the divisor (``-7 % 3 == 2``). The two only coincide when the operands have
#: the same sign, but the invariants must behave the same in all the SDKs for all
#: the inputs.
#:
#: Moreover, the native ``%`` gives a negative zero if the dividend is negative
#: and divisible by the divisor (``-6 % 3`` is ``-0``). Python has no negative
#: integer zero, so we normalize it to a positive zero with ``+ 0``. Otherwise,
#: ``Object.is`` and, consequently, ``toBe`` in jest, would distinguish the result
#: from ``0``.
#:
#: The numbers in TypeScript are double-precision floating-point numbers, so
#: the integers are exact only up to ``Number.MAX_SAFE_INTEGER``.
FLOOR_MOD = Stripped(
    f"""\
/**
 * Compute the remainder of the floored division of `dividend` by `divisor`.
 *
 * @remarks
 *
 * The remainder takes the sign of the divisor, as the modulo in Python,
 * in which the meta-model is written.
 *
 * We deliberately do not use the native operator `%` which truncates
 * the division towards zero so that its remainder takes the sign of
 * the dividend. For example, `-7 % 3 === -1` in TypeScript, while
 * `-7 % 3 == 2` in Python. The two only coincide when the operands have
 * the same sign, but the invariants must behave the same in all the SDKs for
 * all the inputs.
 *
 * Unlike the native operator `%`, this function never returns a negative zero.
 * For example, `-6 % 3` gives `-0` in TypeScript, while this function
 * gives `0`.
 *
 * The `divisor` must not be zero.
 *
 * The numbers in TypeScript are double-precision floating-point numbers, so
 * the result is exact only if the operands are integers within
 * `Number.MIN_SAFE_INTEGER` and `Number.MAX_SAFE_INTEGER`.
 *
 * @param dividend - left operand of the modulo
 * @param divisor - right operand of the modulo, must not be zero
 * @returns the remainder with the sign of the divisor
 */
export function floorMod(dividend: number, divisor: number): number {{
{I}const remainder = dividend % divisor;
{I}if (remainder !== 0 && (remainder < 0) !== (divisor < 0)) {{
{II}return remainder + divisor;
{I}}}

{I}// NOTE (mristin):
{I}// We add zero to turn a negative zero into a positive zero.
{I}return remainder + 0;
}}"""
)


#: Give a new set as the intersection or the difference of two sets, as in Python
SET_OPERATIONS: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * Give a new set of the items which are both in `that` and in `other`.
 */
export function setIntersection<T>(
{I}that: Set<T>,
{I}other: Set<T>
): Set<T> {{
{I}const result = new Set<T>();
{I}for (const item of that) {{
{II}if (other.has(item)) {{
{III}result.add(item);
{II}}}
{I}}}
{I}return result;
}}"""
    ),
    Stripped(
        f"""\
/**
 * Give a new set of the items which are in `that`, but not in `other`.
 */
export function setDifference<T>(
{I}that: Set<T>,
{I}other: Set<T>
): Set<T> {{
{I}const result = new Set<T>();
{I}for (const item of that) {{
{II}if (!other.has(item)) {{
{III}result.add(item);
{II}}}
{I}}}
{I}return result;
}}"""
    ),
]

#: Sort the items of the sets in the properties in the same order as all the SDKs
SET_SORTING: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * Compare `that` and `other` so that `false` comes before `true`.
 *
 * @param that - to be compared
 * @param other - to be compared against
 * @returns negative, zero or positive, as `that` is before, equal to or
 * after `other`
 */
export function compareBooleans(that: boolean, other: boolean): number {{
{I}return (that ? 1 : 0) - (other ? 1 : 0);
}}"""
    ),
    Stripped(
        f"""\
/**
 * Compare the numbers `that` and `other` numerically.
 *
 * @remarks
 * The default sort of an array compares the items as text, so that `10` would
 * come before `3`.
 *
 * @param that - to be compared
 * @param other - to be compared against
 * @returns negative, zero or positive, as `that` is before, equal to or
 * after `other`
 */
export function compareNumbers(that: number, other: number): number {{
{I}return that - other;
}}"""
    ),
]

#: Parse a text as a safe integer; this is how we transpile the built-in ``int``.
#:
#: We deliberately do not use the native ``parseInt`` or ``Number``. They accept
#: much more than the other targets, *e.g.*, the white space, ``1e3`` or ``0x10``,
#: and silently lose the precision beyond ``Number.MAX_SAFE_INTEGER``.
PARSE_SAFE_INT = Stripped(
    f"""\
/**
 * Parse `text` as a safe integer.
 *
 * @remarks
 *
 * The meta-model calls `int` on strings, and this is its transpilation.
 * We are stricter than the Python `int` so that all the SDKs behave the same.
 * We accept only an optional sign followed by the ASCII digits, and only
 * the safe integers, *i.e.*, the integers within `Number.MIN_SAFE_INTEGER` and
 * `Number.MAX_SAFE_INTEGER`, which a double-precision floating-point number
 * represents exactly.
 *
 * @param text - to be parsed
 * @returns the parsed integer
 * @throws {{@link Error}} if `text` is not a safe integer
 */
export function parseSafeInt(text: string): number {{
{I}let start = 0;
{I}if (text.length > 0 && (text[0] === "+" || text[0] === "-")) {{
{II}start = 1;
{I}}}

{I}if (start === text.length) {{
{II}throw new Error(
{III}"Expected an optional sign followed by the ASCII digits, " +
{IIII}`but got: ${{JSON.stringify(text)}}`
{II});
{I}}}

{I}let value = 0;
{I}for (let i = start; i < text.length; i++) {{
{II}const code = text.charCodeAt(i);
{II}if (code < 48 || code > 57) {{
{III}throw new Error(
{IIII}"Expected an optional sign followed by the ASCII digits, " +
{IIIII}`but got: ${{JSON.stringify(text)}}`
{III});
{II}}}

{II}const digit = code - 48;

{II}// NOTE (mristin):
{II}// We check the range before we accumulate so that the arithmetic stays
{II}// exact. The number 900719925474099 is Number.MAX_SAFE_INTEGER divided by 10,
{II}// and 1 is its last digit.
{II}if (value > 900719925474099 || (value === 900719925474099 && digit > 1)) {{
{III}throw new Error(
{IIII}"Expected a safe integer, but got a text out of its range: " +
{IIIII}JSON.stringify(text)
{III});
{II}}}

{II}value = value * 10 + digit;
{I}}}

{I}// NOTE (mristin):
{I}// We do not negate a zero so that we never return a negative zero.
{I}return text[0] === "-" && value !== 0 ? -value : value;
}}"""
)

# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> str:
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
 * Set the `index`-th item of the `array` to the `value`.
 *
 * @remarks
 * Unlike the plain assignment, we do not grow the array on an out-of-bound
 * `index`, but throw so that we follow the semantics of the meta-model.
 *
 * @param array - to set the element in
 * @param index - zero-based index of the `array`. Negative index counts back.
 * @param value - to be set
 * @throws {{@link RangeError}} if `index` out-of-bound
 * @typeParam T - type of the array items
 */
export function setAt<T>(
{I}array: Array<T>,
{I}index: number,
{I}value: T
): void {{
{I}const resolved = index < 0 ? array.length + index : index;
{I}if (resolved < 0 || resolved >= array.length) {{
{II}throw new RangeError(
{III}`The index ${{index}} is out of bound ` +
{III}`for the array of length ${{array.length}}`
{II});
{I}}}
{I}array[resolved] = value;
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

    # NOTE (mristin):
    # The TypeScript strings count the UTF-16 code units, where a character beyond
    # the Basic Multilingual Plane takes two of them (a surrogate pair), while
    # Python counts the characters (code points). Moreover, the native
    # ``substring`` swaps the positions and does not count the negative ones from
    # the end, and ``indexOf`` does not count a negative start from the end either.
    # We need helpers which follow the Python implementation of ``len``, slicing
    # and ``str.find``. Each helper is generated only for a meta-model which
    # takes ``len`` of strings, slices them or calls ``find`` on them, respectively.
    #
    # We count a lone surrogate as a character of its own, as Python does. We do
    # not check whether ``indexOf`` matches in the middle of a surrogate pair, as
    # that could only happen if the searched text started or ended with a lone
    # surrogate.
    uses_len = intermediate_uses.string_len_call(type_inference)
    uses_slicing = intermediate_uses.string_slicing(type_inference)
    uses_find = intermediate_uses.string_find_call(type_inference)

    # NOTE (mristin):
    # ``sliceStr`` and ``findStr`` rely on ``lenStr`` and on the low-level helpers.
    uses_any = uses_len or uses_slicing or uses_find

    string_helpers: List[Stripped] = []

    if uses_any:
        string_helpers.append(
            Stripped(
                f"""\
/**
 * Check whether a surrogate pair starts at `offset` in `text`.
 *
 * @param text - to be inspected
 * @param offset - in UTF-16 code units
 * @returns whether a surrogate pair starts at `offset`
 */
function isSurrogatePairAt(text: string, offset: number): boolean {{
{I}if (offset + 1 >= text.length) {{
{II}return false;
{I}}}

{I}const high = text.charCodeAt(offset);
{I}const low = text.charCodeAt(offset + 1);
{I}return high >= 0xd800 && high <= 0xdbff && low >= 0xdc00 && low <= 0xdfff;
}}"""
            )
        )

    if uses_any:
        string_helpers.append(
            Stripped(
                f"""\
/**
 * Count the characters of `text` between the UTF-16 offsets `startOffset` and
 * `endOffset`.
 *
 * @param text - to be inspected
 * @param startOffset - in UTF-16 code units, inclusive
 * @param endOffset - in UTF-16 code units, exclusive
 * @returns the number of characters (code points)
 */
function countCharacters(
{I}text: string,
{I}startOffset: number,
{I}endOffset: number
): number {{
{I}let count = 0;
{I}let offset = startOffset;
{I}while (offset < endOffset) {{
{II}offset += isSurrogatePairAt(text, offset) ? 2 : 1;
{II}count++;
{I}}}

{I}return count;
}}"""
            )
        )

    if uses_slicing or uses_find:
        string_helpers.append(
            Stripped(
                f"""\
/**
 * Compute the UTF-16 offset of the character at `position` in `text`.
 *
 * @param text - to be inspected
 * @param position - of the character, in characters (code points)
 * @returns the offset in UTF-16 code units
 */
function offsetOf(text: string, position: number): number {{
{I}let offset = 0;
{I}for (let i = 0; i < position; i++) {{
{II}offset += isSurrogatePairAt(text, offset) ? 2 : 1;
{I}}}

{I}return offset;
}}"""
            )
        )

    if uses_slicing:
        string_helpers.append(
            Stripped(
                f"""\
/**
 * Resolve `position` in a string of `length` as Python does in slicing.
 *
 * @remarks
 * A negative position counts from the end, and the positions out of range are
 * clamped to the string.
 *
 * @param position - to be resolved
 * @param length - of the string
 * @returns the resolved position within `[0, length]`
 */
function resolvePosition(position: number, length: number): number {{
{I}if (position < 0) {{
{II}return Math.max(position + length, 0);
{I}}}

{I}return Math.min(position, length);
}}"""
            )
        )

    if uses_any:
        string_helpers.append(
            Stripped(
                f"""\
/**
 * Count the characters (code points) of `text`.
 *
 * @remarks
 * We follow the Python implementation of `len`, since Python is the language of
 * the meta-model specifications. Hence, a character beyond the Basic
 * Multilingual Plane counts as one, unlike in `text.length`.
 *
 * @param text - to be measured
 * @returns the number of characters
 */
export function lenStr(text: string): number {{
{I}return countCharacters(text, 0, text.length);
}}"""
            )
        )

    if uses_slicing:
        string_helpers.append(
            Stripped(
                f"""\
/**
 * Slice `text` from `start` up to `end`, exclusive.
 *
 * @remarks
 * We follow the Python implementation of slicing, since Python is
 * the language of the meta-model specifications. Hence, the positions count
 * the characters (code points), a negative position counts from the end,
 * the positions out of range are clamped to the string, and the slice is empty
 * if `start` is not before `end`.
 *
 * @param text - to be sliced
 * @param start - of the slice, inclusive
 * @param end - of the slice, exclusive; if not given, the length of `text`
 * @returns the slice
 */
export function sliceStr(text: string, start: number, end?: number): string {{
{I}const length = lenStr(text);
{I}const theStart = resolvePosition(start, length);
{I}const theEnd = end === undefined ? length : resolvePosition(end, length);

{I}if (theStart >= theEnd) {{
{II}return "";
{I}}}

{I}return text.substring(offsetOf(text, theStart), offsetOf(text, theEnd));
}}"""
            )
        )

    if uses_find:
        string_helpers.append(
            Stripped(
                f"""\
/**
 * Find the first `sub` in `text` from `start` on.
 *
 * @remarks
 * We follow the Python implementation of `str.find`, since Python is
 * the language of the meta-model specifications. Hence, the positions count
 * the characters (code points), a negative `start` counts from the end, and
 * a `start` beyond the end of `text` gives -1.
 *
 * @param text - to be searched in
 * @param sub - to be searched for
 * @param start - of the search; if not given, the beginning of `text`
 * @returns the position of `sub` in `text`, or -1 if `sub` could not be found
 */
export function findStr(text: string, sub: string, start = 0): number {{
{I}const length = lenStr(text);
{I}const theStart = start < 0 ? Math.max(start + length, 0) : start;
{I}if (theStart > length) {{
{II}return -1;
{I}}}

{I}const startOffset = offsetOf(text, theStart);
{I}const offset = text.indexOf(sub, startOffset);
{I}if (offset === -1) {{
{II}return -1;
{I}}}

{I}return theStart + countCharacters(text, startOffset, offset);
}}"""
            )
        )

    blocks[len(blocks) - 1 : len(blocks) - 1] = string_helpers

    # NOTE (mristin):
    # The TypeScript strings are ordered by their UTF-16 code units, while Python
    # orders them by their characters (code points). The two orders differ for
    # the characters beyond the Basic Multilingual Plane, whose surrogates come
    # before the characters from U+E000 to U+FFFF. The helper is generated only for
    # a meta-model which might order strings, or which sorts the items of the set
    # properties of strings so that all the SDKs serialize them in the same order.
    if intermediate_uses.string_ordering(
        type_inference
    ) or intermediate_uses.sets_of_strings_in_properties(symbol_table):
        blocks[len(blocks) - 1 : len(blocks) - 1] = [
            Stripped(
                f"""\
/**
 * Decode the character (code point) of `text` which covers the UTF-16 offset
 * `offset`.
 *
 * @remarks
 * The offset might point to the low surrogate of a surrogate pair, in which
 * case we decode the whole pair. We decode a lone surrogate as itself, as
 * Python does.
 *
 * @param text - to be decoded
 * @param offset - in UTF-16 code units
 * @returns the character covering `offset`
 */
function codePointCovering(text: string, offset: number): number {{
{I}const codeUnit = text.charCodeAt(offset);

{I}if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff && offset > 0) {{
{II}const high = text.charCodeAt(offset - 1);
{II}if (high >= 0xd800 && high <= 0xdbff) {{
{III}return (high - 0xd800) * 0x400 + (codeUnit - 0xdc00) + 0x10000;
{II}}}
{I}}}

{I}if (codeUnit >= 0xd800 && codeUnit <= 0xdbff && offset + 1 < text.length) {{
{II}const low = text.charCodeAt(offset + 1);
{II}if (low >= 0xdc00 && low <= 0xdfff) {{
{III}return (codeUnit - 0xd800) * 0x400 + (low - 0xdc00) + 0x10000;
{II}}}
{I}}}

{I}return codeUnit;
}}"""
            ),
            Stripped(
                f"""\
/**
 * Compare `that` and `other` by their characters (code points).
 *
 * @remarks
 * We follow the Python implementation of the string comparison, since Python is
 * the language of the meta-model specifications. Hence, we order the strings by
 * their characters (code points), unlike the default sort and the native
 * operators `<` and `>`, which order them by their UTF-16 code units, and put
 * a character beyond the Basic Multilingual Plane, encoded as a surrogate pair,
 * before the characters from U+E000 to U+FFFF.
 *
 * @param that - to be compared
 * @param other - to be compared against
 * @returns -1 if `that` comes before `other`, 0 if they are equal, and 1
 * otherwise
 */
export function compareByCodePoints(that: string, other: string): number {{
{I}const length = Math.min(that.length, other.length);

{I}let offset = 0;
{I}while (
{II}offset < length &&
{II}that.charCodeAt(offset) === other.charCodeAt(offset)
{I}) {{
{II}offset++;
{I}}}

{I}if (offset === length) {{
{II}if (that.length === other.length) {{
{III}return 0;
{II}}}

{II}return that.length < other.length ? -1 : 1;
{I}}}

{I}return codePointCovering(that, offset) < codePointCovering(other, offset)
{II}? -1
{II}: 1;
}}"""
            ),
        ]

    # NOTE (mristin):
    # We add the helper only if the meta-model uses the modulo so that we do not
    # clutter the code otherwise. The helper lives in the common module so that
    # both the verification and the methods in the types can use it. It is exported
    # so that the clients can rely on it, and so that we can unit-test it.
    if intermediate_uses.modulo(symbol_table):
        blocks.insert(len(blocks) - 1, FLOOR_MOD)

    # NOTE (mristin):
    # Analogous to the modulo, we add the helper only if the meta-model calls
    # the built-in ``int``.
    if intermediate_uses.int_call(symbol_table):
        blocks.insert(len(blocks) - 1, PARSE_SAFE_INT)

    # NOTE (mristin):
    # Analogous to the modulo, we add the helpers only if the meta-model computes
    # an intersection or a difference of sets.
    if intermediate_uses.set_operations(symbol_table):
        for block in SET_OPERATIONS:
            blocks.insert(len(blocks) - 1, block)

    # NOTE (mristin):
    # Analogous to the modulo, we add the helpers only if the meta-model has
    # a set in a property, which we serialize as a sorted array.
    if intermediate_uses.set_properties(symbol_table):
        for block in SET_SORTING:
            blocks.insert(len(blocks) - 1, block)

    # NOTE (mristin):
    # We need helpers which follow the Python implementation of ``str.lstrip`` and
    # ``str.rstrip``, as TypeScript has no native equivalents which strip the given
    # characters. Each helper is generated only for a meta-model which calls it.
    if intermediate_uses.lstrip_call(type_inference):
        blocks.insert(
            len(blocks) - 1,
            Stripped(
                f"""\
/**
 * Strip the longest prefix of `text` which consists only of the characters
 * listed in `chars`.
 *
 * @remarks
 * We follow the Python implementation of `str.lstrip`, since Python is
 * the language of the meta-model specifications. Hence, we strip
 * the characters (code points) rather than the UTF-16 code units, so that
 * a character beyond the Basic Multilingual Plane is never split in half.
 *
 * @param text - to be stripped
 * @param chars - to be stripped from the start of `text`
 * @returns `text` without the stripped prefix
 */
export function lstrip(text: string, chars: string): string {{
{I}// NOTE (mristin):
{I}// A string is iterated over its characters (code points), not over its
{I}// UTF-16 code units.
{I}const charSet = new Set<string>(chars);

{I}let offset = 0;
{I}for (const character of text) {{
{II}if (!charSet.has(character)) {{
{III}break;
{II}}}

{II}offset += character.length;
{I}}}

{I}return text.substring(offset);
}}"""
            ),
        )

    if intermediate_uses.rstrip_call(type_inference):
        blocks.insert(
            len(blocks) - 1,
            Stripped(
                f"""\
/**
 * Strip the longest suffix of `text` which consists only of the characters
 * listed in `chars`.
 *
 * @remarks
 * We follow the Python implementation of `str.rstrip`, since Python is
 * the language of the meta-model specifications. Hence, we strip
 * the characters (code points) rather than the UTF-16 code units, so that
 * a character beyond the Basic Multilingual Plane is never split in half.
 *
 * @param text - to be stripped
 * @param chars - to be stripped from the end of `text`
 * @returns `text` without the stripped suffix
 */
export function rstrip(text: string, chars: string): string {{
{I}// NOTE (mristin):
{I}// A string is iterated over its characters (code points), not over its
{I}// UTF-16 code units.
{I}const charSet = new Set<string>(chars);

{I}// NOTE (mristin):
{I}// We keep the text up to the end of the last character which is not to be
{I}// stripped.
{I}let end = 0;
{I}let offset = 0;
{I}for (const character of text) {{
{II}offset += character.length;
{II}if (!charSet.has(character)) {{
{III}end = offset;
{II}}}
{I}}}

{I}return text.substring(0, end);
}}"""
            ),
        )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
