"""Generate code to test the JSON de/serialization of concrete classes."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_serialization_failure_infrastructure() -> List[Stripped]:
    """Generate the helpers shared by the tests of the serialization failures."""
    return [
        Stripped(
            f"""\
template<class ClassT>
std::shared_ptr<ClassT> MustDeserializeTheFirstExpected(
{I}const std::string& model_type,
{I}std::function<
{II}aas::common::expected<
{III}std::shared_ptr<ClassT>,
{III}aas::jsonization::DeserializationError
{II}>(const nlohmann::json&, bool)
{I}> deserialization_function
) {{
{I}const std::deque<std::filesystem::path> paths(
{II}test::common::FindFilesBySuffixRecursively(
{III}DetermineJsonDir() / "Expected" / model_type,
{III}".json"
{II})
{I});

{I}INFO("We expect at least one recorded example of " + model_type)
{I}REQUIRE(!paths.empty());

{I}const nlohmann::json json = test::common::jsonization::MustReadJson(
{II}paths.front()
{I});

{I}aas::common::expected<
{II}std::shared_ptr<ClassT>,
{II}aas::jsonization::DeserializationError
{I}> deserialized = deserialization_function(json, false);

{I}INFO(
{II}aas::common::Concat(
{III}"Failed to de-serialize from ",
{III}paths.front().string()
{II})
{I})
{I}REQUIRE(deserialized.has_value());

{I}return deserialized.value();
}}"""
        ),
        Stripped(
            f"""\
/**
 * Assert that \\p that instance can not be serialized to JSON, and that
 * the failure is reported at \\p expected_path.
 */
void AssertSerializationFailsAt(
{I}const aas::types::IClass& that,
{I}const std::string& expected_path
) {{
{I}try {{
{II}aas::jsonization::Serialize(that);
{I}}} catch (const aas::jsonization::SerializationException& exception) {{
{II}const std::string observed_path(
{III}aas::common::WstringToUtf8(
{IIII}exception.path().ToWstring()
{III})
{II});

{II}INFO(
{III}aas::common::Concat(
{IIII}"Expected the serialization to fail at ",
{IIII}expected_path,
{IIII}", but it failed at ",
{IIII}observed_path,
{IIII}": ",
{IIII}aas::common::WstringToUtf8(exception.cause())
{III})
{II})
{II}REQUIRE(observed_path == expected_path);

{II}return;
{I}}}

{I}INFO(
{II}aas::common::Concat(
{III}"Expected the serialization to fail at ",
{III}expected_path,
{III}", but it succeeded"
{II})
{I})
{I}REQUIRE(false);
}}"""
        ),
    ]


def _generate_serialization_failure_test_case(
    numeric_place: intermediate.NumericPlace,
) -> Stripped:
    """Generate the test that a number unrepresentable in JSON is refused."""
    if numeric_place.a_type is intermediate.PrimitiveType.FLOAT:
        value_type = "double"
        zero_literal = "0.0"
        what = "a non-finite floating-point number"
        value_literals = [
            "std::numeric_limits<double>::infinity()",
            "-std::numeric_limits<double>::infinity()",
            "std::numeric_limits<double>::quiet_NaN()",
        ]
    else:
        value_type = "int64_t"
        zero_literal = "0LL"
        what = "an integer outside the range representable in JSON"
        value_literals = ["9007199254740992LL", "-9007199254740992LL"]

    setter_name = cpp_naming.setter_name(numeric_place.prop.name)

    if numeric_place.index is None:
        mutation = Stripped(f"instance->{setter_name}(value);")
        expected_path = f".{numeric_place.prop.name}"
    elif numeric_place.in_list:
        # NOTE (mristin):
        # The value goes to the position indicated by the numeric place so that
        # a serializer which always reports the index 0 does not pass.
        items_joined = ",\n".join(
            "value" if i == numeric_place.index else zero_literal
            for i in range(numeric_place.index + 1)
        )

        mutation = Stripped(
            f"""\
instance->{setter_name}(
{I}std::vector<{value_type}>{{
{II}{indent_but_first_line(items_joined, II)}
{I}}}
);"""
        )
        expected_path = f".{numeric_place.prop.name}[{numeric_place.index}]"
    else:
        mutable_getter_name = cpp_naming.mutable_getter_name(numeric_place.prop.name)

        mutation = Stripped(
            f"""\
std::get<{numeric_place.index}>(
{I}instance->{mutable_getter_name}()
) = value;"""
        )
        expected_path = f".{numeric_place.prop.name}[{numeric_place.index}]"

    interface_name = cpp_naming.interface_name(numeric_place.cls.name)

    model_type = naming.json_model_type(numeric_place.cls.name)

    deserialization_function = cpp_naming.function_name(
        Identifier(f"{numeric_place.cls.name}_from")
    )

    values_joined = ",\n".join(value_literals)

    return Stripped(
        f"""\
TEST_CASE(
{I}"Test the serialization failure on {what} "
{I}"at {expected_path} of {model_type}"
) {{
{I}for (
{II}const {value_type} value
{II}: {{
{III}{indent_but_first_line(values_joined, III)}
{II}}}
{I}) {{
{II}std::shared_ptr<aas::types::{interface_name}> instance(
{III}MustDeserializeTheFirstExpected<aas::types::{interface_name}>(
{IIII}{cpp_common.string_literal(model_type)},
{IIII}aas::jsonization::{deserialization_function}
{III})
{II});

{II}{indent_but_first_line(mutation, II)}

{II}AssertSerializationFailsAt(
{III}*instance,
{III}{cpp_common.string_literal(expected_path)}
{II});
{I}}}
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
    """Generate implementation to test the JSON de/serialization of concrete classes."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    numeric_places = intermediate.numeric_places(symbol_table)

    # NOTE (mristin):
    # Only the tests of the serialization failures need the limits of
    # the floating-point numbers.
    limits_include = "\n#include <limits>\n" if len(numeric_places) > 0 else ""

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common.hpp"
#include "./common_jsonization.hpp"

#include <{include_prefix_path}/jsonization.hpp>
{limits_include}
#define CATCH_CONFIG_MAIN
#include <catch2/catch.hpp>

namespace aas = {library_namespace};"""
        ),
        Stripped(
            f"""\
template<class ClassT>
void AssertRoundTrip(
{I}const std::filesystem::path& path,
{I}std::function<
{II}aas::common::expected<
{III}std::shared_ptr<ClassT>,
{III}aas::jsonization::DeserializationError
{II}>(const nlohmann::json&, bool)
{I}> deserialization_function
) {{
{I}const nlohmann::json json = test::common::jsonization::MustReadJson(path);

{I}aas::common::expected<
{II}std::shared_ptr<ClassT>,
{II}aas::jsonization::DeserializationError
{I}> deserialized = deserialization_function(json, false);

{I}if (!deserialized.has_value()) {{
{II}INFO(
{III}aas::common::Concat(
{IIII}"Failed to de-serialize from ",
{IIII}path.string(),
{IIII}": ",
{IIII}aas::common::WstringToUtf8(
{IIIII}deserialized.error().path.ToWstring()
{IIII}),
{IIII}": ",
{IIII}aas::common::WstringToUtf8(
{IIIII}deserialized.error().cause
{IIII})
{III})
{II})
{II}REQUIRE(deserialized.has_value());
{I}}}

{I}nlohmann::json another_json = aas::jsonization::Serialize(
{II}*(deserialized.value())
{I});

{I}std::optional<std::string> diff_message = test::common::jsonization::CompareJsons(
{II}json,
{II}another_json
{I});
{I}if (diff_message.has_value()) {{
{II}INFO(
{III}aas::common::Concat(
{IIII}"The JSON round-trip from ",
{IIII}path.string(),
{IIII}" failed. There is a diff between the original JSON "
{IIII}"and the serialized one: ",
{IIII}*diff_message
{III})
{II})
{II}REQUIRE(!diff_message.has_value());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
template<typename ClassT>
void AssertDeserializationFailure(
{I}const std::filesystem::path& path,
{I}std::function<
{II}aas::common::expected<
{III}std::shared_ptr<ClassT>,
{III}aas::jsonization::DeserializationError
{II}>(const nlohmann::json&, bool)
{I}> deserialization_function,
{I}const std::filesystem::path& error_path
) {{
{I}const nlohmann::json json = test::common::jsonization::MustReadJson(path);

{I}aas::common::expected<
{II}std::shared_ptr<ClassT>,
{II}aas::jsonization::DeserializationError
{I}> deserialized = deserialization_function(json, false);

{I}if (deserialized.has_value()) {{
{II}INFO(
{III}aas::common::Concat(
{IIII}"Expected the de-serialization to fail on ",
{IIII}path.string(),
{IIII}", but the de-serialization succeeded"
{III})
{II})
{II}REQUIRE(!deserialized.has_value());
{I}}}

{I}test::common::AssertContentEqualsExpectedOrRecord(
{II}aas::common::Concat(
{III}aas::common::WstringToUtf8(
{IIII}deserialized.error().path.ToWstring()
{III}),
{III}": ",
{III}aas::common::WstringToUtf8(
{IIII}deserialized.error().cause
{III})
{II}),
{II}error_path
{I});
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineJsonDir() {{
{I}static aas::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "Json";
{I}}}

{I}return *result;
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineErrorDir() {{
{I}static aas::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "JsonizationError";
{I}}}

{I}return *result;
}}"""
        ),
    ]  # type: List[Stripped]

    if len(numeric_places) > 0:
        blocks.extend(_generate_serialization_failure_infrastructure())

    for concrete_cls in symbol_table.concrete_classes:
        interface_name = cpp_naming.interface_name(concrete_cls.name)

        model_type = naming.json_model_type(concrete_cls.name)

        deserialization_function = cpp_naming.function_name(
            Identifier(f"{concrete_cls.name}_from")
        )

        cls_name = cpp_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test the round-trip of an expected {cls_name}") {{
{I}const std::deque<std::filesystem::path> paths(
{II}test::common::FindFilesBySuffixRecursively(
{III}DetermineJsonDir()
{IIII}/ "Expected"
{IIII}/ {cpp_common.string_literal(model_type)},
{III}".json"
{II})
{I});

{I}for (const std::filesystem::path& path : paths) {{
{II}AssertRoundTrip<
{III}aas::types::{interface_name}
{II}>(path, aas::jsonization::{deserialization_function});
{I}}}
}}"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test the de-serialization failure on an unexpected {cls_name}") {{
{I}for (
{II}const std::filesystem::path& causeDir
{II}: test::common::ListSubdirectories(
{III}DetermineJsonDir()
{IIII}/ "Unexpected"
{IIII}/ "Unserializable"
{II})
{I}) {{
{II}for (
{III}const std::filesystem::path& path
{III}: test::common::FindFilesBySuffixRecursively(
{IIII}causeDir / {cpp_common.string_literal(model_type)},
{IIII}".json"
{III})
{II}) {{
{III}const std::filesystem::path parent(
{IIII}(
{IIIII}DetermineErrorDir()
{IIIII}/ std::filesystem::relative(path, DetermineJsonDir())
{IIII}).parent_path()
{III});

{III}const std::filesystem::path error_path(
{IIII}parent
{IIII}/ (path.filename().string() + ".error")
{III});

{III}AssertDeserializationFailure<
{IIII}aas::types::{interface_name}
{III}>(
{IIII}path,
{IIII}aas::jsonization::{deserialization_function},
{IIII}error_path
{III});
{II}}}
{I}}}
}}"""
            )
        )

    for numeric_place in numeric_places:
        blocks.append(_generate_serialization_failure_test_case(numeric_place))

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
