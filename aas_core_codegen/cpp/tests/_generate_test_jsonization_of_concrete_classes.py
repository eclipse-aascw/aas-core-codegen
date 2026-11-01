"""Generate code to test the JSON de/serialization of concrete classes."""

import io
from typing import List, Tuple

from icontract import ensure, require

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
{II}our::common::expected<
{III}std::shared_ptr<ClassT>,
{III}our::jsonization::DeserializationError
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

{I}our::common::expected<
{II}std::shared_ptr<ClassT>,
{II}our::jsonization::DeserializationError
{I}> deserialized = deserialization_function(json, false);

{I}INFO(
{II}our::common::Concat(
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
{I}const our::types::IClass& that,
{I}const std::string& expected_path
) {{
{I}try {{
{II}our::jsonization::Serialize(that);
{I}}} catch (const our::jsonization::SerializationException& exception) {{
{II}const std::string observed_path(
{III}our::common::WstringToUtf8(
{IIII}exception.path().ToWstring()
{III})
{II});

{II}INFO(
{III}our::common::Concat(
{IIII}"Expected the serialization to fail at ",
{IIII}expected_path,
{IIII}", but it failed at ",
{IIII}observed_path,
{IIII}": ",
{IIII}our::common::WstringToUtf8(exception.cause())
{III})
{II})
{II}REQUIRE(observed_path == expected_path);

{II}return;
{I}}}

{I}INFO(
{II}our::common::Concat(
{III}"Expected the serialization to fail at ",
{III}expected_path,
{III}", but it succeeded"
{II})
{I})
{I}REQUIRE(false);
}}"""
        ),
    ]


def _generate_safe_integer_infrastructure() -> List[Stripped]:
    """Generate the helpers for the tests of the safe integer range."""
    return [
        Stripped(
            f"""\
/**
 * Assert that the verification, the JSON serialization and the XML serialization
 * of \\p that instance all report \\p expected_cause at \\p expected_path.
 */
void AssertReportedEverywhere(
{I}const std::shared_ptr<our::types::IClass>& that,
{I}const std::string& expected_path,
{I}const std::wstring& expected_cause
) {{
{I}bool reported = false;
{I}std::vector<std::string> error_messages;
{I}for (
{II}const our::verification::Error& error
{II}: our::verification::RecursiveVerification(that)
{I}) {{
{II}const std::string path(
{III}our::common::WstringToUtf8(error.path.ToWstring())
{II});
{II}if (path == expected_path && error.cause == expected_cause) {{
{III}reported = true;
{III}break;
{II}}}

{II}error_messages.emplace_back(
{III}our::common::Concat(
{IIII}path,
{IIII}": ",
{IIII}our::common::WstringToUtf8(error.cause)
{III})
{II});
{I}}}

{I}INFO(
{II}our::common::Concat(
{III}"Expected the verification to report at ",
{III}expected_path,
{III}": ",
{III}our::common::WstringToUtf8(expected_cause),
{III}", but got:\\n",
{III}test::common::JoinStrings(error_messages, "\\n")
{II})
{I})
{I}REQUIRE(reported);

{I}try {{
{II}our::jsonization::Serialize(*that);

{II}INFO("Expected the JSON serialization to fail at " + expected_path)
{II}REQUIRE(false);
{I}}} catch (const our::jsonization::SerializationException& exception) {{
{II}REQUIRE(
{III}our::common::WstringToUtf8(exception.path().ToWstring())
{IIII}== expected_path
{II});
{II}REQUIRE(exception.cause() == expected_cause);
{I}}}

{I}std::ostringstream oss;
{I}try {{
{II}our::xmlization::Serialize(*that, {{}}, oss);

{II}INFO("Expected the XML serialization to fail at " + expected_path)
{II}REQUIRE(false);
{I}}} catch (const our::xmlization::SerializationException& exception) {{
{II}REQUIRE(
{III}our::common::WstringToUtf8(exception.path().ToWstring())
{IIII}== expected_path
{II});
{II}REQUIRE(exception.cause() == expected_cause);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Assert that neither the verification nor the JSON serialization nor the XML
 * serialization of \\p that instance report an error of the safe integer range
 * at \\p path.
 */
void AssertNotReportedAnywhere(
{I}const std::shared_ptr<our::types::IClass>& that,
{I}const std::string& path
) {{
{I}for (
{II}const our::verification::Error& error
{II}: our::verification::RecursiveVerification(that)
{I}) {{
{II}INFO(
{III}our::common::Concat(
{IIII}our::common::WstringToUtf8(error.path.ToWstring()),
{IIII}": ",
{IIII}our::common::WstringToUtf8(error.cause)
{III})
{II})
{II}REQUIRE(
{III}!(
{IIII}our::common::WstringToUtf8(error.path.ToWstring()) == path
{IIII}&& error.cause.find(L"safe integer range") != std::wstring::npos
{III})
{II});
{I}}}

{I}REQUIRE_NOTHROW(our::jsonization::Serialize(*that));

{I}std::ostringstream oss;
{I}REQUIRE_NOTHROW(our::xmlization::Serialize(*that, {{}}, oss));
}}"""
        ),
    ]


def _generate_mutation(
    numeric_place: intermediate.NumericPlace, value_type: str, zero_literal: str
) -> Tuple[Stripped, str]:
    """
    Generate the code which sets ``value`` at the ``numeric_place`` of ``instance``.

    Return the code, and the path to the value.
    """
    setter_name = cpp_naming.setter_name(numeric_place.prop.name)

    if numeric_place.index is None:
        return (
            Stripped(f"instance->{setter_name}(value);"),
            f".{numeric_place.prop.name}",
        )

    expected_path = f".{numeric_place.prop.name}[{numeric_place.index}]"

    if numeric_place.in_list:
        # NOTE (mristin):
        # The value goes to the position indicated by the numeric place so that
        # a serializer which always reports the index 0 does not pass.
        items_joined = ",\n".join(
            "value" if i == numeric_place.index else zero_literal
            for i in range(numeric_place.index + 1)
        )

        return (
            Stripped(
                f"""\
instance->{setter_name}(
{I}std::vector<{value_type}>{{
{II}{indent_but_first_line(items_joined, II)}
{I}}}
);"""
            ),
            expected_path,
        )

    mutable_getter_name = cpp_naming.mutable_getter_name(numeric_place.prop.name)

    return (
        Stripped(
            f"""\
std::get<{numeric_place.index}>(
{I}instance->{mutable_getter_name}()
) = value;"""
        ),
        expected_path,
    )


@require(lambda numeric_place: numeric_place.a_type is intermediate.PrimitiveType.FLOAT)
def _generate_serialization_failure_test_case(
    numeric_place: intermediate.NumericPlace,
) -> Stripped:
    """Generate the test that a non-finite floating-point number is refused."""
    mutation, expected_path = _generate_mutation(
        numeric_place=numeric_place, value_type="double", zero_literal="0.0"
    )

    interface_name = cpp_naming.interface_name(numeric_place.cls.name)

    model_type = naming.json_model_type(numeric_place.cls.name)

    deserialization_function = cpp_naming.function_name(
        Identifier(f"{numeric_place.cls.name}_from")
    )

    return Stripped(
        f"""\
TEST_CASE(
{I}"Test the serialization failure on a non-finite floating-point number "
{I}"at {expected_path} of {model_type}"
) {{
{I}for (
{II}const double value
{II}: {{
{III}std::numeric_limits<double>::infinity(),
{III}-std::numeric_limits<double>::infinity(),
{III}std::numeric_limits<double>::quiet_NaN()
{II}}}
{I}) {{
{II}std::shared_ptr<our::types::{interface_name}> instance(
{III}MustDeserializeTheFirstExpected<our::types::{interface_name}>(
{IIII}{cpp_common.string_literal(model_type)},
{IIII}our::jsonization::{deserialization_function}
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


def _generate_safe_integer_test_case(
    cls: intermediate.ConcreteClass,
    mutation: Stripped,
    value_type: str,
    expected_path: str,
    expected_cause_prefix: str,
) -> Stripped:
    """
    Generate the test that a value outside the safe integer range is refused.

    The ``mutation`` sets ``value`` of the ``value_type`` in ``instance``.
    """
    interface_name = cpp_naming.interface_name(cls.name)

    model_type = naming.json_model_type(cls.name)

    deserialization_function = cpp_naming.function_name(Identifier(f"{cls.name}_from"))

    load_and_mutate = Stripped(
        f"""\
std::shared_ptr<our::types::{interface_name}> instance(
{I}MustDeserializeTheFirstExpected<our::types::{interface_name}>(
{II}{cpp_common.string_literal(model_type)},
{II}our::jsonization::{deserialization_function}
{I})
);

{mutation}"""
    )

    path_literal = cpp_common.string_literal(expected_path)

    return Stripped(
        f"""\
TEST_CASE(
{I}"Test the safe integer range at {expected_path} of {model_type}"
) {{
{I}for (
{II}const int64_t integer
{II}: {{9007199254740992LL, -9007199254740992LL}}
{I}) {{
{II}const {value_type} value(integer);

{II}{indent_but_first_line(load_and_mutate, II)}

{II}AssertReportedEverywhere(
{III}instance,
{III}{path_literal},
{III}our::common::Concat(
{IIII}{cpp_common.wstring_literal(expected_cause_prefix)},
{IIII}std::to_wstring(integer),
{IIII}L", which is outside the safe integer range [-2^53 + 1, 2^53 - 1]"
{III})
{II});
{I}}}

{I}for (
{II}const int64_t integer
{II}: {{9007199254740991LL, -9007199254740991LL}}
{I}) {{
{II}const {value_type} value(integer);

{II}{indent_but_first_line(load_and_mutate, II)}

{II}AssertNotReportedAnywhere(instance, {path_literal});
{I}}}
}}"""
    )


def _json_able_places(
    symbol_table: intermediate.SymbolTable,
) -> List[Tuple[intermediate.ConcreteClass, intermediate.Property]]:
    """
    List the required properties which hold a JSON-able value or array.

    An integer outside the safe integer range can sit in such a property.
    """
    return [
        (cls, prop)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
        if isinstance(
            prop.type_annotation,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
            ),
        )
    ]


def _generate_json_able_safe_integer_test_case(
    cls: intermediate.ConcreteClass, prop: intermediate.Property
) -> Stripped:
    """Generate the test that an integer of a JSON-able value is range-checked."""
    setter_name = cpp_naming.setter_name(prop.name)

    if isinstance(prop.type_annotation, intermediate.JsonArrayTypeAnnotation):
        # NOTE (mristin):
        # We put the integer at the index 1 so that a check which always reports
        # the index 0 does not pass.
        mutation = Stripped(
            f"""\
instance->{setter_name}(
{I}nlohmann::json::array({{nlohmann::json(0), value}})
);"""
        )
        expected_path = f".{prop.name}[1]"
    else:
        mutation = Stripped(f"instance->{setter_name}(value);")
        expected_path = f".{prop.name}"

    return _generate_safe_integer_test_case(
        cls=cls,
        mutation=mutation,
        value_type="nlohmann::json",
        expected_path=expected_path,
        expected_cause_prefix="Expected a JSON-able value, but got the integer ",
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

    float_places = [
        numeric_place
        for numeric_place in numeric_places
        if numeric_place.a_type is intermediate.PrimitiveType.FLOAT
    ]
    int_places = [
        numeric_place
        for numeric_place in numeric_places
        if numeric_place.a_type is intermediate.PrimitiveType.INT
    ]
    json_able_places = _json_able_places(symbol_table)

    checks_safe_integers = len(int_places) > 0 or len(json_able_places) > 0

    # NOTE (mristin):
    # Only the tests of the serialization failures need the limits of
    # the floating-point numbers.
    limits_include = "\n#include <limits>\n" if len(float_places) > 0 else ""

    # NOTE (mristin):
    # The tests of the safe integer range check the verification and the XML
    # serialization as well.
    safe_integer_includes = (
        f"""
#include <{include_prefix_path}/verification.hpp>
#include <{include_prefix_path}/xmlization.hpp>

#include <sstream>"""
        if checks_safe_integers
        else ""
    )

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common.hpp"
#include "./common_jsonization.hpp"

#include <{include_prefix_path}/jsonization.hpp>{safe_integer_includes}
{limits_include}
#include <catch2/catch.hpp>

namespace our = {library_namespace};"""
        ),
        Stripped(
            f"""\
template<class ClassT>
void AssertRoundTrip(
{I}const std::filesystem::path& path,
{I}std::function<
{II}our::common::expected<
{III}std::shared_ptr<ClassT>,
{III}our::jsonization::DeserializationError
{II}>(const nlohmann::json&, bool)
{I}> deserialization_function
) {{
{I}const nlohmann::json json = test::common::jsonization::MustReadJson(path);

{I}our::common::expected<
{II}std::shared_ptr<ClassT>,
{II}our::jsonization::DeserializationError
{I}> deserialized = deserialization_function(json, false);

{I}if (!deserialized.has_value()) {{
{II}INFO(
{III}our::common::Concat(
{IIII}"Failed to de-serialize from ",
{IIII}path.string(),
{IIII}": ",
{IIII}our::common::WstringToUtf8(
{IIIII}deserialized.error().path.ToWstring()
{IIII}),
{IIII}": ",
{IIII}our::common::WstringToUtf8(
{IIIII}deserialized.error().cause
{IIII})
{III})
{II})
{II}REQUIRE(deserialized.has_value());
{I}}}

{I}nlohmann::json another_json = our::jsonization::Serialize(
{II}*(deserialized.value())
{I});

{I}std::optional<std::string> diff_message = test::common::jsonization::CompareJsons(
{II}json,
{II}another_json
{I});
{I}if (diff_message.has_value()) {{
{II}INFO(
{III}our::common::Concat(
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
{II}our::common::expected<
{III}std::shared_ptr<ClassT>,
{III}our::jsonization::DeserializationError
{II}>(const nlohmann::json&, bool)
{I}> deserialization_function,
{I}const std::filesystem::path& error_path
) {{
{I}const nlohmann::json json = test::common::jsonization::MustReadJson(path);

{I}our::common::expected<
{II}std::shared_ptr<ClassT>,
{II}our::jsonization::DeserializationError
{I}> deserialized = deserialization_function(json, false);

{I}if (deserialized.has_value()) {{
{II}INFO(
{III}our::common::Concat(
{IIII}"Expected the de-serialization to fail on ",
{IIII}path.string(),
{IIII}", but the de-serialization succeeded"
{III})
{II})
{II}REQUIRE(!deserialized.has_value());
{I}}}

{I}test::common::AssertContentEqualsExpectedOrRecord(
{II}our::common::Concat(
{III}our::common::WstringToUtf8(
{IIII}deserialized.error().path.ToWstring()
{III}),
{III}": ",
{III}our::common::WstringToUtf8(
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
{I}static our::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "Json";
{I}}}

{I}return *result;
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineErrorDir() {{
{I}static our::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "JsonizationError";
{I}}}

{I}return *result;
}}"""
        ),
    ]

    if len(float_places) > 0 or checks_safe_integers:
        blocks.extend(_generate_serialization_failure_infrastructure())

    if checks_safe_integers:
        blocks.extend(_generate_safe_integer_infrastructure())

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
{III}our::types::{interface_name}
{II}>(path, our::jsonization::{deserialization_function});
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
{IIII}our::types::{interface_name}
{III}>(
{IIII}path,
{IIII}our::jsonization::{deserialization_function},
{IIII}error_path
{III});
{II}}}
{I}}}
}}"""
            )
        )

    for numeric_place in float_places:
        blocks.append(_generate_serialization_failure_test_case(numeric_place))

    for numeric_place in int_places:
        mutation, expected_path = _generate_mutation(
            numeric_place=numeric_place, value_type="int64_t", zero_literal="0LL"
        )
        blocks.append(
            _generate_safe_integer_test_case(
                cls=numeric_place.cls,
                mutation=mutation,
                value_type="int64_t",
                expected_path=expected_path,
                expected_cause_prefix="Expected an integer, but got ",
            )
        )

    for cls, prop in json_able_places:
        blocks.append(_generate_json_able_safe_integer_test_case(cls=cls, prop=prop))

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
