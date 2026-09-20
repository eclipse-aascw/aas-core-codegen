"""Generate the test code for the jsonization of classes with descendants."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    Identifier,
)
from aas_core_codegen.golang import common as golang_common, naming as golang_naming
from aas_core_codegen.golang.common import INDENT as I, INDENT2 as II, INDENT3 as III


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
    """Generate the test code for the jsonization of classes with descendants."""
    blocks = [
        Stripped("package jsonization_test"),
        golang_common.WARNING,
        _IMPORT_PLACEHOLDER,
    ]  # type: List[Stripped]

    for cls in symbol_table.classes:
        # NOTE (mristin):
        # We can only de-serialize instances of concrete descendants which carry
        # a model type in their serializations.
        concrete_descendants_with_model_type = [
            concrete_descendant
            for concrete_descendant in cls.concrete_descendants
            if concrete_descendant.serialization.with_model_type
        ]

        if len(concrete_descendants_with_model_type) == 0:
            continue

        descendant_cls = concrete_descendants_with_model_type[0]

        must_load_minimal_name = golang_naming.function_name(
            Identifier(f"must_load_minimal_{descendant_cls.name}")
        )

        deserialization_function = golang_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        test_name = golang_naming.function_name(
            (Identifier(f"test_{cls.name}_round_trip_OK_over_descendant"))
        )

        model_type = naming.json_model_type(descendant_cls.name)

        blocks.append(
            Stripped(
                f"""\
func {test_name}(t *testing.T) {{
{I}instance := aastesting.{must_load_minimal_name}()

{I}jsonable, err := aasjsonization.ToJsonable(instance)
{I}if err != nil {{
{II}t.Fatalf(
{III}"Failed to serialize the minimal {model_type}: %v",
{III}err,
{II})
{II}return
{I}}}

{I}source := "<minimal {model_type}>"

{I}deserialized, deseriaErr := aasjsonization.{deserialization_function}(
{II}jsonable,
{I})
{I}ok := assertNoDeserializationError(t, deseriaErr, source)
{I}if !ok {{
{II}return
{I}}}

{I}anotherJsonable, seriaErr := aasjsonization.ToJsonable(deserialized)
{I}ok = assertNoSerializationError(t, seriaErr, source)
{I}if !ok {{
{II}return
{I}}}

{I}ok = assertSerializationEqualsDeserialization(
{II}t,
{II}jsonable,
{II}anotherJsonable,
{II}source,
{I})
{I}if !ok {{
{II}return
{I}}}
}}"""
            )
        )

        # NOTE (mristin):
        # We test here only abstract classes as the concrete classes are going
        # to be already tested in another test with concrete classes.
        if isinstance(cls, intermediate.AbstractClass):
            test_name = golang_naming.function_name(
                (Identifier(f"test_{cls.name}_deserialization_fail"))
            )

            blocks.append(
                Stripped(
                    f"""\
func {test_name}(t *testing.T) {{
{I}jsonable := any("this is not an object")

{I}_, err := aasjsonization.{deserialization_function}(
{II}jsonable,
{I})

{I}if err == nil {{
{II}t.Fatal("Expected an error, but got none.")
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
{II}"Expected a JSON object, but got string"

{I}if deseriaErr.Message != expectedMessage {{
{II}t.Fatalf(
{III}"Expected the deserialization error:\\n%s\\n, but got:\\n%s",
{III}expectedMessage, deseriaErr.Message,
{II})
{II}return
{I}}}
}}"""
                )
            )

    blocks.append(golang_common.WARNING)

    import_index = blocks.index(_IMPORT_PLACEHOLDER)

    import_lines = []  # type: List[str]
    for module, literal in (
        ("testing", f'{I}"testing"'),
        ("aasjsonization", f'{I}aasjsonization "{repo_url}/jsonization"'),
        ("aastesting", f'{I}aastesting "{repo_url}/aastesting"'),
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
