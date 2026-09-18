"""Generate code for targeted negative XML de-serialization tests."""

import io
from typing import List, Optional, Tuple

from icontract import ensure, require

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import common as typescript_common
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _first_atomic_list_property_candidate(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Tuple[intermediate.ConcreteClass, intermediate.Property]]:
    """Find a class with a list property whose XML items should be tagged as ``v``."""
    for concrete_cls in symbol_table.concrete_classes:
        for prop in concrete_cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)
            if not isinstance(type_anno, intermediate.ListTypeAnnotation):
                continue

            items = type_anno.items
            if not isinstance(
                items,
                (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
            ):
                continue

            if isinstance(items, intermediate.OurTypeAnnotation) and isinstance(
                items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                continue

            return concrete_cls, prop

    return None


def _first_nested_class_dispatch_candidate(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Tuple[intermediate.ConcreteClass, intermediate.Property]]:
    """Find a property parsed through ``parsePropertyAsClassInstance``."""
    for concrete_cls in symbol_table.concrete_classes:
        for prop in concrete_cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)
            if not isinstance(type_anno, intermediate.OurTypeAnnotation):
                continue

            if not isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                continue

            if (
                isinstance(type_anno.our_type, intermediate.ConcreteClass)
                and len(type_anno.our_type.concrete_descendants) == 0
            ):
                continue

            return concrete_cls, prop

    return None


@require(lambda cls, prop: id(prop) in cls.property_id_set)
def _generate_duplicate_property_test(
    cls: intermediate.ConcreteClass, prop: intermediate.Property
) -> Stripped:
    cls_xml_name = naming.xml_class_name(cls.name)
    cls_xml_name_literal = typescript_common.string_literal(cls_xml_name)

    prop_xml_name = prop.xml_name
    prop_xml_literal = typescript_common.string_literal(prop_xml_name)

    return Stripped(
        f"""\
test("XML duplicate property fails", () => {{
{I}const propertyName = {prop_xml_literal};

{I}const pth = path.join(
{II}TestCommon.TEST_DATA_DIR, "Xml", "Expected", {cls_xml_name_literal}, "minimal.xml"
{I});
{I}const [document, parseError] = parseXml(fs.readFileSync(pth, "utf-8"));
{I}if (parseError !== null) {{
{II}throw new Error(`Invalid XML fixture: ${{parseError}}`);
{I}}}

{I}const root = document.documentElement;
{I}if (root.tagName !== {cls_xml_name_literal}) {{
{II}throw new Error(
{III}`Expected root element <{cls_xml_name}>, ` +
{III}`got <${{root.tagName}}>`
{II});
{I}}}

{I}const property = Array.from(root.children).find(
{II}(child) => child.tagName === propertyName
{I});

{I}if (property === undefined) {{
{II}throw new Error(`Failed to find property element: ${{propertyName}}`);
{I}}}

{I}root.appendChild(property.cloneNode(true));

{I}const brokenText = new XMLSerializer().serializeToString(document);

{I}expectDeserializationError(brokenText);
}});"""
    )


@require(lambda cls, prop: id(prop) in cls.property_id_set)
def _generate_invalid_item_delimiter(
    cls: intermediate.ConcreteClass,
    prop: intermediate.Property,
) -> Stripped:
    cls_xml_name = naming.xml_class_name(cls.name)
    cls_xml_name_literal = typescript_common.string_literal(cls_xml_name)

    prop_xml_name = prop.xml_name
    prop_xml_name_literal = typescript_common.string_literal(prop_xml_name)

    return Stripped(
        f"""\
test("XML list item element name mismatch fails", () => {{
{I}const propertyName = {prop_xml_name_literal};

{I}const pth = path.join(
{II}TestCommon.TEST_DATA_DIR, "Xml", "Expected", {cls_xml_name_literal}, "maximal.xml"
{I});
{I}const [document, parseError] = parseXml(fs.readFileSync(pth, "utf-8"));
{I}if (parseError !== null) {{
{II}throw new Error(`Invalid XML fixture: ${{parseError}}`);
{I}}}

{I}const root = document.documentElement;
{I}if (root.tagName !== {cls_xml_name_literal}) {{
{II}throw new Error(
{III}`Expected root element <{cls_xml_name}>, ` +
{III}`got <${{root.tagName}}>`
{II});
{I}}}

{I}const property = Array.from(root.children).find(
{II}(child) => child.tagName === propertyName
{I});

{I}if (property === undefined) {{
{II}throw new Error(`Failed to find property element: ${{propertyName}}`);
{I}}}

{I}const invalidItem = document.createElement("invalidListItem");
{I}invalidItem.textContent = "so wrong";
{I}property.appendChild(invalidItem);

{I}const brokenText = new XMLSerializer().serializeToString(document);

{I}expectDeserializationError(brokenText);
}});"""
    )


@require(lambda cls, prop: id(prop) in cls.property_id_set)
def _generate_nested_class_dispatch_mismatch(
    cls: intermediate.ConcreteClass,
    prop: intermediate.Property,
) -> Stripped:
    cls_xml_name = naming.xml_class_name(cls.name)
    cls_xml_name_literal = typescript_common.string_literal(cls_xml_name)

    prop_xml_name = prop.xml_name
    prop_xml_name_literal = typescript_common.string_literal(prop_xml_name)

    return Stripped(
        f"""\
test("XML nested class dispatch mismatch fails", () => {{
{I}const propertyName = {prop_xml_name_literal};

{I}const pth = path.join(
{II}TestCommon.TEST_DATA_DIR, "Xml", "Expected", {cls_xml_name_literal}, "maximal.xml"
{I});
{I}const [document, parseError] = parseXml(fs.readFileSync(pth, "utf-8"));
{I}if (parseError !== null) {{
{II}throw new Error(`Invalid XML fixture: ${{parseError}}`);
{I}}}

{I}const root = document.documentElement;
{I}if (root.tagName !== {cls_xml_name_literal}) {{
{II}throw new Error(
{III}`Expected root element <{cls_xml_name}>, ` +
{III}`got <${{root.tagName}}>`
{II});
{I}}}

{I}const property = Array.from(root.children).find(
{II}(child) => child.tagName === propertyName
{I});

{I}if (property === undefined) {{
{II}throw new Error(`Failed to find property element: ${{propertyName}}`);
{I}}}

{I}const nestedClass = Array.from(property.childNodes).find(
{II}(child) => child.nodeType === child.ELEMENT_NODE
{I}) ?? null;
{I}if (nestedClass === null) {{
{II}throw new Error(`Failed to find nested class element in: ${{propertyName}}`);
{I}}}

{I}const brokenNestedClass = document.createElement("unknownNestedClassXmlElement");
{I}// We move the children from nestedClass to brokenNestedClass; appendChild
{I}// will automatically re-assign the parent, see:
{I}// https://developer.mozilla.org/en-US/docs/Web/API/Node/appendChild
{I}while (nestedClass.firstChild !== null) {{
{II}brokenNestedClass.appendChild(nestedClass.firstChild);
{I}}}

{I}property.replaceChild(brokenNestedClass, nestedClass);

{I}const brokenText = new XMLSerializer().serializeToString(document);

{I}expectDeserializationError(brokenText);
}});"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code for targeted negative XML de-serialization tests."""
    atomic_list_candidate = _first_atomic_list_property_candidate(symbol_table)
    nested_dispatch_candidate = _first_nested_class_dispatch_candidate(symbol_table)

    # NOTE (mristin):
    # The other targets pick the class and the property of the duplicate-property
    # test with this very same function, so that all of them break the same shape
    # of a document.
    duplicate_candidate = intermediate.first_class_with_a_required_property(
        symbol_table
    )

    # NOTE (mristin):
    # ``XMLSerializer`` is only used by the duplicate-property, invalid-item-delimiter
    # and nested-class-dispatch-mismatch tests below, which are only generated if
    # a suitable candidate class/property exists in the meta-model. We have to
    # determine that upfront so that we do not import ``XMLSerializer`` in vain and
    # trigger an unused-import lint error on meta-models which do not provide such
    # a candidate (*e.g.*, a class with no properties at all).
    xml_serializer_needed = (
        duplicate_candidate is not None
        or atomic_list_candidate is not None
        or nested_dispatch_candidate is not None
    )

    xmldom_import = (
        "import { DOMParser, XMLSerializer } from " '"@xmldom/xmldom";'
        if xml_serializer_needed
        else 'import { DOMParser } from "@xmldom/xmldom";'
    )

    blocks = [
        Stripped(
            """\
/**
 * Test failure modes in XML parsing to exercise defensive branches.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            f"""\
import * as fs from "fs";
import * as path from "path";

// NOTE (mristin):
// Initially, we used string operations to manipulate the XML files, but that lead
// to maintainability problems. For example, we suddenly had to take care of edge
// cases such as self-closing elements (e.g., `<something />`). Instead, we decided
// to use a proper library. There is a DOMParser in XMLSerializer provided in
// the browser, but node.js does not ship with them, unless we explicitly add "dom".
//
// In the end, we decided to use an external library as development dependency since
// all the other approaches (gymnastics with jest, tsconfig and tsconfig.test) turned
// out to be much more complicated.
{xmldom_import}
import type {{ Document }} from "@xmldom/xmldom";

import * as AasXmlization from "../src/xmlization";

import * as TestCommon from "./common";

function parseXml(xmlText: string): [Document, null] | [null, string] {{
{I}let errorMessage: string | null = null;

{I}const document = new DOMParser({{
{II}errorHandler: (level: string, msg: string) => {{
{III}if (level === "error" || level === "fatalError") {{
{IIII}errorMessage = msg;
{III}}}
{II}}}
{I}}}).parseFromString(xmlText, "application/xml");

{I}return errorMessage !== null ? [null, errorMessage] : [document, null];
}}

function expectDeserializationError(xmlText: string): void {{
{I}const instanceOrError = AasXmlization.fromXmlString(xmlText);
{I}expect(instanceOrError.error).not.toBeNull();
}}"""
        ),
    ]  # type: List[Stripped]

    first_cls = (
        symbol_table.concrete_classes[0]
        if len(symbol_table.concrete_classes) > 0
        else None
    )
    if first_cls is not None:
        first_cls_xml_name = naming.xml_class_name(first_cls.name)
        first_cls_xml_name_literal = typescript_common.string_literal(
            first_cls_xml_name
        )

        blocks.append(
            Stripped(
                f"""\
test("XML namespace mismatch fails", () => {{
{I}const pth = path.join(
{II}TestCommon.TEST_DATA_DIR, "Xml", "Expected", {first_cls_xml_name_literal}, "minimal.xml"
{I});
{I}const text = fs.readFileSync(pth, "utf-8");
{I}const brokenText = text.replace(
{II}/xmlns=\"[^\"]*\"/,
{II}'xmlns="urn:aas-core-codegen:broken"'
{I});

{I}expect(brokenText).not.toStrictEqual(text);
{I}expectDeserializationError(brokenText);
}});"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
test("XML wrong root closing element fails", () => {{
{I}const pth = path.join(
{II}TestCommon.TEST_DATA_DIR, "Xml", "Expected", {first_cls_xml_name_literal}, "minimal.xml"
{I});
{I}const text = fs.readFileSync(pth, "utf-8");

{I}// NOTE (mristin):
{I}// The root element might be self-closing (*e.g.*, `<{first_cls_xml_name} .../>`)
{I}// if it has no content, in which case there is no separate closing tag to
{I}// corrupt. We handle the two cases distinctly.
{I}const selfClosingRegex = new RegExp("<{first_cls_xml_name}(?=[^>]*/>)");
{I}const selfClosingMatch = text.match(selfClosingRegex);

{I}let brokenText: string;
{I}if (selfClosingMatch !== null && selfClosingMatch.index !== undefined) {{
{II}brokenText =
{III}text.slice(0, selfClosingMatch.index) +
{III}"<{first_cls_xml_name}_BROKEN" +
{III}text.slice(selfClosingMatch.index + selfClosingMatch[0].length);
{I}}} else {{
{II}const expectedClosing = "</{first_cls_xml_name}>";
{II}const insertionIndex = text.lastIndexOf(expectedClosing);
{II}if (insertionIndex < 0) {{
{III}throw new Error(`Failed to find root closing tag: ${{expectedClosing}}`);
{II}}}

{II}const brokenClosing = "</{first_cls_xml_name}_BROKEN>";
{II}brokenText =
{III}text.slice(0, insertionIndex) +
{III}brokenClosing +
{III}text.slice(insertionIndex + expectedClosing.length);
{I}}}

{I}expect(brokenText).not.toStrictEqual(text);
{I}expectDeserializationError(brokenText);
}});"""
            )
        )

        # region Check duplicate properties

        if duplicate_candidate is not None:
            duplicate_cls, duplicate_prop = duplicate_candidate

            blocks.append(
                _generate_duplicate_property_test(
                    cls=duplicate_cls, prop=duplicate_prop
                )
            )

    # endregion Check duplicate properties

    if atomic_list_candidate is not None:
        list_cls, list_prop = atomic_list_candidate

        blocks.append(_generate_invalid_item_delimiter(cls=list_cls, prop=list_prop))

    if nested_dispatch_candidate is not None:
        nested_cls, nested_prop = nested_dispatch_candidate

        blocks.append(
            _generate_nested_class_dispatch_mismatch(cls=nested_cls, prop=nested_prop)
        )

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
assert generate.__doc__.strip().startswith(__doc__.strip())
