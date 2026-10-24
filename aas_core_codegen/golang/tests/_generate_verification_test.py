"""Generate code to test the verification."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    Identifier,
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


def _generate_test_runtime_range_for_enum(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the test for checking the valid enumeration range."""
    test_name = golang_naming.function_name(
        Identifier(f"test_{enumeration.name}_runtime_range")
    )

    verify_function = golang_naming.function_name(
        Identifier(f"verify_{enumeration.name}")
    )

    enum_name = golang_naming.enum_name(enumeration.name)

    if len(enumeration.literals) == 0:
        return Stripped(
            f"""\
func {test_name}(t *testing.T) {{
{I}var gotErr *ourverification.VerificationError

{I}// Any value should cause an error since {enum_name}
{I}// specifies no literals.
{I}{verify_function}(
{II}42,
{II}func (err *ourverification.VerificationError) bool {{
{III}gotErr = err
{III}return
{II}}},
{I})

{I}if gotErr == nil {{
{II}t.Fatal("Expected an error, but got none.")
{II}return
{I}}}
}}"""
        )
    else:
        first_literal_idx = 0
        last_literal_idx = len(enumeration.literals) - 1

        return Stripped(
            f"""\
func {test_name}(t *testing.T) {{
{I}var gotErr *ourverification.VerificationError

{I}// No error is expected on the first literal.
{I}ourverification.{verify_function}(
{II}ourtypes.{enum_name}({first_literal_idx}),
{II}func (err *ourverification.VerificationError) bool {{
{III}gotErr = err
{III}return false
{II}}},
{I})

{I}if gotErr != nil {{
{II}t.Fatalf("Expected no error, but got: %s", gotErr.Message)
{II}return
{I}}}

{I}// No error is expected on the last literal.
{I}ourverification.{verify_function}(
{II}ourtypes.{enum_name}({last_literal_idx}),
{II}func (err *ourverification.VerificationError) bool {{
{III}gotErr = err
{III}return false
{II}}},
{I})

{I}if gotErr != nil {{
{II}t.Fatalf("Expected no error, but got: %s", gotErr.Message)
{II}return
{I}}}

{I}// An error is expected before the first literal.
{I}gotErr = nil
{I}ourverification.{verify_function}(
{II}ourtypes.{enum_name}({first_literal_idx} - 1),
{II}func (err *ourverification.VerificationError) bool {{
{III}gotErr = err
{III}return false
{II}}},
{I})

{I}if gotErr == nil {{
{II}t.Fatal("Expected an error, but got none.")
{II}return
{I}}}

{I}// An error is expected after the last literal.
{I}gotErr = nil
{I}ourverification.{verify_function}(
{II}ourtypes.{enum_name}({last_literal_idx} + 1),
{II}func (err *ourverification.VerificationError) bool {{
{III}gotErr = err
{III}return false
{II}}},
{I})

{I}if gotErr == nil {{
{II}t.Fatal("Expected an error, but got none.")
{II}return
{I}}}
}}"""
        )


def _generate_for_cls(cls: intermediate.ConcreteClass) -> List[Stripped]:
    """Generate the tests for a class."""
    model_type_literal = golang_common.string_literal(naming.json_model_type(cls.name))

    deserialization_function = golang_naming.function_name(
        Identifier(f"{cls.name}_from_jsonable")
    )

    blocks: List[Stripped] = []

    test_name = golang_naming.function_name(Identifier(f"Test_{cls.name}_OK"))

    blocks.append(
        Stripped(
            f"""\
func {test_name}(t *testing.T) {{
{I}pths := ourtesting.FindFilesBySuffixRecursively(
{II}filepath.Join(
{III}ourtesting.TestDataDir,
{III}"Json",
{III}"Expected",
{III}{model_type_literal},
{II}),
{II}".json",
{I})
{I}sort.Strings(pths)

{I}for _, pth := range pths {{
{II}jsonable := ourtesting.MustReadJsonable(
{III}pth,
{II})

{II}deserialized, deseriaErr := ourjsonization.{deserialization_function}(
{III}jsonable,
{II})
{II}if deseriaErr != nil {{
{III}t.Fatalf(
{IIII}"Unexpected deserialization error from %s: %s",
{IIII}pth, deseriaErr.Error(),
{III})
{III}return
{II}}}

{II}var errors []*ourverification.VerificationError
{II}ourverification.Verify(
{III}deserialized,
{III}func(veriErr *ourverification.VerificationError) (abort bool) {{
{IIII}errors = append(errors, veriErr)
{IIII}return
{III}}},
{II})

{II}ok := assertNoVerificationErrors(
{III}t,
{III}deserialized,
{III}pth,
{II})
{II}if !ok {{
{III}return
{II}}}
{I}}}
}}"""
        )
    )

    test_name = golang_naming.function_name(Identifier(f"Test_{cls.name}_fail"))

    blocks.append(
        Stripped(
            f"""\
func {test_name}(t *testing.T) {{
{I}pattern := filepath.Join(
{II}ourtesting.TestDataDir,
{II}"Json",
{II}"Unexpected",
{II}"Invalid",
{II}"*",  // This asterisk represents the cause.
{II}{model_type_literal},
{I})

{I}causeDirs, err := filepath.Glob(pattern)
{I}if err != nil {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Failed to find cause directories matching %s: %s",
{IIII}pattern, err.Error(),
{III}),
{II})
{I}}}

{I}for _, causeDir := range causeDirs {{
{II}pths := ourtesting.FindFilesBySuffixRecursively(
{III}causeDir,
{III}".json",
{II})
{II}sort.Strings(pths)

{II}for _, pth := range pths {{
{III}jsonable := ourtesting.MustReadJsonable(
{IIII}pth,
{III})

{III}relPth, err := filepath.Rel(ourtesting.TestDataDir, pth)
{III}if err != nil {{
{IIII}panic(
{IIIII}fmt.Sprintf(
{IIIIII}"Failed to compute the relative path of %s to %s: %s",
{IIIIII}ourtesting.TestDataDir, pth, err.Error(),
{IIIII}),
{IIII})
{III}}}

{III}expectedPth := filepath.Join(
{IIII}ourtesting.TestDataDir,
{IIII}"VerificationError",
{IIII}filepath.Dir(relPth),
{IIII}filepath.Base(relPth)+".errors",
{III})

{III}deserialized, deseriaErr := ourjsonization.{deserialization_function}(
{IIII}jsonable,
{III})
{III}if deseriaErr != nil {{
{IIII}t.Fatalf(
{IIIII}"Unexpected deserialization error from %s: %s",
{IIIII}pth, deseriaErr.Error(),
{IIII})
{IIII}return
{III}}}

{III}var errors []*ourverification.VerificationError
{III}ourverification.Verify(
{IIII}deserialized,
{IIII}func(err *ourverification.VerificationError) (abort bool) {{
{IIIII}errors = append(errors, err)
{IIIII}return
{IIII}}},
{III})

{III}ok := assertEqualsExpectedOrRerecordVerificationErrors(
{IIII}t,
{IIII}errors,
{IIII}pth,
{IIII}expectedPth,
{III})
{III}if !ok {{
{IIII}return
{III}}}
{II}}}
{I}}}
}}"""
        )
    )

    return blocks


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to test the verification."""
    blocks: List[Stripped] = [
        Stripped("package verification_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"encoding/json"
{I}"fmt"
{I}"os"
{I}"path/filepath"
{I}"sort"
{I}"strings"
{I}"testing"
{I}ourjsonization "{repo_url}/jsonization"
{I}ourtesting "{repo_url}/ourtesting"
{I}ourtypes "{repo_url}/types"
{I}ourverification "{repo_url}/verification"
)"""
        ),
        Stripped(
            f"""\
// Assert that there are no verification errors in the `instance` de-serialized
// from `source`.
func assertNoVerificationErrors(
{I}t *testing.T,
{I}instance ourtypes.IClass,
{I}source string,
) (ok bool) {{
{I}errors := make([]*ourverification.VerificationError, 0)
{I}ourverification.Verify(
{II}instance,
{II}func(err *ourverification.VerificationError) (abort bool) {{
{III}errors = append(errors, err)
{III}return
{II}}},
{I})

{I}ok = true
{I}if len(errors) > 0 {{
{II}ok = false

{II}var sb strings.Builder

{II}sb.WriteString(
{III}fmt.Sprintf(
{IIII}"Expected no errors when verifying the instance de-serialized from "+
{IIIII}"%s, but got %d error(s)\\n",
{IIII}source, len(errors),
{III}),
{II})

{II}for i, err := range errors {{
{III}sb.WriteString(
{IIII}fmt.Sprintf(
{IIIII}"Error %d:\\n%s: %s\\n",
{IIIII}i+1,
{IIIII}err.PathString(),
{IIIII}err.Message,
{IIII}),
{III})
{II}}}

{II}jsonable, seriaErr := ourjsonization.ToJsonable(instance)
{II}if seriaErr != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to serialize instance to JSON obtained from %s: %s",
{IIIII}source, seriaErr.Error(),
{IIII}),
{III})
{II}}}
{II}jsonableBytes, err := json.Marshal(jsonable)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to marshal to JSON an instance serialized from %s: %s",
{IIIII}source, err.Error(),
{IIII}),
{III})
{II}}}

{II}sb.WriteString("Instance:\\n")
{II}sb.WriteString(string(jsonableBytes))

{II}t.Fatal(sb.String())
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Assert that either the verification errors match the recorded ones at `pth`, if
// [ourtesting.RecordMode] is set, or re-record the verification errors at `pth`.
func assertEqualsExpectedOrRerecordVerificationErrors(
{I}t *testing.T,
{I}errors []*ourverification.VerificationError,
{I}source string,
{I}expectedPth string,
) (ok bool) {{
{I}ok = true
{I}if len(errors) == 0 {{
{II}ok = false
{II}t.Fatalf(
{III}"Expected at least one verification error, "+
{IIII}"but got none when verifying the model loaded from: %s",
{III}source,
{II})
{I}}}

{I}parts := make([]string, len(errors))
{I}for i, verErr := range errors {{
{II}parts[i] = fmt.Sprintf(
{III}"%s: %s",
{III}verErr.PathString(),
{III}verErr.Message,
{II})
{I}}}

{I}// Add a newline for POSIX systems
{I}got := strings.Replace(strings.Join(parts, ";\\n"), "\\r\\n", "\\n", -1) + "\\n"

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
{III}ok = false
{III}t.Fatalf("Failed to write to %s: %s", expectedPth, err.Error())
{III}return
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

{II}var bb []byte
{II}bb, err = os.ReadFile(expectedPth)
{II}if err != nil {{
{III}ok = false
{III}t.Fatalf("Failed to read from %s: %s", expectedPth, err.Error())
{III}return
{II}}}
{II}expected := strings.ReplaceAll(string(bb), "\\r\\n", "\\n")

{II}if expected != got {{
{III}ok = false
{III}t.Fatalf(
{IIII}"The expected verification errors (read from %s) in the model "+
{IIIII}"de-serialized from %s do not match the obtained ones. "+
{IIIII}"Expected:\\n%s\\nGot:\\n%s",
{IIII}expectedPth, source, expected, got,
{III})
{III}return
{II}}}
{I}}}
{I}return
}}"""
        ),
    ]

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_test_runtime_range_for_enum(enumeration=enumeration))

    for concrete_cls in symbol_table.concrete_classes:
        blocks.extend(_generate_for_cls(cls=concrete_cls))

    blocks.append(golang_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
