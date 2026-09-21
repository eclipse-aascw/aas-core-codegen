"""Generate the XML-RPC subset which carries the JSON-able values."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import common as typescript_common
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_parsers() -> List[Stripped]:
    """
    Generate the parsers of the XML-RPC subset.

    The six functions which the de/serialization of the model names are exported;
    the discriminator and the four readers behind it are not, as nothing outside
    reaches a ``<boolean>`` or a ``<member>`` without going through a ``<value>``
    first.
    """
    return [
        Stripped(
            f"""\
/**
 * Match a numeral of the `<double>` lexical space.
 *
 * @remarks
 * This is the numeric part of the lexical space of `xs:double`, and
 * deliberately not its three named literals -- `INF`, `-INF` and `NaN` --
 * since a JSON number can be none of them.
 */
const DOUBLE_RE = new RegExp(
{I}"^(\\\\+|-)?([0-9]+(\\\\.[0-9]*)?|\\\\.[0-9]+)([Ee](\\\\+|-)?[0-9]+)?$"
);"""
        ),
        Stripped(
            f"""\
/**
 * Parse the content of an element holding a JSON-able value.
 *
 * @remarks
 * The content is a single discriminator element -- `<boolean>`, `<double>`,
 * `<string>`, `<array>` or `<struct>` -- which says what the value is.
 *
 * @param cursor - to read from
 * @returns parsed JSON-able value, or an error
 */
export function parseValueContent(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.JsonValue, DeserializationError> {{
{I}const startTagOrError = readNextOpenTagInNoNamespace(cursor);
{I}if (startTagOrError.error !== null) {{
{II}return new AasCommon.Either<AasTypes.JsonValue, DeserializationError>(
{III}null, startTagOrError.error
{II});
{I}}}

{I}const localName = localNameOfTag(startTagOrError.mustValue().tag);

{I}const parseContent = parserForDiscriminator(localName);
{I}if (parseContent === null) {{
{II}// NOTE (mristin):
{II}// The element which is no discriminator at all gets no step of its own:
{II}// it is that very element which does not belong here, so naming it in
{II}// the path as well as in the message would say nothing more.
{II}return newDeserializationError<AasTypes.JsonValue>(
{III}`Expected a discriminator element (one of 'boolean', 'double', ` +
{IIII}`'string', 'array' or 'struct'), but got: '${{localName}}'`
{II});
{I}}}

{I}cursor.advance();

{I}const parsed = parseElementContentInNoNamespace(cursor, localName, parseContent);
{I}if (parsed.error !== null) {{
{II}// NOTE (mristin):
{II}// The discriminator is an element which we actually enter, so it is
{II}// a step of the path.
{II}parsed.error.path.prepend(new ElementSegment(localName));
{I}}}

{I}return parsed;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Give out the parser of the content of the discriminator `localName`.
 *
 * @param localName - local name of the discriminator element
 * @returns the parser of its content, or `null` if `localName` names no
 * discriminator
 */
function parserForDiscriminator(
{I}localName: string
): ContentParser<AasTypes.JsonValue> | null {{
{I}switch (localName) {{
{II}case "boolean":
{III}return parseBooleanContent;
{II}case "double":
{III}return parseDoubleContent;
{II}case "string":
{III}return parseStringContent;
{II}case "array":
{III}return parseArrayBody;
{II}case "struct":
{III}return parseStructBody;
{II}default:
{III}return null;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse the content of a `<boolean>` element.
 *
 * @remarks
 * Real XML-RPC tooling writes and expects a strict `1`/`0`, and not
 * the `true`/`false` which `xs:boolean` and the rest of this module use.
 *
 * @param cursor - to read from
 * @returns parsed boolean, or an error
 */
function parseBooleanContent(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.JsonValue, DeserializationError> {{
{I}// NOTE (mristin):
{I}// `whiteSpace` is fixed to `collapse` for every atomic XSD type but
{I}// a string, so a pretty-printed `<boolean>` has to be read as well.
{I}const text = collapseWhitespace(parseTextContent(cursor));

{I}if (text === "1") {{
{II}return new AasCommon.Either<AasTypes.JsonValue, DeserializationError>(
{III}true, null
{II});
{I}}}
{I}if (text === "0") {{
{II}return new AasCommon.Either<AasTypes.JsonValue, DeserializationError>(
{III}false, null
{II});
{I}}}

{I}return newDeserializationError<AasTypes.JsonValue>(
{II}`Expected '0' or '1' as the text of a 'boolean' element, ` +
{III}`but got: '${{text}}'`
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse the content of a `<double>` element.
 *
 * @param cursor - to read from
 * @returns parsed number, or an error
 */
function parseDoubleContent(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.JsonValue, DeserializationError> {{
{I}// NOTE (mristin):
{I}// See the note in `parseBooleanContent` on why the whitespace is
{I}// collapsed here.
{I}const text = collapseWhitespace(parseTextContent(cursor));

{I}// NOTE (mristin):
{I}// The lexical form is matched before the text is converted. `Number`
{I}// reads far more than we admit here: a hexadecimal literal, so "0x10"
{I}// would come out as 16, an empty text, which would come out as 0, and
{I}// the spellings "Infinity" and "-Infinity".
{I}//
{I}// Mind that the numeral excludes "INF", "-INF" and "NaN" on purpose,
{I}// unlike `xs:double`, which names all three. A `<double>` carries
{I}// a JSON number, and JSON knows neither an infinity nor a not-a-number,
{I}// so there is no JSON-able value for such a text to parse into.
{I}if (!DOUBLE_RE.test(text)) {{
{II}return newDeserializationError<AasTypes.JsonValue>(
{III}`Expected a number as the text of a 'double' element, ` +
{IIII}`but got: '${{text}}'`
{II});
{I}}}

{I}const value = Number(text);

{I}// NOTE (mristin):
{I}// A literal too large for a `number` gives an infinity, which is no
{I}// JSON-able value either, so it is refused rather than rounded.
{I}if (!Number.isFinite(value)) {{
{II}return newDeserializationError<AasTypes.JsonValue>(
{III}`Expected a number representable as a JSON-able value as the text ` +
{IIII}`of a 'double' element, but got a value which rounds to ` +
{IIII}`an infinity: '${{text}}'`
{II});
{I}}}

{I}return new AasCommon.Either<AasTypes.JsonValue, DeserializationError>(
{II}value, null
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse the content of a `<string>` element.
 *
 * @remarks
 * `xs:string` is `preserve` and not `collapse`, so a `<string>` keeps its
 * whitespace, unlike a `<boolean>` or a `<double>`.
 *
 * @param cursor - to read from
 * @returns parsed string
 */
function parseStringContent(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.JsonValue, DeserializationError> {{
{I}return new AasCommon.Either<AasTypes.JsonValue, DeserializationError>(
{II}parseTextContent(cursor), null
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse the content of a `<data>` element as the items of a JSON-able array.
 *
 * @remarks
 * The `<data>` element is a step of the path, as we enter it, and so is
 * the position of an item. The item's own `<value>` element is not: the index
 * already names it, so a step of its own would say nothing more.
 *
 * @param cursor - to read from
 * @returns parsed JSON-able array, or an error
 */
function parseDataContent(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.JsonArray, DeserializationError> {{
{I}const items = new Array<AasTypes.JsonValue>();

{I}// eslint-disable-next-line no-constant-condition
{I}while (true) {{
{II}cursor.skipIgnorable();
{II}const token = cursor.current();
{II}if (token === null || !(token instanceof OpenTagToken)) {{
{III}break;
{II}}}

{II}const itemOrError = parseNamedElementInNoNamespace(cursor, "value", parseValueContent);
{II}if (itemOrError.error !== null) {{
{III}itemOrError.error.path.prepend(new IndexSegment(items.length));
{III}itemOrError.error.path.prepend(new ElementSegment("data"));
{III}return new AasCommon.Either<AasTypes.JsonArray, DeserializationError>(
{IIII}null, itemOrError.error
{III});
{II}}}

{II}items.push(itemOrError.mustValue());
{I}}}

{I}return new AasCommon.Either<AasTypes.JsonArray, DeserializationError>(
{II}items, null
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse the content of an element holding a JSON-able array.
 *
 * @remarks
 * The content is a single `<data>` element holding a `<value>` per item.
 *
 * @param cursor - to read from
 * @returns parsed JSON-able array, or an error
 */
export function parseArrayBody(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.JsonArray, DeserializationError> {{
{I}return parseNamedElementInNoNamespace(cursor, "data", parseDataContent);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse the content of an element holding a JSON-able object.
 *
 * @remarks
 * The content is a `<member>` per key, each holding a `<name>` and
 * a `<value>`.
 *
 * @param cursor - to read from
 * @returns parsed JSON-able object, or an error
 */
export function parseStructBody(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.JsonObject, DeserializationError> {{
{I}const members: AasTypes.JsonObject = {{}};

{I}// eslint-disable-next-line no-constant-condition
{I}while (true) {{
{II}cursor.skipIgnorable();
{II}const token = cursor.current();
{II}if (token === null || !(token instanceof OpenTagToken)) {{
{III}break;
{II}}}

{II}const memberOrError = parseNamedElementInNoNamespace(
{III}cursor, "member", parseMemberContent
{II});
{II}if (memberOrError.error !== null) {{
{III}return new AasCommon.Either<AasTypes.JsonObject, DeserializationError>(
{IIII}null, memberOrError.error
{III});
{II}}}

{II}const [key, value] = memberOrError.mustValue();

{II}// NOTE (mristin):
{II}// A repeated member name is refused, just as a repeated property element
{II}// is refused in the de/serialization of the model. Letting the later
{II}// member win would silently accept a document which says two different
{II}// things about the same key.
{II}if (Object.prototype.hasOwnProperty.call(members, key)) {{
{III}const error = new DeserializationError(
{IIII}"The member occurred more than once"
{III});
{III}error.path.prepend(new KeySegment(key));
{III}return new AasCommon.Either<AasTypes.JsonObject, DeserializationError>(
{IIII}null, error
{III});
{II}}}

{II}members[key] = value;
{I}}}

{I}return new AasCommon.Either<AasTypes.JsonObject, DeserializationError>(
{II}members, null
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse the content of a `<name>` element as the key of a member.
 *
 * @remarks
 * `xs:string` is `preserve` and not `collapse`, so a key keeps its whitespace
 * exactly as a `<string>` does.
 *
 * @param cursor - to read from
 * @returns the key
 */
function parseNameContent(
{I}cursor: XmlCursor
): AasCommon.Either<string, DeserializationError> {{
{I}return new AasCommon.Either<string, DeserializationError>(
{II}parseTextContent(cursor), null
{I});
}}

/**
 * Parse the content of a `<member>` element as a key and a JSON-able value.
 *
 * @remarks
 * From the `<name>` element on the key is known, so every failure beneath it
 * can name the member it belongs to. A `<struct>` carries that key in a `<name>`
 * child element instead of in an attribute, so the key segment renders as
 * a predicate on that child element, and the `<member>` element itself gets no
 * step of its own.
 *
 * @param cursor - to read from
 * @returns the member's name and its parsed value, or an error
 */
function parseMemberContent(
{I}cursor: XmlCursor
): AasCommon.Either<[string, AasTypes.JsonValue], DeserializationError> {{
{I}const keyOrError = parseNamedElementInNoNamespace(cursor, "name", parseNameContent);
{I}if (keyOrError.error !== null) {{
{II}return new AasCommon.Either<
{III}[string, AasTypes.JsonValue], DeserializationError
{II}>(null, keyOrError.error);
{I}}}
{I}const key = keyOrError.mustValue();

{I}const valueOrError = parseNamedElementInNoNamespace(cursor, "value", parseValueContent);
{I}if (valueOrError.error !== null) {{
{II}valueOrError.error.path.prepend(new ElementSegment("value"));
{II}valueOrError.error.path.prepend(new KeySegment(key));
{II}return new AasCommon.Either<
{III}[string, AasTypes.JsonValue], DeserializationError
{II}>(null, valueOrError.error);
{I}}}

{I}return new AasCommon.Either<
{II}[string, AasTypes.JsonValue], DeserializationError
{I}>([key, valueOrError.mustValue()], null);
}}"""
        ),
    ]


def _generate_writers() -> List[Stripped]:
    """
    Generate the writers of the XML-RPC subset.

    These mirror :py:func:`_generate_parsers`, element for element.
    """
    return [
        Stripped(
            f"""\
/**
 * Write `value` as the content of an element holding a JSON-able value.
 *
 * @remarks
 * The content is a single discriminator element which says what the value is.
 *
 * @param parts - to write to
 * @param value - to be serialized
 * @throws {{@link SerializationError}} if `value` is not JSON-able
 */
export function writeValueContent(
{I}parts: Array<string>,
{I}value: AasTypes.JsonValue
): void {{
{I}writeValue(parts, value, true);
}}

/**
 * Write `value` as the content of a `<value>` element of this very module,
 * which already resides in no namespace.
 *
 * @param parts - to write to
 * @param value - to be serialized
 * @throws {{@link SerializationError}} if `value` is not JSON-able
 */
function writeNestedValueContent(
{I}parts: Array<string>,
{I}value: AasTypes.JsonValue
): void {{
{I}writeValue(parts, value, false);
}}

function writeValue(
{I}parts: Array<string>,
{I}value: AasTypes.JsonValue,
{I}undeclareNamespace: boolean
): void {{
{I}const xmlns = undeclareNamespace ? ' xmlns=""' : "";

{I}if (value === null || value === undefined) {{
{II}throw new SerializationError(
{III}`Expected a JSON-able value, but got: ${{value}}`
{II});
{I}}}

{I}switch (typeof value) {{
{II}case "boolean":
{III}// NOTE (mristin):
{III}// Real XML-RPC tooling writes and expects a strict `1`/`0`, and not
{III}// the `true`/`false` which `xs:boolean` and the rest of this module
{III}// use.
{III}parts.push(
{IIII}value
{IIIII}? `<boolean${{xmlns}}>1</boolean>`
{IIIII}: `<boolean${{xmlns}}>0</boolean>`
{III});
{III}return;

{II}case "number":
{III}// NOTE (mristin):
{III}// JSON knows neither an infinity nor a not-a-number, so neither is
{III}// a JSON-able value, and `parseDoubleContent` refuses to read either
{III}// back.
{III}if (!Number.isFinite(value)) {{
{IIII}throw new SerializationError(
{IIIII}`Expected a JSON-able value, but got the number ${{value}}, ` +
{IIIII}`which is neither finite nor representable in JSON`
{IIII});
{III}}}
{III}parts.push(`<double${{xmlns}}>${{value}}</double>`);
{III}return;

{II}case "string":
{III}parts.push(`<string${{xmlns}}>${{escapeXmlText(value)}}</string>`);
{III}return;

{II}case "object":
{III}break;

{II}default:
{III}throw new SerializationError(
{IIII}`Expected a JSON-able value (a boolean, a number, a string, ` +
{IIIII}`an array or an object), but got: ${{typeof value}}`
{III});
{I}}}

{I}if (Array.isArray(value)) {{
{II}parts.push(`<array${{xmlns}}>`);
{II}writeArray(parts, value, false);
{II}parts.push("</array>");
{II}return;
{I}}}

{I}parts.push(`<struct${{xmlns}}>`);
{I}writeStruct(parts, value as AasTypes.JsonObject, false);
{I}parts.push("</struct>");
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write `value` as the content of an element holding a JSON-able array.
 *
 * @remarks
 * The content is a single `<data>` element holding a `<value>` per item.
 *
 * @param parts - to write to
 * @param value - to be serialized
 * @throws {{@link SerializationError}} if `value` is not JSON-able
 */
export function writeArrayBody(
{I}parts: Array<string>,
{I}value: AasTypes.JsonArray
): void {{
{I}writeArray(parts, value, true);
}}

function writeArray(
{I}parts: Array<string>,
{I}value: AasTypes.JsonArray,
{I}undeclareNamespace: boolean
): void {{
{I}parts.push(undeclareNamespace ? '<data xmlns="">' : "<data>");
{I}for (let i = 0; i < value.length; i++) {{
{II}parts.push("<value>");
{II}try {{
{III}writeNestedValueContent(parts, value[i]);
{II}}} catch (error) {{
{III}if (error instanceof SerializationError) {{
{IIII}error.prependIndex(i);
{III}}}
{III}throw error;
{II}}}
{II}parts.push("</value>");
{I}}}
{I}parts.push("</data>");
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write `value` as the content of an element holding a JSON-able object.
 *
 * @remarks
 * The content is a `<member>` per key, each holding a `<name>` and a
 * `<value>`.
 *
 * @param parts - to write to
 * @param value - to be serialized
 * @throws {{@link SerializationError}} if `value` is not JSON-able
 */
export function writeStructBody(
{I}parts: Array<string>,
{I}value: AasTypes.JsonObject
): void {{
{I}writeStruct(parts, value, true);
}}

function writeStruct(
{I}parts: Array<string>,
{I}value: AasTypes.JsonObject,
{I}undeclareNamespace: boolean
): void {{
{I}// NOTE (mristin):
{I}// The members are siblings, so each of them is an outermost element of
{I}// its own where the enclosing element is not ours.
{I}const memberStartTag = (
{II}undeclareNamespace ? '<member xmlns="">' : "<member>"
{I});

{I}for (const key of Object.keys(value)) {{
{II}parts.push(memberStartTag);
{II}parts.push(`<name>${{escapeXmlText(key)}}</name>`);
{II}parts.push("<value>");
{II}try {{
{III}writeNestedValueContent(parts, value[key]);
{II}}} catch (error) {{
{III}if (error instanceof SerializationError) {{
{IIII}error.prependKey(key);
{III}}}
{III}throw error;
{II}}}
{II}parts.push("</value>");
{II}parts.push("</member>");
{I}}}
}}"""
        ),
    ]


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate() -> str:
    """Generate the code of the XML-RPC subset."""
    blocks = [
        Stripped(
            """\
/**
 * Provide the subset of XML-RPC which carries the JSON-able values.
 *
 * @remarks
 *
 * JSON prescribes no XML representation of its own, so a JSON-able value is
 * written as the subset of XML-RPC which covers exactly what such a value can
 * be: `<boolean>`, `<double>`, `<string>`, `<array>` and `<struct>`.
 *
 * These elements reside in no namespace at all, as the XML-RPC specification
 * prescribes, and not in the namespace of the enclosing document. The
 * outermost one therefore undeclares the default namespace with `xmlns=\"\"`,
 * and the elements nested in it inherit that.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasCommon from "./common";
import * as AasTypes from "./types";

import {
  ContentParser,
  DeserializationError,
  ElementSegment,
  IndexSegment,
  KeySegment,
  SerializationError,
  XmlCursor,
  collapseWhitespace,
  escapeXmlText,
  localNameOfTag,
  newDeserializationError,
  parseElementContentInNoNamespace,
  parseNamedElementInNoNamespace,
  parseTextContent,
  readNextOpenTagInNoNamespace
} from "./xmlcommon";

import { OpenTagToken } from "xmlsax-typescript";"""
        ),
    ]  # type: List[Stripped]

    blocks.extend(_generate_parsers())
    blocks.extend(_generate_writers())

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert __doc__ is not None
