"""Generate code to test the JSON de/serialization of the JSON-able values."""

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
    """
    Generate code to test the JSON de/serialization of the JSON-able values.

    The integers are put together programmatically, as JSON itself only gives
    a float64. They are accepted only within the safe integer range
    [-2^53 + 1, 2^53 - 1].
    """
    blocks = [
        Stripped("package jsonization_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"
{I}"testing"
{I}ourjsonization "{repo_url}/jsonization"
)"""
        ),
        Stripped(
            f"""\
// Format the error of an integer outside the safe integer range.
func unsafeIntegerMessage(value int64) string {{
{I}return fmt.Sprintf(
{II}"Expected a JSON-able value, but got the integer %d, "+
{II}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]",
{II}value,
{I})
}}"""
        ),
        Stripped(
            f"""\
func TestJsonValueFromJsonableAcceptsSafeIntegers(t *testing.T) {{
{I}for _, value := range []int64{{
{II}9007199254740991,
{II}-9007199254740991,
{I}}} {{
{II}result, err := ourjsonization.JsonValueFromJsonable(value)
{II}if err != nil {{
{III}t.Fatalf(
{IIII}"Expected no error when parsing %d, but got: %s",
{IIII}value, err.Error(),
{III})
{III}return
{II}}}

{II}if result != float64(value) {{
{III}t.Fatalf(
{IIII}"Expected %d to be parsed as a float64, but got %T: %v",
{IIII}value, result, result,
{III})
{III}return
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestJsonValueFromJsonableRefusesUnsafeIntegers(t *testing.T) {{
{I}for _, value := range []int64{{
{II}9007199254740992,
{II}-9007199254740992,
{I}}} {{
{II}_, err := ourjsonization.JsonValueFromJsonable(value)
{II}if err == nil {{
{III}t.Fatalf("Expected an error when parsing %d, but got none", value)
{III}return
{II}}}

{II}deseriaErr, ok := err.(*ourjsonization.DeserializationError)
{II}if !ok {{
{III}t.Fatalf(
{IIII}"Expected a *DeserializationError, but got %T: %v",
{IIII}err, err,
{III})
{III}return
{II}}}

{II}expected := unsafeIntegerMessage(value)
{II}if deseriaErr.Message != expected {{
{III}t.Fatalf(
{IIII}"Expected the error %q, but got %q",
{IIII}expected, deseriaErr.Message,
{III})
{III}return
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestJsonValueToJsonableAcceptsSafeIntegers(t *testing.T) {{
{I}for _, value := range []int64{{
{II}9007199254740991,
{II}-9007199254740991,
{I}}} {{
{II}result, err := ourjsonization.JsonValueToJsonable(value)
{II}if err != nil {{
{III}t.Fatalf(
{IIII}"Expected no error when serializing %d, but got: %s",
{IIII}value, err.Error(),
{III})
{III}return
{II}}}

{II}if result != float64(value) {{
{III}t.Fatalf(
{IIII}"Expected %d to be serialized as a float64, but got %T: %v",
{IIII}value, result, result,
{III})
{III}return
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func TestJsonValueToJsonableRefusesUnsafeIntegers(t *testing.T) {{
{I}for _, value := range []int64{{
{II}9007199254740992,
{II}-9007199254740992,
{I}}} {{
{II}_, err := ourjsonization.JsonValueToJsonable(
{III}[]interface{{}}{{
{IIII}map[string]interface{{}}{{
{IIIII}"key": value,
{IIII}}},
{III}}},
{II})
{II}if err == nil {{
{III}t.Fatalf("Expected an error when serializing %d, but got none", value)
{III}return
{II}}}

{II}seriaErr, ok := err.(*ourjsonization.SerializationError)
{II}if !ok {{
{III}t.Fatalf(
{IIII}"Expected a *SerializationError, but got %T: %v",
{IIII}err, err,
{III})
{III}return
{II}}}

{II}expected := unsafeIntegerMessage(value)
{II}if seriaErr.Message != expected {{
{III}t.Fatalf(
{IIII}"Expected the error %q, but got %q",
{IIII}expected, seriaErr.Message,
{III})
{III}return
{II}}}
{I}}}
}}"""
        ),
        golang_common.WARNING,
    ]

    return "\n\n".join(blocks) + "\n"


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
