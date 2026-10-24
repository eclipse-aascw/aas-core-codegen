"""Generate code to test ``Is*`` functions."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.golang import common as golang_common, naming as golang_naming
from aas_core_codegen.golang.common import INDENT as I, INDENT2 as II


def _generate_for_cls(
    cls: intermediate.ConcreteClass, symbol_table: intermediate.SymbolTable
) -> Stripped:
    """Generate the test function."""
    must_load_minimal_name = golang_naming.function_name(
        Identifier(f"must_load_minimal_{cls.name}")
    )

    interface_name = golang_naming.interface_name(cls.name)

    block: List[Stripped] = [
        Stripped(
            f"""\
instance := ourtesting.{must_load_minimal_name}()"""
        )
    ]

    for concrete_cls in symbol_table.concrete_classes:
        is_function_name = golang_naming.function_name(
            Identifier(f"is_{concrete_cls.name}")
        )

        if cls.is_subclass_of(concrete_cls):
            block.append(
                Stripped(
                    f"""\
if !ourtypes.{is_function_name}(instance) {{
{I}t.Errorf(
{II}"Expected {is_function_name} to be true on an instance " +
{II}"of {interface_name} with runtime type %T and with model type %v",
{II}instance, instance.ModelType(),
{I})
}}"""
                )
            )
        else:
            block.append(
                Stripped(
                    f"""\
if ourtypes.{is_function_name}(instance) {{
{I}t.Errorf(
{II}"Expected {is_function_name} to be false on an instance " +
{II}"of {interface_name} with runtime type %T and with model type %v",
{II}instance, instance.ModelType(),
{I})
}}"""
                )
            )

    body = "\n\n".join(block)

    test_name = golang_naming.function_name(
        Identifier(f"test_is_Xxx_on_an_instance_of_{cls.name}")
    )

    return Stripped(
        f"""\
func {test_name}(t *testing.T) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to test ``Is*`` functions."""
    blocks: List[Stripped] = [
        Stripped("package types_is_xxx_test"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"testing"
{I}ourtesting "{repo_url}/ourtesting"
{I}ourtypes "{repo_url}/types"
)"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_for_cls(cls=concrete_cls, symbol_table=symbol_table))

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
