"""Generate code to test the verification of enums."""

from typing import List

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line
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
    Generate code to test the verification of enums.
    """
    blocks: List[Stripped] = []

    for enumeration in symbol_table.enumerations:
        enum_name = java_naming.enum_name(enumeration.name)

        assert (
            len(enumeration.literals) > 0
        ), f"Unexpected enumeration without literals: {enumeration.name}"

        literal_name = java_naming.enum_literal_name(enumeration.literals[0].name)

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{enum_name}Valid() {{
{I}final List<Reporting.Error> errors = Verification.verify{enum_name}(
{II}{enum_name}.{literal_name}).collect(Collectors.toList());

{I}assertEquals(0, errors.size());
}} // void test{enum_name}Valid"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{enum_name}Invalid() {{
{I}final {enum_name} value = null;
{I}final List<Reporting.Error> errors =
{II}Verification.verify{enum_name}(value).collect(Collectors.toList());

{I}assertEquals(1, errors.size());
{I}assertEquals("Invalid {enum_name}: null", errors.get(0).getCause());
}} // void test{enum_name}Invalid"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestVerificationOfEnums.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.reporting.Reporting;
import {package}.types.enums.*;
import {package}.verification.Verification;
import java.util.List;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

public class TestVerificationOfEnums {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestVerificationOfEnums

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
