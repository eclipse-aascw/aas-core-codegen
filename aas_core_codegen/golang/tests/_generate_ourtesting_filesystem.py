"""Generate the functions related to filesystem used across the tests."""

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
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate() -> str:
    """Generate the functions related to filesystem used across the tests."""
    blocks: List[Stripped] = [
        Stripped(
            """\
package ourtesting"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"encoding/json"
{I}"fmt"
{I}"io/fs"
{I}"os"
{I}"path/filepath"
)"""
        ),
        Stripped(
            f"""\
// Read the content of `pth` and parse it as a JSON.
//
// If any errors, panic.
func MustReadJsonable(pth string) (jsonable interface{{}}) {{
{I}bb, err := os.ReadFile(pth)
{I}if err != nil {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Failed to read the content of: %s",
{IIII}pth,
{III}),
{II})
{I}}}

{I}err = json.Unmarshal(bb, &jsonable)
{I}if err != nil {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Failed to parse the content of %s as JSON: %s",
{IIII}pth, err.Error(),
{III}),
{II})
{I}}}
{I}return
}}"""
        ),
        Stripped(
            f"""\
func FindFilesBySuffixRecursively(root, suffix string) []string {{
{I}var a []string

{I}_, statErr := os.Stat(root)
{I}if statErr != nil {{
{II}if os.IsNotExist(statErr) {{
{III}return a
{II}}}

{II}panic(fmt.Sprintf("Failed to stat %s: %s", root, statErr.Error()))
{I}}}

{I}err := filepath.WalkDir(root, func(s string, d fs.DirEntry, e error) error {{
{II}if e != nil {{
{III}return e
{II}}}
{II}if filepath.Ext(d.Name()) == suffix {{
{III}a = append(a, s)
{II}}}
{II}return nil
{I}}})

{I}if err != nil {{
{II}panic(fmt.Sprintf("Failed to walk %s: %s", root, err.Error()))
{I}}}
{I}return a
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
