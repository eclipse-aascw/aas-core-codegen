"""Generate code to test ``JsonValueVerificator`` in isolation."""

import io

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(library_namespace: Stripped) -> str:
    """Generate implementation to test ``JsonValueVerificator`` in isolation."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            """\
/**
 * Test ``JsonValueVerificator`` -- the exhaustive, depth-agnostic
 * verification of a ``nlohmann::json`` value -- in isolation, independent
 * of any particular meta-model.
 */"""
        ),
        Stripped(
            f"""\
#include "{include_prefix_path}/verification.hpp"
#include "json_value_verification.hpp"

#pragma warning(push, 0)
#include <nlohmann/json.hpp>

#include <string>
#include <vector>
#pragma warning(pop)"""
        ),
        Stripped(
            """\
#define CATCH_CONFIG_MAIN
#include <catch2/catch.hpp>"""
        ),
        Stripped(
            f"""\
namespace aas = {library_namespace};
namespace verification = aas::verification;

namespace {{
/**
 * \\brief Drain \\p verificator and return the causes of all the errors,
 * in order.
 *
 * This exercises \\ref verification::JsonValueVerificator exactly the way
 * every other verificator in ``verification.cpp`` is exercised, but
 * standalone, so that we can assert on the *exhaustive* enumeration of
 * the violations -- not just the first one -- independent of any
 * particular meta-model.
 */
std::vector<std::wstring> CollectCauses(
{I}verification::JsonValueVerificator& verificator
) {{
{I}std::vector<std::wstring> causes;

{I}for (
{II}verificator.Start();
{II}!verificator.Done();
{II}verificator.Next()
{I}) {{
{II}causes.push_back(verificator.Get().cause);
{I}}}

{I}return causes;
}}
}}  // anonymous namespace"""
        ),
        Stripped(
            f"""\
TEST_CASE("Report no violation for a deeply nested, valid value") {{
{I}const nlohmann::json value = nlohmann::json::parse(
{II}R"({{"a": [1.0, true, "x", [1.0, 2.0], {{"b": "not null"}}]}})"
{I});

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kAny
{I});

{I}REQUIRE(CollectCauses(verificator).empty());
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Reject a null value at the top level") {{
{I}const nlohmann::json value(nullptr);

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kAny
{I});

{I}const std::vector<std::wstring> causes(CollectCauses(verificator));
{I}REQUIRE(causes.size() == 1);
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE(
{I}"Report every rejected value at every depth, not just the first"
) {{
{I}nlohmann::json value = nlohmann::json::parse(
{II}R"({{"a": [1.0, null, {{"b": null}}]}})"
{I});

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kAny
{I});

{I}const std::vector<std::wstring> causes(CollectCauses(verificator));

{I}INFO(
{II}"Expected exactly two violations (one for each nested null), "
{II}"but got: "
{II}+ std::to_string(causes.size())
{I});
{I}REQUIRE(causes.size() == 2);
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Reject a value whose top-level shape does not match kArray") {{
{I}const nlohmann::json value = nlohmann::json::object();

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kArray
{I});

{I}const std::vector<std::wstring> causes(CollectCauses(verificator));
{I}REQUIRE(causes.size() == 1);
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Reject a value whose top-level shape does not match kObject") {{
{I}const nlohmann::json value = nlohmann::json::array();

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kObject
{I});

{I}const std::vector<std::wstring> causes(CollectCauses(verificator));
{I}REQUIRE(causes.size() == 1);
}}"""
        ),
        cpp_common.WARNING,
    ]

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
