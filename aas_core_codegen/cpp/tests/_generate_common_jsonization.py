# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code for common JSON de/serialization shared across the tests."""

import io

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(library_namespace: Stripped) -> str:
    """Generate header for common JSON de/serialization shared across the tests."""
    include_guard_var = cpp_common.include_guard_var(
        Stripped("test::common::jsonization")
    )

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
/**
 * Provide methods which are used throughout the jsonization tests.
 */
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        Stripped(
            """\
#include <nlohmann/json.hpp>"""
        ),
        Stripped(
            """\
#include <optional>
#include <vector>
#include <string>"""
        ),
        Stripped(
            """\
namespace test {
namespace common {
namespace jsonization {"""
        ),
        Stripped(
            """\
/**
 * Read the content of the `path` and parse it as JSON.
 */
nlohmann::json MustReadJson(const std::filesystem::path& path);"""
        ),
        Stripped(
            f"""\
/**
 * Compare two JSON values.
 *
 * Return the JSON patch, if there is any difference.
 */
std::optional<std::string> CompareJsons(
{I}const nlohmann::json& that,
{I}const nlohmann::json& other
);"""
        ),
        Stripped(
            """\
}  // namespace jsonization
}  // namespace common
}  // namespace test"""
        ),
        Stripped(
            f"""\
#endif  // {include_guard_var}"""
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


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(library_namespace: Stripped) -> str:
    """Generate implementation for common JSON de/serialization shared across the tests."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            '''\
#include "./common_jsonization.hpp"'''
        ),
        Stripped(
            f"""\
#include <{include_prefix_path}/common.hpp>"""
        ),
        Stripped(
            """\
#include <fstream>"""
        ),
        Stripped(
            f"""\
namespace our = {library_namespace};"""
        ),
        Stripped(
            """\
namespace test {
namespace common {
namespace jsonization {"""
        ),
        Stripped(
            f"""\
nlohmann::json MustReadJson(const std::filesystem::path& path) {{
{I}std::ifstream ifs(path);

{I}nlohmann::json result;
{I}try {{
{II}result = nlohmann::json::parse(ifs);
{I}}} catch (nlohmann::json::parse_error& exception) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to read JSON from ",
{IIII}path.string(),
{IIII}": ",
{IIII}exception.what()
{III})
{II});
{I}}}

{I}if (ifs.bad()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to read JSON from ",
{IIII}path.string(),
{IIII}"; the bad bit of the file stream is set"
{III})
{II});
{I}}}

{I}if (ifs.fail()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to read JSON from ",
{IIII}path.string(),
{IIII}"; the fail bit of the file stream is set"
{III})
{II});
{I}}}

{I}if (!ifs.eof()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to read JSON from ",
{IIII}path.string(),
{IIII}"; the EOF bit is not set meaning that we did not parse all the content"
{III})
{II});
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
std::optional<std::string> CompareJsons(
{I}const nlohmann::json& that,
{I}const nlohmann::json& other
) {{
{I}const nlohmann::json patch = nlohmann::json::diff(that, other);

{I}if (!patch.is_array()) {{
{II}throw std::logic_error(
{III}our::common::Concat(
{IIII}"Expected the patch to be an array, but got ",
{IIII}patch.type_name()
{III})
{II});
{I}}}

{I}if (patch.size() != 0) {{
{II}return nlohmann::to_string(patch);
{I}}}

{I}return std::nullopt;
}}"""
        ),
        Stripped(
            """\
}  // namespace jsonization
}  // namespace common
}  // namespace test"""
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


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
