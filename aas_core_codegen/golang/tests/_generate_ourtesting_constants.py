"""Generate the constants shared across the unit tests."""

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
def generate(repo_url: Stripped) -> str:
    """Generate the constants shared across the unit tests."""
    environment_variable = golang_common.repo_url_to_environment_variable(repo_url)

    blocks: List[Stripped] = [
        Stripped(
            """\
package ourtesting"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"
{I}"os"
{I}"strings"
)"""
        ),
        Stripped(
            f"""\
const RecordModeEnvironmentVariableName string = (
{I}"{environment_variable}_TEST_RECORD_MODE")"""
        ),
        Stripped(
            '''\
// NOTE (mristin):
// It is tedious to record manually all the expected error messages. Therefore we
// include this variable to steer the automatic recording. We intentionally
// intertwine the recording code with the test code to keep them close to each other
// so that they are easier to maintain.
var rM = os.Getenv(RecordModeEnvironmentVariableName)
var RecordMode = rM == "1" || strings.ToLower(rM) == "true" || strings.ToLower(rM) == "on"'''
        ),
        Stripped(
            f"""\
const TestDataDirEnvironmentVariableName string = (
{I}"{environment_variable}_TEST_DATA_DIR")"""
        ),
        Stripped(
            f"""\
func getTestDataDir() string {{
{I}variable := TestDataDirEnvironmentVariableName
{I}val, ok := os.LookupEnv(variable)
{I}if !ok {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Expected the environment variable to be set, but it was not: %s",
{IIII}variable,
{III}),
{II})
{I}}}
{I}return val
}}"""
        ),
        Stripped(
            """\
var TestDataDir = getTestDataDir()"""
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
