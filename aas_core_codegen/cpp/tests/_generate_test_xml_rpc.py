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
#include <tuple>
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
namespace xml_common = aas::xml_common;
namespace xml_rpc = aas::xml_rpc;

namespace {{
/**
 * Serialize \\p value, deserialize it back and require that the outcome
 * equals \\p value.
 */
void RequireRoundTrip(const nlohmann::json& value) {{
{I}std::ostringstream oss;
{I}common::optional<xml_rpc::SerializationError> serialization_error(
{II}xml_rpc::SerializeValue(oss, value)
{I});
{I}INFO(
{II}"Unexpected serialization error for "
{II}+ value.dump()
{I});
{I}REQUIRE(!serialization_error.has_value());

{I}const std::string xml_text(oss.str());

{I}std::istringstream iss(xml_text);
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss)
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

{I}// NOTE (mristin):
{I}// A double is written with as many digits as it takes to read it back
{I}// as the very same value, so even the least round of them round-trips.
{I}RequireRoundTrip(nlohmann::json(1.2345678901234567));
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Serialize rejects a non-finite number") {{
{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so neither is
{I}// a JSON-able value, even though ``nlohmann::json`` holds one happily.
{I}for (
{II}const double value : {{
{III}std::numeric_limits<double>::infinity(),
{III}-std::numeric_limits<double>::infinity(),
{III}std::numeric_limits<double>::quiet_NaN()
{II}}}
{I}) {{
{II}std::ostringstream oss;
{II}common::optional<xml_rpc::SerializationError> error(
{III}xml_rpc::SerializeValue(oss, nlohmann::json(value))
{II});
{II}REQUIRE(error.has_value());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize rejects a non-finite number") {{
{I}// NOTE (mristin):
{I}// The xs:double spellings of the three special values are deliberately
{I}// not part of the <double> lexical space here, and a literal which
{I}// rounds to an infinity is refused rather than rounded.
{I}for (
{II}const std::string& text : {{
{III}std::string("INF"),
{III}std::string("-INF"),
{III}std::string("NaN"),
{III}std::string("1e400"),
{III}std::string("-1e400")
{II}}}
{I}) {{
{II}std::istringstream iss(
{III}"<value><double>"
{III}+ text
{III}+ "</double></value>"
{II});
{II}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{III}xml_rpc::DeserializeValue(iss)
{II});
{II}INFO("Unexpectedly accepted the <double> text " + text);
{II}REQUIRE(!result.has_value());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize rejects a malformed double") {{
{I}// NOTE (mristin):
{I}// std::strtod would read all of these, which is exactly why the lexical
{I}// form is matched before the text is ever parsed.
{I}for (
{II}const std::string& text : {{
{III}std::string("0x10"),
{III}std::string("1.0abc"),
{III}std::string("inf"),
{III}std::string("nan"),
{III}std::string("")
{II}}}
{I}) {{
{II}std::istringstream iss(
{III}"<value><double>"
{III}+ text
{III}+ "</double></value>"
{II});
{II}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{III}xml_rpc::DeserializeValue(iss)
{II});
{II}INFO("Unexpectedly accepted the <double> text " + text);
{II}REQUIRE(!result.has_value());
{I}}}
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
{II}xml_rpc::SerializeValue(oss, nlohmann::json(nullptr))
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
{II}xml_rpc::SerializeValue(oss, value)
{I});
{I}REQUIRE(error.has_value());
{I}REQUIRE(error->path.ToWstring() == L"[1]");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Serialize reports the key of an invalid member") {{
{I}nlohmann::json value = nlohmann::json::object();
{I}value["a"] = 1.0;
{I}value["b"] = nlohmann::json(nullptr);

{I}std::ostringstream oss;
{I}common::optional<xml_rpc::SerializationError> error(
{II}xml_rpc::SerializeValue(oss, value)
{I});
{I}REQUIRE(error.has_value());

{I}// NOTE (mristin):
{I}// A serialization error points into the value that we were given,
{I}// not into a document which was never written, so the path reads as
{I}// a C++ expression on that value.
{I}REQUIRE(error->path.ToWstring() == L"[\\"b\\"]");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize reports the XPath to a nested invalid value") {{
{I}// NOTE (mristin):
{I}// The XPath descends through every element which actually stands in
{I}// the document -- the <struct> and <array> wrappers included, since
{I}// we entered both of them on the way down.
{I}std::istringstream iss(
{II}"<value><struct>"
{II}"<member><name>nested</name><value><array><data>"
{II}"<value><double>1</double></value>"
{II}"<value><nil/></value>"
{II}"</data></array></value></member>"
{II}"</struct></value>"
{I});
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss)
{I});
{I}REQUIRE(!result.has_value());

{I}INFO(
{II}"Unexpected XPath: "
{II}+ common::WstringToUtf8(result.error().path.ToWstring())
{I});
{I}REQUIRE(
{II}result.error().path.ToWstring()
{II}== L"struct/member[name=\\"nested\\"]/value/array/data/*[1]"
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize reports no <array> wrapper for an array body") {{
{I}// NOTE (mristin):
{I}// A property which is by definition an array holds the <data> element
{I}// directly, with no <array> wrapper, so the XPath must not invent one.
{I}// We enter here exactly where the xmlization enters for such
{I}// a property.
{I}std::istringstream iss(
{II}"<data>"
{II}"<value><nil/></value>"
{II}"</data>"
{I});
{I}xml_common::ReaderMergingText reader(
{II}iss, false, 1024
{I});
{I}reader.Initialize();

{I}common::optional<nlohmann::json> value;
{I}common::optional<xml_rpc::DeserializationError> error;
{I}std::tie(value, error) = xml_rpc::DeserializeArrayBodyFrom(reader);

{I}REQUIRE(error.has_value());
{I}REQUIRE(error->path.ToWstring() == L"data/*[0]");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize reports no <struct> wrapper for a struct body") {{
{I}// NOTE (mristin):
{I}// The counterpart of the array body -- a property which is by
{I}// definition an object holds the <member> elements directly.
{I}std::istringstream iss(
{II}"<member>"
{II}"<name>k</name><value><nil/></value>"
{II}"</member>"
{I});
{I}xml_common::ReaderMergingText reader(
{II}iss, false, 1024
{I});
{I}reader.Initialize();

{I}common::optional<nlohmann::json> value;
{I}common::optional<xml_rpc::DeserializationError> error;
{I}std::tie(value, error) = xml_rpc::DeserializeStructBodyFrom(reader);

{I}REQUIRE(error.has_value());
{I}REQUIRE(error->path.ToWstring() == L"member[name=\\"k\\"]/value");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize escapes a member name in the XPath") {{
{I}// NOTE (mristin):
{I}// A member name is arbitrary text, so it has to be escaped lest it
{I}// break out of the XPath predicate which matches on it.
{I}std::istringstream iss(
{II}"<member>"
{II}"<name>a&amp;b&quot;c</name><value><nil/></value>"
{II}"</member>"
{I});
{I}xml_common::ReaderMergingText reader(
{II}iss, false, 1024
{I});
{I}reader.Initialize();

{I}common::optional<nlohmann::json> value;
{I}common::optional<xml_rpc::DeserializationError> error;
{I}std::tie(value, error) = xml_rpc::DeserializeStructBodyFrom(reader);

{I}REQUIRE(error.has_value());
{I}REQUIRE(
{II}error->path.ToWstring()
{II}== L"member[name=\\"a&amp;b&quot;c\\"]/value"
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize rejects an unexpected element") {{
{I}std::istringstream iss(
{II}"<value><nil/></value>"
{I});
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss)
{I});
{I}REQUIRE(!result.has_value());
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize accepts only a strict \\"0\\"/\\"1\\" for a boolean") {{
{I}{{
{II}std::istringstream iss(
{III}"<value>"
{III}"<boolean>true</boolean></value>"
{II});
{II}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{III}xml_rpc::DeserializeValue(iss)
{II});
{II}REQUIRE(!result.has_value());
{I}}}

{I}{{
{II}std::istringstream iss(
{III}"<value>"
{III}"<boolean>1</boolean></value>"
{II});
{II}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{III}xml_rpc::DeserializeValue(iss)
{II});
{II}REQUIRE(result.has_value());
{II}REQUIRE(*result == nlohmann::json(true));
{I}}}
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize rejects a repeated member key") {{
{I}// NOTE (mristin):
{I}// A repeated <member> name is refused, just as a repeated property
{I}// element is refused in the xmlization -- letting the later member
{I}// win would silently accept a document which says two different
{I}// things about the same key.
{I}std::istringstream iss(
{II}"<value><struct>"
{II}"<member><name>a</name><value><double>1</double></value></member>"
{II}"<member><name>a</name><value><double>2</double></value></member>"
{II}"</struct></value>"
{I});
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss)
{I});
{I}REQUIRE(!result.has_value());
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize collapses the whitespace of a boolean and a double") {{
{I}// NOTE (mristin):
{I}// `whiteSpace` is fixed to `collapse` for every atomic XSD type but
{I}// a string, so a pretty-printed document has to be read as well.
{I}{{
{II}std::istringstream iss(
{III}"<value>"
{III}"<boolean>\\n  1\\n  </boolean></value>"
{II});
{II}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{III}xml_rpc::DeserializeValue(iss)
{II});
{II}REQUIRE(result.has_value());
{II}REQUIRE(*result == nlohmann::json(true));
{I}}}

{I}{{
{II}std::istringstream iss(
{III}"<value>"
{III}"<double>\\n  3.14\\n  </double></value>"
{II});
{II}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{III}xml_rpc::DeserializeValue(iss)
{II});
{II}REQUIRE(result.has_value());
{II}REQUIRE(*result == nlohmann::json(3.14));
{I}}}
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize preserves the whitespace of a string") {{
{I}// NOTE (mristin):
{I}// `xs:string` is `preserve` and not `collapse`, so a <string> keeps
{I}// its whitespace, unlike a <boolean> or a <double>.
{I}std::istringstream iss(
{II}"<value>"
{II}"<string>  keep  me  </string></value>"
{I});
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss)
{I});
{I}REQUIRE(result.has_value());
{I}REQUIRE(*result == nlohmann::json(std::string("  keep  me  ")));
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
{II}xml_rpc::DeserializeValue(iss)
{I});
{I}REQUIRE(!result.has_value());
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Deserialize rejects an element within the document namespace") {{
{I}// NOTE (mristin):
{I}// The XML-RPC elements reside in no namespace at all, so an element which
{I}// inherits the namespace of an enclosing document is none of ours.
{I}std::istringstream iss(
{II}common::Concat(
{III}"<value xmlns=\\"",
{III}xml_common::kNamespace,
{III}"\\"><boolean>1</boolean></value>"
{II})
{I});
{I}common::expected<nlohmann::json, xml_rpc::DeserializationError> result(
{II}xml_rpc::DeserializeValue(iss)
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
