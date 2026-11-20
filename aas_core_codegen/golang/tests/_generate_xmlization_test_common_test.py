# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code for common XML de/serialization shared across the tests."""

import html
import io
from typing import List, MutableMapping, Optional, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
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
{I}canonicalByValue := make(map[string]xmlComparison)
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
// NOTE (mristin):
// Currently, Go does not support self-closing tags,
// see: https://github.com/golang/go/issues/21399.
// We apply the following hack to make the tags self-closing even if they are not.
// This is unsafe in general, but works OK for the limited set of test data that we are
// here dealing with.
//
// The code has been taken from: https://github.com/golang/go/issues/21399#issuecomment-1342730174"""
        ),
        Stripped(
            """\
// NOTE (mristin):
// The opening tag, tag name plus an optional attribute list (*e.g.*,
// ``xmlns="..."`` on a root element), is captured in the first (and only)
// submatch group so that we do not lose any attributes when we force
// the tag to be self-closing below. The attribute list must not end with
// a slash, as we would otherwise match an already self-closing tag followed
// by the closing tag of its parent, *e.g.*, ``<someBytes /></something>``.
var emptyTagRe = regexp.MustCompile(`<(\\w+(?:\\s[^>]*[^/>])?)></\\w+>`)"""
        ),
        Stripped(
            f"""\
func forceSelfClosingTags(text string) string {{
{I}b := []byte(text)
{I}emptyTagIdxs := emptyTagRe.FindAllSubmatchIndex(b, -1)

{I}if len(emptyTagIdxs) == 0 {{
{II}return text
{I}}}

{I}// NOTE (mristin):
{I}// The matches are walked in order, and the pieces of `b` between them are
{I}// copied over as they are. Mind that `nb` starts out empty and that `b` is
{I}// only ever *read*: an earlier version appended into `b[0:idx[0]]`, which
{I}// writes into `b`'s own backing array, so a document with more than one
{I}// empty tag came out garbled -- every turn of the loop then indexed into
{I}// a `b` which the previous turn had already overwritten.
{I}var nb []byte
{I}previous := 0

{I}for _, idx := range emptyTagIdxs {{
{II}// Copy everything since the previous match, then the tag itself --
{II}// its name and its attributes -- as a self-closing one.
{II}nb = append(nb, b[previous:idx[0]]...)
{II}nb = append(nb, fmt.Sprintf("<%s/>", b[idx[2]:idx[3]])...)

{II}previous = idx[1]
{I}}}

{I}// Finally, copy everything after the last match.
{I}nb = append(nb, b[previous:]...)

{I}return string(nb)
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
const xmlComparisonMarker = "{golang_common.repo_url_to_environment_variable(repo_url)}_XML_COMPARISON_PI"

func canonicalizeXmlForComparison(text string) (xmlComparison, error) {{
{I}text = strings.TrimSpace(text)
{I}// Escape text before applying the legacy markup cleanup, so a literal
{I}// '>' in a value can not make the cleanup remove a preceding space.
{I}comparison, err := normalizeXmlTextEscaping(text)
{I}if err != nil {{
{II}return xmlComparison{{}}, err
{I}}}
{I}text = comparison.text
{I}// Protect processing instructions while the legacy regexes clean up markup.
{I}// The marker target is absent even after carriage-return removal.
{I}markerPrefix := xmlComparisonMarker
{I}withoutCR := strings.ReplaceAll(text, "\\r", "")
{I}for strings.Contains(withoutCR, markerPrefix) {{
{II}markerPrefix += "X"
{I}}}
{I}var instructions []string
{I}var protected bytes.Buffer
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
{II}if _, ok := token.(xml.ProcInst); ok {{
{III}fmt.Fprintf(&protected, "<?%s%d?>", markerPrefix, len(instructions))
{III}// XML 1.0 section 2.11 normalizes literal line endings before parsing.
{III}original = strings.ReplaceAll(strings.ReplaceAll(original, "\\r\\n", "\\n"), "\\r", "\\n")
{III}instructions = append(instructions, original)
{II}}} else {{
{III}protected.WriteString(original)
{II}}}
{I}}}
{I}text = protected.String()
{I}text = strings.ReplaceAll(text, "\\r", "")
{I}text = removeWhitespaceBetweenTags(text)
{I}text = forceSelfClosingTags(text)
{I}text = removeWhitespaceWithinTags(text)
{I}for i, original := range instructions {{
{II}text = strings.ReplaceAll(text, fmt.Sprintf("<?%s%d?>", markerPrefix, i), original)
{I}}}
{I}comparison.text = text
{I}return comparison, nil
}}"""
        ),
        Stripped(
            f"""\
func TestXmlComparisonPreservesText(t *testing.T) {{
{I}for _, c := range []struct {{
{II}name     string
{II}expected string
{II}actual   string
{II}equal    bool
{I}}}{{
{II}{{"equivalent_escaping", `<v>x ></v>`, `<v>x &gt;</v>`, true}},
{II}{{"lost_space", `<v>x ></v>`, `<v>x&gt;</v>`, false}},
{II}{{"numeric_reference", `<v>x ></v>`, `<v>x &#62;</v>`, true}},
{II}{{"extra_space", `<v>x ></v>`, `<v>x  &gt;</v>`, false}},
{II}{{"tab_vs_newline", `<v>&#x9;</v>`, `<v>&#xA;</v>`, false}},
{II}{{"tab_vs_space", `<v>&#x9;</v>`, `<v>&#32;</v>`, false}},
{II}{{"lost_tab", `<v>&#x9;</v>`, `<v></v>`, false}},
{II}{{"space_vs_literal_tab", `<v>&#32;</v>`, "<v>\\t</v>", false}},
{II}{{"instruction_data", `<v><?p x > y?></v>`, `<v><?p x> y?></v>`, false}},
{II}{{"instruction_markup", `<v><?p <a></a>?></v>`, `<v><?p <a/>?></v>`, false}},
{II}{{"instruction_cr", "<v><?p x\\ry?></v>", `<v><?p xy?></v>`, false}},
{II}{{"instruction_cr_as_lf", "<v><?p x\\ry?></v>", "<v><?p x\\ny?></v>", true}},
{II}{{"instruction_crlf_as_lf", "<v><?p x\\r\\ny?></v>", "<v><?p x\\ny?></v>", true}},
{II}{{"instruction_indentation", "<v>\\n<?p x > y?>\\n</v>", `<v><?p x > y?></v>`, true}},
{II}{{
{III}"instruction_marker",
{III}"<v><!--<?" + xmlComparisonMarker + "0?>--><?p x?></v>",
{III}"<v><!--<?p x?>--><?p x?></v>",
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

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
