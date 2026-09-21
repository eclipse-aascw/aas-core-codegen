"""Generate code for basic XMLization helper and malformed-input tests."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import common as typescript_common
from aas_core_codegen.typescript.common import INDENT as I, INDENT2 as II


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate() -> str:
    """Generate code for basic XMLization helper and malformed-input tests."""
    blocks = [
        Stripped(
            """\
/**
 * Test basic XMLization helper classes and malformed XML inputs.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasXmlization from "../src/xmlization";"""
        ),
        Stripped(
            f"""\
test("xmlization path renders as a relative XPath", () => {{
{I}const path = new AasXmlization.Path();

{I}path.prepend(new AasXmlization.IndexSegment(3));
{I}path.prepend(new AasXmlization.ElementSegment("something"));

{I}expect(path.toString()).toStrictEqual("something/*[3]");
}});

test("xmlization key segment renders as a predicate on the name", () => {{
{I}const path = new AasXmlization.Path();

{I}path.prepend(new AasXmlization.ElementSegment("value"));
{I}path.prepend(new AasXmlization.KeySegment("a \\"tricky\\" <key>"));
{I}path.prepend(new AasXmlization.ElementSegment("struct"));

{I}expect(path.toString()).toStrictEqual(
{II}"struct/member[name=\\"a &quot;tricky&quot; &lt;key&gt;\\"]/value"
{I});
}});"""
        ),
        Stripped(
            f"""\
test("xmlization errors default to empty path", () => {{
{I}const deserializationError = new AasXmlization.DeserializationError("broken XML");
{I}expect(deserializationError.message).toStrictEqual("broken XML");
{I}expect(deserializationError.path.toString()).toStrictEqual("");

{I}const serializationError = new AasXmlization.SerializationError("broken object graph");
{I}expect(serializationError.message).toStrictEqual("broken object graph");
{I}expect(serializationError.path).toStrictEqual("");
}});

test("xmlization serialization path renders as an access expression", () => {{
{I}const error = new AasXmlization.SerializationError("broken object graph");

{I}error.prependKey("a b");
{I}error.prependIndex(3);
{I}error.prependProperty("something");

{I}expect(error.path).toStrictEqual('.something[3]["a b"]');
}});"""
        ),
        Stripped(
            f"""\
test("xmlization fails on malformed XML", () => {{
{I}const malformedXml = "<something><notClosed>";
{I}const instanceOrError = AasXmlization.fromXmlString(malformedXml);
{I}expect(instanceOrError.error).not.toBeNull();
}});"""
        ),
        Stripped(
            f"""\
test("xmlization fails on empty XML", () => {{
{I}const instanceOrError = AasXmlization.fromXmlString("");
{I}expect(instanceOrError.error).not.toBeNull();
}});"""
        ),
        Stripped(
            f"""\
test("xmlization fails on non-XML text", () => {{
{I}const instanceOrError = AasXmlization.fromXmlString("Definitely not XML");
{I}expect(instanceOrError.error).not.toBeNull();
}});"""
        ),
    ]  # type: List[Stripped]

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
