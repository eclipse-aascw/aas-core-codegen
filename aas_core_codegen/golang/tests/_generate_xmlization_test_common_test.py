# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code for common XML de/serialization shared across the tests."""

import html
import io
from typing import List, MutableMapping, Optional, Sequence, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.common import (
    Stripped,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.golang import common as golang_common, naming as golang_naming
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


def _generate_whitespace_round_trip_test(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Stripped]:
    """Exercise whitespace-only strings through the real model reader and writer."""
    for cls in symbol_table.our_types:
        if not isinstance(cls, intermediate.ConcreteClass):
            continue
        required = [
            prop
            for prop in cls.properties
            if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        ]
        if any(
            intermediate.try_primitive_type(prop.type_annotation) is None
            and not (
                isinstance(prop.type_annotation, intermediate.OurTypeAnnotation)
                and isinstance(prop.type_annotation.our_type, intermediate.Enumeration)
            )
            for prop in required
        ):
            continue
        prop = next(
            (
                candidate
                for candidate in required
                if isinstance(
                    candidate.type_annotation, intermediate.PrimitiveTypeAnnotation
                )
                and candidate.type_annotation.a_type is intermediate.PrimitiveType.STR
            ),
            None,
        )
        if prop is None:
            continue

        namespace = html.escape(symbol_table.meta_model.xml_namespace, quote=True)
        local = naming.xml_class_name(cls.name)
        prefix = f'<{local} xmlns="{namespace}">'
        suffix = f"</{local}>"
        following = False
        for sibling in required:
            if sibling is prop:
                prefix += f"<{prop.xml_name}>"
                suffix = f"</{prop.xml_name}>" + suffix
                following = True
                continue
            a_type = intermediate.try_primitive_type(sibling.type_annotation)
            if a_type is not None:
                value = {
                    intermediate.PrimitiveType.STR: "",
                    intermediate.PrimitiveType.BOOL: "false",
                    intermediate.PrimitiveType.INT: "0",
                    intermediate.PrimitiveType.FLOAT: "0",
                    intermediate.PrimitiveType.BYTEARRAY: "",
                }[a_type]
            else:
                assert isinstance(
                    sibling.type_annotation, intermediate.OurTypeAnnotation
                )
                assert isinstance(
                    sibling.type_annotation.our_type, intermediate.Enumeration
                )
                value = html.escape(sibling.type_annotation.our_type.literals[0].value)
            element = f"<{sibling.xml_name}>{value}</{sibling.xml_name}>"
            if following:
                suffix = suffix.removesuffix(f"</{local}>") + element + f"</{local}>"
            else:
                prefix += element
        prefix_literal = golang_common.string_literal(prefix)
        suffix_literal = golang_common.string_literal(suffix)
        self_closing_string = golang_common.string_literal(
            prefix.removesuffix(">") + "/>" + suffix.removeprefix(f"</{prop.xml_name}>")
        )
        getter = golang_naming.getter_name(prop.name)
        empty_container = golang_common.string_literal(
            f'<{local} xmlns="{namespace}"/>'
        )
        indented_container = golang_common.string_literal(
            f'<{local} xmlns="{namespace}">\n\t</{local}>'
        )
        return Stripped(
            f"""\
func TestWhitespaceStringRoundTrip(t *testing.T) {{
{I}// Compare the paired spelling and whitespace values against a self-closing string.
{I}selfClosing, err := canonicalizeXmlForComparison({self_closing_string})
{I}if err != nil {{
{II}t.Fatal(err)
{I}}}
{I}canonicalByValue := map[string]xmlComparison{{"": selfClosing}}
{I}for _, c := range []struct {{
{II}name string
{II}xml  string
{II}want string
{I}}}{{
{II}{{"literal_tab", "\\t", "\\t"}},
{II}{{"decimal_tab", "&#9;", "\\t"}},
{II}{{"hex_tab", "&#x9;", "\\t"}},
{II}{{"literal_newline", "\\n", "\\n"}},
{II}{{"decimal_newline", "&#10;", "\\n"}},
{II}{{"hex_newline", "&#xA;", "\\n"}},
{II}{{"literal_crlf", "\\r\\n", "\\n"}},
{II}{{"literal_cr", "\\r", "\\n"}},
{II}{{"referenced_cr", "&#13;", "\\r"}},
{II}{{"literal_space", " ", " "}},
{II}{{"decimal_space", "&#32;", " "}},
{II}{{"hex_space", "&#x20;", " "}},
{II}{{"two_spaces", "  ", "  "}},
{II}{{"mixed_whitespace", " &#9;\\n", " \\t\\n"}},
{II}{{"empty", "", ""}},
{II}{{"space_before_angle", "x &gt;", "x >"}},
{II}{{"lost_space_before_angle", "x&gt;", "x>"}},
{II}{{"cdata_tab", "<![CDATA[\\t]]>", "\\t"}},
{I}}} {{
{II}t.Run(c.name, func(t *testing.T) {{
{III}document := {prefix_literal} + c.xml + {suffix_literal}
{III}instance, err := ourxmlization.Unmarshal(xml.NewDecoder(strings.NewReader(document)))
{III}if err != nil {{
{IIII}t.Fatal(err)
{III}}}
{III}typed, ok := instance.(interface{{ {getter}() string }})
{III}if !ok || typed.{getter}() != c.want {{
{IIII}t.Fatalf("Expected decoded string %q, got %v", c.want, instance)
{III}}}
{III}var serialized bytes.Buffer
{III}encoder := xml.NewEncoder(&serialized)
{III}encoder.Indent("", "\\t")
{III}if err := ourxmlization.Marshal(encoder, instance, true); err != nil {{
{IIII}t.Fatal(err)
{III}}}
{III}assertSerializationEqualsDeserialization(t, document, serialized.String(), c.name)
{III}canonical, err := canonicalizeXmlForComparison(document)
{III}if err != nil {{
{IIII}t.Fatal(err)
{III}}}
{III}for value, previous := range canonicalByValue {{
{IIII}if (canonical == previous) != (c.want == value) {{
{IIIII}t.Fatalf("Comparison confuses string values %q and %q", c.want, value)
{IIII}}}
{III}}}
{III}canonicalByValue[c.want] = canonical
{II}}})
{I}}}
{I}empty, err := canonicalizeXmlForComparison({empty_container})
{I}if err != nil {{
{II}t.Fatal(err)
{I}}}
{I}indented, err := canonicalizeXmlForComparison({indented_container})
{I}if err != nil || empty != indented {{
{II}t.Fatalf("Empty container indentation differs: %v", err)
{I}}}
}}"""
        )
    return None


def _generate_numeric_comparison_test(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Stripped]:
    """Exercise numeric equivalence only at model-defined numeric positions."""
    paths_by_kind: MutableMapping[str, Tuple[str, str]] = {}
    namespace = html.escape(symbol_table.meta_model.xml_namespace, quote=True)
    for cls in symbol_table.our_types:
        if not isinstance(cls, intermediate.ConcreteClass):
            continue
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)
            if (
                intermediate.try_primitive_type(type_anno)
                is intermediate.PrimitiveType.FLOAT
            ):
                kind = "double"
            elif (
                intermediate.try_primitive_type(type_anno)
                is intermediate.PrimitiveType.STR
            ):
                kind = "text"
            elif isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
                kind = "json:double"
            elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
                kind = "json:array"
            elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
                kind = "json:object"
            else:
                continue
            if kind in paths_by_kind:
                continue
            local = naming.xml_class_name(cls.name)
            prefix = f'<{local} xmlns="{namespace}"><{prop.xml_name}>'
            suffix = f"</{prop.xml_name}></{local}>"
            if kind == "json:double":
                prefix += '<double xmlns="">'
                suffix = "</double>" + suffix
            elif kind == "json:array":
                prefix += '<data xmlns=""><value><double>'
                suffix = "</double></value></data>" + suffix
            elif kind == "json:object":
                prefix += '<member xmlns=""><name>x</name><value><double>'
                suffix = "</double></value></member>" + suffix
            paths_by_kind[kind] = (prefix, suffix)
    if not any(kind != "text" for kind in paths_by_kind):
        return None
    paths = ",\n".join(
        "{"
        + ", ".join(golang_common.string_literal(value) for value in (kind, *path))
        + "}"
        for kind, path in sorted(paths_by_kind.items())
    )
    return Stripped(
        f"""\
func TestXmlNumericComparison(t *testing.T) {{
{I}// These fragments exercise comparison at typed paths, without model verification.
{I}for _, path := range []struct {{
{II}kind, prefix, suffix string
{I}}}{{
{II}{indent_but_first_line(paths, II)},
{I}}} {{
{II}t.Run(path.kind, func(t *testing.T) {{
{III}for _, c := range []struct {{
{IIII}name, left, right string
{IIII}equal             bool
{III}}}{{
{IIII}{{"decimal", "42.0", "42", true}},
{IIII}{{"exponent", "21668651.6", "2.16686516e+07", true}},
{IIII}{{"leading_zeroes", "+0042.00", "42", true}},
{IIII}{{"exponent_case", "4.2E1", "4.2e+01", true}},
{IIII}{{"negative", "-42.00", "-4.2e1", true}},
{IIII}{{"small", "0.0000000001", "1e-10", true}},
{IIII}{{"smallest_subnormal", "5e-324", "4.9406564584124654e-324", true}},
{IIII}{{"subnormal_vs_zero", "5e-324", "0", false}},
{IIII}{{"largest_finite", "1.7976931348623157e308", "1.7976931348623157E+308", true}},
{IIII}{{"different", "42", "43", false}},
{IIII}{{"adjacent_doubles", "1", "1.0000000000000002", false}},
{IIII}{{"integer_precision", "9007199254740991", "9007199254740992", false}},
{IIII}{{"signed_zero", "0", "-0", false}},
{IIII}{{"negative_zero", "-0.0", "-0e0", true}},
{IIII}{{"same_instruction", "<?p x > y?>42.0", "<?p x > y?>42", true}},
{IIII}{{"different_instruction", "<?p x > y?>42.0", "<?p x> y?>42", false}},
{IIII}{{"moved_instruction", "4<?p x?>2", "42<?p x?>", false}},
{IIII}{{"moved_comment", "4<!--c-->2", "42<!--c-->", false}},
{IIII}{{"split_comment", "4<!--c-->2.0", "4<!--c-->2", true}},
{IIII}{{"split_instruction", "4<?p x?>2.0", "4<?p x?>2", true}},
{IIII}{{"changed_number", "4<!--c-->2", "4<!--c-->3", false}},
{IIII}{{"changed_comment", "4<!--c-->2", "4<!--d-->2", false}},
{IIII}{{"changed_offset", "12<!--c-->3.0", "1<!--c-->23", false}},
{IIII}{{"missing_comment", "4<!--c-->2", "42", false}},
{IIII}{{"leading_or_trailing", "<?p x?>42", "42<?p x?>", false}},
{IIII}{{"trailing_markup", "42.0<!--c-->", "42<!--c-->", true}},
{III}}} {{
{IIII}t.Run(c.name, func(t *testing.T) {{
{IIIII}left, err := canonicalizeXmlForComparison(path.prefix + c.left + path.suffix)
{IIIII}if err != nil {{
{IIIIII}t.Fatal(err)
{IIIII}}}
{IIIII}right, err := canonicalizeXmlForComparison(path.prefix + c.right + path.suffix)
{IIIII}if err != nil {{
{IIIIII}t.Fatal(err)
{IIIII}}}
{IIIII}want := c.equal && path.kind != "text"
{IIIII}if (left == right) != want {{
{IIIIII}t.Fatalf("Unexpected comparison of %q and %q", left, right)
{IIIII}}}
{IIII}}})
{III}}}
{III}if path.kind == "text" {{
{IIII}return
{III}}}
{III}for _, c := range []struct{{ input, want string }}{{
{IIII}{{"4<![CDATA[2]]>", "42"}},
{IIII}{{"4&#50;", "42"}},
{IIII}{{" 42 ", "42"}},
{IIII}{{" <![CDATA[4]]><?p x?><!--c-->&#50; ", "4<?p x?><!--c-->2"}},
{IIII}{{" <!--a-->42.0<?p x?> ", "<!--a-->42<?p x?>"}},
{III}}} {{
{IIII}input := path.prefix + c.input + path.suffix
{IIII}instanceNumber, err := canonicalizeXmlForComparison(input)
{IIII}if err != nil {{
{IIIII}t.Fatal(err)
{IIII}}}
{IIII}expected, err := canonicalizeXmlForComparison(path.prefix + c.want + path.suffix)
{IIII}if err != nil {{
{IIIII}t.Fatal(err)
{IIII}}}
{IIII}if instanceNumber != expected {{
{IIIII}t.Fatalf("Expected %q, got %q", expected, instanceNumber)
{IIII}}}
{III}}}
{III}for _, spelling := range []string{{
{IIII}"", " ", "nan", "Infinity", "0x1p0", "1_0", "1 2",
{IIII}"<v>42</v>", "4<?p x?> 2", "42" + string(rune(160)),
{III}}} {{
{IIII}if _, err := canonicalizeXmlForComparison(path.prefix + spelling + path.suffix); err == nil {{
{IIIII}t.Fatalf("Accepted invalid numeric content %q", spelling)
{IIII}}}
{III}}}
{III}for _, c := range []struct {{
{IIII}spelling, want string
{III}}}{{
{IIII}{{"INF", "INF"}}, {{"-INF", "-INF"}}, {{"NaN", "NaN"}}, {{"1e9999", "INF"}},
{III}}} {{
{IIII}canonical, err := canonicalizeXmlForComparison(path.prefix + c.spelling + path.suffix)
{IIII}if strings.HasPrefix(path.kind, "json:") {{
{IIIII}if err == nil {{
{IIIIII}t.Fatalf("Accepted non-finite JSON number %q", c.spelling)
{IIIII}}}
{IIII}}} else {{
{IIIII}if err != nil {{
{IIIIII}t.Fatal(err)
{IIIII}}}
{IIIII}if canonical.text != path.prefix+c.want+path.suffix {{
{IIIIII}t.Fatalf("Unexpected non-finite model number: %q", canonical)
{IIIII}}}
{IIII}}}
{III}}}
{II}}})
{I}}}
}}"""
    )


def _generate_xml_rpc_member_order_test(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Stripped]:
    """Exercise unordered objects at the model's XML-RPC property paths."""
    paths: List[Tuple[str, str, str, str]] = []
    namespace = html.escape(symbol_table.meta_model.xml_namespace, quote=True)

    def sample_item(
        type_anno: intermediate.TypeAnnotationExceptOptional, local: str
    ) -> str:
        """Supply tuple siblings so positional dispatch reaches the intended slot."""
        primitive = intermediate.try_primitive_type(type_anno)
        if primitive is not None:
            text = {
                intermediate.PrimitiveType.BOOL: "true",
                intermediate.PrimitiveType.INT: "0",
                intermediate.PrimitiveType.FLOAT: "0",
                intermediate.PrimitiveType.STR: "text",
                intermediate.PrimitiveType.BYTEARRAY: "",
            }[primitive]
            return f"<{local}>{text}</{local}>"
        if isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type
            if isinstance(our_type, intermediate.Enumeration):
                # Siblings provide positional context without being deserialized.
                # An enum literal can contain characters forbidden in XML.
                return f"<{local}>text</{local}>"
            if isinstance(our_type, intermediate.ConcreteClass):
                local = naming.xml_class_name(our_type.name)
            elif isinstance(our_type, intermediate.AbstractClass):
                if our_type.concrete_descendants:
                    local = naming.xml_class_name(our_type.concrete_descendants[0].name)
            elif isinstance(our_type, intermediate.NamedUnion):
                if our_type.implementers:
                    local = naming.xml_class_name(our_type.implementers[0].name)
            return f"<{local}/>"
        if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
            return f'<{local}><nil xmlns=""/></{local}>'
        if isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
            return f'<{local}><data xmlns=""/></{local}>'
        if isinstance(type_anno, intermediate.TupleTypeAnnotation):
            contents = "".join(
                sample_item(item, f"v{index}")
                for index, item in enumerate(type_anno.items, 1)
            )
            return f"<{local}>{contents}</{local}>"
        return f"<{local}/>"

    def visit(
        type_anno: intermediate.TypeAnnotationExceptOptional,
        wrappers: Sequence[Tuple[str, str, bool]],
        path: str,
    ) -> None:
        """Follow model collections and retain boundaries of ordered list items."""
        if isinstance(
            type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
        ):
            ordered = isinstance(type_anno, intermediate.ListTypeAnnotation)
            visit(
                type_anno.items,
                [*wrappers, ("<v>", "</v>", ordered)],
                path + ("/list" if ordered else "/set"),
            )
            return
        if isinstance(type_anno, intermediate.TupleTypeAnnotation):
            siblings = [
                sample_item(item, f"v{index}")
                for index, item in enumerate(type_anno.items, 1)
            ]
            for index, item in enumerate(type_anno.items):
                local = f"v{index + 1}"
                opening = "".join(siblings[:index]) + f"<{local}>"
                closing = f"</{local}>" + "".join(siblings[index + 1 :])
                visit(
                    item,
                    [*wrappers, (opening, closing, False)],
                    path + f"/tuple[{index + 1}]",
                )
            return
        if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
            kind, opening, closing = "value", '<struct xmlns="">', "</struct>"
        elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
            kind = "array"
            opening = '<data xmlns=""><value><struct>'
            closing = "</struct></value></data>"
        elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
            kind, opening, closing = "object", "", ""
        else:
            return
        frames = [*wrappers, (opening, closing, False)]
        prefix = "".join(frame[0] for frame in frames)
        suffix = "".join(frame[1] for frame in reversed(frames))
        middle = ""
        for index, frame in enumerate(frames):
            if frame[2]:
                item_frames = frames[index:]
                middle = "".join(item[1] for item in reversed(item_frames)) + "".join(
                    item[0] for item in item_frames
                )
        paths.append((path + "/" + kind, prefix, suffix, middle))

    for cls in symbol_table.our_types:
        if not isinstance(cls, intermediate.ConcreteClass):
            continue
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)
            local = naming.xml_class_name(cls.name)
            visit(
                type_anno,
                [
                    (
                        f'<{local} xmlns="{namespace}"><{prop.xml_name}>',
                        f"</{prop.xml_name}></{local}>",
                        False,
                    )
                ],
                f"{cls.name}.{prop.name}",
            )
    if not paths:
        return None
    path_literals = ",\n".join(
        "{" + ", ".join(golang_common.string_literal(value) for value in path) + "}"
        for path in paths
    )
    return Stripped(
        f"""\
func TestXmlRpcMemberOrderComparison(t *testing.T) {{
{I}member := func(key, value string) string {{
{II}return `<member xmlns=""><name>` + key + `</name><value>` + value + `</value></member>`
{I}}}
{I}a := member("a", "<string>42.0</string>")
{I}b := member("b", "<double>2.0</double>")
{I}aNumber := member("a", "<double>4<!--c-->2.0</double>")
{I}bNumber := member("b", "<double>5<!--d-->2.0</double>")
{I}array := "<array><data><value><double>1</double></value><value><double>2</double></value></data></array>"
{I}reversedArray := "<array><data><value><double>2</double></value><value><double>1</double></value></data></array>"
{I}attributeA := strings.Replace(a, "<member ", `<member label="a >b" `, 1)
{I}comment := "<!--<c></c>-->"
{I}for _, path := range []struct{{ name, prefix, suffix, middle string }}{{
{II}{indent_but_first_line(path_literals, II)},
{I}}} {{
{II}t.Run(path.name, func(t *testing.T) {{
{III}for _, c := range []struct {{
{IIII}name, left, right string
{IIII}equal             bool
{III}}}{{
{IIII}{{"reordered", b + a, a + b, true}},
{IIII}{{"numeric_spelling", b + a, a + member("b", "<double>2</double>"), true}},
{IIII}{{"changed_value", b + a, a + member("b", "<double>3</double>"), false}},
{IIII}{{"changed_key", b + a, a + member("c", "<double>2</double>"), false}},
{IIII}{{"changed_type", b + a, a + member("b", "<string>2.0</string>"), false}},
{IIII}{{"changed_string", b + a, member("a", "<string>42</string>") + b, false}},
{IIII}{{"missing_member", b + a, a, false}},
{IIII}{{"empty_key", b + member("", "<nil/>"), member("", "<nil/>") + b, true}},
{IIII}{{"escaped_key", b + member("a&amp;b", "<nil/>"), member("a&#38;b", "<nil/>") + b, true}},
{IIII}{{"cdata_key", b + member("<![CDATA[a]]>", "<nil/>"), member("a", "<nil/>") + b, true}},
{IIII}{{
{IIIII}"nested_object",
{IIIII}member("nested", "<struct>"+b+a+"</struct>"),
{IIIII}member("nested", "<struct>"+a+b+"</struct>"),
{IIIII}true,
{IIII}}},
{IIII}{{
{IIIII}"object_in_array",
{IIIII}member("array", "<array><data><value><struct>"+b+a+"</struct></value></data></array>"),
{IIIII}member("array", "<array><data><value><struct>"+a+b+"</struct></value></data></array>"),
{IIIII}true,
{IIII}}},
{IIII}{{"array_order", member("array", array), member("array", reversedArray), false}},
{IIII}{{"numeric_markup", bNumber + aNumber, strings.ReplaceAll(aNumber+bNumber, "2.0", "2"), true}},
{IIII}{{
{IIIII}"changed_numeric_markup", bNumber + aNumber,
{IIIII}aNumber + strings.ReplaceAll(bNumber, "<!--d-->", "<!--e-->"), false,
{IIII}}},
{IIII}{{
{IIIII}"moved_numeric_markup", bNumber + aNumber,
{IIIII}aNumber + strings.ReplaceAll(bNumber, "5<!--d-->2.0", "52.0<!--d-->"), false,
{IIII}}},
{IIII}{{"member_attribute", b + a, strings.Replace(a, "<member ", `<member extra="x" `, 1) + b, false}},
{IIII}{{"attribute_reorder_control", attributeA + b, b + attributeA, true}},
{IIII}{{
{IIIII}"attribute_changed", attributeA + b,
{IIIII}b + strings.Replace(attributeA, `label="a >b"`, `label="a>b"`, 1), false,
{IIII}}},
{IIII}{{"comment_reorder_control", a + comment + b, b + comment + a, true}},
{IIII}{{"comment_content_changed", a + comment + b, b + "<!--<c/>-->" + a, false}},
{IIII}{{"inter_member_comment", b + "<!--gap-->" + a, a + "<!--gap-->" + b, true}},
{IIII}{{"changed_comment", b + "<!--gap-->" + a, a + "<!--changed-->" + b, false}},
{IIII}{{
{IIIII}"wrong_namespace",
{IIIII}strings.ReplaceAll(b+a, `xmlns=""`, `xmlns="urn:other"`),
{IIIII}strings.ReplaceAll(a+b, `xmlns=""`, `xmlns="urn:other"`), false,
{IIII}}},
{III}}} {{
{IIII}t.Run(c.name, func(t *testing.T) {{
{IIIII}left, err := canonicalizeXmlForComparison(path.prefix + c.left + path.suffix)
{IIIII}if err != nil {{
{IIIIII}t.Fatal(err)
{IIIII}}}
{IIIII}right, err := canonicalizeXmlForComparison(path.prefix + c.right + path.suffix)
{IIIII}if err != nil {{
{IIIIII}t.Fatal(err)
{IIIII}}}
{IIIII}if (left == right) != c.equal {{
{IIIIII}t.Fatalf("Unexpected comparison of %q and %q", left, right)
{IIIII}}}
{IIII}}})
{III}}}
{III}for _, invalid := range []string{{
{IIII}a + a,
{IIII}a + member("&#97;", "<nil/>"),
{IIII}`<member xmlns=""><value><nil/></value></member>`,
{IIII}`<member xmlns=""><name>a</name><name>b</name><value><nil/></value></member>`,
{III}}} {{
{IIII}if _, err := canonicalizeXmlForComparison(path.prefix + invalid + path.suffix); err == nil {{
{IIIII}t.Fatalf("Accepted invalid object members %q", invalid)
{IIII}}}
{III}}}
{III}if path.middle != "" {{
{IIII}// Reorder members inside each list item while preserving the item positions.
{IIII}second := member("a", "<string>different</string>") + b
{IIII}left, err := canonicalizeXmlForComparison(
{IIIII}path.prefix + b + a + path.middle + second + path.suffix)
{IIII}if err != nil {{
{IIIII}t.Fatal(err)
{IIII}}}
{IIII}right, err := canonicalizeXmlForComparison(
{IIIII}path.prefix + a + b + path.middle + second + path.suffix)
{IIII}if err != nil {{
{IIIII}t.Fatal(err)
{IIII}}}
{IIII}if left != right {{
{IIIII}t.Fatal("Reordered members inside a model list item compared differently")
{IIII}}}
{IIII}swapped, err := canonicalizeXmlForComparison(
{IIIII}path.prefix + second + path.middle + a + b + path.suffix)
{IIII}if err != nil {{
{IIIII}t.Fatal(err)
{IIII}}}
{IIII}if left == swapped {{
{IIIII}t.Fatal("Swapped distinct model list items compared equally")
{IIII}}}
{III}}}
{II}}})
{I}}}
{I}// A struct-shaped fragment outside a model-defined JSON path keeps its order.
{I}left, err := canonicalizeXmlForComparison("<struct>" + b + a + "</struct>")
{I}if err != nil {{
{II}t.Fatal(err)
{I}}}
{I}right, err := canonicalizeXmlForComparison("<struct>" + a + b + "</struct>")
{I}if err != nil {{
{II}t.Fatal(err)
{I}}}
{I}if left == right {{
{II}t.Fatal("Reordered elements outside a model-defined JSON path")
{I}}}
}}"""
    )


def _generate_xml_rpc_member_order() -> Stripped:
    """Order only model-identified XML-RPC members, retaining their original XML."""
    return Stripped(
        f"""\
// Order XML-RPC object members by decoded key, preserving the XML of each member.
// Source ranges preserve tags, namespaces and markup without re-serializing them.
func orderXmlRpcMembersForComparison(text string) (string, error) {{
{I}// Member element names contain this literal text, including when prefixed.
{I}if !strings.Contains(text, "member") {{
{II}return text, nil
{I}}}
{I}type element struct {{
{II}start, end int64
{II}context    string
{II}key        string
{II}hasKey     bool
{II}children   []*element
{I}}}
{I}root := &element{{end: int64(len(text)), context: "root"}}
{I}stack := []*element{{root}}
{I}decoder := xml.NewDecoder(strings.NewReader(text))
{I}for {{
{II}start := decoder.InputOffset()
{II}token, err := decoder.Token()
{II}if err == io.EOF {{
{III}break
{II}}}
{II}if err != nil {{
{III}return "", err
{II}}}
{II}switch token := token.(type) {{
{II}case xml.StartElement:
{III}parent := stack[len(stack)-1]
{III}child := &element{{
{IIII}start:   start,
{IIII}context: xmlTextContext(parent.context, len(parent.children)+1, token.Name),
{III}}}
{III}parent.children = append(parent.children, child)
{III}if parent.context == "json:member" && token.Name == (xml.Name{{Local: "name"}}) {{
{IIII}if parent.hasKey {{
{IIIII}return "", fmt.Errorf("duplicate XML-RPC member name element")
{IIII}}}
{IIII}if err := decoder.DecodeElement(&parent.key, &token); err != nil {{
{IIIII}return "", err
{IIII}}}
{IIII}parent.hasKey = true
{IIII}child.end = decoder.InputOffset()
{IIII}continue
{III}}}
{III}stack = append(stack, child)
{II}case xml.EndElement:
{III}stack[len(stack)-1].end = decoder.InputOffset()
{III}stack = stack[:len(stack)-1]
{II}}}
{I}}}

{I}var result strings.Builder
{I}var write func(*element) error
{I}write = func(parent *element) error {{
{II}var members []*element
{II}for _, child := range parent.children {{
{III}if child.context == "json:member" {{
{IIII}if !child.hasKey {{
{IIIII}return fmt.Errorf("XML-RPC member has no name")
{IIII}}}
{IIII}members = append(members, child)
{III}}}
{II}}}
{II}sort.Slice(members, func(i, j int) bool {{ return members[i].key < members[j].key }})
{II}for i := 1; i < len(members); i++ {{
{III}if members[i-1].key == members[i].key {{
{IIII}return fmt.Errorf("duplicate XML-RPC member key %q", members[i].key)
{III}}}
{II}}}
{II}cursor := parent.start
{II}memberIndex := 0
{II}for _, child := range parent.children {{
{III}// Keep gaps between children, including comments, in their original positions.
{III}result.WriteString(text[cursor:child.start])
{III}selected := child
{III}if child.context == "json:member" {{
{IIII}selected = members[memberIndex]
{IIII}memberIndex++
{III}}}
{III}if err := write(selected); err != nil {{
{IIII}return err
{III}}}
{III}cursor = child.end
{II}}}
{II}result.WriteString(text[cursor:parent.end])
{II}return nil
{I}}}
{I}if err := write(root); err != nil {{
{II}return "", err
{I}}}
{I}return result.String(), nil
}}"""
    )


def _generate_text_context(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Track element types by their position in the model's XML structure."""
    namespace = symbol_table.meta_model.xml_namespace
    children_by_type: MutableMapping[str, MutableMapping[Tuple[str, str], str]] = {
        "root": {}
    }

    def class_content(cls: intermediate.ConcreteClass) -> str:
        """Register a class before its properties so recursive models terminate."""
        key = f"class:{cls.name}"
        if key not in children_by_type:
            children_by_type[key] = {}
            for prop in cls.properties:
                children_by_type[key][(namespace, prop.xml_name)] = content(
                    intermediate.beneath_optional(prop.type_annotation)
                )
        return key

    def items(
        type_anno: intermediate.TypeAnnotationExceptOptional, local: str
    ) -> MutableMapping[Tuple[str, str], str]:
        """Describe self-naming instances or positionally named collection items."""
        if isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type
            alternatives: List[intermediate.ConcreteClass]
            if isinstance(our_type, intermediate.NamedUnion):
                alternatives = list(our_type.implementers)
            elif isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                alternatives = list(our_type.concrete_descendants)
                if isinstance(our_type, intermediate.ConcreteClass):
                    alternatives.append(our_type)
            else:
                alternatives = []
            if alternatives:
                return {
                    (namespace, naming.xml_class_name(cls.name)): class_content(cls)
                    for cls in alternatives
                }
        return {(namespace, local): content(type_anno)}

    def content(type_anno: intermediate.TypeAnnotationExceptOptional) -> str:
        """Distinguish whitespace-preserving strings from their enclosing containers."""
        if intermediate.try_primitive_type(type_anno) is intermediate.PrimitiveType.STR:
            return "text"
        if (
            intermediate.try_primitive_type(type_anno)
            is intermediate.PrimitiveType.FLOAT
        ):
            return "double"
        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            return ""
        if isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type
            if isinstance(
                our_type, (intermediate.ConstrainedPrimitive, intermediate.Enumeration)
            ):
                return "text" if isinstance(our_type, intermediate.Enumeration) else ""
            if isinstance(our_type, intermediate.ConcreteClass) and not (
                our_type.concrete_descendants
            ):
                return class_content(our_type)

        prefix = (
            "tuple"
            if isinstance(type_anno, intermediate.TupleTypeAnnotation)
            else "content"
        )
        key = f"{prefix}:{golang_common.type_moniker(type_anno)}"
        if key in children_by_type:
            return key
        children_by_type[key] = {}
        if isinstance(type_anno, intermediate.OurTypeAnnotation):
            children_by_type[key].update(items(type_anno, ""))
        elif isinstance(
            type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
        ):
            children_by_type[key].update(items(type_anno.items, "v"))
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            for position, item in enumerate(type_anno.items, 1):
                children_by_type[f"{key}:{position}"] = items(item, f"v{position}")
        elif isinstance(
            type_anno,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            children_by_type["json:value"] = {
                ("", "array"): "json:array",
                ("", "struct"): "json:object",
                ("", "string"): "text",
                ("", "double"): "json:double",
            }
            children_by_type["json:array"] = {("", "data"): "json:data"}
            children_by_type["json:data"] = {("", "value"): "json:value"}
            children_by_type["json:object"] = {("", "member"): "json:member"}
            children_by_type["json:member"] = {
                ("", "name"): "text",
                ("", "value"): "json:value",
            }
            if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
                json_key = "json:value"
            elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
                json_key = "json:array"
            else:
                json_key = "json:object"
            children_by_type[key].update(children_by_type[json_key])
        else:
            assert_never(type_anno)
        return key

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.ConcreteClass):
            children_by_type["root"][
                (namespace, naming.xml_class_name(our_type.name))
            ] = class_content(our_type)

    cases: List[str] = []
    for key, children in sorted(children_by_type.items()):
        child_cases: List[str] = []
        for (space, local), child_type in sorted(children.items()):
            if not child_type:
                continue
            child_cases.append(
                f"""\
case (xml.Name{{Space: {golang_common.string_literal(space)}, Local: {golang_common.string_literal(local)}}}):
{I}return {golang_common.string_literal(child_type)}"""
            )
        if not child_cases:
            continue
        joined = "\n".join(child_cases)
        cases.append(
            f"""\
case {golang_common.string_literal(key)}:
{I}switch name {{
{I}{indent_but_first_line(joined, I)}
{I}}}"""
        )
    joined = "\n".join(cases)
    return Stripped(
        f"""\
// Identify class containers, collection containers, and scalar content
// from each element's position in the model's XML structure.
func xmlTextContext(parent string, position int, name xml.Name) string {{
{I}// Different tuple slots can have the same XML name.
{I}if strings.HasPrefix(parent, "tuple:") {{
{II}parent += ":" + strconv.Itoa(position)
{I}}}
{I}switch parent {{
{I}{indent_but_first_line(joined, I)}
{I}}}
{I}return ""
}}"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code for common XML de/serialization shared across the tests."""
    uses_json_types = intermediate_uses.json_types(symbol_table)
    sort_import = f'{I}"sort"\n' if uses_json_types else ""
    member_order_normalization = (
        f"""\
{I}text, err := orderXmlRpcMembersForComparison(text)
{I}if err != nil {{
{II}return xmlComparison{{}}, err
{I}}}
"""
        if uses_json_types
        else ""
    )
    blocks: List[Stripped] = [
        Stripped(
            """\
package xmlization_test"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"bytes"
{I}"encoding/xml"
{I}"fmt"
{I}"io"
{I}"math"
{I}"os"
{I}"path/filepath"
{I}"regexp"
{sort_import}\
{I}"strconv"
{I}"strings"
{I}"testing"

{I}xmlcommon "{repo_url}/internal/xmlcommon"
{I}ourtesting "{repo_url}/ourtesting"
{I}ourxmlization "{repo_url}/xmlization"
)"""
        ),
        Stripped(
            f"""\
// Assert that there is no de-serialization error when de-serializing
// from `source`.
func assertNoDeserializationError(
{I}t *testing.T,
{I}err error,
{I}source string,
) (ok bool) {{
{I}ok = true
{I}if err != nil {{
{II}ok = false
{II}t.Fatalf(
{III}"Expected no de-serialization error from %s, but got: %s",
{III}source, err.Error(),
{II})
{II}return
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Assert that there is no serialization error when serializing the instance
// originally coming from `source`.
func assertNoSerializationError(
{I}t *testing.T,
{I}err error,
{I}source string,
) (ok bool) {{
{I}ok = true
{I}if err != nil {{
{II}ok = false
{II}t.Fatalf(
{III}"Expected no serialization error when serializing "+
{IIII}"the instance obtained from %s, but got: %s",
{III}source, err.Error(),
{II})
{II}return
{I}}}
{I}return
}}"""
        ),
        Stripped(
            """\
var whitespaceBetweenTagsRe = regexp.MustCompile(`>\\s+<`)"""
        ),
        Stripped(
            f"""\
// Remove all whitespace (including newlines, tabs, and spaces) between XML tags
// without parsing the XML.
func removeWhitespaceBetweenTags(text string) string {{
{I}return whitespaceBetweenTagsRe.ReplaceAllString(text, "><")
}}"""
        ),
        Stripped(
            """\
var whitespaceBeforeAngleBracketsRe = regexp.MustCompile(`\\s+>`)
var whitespaceBeforeSelfClosingRe = regexp.MustCompile(`\\s+/>`)
var whitespaceAfterAngleBracketsRe = regexp.MustCompile(`<\\s+`)"""
        ),
        Stripped(
            f"""\
// Remove any whitespace before `>` and `/>` or after `<`
func removeWhitespaceWithinTags(text string) string {{
{I}result := text
{I}result = whitespaceBeforeAngleBracketsRe.ReplaceAllString(result, ">")
{I}result = whitespaceBeforeSelfClosingRe.ReplaceAllString(result, "/>")
{I}result = whitespaceAfterAngleBracketsRe.ReplaceAllString(result, "<")
{I}return result
}}"""
        ),
        _generate_text_context(symbol_table),
        Stripped(
            f"""\
// Keep numeric markup separate from the normalized XML so a change of number
// spelling can neither move a comment nor hide a change in its contents.
type xmlComparison struct {{
{I}text, numericMarkup string
}}

func normalizeXmlNumericContent(
{I}decoder *xml.Decoder, source, context string, numberIndex int, numericMarkup *strings.Builder,
) (string, error) {{
{I}var content bytes.Buffer
{I}type mark struct {{
{II}offset int
{II}xml    string
{I}}}
{I}var marks []mark
{I}for {{
{II}start := decoder.InputOffset()
{II}token, err := decoder.Token()
{II}if err != nil {{
{III}return "", err
{II}}}
{II}switch token := token.(type) {{
{II}case xml.CharData:
{III}content.Write(token)
{II}case xml.Comment, xml.ProcInst:
{III}raw := source[start:decoder.InputOffset()]
{III}marks = append(marks, mark{{content.Len(), raw}})
{II}case xml.EndElement:
{III}// Reuse the SDK reader's lexical validation and double-precision conversion.
{III}// The sentinel element terminates the supplied character data for ReadText.
{III}number, _, err := xmlcommon.ReadTextAs_double(
{IIII}xml.NewDecoder(strings.NewReader("<end/>")), xml.CharData(content.Bytes()))
{III}if err != nil {{
{IIII}return "", err
{III}}}
{III}if context == "json:double" && (math.IsInf(number, 0) || math.IsNaN(number)) {{
{IIII}return "", fmt.Errorf("expected a finite JSON number")
{III}}}
{III}if len(marks) > 0 {{
{IIII}// Count decoded numeric characters, excluding surrounding XML whitespace.
{IIII}// Leading and trailing marks stay at the boundaries even if the spelling changes length.
{IIII}text := content.Bytes()
{IIII}first := len(text) - len(bytes.TrimLeft(text, " \\t\\r\\n"))
{IIII}end := len(bytes.TrimRight(text, " \\t\\r\\n"))
{IIII}for _, m := range marks {{
{IIIII}var position string
{IIIII}switch {{
{IIIII}case m.offset <= first:
{IIIIII}position = "start"
{IIIII}case m.offset >= end:
{IIIIII}position = "end"
{IIIII}default:
{IIIIII}position = strconv.Itoa(m.offset - first)
{IIIII}}}
{IIIII}raw := strings.ReplaceAll(strings.ReplaceAll(m.xml, "\\r\\n", "\\n"), "\\r", "\\n")
{IIIII}fmt.Fprintf(numericMarkup, "number %d at %s: %q\\n", numberIndex, position, raw)
{IIII}}}
{III}}}
{III}// FormatFloat preserves every representable value, including signed zero.
{III}canonical := strconv.FormatFloat(number, 'g', -1, 64)
{III}if math.IsInf(number, 1) {{
{IIII}canonical = "INF"
{III}}} else if math.IsInf(number, -1) {{
{IIII}canonical = "-INF"
{III}}}
{III}return canonical + source[start:decoder.InputOffset()], nil
{II}default:
{III}return "", fmt.Errorf("expected numeric text, got %T", token)
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Normalize character escaping and numeric spelling while retaining the markup.
// Copying tags verbatim avoids changing namespace declarations or prefixes.
func normalizeXmlTextEscaping(text string) (xmlComparison, error) {{
{I}decoder := xml.NewDecoder(strings.NewReader(text))
{I}var result bytes.Buffer
{I}var numericMarkup strings.Builder
{I}numberIndex := 0
{I}type frame struct {{
{II}context  string
{II}children int
{I}}}
{I}stack := []frame{{{{context: "root"}}}}
{I}for {{
{II}start := decoder.InputOffset()
{II}token, err := decoder.Token()
{II}if err == io.EOF {{
{III}return xmlComparison{{result.String(), numericMarkup.String()}}, nil
{II}}}
{II}if err != nil {{
{III}return xmlComparison{{}}, err
{II}}}
{II}if element, ok := token.(xml.StartElement); ok {{
{III}parent := &stack[len(stack)-1]
{III}parent.children++
{III}context := xmlTextContext(parent.context, parent.children, element.Name)
{III}if context == "double" || context == "json:double" {{
{IIII}result.WriteString(text[start:decoder.InputOffset()])
{IIII}numberIndex++
{IIII}normalized, err := normalizeXmlNumericContent(decoder, text, context, numberIndex, &numericMarkup)
{IIII}if err != nil {{
{IIIII}return xmlComparison{{}}, err
{IIII}}}
{IIII}result.WriteString(normalized)
{IIII}continue
{III}}}
{III}stack = append(stack, frame{{context: context}})
{II}}}
{II}if data, ok := token.(xml.CharData); ok {{
{III}// Normalize strings consistently, even if they consist only of whitespace.
{III}// Keep container indentation available to the existing cleanup.
{III}if stack[len(stack)-1].context != "text" && strings.Trim(string(data), " \\t\\r\\n") == "" {{
{IIII}result.WriteString(text[start:decoder.InputOffset()])
{III}}} else {{
{IIII}var escaped bytes.Buffer
{IIII}if err := xml.EscapeText(&escaped, data); err != nil {{
{IIIII}return xmlComparison{{}}, err
{IIII}}}
{IIII}if stack[len(stack)-1].context == "text" {{
{IIIII}// Protect spaces as well as tabs and line breaks from the regex cleanup.
{IIIII}result.WriteString(strings.ReplaceAll(escaped.String(), " ", "&#32;"))
{IIII}}} else {{
{IIIII}result.Write(escaped.Bytes())
{IIII}}}
{III}}}
{II}}} else {{
{III}result.WriteString(text[start:decoder.InputOffset()])
{II}}}
{II}if _, ok := token.(xml.EndElement); ok {{
{III}stack = stack[:len(stack)-1]
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestWritePositiveInfinity(t *testing.T) {{
{I}var output strings.Builder
{I}encoder := xml.NewEncoder(&output)
{I}if err := xmlcommon.WriteAsText_double(encoder, math.Inf(1)); err != nil {{
{II}t.Fatal(err)
{I}}}
{I}if err := encoder.Flush(); err != nil {{
{II}t.Fatal(err)
{I}}}
{I}// XSD 1.0 requires INF even though the reader also accepts +INF.
{I}if got := output.String(); got != "INF" {{
{II}t.Fatalf("Expected positive infinity as %q, got %q", "INF", got)
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestNormalizeXmlTextEscaping(t *testing.T) {{
{I}cases := []struct {{
{II}name  string
{II}input string
{II}want  string
{I}}}{{
{II}{{"quotes", `<v>"hello"</v>`, `<v>&#34;hello&#34;</v>`}},
{II}{{"quote_references", `<v>&quot;hello&#x22;</v>`, `<v>&#34;hello&#34;</v>`}},
{II}{{"apostrophes", `<v>'hello'</v>`, `<v>&#39;hello&#39;</v>`}},
{II}{{"tabs", "<v>a\\tb</v>", `<v>a&#x9;b</v>`}},
{II}{{"tab_reference", `<v>a&#9;b</v>`, `<v>a&#x9;b</v>`}},
{II}{{"double_escaping", `<v>&amp;#34;</v>`, `<v>&amp;#34;</v>`}},
{II}{{"text_is_not_markup", `<v>&#60;x/&#62;</v>`, `<v>&lt;x/&gt;</v>`}},
{II}{{"string_spaces", `<v> hello </v>`, `<v> hello </v>`}},
{II}{{"markup", `<p:v xmlns:p='urn:test' a='"'/>`, `<p:v xmlns:p='urn:test' a='"'/>`}},
{II}{{"numbers", `<v>1e2</v>`, `<v>1e2</v>`}},
{II}{{"indentation", "<r>\\n\\t<v/>\\n</r>", "<r>\\n\\t<v/>\\n</r>"}},
{II}{{"whitespace_reference", `<v>&#x9;</v>`, `<v>&#x9;</v>`}},
{I}}}
{I}for _, c := range cases {{
{II}t.Run(c.name, func(t *testing.T) {{
{III}got, err := normalizeXmlTextEscaping(c.input)
{III}if err != nil {{
{IIII}t.Fatal(err)
{III}}}
{III}if got.text != c.want {{
{IIII}t.Fatalf("Expected %q, got %q", c.want, got)
{III}}}
{II}}})
{I}}}
}}"""
        ),
        Stripped(
            f"""\
const xmlComparisonMarker = "{golang_common.repo_url_to_environment_variable(repo_url)}_XML_COMPARISON_LITERAL"

func canonicalizeXmlForComparison(text string) (xmlComparison, error) {{
{I}text = strings.TrimSpace(text)
{member_order_normalization}\
{I}// Escape text before applying the legacy markup cleanup, so a literal
{I}// '>' in a value can not make the cleanup remove a preceding space.
{I}comparison, err := normalizeXmlTextEscaping(text)
{I}if err != nil {{
{II}return xmlComparison{{}}, err
{I}}}
{I}text = comparison.text
{I}// Protect literal content while the legacy regexes clean up markup.
{I}// Check after simulating carriage-return removal so cleanup cannot turn
{I}// existing XML text into a placeholder that gets replaced on restoration.
{I}markerPrefix := xmlComparisonMarker
{I}withoutCR := strings.ReplaceAll(text, "\\r", "")
{I}for strings.Contains(withoutCR, markerPrefix) {{
{II}markerPrefix += "X"
{I}}}
{I}// Collect placeholder/original pairs for a single-pass restoration.
{I}var replacements []string
{I}protectLiteral := func(original string, asMarkup bool) string {{
{II}marker := fmt.Sprintf("%s_%d_", markerPrefix, len(replacements)/2)
{II}if asMarkup {{
{III}marker = "<?" + marker + "?>"
{II}}}
{II}// XML 1.0 section 2.11 normalizes literal line endings before parsing.
{II}original = strings.ReplaceAll(strings.ReplaceAll(original, "\\r\\n", "\\n"), "\\r", "\\n")
{II}replacements = append(replacements, marker, original)
{II}return marker
{I}}}
{I}var protected bytes.Buffer
{I}// Track the buffered end of a start tag followed only by formatting whitespace.
{I}openingTagEnd := 0
{I}decoder := xml.NewDecoder(strings.NewReader(text))
{I}for {{
{II}start := decoder.InputOffset()
{II}token, err := decoder.Token()
{II}if err == io.EOF {{
{III}break
{II}}}
{II}if err != nil {{
{III}return xmlComparison{{}}, err
{II}}}
{II}original := text[start:decoder.InputOffset()]
{II}switch token.(type) {{
{II}case xml.Comment, xml.ProcInst, xml.Directive:
{III}openingTagEnd = 0
{III}protected.WriteString(protectLiteral(original, true))
{II}case xml.StartElement:
{III}// Quoted attribute values can contain '>' and the other quote character.
{III}// Keep the original quotes and protect only the contents between them.
{III}cursor := 0
{III}for i := 0; i < len(original); i++ {{
{IIII}quote := original[i]
{IIII}if quote != '\\'' && quote != '"' {{
{IIIII}continue
{IIII}}}
{IIII}end := i + 1
{IIII}for end < len(original) && original[end] != quote {{
{IIIII}end++
{IIII}}}
{IIII}if end == len(original) {{
{IIIII}return xmlComparison{{}}, fmt.Errorf("unterminated XML attribute value")
{IIII}}}
{IIII}protected.WriteString(original[cursor : i+1])
{IIII}protected.WriteString(protectLiteral(original[i+1:end], false))
{IIII}protected.WriteByte(quote)
{IIII}cursor = end + 1
{IIII}i = end
{III}}}
{III}protected.WriteString(original[cursor:])
{III}openingTagEnd = protected.Len()
{II}case xml.CharData:
{III}// Check the source spelling so whitespace references and CDATA still count.
{III}if strings.Trim(original, " \\t\\r\\n") != "" {{
{IIII}openingTagEnd = 0
{III}}}
{III}protected.WriteString(original)
{II}case xml.EndElement:
{III}// An already self-closing tag produces an end token without source bytes.
{III}if openingTagEnd > 0 && original != "" {{
{IIII}protected.Truncate(openingTagEnd - 1)
{IIII}protected.WriteString("/>")
{III}}} else {{
{IIII}protected.WriteString(original)
{III}}}
{III}openingTagEnd = 0
{II}default:
{III}openingTagEnd = 0
{III}protected.WriteString(original)
{II}}}
{I}}}
{I}text = protected.String()
{I}text = strings.ReplaceAll(text, "\\r", "")
{I}text = removeWhitespaceBetweenTags(text)
{I}text = removeWhitespaceWithinTags(text)
{I}if len(replacements) > 0 {{
{II}text = strings.NewReplacer(replacements...).Replace(text)
{I}}}
{I}comparison.text = text
{I}return comparison, nil
}}"""
        ),
        Stripped(
            f"""\
func TestXmlComparisonPreservesText(t *testing.T) {{
{I}withDefaultAttribute := func(value string) string {{
{II}return `<!DOCTYPE v [<!ATTLIST v label CDATA "` + value + `">]><v/>`
{I}}}
{I}for _, c := range []struct {{
{II}name     string
{II}expected string
{II}actual   string
{II}equal    bool
{I}}}{{
{II}{{"empty_prefixed", `<p:v xmlns:p="urn:test"></p:v>`, `<p:v xmlns:p="urn:test"/>`, true}},
{II}{{"empty_tag_space", `<v ></v>`, `<v/>`, true}},
{II}{{"empty_indented", "<v>\\n\\t</v>", `<v/>`, true}},
{II}{{"empty_siblings", `<root><v></v><v /><v ></v></root>`, `<root><v/><v/><v/></root>`, true}},
{II}{{
{III}"empty_prefixed_attribute",
{III}`<p:v xmlns:p="urn:test" label="a >b"></p:v>`,
{III}`<p:v xmlns:p="urn:test" label="a >b"/>`, true,
{II}}},
{II}{{
{III}"empty_prefixed_changed_attribute",
{III}`<p:v xmlns:p="urn:test" label="a >b"></p:v>`,
{III}`<p:v xmlns:p="urn:test" label="a>b"/>`, false,
{II}}},
{II}{{"empty_vs_text", `<v>x</v>`, `<v/>`, false}},
{II}{{"empty_vs_reference", `<v>&#32;</v>`, `<v/>`, false}},
{II}{{"empty_vs_cdata_space", `<v><![CDATA[ ]]></v>`, `<v/>`, false}},
{II}{{"empty_vs_comment", `<v><!--note--></v>`, `<v/>`, false}},
{II}{{"empty_vs_instruction", `<v><?p note?></v>`, `<v/>`, false}},
{II}{{"empty_vs_child", `<v><child/></v>`, `<v/>`, false}},
{II}{{"equivalent_escaping", `<v>x ></v>`, `<v>x &gt;</v>`, true}},
{II}{{"lost_space", `<v>x ></v>`, `<v>x&gt;</v>`, false}},
{II}{{"numeric_reference", `<v>x ></v>`, `<v>x &#62;</v>`, true}},
{II}{{"extra_space", `<v>x ></v>`, `<v>x  &gt;</v>`, false}},
{II}{{"tab_vs_newline", `<v>&#x9;</v>`, `<v>&#xA;</v>`, false}},
{II}{{"tab_vs_space", `<v>&#x9;</v>`, `<v>&#32;</v>`, false}},
{II}{{"lost_tab", `<v>&#x9;</v>`, `<v></v>`, false}},
{II}{{"space_vs_literal_tab", `<v>&#32;</v>`, "<v>\\t</v>", false}},
{II}{{"attribute_space", `<v label="a >b"/>`, `<v label="a>b"/>`, false}},
{II}{{"attribute_single_quote", `<v label='a >b'/>`, `<v label='a>b'/>`, false}},
{II}{{"attribute_mixed_quotes", `<v label='a " >b'/>`, `<v label='a ">b'/>`, false}},
{II}{{"attribute_empty_element", `<v label="a >b"></v>`, `<v label="a >b"/>`, true}},
{II}{{"attribute_tag_spacing", `<v label="a >b" />`, `<v label="a >b"/>`, true}},
{II}{{"attribute_crlf", "<v label=\\"a\\r\\nb\\"/>", "<v label=\\"a\\nb\\"/>", true}},
{II}{{"attribute_cr", "<v label=\\"a\\rb\\"/>", "<v label=\\"ab\\"/>", false}},
{II}{{
{III}"attribute_many_literals",
{III}`<v a0="0" a1="1" a2="2" a3="3" a4="4" a5="5"` +
{IIII}` a6="6" a7="7" a8="8" a9="9" a10="10"/>`,
{III}`<v a0="0" a1="1" a2="2" a3="3" a4="4" a5="5"` +
{IIII}` a6="6" a7="7" a8="8" a9="9" a10="changed"/>`,
{III}false,
{II}}},
{II}{{
{III}"namespace_changed",
{III}`<p:v xmlns:p="urn:a" label="a >b"/>`,
{III}`<p:v xmlns:p="urn:b" label="a >b"/>`, false,
{II}}},
{II}{{"comment_markup", `<v><!--<c></c>--></v>`, `<v><!--<c/>--></v>`, false}},
{II}{{"comment_space", `<v><!--a >b--></v>`, `<v><!--a>b--></v>`, false}},
{II}{{"comment_crlf", "<v><!--a\\r\\nb--></v>", "<v><!--a\\nb--></v>", true}},
{II}{{"comment_cr_as_lf", "<v><!--a\\rb--></v>", "<v><!--a\\nb--></v>", true}},
{II}{{"comment_cr", "<v><!--a\\rb--></v>", `<v><!--ab--></v>`, false}},
{II}{{"doctype_cr_as_lf", withDefaultAttribute("a\\rb"), withDefaultAttribute("a\\nb"), true}},
{II}{{"doctype_crlf", withDefaultAttribute("a\\r\\nb"), withDefaultAttribute("a\\nb"), true}},
{II}{{"doctype_cr", withDefaultAttribute("a\\rb"), withDefaultAttribute("ab"), false}},
{II}{{"doctype_attribute_space", withDefaultAttribute("a >b"), withDefaultAttribute("a>b"), false}},
{II}{{"doctype_spacing", `<!DOCTYPE v  ><v/>`, `<!DOCTYPE v><v/>`, false}},
{II}{{"instruction_data", `<v><?p x > y?></v>`, `<v><?p x> y?></v>`, false}},
{II}{{"instruction_markup", `<v><?p <a></a>?></v>`, `<v><?p <a/>?></v>`, false}},
{II}{{"instruction_cr", "<v><?p x\\ry?></v>", `<v><?p xy?></v>`, false}},
{II}{{"instruction_cr_as_lf", "<v><?p x\\ry?></v>", "<v><?p x\\ny?></v>", true}},
{II}{{"instruction_crlf_as_lf", "<v><?p x\\r\\ny?></v>", "<v><?p x\\ny?></v>", true}},
{II}{{"instruction_indentation", "<v>\\n<?p x > y?>\\n</v>", `<v><?p x > y?></v>`, true}},
{II}{{
{III}"instruction_marker",
{III}"<v><!--<?" + xmlComparisonMarker + "_0_?>--><?p x?></v>",
{III}"<v><!--<?p x?>--><?p x?></v>",
{III}false,
{II}}},
{II}{{
{III}"attribute_marker",
{III}"<v a=\\"" + xmlComparisonMarker + "_0_\\" b=\\"other\\"/>",
{III}"<v a=\\"other\\" b=\\"other\\"/>",
{III}false,
{II}}},
{I}}} {{
{II}t.Run(c.name, func(t *testing.T) {{
{III}expected, err := canonicalizeXmlForComparison(c.expected)
{III}if err != nil {{
{IIII}t.Fatal(err)
{III}}}
{III}actual, err := canonicalizeXmlForComparison(c.actual)
{III}if err != nil {{
{IIII}t.Fatal(err)
{III}}}
{III}if (expected == actual) != c.equal {{
{IIII}t.Fatalf("Unexpected comparison of %q and %q", expected, actual)
{III}}}
{II}}})
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Assert that the serialization `other`, as XML document, equals the original
//
//	XML document `that` read from the `source`.
func assertSerializationEqualsDeserialization(
{I}t *testing.T,
{I}that string,
{I}other string,
{I}source string,
) (ok bool) {{
{I}ok = true

{I}// NOTE (mristin):
{I}// The following hack is SUPER ugly and unsafe! However, it works. Given Go's
{I}// limited support for XML, we gave up on a safer approach :(. We tested
{I}// the following approaches before applying this hack:
{I}//  * A round-trip over `encoding/xml`. Failed due to
{I}//    https://github.com/golang/go/issues/13400.
{I}//  * Using `aqwari.net/xml/xmltree`. Failed as the special characters in the
{I}//    element content still has not been de-escaped or consistently escaped in
{I}//    a round trip.

{I}canonicalThat, err := canonicalizeXmlForComparison(that)
{I}if err != nil {{
{II}t.Fatalf("Failed to normalize original XML from %s: %s", source, err)
{II}return false
{I}}}
{I}canonicalOther, err := canonicalizeXmlForComparison(other)
{I}if err != nil {{
{II}t.Fatalf("Failed to normalize serialized XML from %s: %s", source, err)
{II}return false
{I}}}

{I}if canonicalThat.numericMarkup != canonicalOther.numericMarkup {{
{II}t.Fatalf("Numeric XML markup differs in %s:\\nORIGINAL:\\n%sSERIALIZED:\\n%s",
{III}source, canonicalThat.numericMarkup, canonicalOther.numericMarkup)
{I}}}
{I}thatLines := strings.Split(canonicalThat.text, "\\n")
{I}otherLines := strings.Split(canonicalOther.text, "\\n")

{I}if canonicalThat.text != canonicalOther.text {{
{II}b := new(strings.Builder)
{II}minLines := len(thatLines)
{II}if minLines > len(otherLines) {{
{III}minLines = len(otherLines)
{II}}}
{II}for i := 0; i < minLines; i++ {{
{III}if thatLines[i] == otherLines[i] {{
{IIII}b.WriteString(fmt.Sprintf("           %s\\n", thatLines[i]))
{III}}} else {{
{IIII}b.WriteString(fmt.Sprintf("ORIGINAL   %s\\n", thatLines[i]))
{IIII}b.WriteString(fmt.Sprintf("SERIALIZED %s\\n", otherLines[i]))
{IIII}break
{III}}}
{II}}}

{II}ok = false
{II}t.Fatalf(
{III}"The canonicalized XML serialization of the de-serialized instance "+
{IIII}"from %s does not equal the canonicalized original XML document:\\n"+
{IIII}"%s",
{III}source, b.String(),
{II})
{II}return
{I}}}

{I}return
}}"""
        ),
        Stripped(
            f"""\
// Assert that there is a de-serialization error.
//
// If [ourtesting.RecordMode] is set, the de-serialization error is re-recorded
// to `expectedPth`. Otherwise, the error is compared against the golden file
// `expectedPth`.
func assertIsDeserializationErrorAndEqualsExpectedOrRecord(
{I}t *testing.T,
{I}err error,
{I}source string,
{I}expectedPth string,
) (ok bool) {{
{I}ok = true

{I}if err == nil {{
{II}ok = false
{II}t.Fatalf("De-serialization error expected from %s, but got none", source)
{II}return
{I}}}

{I}deseriaErr, is := err.(*ourxmlization.DeserializationError)
{I}if !is {{
{II}ok = false
{II}t.Fatalf(
{III}"Expected a de-serialization error, "+
{IIII}"but got an error of type %T from %s: %v",
{III}err, source, err,
{II})
{II}return
{I}}}

{I}// Add a new line for POSIX systems.
{I}got := deseriaErr.Error() + "\\n"

{I}if ourtesting.RecordMode {{
{II}parent := filepath.Dir(expectedPth)
{II}err := os.MkdirAll(parent, os.ModePerm)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to create the directory %s: %s", parent, err.Error(),
{IIII}),
{III})
{II}}}

{II}err = os.WriteFile(expectedPth, []byte(got), 0644)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to write to the file %s: %s", expectedPth, err.Error(),
{IIII}),
{III})
{II}}}
{I}}} else {{
{II}_, err := os.Stat(expectedPth)
{II}if err != nil {{
{III}ok = false
{III}t.Fatalf(
{IIII}"Failed to stat the file %s: %s; if the file does not exist, "+
{IIIII}"you probably want to record the test data by "+
{IIIII}"setting the environment variable %s",
{IIII}expectedPth, err.Error(), ourtesting.RecordModeEnvironmentVariableName,
{III})
{III}return
{II}}}

{II}bb, err := os.ReadFile(expectedPth)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to read from file %s: %s", expectedPth, err.Error(),
{IIII}),
{III})
{II}}}

{II}expected := string(bb)

{II}// NOTE (mristin):
{II}// Git automatically strips and adds `\\r`, so we have to remove it here
{II}// to obtain a canonical text.
{II}expected = strings.Replace(expected, "\\r", "", -1)

{II}if expected != got {{
{III}ok = false
{III}t.Fatalf(
{IIII}"What we got differs from the expected in %s. "+
{IIIII}"We got:\\n%s\\nWe expected:\\n%s",
{IIII}expectedPth, got, expected,
{III})
{III}return
{II}}}
{I}}}

{I}return
}}"""
        ),
        golang_common.WARNING,
    ]

    whitespace_test = _generate_whitespace_round_trip_test(symbol_table)
    if whitespace_test is not None:
        blocks.insert(-1, whitespace_test)

    numeric_test = _generate_numeric_comparison_test(symbol_table)
    if numeric_test is not None:
        blocks.insert(-1, numeric_test)

    if uses_json_types:
        blocks.insert(-1, _generate_xml_rpc_member_order())

    member_order_test = _generate_xml_rpc_member_order_test(symbol_table)
    if member_order_test is not None:
        blocks.insert(-1, member_order_test)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
