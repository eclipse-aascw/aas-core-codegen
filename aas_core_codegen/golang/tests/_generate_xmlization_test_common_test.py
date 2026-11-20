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
{I}canonicalByValue := make(map[string]string)
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


def _generate_text_context(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Identify string content by its position in the model's XML structure."""
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

        key = f"content:{golang_common.type_moniker(type_anno)}"
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
            for i, item in enumerate(type_anno.items):
                children_by_type[key].update(items(item, f"v{i + 1}"))
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
// Follow the model's XML nesting to recognize string values, including collection
// items. Container whitespace remains available to the existing indentation cleanup.
func xmlTextContext(parent string, name xml.Name) string {{
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
{I}"os"
{I}"path/filepath"
{I}"regexp"
{I}"strings"
{I}"testing"

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
// Normalize escaping in character data while retaining the original markup.
// Copying tags verbatim avoids changing namespace declarations or prefixes.
func normalizeXmlTextEscaping(text string) (string, error) {{
{I}decoder := xml.NewDecoder(strings.NewReader(text))
{I}var result bytes.Buffer
{I}contexts := []string{{"root"}}
{I}for {{
{II}start := decoder.InputOffset()
{II}token, err := decoder.Token()
{II}if err == io.EOF {{
{III}return result.String(), nil
{II}}}
{II}if err != nil {{
{III}return "", err
{II}}}
{II}if start, ok := token.(xml.StartElement); ok {{
{III}contexts = append(contexts, xmlTextContext(contexts[len(contexts)-1], start.Name))
{II}}}
{II}if data, ok := token.(xml.CharData); ok {{
{III}// Normalize strings consistently, even if they consist only of whitespace.
{III}// Keep container indentation available to the existing cleanup.
{III}if contexts[len(contexts)-1] != "text" && strings.Trim(string(data), " \\t\\r\\n") == "" {{
{IIII}result.WriteString(text[start:decoder.InputOffset()])
{III}}} else {{
{IIII}var escaped bytes.Buffer
{IIII}if err := xml.EscapeText(&escaped, data); err != nil {{
{IIIII}return "", err
{IIII}}}
{IIII}if contexts[len(contexts)-1] == "text" {{
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
{III}contexts = contexts[:len(contexts)-1]
{II}}}
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
{III}if got != c.want {{
{IIII}t.Fatalf("Expected %q, got %q", c.want, got)
{III}}}
{II}}})
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func canonicalizeXmlForComparison(text string) (string, error) {{
{I}text = strings.TrimSpace(text)
{I}// Escape text before applying the legacy markup cleanup, so a literal
{I}// '>' in a value can not make the cleanup remove a preceding space.
{I}text, err := normalizeXmlTextEscaping(text)
{I}if err != nil {{
{II}return "", err
{I}}}
{I}text = strings.ReplaceAll(text, "\\r", "")
{I}text = removeWhitespaceBetweenTags(text)
{I}text = forceSelfClosingTags(text)
{I}return removeWhitespaceWithinTags(text), nil
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

{I}thatLines := strings.Split(canonicalThat, "\\n")
{I}otherLines := strings.Split(canonicalOther, "\\n")

{I}if canonicalThat != canonicalOther {{
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

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
