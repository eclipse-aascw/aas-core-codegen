"""Generate code to test the verification of enums."""

from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    namespace: csharp_common.NamespaceIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> str:
    """
    Generate code to test the verification of enums.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = []

    for enumeration in symbol_table.enumerations:
        enum_name = csharp_naming.enum_name(enumeration.name)

        assert (
            len(enumeration.literals) > 0
        ), f"Unexpected enumeration without literals: {enumeration.name}"

        literal_name = csharp_naming.enum_literal_name(enumeration.literals[0].name)

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{enum_name}_valid()
{{
{I}var errors = Our.Verification.Verify{enum_name}(
{II}Our.{enum_name}.{literal_name}).ToList();

{I}Assert.IsEmpty(errors);
}}  // void Test_{enum_name}_valid"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
[Test]
public void Test_{enum_name}_invalid()
{{
{I}int valueAsInt = -1;
{I}Our.{enum_name} value = (Our.{enum_name})valueAsInt;

{I}var errors = Our.Verification.Verify{enum_name}(
{II}value).ToList();

{I}Assert.AreEqual(1, errors.Count);
{I}Assert.AreEqual("Invalid {enum_name}: -1", errors[0].Cause);
}}  // void Test_{enum_name}_invalid"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using System.Linq;  // can't alias
using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}public class TestVerificationOfEnums
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestVerificationOfEnums
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
