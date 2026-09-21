"""Generate the XML primitives shared by the modules which read and write XML."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import common as typescript_common
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
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate the code of the XML primitives."""
    namespace_literal = typescript_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    # NOTE (mristin):
    # The XML-RPC subset, over which the JSON-able values are de/serialized,
    # reads its elements in no namespace at all, as the XML-RPC specification
    # prescribes. The primitives which deal with such elements are therefore
    # only generated for a meta-model which actually has a JSON-able type.
    in_no_namespace_blocks = (
        [
            Stripped(
                f"""\
/**
 * Read the next non-ignorable token from `cursor`, expecting it to be
 * an opening XML element which resides in no namespace at all.
 *
 * @param cursor - to read from
 * @returns the opening tag, or an error
 */
export function readNextOpenTagInNoNamespace(
{I}cursor: XmlCursor
): AasCommon.Either<OpenTagToken, DeserializationError> {{
{I}return readNextOpenTagInNamespace(cursor, "");
}}"""
            ),
            Stripped(
                f"""\
/**
 * Parse the content of the XML element in no namespace at all which the caller
 * has opened, and consume the corresponding closing element named `localName`.
 *
 * @param cursor - to read from
 * @param localName - local name of the element which the caller has opened
 * @param parseContent - parses the content of the element
 * @returns parsed value, or an error
 * @typeParam T - type of the parsed value
 */
export function parseElementContentInNoNamespace<T>(
{I}cursor: XmlCursor,
{I}localName: string,
{I}parseContent: ContentParser<T>
): AasCommon.Either<T, DeserializationError> {{
{I}return parseElementContentInNamespace(cursor, localName, parseContent, "");
}}"""
            ),
            Stripped(
                f"""\
/**
 * Read the next XML element in no namespace at all from `cursor`, expecting it
 * to be named `expectedLocalName`, parse its content with `parseContent` and
 * consume the matching closing element.
 *
 * @param cursor - to read from
 * @param expectedLocalName - the expected local name of the element
 * @param parseContent - parses the content of the element
 * @returns parsed value, or an error
 * @typeParam T - type of the parsed value
 */
export function parseNamedElementInNoNamespace<T>(
{I}cursor: XmlCursor,
{I}expectedLocalName: string,
{I}parseContent: ContentParser<T>
): AasCommon.Either<T, DeserializationError> {{
{I}return parseNamedElementInNamespace(
{II}cursor, expectedLocalName, parseContent, ""
{I});
}}"""
            ),
        ]
        if intermediate.uses_json_types(symbol_table)
        else []
    )  # type: List[Stripped]

    blocks = [
        Stripped(
            """\
/**
 * Provide the XML primitives shared by the modules of this SDK which read and
 * write XML.
 *
 * @remarks
 *
 * The skipping of the ignorable tokens, the checks of the namespace and
 * the consumption of the tags are spelled out here once, instead of once in
 * the de/serialization of the model and once again wherever else a document is
 * read or written.
 *
 * The XML namespace is a constant of this module, and not an argument which
 * every primitive takes. Every parser wears one and the same shape,
 * {@link ContentParser}, which is handed the cursor and nothing else, so that
 * a parser can be given to another parser without allocating a closure; and
 * one SDK speaks of exactly one namespace anyhow.
 *
 * The elements of the XML-RPC subset, over which a JSON-able value is
 * de/serialized, are the one exception: they reside in no namespace at all,
 * and are read with the primitives named `...InNoNamespace`.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasCommon from "./common";

import {
  CdataToken,
  CloseTagToken,
  CommentToken,
  EndToken,
  OpenTagToken,
  TextToken,
  XmlAnyToken,
  XmlSaxParser
} from "xmlsax-typescript";"""
        ),
        Stripped(
            f"""\
export const NAMESPACE = {namespace_literal};"""
        ),
        typescript_common.NOTE_ON_THE_THREE_ERROR_PATHS,
        Stripped(
            f"""\
/**
 * Escape the characters which an XPath can not carry literally.
 *
 * @remarks
 *
 * Neither an ampersand nor a less-than sign can occur in a valid element name,
 * but they are escaped all the same, so that a bug report over a broken
 * document still reads.
 */
function escapeForXPath(text: string): string {{
{I}// NOTE (mristin):
{I}// Mind the order -- the ampersand has to go first, or the ampersands of
{I}// the replacements below would be escaped in their turn.
{I}return text
{II}.replace(/&/g, "&amp;")
{II}.replace(/\\//g, "&#47;")
{II}.replace(/</g, "&lt;")
{II}.replace(/>/g, "&gt;")
{II}.replace(/"/g, "&quot;")
{II}.replace(/'/g, "&apos;");
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent an element on a path to the erroneous value.
 */
export class ElementSegment {{
{I}/**
{I} * Local name of the element, without the namespace
{I} */
{I}readonly name: string;

{I}constructor(name: string) {{
{II}this.name = name;
{I}}}

{I}/**
{I} * Render the segment as a tag without the namespace.
{I} *
{I} * @remarks
{I} *
{I} * We deliberately omit the namespace in the tag names. If you want to
{I} * actually query with the resulting XPath, you have to insert the namespaces
{I} * manually. We did not know how to include the namespace in a meaningful way,
{I} * as XPath assumes namespace prefixes to be defined *outside* of the document.
{I} * At least the path thus rendered is informative, and you should be able to
{I} * descend it manually.
{I} */
{I}toString(): string {{
{II}return escapeForXPath(this.name);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent an element in a sequence on a path to the erroneous value.
 */
export class IndexSegment {{
{I}/**
{I} * Index of the element in the sequence
{I} */
{I}readonly index: number;

{I}constructor(index: number) {{
{II}this.index = index;
{I}}}

{I}/**
{I} * Render the segment as an element wildcard with the index.
{I} */
{I}toString(): string {{
{II}return `*[${{this.index}}]`;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent a member of an open JSON-able object on a path to the erroneous
 * element.
 *
 * @remarks
 *
 * Unlike an {{@link ElementSegment}}, which names an element prescribed by
 * the meta-model, a key is known only at run time, and can be any string at
 * all.
 */
export class KeySegment {{
{I}/**
{I} * Key of the member
{I} */
{I}readonly key: string;

{I}constructor(key: string) {{
{II}this.key = key;
{I}}}

{I}/**
{I} * Render the segment as a predicate on the `<name>` child element.
{I} *
{I} * @remarks
{I} *
{I} * A JSON-able object is written as an XML-RPC `<struct>`, which carries
{I} * the key of a member in a `<name>` child element instead of in an attribute,
{I} * so the XPath has to match on that child element.
{I} */
{I}toString(): string {{
{II}return `member[name="${{escapeForXPath(this.key)}}"]`;
{I}}}
}}"""
        ),
        Stripped(
            """\
export type Segment = ElementSegment | IndexSegment | KeySegment;"""
        ),
        Stripped(
            f"""\
/**
 * Represent the relative path to the erroneous element.
 */
export class Path {{
{I}private readonly _segments = new Array<Segment>();

{I}segments(): Array<Segment> {{
{II}return this._segments;
{I}}}

{I}prepend(segment: Segment): void {{
{II}this._segments.unshift(segment);
{I}}}

{I}/**
{I} * Render the path as a relative XPath.
{I} *
{I} * @remarks
{I} *
{I} * We omit the leading `/` so that you can easily prefix it as you need.
{I} */
{I}toString(): string {{
{II}return this._segments.join("/");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Signal that XML de-serialization could not be performed.
 */
export class DeserializationError {{
{I}readonly message: string;
{I}readonly path: Path;

{I}constructor(message: string, path: Path | null = null) {{
{II}this.message = message;
{II}this.path = path ?? new Path();
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Signal that XML serialization could not be performed.
 *
 * @remarks
 *
 * The {{@link SerializationError.path}} points into the instance which was handed
 * over for the serialization, and *not* into an XML document -- at the point of
 * the failure there is no document yet. For example, `.submodels[0].id` tells you
 * that the serialization broke on `that.submodels[0].id`.
 *
 * The path is therefore a TypeScript access expression, and not the relative
 * XPath which the de-serialization reports, and it is a plain string, unlike
 * the structured {{@link Path}} of the de-serialization: the elements which
 * the XML representation adds on top of the instance contribute no segment, as
 * they correspond to no property access. This concerns the element enclosing
 * the instance itself, and the element which designates the model type of
 * the value of a property -- a caller holding the instance reaches the value as,
 * say, `value.idShort` and not as `value/idShort`.
 */
export class SerializationError extends Error {{
{I}private readonly _segments = new Array<string>();

{I}/**
{I} * Render the path to the erroneous value as a TypeScript access expression.
{I} */
{I}get path(): string {{
{II}return this._segments.join("");
{I}}}

{I}/**
{I} * Insert the access to the property `name` before the {{@link path}}.
{I} */
{I}prependProperty(name: string): void {{
{II}this._segments.unshift(`.${{name}}`);
{I}}}

{I}/**
{I} * Insert the access to the item at `index` before the {{@link path}}.
{I} */
{I}prependIndex(index: number): void {{
{II}this._segments.unshift(`[${{index}}]`);
{I}}}

{I}/**
{I} * Insert the access to the member `key` before the {{@link path}}.
{I} *
{I} * @remarks
{I} *
{I} * Unlike a property of one of our classes, a member of an open JSON-able
{I} * object is known only at run time and can be any string at all, so it is
{I} * always rendered as a subscript.
{I} */
{I}prependKey(key: string): void {{
{II}this._segments.unshift(`[${{JSON.stringify(key)}}]`);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
export function newDeserializationError<T>(
{I}message: string
): AasCommon.Either<T, DeserializationError> {{
{I}return new AasCommon.Either<T, DeserializationError>(
{II}null,
{II}new DeserializationError(message)
{I});
}}

/**
 * Parse a value from `cursor`.
 *
 * Every parser in this module wears this one shape, which is what lets them
 * compose: a parser can be given to another parser without a closure, since
 * everything it needs comes from the `cursor` and from its own definition.
 * The name says what a parser consumes -- a `parse*Content` stops right before
 * the closing tag of the element which the caller has opened, while
 * a `parse*Element` and a `dispatchParse*Element` read an element of their own,
 * its tags included.
 *
 * @typeParam T - type of the parsed value
 */
export type ContentParser<T> = (
{I}cursor: XmlCursor
) => AasCommon.Either<T, DeserializationError>;

export function currentTokenKind(cursor: XmlCursor): string {{
{I}const token = cursor.current();
{I}if (token === null) {{
{II}return "end-of-token-stream";
{I}}}

{I}return token.kind;
}}

export function localNameOfTag(tag: unknown): string {{
{I}const aTag = tag as {{
{II}name?: unknown,
{II}local?: unknown,
{II}localName?: unknown
{I}}};

{I}if (typeof aTag.local === "string") {{
{II}return aTag.local;
{I}}}
{I}if (typeof aTag.localName === "string") {{
{II}return aTag.localName;
{I}}}
{I}if (typeof aTag.name === "string") {{
{II}const colonIndex = aTag.name.indexOf(":");
{II}if (colonIndex >= 0) {{
{III}return aTag.name.substring(colonIndex + 1);
{II}}}
{II}return aTag.name;
{I}}}

{I}return "";
}}

function namespaceOfTag(tag: unknown): string {{
{I}const aTag = tag as {{ uri?: unknown, namespaceURI?: unknown }};
{I}if (typeof aTag.uri === "string") {{
{II}return aTag.uri;
{I}}}
{I}if (typeof aTag.namespaceURI === "string") {{
{II}return aTag.namespaceURI;
{I}}}
{I}return "";
}}

function describeNamespace(namespace: string): string {{
{I}return namespace.length === 0 ? "no namespace" : `'${{namespace}}'`;
}}

function checkExpectedOpenTagNamespace(
{I}openTag: OpenTagToken,
{I}expectedNamespace: string
): DeserializationError | null {{
{I}const namespace = namespaceOfTag(openTag.tag);
{I}if (namespace !== expectedNamespace) {{
{II}return new DeserializationError(
{III}`Expected XML namespace ${{describeNamespace(expectedNamespace)}}, ` +
{IIII}`but got ${{describeNamespace(namespace)}}`
{II});
{I}}}

{I}return null;
}}

/**
 * Read the next property's opening tag while parsing the sequence of
 * properties of `className`, advancing `cursor` past it.
 *
 * @param cursor - to be read from
 * @param className - name of the class being parsed, for error reporting
 * @returns
 * the next property's opening tag, or `null` if the closing tag of
 * `className` was reached instead, or an error
 */
export function nextPropertyOpenTag(
{I}cursor: XmlCursor,
{I}className: string
): OpenTagToken | DeserializationError | null {{
{I}const token = cursor.current();
{I}if (token === null) {{
{II}return new DeserializationError(
{III}`Unexpected end of token stream while parsing ${{className}}`
{II});
{I}}}

{I}if (token instanceof CloseTagToken) {{
{II}return null;
{I}}}

{I}if (!(token instanceof OpenTagToken)) {{
{II}return new DeserializationError(
{III}"Expected an XML property start element or the closing element of " +
{III}`${{className}}, but got token kind: ${{token.kind}}`
{II});
{I}}}

{I}const namespaceError = checkExpectedOpenTagNamespace(token, NAMESPACE);
{I}if (namespaceError !== null) {{
{II}return namespaceError;
{I}}}

{I}cursor.advance();
{I}return token;
}}

function checkExpectedCloseTag(
{I}closeTag: CloseTagToken,
{I}expectedLocalName: string,
{I}expectedNamespace: string
): DeserializationError | null {{
{I}const namespace = namespaceOfTag(closeTag.tag);
{I}if (namespace !== expectedNamespace) {{
{II}return new DeserializationError(
{III}`Expected XML namespace ${{describeNamespace(expectedNamespace)}}, ` +
{IIII}`but got ${{describeNamespace(namespace)}}`
{II});
{I}}}

{I}const observedLocalName = localNameOfTag(closeTag.tag);
{I}if (observedLocalName !== expectedLocalName) {{
{II}return new DeserializationError(
{III}`Expected closing XML element '${{expectedLocalName}}', ` +
{III}`but got '${{observedLocalName}}'`
{II});
{I}}}

{I}return null;
}}

/**
 * Read the next token from `cursor`, expecting it to be the closing XML
 * element named `expectedLocalName`, and consume it.
 */
export function consumeCloseTag(
{I}cursor: XmlCursor,
{I}expectedLocalName: string
): DeserializationError | null {{
{I}return consumeCloseTagInNamespace(cursor, expectedLocalName, NAMESPACE);
}}

function consumeCloseTagInNamespace(
{I}cursor: XmlCursor,
{I}expectedLocalName: string,
{I}expectedNamespace: string
): DeserializationError | null {{
{I}const closeTag = cursor.current();
{I}if (!(closeTag instanceof CloseTagToken)) {{
{II}return new DeserializationError(
{III}`Expected a closing element '${{expectedLocalName}}', ` +
{III}`but got token kind: ${{currentTokenKind(cursor)}}`
{II});
{I}}}

{I}const closeError = checkExpectedCloseTag(
{II}closeTag, expectedLocalName, expectedNamespace
{I});
{I}if (closeError !== null) {{
{II}return closeError;
{I}}}

{I}cursor.advance();
{I}return null;
}}

/**
 * Read the next non-ignorable token from `cursor`, expecting it to be
 * an opening XML element in the expected namespace.
 *
 * This is shared by the parsing of a single list item, a single tuple
 * item, and the dispatch-parsing of an interface.
 *
 * @param cursor - to read from
 * @returns the opening tag, or an error
 */
export function readNextOpenTag(
{I}cursor: XmlCursor
): AasCommon.Either<OpenTagToken, DeserializationError> {{
{I}return readNextOpenTagInNamespace(cursor, NAMESPACE);
}}

function readNextOpenTagInNamespace(
{I}cursor: XmlCursor,
{I}expectedNamespace: string
): AasCommon.Either<OpenTagToken, DeserializationError> {{
{I}cursor.skipIgnorable();
{I}const token = cursor.current();
{I}if (token === null) {{
{II}return newDeserializationError<OpenTagToken>(
{III}"Expected an XML element, but got end of token stream"
{II});
{I}}}
{I}if (!(token instanceof OpenTagToken)) {{
{II}return newDeserializationError<OpenTagToken>(
{III}`Expected an XML element, but got token kind: ${{token.kind}}`
{II});
{I}}}

{I}const namespaceError = checkExpectedOpenTagNamespace(
{II}token, expectedNamespace
{I});
{I}if (namespaceError !== null) {{
{II}return new AasCommon.Either<OpenTagToken, DeserializationError>(
{III}null,
{III}namespaceError
{II});
{I}}}

{I}return new AasCommon.Either<OpenTagToken, DeserializationError>(token, null);
}}

/**
 * Parse the content of the XML element which the caller has opened, and consume
 * the corresponding closing element named `localName`.
 *
 * This is the one thing which every value of an XML element has in common,
 * whatever it holds: the property loop of a class calls it directly, since
 * it has already read the opening tag and switched on its local name, and
 * `parseNamedElement` calls it after reading an opening tag of its own.
 *
 * A property loop assigns *both* halves of the result -- the value as well as
 * the error -- without looking at either first. The loop returns as soon as
 * the error is set, so the `null` value which comes with an error is never
 * read, and the property's variable needs no guard.
 *
 * @param cursor - to read from
 * @param localName - local name of the element which the caller has opened
 * @param parseContent - parses the content of the element
 * @returns parsed value, or an error
 * @typeParam T - type of the parsed value
 */
export function parseElementContent<T>(
{I}cursor: XmlCursor,
{I}localName: string,
{I}parseContent: ContentParser<T>
): AasCommon.Either<T, DeserializationError> {{
{I}return parseElementContentInNamespace(
{II}cursor, localName, parseContent, NAMESPACE
{I});
}}

function parseElementContentInNamespace<T>(
{I}cursor: XmlCursor,
{I}localName: string,
{I}parseContent: ContentParser<T>,
{I}expectedNamespace: string
): AasCommon.Either<T, DeserializationError> {{
{I}const parsedOrError = parseContent(cursor);
{I}if (parsedOrError.error !== null) {{
{II}return parsedOrError;
{I}}}

{I}const closeError = consumeCloseTagInNamespace(
{II}cursor, localName, expectedNamespace
{I});
{I}if (closeError !== null) {{
{II}return new AasCommon.Either<T, DeserializationError>(null, closeError);
{I}}}

{I}return parsedOrError;
}}

/**
 * Read the next XML element from `cursor`, expecting it to be named
 * `expectedLocalName`, parse its content with `parseContent` and consume
 * the matching closing element.
 *
 * This is what an item of a list or of a tuple is parsed with -- a scalar item
 * in an element tagged `"v"`, `"v1"`, `"v2"`, *etc.*, and an item whose concrete
 * class is statically known in an element named after that class. Rejecting
 * an unexpected element on its local name alone spares us parsing its full
 * (possibly deeply nested) content only to discover the mismatch afterwards.
 *
 * @param cursor - to read from
 * @param expectedLocalName - the expected local name of the element
 * @param parseContent - parses the content of the element
 * @returns parsed value, or an error
 * @typeParam T - type of the parsed value
 */
export function parseNamedElement<T>(
{I}cursor: XmlCursor,
{I}expectedLocalName: string,
{I}parseContent: ContentParser<T>
): AasCommon.Either<T, DeserializationError> {{
{I}return parseNamedElementInNamespace(
{II}cursor, expectedLocalName, parseContent, NAMESPACE
{I});
}}

function parseNamedElementInNamespace<T>(
{I}cursor: XmlCursor,
{I}expectedLocalName: string,
{I}parseContent: ContentParser<T>,
{I}expectedNamespace: string
): AasCommon.Either<T, DeserializationError> {{
{I}const startTagOrError = readNextOpenTagInNamespace(
{II}cursor, expectedNamespace
{I});
{I}if (startTagOrError.error !== null) {{
{II}return new AasCommon.Either<T, DeserializationError>(
{III}null,
{III}startTagOrError.error
{II});
{I}}}
{I}const startTag = startTagOrError.mustValue();

{I}const observedLocalName = localNameOfTag(startTag.tag);
{I}if (observedLocalName !== expectedLocalName) {{
{II}return newDeserializationError<T>(
{III}`Expected the element '${{expectedLocalName}}', ` +
{IIII}`but got '${{observedLocalName}}'`
{II});
{I}}}

{I}cursor.advance();

{I}return parseElementContentInNamespace(
{II}cursor, expectedLocalName, parseContent, expectedNamespace
{I});
}}

/**
 * Parse a sequence of list items from `cursor`, stopping (without consuming)
 * at the first closing element.
 *
 * The caller is expected to read and verify the property's own closing
 * element afterwards.
 *
 * @param cursor - to read from
 * @param parseItem - parses a single list item
 * @returns the parsed items, or an error
 * @typeParam T - type of a single list item
 */
export function parseList<T>(
{I}cursor: XmlCursor,
{I}parseItem: ContentParser<T>
): AasCommon.Either<Array<T>, DeserializationError> {{
{I}const items = new Array<T>();
{I}let itemIndex = 0;

{I}cursor.skipIgnorable();
{I}// eslint-disable-next-line no-constant-condition
{I}while (true) {{
{II}const maybeClose = cursor.current();
{II}if (maybeClose === null) {{
{III}return newDeserializationError<Array<T>>(
{IIII}"Expected an XML element corresponding to a list item " +
{IIIII}"or property closing element, but got end of token stream"
{III});
{II}}}

{II}if (maybeClose instanceof CloseTagToken) {{
{III}break;
{II}}}

{II}const itemOrError = parseItem(cursor);
{II}if (itemOrError.error !== null) {{
{III}itemOrError.error.path.prepend(new IndexSegment(itemIndex));
{III}return new AasCommon.Either<Array<T>, DeserializationError>(
{IIII}null,
{IIII}itemOrError.error
{III});
{II}}}

{II}items.push(itemOrError.mustValue());
{II}itemIndex++;
{II}cursor.skipIgnorable();
{I}}}

{I}return new AasCommon.Either<Array<T>, DeserializationError>(items, null);
}}

/**
 * Cursor over parsed XML SAX tokens.
 */
export class XmlCursor {{
{I}private readonly _tokens: Array<XmlAnyToken>;
{I}private _index = 0;

{I}constructor(tokens: Array<XmlAnyToken>) {{
{II}this._tokens = tokens;
{I}}}

{I}current(): XmlAnyToken | null {{
{II}if (this._index >= this._tokens.length) {{
{III}return null;
{II}}}
{II}return this._tokens[this._index];
{I}}}

{I}advance(): void {{
{II}if (this._index < this._tokens.length) {{
{III}this._index++;
{II}}}
{I}}}

{I}skipIgnorable(): void {{
{II}// eslint-disable-next-line no-constant-condition
{II}while (true) {{
{III}const token = this.current();
{III}if (token === null) {{
{IIII}break;
{III}}}

{III}if (token instanceof CommentToken) {{
{IIII}this.advance();
{IIII}continue;
{III}}}

{III}if (token instanceof TextToken || token instanceof CdataToken) {{
{IIII}if (token.text.trim().length === 0) {{
{IIIII}this.advance();
{IIIII}continue;
{IIII}}}
{III}}}

{III}break;
{II}}}
{I}}}
}}

export function tokenizeXml(
{I}xml: string
): AasCommon.Either<Array<XmlAnyToken>, DeserializationError> {{
{I}const parser = new XmlSaxParser({{ allowDoctype: false, xmlns: true }});
{I}const tokens = new Array<XmlAnyToken>();

{I}try {{
{II}for (const token of parser.feed(xml)) {{
{III}tokens.push(token);
{II}}}
{II}for (const token of parser.close()) {{
{III}if (!(token instanceof EndToken)) {{
{IIII}tokens.push(token);
{III}}}
{II}}}
{I}}} catch (error) {{
{II}return newDeserializationError<Array<XmlAnyToken>>(
{III}`Failed to parse XML: ${{error}}`
{II});
{I}}}

{I}return new AasCommon.Either<Array<XmlAnyToken>, DeserializationError>(
{II}tokens,
{II}null
{I});
}}

export function readRequiredRootOpenTag(
{I}cursor: XmlCursor
): AasCommon.Either<OpenTagToken, DeserializationError> {{
{I}cursor.skipIgnorable();

{I}const token = cursor.current();
{I}if (token === null) {{
{II}return newDeserializationError<OpenTagToken>(
{III}"Expected a root XML element, but got an empty token stream"
{II});
{I}}}

{I}if (!(token instanceof OpenTagToken)) {{
{II}return newDeserializationError<OpenTagToken>(
{III}`Expected a root XML start element, but got token kind: ${{token.kind}}`
{II});
{I}}}

{I}const namespaceError = checkExpectedOpenTagNamespace(token, NAMESPACE);
{I}if (namespaceError !== null) {{
{II}return new AasCommon.Either<OpenTagToken, DeserializationError>(
{III}null,
{III}namespaceError
{II});
{I}}}

{I}cursor.advance();

{I}return new AasCommon.Either<OpenTagToken, DeserializationError>(
{II}token,
{II}null
{I});
}}

/**
 * Match a run of the four characters which XML calls whitespace.
 */
const WHITESPACE_RUN = /[ \\t\\n\\r]+/g;

/**
 * Normalize `text` the way `whiteSpace="collapse"` prescribes.
 *
 * Every atomic XSD type except a string, and every type derived from one by
 * restriction, fixes `whiteSpace` to `collapse`, and a schema author can not
 * change it. A tab, a line feed and a carriage return each become a space,
 * a run of spaces becomes one space, and the leading and trailing spaces go.
 * Only the result of that is a lexical representation to be matched.
 *
 * Mind that this strips only the whitespace *around* the value: a space
 * within it survives as a single space, so `2  3` becomes `2 3`, which is
 * still no number.
 *
 * See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace
 */
export function collapseWhitespace(text: string): string {{
{I}return text.replace(WHITESPACE_RUN, " ").trim();
}}

/**
 * Tell whether `text` is a lexical form of `xs:base64Binary`.
 *
 * The whitespace is expected to be gone already. What is left has to match
 * `(B64 B64 B64 B64)* ((B64 B64 B64 B64) | (B64 B64 B16 "=") | (B64 B04 "=="))?`
 * -- a length which is a multiple of four, the alphabet and nothing else,
 * an equals sign only at the very end, and, easily missed, a constrained
 * character *before* the padding, as the bits which the padding drops have
 * to be zero.
 *
 * The decoders do not agree on any of this, so every target does the same
 * check of its own and refuses the same texts.
 *
 * See: https://www.w3.org/TR/xmlschema-2/#base64Binary
 */
export function matchesXsBase64Binary(text: string): boolean {{
{I}if (text.length % 4 !== 0) {{
{II}return false;
{I}}}

{I}if (text.length === 0) {{
{II}return true;
{I}}}

{I}let pads = 0;
{I}if (text[text.length - 1] === "=") {{
{II}pads = 1;
{II}if (text[text.length - 2] === "=") {{
{III}pads = 2;
{II}}}
{I}}}

{I}for (let i = 0; i < text.length - pads; i++) {{
{II}const character = text[i];
{II}const inAlphabet =
{III}(character >= "A" && character <= "Z") ||
{III}(character >= "a" && character <= "z") ||
{III}(character >= "0" && character <= "9") ||
{III}character === "+" ||
{III}character === "/";
{II}if (!inAlphabet) {{
{III}return false;
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// Only these sixteen characters leave the two dropped bits at zero, and
{I}// only these four leave the four dropped bits at zero.
{I}if (pads === 1) {{
{II}return "AEIMQUYcgkosw048".includes(text[text.length - 2]);
{I}}}

{I}if (pads === 2) {{
{II}return "AQgw".includes(text[text.length - 3]);
{I}}}

{I}return true;
}}

/**
 * Drop every whitespace character of `text`.
 *
 * This is what `xs:base64Binary` needs: it allows whitespace between
 * the characters and not only around them, so collapsing is not enough --
 * the decoder accepts none of it.
 */
export function removeWhitespace(text: string): string {{
{I}return text.replace(WHITESPACE_RUN, "");
}}

/**
 * Consume the text (or CDATA) content at `cursor`, if any.
 *
 * The caller is responsible for reading and verifying the closing element
 * afterwards.
 */
export function parseTextContent(cursor: XmlCursor): string {{
{I}cursor.skipIgnorable();

{I}let text = "";
{I}const maybeText = cursor.current();
{I}if (maybeText instanceof TextToken || maybeText instanceof CdataToken) {{
{II}text = maybeText.text;
{II}cursor.advance();
{II}cursor.skipIgnorable();
{I}}}

{I}return text;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write the content of an XML element -- everything between its opening and its
 * closing tag -- into `parts`.
 *
 * @remarks
 *
 * This is the one shape which every writer wears, so that a writer can be given
 * to another writer as its item writer. The framing of the element around such
 * a content is written by {{@link writeElement}}, and only there.
 *
 * The content is pushed as one or more separate entries instead of being
 * concatenated as it is produced, so that the single `parts.join("")` at the very
 * end copies every piece of text exactly once, however deeply it is nested.
 */
export type ContentWriter<T> = (parts: Array<string>, value: T) => void;

/**
 * Write `value` as the XML element `localName`, its content written
 * by `writeContent`.
 *
 * @remarks
 *
 * The root element, and only the root element, declares the XML namespace. It is
 * by definition the first element to be written, so `parts` is still empty when
 * we push its opening tag, and we need no flag threaded through the writers to
 * tell it apart.
 */
export function writeElement<T>(
{I}parts: Array<string>,
{I}localName: string,
{I}value: T,
{I}writeContent: ContentWriter<T>
): void {{
{I}parts.push(
{II}parts.length === 0
{III}? `<${{localName}} xmlns="${{NAMESPACE}}">`
{III}: `<${{localName}}>`
{I});
{I}writeContent(parts, value);
{I}parts.push(`</${{localName}}>`);
}}

/**
 * Write `value`, a property of the instance being serialized, as the XML element
 * `elementName`.
 *
 * @remarks
 *
 * This is {{@link writeElement}} plus the reporting: a failure anywhere beneath
 * this property is reported at a path which begins with the property. The framing
 * of an *item* of a list or of a tuple deliberately goes through
 * {{@link writeElement}} instead, as an item is reported by its index.
 *
 * The path names the TypeScript property, and not the XML element: a failed
 * serialization is reported on an *instance*, which the caller holds, and not on
 * a document which has not been written yet. The two names part company only
 * where the meta-model prescribes a serialization name of its own, so
 * `propertyName` falls back to `elementName` and is spelled out at those
 * properties alone.
 */
export function writeProperty<T>(
{I}parts: Array<string>,
{I}elementName: string,
{I}value: T,
{I}writeContent: ContentWriter<T>,
{I}propertyName: string = elementName
): void {{
{I}try {{
{II}writeElement(parts, elementName, value, writeContent);
{I}}} catch (error) {{
{II}if (error instanceof SerializationError) {{
{III}error.prependProperty(propertyName);
{II}}}
{II}throw error;
{I}}}
}}

/**
 * Write `value`, a property of the instance being serialized, as the XML element
 * `elementName` if it has been given, and write nothing at all otherwise.
 */
export function writeOptionalProperty<T>(
{I}parts: Array<string>,
{I}elementName: string,
{I}value: T | null,
{I}writeContent: ContentWriter<T>,
{I}propertyName: string = elementName
): void {{
{I}if (value !== null) {{
{II}writeProperty(parts, elementName, value, writeContent, propertyName);
{I}}}
}}

/**
 * Write the items of `values`, each as its own whole XML element.
 *
 * @remarks
 *
 * The index is advanced only after an item has been written, so that a failure is
 * reported at the item which actually failed.
 */
export function writeList<T>(
{I}parts: Array<string>,
{I}values: Array<T>,
{I}writeItemElement: ContentWriter<T>
): void {{
{I}let index = 0;
{I}try {{
{II}for (const value of values) {{
{III}writeItemElement(parts, value);
{III}index++;
{II}}}
{I}}} catch (error) {{
{II}if (error instanceof SerializationError) {{
{III}error.prependIndex(index);
{II}}}
{II}throw error;
{I}}}
}}

export function escapeXmlText(text: string): string {{
{I}return text
{II}.replace(/&/g, "&amp;")
{II}.replace(/</g, "&lt;")
{II}.replace(/>/g, "&gt;")
{II}.replace(/\"/g, "&quot;")
{II}.replace(/'/g, "&apos;");
}}"""
        ),
        *in_no_namespace_blocks,
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
assert __doc__ is not None
