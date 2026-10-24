"""Generate the functions used across descent tests."""

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
    """Generate the functions used across descent tests."""
    blocks: List[Stripped] = [
        Stripped(
            """\
package types_descend_test"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"
{I}"os"
{I}"path/filepath"
{I}"strings"
{I}ourtesting "{repo_url}/ourtesting"
{I}ourtypes "{repo_url}/types"
)"""
        ),
        Stripped(
            f"""\
// Trace the `instance` and compare the trace against the golden one from
// the test data, or re-record the trace if [ourtesting.RecordMode] is set.
//
// If `onlyOnce`, trace the `instance` with [ourtypes.DescendOnce]. Otherwise,
// trace with [ourtypes.Descend].
//
// If we are comparing, and not recording, return the error message if
// the expected and the obtained trace differ.
func compareOrRerecordTrace(
{I}instance ourtypes.IClass,
{I}expectedPath string,
{I}onlyOnce bool,
) (message *string) {{
{I}lines := []string{{ourtesting.TraceMark(instance)}}

{I}if onlyOnce {{
{II}instance.DescendOnce(func(descendant ourtypes.IClass) (abort bool) {{
{III}lines = append(lines, ourtesting.TraceMark(descendant))
{III}return
{II}}})
{I}}} else {{
{II}instance.Descend(func(descendant ourtypes.IClass) (abort bool) {{
{III}lines = append(lines, ourtesting.TraceMark(descendant))
{III}return
{II}}})
{I}}}

{I}got := strings.Join(lines, "\\n")

{I}// Add a new line for POSIX systems.
{I}got += "\\n"

{I}if ourtesting.RecordMode {{
{II}parent := filepath.Dir(expectedPath)
{II}err := os.MkdirAll(parent, os.ModePerm)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to create the directory %s: %s", parent, err.Error(),
{IIII}),
{III})
{II}}}

{II}err = os.WriteFile(expectedPath, []byte(got), 0644)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to write to the file %s: %s", expectedPath, err.Error(),
{IIII}),
{III})
{II}}}
{I}}} else {{
{II}bb, err := os.ReadFile(expectedPath)
{II}if err != nil {{
{III}panic(
{IIII}fmt.Sprintf(
{IIIII}"Failed to read from file %s: %s", expectedPath, err.Error(),
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
{IIII}"What we got differs from the expected in %s. "+
{IIIII}"We got:\\n%s\\nWe expected:\\n%s",
{IIII}expectedPath, got, expected,
{III})
{III}message = &text
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
