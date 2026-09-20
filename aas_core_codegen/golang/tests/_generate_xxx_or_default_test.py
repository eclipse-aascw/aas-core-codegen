"""Generate code to test ``*OrDefault`` functions."""


import io
from typing import List, Optional

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.golang import common as golang_common, naming as golang_naming
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


#: Stand in for the import block, which is filled in at the very end: it
#: depends on what the generated code actually names, and an unused import does
#: not compile in Go.
_IMPORT_PLACEHOLDER = Stripped("")


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to test ``*OrDefault`` functions."""
    blocks = [
        Stripped("package types_xxx_or_default_test"),
        golang_common.WARNING,
        _IMPORT_PLACEHOLDER,
        Stripped(
            f"""\
// Represent explicitly a literal of an enumeration.
type enumerationLiteral struct {{
{I}enumerationName string
{I}literalName string
}}"""
        ),
        Stripped(
            f"""\
func (el *enumerationLiteral) String() string {{
{I}return fmt.Sprintf("%s.%s", el.enumerationName, el.literalName)
}}"""
        ),
        Stripped(
            f"""\
// Marshal the value as JSON, or panic otherwise.
func mustJSONMarshal(value interface{{}}) string {{
{I}bb, err := json.Marshal(value)
{I}if err != nil {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Failed to marshal the value %v to JSON: %s",
{IIII}value, err.Error(),
{III}),
{II})
{I}}}

{I}return string(bb)
}}"""
        ),
        Stripped(
            f"""\
func stringify(value interface{{}}) (got string) {{
{I}if value == nil {{
{II}got = mustJSONMarshal(value)
{I}}} else {{
{II}// See: https://stackoverflow.com/questions/38748098/golang-type-switch-how-to-match-a-generic-slice-array-map-chan
{II}reflected := reflect.ValueOf(value)

{II}if reflected.Kind() == reflect.Slice {{
{III}parts := make([]string, reflected.Len())

{III}for i := 0; i < reflected.Len(); i++ {{
{IIII}item := reflected.Index(i)
{IIII}parts[i] = stringify(item)
{III}}}

{III}got = fmt.Sprintf("[%s]", strings.Join(parts, ", "))
{II}}} else {{
{III}switch casted := value.(type) {{
{III}case bool:
{IIII}got = mustJSONMarshal(casted)
{III}case int:
{IIII}got = mustJSONMarshal(casted)
{III}case string:
{IIII}got = mustJSONMarshal(casted)
{III}case []byte:
{IIII}got = fmt.Sprintf("%d byte(s)", len(casted))
{III}case *enumerationLiteral:
{IIII}got = casted.String()
{III}case aastypes.IClass:
{IIII}got = aastesting.TraceMark(casted)
{III}default:
{IIII}panic(
{IIII}{I}fmt.Sprintf(
{IIII}{II}"We do not know hot to represent the value of type %T: %v",
{IIII}{II}value, value,
{IIII}{I}),
{IIII})
{III}}}
{II}}}
{I}}}

{I}return
}}"""
        ),
        Stripped(
            f"""\
// Represent `value` such that we can immediately check whether it is the default value
// or the set one.
//
// We compare it against the recorded golden file, if not [aastesting.RecordMode].
// If there are differences, a `message` is set.
//
// Otherwise, when [aastesting.RecordMode] is set, we re-record the golden file.
func compareOrRerecordValue(
{I}value interface{{}},
{I}expectedPath string,
) (message *string) {{
{I}got := stringify(value)

{I}// NOTE (mristin):
{I}// Add a new line for POSIX systems.
{I}got += "\\n"

{I}if aastesting.RecordMode {{
{II}parent := filepath.Dir(expectedPath)
{II}err := os.MkdirAll(parent, os.ModePerm)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIII}{I}"Failed to create the directory %s: %s", parent, err.Error(),
{IIII}),
{III})
{II}}}

{II}err = os.WriteFile(expectedPath, []byte(got), 0644)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIII}{I}"Failed to write to the file %s: %s", expectedPath, err.Error(),
{IIII}),
{III})
{II}}}
{I}}} else {{
{II}bb, err := os.ReadFile(expectedPath)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIII}{I}"Failed to read from file %s: %s", expectedPath, err.Error(),
{IIII}),
{III})
{II}}}

{II}expected := string(bb)

{II}// NOTE (mristin):
{II}// Git automatically strips and adds `\\r`, so we have to remove it here
{II}// to obtain a canonical text.
{II}expected = strings.Replace(expected, "\\r", "", -1)

{II}if expected != got {{
{III}text := fmt.Sprintf(
{IIII}"What we got differs from the expected in %s. " +
{IIII}"We got:\\n%s\\nWe expected:\\n%s",
{IIII}expectedPath, got, expected,
{III})
{III}message = &text
{II}}}
{I}}}

{I}return
}}"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        x_or_default_methods = [
            method
            for method in concrete_cls.methods
            if method.name.endswith("_or_default")
        ]  # type: List[intermediate.MethodUnion]

        model_type = naming.json_model_type(concrete_cls.name)

        for method in x_or_default_methods:
            method_name = golang_naming.method_name(method.name)

            result_enum = None  # type: Optional[intermediate.Enumeration]
            assert method.returns is not None, (
                f"Expected all X_or_default to return something, "
                f"but got None for {concrete_cls}.{method.name}"
            )

            if isinstance(
                method.returns, intermediate.OurTypeAnnotation
            ) and isinstance(method.returns.our_type, intermediate.Enumeration):
                result_enum = method.returns.our_type

            if result_enum is None:
                value_assignment_snippet = Stripped(
                    f"value := instance.{method_name}()"
                )
            else:
                enum_to_string_name = golang_naming.function_name(
                    Identifier(f"must_{result_enum.name}_to_string")
                )

                enum_name = golang_naming.enum_name(result_enum.name)

                value_assignment_snippet = Stripped(
                    f"""\
value := &enumerationLiteral{{
{I}enumerationName: {golang_common.string_literal(enum_name)},
{I}literalName: aasstringification.{enum_to_string_name}(
{II}instance.{method_name}(),
{I}),
}}"""
                )

            test_function_name = golang_naming.function_name(
                Identifier(f"Test_{concrete_cls.name}_{method.name}_on_minimal")
            )

            must_load_minimal_name = golang_naming.function_name(
                Identifier(f"must_load_minimal_{concrete_cls.name}")
            )

            blocks.append(
                Stripped(
                    f"""\
func {test_function_name}(t *testing.T) {{
{I}instance := aastesting.{must_load_minimal_name}()

{I}{indent_but_first_line(value_assignment_snippet, I)}

{I}expectedPth := filepath.Join(
{II}aastesting.TestDataDir,
{II}"XxxOrDefault",
{II}{golang_common.string_literal(model_type)},
{II}"{method_name}.on_minimal.txt",
{I})

{I}message := compareOrRerecordValue(
{II}value,
{II}expectedPth,
{I})

{I}if message != nil {{
{II}t.Fatal(*message)
{I}}}
}}"""
                )
            )

            test_function_name = golang_naming.function_name(
                Identifier(f"Test_{concrete_cls.name}_{method.name}_on_maximal")
            )

            must_load_maximal_name = golang_naming.function_name(
                Identifier(f"must_load_maximal_{concrete_cls.name}")
            )

            blocks.append(
                Stripped(
                    f"""\
func {test_function_name}(t *testing.T) {{
{I}instance := aastesting.{must_load_maximal_name}()

{I}{indent_but_first_line(value_assignment_snippet, I)}

{I}expectedPth := filepath.Join(
{II}aastesting.TestDataDir,
{II}"XxxOrDefault",
{II}{golang_common.string_literal(model_type)},
{II}"{method_name}.on_maximal.txt",
{I})

{I}message := compareOrRerecordValue(
{II}value,
{II}expectedPth,
{I})

{I}if message != nil {{
{II}t.Fatal(*message)
{I}}}
}}"""
                )
            )

    blocks.append(golang_common.WARNING)

    import_index = blocks.index(_IMPORT_PLACEHOLDER)

    import_lines = []  # type: List[str]
    for module, literal in (
        ("filepath", f'{I}"path/filepath"'),
        ("fmt", f'{I}"fmt"'),
        ("json", f'{I}"encoding/json"'),
        ("os", f'{I}"os"'),
        ("reflect", f'{I}"reflect"'),
        ("strings", f'{I}"strings"'),
        ("testing", f'{I}"testing"'),
        ("aasstringification", f'{I}aasstringification "{repo_url}/stringification"'),
        ("aastesting", f'{I}aastesting "{repo_url}/aastesting"'),
        ("aastypes", f'{I}aastypes "{repo_url}/types"'),
    ):
        if golang_common.names_package(blocks, module):
            import_lines.append(literal)

    blocks[import_index] = Stripped("import (\n" + "\n".join(import_lines) + "\n)")

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
