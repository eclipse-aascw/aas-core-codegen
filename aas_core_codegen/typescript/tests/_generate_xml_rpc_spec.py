"""Generate code for the tests of the XML-RPC subset in isolation."""

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
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code for the tests of the XML-RPC subset in isolation."""
    namespace_literal = typescript_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    blocks = [
        Stripped(
            """\
/**
 * Test the XML-RPC subset which carries the JSON-able values in isolation.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasCommon from "../src/common";
import * as AasTypes from "../src/types";
import * as AasXmlCommon from "../src/xmlcommon";
import * as AasXmlRpc from "../src/xmlrpc";"""
        ),
        Stripped(f"""const NAMESPACE = {namespace_literal};"""),
        Stripped(
            f"""\
/**
 * Tokenize `text` and consume the opening tag of its root element.
 *
 * @remarks
 *
 * The module under test expects a cursor which already stands *inside* the
 * element whose content it is to read, exactly as the de/serialization of
 * the model hands it over.
 */
function enter(text: string): AasXmlCommon.XmlCursor {{
{I}const tokensOrError = AasXmlCommon.tokenizeXml(text);
{I}if (tokensOrError.error !== null) {{
{II}throw new Error(
{III}`Expected a well-formed XML, but got: ${{tokensOrError.error.message}}`
{II});
{I}}}

{I}const cursor = new AasXmlCommon.XmlCursor(tokensOrError.mustValue());

{I}const rootOrError = AasXmlCommon.readRequiredRootOpenTag(cursor);
{I}if (rootOrError.error !== null) {{
{II}throw new Error(
{III}`Expected a root element, but got: ${{rootOrError.error.message}}`
{II});
{I}}}

{I}return cursor;
}}

/**
 * Assert that `parsed` failed and give out its error.
 */
function mustError(
{I}parsed: AasCommon.Either<unknown, AasXmlCommon.DeserializationError>
): AasXmlCommon.DeserializationError {{
{I}const error = parsed.error;
{I}if (error === null) {{
{II}throw new Error("Expected an error, but the parsing succeeded");
{I}}}
{I}return error;
}}"""
        ),
        Stripped(
            f"""\
test("a value round-trips through every discriminator", () => {{
{I}const cursor = enter(
{II}`<v xmlns="${{NAMESPACE}}"><struct xmlns="">` +
{III}"<member><name>b</name><value><boolean>1</boolean></value></member>" +
{III}"<member><name>f</name><value><double>1.5</double></value></member>" +
{III}"<member><name>s</name><value><string>x</string></value></member>" +
{III}"<member><name>a</name><value><array><data>" +
{IIII}"<value><double>0</double></value>" +
{III}"</data></array></value></member>" +
{III}"</struct></v>"
{I});

{I}const parsed = AasXmlRpc.parseValueContent(cursor);

{I}expect(parsed.error).toBeNull();
{I}expect(parsed.mustValue()).toStrictEqual({{
{II}b: true,
{II}f: 1.5,
{II}s: "x",
{II}a: [0]
{I}}});
}});"""
        ),
        Stripped(
            f"""\
test("the discriminator is a step of the path", () => {{
{I}const cursor = enter(
{II}`<v xmlns="${{NAMESPACE}}"><boolean xmlns="">yes</boolean></v>`
{I});

{I}const parsed = AasXmlRpc.parseValueContent(cursor);

{I}expect(parsed.error).not.toBeNull();
{I}expect(mustError(parsed).path.toString()).toStrictEqual("boolean");
}});"""
        ),
        Stripped(
            f"""\
test("an element which is no discriminator gets no step", () => {{
{I}// NOTE (mristin):
{I}// It is this very element which does not belong here, so naming it in
{I}// the path as well as in the message would say nothing more.
{I}const cursor = enter(`<v xmlns="${{NAMESPACE}}"><oops xmlns=""/></v>`);

{I}const parsed = AasXmlRpc.parseValueContent(cursor);

{I}expect(parsed.error).not.toBeNull();
{I}expect(mustError(parsed).path.toString()).toStrictEqual("");
{I}expect(mustError(parsed).message).toContain("but got: 'oops'");
}});"""
        ),
        Stripped(
            f"""\
test("the path into a nested value", () => {{
{I}const cursor = enter(
{II}`<v xmlns="${{NAMESPACE}}"><struct xmlns="">` +
{III}"<member><name>nested</name><value><array><data>" +
{IIII}"<value><double>0</double></value>" +
{IIII}"<value><string><oops/></string></value>" +
{III}"</data></array></value></member>" +
{III}"</struct></v>"
{I});

{I}const parsed = AasXmlRpc.parseValueContent(cursor);

{I}expect(parsed.error).not.toBeNull();
{I}expect(mustError(parsed).path.toString()).toStrictEqual(
{II}'struct/member[name="nested"]/value/array/data/*[1]/string'
{I});
}});"""
        ),
        Stripped(
            f"""\
test("the array body is entered without its wrapper", () => {{
{I}// NOTE (mristin):
{I}// A `JSONArray` property is represented by a `<data>` element directly,
{I}// with no `<array>` element around it, so the path has none either.
{I}const cursor = enter(
{II}`<v xmlns="${{NAMESPACE}}"><data xmlns="">` +
{III}"<value><boolean>yes</boolean></value>" +
{III}"</data></v>"
{I});

{I}const parsed = AasXmlRpc.parseArrayBody(cursor);

{I}expect(parsed.error).not.toBeNull();
{I}expect(mustError(parsed).path.toString()).toStrictEqual("data/*[0]/boolean");
}});"""
        ),
        Stripped(
            f"""\
test("the struct body is entered without its wrapper", () => {{
{I}// NOTE (mristin):
{I}// A `JSONObject` property is represented by its `<member>` elements
{I}// directly, with no `<struct>` element around them.
{I}const cursor = enter(
{II}`<v xmlns="${{NAMESPACE}}">` +
{III}'<member xmlns=""><name>k</name><value><oops/></value></member>' +
{III}"</v>"
{I});

{I}const parsed = AasXmlRpc.parseStructBody(cursor);

{I}expect(parsed.error).not.toBeNull();
{I}expect(mustError(parsed).path.toString()).toStrictEqual(
{II}'member[name="k"]/value'
{I});
}});"""
        ),
        Stripped(
            f"""\
test("the key of a member is escaped in the path", () => {{
{I}const cursor = enter(
{II}`<v xmlns="${{NAMESPACE}}">` +
{III}'<member xmlns=""><name>a&amp;b/c&lt;d</name>' +
{III}"<value><oops/></value></member>" +
{III}"</v>"
{I});

{I}const parsed = AasXmlRpc.parseStructBody(cursor);

{I}expect(parsed.error).not.toBeNull();
{I}expect(mustError(parsed).path.toString()).toStrictEqual(
{II}'member[name="a&amp;b&#47;c&lt;d"]/value'
{I});
}});"""
        ),
        Stripped(
            f"""\
test("a repeated member is refused", () => {{
{I}const cursor = enter(
{II}`<v xmlns="${{NAMESPACE}}">` +
{III}'<member xmlns=""><name>k</name><value><double>1</double></value></member>' +
{III}'<member xmlns=""><name>k</name><value><double>2</double></value></member>' +
{III}"</v>"
{I});

{I}const parsed = AasXmlRpc.parseStructBody(cursor);

{I}expect(parsed.error).not.toBeNull();
{I}expect(mustError(parsed).path.toString()).toStrictEqual('member[name="k"]');
{I}expect(mustError(parsed).message).toStrictEqual(
{II}"The member occurred more than once"
{I});
}});"""
        ),
        Stripped(
            f"""\
test("neither an infinity nor a not-a-number is read", () => {{
{I}for (const text of ["INF", "-INF", "NaN", "Infinity", "1e400"]) {{
{II}const cursor = enter(
{III}`<v xmlns="${{NAMESPACE}}"><double xmlns="">${{text}}</double></v>`
{II});

{II}const parsed = AasXmlRpc.parseValueContent(cursor);

{II}expect(parsed.error).not.toBeNull();
{II}expect(mustError(parsed).path.toString()).toStrictEqual("double");
{I}}}
}});"""
        ),
        Stripped(
            f"""\
test("a value is written with its discriminator", () => {{
{I}const cases: Array<[AasTypes.JsonValue, string]> = [
{II}[true, '<boolean xmlns="">1</boolean>'],
{II}[false, '<boolean xmlns="">0</boolean>'],
{II}[1, '<double xmlns="">1</double>'],
{II}[1.5, '<double xmlns="">1.5</double>'],
{II}["a<b&c", '<string xmlns="">a&lt;b&amp;c</string>'],
{II}[
{III}[0],
{III}'<array xmlns=""><data><value><double>0</double></value></data></array>'
{II}],
{II}[
{III}{{ k: 0 }},
{III}'<struct xmlns=""><member><name>k</name>' +
{IIII}"<value><double>0</double></value></member></struct>"
{II}]
{I}];

{I}for (const [value, expected] of cases) {{
{II}const parts = new Array<string>();
{II}AasXmlRpc.writeValueContent(parts, value);
{II}expect(parts.join("")).toStrictEqual(expected);
{I}}}
}});"""
        ),
        Stripped(
            f"""\
test("the path of a failed write points into the value", () => {{
{I}const parts = new Array<string>();

{I}expect(() =>
{II}AasXmlRpc.writeStructBody(parts, {{
{III}"a b": [0, Number.POSITIVE_INFINITY]
{II}}})
{I}).toThrow(AasXmlCommon.SerializationError);

{I}try {{
{II}AasXmlRpc.writeStructBody(new Array<string>(), {{
{III}"a b": [0, Number.POSITIVE_INFINITY]
{II}}});
{I}}} catch (error) {{
{II}expect(error).toBeInstanceOf(AasXmlCommon.SerializationError);
{II}expect((error as AasXmlCommon.SerializationError).path).toStrictEqual(
{III}'["a b"][1]'
{II});
{I}}}
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
