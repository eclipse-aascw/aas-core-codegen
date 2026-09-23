"""Generate code of common functionality."""

# pylint: disable=line-too-long

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.cpp import (
    common as cpp_common,
)
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_concatenate_definitions_for_2_parts_and_above() -> List[Stripped]:
    """
    Generate the definition of ``concat`` functions.

    >>> print(_generate_concatenate_definitions_for_2_parts_and_above()[0])
    /**
     * Concatenate 2 strings.
     *
     * \\param part0 1st part of the concatenation
     * \\param part1 2nd part of the concatenation
     * \\return a concatenation of the 2 parts
     */
    std::string Concat(
      const std::string& part0,
      const std::string& part1
    );
    """
    concat_funcs = []  # type: List[Stripped]
    for string_type in ["std::string", "std::wstring"]:
        for count in range(2, 65):
            param_descriptions = []  # type: List[str]
            for i in range(0, count):
                ordinal: str

                ordinal_i = i + 1

                if ordinal_i % 10 == 1:
                    ordinal = f"{ordinal_i}st"
                elif ordinal_i % 10 == 2:
                    ordinal = f"{ordinal_i}nd"
                elif ordinal_i % 10 == 3:
                    ordinal = f"{ordinal_i}rd"
                else:
                    ordinal = f"{ordinal_i}th"

                param_descriptions.append(
                    f" * \\param part{i} {ordinal} part of the concatenation"
                )
            param_description_joined = "\n".join(param_descriptions)

            args_definition = ",\n".join(
                f"{I}const {string_type}& part{i}" for i in range(0, count)
            )

            concat_funcs.append(
                Stripped(
                    f"""\
/**
 * Concatenate {count} strings.
 *
{param_description_joined}
 * \\return a concatenation of the {count} parts
 */
{string_type} Concat(
{args_definition}
);"""
                )
            )

    return concat_funcs


def _generate_concatenate_implementations_for_2_parts_and_above() -> List[Stripped]:
    """
    Generate the implementation of ``concat`` functions.

    >>> print(_generate_concatenate_implementations_for_2_parts_and_above()[0])
    std::string Concat(
      const std::string& part0,
      const std::string& part1
    ) {
      size_t size = 0;
      size += part0.size();
      size += part1.size();
    <BLANKLINE>
      std::string result;
      result.reserve(size);
    <BLANKLINE>
      result.append(part0);
      result.append(part1);
    <BLANKLINE>
      return result;
    }
    """
    concat_funcs = []  # type: List[Stripped]
    for string_type in ["std::string", "std::wstring"]:
        for count in range(2, 65):
            args_definition = ",\n".join(
                f"{I}const {string_type}& part{i}" for i in range(0, count)
            )

            size_block = Stripped(
                "\n".join(f"size += part{i}.size();" for i in range(0, count))
            )

            append_block = Stripped(
                "\n".join(f"result.append(part{i});" for i in range(0, count))
            )

            concat_funcs.append(
                Stripped(
                    f"""\
{string_type} Concat(
{args_definition}
) {{
{I}size_t size = 0;
{I}{indent_but_first_line(size_block, I)}

{I}{string_type} result;
{I}result.reserve(size);

{I}{indent_but_first_line(append_block, I)}

{I}return result;
}}"""
                )
            )

    return concat_funcs


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate header of common functionality."""
    namespace = Stripped(f"{library_namespace}")

    include_guard_var = cpp_common.include_guard_var(namespace)

    make_uniques = [
        Stripped(
            f"""\
template<typename T>
std::unique_ptr<T> make_unique() {{
{I}return std::unique_ptr<T>(
{II}new T()
{I});
}}"""
        )
    ]  # type: List[Stripped]
    for i in range(1, 16):
        typenames_joined = ",\n".join(
            ["typename T"] + [f"typename A{j + 1}" for j in range(i)]
        )

        args_joined = ",\n".join(f"A{j + 1}&& a{j + 1}" for j in range(i))

        forward_args_joined = ",\n".join(
            f"std::forward<A{j + 1}>(a{j + 1})" for j in range(i)
        )

        make_uniques.append(
            Stripped(
                f"""\
template<
{I}{indent_but_first_line(typenames_joined, I)}
>
std::unique_ptr<T> make_unique(
{I}{indent_but_first_line(args_joined, I)}
) {{
{I}return std::unique_ptr<T>(
{II}new T(
{III}{indent_but_first_line(forward_args_joined, III)}
{II})
{I});
}}"""
            )
        )

    make_uniques_joined = "\n\n".join(make_uniques)

    blocks = [
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        cpp_common.WARNING,
        Stripped(
            """\
#pragma warning(push, 0)
#include <algorithm>
#include <functional>
#include <memory>
#include <sstream>
#include <string>
#include <utility>
#pragma warning(pop)

// NOTE (mristin):
// See: https://stackoverflow.com/questions/2324658/how-to-determine-the-version-of-the-c-standard-used-by-the-compiler
#if ((defined(_MSVC_LANG) && _MSVC_LANG >= 201703L) || __cplusplus >= 201703L)
// NOTE (mristin):
// Standard library provides std::optional in C++17 and above.
#pragma warning(push, 0)
#include <optional>
#pragma warning(pop)
#else
// NOTE (mristin):
// We rely on https://github.com/TartanLlama/optional for optional structure.
#pragma warning(push, 0)
#include <tl/optional.hpp>
#pragma warning(pop)
#endif

// NOTE (mristin):
// We check for the version above C++20 as there is no C++23 literal yet, and
// std::expected is available only in C++23.
// See: https://stackoverflow.com/questions/2324658/how-to-determine-the-version-of-the-c-standard-used-by-the-compiler
// and: http://eel.is/c++draft/cpp.predefined#1.1
#if ((defined(_MSVC_LANG) && _MSVC_LANG > 202002L) || __cplusplus > 202002L)
// Standard library provides std::expected in C++23 and above.
#pragma warning(push, 0)
#include <expected>
#pragma warning(pop)
#else
// NOTE (mristin):
// We rely on https://github.com/TartanLlama/expected for expected structure.
#pragma warning(push, 0)
#include <tl/expected.hpp>
#pragma warning(pop)
#endif"""
        ),
    ]  # type: List[Stripped]

    # NOTE (mristin):
    # Only the named unions need a variant, so we do not burden the users of
    # the other meta-models with an additional dependency in C++11 and C++14.
    uses_variant = len(symbol_table.named_unions) > 0

    if uses_variant:
        blocks.append(
            Stripped(
                """\
// NOTE (mristin):
// See: https://stackoverflow.com/questions/2324658/how-to-determine-the-version-of-the-c-standard-used-by-the-compiler
#if ((defined(_MSVC_LANG) && _MSVC_LANG >= 201703L) || __cplusplus >= 201703L)
// NOTE (mristin):
// Standard library provides std::variant in C++17 and above.
#pragma warning(push, 0)
#include <variant>
#pragma warning(pop)
#else
// NOTE (mristin):
// We rely on https://github.com/mpark/variant for variant structure.
#pragma warning(push, 0)
#include <mpark/variant.hpp>
#pragma warning(pop)
#endif"""
            )
        )

    variant_aliases = (
        [
            Stripped(
                """\
// Please keep in sync with the preprocessing directives above in the include block.
#if ((defined(_MSVC_LANG) && _MSVC_LANG >= 201703L) || __cplusplus >= 201703L)
using std::variant;
using std::get;
#else
using mpark::variant;
using mpark::get;
#endif"""
            )
        ]
        if uses_variant
        else []
    )  # type: List[Stripped]

    blocks.extend(
        [
            cpp_common.generate_namespace_opening(library_namespace),
            Stripped(
                f"""\
/**
 * \\defgroup common Common functionality used throughout the library
 * @{{
 */
namespace {cpp_common.COMMON_NAMESPACE} {{"""
            ),
            Stripped(
                """\
// Please keep in sync with the preprocessing directives above in the include block.
#if ((defined(_MSVC_LANG) && _MSVC_LANG >= 201703L) || __cplusplus >= 201703L)
// Standard library provides std::optional in C++17 and above.
using std::optional;
using std::nullopt;
using std::make_optional;
#else
using tl::optional;
using tl::nullopt;
using tl::make_optional;
#endif"""
            ),
            Stripped(
                """\
// Please keep in sync with the preprocessing directives above in the include block.
#if ((defined(_MSVC_LANG) && _MSVC_LANG > 202002L) || __cplusplus > 202002L)
using std::expected;
using std::unexpected;
using std::make_unexpected;
#else
using tl::expected;
using tl::unexpected;
using tl::make_unexpected;
#endif"""
            ),
            *variant_aliases,
            Stripped(
                f"""\
// Please keep in sync with the preprocessing directives above in the include block.
// Standard library provides std::make_unique in C++14 and above.
#if ((defined(_MSVC_LANG) && _MSVC_LANG >= 201402L) || __cplusplus >= 201402L)
using std::make_unique;
#else
// Inspired by:
// https://stackoverflow.com/questions/12547983/is-there-a-way-to-write-make-unique-in-vs2012
{make_uniques_joined}
#endif"""
            ),
            *_generate_concatenate_definitions_for_2_parts_and_above(),
            Stripped(
                f"""\
/**
 * Check if all the elements satisfy the \\p condition.
 *
 * \\param condition returning a boolean to be checked for each element
 * \\param container to be iterated through
 * \\return `true` if all the elements of \\p container satisfy the \\p condition
 */
template<typename ContainerT, typename FunctorT>
bool All(
{I}FunctorT condition,
{I}const ContainerT& container
) {{
{I}for (const auto& item : container ) {{
{II}if (!condition(item)) {{
{III}return false;
{II}}}
{I}}}
{I}return true;
}}"""
            ),
            Stripped(
                f"""\
/**
 * Check if any of the elements satisfy the \\p condition.
 *
 * \\param condition returning a boolean to be checked for each element
 * \\param container to be iterated through
 * \\return `true` if any of the elements of \\p container satisfy the \\p condition
 */
template<typename ContainerT, typename FunctorT>
bool Some(
{I}FunctorT condition,
{I}const ContainerT& container
) {{
{I}for (const auto& item : container ) {{
{II}if (condition(item)) {{
{III}return true;
{II}}}
{I}}}
{I}return false;
}}"""
            ),
            Stripped(
                f"""\
/**
 * Check if all the numbers in the range `[start, end)` satisfy the \\p condition.
 *
 * \\param condition returning a boolean to be checked for each number
 * \\param start of the range
 * \\param end of the range
 * \\return \\parblock
 * `true` if all the numbers between \\p start and \\p end (excluded)
 * satisfy the \\p condition
 * \\endparblock
 */
template<typename FunctorT>
bool AllRange(
{I}FunctorT condition,
{I}size_t start,
{I}size_t end
) {{
{I}for (size_t i = start; i < end; ++i) {{
{II}if (!condition(i)) {{
{III}return false;
{II}}}
{I}}}
{I}return true;
}}"""
            ),
            Stripped(
                f"""\
/**
 * Check if any number in the range `[start, end)` satisfy the \\p condition.
 *
 * \\param condition returning a boolean to be checked for each number
 * \\param start of the range
 * \\param end of the range
 * \\return \\parblock
 * `true` if any number between \\p start and
 * \\p end (excluded) satisfy the \\p condition
 * \\endparblock
 */
template<typename FunctorT>
bool SomeRange(
{I}FunctorT condition,
{I}size_t start,
{I}size_t end
) {{
{I}for (size_t i = start; i < end; ++i) {{
{II}if (condition(i)) {{
{III}return true;
{II}}}
{I}}}
{I}return false;
}}"""
            ),
            Stripped(
                f"""\
/**
 * Check if the \\p container contains the \\p value.
 *
 * \\param container to be searched through
 * \\param value to be search for
 * \\return `true` if \\p value is in the \\p container
 */
template<typename ContainerT, typename ValueT>
bool Contains(
{I}const ContainerT& container,
{I}const ValueT& value
) {{
{I}const auto container_begin = std::begin(container);
{I}const auto container_end = std::end(container);
{I}return std::find(
{II}container_begin,
{II}container_end,
{II}value
{I}) != container_end;
}}"""
            ),
            Stripped(
                """\
/**
 * Convert platform-independent the wide string to a UTF-8 string.
 *
 * \\param text to be converted
 * \\return UTF-8 encoded \\p text
 */
std::string WstringToUtf8(const std::wstring& text);"""
            ),
            Stripped(
                f"""\
/**
 * Convert platform-independent the UTF-8 encoded string to a wide string.
 *
 * \\param utf8_text UTF-8 encoded text to be converted
 * \\param utf8_text_size size of the text to be converted. If std::string::npos,
 * the \\p utf8_text is assumed to be null-terminated and the size is determined
 * using `strlen`.
 * \\return the wide-string representation
 */
std::wstring Utf8ToWstring(
{I}const char* utf8_text,
{I}size_t utf8_text_size = std::string::npos
);"""
            ),
            Stripped(
                """\
/**
 * Convert platform-independent the UTF-8 encoded string to a wide string.
 *
 * \\param utf8_text UTF-8 encoded text to be converted
 * \\return wide string
 */
std::wstring Utf8ToWstring(const std::string& utf8_text);"""
            ),
            Stripped(
                f"""\
}}  // namespace {cpp_common.COMMON_NAMESPACE}
/**@}}*/"""
            ),
            cpp_common.generate_namespace_closing(library_namespace),
            cpp_common.WARNING,
            Stripped(f"#endif  // {include_guard_var}"),
        ]
    )

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
    """Generate implementation of common functionality."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.COMMON_NAMESPACE}")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f'''\
#include "{include_prefix_path}/common.hpp"'''
        ),
        Stripped(
            """\
#pragma warning(push, 0)
#include <algorithm>
#pragma warning(pop)

// NOTE (mristin):
// We use MultiByteToWideChar and WideCharToMulitByte from <windows.h> on Windows
// as std::codecvt is not robust enough on Windows, and produces invalid UTF-16
// sequences as std::wstring. See:
// https://stackoverflow.com/questions/2573834/c-convert-string-or-char-to-wstring-or-wchar-t,
// especially the comment:
// https://stackoverflow.com/questions/2573834/c-convert-string-or-char-to-wstring-or-wchar-t#comment110447503_18597384
#ifdef _WIN32
#pragma warning(push, 0)
#include <windows.h>
#include <limits>
#include <cstring>
#pragma warning(pop)
#else
// NOTE (mristin):
// We use codecvt although it has been deprecated. There has been not
// suitable replacement proposed yet, so we simply stick to it
// until there is. See:
// https://stackoverflow.com/questions/42946335/deprecated-header-codecvt-replacement

#pragma warning(push, 0)
#include <codecvt>
#include <locale>
#pragma warning(pop)
#endif"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        *_generate_concatenate_implementations_for_2_parts_and_above(),
        Stripped(
            f"""\
std::string WstringToUtf8(const std::wstring& text) {{
{I}#ifdef _WIN32
{I}// Inspired by:
{I}// https://stackoverflow.com/a/69410299/1600678

{I}if (text.empty()) {{
{II}return "";
{I}}}

{I}// NOTE (mristin):
{I}// We put `max` into parentheses to avoid conflicts with
{I}// <windows.h> `max` macro, see:
{I}// https://stackoverflow.com/questions/11544073/how-do-i-deal-with-the-max-macro-in-windows-h-colliding-with-max-in-std

{I}const size_t text_size = text.size();
{I}if (
{II}text_size
{II}> static_cast<size_t>(
{III}(std::numeric_limits<int>::max)()
{II})
{I}) {{
{II}throw std::out_of_range(
{III}common::Concat(
{IIII}"The size of the text to be converted to UTF-8, ",
{IIII}std::to_string(text_size),
{IIII}", exceeds the maximum int value ",
{IIII}std::to_string((std::numeric_limits<int>::max)())
{III})
{II});
{I}}}
{I}const int text_size_int = static_cast<int>(text_size);

{I}const auto size_needed = WideCharToMultiByte(
{II}CP_UTF8,
{II}0,
{II}&(text[0]),
{II}text_size_int,
{II}nullptr,
{II}0,
{II}nullptr,
{II}nullptr
{I});

{I}if (size_needed <= 0) {{
{II}throw std::runtime_error(
{III}"WideCharToMultiByte() failed: " + std::to_string(size_needed)
{II});
{I}}}

{I}std::string result(size_needed, 0);

{I}WideCharToMultiByte(
{II}CP_UTF8,
{II}0,
{II}&(text[0]),
{II}text_size_int,
{II}&(result[0]),
{II}size_needed,
{II}nullptr,
{II}nullptr
{I});

{I}return result;
{I}#else
{I}// NOTE (mristin):
{I}// We use codecvt although it has been deprecated. There has been not
{I}// suitable replacement proposed yet, so we simply stick to it
{I}// until there is. See:
{I}// https://stackoverflow.com/questions/42946335/deprecated-header-codecvt-replacement

{I}std::wstring_convert<std::codecvt_utf8<wchar_t> > conv;
{I}return conv.to_bytes(text.data());
{I}#endif
}}"""
        ),
        Stripped(
            f"""\
std::wstring Utf8ToWstring(
{I}const char* utf8_text,
{I}size_t utf8_text_size
) {{
{I}if (utf8_text_size == 0) {{
{II}return std::wstring();
{I}}}

{I}#ifdef _WIN32
{I}// NOTE (mristin):
{I}// We have to use MultiByteToWideChar from <windows.h> on Windows
{I}// as std::codecvt is not robust enough on Windows and produces invalid UTF-16
{I}// sequences as std::wstring. See:
{I}// https://stackoverflow.com/questions/2573834/c-convert-string-or-char-to-wstring-or-wchar-t,
{I}// especially the comment:
{I}// https://stackoverflow.com/questions/2573834/c-convert-string-or-char-to-wstring-or-wchar-t#comment110447503_18597384

{I}// Inspired by:
{I}// https://stackoverflow.com/a/69410299/1600678

{I}if (utf8_text_size == std::string::npos) {{
{II}utf8_text_size = strlen(utf8_text);
{I}}}

{I}// NOTE (mristin):
{I}// We put `max` into parentheses to avoid conflicts with
{I}// <windows.h> `max` macro, see:
{I}// https://stackoverflow.com/questions/11544073/how-do-i-deal-with-the-max-macro-in-windows-h-colliding-with-max-in-std

{I}if (
{II}utf8_text_size
{II}> static_cast<size_t>(
{III}(std::numeric_limits<int>::max)()
{II})
{I}) {{
{II}throw std::out_of_range(
{III}common::Concat(
{IIII}"The size of the UTF-8 text to be converted to wide string, ",
{IIII}std::to_string(utf8_text_size),
{IIII}", exceeds the maximum int value ",
{IIII}std::to_string((std::numeric_limits<int>::max)())
{III})
{II});
{I}}}
{I}const int utf8_text_size_int = static_cast<int>(utf8_text_size);

{I}const auto size_needed = MultiByteToWideChar(
{II}CP_UTF8,
{II}0,
{II}utf8_text,
{II}utf8_text_size_int,
{II}nullptr,
{II}0
{I});
{I}if (size_needed <= 0) {{
{II}throw std::runtime_error(
{III}"MultiByteToWideChar() failed: " + std::to_string(size_needed)
{II});
{I}}}

{I}std::wstring result(size_needed, 0);

{I}MultiByteToWideChar(
{II}CP_UTF8,
{II}0,
{II}utf8_text,
{II}utf8_text_size_int,
{II}&(result[0]),
{II}size_needed
{I});

{I}return result;

{I}#else
{I}// NOTE (mristin):
{I}// We use codecvt although it has been deprecated. There has been not
{I}// suitable replacement proposed yet, so we simply stick to it
{I}// until there is. See:
{I}// https://stackoverflow.com/questions/42946335/deprecated-header-codecvt-replacement

{I}std::wstring_convert<std::codecvt_utf8<wchar_t>,wchar_t> conv;
{I}return conv.from_bytes(utf8_text);
{I}#endif
}}"""
        ),
        Stripped(
            f"""\
std::wstring Utf8ToWstring(const std::string& utf8_text) {{
{I}return Utf8ToWstring(&(utf8_text[0]), utf8_text.size());
}}"""
        ),
        cpp_common.generate_namespace_closing(namespace),
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
