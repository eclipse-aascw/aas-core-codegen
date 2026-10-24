"""Generate code to test the stringification of enums."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    Identifier,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


def _generate_test_round_trip_for_model_type(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """
    Generate the test case for valid de/stringification of model type enum.

    This enum does not explicitly exist in the meta-model, so we have to generate
    the test for it separately.
    """
    enum_name = cpp_naming.enum_name(Identifier("Model_type"))

    statements: List[Stripped] = []

    must_from_string = cpp_naming.function_name(
        Identifier("must_model_type_from_string")
    )

    for concrete_cls in symbol_table.concrete_classes:
        literal_name = cpp_naming.enum_literal_name(concrete_cls.name)
        literal_value = naming.json_model_type(concrete_cls.name)

        statements.append(
            Stripped(
                f"""\
REQUIRE(
{I}our::types::{enum_name}::{literal_name}
{I}== our::stringification::{must_from_string}(
{II}{cpp_common.string_literal(literal_value)}
{I})
);"""
            )
        )

        statements.append(
            Stripped(
                f"""\
REQUIRE(
{I}our::stringification::to_string(
{II}our::types::{enum_name}::{literal_name}
{I})
{I}== {cpp_common.string_literal(literal_value)}
);"""
            )
        )

    body = "\n\n".join(statements)

    return Stripped(
        f"""\
TEST_CASE("Test {enum_name} round-trip") {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_test_failure_for_model_type() -> Stripped:
    """
    Generate the test case for invalid de-stringification of model type enum.

    This enum does not explicitly exist in the meta-model, so we have to generate
    the test for it separately.
    """
    enum_name = cpp_naming.enum_name(Identifier("Model_type"))

    from_string = cpp_naming.function_name(Identifier("model_type_from_string"))

    must_from_string = cpp_naming.function_name(
        Identifier("must_model_type_from_string")
    )

    return Stripped(
        f"""\
TEST_CASE("Test failure on {enum_name}") {{
{I}CHECK(
{II}!our::stringification::{from_string}(
{III}"Totally utterly invalid"
{II}).has_value()
{I});

{I}REQUIRE_THROWS_WITH(
{II}our::stringification::{must_from_string}(
{III}"Totally utterly invalid"
{II}),
{II}"Unexpected {enum_name} literal: Totally utterly invalid"
{I});
}}"""
    )


def _generate_test_round_trip_for(enum: intermediate.Enumeration) -> Stripped:
    """Generate the test of the valid de/serialization for an enum."""
    enum_name = cpp_naming.enum_name(enum.name)

    statements: List[Stripped] = []

    must_from_string = cpp_naming.function_name(
        Identifier(f"must_{enum.name}_from_string")
    )

    for literal in enum.literals:
        literal_name = cpp_naming.enum_literal_name(literal.name)

        statements.append(
            Stripped(
                f"""\
REQUIRE(
{I}our::types::{enum_name}::{literal_name}
{I}== our::stringification::{must_from_string}(
{II}{cpp_common.string_literal(literal.value)}
{I})
);"""
            )
        )

        statements.append(
            Stripped(
                f"""\
REQUIRE(
{I}our::stringification::to_string(
{II}our::types::{enum_name}::{literal_name}
{I})
{I}== {cpp_common.string_literal(literal.value)}
);"""
            )
        )

    body = "\n\n".join(statements)

    return Stripped(
        f"""\
TEST_CASE("Test {enum_name} round-trip") {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_test_failure_for(enum: intermediate.Enumeration) -> Stripped:
    """Generate the de-stringification of an invalid literal."""
    enum_name = cpp_naming.enum_name(enum.name)

    from_string = cpp_naming.function_name(Identifier(f"{enum.name}_from_string"))

    must_from_string = cpp_naming.function_name(
        Identifier(f"must_{enum.name}_from_string")
    )

    return Stripped(
        f"""\
TEST_CASE("Test failure on {enum_name}") {{
{I}CHECK(
{II}!our::stringification::{from_string}(
{III}"Totally utterly invalid"
{II}).has_value()
{I});

{I}REQUIRE_THROWS_WITH(
{II}our::stringification::{must_from_string}(
{III}"Totally utterly invalid"
{II}),
{II}"Unexpected {enum_name} literal: Totally utterly invalid"
{I});
}}"""
    )


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate implementation to test the stringification of enums."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/stringification.hpp"

#include <catch2/catch.hpp>

namespace our = {library_namespace};"""
        ),
        _generate_test_round_trip_for_model_type(symbol_table=symbol_table),
        _generate_test_failure_for_model_type(),
    ]

    for enum in symbol_table.enumerations:
        if len(enum.literals) == 0:
            continue

        blocks.append(_generate_test_round_trip_for(enum=enum))

        blocks.append(_generate_test_failure_for(enum=enum))

    blocks.append(cpp_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
