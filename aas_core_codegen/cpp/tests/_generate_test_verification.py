"""Generate code to test the verification of pos. and neg. cases."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


def _generate_safe_integer_predicate_test() -> Stripped:
    """Generate the test of the predicates of the safe integer range."""
    return Stripped(
        f"""\
TEST_CASE("Test the predicates of the safe integer range") {{
{I}for (
{II}const int64_t value
{II}: {{9007199254740991LL, -9007199254740991LL, 0LL}}
{I}) {{
{II}REQUIRE(our::common::IsSafeInteger(value));
{I}}}

{I}for (
{II}const int64_t value
{II}: {{
{III}int64_t(9007199254740992LL),
{III}int64_t(-9007199254740992LL),
{III}std::numeric_limits<int64_t>::max(),
{III}std::numeric_limits<int64_t>::min()
{II}}}
{I}) {{
{II}REQUIRE(!our::common::IsSafeInteger(value));
{I}}}

{I}REQUIRE(our::common::IsSafeInteger(uint64_t(9007199254740991ULL)));
{I}REQUIRE(!our::common::IsSafeInteger(uint64_t(9007199254740992ULL)));
{I}REQUIRE(
{II}!our::common::IsSafeInteger(
{III}std::numeric_limits<uint64_t>::max()
{II})
{I});

{I}for (
{II}const double value
{II}: {{9007199254740991.0, -9007199254740991.0, 0.0}}
{I}) {{
{II}REQUIRE(our::common::IsSafeInteger(value));
{I}}}

{I}for (
{II}const double value
{II}: {{
{III}9007199254740992.0,
{III}-9007199254740992.0,
{III}std::numeric_limits<double>::infinity(),
{III}-std::numeric_limits<double>::infinity(),
{III}std::numeric_limits<double>::quiet_NaN()
{II}}}
{I}) {{
{II}REQUIRE(!our::common::IsSafeInteger(value));
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
    """Generate implementation to test the verification of pos. and neg. cases."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    # NOTE (mristin):
    # Only the test of the safe integer range needs the limits.
    limits_include = (
        "\n#include <limits>"
        if intermediate_uses.safe_integer_checks(symbol_table)
        else ""
    )

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common.hpp"
#include "./common_xmlization.hpp"

#include <{include_prefix_path}/verification.hpp>
#include <{include_prefix_path}/xmlization.hpp>

#include <catch2/catch.hpp>

#include <fstream>{limits_include}

namespace our = {library_namespace};"""
        ),
        Stripped(
            f"""\
void AssertNoVerificationError(
{I}const std::filesystem::path& xml_path
) {{
{I}std::shared_ptr<
{II}our::types::IClass
{I}> instance(
{II}test::common::xmlization::MustDeserializeFile(xml_path)
{I});

{I}std::vector<std::string> error_messages;
{I}for (
{II}const our::verification::Error &error
{II}: our::verification::RecursiveVerification(instance)
{I}) {{
{II}error_messages.emplace_back(
{III}our::common::Concat(
{IIII}our::common::WstringToUtf8(error.path.ToWstring()),
{IIII}": ",
{IIII}our::common::WstringToUtf8(error.cause)
{III})
{II});
{I}}}

{I}if (!error_messages.empty()) {{
{II}std::vector<std::string> parts;
{II}parts.emplace_back("Expected no error messages from ");
{II}parts.emplace_back(xml_path.string());
{II}parts.emplace_back(", but got:\\n");
{II}parts.emplace_back(test::common::JoinStrings(error_messages, "\\n"));

{II}INFO(test::common::JoinStrings(parts, ""))
{II}CHECK(error_messages.empty());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineXmlDir() {{
{I}static our::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "Xml";
{I}}}

{I}return *result;
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineErrorDir() {{
{I}static our::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "VerificationError";
{I}}}

{I}return *result;
}}"""
        ),
        Stripped(
            f"""\
void AssertVerificationFailure(
{I}const std::filesystem::path& path,
{I}const std::filesystem::path& error_path
) {{
{I}std::ifstream ifs(path, std::ios::binary);

{I}our::common::expected<
{II}std::shared_ptr<our::types::IClass>,
{II}our::xmlization::DeserializationError
{I}> deserialized = our::xmlization::From(
{II}ifs
{I});

{I}if (!deserialized.has_value()) {{
{II}INFO(
{III}our::common::Concat(
{IIII}"Expected to de-serialize ",
{IIII}path.string(),
{IIII}", but the de-serialization failed: ",
{IIII}our::common::WstringToUtf8(deserialized.error().path.ToWstring()),
{IIII}our::common::WstringToUtf8(deserialized.error().cause)
{III})
{II})
{II}REQUIRE(!deserialized.has_value());
{I}}}

{I}std::vector<std::string> error_messages;
{I}for (
{II}const our::verification::Error& error
{II}: our::verification::RecursiveVerification(deserialized.value())
{II}) {{
{II}error_messages.emplace_back(
{III}our::common::Concat(
{IIII}our::common::WstringToUtf8(error.path.ToWstring()),
{IIII}": ",
{IIII}our::common::WstringToUtf8(error.cause)
{III})
{II});
{I}}}

{I}if (error_messages.empty()) {{
{II}INFO(
{III}our::common::Concat(
{IIII}"Expected error messages from ",
{IIII}path.string(),
{IIII}", but got none"
{III})
{II})
{II}REQUIRE(!error_messages.empty());
{I}}}

{I}const std::string joined_error_messages = test::common::JoinStrings(
{II}error_messages,
{II}"\\n"
{I});

{I}test::common::AssertContentEqualsExpectedOrRecord(
{II}joined_error_messages,
{II}error_path
{I});
}}"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        xml_class_name = naming.xml_class_name(concrete_cls.name)

        cls_name = cpp_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test verification of a valid {cls_name}") {{
{I}const std::deque<std::filesystem::path> paths(
{II}test::common::FindFilesBySuffixRecursively(
{III}DetermineXmlDir()
{IIII}/ "Expected"
{IIII}/ {cpp_common.string_literal(xml_class_name)},
{III}".xml"
{II})
{I});

{I}for (const std::filesystem::path& path : paths) {{
{II}AssertNoVerificationError(path);
{I}}}
}}"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test verification of invalid cases for {cls_name}") {{
{I}for (
{II}const std::filesystem::path& causeDir
{II}: test::common::ListSubdirectories(
{III}DetermineXmlDir()
{IIII}/ "Unexpected"
{IIII}/ "Invalid"
{II})
{I}) {{
{II}for (
{III}const std::filesystem::path& path
{III}: test::common::FindFilesBySuffixRecursively(
{IIII}causeDir / {cpp_common.string_literal(xml_class_name)},
{IIII}".xml"
{III})
{II}) {{
{III}const std::filesystem::path parent(
{IIII}(
{IIIII}DetermineErrorDir()
{IIIIII}/ std::filesystem::relative(path, DetermineXmlDir())
{IIII}).parent_path()
{III});

{III}const std::filesystem::path error_path(
{IIII}parent
{IIIII}/ (path.filename().string() + ".errors")
{III});

{III}AssertVerificationFailure(path, error_path);
{II}}}
{I}}}
}}"""
            )
        )

    if intermediate_uses.safe_integer_checks(symbol_table):
        blocks.append(_generate_safe_integer_predicate_test())

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
