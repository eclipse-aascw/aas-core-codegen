"""Generate code for the XPath to an erroneous value in an XML document."""

# NOTE (mristin):
# This module is public (it is installed alongside the other headers in
# ``include/``), as ``xmlization``'s own de-serialization errors report
# their location with it.
#
# We keep the XPath in a module of its own since both ``xmlization``, which
# reads the meta-model's own classes, and ``xml_rpc``, which reads the values
# nested in them, grow one and the same path as they descend. Were the XPath
# to live in ``xmlization``, ``xml_rpc`` would have to keep a parallel
# vocabulary of its own, and every error crossing the boundary between the two
# would have to be translated segment by segment.
#
# Unlike most of the other C++ library modules, the content generated here does
# not depend on the meta-model (``symbol_table``) at all -- it is always
# the same, exactly as with ``revm`` or ``pattern``.

import io
from typing import List

from aas_core_codegen.common import Stripped
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_declarations() -> List[Stripped]:
    """Generate the declarations of the XPath and its segments."""
    return [
        Stripped(
            f"""\
/**
 * Represent a segment of an XPath to an erroneous value.
 */
class ISegment {{
 public:
{I}/**
{I} * \\brief Convert the segment to a string in an XPath.
{I} *
{I} * The result is escaped such that it can be directly inserted
{I} * into an XPath.
{I} */
{I}virtual std::wstring ToWstring() const = 0;

{I}virtual std::unique_ptr<ISegment> Clone() const = 0;

{I}virtual ~ISegment() = default;
}};  // class ISegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent an element on an XPath to the erroneous value.
 */
struct ElementSegment : public ISegment {{
{I}/**
{I} * \\brief Name of the XML element, without the namespace
{I} *
{I} * We deliberately omit the namespace in the tag names. If you want to actually
{I} * query with the resulting XPath, you have to insert the namespaces manually.
{I} * We did not know how to include the namespace in a meaningful way, as XPath
{I} * assumes namespace prefixes to be defined <em>outside</em> of the document.
{I} * At least the path thus rendered is informative, and you should be able to
{I} * descend it manually.
{I} */
{I}std::wstring name;

{I}ElementSegment(
{II}std::wstring a_name
{I});

{I}std::wstring ToWstring() const override;

{I}std::unique_ptr<ISegment> Clone() const override;

{I}~ElementSegment() override = default;
}};  // struct ElementSegment"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Represent a member of a struct on an XPath to the erroneous value.
 *
 * A struct holds its members' names in a ``<name>`` child element instead of
 * an attribute, so we have to match on that child element.
 */
struct MemberSegment : public ISegment {{
{I}/**
{I} * Name of the member
{I} */
{I}std::wstring name;

{I}explicit MemberSegment(
{II}std::wstring a_name
{I});

{I}std::wstring ToWstring() const override;

{I}std::unique_ptr<ISegment> Clone() const override;

{I}~MemberSegment() override = default;
}};  // struct MemberSegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent an element in a sequence on an XPath to the erroneous value.
 */
struct IndexSegment : public ISegment {{
{I}/**
{I} * Index of the element in the sequence
{I} */
{I}size_t index;

{I}explicit IndexSegment(
{II}size_t an_index
{I});

{I}std::wstring ToWstring() const override;

{I}std::unique_ptr<ISegment> Clone() const override;

{I}~IndexSegment() override = default;
}};  // struct IndexSegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent the relative XPath to the erroneous element.
 */
struct Path {{
{I}std::deque<std::unique_ptr<ISegment> > segments;

{I}Path();
{I}Path(const Path& other);
{I}Path(Path&& other);
{I}Path& operator=(const Path& other);
{I}Path& operator=(Path&& other);

{I}std::wstring ToWstring() const;
}};  // struct Path"""
        ),
    ]


def _generate_escape_for_xpath_implementation() -> Stripped:
    """Generate the impl. of the escaping of a text to be put in an XPath."""
    return Stripped(
        f"""\
namespace {{

/**
 * \\brief Escape \\p text so that it can be directly inserted into an XPath.
 *
 * \\param text to be escaped
 * \\return the escaped text
 */
std::wstring EscapeForXPath(
{I}const std::wstring& text
) {{
{I}size_t out_len = 0;
{I}for (const wchar_t character : text) {{
{II}switch (character) {{
{III}// NOTE (mristin):
{III}// We use sizeof on *strings* instead of *wide strings* to get
{III}// the number of *characters*. Otherwise, if we used wide strings,
{III}// we would obtain the wrong number of characters with `sizeof`
{III}// as we would count bytes instead of characters, which differ
{III}// in wide strings due to encoding.

{III}case L'&': {{
{IIII}out_len += sizeof("&amp;");
{IIII}break;
{III}}}
{III}case L'/': {{
{IIII}out_len += sizeof("&#47;");
{IIII}break;
{III}}}
{III}case L'<': {{
{IIII}out_len += sizeof("&lt;");
{IIII}break;
{III}}}
{III}case L'>': {{
{IIII}out_len += sizeof("&gt;");
{IIII}break;
{III}}}
{III}case L'"': {{
{IIII}out_len += sizeof("&quot;");
{IIII}break;
{III}}}
{III}case L'\\'': {{
{IIII}out_len += sizeof("&apos;");
{IIII}break;
{III}}}
{III}default:
{IIII}++out_len;
{IIII}break;
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// We assume here that XML encoding is always *longer* than
{I}// the original text.
{I}if (out_len == text.size()) {{
{II}return text;
{I}}}

{I}std::wstring out;
{I}out.reserve(out_len);

{I}for (const wchar_t character : text) {{
{II}switch (character) {{
{III}case L'&':
{IIII}out.append(L"&amp;");
{IIII}break;
{III}case L'/':
{IIII}out.append(L"&#47;");
{IIII}break;
{III}case L'<':
{IIII}out.append(L"&lt;");
{IIII}break;
{III}case L'>':
{IIII}out.append(L"&gt;");
{IIII}break;
{III}case L'"':
{IIII}out.append(L"&quot;");
{IIII}break;
{III}case L'\\'':
{IIII}out.append(L"&apos;");
{IIII}break;
{III}default:
{IIII}out.push_back(character);
{IIII}break;
{II}}}
{I}}}

{I}return out;
}}

}}  // namespace"""
    )


def _generate_element_segment_implementation() -> List[Stripped]:
    """Generate the impl. of the element segment in an error XPath."""
    return [
        Stripped("// region struct ElementSegment"),
        Stripped(
            f"""\
ElementSegment::ElementSegment(
{I}std::wstring a_name
) :
{I}name(std::move(a_name)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
std::wstring ElementSegment::ToWstring() const {{
{I}return EscapeForXPath(name);
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<ISegment> ElementSegment::Clone() const {{
{I}return common::make_unique<ElementSegment>(*this);
}}"""
        ),
        Stripped("// endregion struct ElementSegment"),
    ]


def _generate_member_segment_implementation() -> List[Stripped]:
    """Generate the impl. of the struct member segment in an error XPath."""
    return [
        Stripped("// region struct MemberSegment"),
        Stripped(
            f"""\
MemberSegment::MemberSegment(
{I}std::wstring a_name
) :
{I}name(std::move(a_name)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
std::wstring MemberSegment::ToWstring() const {{
{I}return common::Concat(
{II}L"member[name=\\"",
{II}EscapeForXPath(name),
{II}L"\\"]"
{I});
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<ISegment> MemberSegment::Clone() const {{
{I}return common::make_unique<MemberSegment>(*this);
}}"""
        ),
        Stripped("// endregion struct MemberSegment"),
    ]


def _generate_index_segment_implementation() -> List[Stripped]:
    """Generate the impl. of the index segment in an error XPath."""
    return [
        Stripped("// region struct IndexSegment"),
        Stripped(
            f"""\
IndexSegment::IndexSegment(
{I}size_t an_index
) :
{I}index(an_index) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
std::wstring IndexSegment::ToWstring() const {{
{I}return common::Concat(
{II}L"*[",
{II}std::to_wstring(index),
{II}L"]"
{I});
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<ISegment> IndexSegment::Clone() const {{
{I}return common::make_unique<IndexSegment>(*this);
}}"""
        ),
        Stripped("// endregion struct IndexSegment"),
    ]


def _generate_path_implementation() -> List[Stripped]:
    """Generate the impl. of the XPath to the erroneous value."""
    return [
        Stripped("// region struct Path"),
        Stripped(
            f"""\
Path::Path() {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Path::Path(const Path& other) {{
{I}for (const std::unique_ptr<ISegment>& segment : other.segments) {{
{II}segments.emplace_back(segment->Clone());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
Path::Path(Path&& other) {{
{I}segments = std::move(other.segments);
}}"""
        ),
        Stripped(
            f"""\
Path& Path::operator=(const Path& other) {{
{I}segments.clear();
{I}for (const std::unique_ptr<ISegment>& segment : other.segments) {{
{II}segments.emplace_back(segment->Clone());
{I}}}
{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
Path& Path::operator=(Path&& other) {{
{I}if (this != &other) {{
{II}segments = std::move(other.segments);
{I}}}
{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
std::wstring Path::ToWstring() const {{
{I}if (segments.empty()) {{
{II}return L"";
{I}}}

{I}std::vector<std::wstring> parts;
{I}parts.reserve(segments.size() * 2 - 1);

{I}auto it = segments.begin();

{I}parts.emplace_back((*it)->ToWstring());
{I}++it;

{I}for (; it != segments.end(); ++it) {{
{II}parts.emplace_back(L"/");
{II}parts.emplace_back((*it)->ToWstring());
{I}}}

{I}size_t out_len = 0;
{I}for (const std::wstring& part : parts) {{
{II}out_len += part.size();
{I}}}

{I}std::wstring out;
{I}out.reserve(out_len);
{I}for (const std::wstring& part : parts) {{
{II}out.append(part);
{I}}}

{I}return out;
}}"""
        ),
    ]


def generate_header(library_namespace: Stripped) -> str:
    """Generate header for the XPath to an erroneous value in an XML document."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.XML_PATH_NAMESPACE}")

    include_guard_var = cpp_common.include_guard_var(namespace)

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/common.hpp"

#pragma warning(push, 0)
#include <deque>
#include <memory>
#include <string>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            f"""\
/**
 * \\defgroup xml_path Report where in an XML document an error occurred.
 * @{{
 */
namespace {cpp_common.XML_PATH_NAMESPACE} {{"""
        ),
        *_generate_declarations(),
        Stripped(
            f"""\
}}  // namespace {cpp_common.XML_PATH_NAMESPACE}
/**@}}*/"""
        ),
        cpp_common.generate_namespace_closing(library_namespace),
        cpp_common.WARNING,
        Stripped(f"#endif  // {include_guard_var}"),
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


def generate_implementation(library_namespace: Stripped) -> str:
    """Generate implementation for the XPath to an erroneous value in an XML document."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.XML_PATH_NAMESPACE}")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/xml_path.hpp"

#pragma warning(push, 0)
#include <string>
#include <utility>
#include <vector>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        _generate_escape_for_xpath_implementation(),
        *_generate_element_segment_implementation(),
        *_generate_member_segment_implementation(),
        *_generate_index_segment_implementation(),
        *_generate_path_implementation(),
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
