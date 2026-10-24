"""Generate code for common JSON de/serialization shared across the tests."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
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
    """Generate code for common JSON de/serialization shared across the tests."""
    blocks: List[Stripped] = [
        Stripped(
            """\
package jsonization_test"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"encoding/json"
{I}"fmt"
{I}"os"
{I}"path/filepath"
{I}"strings"
{I}"testing"
{I}ourjsonization "{repo_url}/jsonization"
{I}ourtesting "{repo_url}/ourtesting"
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
{III}"Expected no de-serialization error from %s, "+
{IIII}"but got: %v",
{III}source, err,
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
{IIII}"the instance obtained from %s, "+
{IIII}"but got: %v",
{III}source, err,
{II})
{II}return
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
// Assert that the serialization `other`, as JSON-able, equals the original
// JSON-able `that` read from `source`.
func assertSerializationEqualsDeserialization(
{I}t *testing.T,
{I}that interface{{}},
{I}other interface{{}},
{I}source string,
) (ok bool) {{
{I}ok = true

{I}thatBytes, err := json.Marshal(that)
{I}if err != nil {{
{II}panic(fmt.Sprintf("Failed to marshal that jsonable %v: %s", that, err.Error()))
{I}}}
{I}thatText := string(thatBytes)

{I}otherBytes, err := json.Marshal(other)
{I}if err != nil {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Failed to marshal other jsonable %v: %s", other, err.Error(),
{III}),
{II})
{I}}}
{I}otherText := string(otherBytes)

{I}if thatText != otherText {{
{II}ok = false
{II}t.Fatalf(
{III}"The serialization of the de-serialized instance from %s does not equal "+
{IIII}"the original JSON-able:\\nOriginal:\\n%s\\nSerialized:\\n%s",
{III}source, thatText, otherText,
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
func assertDeserializationErrorEqualsExpectedOrRecord(
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

{I}var deseriaErr *ourjsonization.DeserializationError
{I}deseriaErr, ok = err.(*ourjsonization.DeserializationError)
{I}if !ok {{
{II}t.Fatalf("Expected a de-serialization error, but got: %v from %s", err, source)
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

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
