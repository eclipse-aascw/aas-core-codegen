# SPDX-FileCopyrightText: 2026 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code to test the XML de-serialization of JSON-able values."""

import html
from typing import List, MutableMapping, Optional

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped
from aas_core_codegen.golang import common as golang_common
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to test the XML de-serialization of JSON-able values."""
    document_prefix: Optional[str] = None
    document_suffix = ""
    for our_type in symbol_table.our_types:
        if not isinstance(our_type, intermediate.ConcreteClass):
            continue
        for prop in our_type.properties:
            if isinstance(
                intermediate.beneath_optional(prop.type_annotation),
                intermediate.JsonValueTypeAnnotation,
            ):
                class_name = naming.xml_class_name(our_type.name)
                property_name = prop.xml_name
                namespace = html.escape(
                    symbol_table.meta_model.xml_namespace, quote=True
                )
                document_prefix = f'<{class_name} xmlns="{namespace}"><{property_name}>'
                document_suffix = f"</{property_name}></{class_name}>"
                break
        if document_prefix is not None:
            break

    imports_by_path: MutableMapping[str, str] = {
        "context": '"context"',
        "encoding/xml": '"encoding/xml"',
        "io": '"io"',
        "reflect": '"reflect"',
        "strings": '"strings"',
        "testing": '"testing"',
        "testing/iotest": '"testing/iotest"',
        f"{repo_url}/types": f'ourtypes "{repo_url}/types"',
        f"{repo_url}/xmlrpc": f'ourxmlrpc "{repo_url}/xmlrpc"',
    }
    model_reader = ""
    model_io_reader = ""
    if document_prefix is not None:
        imports_by_path[
            f"{repo_url}/xmlization"
        ] = f'ourxmlization "{repo_url}/xmlization"'
        prefix_literal = golang_common.string_literal(document_prefix)
        suffix_literal = golang_common.string_literal(document_suffix)
        model_reader = f"""\
{II}{{"xmlization", func(text string) error {{
{III}document := {prefix_literal} + text
{III}if strings.HasSuffix(text, "</array>") {{
{IIII}document += {suffix_literal}
{III}}}
{III}decoder := xml.NewDecoder(strings.NewReader(document))
{III}_, err := ourxmlization.Unmarshal(decoder)
{III}return err
{II}}}}},
"""
        model_io_reader = f"""\
{II}{{"xmlization", func(reader io.Reader) error {{
{III}decoder := xml.NewDecoder(io.MultiReader(strings.NewReader({prefix_literal}), reader))
{III}_, err := ourxmlization.Unmarshal(decoder)
{III}return err
{II}}}}},
"""
    imports = "\n".join(
        f"{I}{imports_by_path[path]}" for path in sorted(imports_by_path)
    )
    blocks: List[Stripped] = [
        Stripped("package xmlrpc_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{imports}
)"""
        ),
        Stripped(
            f"""\
func TestReadValueContentAcceptsWhitespaceBetweenElements(t *testing.T) {{
{I}containers := []struct {{
{II}name     string
{II}prefix   string
{II}suffix   string
{II}expected ourtypes.JsonValue
{I}}}{{
{II}{{
{III}name:     "array",
{III}prefix:   "<array><data><value>",
{III}suffix:   "</value></data></array>",
{III}expected: ourtypes.JsonArray{{"hello"}},
{II}}},
{II}{{
{III}name:     "object",
{III}prefix:   "<struct><member><name>key</name><value>",
{III}suffix:   "</value></member></struct>",
{III}expected: ourtypes.JsonObject{{"key": "hello"}},
{II}}},
{I}}}
{I}separators := []struct {{
{II}name string
{II}text string
{I}}}{{
{II}{{"compact", ""}},
{II}{{"lf", "\\n  "}},
{II}{{"tab_indentation", "\\n\\t"}},
{II}{{"crlf", "\\r\\n  "}},
{II}{{"comment", "<!-- comment -->"}},
{II}{{"comment_with_whitespace", "\\n  <!-- comment -->\\n  "}},
{I}}}
{I}for _, container := range containers {{
{II}for _, separator := range separators {{
{III}t.Run(container.name+"/"+separator.name, func(t *testing.T) {{
{IIII}text := container.prefix + "<string>hello</string>" + container.suffix
{IIII}text = strings.ReplaceAll(text, "><", ">"+separator.text+"<")
{IIII}decoder := xml.NewDecoder(strings.NewReader(text))
{IIII}current, err := decoder.Token()
{IIII}if err != nil {{
{IIIII}t.Fatal(err)
{IIII}}}
{IIII}got, _, err := ourxmlrpc.ReadValueContent(decoder, current)
{IIII}if err != nil {{
{IIIII}t.Fatalf("Expected no error, but got: %v", err)
{IIII}}}
{IIII}if !reflect.DeepEqual(got, container.expected) {{
{IIIII}t.Fatalf("Expected %#v, but got %#v", container.expected, got)
{IIII}}}
{III}}})
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestReadValueContentPreservesStringWhitespace(t *testing.T) {{
{I}cases := []struct {{
{II}name string
{II}text string
{I}}}{{
{II}{{"empty", ""}},
{II}{{"spaces", " hello "}},
{II}{{"whitespace_only", " \\t\\n "}},
{II}{{"mixed", " \\thello\\n "}},
{II}{{"unicode_whitespace", "\\u00a0hello\\u2003"}},
{II}{{"unicode_whitespace_only", "\\u00a0\\u2003"}},
{I}}}
{I}for _, c := range cases {{
{II}t.Run(c.name, func(t *testing.T) {{
{III}text := "<array><data><value>\\n  <string>" + c.text +
{IIII}"</string>\\n  </value></data></array>"
{III}decoder := xml.NewDecoder(strings.NewReader(text))
{III}current, err := decoder.Token()
{III}if err != nil {{
{IIII}t.Fatal(err)
{III}}}
{III}got, _, err := ourxmlrpc.ReadValueContent(decoder, current)
{III}if err != nil {{
{IIII}t.Fatalf("Expected no error, but got: %v", err)
{III}}}
{III}expected := ourtypes.JsonArray{{c.text}}
{III}if !reflect.DeepEqual(got, expected) {{
{IIII}t.Fatalf("Expected %#v, but got %#v", expected, got)
{III}}}
{II}}})
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestReadValueContentRejectsInvalidValueEnd(t *testing.T) {{
{I}cases := []struct {{
{II}name   string
{II}suffix string
{I}}}{{
{II}{{"trailing_text", "unexpected</value></data></array>"}},
{II}{{"text_after_whitespace", "\\n  unexpected</value></data></array>"}},
{II}{{"non_breaking_space", "\\u00a0</value></data></array>"}},
{II}{{"em_space", "\\u2003</value></data></array>"}},
{II}{{"non_breaking_space_reference", "&#xA0;</value></data></array>"}},
{II}{{"em_space_reference", "&#x2003;</value></data></array>"}},
{II}{{"extra_child", "<string>extra</string></value></data></array>"}},
{I}}}
{I}for _, c := range cases {{
{II}t.Run(c.name, func(t *testing.T) {{
{III}text := "<array><data><value><string>hello</string>" + c.suffix
{III}decoder := xml.NewDecoder(strings.NewReader(text))
{III}current, err := decoder.Token()
{III}if err != nil {{
{IIII}t.Fatal(err)
{III}}}
{III}_, _, err = ourxmlrpc.ReadValueContent(decoder, current)
{III}if err == nil {{
{IIII}t.Fatal("Expected an error, but got none")
{III}}}
{III}if _, ok := err.(*ourxmlrpc.DeserializationError); !ok {{
{IIII}t.Fatalf("Expected a deserialization error, but got %T: %v", err, err)
{III}}}
{II}}})
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestReadValueContentRejectsMalformedXml(t *testing.T) {{
{I}readers := []struct {{
{II}name string
{II}read func(string) error
{I}}}{{
{II}{{"xmlrpc", func(text string) error {{
{III}decoder := xml.NewDecoder(strings.NewReader(text))
{III}current, err := decoder.Token()
{III}if err != nil {{
{IIII}return err
{III}}}
{III}_, _, err = ourxmlrpc.ReadValueContent(decoder, current)
{III}return err
{II}}}}},
{model_reader}{I}}}
{I}separators := []struct {{
{II}name string
{II}text string
{I}}}{{
{II}{{"whitespace", "\\n "}},
{II}{{"comment", "<!-- comment -->"}},
{II}{{"whitespace_and_comment", "\\n <!-- comment -->\\n "}},
{I}}}
{I}endings := []struct {{
{II}name string
{II}text string
{I}}}{{
{II}{{"truncated", ""}},
{II}{{"mismatched_end", "</wrong></data></array>"}},
{II}{{"invalid_entity", "&invalid;</value></data></array>"}},
{I}}}
{I}for _, reader := range readers {{
{II}for _, separator := range separators {{
{III}for _, ending := range endings {{
{IIII}t.Run(reader.name+"/"+separator.name+"/"+ending.name, func(t *testing.T) {{
{IIIII}text := `<array xmlns=""><data><value><string>hello</string>` +
{IIIIII}separator.text + ending.text
{IIIII}err := reader.read(text)
{IIIII}if err == nil {{
{IIIIII}t.Fatal("Expected an error, but got none")
{IIIII}}}
{IIIII}if _, ok := err.(*xml.SyntaxError); !ok {{
{IIIIII}t.Fatalf("Expected an XML syntax error, but got %T: %v", err, err)
{IIIII}}}
{IIII}}})
{III}}}
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestReadValueContentPreservesReaderError(t *testing.T) {{
{I}readers := []struct {{
{II}name string
{II}read func(io.Reader) error
{I}}}{{
{II}{{"xmlrpc", func(reader io.Reader) error {{
{III}decoder := xml.NewDecoder(reader)
{III}current, err := decoder.Token()
{III}if err != nil {{
{IIII}return err
{III}}}
{III}_, _, err = ourxmlrpc.ReadValueContent(decoder, current)
{III}return err
{II}}}}},
{model_io_reader}{I}}}
{I}prefixes := []struct {{
{II}name string
{II}text string
{I}}}{{
{II}{{"array", `<array xmlns=""><data><value><string>hello</string>`}},
{II}{{"object", `<struct xmlns=""><member><name>key</name><value><string>hello</string>`}},
{I}}}
{I}for _, reader := range readers {{
{II}for _, prefix := range prefixes {{
{III}t.Run(reader.name+"/"+prefix.name, func(t *testing.T) {{
{IIII}input := io.MultiReader(
{IIIII}strings.NewReader(prefix.text+"\\n "),
{IIIII}iotest.ErrReader(context.DeadlineExceeded),
{IIII})
{IIII}err := reader.read(input)
{IIII}if err != context.DeadlineExceeded {{
{IIIII}t.Fatalf("Expected the original deadline error, but got %T: %v", err, err)
{IIII}}}
{III}}})
{II}}}
{I}}}
}}"""
        ),
        golang_common.WARNING,
    ]

    return "\n\n".join(blocks) + "\n"


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
