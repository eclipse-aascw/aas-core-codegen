# SPDX-FileCopyrightText: 2026 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code to test the XML de-serialization of JSON-able values."""

from typing import List, Mapping

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.golang import common as golang_common
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(repo_url: Stripped) -> str:
    """Generate code to test the XML de-serialization of JSON-able values."""
    imports_by_path: Mapping[str, str] = {
        "encoding/xml": '"encoding/xml"',
        "reflect": '"reflect"',
        "strings": '"strings"',
        "testing": '"testing"',
        f"{repo_url}/types": f'ourtypes "{repo_url}/types"',
        f"{repo_url}/xmlrpc": f'ourxmlrpc "{repo_url}/xmlrpc"',
    }
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
{II}}})
{I}}}
}}"""
        ),
        golang_common.WARNING,
    ]

    return "\n\n".join(blocks) + "\n"


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
