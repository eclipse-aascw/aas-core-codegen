"""Generate code to test the JSON de/serialization of enumerations."""

import io
from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate
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
)


# fmt: off
@require(
    lambda enumeration: len(enumeration.literals) > 0,
    "Enumeration must have at least one literal as enumerations without literals "
    "can not be tested"
)
# fmt: on
def _generate_round_trip_test_for_enum(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the test that the de-serialization equals the serialization."""
    test_name = golang_naming.function_name(
        Identifier(f"test_{enumeration.name}_round_trip_OK")
    )

    literals_joined = "\n".join(
        f"{golang_common.string_literal(literal.value)},"
        for literal in enumeration.literals
    )

    deserialization_function = golang_naming.function_name(
        Identifier(f"{enumeration.name}_from_jsonable")
    )

    serialization_function = golang_naming.function_name(
        Identifier(f"{enumeration.name}_to_jsonable")
    )

    return Stripped(
        f"""\
func {test_name}(t *testing.T) {{
{I}literals := []string{{
{II}{indent_but_first_line(literals_joined, II)}
{I}}}

{I}for _, literal := range literals {{
{II}source := fmt.Sprintf("<string literal %s>", literal)
{II}jsonable := any(literal)

{II}deserialized, deseriaErr := aasjsonization.{deserialization_function}(
{III}jsonable,
{II})
{II}ok := assertNoDeserializationError(t, deseriaErr, source)
{II}if !ok {{
{III}return
{II}}}

{II}anotherJsonable, seriaErr :=
{III}aasjsonization.{serialization_function}(deserialized)
{II}ok = assertNoSerializationError(t, seriaErr, source)
{II}if !ok {{
{III}return
{II}}}

{II}ok = assertSerializationEqualsDeserialization(
{III}t,
{III}jsonable,
{III}anotherJsonable,
{III}source,
{II})
{II}if !ok {{
{III}return
{II}}}
{I}}}
}}"""
    )


def _generate_deserialization_fail_for_enum(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the test for de-serialization of an invalid value."""
    test_name = golang_naming.function_name(
        Identifier(f"test_{enumeration.name}_deserialization_fail")
    )

    deserialization_function = golang_naming.function_name(
        Identifier(f"{enumeration.name}_from_jsonable")
    )

    enum_name = golang_naming.enum_name(enumeration.name)

    invalid_literal = "THIS-CANNOT-POSSIBLY-BE-VALID"
    trial = 0
    while invalid_literal in enumeration.literal_value_set:
        trial += 1
        infix = "-EVER" * trial
        invalid_literal = f"THIS-CANNOT{infix}-POSSIBLY-BE-VALID"

    return Stripped(
        f"""\
func {test_name}(t *testing.T) {{
{I}jsonable := any({golang_common.string_literal(invalid_literal)})

{I}_, err := aasjsonization.{deserialization_function}(
{II}jsonable,
{I})

{I}if err == nil {{
{II}t.Fatal("Expected a deserialization error, but got none.")
{II}return
{I}}}

{I}deseriaErr, ok := err.(*aasjsonization.DeserializationError)
{I}if !ok {{
{II}t.Fatalf("Expected a de-serialization error, but got: %v", err)
{II}return
{I}}}

{I}pathString := deseriaErr.PathString()
{I}if len(pathString) != 0 {{
{II}t.Fatalf(
{III}"Expected an empty path in error, but got: %s",
{III}pathString,
{II})
{II}return
{I}}}

{I}expectedMessage :=
{II}"Expected a string representation of {enum_name}, " +
{II}"but got {invalid_literal}"

{I}if deseriaErr.Message != expectedMessage {{
{II}t.Fatalf(
{III}"Expected the deserialization error:\\n%s\\n, but got:\\n%s",
{III}expectedMessage, deseriaErr.Message,
{II})
{II}return
{I}}}
}}"""
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
    """Generate code to test the JSON de/serialization of enumerations."""
    blocks = [
        Stripped("package jsonization_test"),
        golang_common.WARNING,
        _IMPORT_PLACEHOLDER,
    ]  # type: List[Stripped]

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_round_trip_test_for_enum(enumeration=enumeration))
        blocks.append(_generate_deserialization_fail_for_enum(enumeration=enumeration))

    blocks.append(golang_common.WARNING)

    import_index = blocks.index(_IMPORT_PLACEHOLDER)

    import_lines = []  # type: List[str]
    for module, literal in (
        ("fmt", f'{I}"fmt"'),
        ("testing", f'{I}"testing"'),
        ("aasjsonization", f'{I}aasjsonization "{repo_url}/jsonization"'),
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
