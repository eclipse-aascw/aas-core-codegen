"""Generate code to test the JSON de/serialization of concrete classes."""

import io
from typing import List

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
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


def _generate_for_class(cls: intermediate.ConcreteClass) -> List[Stripped]:
    """Generate the tests for the given class."""
    model_type_literal = golang_common.string_literal(naming.json_model_type(cls.name))

    deserialization_function = golang_naming.function_name(
        Identifier(f"{cls.name}_from_jsonable")
    )

    blocks = []  # type: List[Stripped]

    test_name = golang_naming.function_name(
        Identifier(f"Test_{cls.name}_round_trip_OK")
    )

    blocks.append(
        Stripped(
            f"""\
func {test_name}(t *testing.T) {{
{I}pths := aastesting.FindFilesBySuffixRecursively(
{II}filepath.Join(
{III}aastesting.TestDataDir,
{III}"Json",
{III}"Expected",
{III}{model_type_literal},
{II}),
{II}".json",
{I})
{I}sort.Strings(pths)

{I}for _, pth := range pths {{
{II}jsonable := aastesting.MustReadJsonable(
{III}pth,
{II})

{II}deserialized, deseriaErr := aasjsonization.{deserialization_function}(
{III}jsonable,
{II})
{II}ok := assertNoDeserializationError(t, deseriaErr, pth)
{II}if !ok {{
{III}return
{II}}}

{II}anotherJsonable, seriaErr := aasjsonization.ToJsonable(deserialized)
{II}ok = assertNoSerializationError(t, seriaErr, pth)
{II}if !ok {{
{III}return
{II}}}

{II}ok = assertSerializationEqualsDeserialization(
{III}t,
{III}jsonable,
{III}anotherJsonable,
{III}pth,
{II})
{II}if !ok {{
{III}return
{II}}}
{I}}}
}}"""
        )
    )

    test_name = golang_naming.function_name(
        Identifier(f"Test_{cls.name}_deserialization_fail")
    )

    blocks.append(
        Stripped(
            f"""\
func {test_name}(t *testing.T) {{
{I}pattern := filepath.Join(
{II}aastesting.TestDataDir,
{II}"Json",
{II}"Unexpected",
{II}"Unserializable",
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
{II}pths := aastesting.FindFilesBySuffixRecursively(
{III}causeDir,
{III}".json",
{II})
{II}sort.Strings(pths)

{II}for _, pth := range pths {{
{III}jsonable := aastesting.MustReadJsonable(
{IIII}pth,
{III})

{III}relPth, err := filepath.Rel(aastesting.TestDataDir, pth)
{III}if err != nil {{
{IIII}panic(
{IIIII}fmt.Sprintf(
{IIIIII}"Failed to compute the relative path of %s to %s: %s",
{IIIIII}aastesting.TestDataDir, pth, err.Error(),
{IIIII}),
{IIII})
{III}}}

{III}expectedPth := filepath.Join(
{IIII}aastesting.TestDataDir,
{IIII}"DeserializationError",
{IIII}filepath.Dir(relPth),
{IIII}filepath.Base(relPth)+".error",
{III})

{III}_, deseriaErr := aasjsonization.{deserialization_function}(
{IIII}jsonable,
{III})
{III}ok := assertDeserializationErrorEqualsExpectedOrRecord(
{IIII}t, deseriaErr, pth, expectedPth,
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


def _generate_serialization_failure_infrastructure() -> List[Stripped]:
    """Generate the helpers shared by the tests of the serialization failures."""
    return [
        Stripped(
            f"""\
// Determine the path to the first recorded example of `modelType`.
func mustFirstExpectedPath(t *testing.T, modelType string) string {{
{I}pths := aastesting.FindFilesBySuffixRecursively(
{II}filepath.Join(
{III}aastesting.TestDataDir,
{III}"Json",
{III}"Expected",
{III}modelType,
{II}),
{II}".json",
{I})
{I}sort.Strings(pths)

{I}if len(pths) == 0 {{
{II}t.Fatalf(
{III}"Expected at least one recorded example of %s, but got none",
{III}modelType,
{II})
{I}}}

{I}return pths[0]
}}"""
        ),
        Stripped(
            f"""\
// Assert that `that` can not be serialized to JSON, and that the failure
// is reported at `expectedPath`.
func assertSerializationFailsAt(
{I}t *testing.T,
{I}that aastypes.IClass,
{I}expectedPath string,
) {{
{I}_, err := aasjsonization.ToJsonable(that)

{I}if err == nil {{
{II}t.Fatalf(
{III}"Expected the serialization to fail at %s, but it succeeded",
{III}expectedPath,
{II})
{II}return
{I}}}

{I}seriaErr, ok := err.(*aasjsonization.SerializationError)
{I}if !ok {{
{II}t.Fatalf(
{III}"Expected a *SerializationError, but got %T: %v",
{III}err, err,
{II})
{II}return
{I}}}

{I}if seriaErr.PathString() != expectedPath {{
{II}t.Fatalf(
{III}"Expected the serialization to fail at %s, "+
{IIII}"but it failed at %s: %s",
{III}expectedPath, seriaErr.PathString(), seriaErr.Message,
{II})
{I}}}
}}"""
        ),
    ]


def _generate_serialization_failure_test(
    numeric_place: intermediate.NumericPlace,
) -> Stripped:
    """Generate the test that a number unrepresentable in JSON is refused."""
    if numeric_place.a_type is intermediate.PrimitiveType.FLOAT:
        value_type = "float64"
        zero_literal = "0"
        what = "non_finite"
        values_joined = ",\n".join(["math.Inf(1)", "math.Inf(-1)", "math.NaN()"])
    else:
        value_type = "int64"
        zero_literal = "0"
        what = "out_of_range"
        values_joined = ",\n".join(["9007199254740992", "-9007199254740992"])

    getter_name = golang_naming.getter_name(numeric_place.prop.name)
    setter_name = golang_naming.setter_name(numeric_place.prop.name)

    if numeric_place.index is None:
        mutation = Stripped(f"instance.{setter_name}(value)")
        expected_path = f"{getter_name}()"
    elif numeric_place.in_list:
        # NOTE (mristin):
        # The value goes to the position indicated by the numeric place so that
        # a serializer which always reports the index 0 does not pass.
        items_joined = ", ".join(
            "value" if i == numeric_place.index else zero_literal
            for i in range(numeric_place.index + 1)
        )

        mutation = Stripped(f"instance.{setter_name}([]{value_type}{{{items_joined}}})")
        expected_path = f"{getter_name}()[{numeric_place.index}]"
    else:
        # NOTE (mristin):
        # A tuple is a value in Go, so it has to be read out, changed and
        # written back.
        mutation = Stripped(
            f"""\
tuple := instance.{getter_name}()
tuple.Item{numeric_place.index + 1} = value
instance.{setter_name}(tuple)"""
        )
        expected_path = f"{getter_name}()[{numeric_place.index}]"

    model_type_literal = golang_common.string_literal(
        naming.json_model_type(numeric_place.cls.name)
    )

    deserialization_function = golang_naming.function_name(
        Identifier(f"{numeric_place.cls.name}_from_jsonable")
    )

    test_name = golang_naming.function_name(
        Identifier(
            f"Test_{numeric_place.cls.name}_serialization_fail_"
            f"on_{what}_{numeric_place.prop.name}"
        )
    )

    return Stripped(
        f"""\
func {test_name}(t *testing.T) {{
{I}pth := mustFirstExpectedPath(t, {model_type_literal})

{I}for _, value := range []{value_type}{{
{II}{indent_but_first_line(values_joined, II)},
{I}}} {{
{II}jsonable := aastesting.MustReadJsonable(pth)

{II}instance, deseriaErr := aasjsonization.{deserialization_function}(
{III}jsonable,
{II})
{II}if !assertNoDeserializationError(t, deseriaErr, pth) {{
{III}return
{II}}}

{II}{indent_but_first_line(mutation, II)}

{II}assertSerializationFailsAt(
{III}t,
{III}instance,
{III}{golang_common.string_literal(expected_path)},
{II})
{I}}}
}}"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to test the JSON de/serialization of concrete classes."""
    numeric_places = intermediate.numeric_places(symbol_table)

    # NOTE (mristin):
    # Only the tests of the serialization failures need the non-finite floats
    # and the types of the instances they corrupt.
    extra_imports = (
        f'\n{I}"math"\n{I}aastypes "{repo_url}/types"'
        if len(numeric_places) > 0
        else ""
    )

    blocks = [
        Stripped("package jsonization_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"
{I}"path/filepath"
{I}"sort"
{I}"testing"{extra_imports}
{I}aasjsonization "{repo_url}/jsonization"
{I}aastesting "{repo_url}/aastesting"
)"""
        ),
    ]  # type: List[Stripped]

    if len(numeric_places) > 0:
        blocks.extend(_generate_serialization_failure_infrastructure())

    for concrete_cls in symbol_table.concrete_classes:
        blocks.extend(_generate_for_class(cls=concrete_cls))

    for numeric_place in numeric_places:
        blocks.append(_generate_serialization_failure_test(numeric_place))

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
