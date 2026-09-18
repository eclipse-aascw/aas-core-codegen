"""Generate code to test the XML de/serialization of concrete classes."""

import io
from typing import Dict, List, Mapping, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, Identifier
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


#: The lexical forms which no recorded example can hold, by the primitive they
#: belong to. A recorded example has to serialize back to itself, character for
#: character, so it can hold neither a value written in another form than it
#: was read nor one whose written form the targets spell differently.
_LEXICAL_CASES_BY_PRIMITIVE = {
    intermediate.PrimitiveType.FLOAT: [
        # NOTE (mristin):
        # A literal too large for a double is not an error: XSD rounds it to
        # an infinity, and one too small to zero.
        #
        # See: https://www.w3.org/TR/xmlschema11-2/#double
        ("1e400", "Infinity"),
        ("-1e400", "-Infinity"),
        ("1e-400", "0"),
        ("INF", "Infinity"),
        ("+INF", "Infinity"),
        ("-INF", "-Infinity"),
    ],
    intermediate.PrimitiveType.BYTEARRAY: [
        # NOTE (mristin):
        # ``xs:base64Binary`` admits whitespace *between* the characters and
        # not only around them, and an empty value stands for zero bytes.
        # Neither can be a recorded example: the first is written back without
        # the space, and the second as an empty element.
        #
        # See: https://www.w3.org/TR/xmlschema-2/#base64Binary
        ("SGk=", "new Uint8Array([72, 105])"),
        ("SG k=", "new Uint8Array([72, 105])"),
        ("S G k =", "new Uint8Array([72, 105])"),
        ("", "new Uint8Array([])"),
    ],
    intermediate.PrimitiveType.BOOL: [
        # NOTE (mristin):
        # ``xs:boolean`` spells the two values in four ways, not two.
        ("1", "true"),
        ("0", "false"),
        ("true", "true"),
        ("false", "false"),
    ],
}  # type: Mapping[intermediate.PrimitiveType, List[Tuple[str, str]]]


def _generate_lexical_tests(symbol_table: intermediate.SymbolTable) -> List[Stripped]:
    """Generate the tests over the lexical forms which no example can hold."""
    cls = intermediate.first_class_of_only_required_primitives(symbol_table)
    if cls is None:
        return []

    prop_by_a_type = (
        dict()
    )  # type: Dict[intermediate.PrimitiveType, intermediate.Property]
    for prop in cls.properties:
        assert isinstance(prop.type_annotation, intermediate.PrimitiveTypeAnnotation)
        prop_by_a_type.setdefault(prop.type_annotation.a_type, prop)

    relevant = [
        (a_type, prop_by_a_type[a_type])
        for a_type in (
            intermediate.PrimitiveType.FLOAT,
            intermediate.PrimitiveType.BOOL,
            intermediate.PrimitiveType.BYTEARRAY,
        )
        if a_type in prop_by_a_type
    ]

    if len(relevant) == 0:
        return []

    cls_name_typescript = typescript_naming.class_name(cls.name)
    cls_name_xml = naming.xml_class_name(cls.name)
    as_function = typescript_naming.function_name(Identifier(f"as_{cls.name}"))

    result = [
        Stripped(
            f"""\
/**
 * Read the first recorded example of {cls_name_typescript} with the content
 * of the element `xmlName` replaced by `text`.
 */
function readWith(xmlName: string, text: string): AasTypes.{cls_name_typescript} {{
{I}const pths = Array.from(
{II}TestCommon.findFilesBySuffixRecursively(
{III}path.join(
{IIII}TestCommon.TEST_DATA_DIR,
{IIII}"Xml",
{IIII}"Expected",
{IIII}{typescript_common.string_literal(cls_name_xml)}
{III}),
{III}".xml"
{II})
{I});
{I}pths.sort();

{I}expect(pths.length).toBeGreaterThan(0);

{I}const original = fs.readFileSync(pths[0], "utf-8");

{I}const start = original.indexOf(`<${{xmlName}}>`) + xmlName.length + 2;
{I}const end = original.indexOf(`</${{xmlName}}>`);

{I}const patched = original.slice(0, start) + text + original.slice(end);

{I}const instanceOrError = AasXmlization.fromXmlString(patched);
{I}expect(instanceOrError.error).toBeNull();

{I}const casted = AasTypes.{as_function}(instanceOrError.mustValue());
{I}if (casted === null) {{
{II}throw new Error(`Expected an instance of {cls_name_typescript}`);
{I}}}

{I}return casted;
}}"""
        )
    ]  # type: List[Stripped]

    for a_type, prop in relevant:
        prop_xml_name = naming.xml_property(prop.name)
        prop_name = typescript_naming.property_name(prop.name)

        # NOTE (mristin):
        # A byte array is compared element by element, and not by its
        # identity, which is what ``toBe`` would do.
        matcher = (
            ".toEqual" if a_type is intermediate.PrimitiveType.BYTEARRAY else ".toBe"
        )

        for a_text, expected in _LEXICAL_CASES_BY_PRIMITIVE[a_type]:
            result.append(
                Stripped(
                    f"""\
test({typescript_common.string_literal(f"{prop_xml_name} read from {a_text!r}")}, () => {{
{I}const instance = readWith(
{II}{typescript_common.string_literal(prop_xml_name)},
{II}{typescript_common.string_literal(a_text)}
{I});
{I}expect(instance.{prop_name}){matcher}({expected});
}});"""
                )
            )

    return result


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test the XML de/serialization of concrete classes."""
    blocks = [
        Stripped(
            """\
/**
 * Test XML de/serialization of concrete classes.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as fs from "fs";
import * as path from "path";

import * as AasXmlization from "../src/xmlization";
import * as AasTypes from "../src/types";
import * as AasVerification from "../src/verification";

import * as TestCommon from "./common";"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)
        cls_name_xml = naming.xml_class_name(concrete_cls.name)
        as_function = typescript_naming.function_name(
            Identifier(f"as_{concrete_cls.name}")
        )

        blocks.append(
            Stripped(
                f"""\
test("{cls_name_typescript} XML round-trip OK", () => {{
{I}const pths = Array.from(
{II}TestCommon.findFilesBySuffixRecursively(
{III}path.join(
{IIII}TestCommon.TEST_DATA_DIR,
{IIII}"Xml",
{IIII}"Expected",
{IIII}{typescript_common.string_literal(cls_name_xml)}
{III}),
{III}".xml"
{II})
{I});
{I}pths.sort();

{I}for (const pth of pths) {{
{II}const text = fs.readFileSync(pth, "utf-8");

{II}const instanceOrError = AasXmlization.fromXmlString(text);
{II}expect(instanceOrError.error).toBeNull();
{II}const instance = instanceOrError.mustValue();

{II}const casted = AasTypes.{as_function}(instance);
{II}if (casted === null) {{
{III}throw new Error(
{IIII}`Expected instance of {cls_name_typescript} in ${{pth}}, ` +
{IIII}`but got: ${{typeof instance}}`
{III});
{II}}}

{II}TestCommon.assertNoVerificationErrors(AasVerification.verify(casted), pth);

{II}const roundTripText = AasXmlization.toXmlString(casted);
{II}expect(roundTripText.length).toBeGreaterThan(0);
{I}}}
}});"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
test("{cls_name_typescript} XML deserialization fail", () => {{
{I}for (
{II}const causeDir of
{II}TestCommon.findImmediateSubdirectories(
{III}path.join(
{IIII}TestCommon.TEST_DATA_DIR,
{IIII}"Xml",
{IIII}"Unexpected",
{IIII}"Unserializable"
{III})
{II})
{I}) {{
{II}const clsDir = path.join(
{III}causeDir,
{III}{typescript_common.string_literal(cls_name_xml)}
{II});
{II}if (!fs.existsSync(clsDir)) {{
{III}continue;
{II}}}

{II}const pths = Array.from(
{III}TestCommon.findFilesBySuffixRecursively(
{IIII}clsDir,
{IIII}".xml"
{III})
{II});
{II}pths.sort();

{II}for (const pth of pths) {{
{III}const text = fs.readFileSync(pth, "utf-8");
{III}const instanceOrError = AasXmlization.fromXmlString(text);
{III}expect(instanceOrError.error).not.toBeNull();
{II}}}
{I}}}
}});"""
            )
        )

    blocks.extend(_generate_lexical_tests(symbol_table))

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
