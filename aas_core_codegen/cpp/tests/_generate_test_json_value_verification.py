"""Generate code to test ``JsonValueVerificator`` in isolation."""

import io

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
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

#include <limits>
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
 * \\brief Drain \\p verificator and return all of its errors, in order.
 *
 * This exercises \\ref verification::JsonValueVerificator exactly the way
 * every other verificator in ``verification.cpp`` is exercised, but
 * standalone, so that we can assert on the *exhaustive* enumeration of
 * the violations -- not just the first one -- independent of any
 * particular meta-model.
 */
std::vector<verification::Error> CollectErrors(
{I}verification::JsonValueVerificator& verificator
) {{
{I}std::vector<verification::Error> errors;

{I}for (
{II}verificator.Start();
{II}!verificator.Done();
{II}verificator.Next()
{I}) {{
{II}errors.push_back(verificator.Get());
{I}}}

{I}return errors;
}}

/**
 * \\brief Render the paths of \\p errors, in order.
 *
 * \\param errors whose paths are to be rendered
 * \\return the rendered paths
 */
std::vector<std::wstring> PathsOf(
{I}const std::vector<verification::Error>& errors
) {{
{I}std::vector<std::wstring> paths;
{I}paths.reserve(errors.size());

{I}for (const verification::Error& error : errors) {{
{II}paths.push_back(error.path.ToWstring());
{I}}}

{I}return paths;
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

{I}REQUIRE(CollectErrors(verificator).empty());
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Reject a null value at the top level") {{
{I}const nlohmann::json value(nullptr);

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kAny
{I});

{I}const std::vector<verification::Error> errors(CollectErrors(verificator));
{I}REQUIRE(errors.size() == 1);

{I}// NOTE (mristin):
{I}// The offending value *is* the value under verification, so there is
{I}// no path leading to it.
{I}REQUIRE(errors[0].path.ToWstring() == L"");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Reject a non-finite number") {{
{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so neither is
{I}// a JSON-able value -- and ``nlohmann::json`` holds either happily if
{I}// it was constructed programmatically rather than parsed.
{I}for (
{II}const double number : {{
{III}std::numeric_limits<double>::infinity(),
{III}-std::numeric_limits<double>::infinity(),
{III}std::numeric_limits<double>::quiet_NaN()
{II}}}
{I}) {{
{II}const nlohmann::json value(number);

{II}verification::JsonValueVerificator verificator(
{III}value, verification::JsonValueShape::kAny
{II});

{II}const std::vector<verification::Error> errors(CollectErrors(verificator));
{II}REQUIRE(errors.size() == 1);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Reject a non-finite number nested in an array") {{
{I}nlohmann::json value = nlohmann::json::array();
{I}value.push_back(1.0);
{I}value.push_back(std::numeric_limits<double>::infinity());

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kArray
{I});

{I}const std::vector<verification::Error> errors(CollectErrors(verificator));
{I}REQUIRE(errors.size() == 1);
{I}REQUIRE(errors[0].path.ToWstring() == L"[1]");
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

{I}const std::vector<verification::Error> errors(CollectErrors(verificator));

{I}INFO(
{II}"Expected exactly two violations (one for each nested null), "
{II}"but got: "
{II}+ std::to_string(errors.size())
{I});
{I}REQUIRE(errors.size() == 2);

{I}const std::vector<std::wstring> paths(PathsOf(errors));
{I}REQUIRE(paths[0] == L"[\\"a\\"][1]");
{I}REQUIRE(paths[1] == L"[\\"a\\"][2][\\"b\\"]");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Report the violations in the order of a depth-first walk") {{
{I}// NOTE (mristin):
{I}// We descend into ``a`` before we ever look at ``z``, which is exactly
{I}// what distinguishes the depth-first walk from a breadth-first one --
{I}// the latter would report ``z`` first, as it sits one level higher.
{I}nlohmann::json value = nlohmann::json::parse(
{II}R"({{"a": {{"deep": null}}, "z": null}})"
{I});

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kObject
{I});

{I}const std::vector<std::wstring> paths(
{II}PathsOf(CollectErrors(verificator))
{I});

{I}REQUIRE(paths.size() == 2);
{I}REQUIRE(paths[0] == L"[\\"a\\"][\\"deep\\"]");
{I}REQUIRE(paths[1] == L"[\\"z\\"]");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Escape a key of a JSON object in the path") {{
{I}// NOTE (mristin):
{I}// The path is meant to read as a C++ expression on the very
{I}// ``nlohmann::json`` value, so a key is escaped exactly as a JSON
{I}// string is.
{I}nlohmann::json value = nlohmann::json::parse(
{II}R"({{"a\\"b\\\\c\\nd": null}})"
{I});

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kObject
{I});

{I}const std::vector<std::wstring> paths(
{II}PathsOf(CollectErrors(verificator))
{I});

{I}REQUIRE(paths.size() == 1);
{I}REQUIRE(paths[0] == L"[\\"a\\\\\\"b\\\\\\\\c\\\\nd\\"]");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Reject a value whose top-level shape does not match kArray") {{
{I}const nlohmann::json value = nlohmann::json::object();

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kArray
{I});

{I}const std::vector<verification::Error> errors(CollectErrors(verificator));
{I}REQUIRE(errors.size() == 1);
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Reject a value whose top-level shape does not match kObject") {{
{I}const nlohmann::json value = nlohmann::json::array();

{I}verification::JsonValueVerificator verificator(
{II}value, verification::JsonValueShape::kObject
{I});

{I}const std::vector<verification::Error> errors(CollectErrors(verificator));
{I}REQUIRE(errors.size() == 1);
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
