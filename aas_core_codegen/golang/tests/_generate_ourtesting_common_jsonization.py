"""Generate code to load minimal and maximal examples."""

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
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to load minimal and maximal examples."""
    blocks: List[Stripped] = [
        Stripped("package ourtesting"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"
{I}"path"
{I}ourjsonization "{repo_url}/jsonization"
{I}ourtypes "{repo_url}/types"
)"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        interface_name = golang_naming.interface_name(concrete_cls.name)

        cls_name_json = naming.json_model_type(concrete_cls.name)

        deserialization_function = golang_naming.function_name(
            Identifier(f"{concrete_cls.name}_from_jsonable")
        )

        deserialization_snippet = Stripped(
            f"""\
instance, err := ourjsonization.{deserialization_function}(
{I}jsonable,
)
if err != nil {{
{I}panic(
{II}fmt.Sprintf(
{III}"Failed to de-serialize an instance of {interface_name} " +
{III}"from %s: %s",
{III}pth, err.Error(),
{II}),
{I})
}}
var ok bool
result, ok = instance.(ourtypes.{interface_name})
if !ok {{
{I}panic(
{II}fmt.Sprintf(
{III}"Expected to find an instance of {interface_name} at %s, " +
{III}"but got an instance of %T: %v",
{III}pth, instance, instance,
{II}),
{I})
}}"""
        )

        must_load_maximal_name = golang_naming.function_name(
            Identifier(f"must_load_maximal_{concrete_cls.name}")
        )

        must_load_minimal_name = golang_naming.function_name(
            Identifier(f"must_load_minimal_{concrete_cls.name}")
        )

        blocks.append(
            Stripped(
                f"""\
// Load a maximal example of [ourtypes.{interface_name}] from
// the test data directory.
//
// If there is any error, panic.
func {must_load_maximal_name}(
) (result ourtypes.{interface_name}) {{
{I}pth := path.Join(
{II}TestDataDir,
{II}"Json",
{II}"Expected",
{II}{golang_common.string_literal(cls_name_json)},
{II}"maximal.json",
{I})

{I}jsonable := MustReadJsonable(pth)

{I}{indent_but_first_line(deserialization_snippet, I)}
{I}return
}}"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
// Load a minimal example of [ourtypes.{interface_name}] from
// the test data directory.
//
// If there is any error, panic.
func {must_load_minimal_name}(
) (result ourtypes.{interface_name}) {{
{I}pth := path.Join(
{II}TestDataDir,
{II}"Json",
{II}"Expected",
{II}{golang_common.string_literal(cls_name_json)},
{II}"minimal.json",
{I})

{I}jsonable := MustReadJsonable(pth)

{I}{indent_but_first_line(deserialization_snippet, I)}
{I}return
}}"""
            )
        )

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
