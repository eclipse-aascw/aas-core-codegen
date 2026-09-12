"""Generate code to test the ``xml_rpc`` module in isolation."""

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
    """Generate implementation to test the ``xml_rpc`` module in isolation."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            """\
/**
 * Test the ``xml_rpc`` module -- the de/serialization of JSON-able values
 * to and from the XML-RPC subset -- in isolation, independent of any
 * particular meta-model.
 */"""
        ),
        Stripped(
            f"""\
#include "{include_prefix_path}/common.hpp"
#include "xml_rpc.hpp"

#pragma warning(push, 0)
#include <nlohmann/json.hpp>

#include <cmath>
#include <limits>
#include <sstream>
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
namespace common = aas::common;
namespace xml_rpc = aas::xml_rpc;

namespace {{
const std::string kNamespace("https://xml-rpc.test/1/0");

/**
 * Serialize \\p value, deserialize it back and require that the outcome
 * equals \\p value.
 */
void RequireRoundTrip(const nlohmann::json& value) {{
{I}std::ostringstream oss;
{I}common::optional<xml_rpc::SerializationError> serialization_error(
{II}xml_rpc::SerializeValue(oss, value, kNamespace)
{I});
{I}INFO(
{II}"Unexpected serialization error for "
{II}+ value.dump()
{I});
{I}REQUIRE(!serialization_error.has_value());

{I}const std::string xml_text(oss.str());

{I}std::istringstream iss(xml_text);
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss, kNamespace)
{I});
{I}INFO(
{II}"Unexpected de-serialization error for "
{II}+ xml_text
{I});
{I}REQUIRE(result.has_value());

{I}REQUIRE(*result == value);
}}
}}  // anonymous namespace"""
        ),
        Stripped(
            f"""\
TEST_CASE("Round-trip a boolean") {{
{I}RequireRoundTrip(nlohmann::json(true));
{I}RequireRoundTrip(nlohmann::json(false));
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Round-trip a double") {{
{I}RequireRoundTrip(nlohmann::json(0.0));
{I}RequireRoundTrip(nlohmann::json(3.14));
{I}RequireRoundTrip(nlohmann::json(-1.0));
{I}RequireRoundTrip(
{II}nlohmann::json(std::numeric_limits<double>::infinity())
{I});
{I}RequireRoundTrip(
{II}nlohmann::json(-std::numeric_limits<double>::infinity())
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Round-trip NaN") {{
{I}// NOTE (mristin):
{I}// NaN can not be compared with ``==``, so we test it separately from
{I}// the other doubles.
{I}std::ostringstream oss;
{I}common::optional<xml_rpc::SerializationError> serialization_error(
{II}xml_rpc::SerializeValue(
{III}oss,
{III}nlohmann::json(std::numeric_limits<double>::quiet_NaN()),
{III}kNamespace
{II})
{I});
{I}REQUIRE(!serialization_error.has_value());
{I}REQUIRE(oss.str() == "<value xmlns=\\"https://xml-rpc.test/1/0\\">"
{II}"<double>NaN</double></value>");

{I}std::istringstream iss(oss.str());
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss, kNamespace)
{I});
{I}REQUIRE(result.has_value());
{I}REQUIRE(result->is_number());
{I}REQUIRE(std::isnan(result->get<double>()));
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Round-trip a string") {{
{I}RequireRoundTrip(nlohmann::json(std::string()));
{I}RequireRoundTrip(nlohmann::json(std::string("something simple")));
{I}RequireRoundTrip(
{II}nlohmann::json(
{III}std::string("needs & <escaping> \\"badly\\" 'so'")
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Round-trip an array") {{
{I}RequireRoundTrip(nlohmann::json::array());

{I}RequireRoundTrip(
{II}nlohmann::json::parse(
{III}R"([1.0, true, "x", [1.0, 2.0], {{"a": 1.0}}])"
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Round-trip an object") {{
{I}RequireRoundTrip(nlohmann::json::object());

{I}RequireRoundTrip(
{II}nlohmann::json::parse(
{III}R"({{"a": 1.0, "b": [true, false], "c": {{"d": "e"}}}})"
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Serialize rejects null") {{
{I}std::ostringstream oss;
{I}common::optional<xml_rpc::SerializationError> error(
{II}xml_rpc::SerializeValue(oss, nlohmann::json(nullptr), kNamespace)
{I});
{I}REQUIRE(error.has_value());
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Serialize reports the path to a nested invalid value") {{
{I}nlohmann::json value = nlohmann::json::array();
{I}value.push_back(1.0);
{I}value.push_back(nlohmann::json(nullptr));

{I}std::ostringstream oss;
{I}common::optional<xml_rpc::SerializationError> error(
{II}xml_rpc::SerializeValue(oss, value, kNamespace)
{I});
{I}REQUIRE(error.has_value());
{I}REQUIRE(error->path.ToWstring() == L"[1]");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize rejects an unexpected element") {{
{I}std::istringstream iss(
{II}"<value xmlns=\\"https://xml-rpc.test/1/0\\"><nil/></value>"
{I});
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss, kNamespace)
{I});
{I}REQUIRE(!result.has_value());
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize accepts only a strict \\"0\\"/\\"1\\" for a boolean") {{
{I}{{
{II}std::istringstream iss(
{III}"<value xmlns=\\"https://xml-rpc.test/1/0\\">"
{III}"<boolean>true</boolean></value>"
{II});
{II}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{III}xml_rpc::DeserializeValue(iss, kNamespace)
{II});
{II}REQUIRE(!result.has_value());
{I}}}

{I}{{
{II}std::istringstream iss(
{III}"<value xmlns=\\"https://xml-rpc.test/1/0\\">"
{III}"<boolean>1</boolean></value>"
{II});
{II}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{III}xml_rpc::DeserializeValue(iss, kNamespace)
{II});
{II}REQUIRE(result.has_value());
{II}REQUIRE(*result == nlohmann::json(true));
{I}}}
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize resolves a repeated member key to the last value") {{
{I}std::istringstream iss(
{II}"<value xmlns=\\"https://xml-rpc.test/1/0\\"><struct>"
{II}"<member><name>a</name><value><double>1</double></value></member>"
{II}"<member><name>a</name><value><double>2</double></value></member>"
{II}"</struct></value>"
{I});
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss, kNamespace)
{I});
{I}REQUIRE(result.has_value());
{I}REQUIRE((*result)["a"] == nlohmann::json(2.0));
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize rejects an XML namespace mismatch") {{
{I}std::istringstream iss(
{II}"<value xmlns=\\"https://unexpected.example.com\\">"
{II}"<boolean>1</boolean></value>"
{I});
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss, kNamespace)
{I});
{I}REQUIRE(!result.has_value());
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
