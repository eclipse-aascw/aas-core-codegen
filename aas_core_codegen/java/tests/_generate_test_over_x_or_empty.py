"""Generate code to test the ``OverXOrEmpty`` methods."""

from typing import List

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line, Identifier
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
)


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the ``OverXOrEmpty`` methods.
    """
    blocks: List[Stripped] = []

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_java = java_naming.class_name(concrete_cls.name)

        for prop in concrete_cls.properties:
            method_name_java = java_naming.method_name(
                Identifier(f"over_{prop.name}_or_empty")
            )
            method_name_capitalized_java = (
                method_name_java[0].upper() + method_name_java[1:]
            )
            getter_name_java = java_naming.getter_name(prop.name)

            if isinstance(
                prop.type_annotation, intermediate.OptionalTypeAnnotation
            ) and isinstance(
                prop.type_annotation.value,
                (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
            ):
                blocks.append(
                    Stripped(
                        f"""\
@Test
public void test{cls_name_java}{method_name_capitalized_java}() throws IOException {{
{I}for ({cls_name_java} instance : new {cls_name_java}[]
{I}{{
{II}CommonJsonization.loadMinimal{cls_name_java}(),
{II}CommonJsonization.loadMaximal{cls_name_java}()
{I}}}) {{
{II}int length = instance.{getter_name_java}().map(elem -> elem.size()).orElse(0);
{II}AtomicInteger count = new AtomicInteger();
{II}instance.{method_name_java}().forEach(i -> count.getAndIncrement());
{II}assertEquals(length , count.get());
{I}}}
}} // public void test{cls_name_java}{method_name_java}"""
                    )
                )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestOverXOrEmpty.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.types.enums.*;
import {package}.types.impl.*;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

public class TestOverXOrEmpty {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestOverXOrEmpty

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
