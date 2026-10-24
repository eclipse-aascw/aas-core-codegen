"""Generate code to test the ``OverXOrEmpty`` methods."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, Identifier
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test the ``OverXOrEmpty`` methods."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test `over*OrEmpty` methods.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as TestCommonJsonization from "./commonJsonization";"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_typescript = typescript_naming.class_name(concrete_cls.name)

        for prop in concrete_cls.properties:
            method_name_typescript = typescript_naming.method_name(
                Identifier(f"Over_{prop.name}_or_empty")
            )

            prop_name_typescript = typescript_naming.property_name(prop.name)

            if not isinstance(
                prop.type_annotation, intermediate.OptionalTypeAnnotation
            ):
                continue

            # NOTE (mristin):
            # We only count the items, so the test does not depend on the order
            # of the items in a set, which differs among the targets.
            size_property: str
            if isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
                size_property = "length"
            elif isinstance(prop.type_annotation.value, intermediate.SetTypeAnnotation):
                size_property = "size"
            else:
                continue

            load_maximal_name = typescript_naming.function_name(
                Identifier(f"load_maximal_{concrete_cls.name}")
            )

            # noinspection SpellCheckingInspection
            blocks.append(
                Stripped(
                    f"""\
test("{cls_name_typescript}.{method_name_typescript} on maximal", () => {{
{I}const instance = TestCommonJsonization.{load_maximal_name}();

{I}let count = 0;
{I}for (const _ of instance.{method_name_typescript}()) {{
{II}count++;
{I}}}

{I}expect(count).toStrictEqual(
{II}instance.{prop_name_typescript}?.{size_property} ?? 0,
{I});
}});"""
                )
            )

            load_minimal_name = typescript_naming.function_name(
                Identifier(f"load_minimal_{concrete_cls.name}")
            )

            blocks.append(
                Stripped(
                    f"""\
test("{cls_name_typescript}.{method_name_typescript} on minimal", () => {{
{I}const instance = TestCommonJsonization.{load_minimal_name}();

{I}let count = 0;
{I}for (const _ of instance.{method_name_typescript}()) {{
{II}count++;
{I}}}

{I}expect(count).toStrictEqual(
{II}instance.{prop_name_typescript}?.{size_property} ?? 0,
{I});
}});"""
                )
            )

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
