"""Generate code for common functionality shared across the tests."""

import io
import re

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
    Identifier,
)
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _library_namespace_to_upper_snake(
    library_namespace: Stripped,
) -> Identifier:
    """
    Convert a CamelCase dotted namespace into UPPER_SNAKE_CASE.

    >>> _library_namespace_to_upper_snake(Stripped("aas_core::aas_3_0"))
    'AAS_CORE_AAS_3_0'

    >>> _library_namespace_to_upper_snake(Stripped("SimpleTest"))
    'SIMPLE_TEST'

    >>> _library_namespace_to_upper_snake(Stripped("Already_Snake"))
    'ALREADY_SNAKE'
    """
    result = library_namespace.replace("::", "_")

    # Insert underscore between lowercase and uppercase (aasCore → aas_Core)
    result = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", result)

    return Identifier(result.upper())


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(library_namespace: Stripped) -> str:
    """Generate header for common functionality shared across the tests."""
    include_guard_var = cpp_common.include_guard_var(Stripped("test::common"))

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    environment_variable = _library_namespace_to_upper_snake(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        Stripped(
            f"""\
#include <{include_prefix_path}/types.hpp>"""
        ),
        Stripped(
            """\
#include <nlohmann/json.hpp>"""
        ),
        Stripped(
            """\
#include <deque>
#include <filesystem>"""
        ),
        Stripped(
            """\
/**
* Provide common functionalities shared across the tests.
*/
namespace test {
namespace common {"""
        ),
        Stripped(
            f"""\
/**
 * Set to true if we run tests in the record mode according to the environment
 * variable `{environment_variable}_TEST_RECORD_MODE`.
 *
 * \\remark It is tedious to record manually all the expected error messages. Therefore
 * we include this variable to steer the automatic recording. We intentionally
 * intertwine the recording code with the test code to keep them close to each other
 * so that they are easier to maintain.
 */
bool DetermineRecordMode();"""
        ),
        Stripped(
            f"""\
/**
 * Point to the directory with the test data according to the environment
 * variable `{environment_variable}_TEST_DATA_DIR`.
 */
std::filesystem::path DetermineTestDataDir();"""
        ),
        Stripped(
            f"""\
/**
 * Represent `that` instance as a human-readable line of an iteration trace.
 */
std::wstring TraceMark(
{I}const {library_namespace}::types::IClass& that
);"""
        ),
        Stripped(
            f"""\
/**
 * Find files beneath the `root` recursively which have the `suffix`.
 *
 * If the `root` does not exist, return an empty deque.
 *
 * If the `root` is not a directory, throw a runtime error.
 *
 * The files are sorted.
 */
std::deque<std::filesystem::path> FindFilesBySuffixRecursively(
{I}const std::filesystem::path& root,
{I}const std::string& suffix
);"""
        ),
        Stripped(
            f"""\
/**
 * List non-recursively the subdirectories contained in the \\p root.
 *
 * @param root directory that you want to list
 * @return subdirectories beneath \\p root, sorted
 */
std::deque<std::filesystem::path> ListSubdirectories(
{I}const std::filesystem::path& root
);"""
        ),
        Stripped(
            f"""\
/**
 * Check that the content coincides with the file or re-record if in record mode.
 */
void AssertContentEqualsExpectedOrRecord(
{I}const std::string& content,
{I}const std::filesystem::path& path
);"""
        ),
        Stripped(
            f"""\
template<typename T>
std::string JoinStrings(const T& container, const std::string& delimiter) {{
{I}static_assert(std::is_same<typename T::value_type, std::string>::value);

{I}// NOTE (mristin):
{I}// We have to handle the empty container explicitly, as the computations
{I}// below subtract one from its size, which would wrap around.
{I}if (container.empty()) {{
{II}return "";
{I}}}

{I}size_t size = 0;
{I}for (const std::string& part : container
{II}) {{
{II}size += part.size();
{I}}}
{I}size += delimiter.size() * (container.size() - 1);

{I}std::string result;
{I}result.reserve(size);

{I}auto it = container.begin();
{I}for (size_t i = 0; i < container.size() - 1; ++i) {{
{II}result.append(*it);
{II}result.append(delimiter);
{II}++it;
{I}}}

{I}result.append(*it);

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
template<typename T>
std::wstring JoinWstrings(const T& container, const std::wstring& delimiter) {{
{I}if (container.size() == 0) {{
{II}return L"";
{I}}}

{I}static_assert(std::is_same<typename T::value_type, std::wstring>::value);

{I}size_t size = 0;
{I}for (const std::wstring& part : container
{II}) {{
{II}size += part.size();
{I}}}
{I}size += delimiter.size() * (container.size() - 1);

{I}std::wstring result;
{I}result.reserve(size);

{I}auto it = container.begin();
{I}for (size_t i = 0; i < container.size() - 1; ++i) {{
{II}result.append(*it);
{II}result.append(delimiter);
{II}++it;
{I}}}

{I}result.append(*it);

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
std::string MustReadString(
{I}const std::filesystem::path& path
);"""
        ),
        Stripped(
            """\
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
    """Generate implementation for common functionality shared across the tests."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    environment_variable = _library_namespace_to_upper_snake(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            '''\
#include "./common.hpp"'''
        ),
        Stripped(
            f"""\
#include <{include_prefix_path}/stringification.hpp>
#include <{include_prefix_path}/wstringification.hpp>"""
        ),
        Stripped(
            """\
#include <catch2/catch.hpp>"""
        ),
        Stripped(
            """\
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <queue>
#include <set>
#include <stdexcept>
#include <type_traits>"""
        ),
        Stripped(
            f"""\
namespace our = {library_namespace};"""
        ),
        Stripped(
            """\
namespace fs = std::filesystem;"""
        ),
        Stripped(
            """\
namespace test {
namespace common {"""
        ),
        Stripped(
            f"""\
static std::optional<std::string> GetEnv(const char *variable_name) {{
{I}// NOTE (empwilli): MSVC complains about getenv being unsafe.
{I}// This should not be an issue as we don't run our tests in parallel, though,
{I}// so we use getenv_s in Windows. However, this function is a Microsoft
{I}// extension.
#ifdef _WIN32
{I}char buffer[256];
{I}size_t len;
{I}errno_t error = getenv_s(
{II}&len, buffer, sizeof(buffer), variable_name
{I});
{I}if (error != 0) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"The getenv_s returned an error code ",
{IIII}std::to_string(error),
{IIII}" when asking for the variable ",
{IIII}variable_name
{III})
{II});
{I}}}

{I}if (len == 0) {{
{II}return std::nullopt;
{I}}}

{I}if (buffer[len - 1] != 0) {{
{II}throw std::logic_error(
{III}our::common::Concat(
{IIII}"Expected the last byte of buffer for getenv_s on ",
{IIII}variable_name,
{IIII}" to be zero, but got ",
{IIII}std::to_string(static_cast<std::uint8_t>(buffer[len - 1]))
{III})
{II});
{I}}}

{I}return std::optional {{ std::string(buffer, len - 1) }};
#else
{I}auto value = getenv(variable_name);

{I}if (value == nullptr) {{
{II}return std::nullopt;
{I}}}

{I}return std::optional {{ std::string(value) }};
#endif
}}"""
        ),
        Stripped(
            f"""\
bool DetermineRecordMode() {{
{I}const char* variable_name = "{environment_variable}_TEST_RECORD_MODE";

{I}auto result = GetEnv(variable_name);

{I}if (!result.has_value())
{I}{{
{II}return false;
{I}}}

{I}static const std::set<std::string> hot_value_set{{
{II}"on", "ON", "On",
{II}"true", "TRUE", "True",
{II}"1",
{II}"yes", "Yes", "YES"
{I}}};
{I}return hot_value_set.find(result.value()) != hot_value_set.end();
}}"""
        ),
        Stripped(
            f"""\
std::filesystem::path DetermineTestDataDir() {{
{I}const char* variable_name = "{environment_variable}_TEST_DATA_DIR";

{I}auto result = GetEnv(variable_name);

{I}if (!result.has_value())
{I}{{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"The environment variable ",
{IIII}variable_name,
{IIII}" has not been set."
{III})
{II});
{I}}}

{I}return fs::path(result.value());
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write `text` to the given `path` encoded as UTF-8.
 */
void MustWriteWstringAsUtf8(
{I}const std::filesystem::path& path,
{I}const std::wstring& text
) {{
{I}std::ofstream ofs(path, std::ios::binary);

{I}const std::string encoded = our::common::WstringToUtf8(text);
{I}ofs.write(encoded.data(), encoded.size());

{I}if (ofs.fail()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to write to ",
{IIII}path.string(),
{IIII}"; the fail bit of the file stream is set"
{III})
{II});
{I}}}

{I}if (ofs.bad()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to write to ",
{IIII}path.string(),
{IIII}"; the bad bit of the file stream is set"
{III})
{II});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of the file `path` and decode it from UTF-8.
 */
std::wstring MustReadWstringAsUtf8(
{I}const std::filesystem::path& path
) {{
{I}std::ifstream ifs(path, std::ios::binary);
{I}ifs.seekg(0, std::ios::end);
{I}std::streamoff size = ifs.tellg();
{I}if (size < 0) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Unexpected negative size of ",
{IIII}path.string(),
{IIII}": ",
{IIII}std::to_string(size)
{III})
{II});
{I}}}

{I}std::string buffer(static_cast<size_t>(size), ' ');
{I}ifs.seekg(0);
{I}ifs.read(&buffer[0], size);

{I}if (ifs.fail()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to read from ",
{IIII}path.string(),
{IIII}"; the fail bit of the file stream is set"
{III})
{II});
{I}}}

{I}if (ifs.bad()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to read from ",
{IIII}path.string(),
{IIII}"; the bad bit of the file stream is set"
{III})
{II});
{I}}}

{I}try {{
{II}return our::common::Utf8ToWstring(buffer);
{I}}} catch (const std::exception& exception) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to de-code ",
{IIII}path.string(),
{IIII}" as UTF-8: ",
{IIII}exception.what()
{III})
{II});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write `text` to the given `path` as binary.
 */
void MustWriteString(
{I}const std::filesystem::path& path,
{I}const std::string& text
) {{
{I}std::ofstream ofs(path, std::ios::binary);

{I}ofs.write(text.data(), text.size());

{I}if (ofs.fail()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to write to ",
{IIII}path.string(),
{IIII}"; the fail bit of the file stream is set"
{III})
{II});
{I}}}

{I}if (ofs.bad()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to write to ",
{IIII}path.string(),
{IIII}"; the bad bit of the file stream is set"
{III})
{II});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of the file `path` as binary.
 */
std::string MustReadString(
{I}const std::filesystem::path& path
) {{
{I}std::ifstream ifs(path, std::ios::binary);
{I}ifs.seekg(0, std::ios::end);
{I}std::streamoff size = ifs.tellg();
{I}if (size < 0) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Unexpected negative size of ",
{IIII}path.string(),
{IIII}": ",
{IIII}std::to_string(size)
{III})
{II});
{I}}}

{I}std::string buffer(static_cast<size_t>(size), ' ');
{I}ifs.seekg(0);
{I}ifs.read(&buffer[0], size);

{I}if (ifs.fail()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to read from ",
{IIII}path.string(),
{IIII}"; the fail bit of the file stream is set"
{III})
{II});
{I}}}

{I}if (ifs.bad()) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to read from ",
{IIII}path.string(),
{IIII}"; the bad bit of the file stream is set"
{III})
{II});
{I}}}

{I}return buffer;
}}"""
        ),
        Stripped(
            f"""\
std::wstring TraceMark(
{I}const {library_namespace}::types::IClass& that
) {{
{I}const std::wstring model_type = our::wstringification::to_wstring(
{II}that.model_type()
{I});
{I}return model_type;
}}"""
        ),
        Stripped(
            f"""\
bool StringEndsWith(
{I}const std::string& text,
{I}const std::string& suffix
) {{
{I}if (text.size() < suffix.size()) {{
{II}return false;
{I}}}

{I}return (
{II}text.substr(text.size() - suffix.size(), suffix.size())
{III}== suffix
{I});
}}"""
        ),
        Stripped(
            f"""\
std::deque<std::filesystem::path> FindFilesBySuffixRecursively(
{I}const std::filesystem::path& root,
{I}const std::string& suffix
) {{
{I}if (!fs::exists(root)) {{
{II}return std::deque<std::filesystem::path>();
{I}}}

{I}if (!fs::is_directory(root)) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Expected to search for files with suffix recursively in ",
{IIII}root.string(),
{IIII}", but it is not a directory"
{III})
{II});
{I}}}

{I}std::deque<fs::path> result;

{I}for (
{II}const fs::directory_entry& entry
{II}: fs::recursive_directory_iterator(root)
{II}) {{
{II}if (
{III}StringEndsWith(
{IIII}entry.path().filename().string(),
{IIII}suffix
{III})
{III}) {{
{III}result.push_back(entry.path());
{II}}}
{I}}}

{I}std::sort(result.begin(), result.end());

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
std::deque<std::filesystem::path> ListSubdirectories(
{I}const std::filesystem::path& root
) {{
{I}if (!fs::exists(root)) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"The root directory which you wanted to list for subdirectories "
{IIII}"does not exist: ",
{IIII}root.string()
{III})
{II});
{I}}}

{I}if (!fs::is_directory(root)) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"The path that you specified as a root directory which you wanted to "
{IIII}"list for subdirectories is not a directory: ",
{IIII}root.string()
{III})
{II});
{I}}}

{I}std::deque<fs::path> result;

{I}for (
{II}const fs::directory_entry& entry
{II}: fs::directory_iterator(root)
{II}) {{
{II}if (fs::is_directory(entry.path())) {{
{III}result.push_back(entry.path());
{II}}}
{I}}}

{I}std::sort(result.begin(), result.end());
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
void AssertContentEqualsExpectedOrRecord(
{I}const std::string& content,
{I}const std::filesystem::path& path
) {{
{I}const bool record_mode = DetermineRecordMode();
{I}if (record_mode) {{
{II}fs::create_directories(path.parent_path());

{II}MustWriteString(path, content);
{I}}} else {{
{II}INFO(
{III}our::common::Concat(
{IIII}"Expected to compare the content against "
{IIII}"the recorded file: ",
{IIII}path.string(),
{IIII}", but the file does not exist. If you want to re-record, "
{IIII}"please set the environment variable {environment_variable}_TEST_RECORD_MODE "
{IIII}"to 'ON'"
{III})
{II})
{II}REQUIRE(std::filesystem::exists(path));

{II}const std::string expected = MustReadString(path);
{II}INFO(
{III}our::common::Concat(
{IIII}"Got unexpected content, which should have been equal "
{IIII}"to the content of the file: ",
{IIII}path.string()
{III})
{II})
{II}REQUIRE(content == expected);
{I}}}
}}"""
        ),
        Stripped(
            """\
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
