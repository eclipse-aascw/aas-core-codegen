"""Generate code to test the JSON de/serialization of concrete classes."""

import io
from typing import Final, List, Sequence, Tuple

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

    blocks: List[Stripped] = []

    test_name = golang_naming.function_name(
        Identifier(f"Test_{cls.name}_round_trip_OK")
    )

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
{II}ok := assertNoDeserializationError(t, deseriaErr, pth)
{II}if !ok {{
{III}return
{II}}}

{II}anotherJsonable, seriaErr := ourjsonization.ToJsonable(deserialized)
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
{II}ourtesting.TestDataDir,
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
{IIII}"DeserializationError",
{IIII}filepath.Dir(relPth),
{IIII}filepath.Base(relPth)+".error",
{III})

{III}_, deseriaErr := ourjsonization.{deserialization_function}(
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
    """Generate the helpers shared by the tests of the non-finite numbers."""
    return [
        Stripped(
            f"""\
// Assert that `that` can not be serialized to JSON, and that the failure
// is reported at `expectedPath`.
func assertSerializationFailsAt(
{I}t *testing.T,
{I}that ourtypes.IClass,
{I}expectedPath string,
) {{
{I}_, err := ourjsonization.ToJsonable(that)

{I}if err == nil {{
{II}t.Fatalf(
{III}"Expected the serialization to fail at %s, but it succeeded",
{III}expectedPath,
{II})
{II}return
{I}}}

{I}seriaErr, ok := err.(*ourjsonization.SerializationError)
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


def _generate_first_expected_path() -> Stripped:
    """Generate the helper locating the first recorded example of a class."""
    return Stripped(
        f"""\
// Determine the path to the first recorded example of `modelType`.
func mustFirstExpectedPath(t *testing.T, modelType string) string {{
{I}pths := ourtesting.FindFilesBySuffixRecursively(
{II}filepath.Join(
{III}ourtesting.TestDataDir,
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
    )


def _generate_safe_integer_infrastructure() -> List[Stripped]:
    """
    Generate the helpers shared by the tests of the safe integer range.

    The verification, the JSON serialization and the XML serialization have to
    agree on which integers they refuse, so that a verified instance is
    guaranteed to serialize.
    """
    return [
        Stripped(
            f"""\
// Assert that the verification, the JSON serialization and the XML
// serialization of `that` all report `expectedMessage`. The verification
// reports it at `expectedVerificationPath`, and the JSON serialization at
// `expectedSerializationPath`.
//
// The serialization names a property by its getter, *e.g.*, `Value()`, while
// the verification names it by the property, *e.g.*, `Value`.
func assertSafeIntegerRefused(
{I}t *testing.T,
{I}that ourtypes.IClass,
{I}expectedVerificationPath string,
{I}expectedSerializationPath string,
{I}expectedMessage string,
) {{
{I}var veriErrs []*ourverification.VerificationError
{I}ourverification.Verify(
{II}that,
{II}func(err *ourverification.VerificationError) (abort bool) {{
{III}veriErrs = append(veriErrs, err)
{III}return
{II}}},
{I})

{I}found := false
{I}for _, veriErr := range veriErrs {{
{II}if veriErr.PathString() == expectedVerificationPath &&
{III}veriErr.Message == expectedMessage {{
{III}found = true
{III}break
{II}}}
{I}}}
{I}if !found {{
{II}t.Fatalf(
{III}"Expected the verification to report at %s: %s, but got: %v",
{III}expectedVerificationPath, expectedMessage, veriErrs,
{II})
{II}return
{I}}}

{I}_, err := ourjsonization.ToJsonable(that)
{I}jsonErr, ok := err.(*ourjsonization.SerializationError)
{I}if !ok ||
{II}jsonErr.PathString() != expectedSerializationPath ||
{II}jsonErr.Message != expectedMessage {{
{II}t.Fatalf(
{III}"Expected the JSON serialization to fail at %s: %s, but got: %v",
{III}expectedSerializationPath, expectedMessage, err,
{II})
{II}return
{I}}}

{I}var builder strings.Builder
{I}err = ourxmlization.Marshal(xml.NewEncoder(&builder), that, true)
{I}xmlErr, ok := err.(*ourxmlization.SerializationError)
{I}if !ok || xmlErr.Message != expectedMessage {{
{II}t.Fatalf(
{III}"Expected the XML serialization to fail with: %s, but got: %v",
{III}expectedMessage, err,
{II})
{II}return
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// Assert that neither the verification, nor the JSON serialization nor
// the XML serialization of `that` refuses an integer as unsafe.
//
// The verification might still report the violations of the invariants, as
// the tests change the instance at will.
func assertSafeIntegerAccepted(
{I}t *testing.T,
{I}that ourtypes.IClass,
) {{
{I}ourverification.Verify(
{II}that,
{II}func(err *ourverification.VerificationError) (abort bool) {{
{III}if strings.Contains(err.Message, "safe integer range") {{
{IIII}t.Fatalf("Expected no safe-integer error, but got: %v", err)
{III}}}
{III}return
{II}}},
{I})

{I}_, err := ourjsonization.ToJsonable(that)
{I}if err != nil {{
{II}t.Fatalf("Expected no JSON serialization error, but got: %v", err)
{II}return
{I}}}

{I}var builder strings.Builder
{I}err = ourxmlization.Marshal(xml.NewEncoder(&builder), that, true)
{I}if err != nil {{
{II}t.Fatalf("Expected no XML serialization error, but got: %v", err)
{II}return
{I}}}
}}"""
        ),
    ]


def _generate_test_on_first_expected(
    test_name: Identifier,
    cls: intermediate.ConcreteClass,
    value_type: str,
    values: Sequence[str],
    mutation: str,
    assertion: str,
) -> Stripped:
    """
    Generate the test which changes the first recorded example of ``cls``.

    For each of the ``values``, the ``mutation`` sets it to the de-serialized
    ``instance``, and the ``assertion`` checks the outcome.
    """
    model_type_literal = golang_common.string_literal(naming.json_model_type(cls.name))

    deserialization_function = golang_naming.function_name(
        Identifier(f"{cls.name}_from_jsonable")
    )

    values_joined = ",\n".join(values)

    return Stripped(
        f"""\
func {test_name}(t *testing.T) {{
{I}pth := mustFirstExpectedPath(t, {model_type_literal})

{I}for _, value := range []{value_type}{{
{II}{indent_but_first_line(values_joined, II)},
{I}}} {{
{II}jsonable := ourtesting.MustReadJsonable(pth)

{II}instance, deseriaErr := ourjsonization.{deserialization_function}(
{III}jsonable,
{II})
{II}if !assertNoDeserializationError(t, deseriaErr, pth) {{
{III}return
{II}}}

{II}{indent_but_first_line(mutation, II)}

{II}{indent_but_first_line(assertion, II)}
{I}}}
}}"""
    )


#: Integers just outside the safe integer range
_UNSAFE_INTEGERS: Final[Sequence[str]] = ["9007199254740992", "-9007199254740992"]

#: Integers at the bounds of the safe integer range
_SAFE_INTEGERS: Final[Sequence[str]] = ["9007199254740991", "-9007199254740991"]


def _generate_numeric_place_tests(
    numeric_place: intermediate.NumericPlace,
) -> List[Stripped]:
    """
    Generate the tests that a number unrepresentable in JSON is refused.

    A non-finite float is refused by the JSON serialization. An integer outside
    the safe integer range is refused by the verification, the JSON and
    the XML serialization alike, while the integers at the bounds are accepted.
    """
    value_type = golang_common.PRIMITIVE_TYPE_MAP[numeric_place.a_type]

    getter_name = golang_naming.getter_name(numeric_place.prop.name)
    setter_name = golang_naming.setter_name(numeric_place.prop.name)

    if numeric_place.index is None:
        mutation = f"instance.{setter_name}(value)"
        subscript = ""
    elif numeric_place.in_list:
        # NOTE (mristin):
        # The value goes to the position indicated by the numeric place so that
        # a serializer which always reports the index 0 does not pass.
        items_joined = ", ".join(
            "value" if i == numeric_place.index else "0"
            for i in range(numeric_place.index + 1)
        )

        mutation = f"instance.{setter_name}([]{value_type}{{{items_joined}}})"
        subscript = f"[{numeric_place.index}]"
    else:
        # NOTE (mristin):
        # A tuple is a value in Go, so it has to be read out, changed and
        # written back.
        mutation = f"""\
tuple := instance.{getter_name}()
tuple.Item{numeric_place.index + 1} = value
instance.{setter_name}(tuple)"""
        subscript = f"[{numeric_place.index}]"

    # NOTE (mristin):
    # The serialization names a property by its getter, while the verification
    # names it by the property.
    serialization_path_literal = golang_common.string_literal(
        f"{getter_name}(){subscript}"
    )
    verification_path_literal = golang_common.string_literal(
        f"{golang_naming.property_name(numeric_place.prop.name)}{subscript}"
    )

    cls = numeric_place.cls
    prop_name = numeric_place.prop.name

    if numeric_place.a_type is intermediate.PrimitiveType.FLOAT:
        return [
            _generate_test_on_first_expected(
                test_name=golang_naming.function_name(
                    Identifier(
                        f"Test_{cls.name}_serialization_fail_on_non_finite_{prop_name}"
                    )
                ),
                cls=cls,
                value_type=value_type,
                values=["math.Inf(1)", "math.Inf(-1)", "math.NaN()"],
                mutation=mutation,
                assertion=f"""\
assertSerializationFailsAt(
{I}t,
{I}instance,
{I}{serialization_path_literal},
)""",
            )
        ]

    return [
        _generate_test_on_first_expected(
            test_name=golang_naming.function_name(
                Identifier(f"Test_{cls.name}_refuses_unsafe_integer_in_{prop_name}")
            ),
            cls=cls,
            value_type=value_type,
            values=_UNSAFE_INTEGERS,
            mutation=mutation,
            assertion=f"""\
assertSafeIntegerRefused(
{I}t,
{I}instance,
{I}{verification_path_literal},
{I}{serialization_path_literal},
{I}fmt.Sprintf(
{II}"Expected an integer, but got %d, "+
{II}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]",
{II}value,
{I}),
)""",
        ),
        _generate_test_on_first_expected(
            test_name=golang_naming.function_name(
                Identifier(f"Test_{cls.name}_accepts_safe_integer_in_{prop_name}")
            ),
            cls=cls,
            value_type=value_type,
            values=_SAFE_INTEGERS,
            mutation=mutation,
            assertion="assertSafeIntegerAccepted(t, instance)",
        ),
    ]


def _json_value_properties(
    symbol_table: intermediate.SymbolTable,
) -> List[Tuple[intermediate.ConcreteClass, intermediate.Property]]:
    """List the required properties which are bare JSON-able values."""
    return [
        (cls, prop)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
        if isinstance(prop.type_annotation, intermediate.JsonValueTypeAnnotation)
    ]


def _generate_json_value_tests(
    cls: intermediate.ConcreteClass, prop: intermediate.Property
) -> List[Stripped]:
    """
    Generate the tests of an integer nested in a JSON-able value.

    The integer can only be put there programmatically, as JSON itself gives
    a float64. Outside the safe integer range, it is refused by
    the verification, the JSON and the XML serialization alike, while
    the integers at the bounds are accepted.
    """
    setter_name = golang_naming.setter_name(prop.name)

    # NOTE (mristin):
    # We nest the integer in an array so that the path is checked at depth.
    mutation = f"instance.{setter_name}(ourtypes.JsonArray{{value}})"

    serialization_path_literal = golang_common.string_literal(
        f"{golang_naming.getter_name(prop.name)}()[0]"
    )
    verification_path_literal = golang_common.string_literal(
        f"{golang_naming.property_name(prop.name)}[0]"
    )

    return [
        _generate_test_on_first_expected(
            test_name=golang_naming.function_name(
                Identifier(f"Test_{cls.name}_refuses_unsafe_integer_in_{prop.name}")
            ),
            cls=cls,
            value_type="int64",
            values=_UNSAFE_INTEGERS,
            mutation=mutation,
            assertion=f"""\
assertSafeIntegerRefused(
{I}t,
{I}instance,
{I}{verification_path_literal},
{I}{serialization_path_literal},
{I}fmt.Sprintf(
{II}"Expected a JSON-able value, but got the integer %d, "+
{II}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]",
{II}value,
{I}),
)""",
        ),
        _generate_test_on_first_expected(
            test_name=golang_naming.function_name(
                Identifier(f"Test_{cls.name}_accepts_safe_integer_in_{prop.name}")
            ),
            cls=cls,
            value_type="int64",
            values=_SAFE_INTEGERS,
            mutation=mutation,
            assertion="assertSafeIntegerAccepted(t, instance)",
        ),
    ]


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
    """Generate code to test the JSON de/serialization of concrete classes."""
    numeric_places = intermediate.numeric_places(symbol_table)

    json_value_properties = _json_value_properties(symbol_table)

    blocks: List[Stripped] = [
        Stripped("package jsonization_test"),
        golang_common.WARNING,
        _IMPORT_PLACEHOLDER,
    ]

    if len(numeric_places) > 0 or len(json_value_properties) > 0:
        blocks.append(_generate_first_expected_path())

    if any(
        numeric_place.a_type is intermediate.PrimitiveType.FLOAT
        for numeric_place in numeric_places
    ):
        blocks.extend(_generate_serialization_failure_infrastructure())

    if len(json_value_properties) > 0 or any(
        numeric_place.a_type is intermediate.PrimitiveType.INT
        for numeric_place in numeric_places
    ):
        blocks.extend(_generate_safe_integer_infrastructure())

    for concrete_cls in symbol_table.concrete_classes:
        blocks.extend(_generate_for_class(cls=concrete_cls))

    for numeric_place in numeric_places:
        blocks.extend(_generate_numeric_place_tests(numeric_place))

    for cls, prop in json_value_properties:
        blocks.extend(_generate_json_value_tests(cls, prop))

    blocks.append(golang_common.WARNING)

    import_index = blocks.index(_IMPORT_PLACEHOLDER)

    import_lines: List[str] = []
    for module, literal in (
        ("xml", f'{I}"encoding/xml"'),
        ("fmt", f'{I}"fmt"'),
        ("filepath", f'{I}"path/filepath"'),
        ("math", f'{I}"math"'),
        ("sort", f'{I}"sort"'),
        ("strings", f'{I}"strings"'),
        ("testing", f'{I}"testing"'),
        ("ourjsonization", f'{I}ourjsonization "{repo_url}/jsonization"'),
        ("ourtesting", f'{I}ourtesting "{repo_url}/ourtesting"'),
        ("ourtypes", f'{I}ourtypes "{repo_url}/types"'),
        ("ourverification", f'{I}ourverification "{repo_url}/verification"'),
        ("ourxmlization", f'{I}ourxmlization "{repo_url}/xmlization"'),
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
