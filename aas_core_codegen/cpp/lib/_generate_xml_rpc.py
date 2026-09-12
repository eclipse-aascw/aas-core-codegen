"""Generate code for de/serializing JSON-able values to and from XML."""

# NOTE (mristin):
# This module is private (it is emitted to ``src/``, never installed alongside
# the public headers in ``include/``), just like ``xml_common`` on which it
# depends. It implements a restricted subset of XML-RPC's own element
# vocabulary -- ``<boolean>``, ``<double>``, ``<string>``, ``<array>``,
# ``<data>``, ``<struct>``, ``<member>``, ``<name>`` and ``<value>`` -- to
# de/serialize a ``nlohmann::json`` value which is JSON-able (*i.e.*,
# recursively a boolean, a number, a string, an array of JSON-able values or
# an object of JSON-able values with string keys; never ``null``).
#
# It is meant to be used in two different ways:
# * Stand-alone, over a whole ``<value>`` document (see
#   :py:func:`_generate_xml_rpc.generate_header`'s ``DeserializeValue`` and
#   ``SerializeValue``) -- this is how it is tested in isolation, and how
#   a user could use it directly; and
# * Embedded within a larger XML document, one JSON-able property at a time
#   (see ``DeserializeValueFrom``/``DeserializeArrayBodyFrom``/
#   ``DeserializeStructBodyFrom`` and their serialization counterparts),
#   consuming/producing nodes on the *same*, already-open
#   ``xml_common::ReaderMergingText``/``xml_common::SelfClosingWriter`` that
#   ``xmlization`` itself uses to read/write the surrounding document. This is
#   how ``xmlization`` uses this module for ``JSONValue``/``JSONArray``/
#   ``JSONObject[K]``-typed properties -- see ``_generate_xmlization.py``.
#
# Like ``xml_common``, the content generated here does not depend on
# the meta-model (``symbol_table``) at all.

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
    INDENT7 as IIIIIII,
)


# region Path


def _generate_path_declaration() -> List[Stripped]:
    """Generate the declaration of the path to a value within a JSON-able tree."""
    return [
        Stripped(
            """\
/**
 * Represent a segment of a path to a value within a JSON-able tree.
 */
class ISegment {
 public:
  virtual std::wstring ToWstring() const = 0;
  virtual std::unique_ptr<ISegment> Clone() const = 0;
  virtual ~ISegment() = default;
};  // class ISegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent an access to an item of a JSON array by its index.
 */
struct IndexSegment : public ISegment {{
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
 * Represent an access to a value of a JSON object (a struct's member) by
 * its key (the member's name).
 */
struct MemberSegment : public ISegment {{
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
 * Represent a path to a value within a JSON-able tree.
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


def _generate_path_implementation() -> List[Stripped]:
    """Generate the implementation of the path to a value within a JSON-able tree."""
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
{II}L"[",
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
{II}L".",
{II}name
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

{I}std::deque<std::wstring> parts;
{I}for (const std::unique_ptr<ISegment>& segment : segments) {{
{II}parts.emplace_back(segment->ToWstring());
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
        Stripped("// endregion struct Path"),
    ]


# endregion

# region De-serialization


def _generate_deserialization_error_declaration() -> List[Stripped]:
    """Generate the declaration of the de-serialization error and reading options."""
    return [
        Stripped(
            f"""\
/**
 * Represent a de-serialization error.
 */
struct DeserializationError {{
{I}/**
{I} * Human-readable description of the error
{I} */
{I}std::wstring cause;

{I}/**
{I} * Path to the erroneous value
{I} */
{I}Path path;

{I}explicit DeserializationError(std::wstring a_cause);
{I}DeserializationError(std::wstring a_cause, Path a_path);
}};  // struct DeserializationError"""
        ),
        Stripped(
            f"""\
struct ReadingOptions {{
{I}/**
{I} * No XML attributes are expected in XML elements.
{I} * If `additional_attributes` is set, unexpected XML attributes are
{I} * ignored during parsing, and not reported as errors.
{I} */
{I}bool additional_attributes = false;

{I}/**
{I} * Size of the chunk to be read from the input stream and passed to
{I} * the XML parser.
{I} */
{I}size_t buffer_size = 1024;
}};  // struct ReadingOptions"""
        ),
    ]


def _generate_deserialize_definitions() -> List[Stripped]:
    """Generate the declarations of the de-serialization functions."""
    return [
        Stripped(
            f"""\
/**
 * \\brief Deserialize a JSON-able value from a stand-alone XML-RPC
 * ``<value>`` document.
 *
 * \\param is stream to read the XML from
 * \\param expected_namespace the only XML namespace we accept for every
 * element; this must match whatever namespace \\p is was serialized with
 * \\param options to be tweaked for special cases. The defaults should
 * work in most cases.
 * \\return The deserialized value, or a de-serialization error, if any.
 */
common::expected<
{I}nlohmann::json,
{I}DeserializationError
> DeserializeValue(
{I}std::istream& is,
{I}const std::string& expected_namespace,
{I}const ReadingOptions& options = ReadingOptions()
);"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Deserialize a JSON-able value, embedded within a larger XML
 * document which is already being read through \\p reader.
 *
 * \\p reader is expected to be positioned at the start element of
 * the discriminator (\\c \\<boolean\\>, \\c \\<double\\>, \\c \\<string\\>,
 * \\c \\<array\\> or \\c \\<struct\\>). On success, \\p reader is left
 * positioned at the node right after the discriminator's own stop element,
 * mirroring how the primitive ``Deserialize*`` functions in ``xmlization``
 * behave.
 */
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeValueFrom(
{I}xml_common::ReaderMergingText& reader
);"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Deserialize a JSON array's body, embedded within a larger XML
 * document which is already being read through \\p reader.
 *
 * \\p reader is expected to be positioned at the start element \\c \\<data\\>.
 * On success, \\p reader is left positioned at the node right after
 * the \\c \\<data\\> element's own stop element.
 */
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeArrayBodyFrom(
{I}xml_common::ReaderMergingText& reader
);"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Deserialize a JSON object's body, embedded within a larger XML
 * document which is already being read through \\p reader.
 *
 * \\p reader is expected to be positioned either at the first
 * \\c \\<member\\> start element, or already at the enclosing element's own
 * stop element if there are no members at all. On success, \\p reader is
 * left positioned at that same enclosing element's stop element.
 */
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeStructBodyFrom(
{I}xml_common::ReaderMergingText& reader
);"""
        ),
    ]


# endregion

# region Serialization


def _generate_serialization_error_declaration() -> List[Stripped]:
    """Generate the declaration of the serialization error."""
    return [
        Stripped(
            f"""\
/**
 * Represent a serialization error.
 */
struct SerializationError {{
{I}/**
{I} * Human-readable description of the error
{I} */
{I}std::wstring cause;

{I}/**
{I} * Path to the value that caused the error
{I} */
{I}Path path;

{I}explicit SerializationError(std::wstring a_cause);
{I}SerializationError(std::wstring a_cause, Path a_path);
}};  // struct SerializationError"""
        ),
    ]


def _generate_serialize_definitions() -> List[Stripped]:
    """Generate the declarations of the serialization functions."""
    return [
        Stripped(
            f"""\
/**
 * \\brief Serialize \\p value to a stand-alone XML-RPC ``<value>`` document.
 *
 * \\param os the UTF-8-encoded output stream where the XML will be written
 * \\param value to be serialized; it must be JSON-able (recursively
 * a boolean, a number, a string, an array or an object with string keys),
 * and never \\c null, or a \\ref SerializationError is returned
 * \\param xml_namespace to be written as the \\c xmlns attribute of the root
 * \\c \\<value\\> element
 * \\return An error, if any.
 */
common::optional<SerializationError> SerializeValue(
{I}std::ostream& os,
{I}const nlohmann::json& value,
{I}const std::string& xml_namespace
);"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Serialize \\p value, embedded within a larger XML document which is
 * already being written through \\p writer.
 *
 * This writes exactly one discriminator element (\\c \\<boolean\\>,
 * \\c \\<double\\>, \\c \\<string\\>, \\c \\<array\\> or \\c \\<struct\\>).
 */
common::optional<SerializationError> SerializeValueBodyTo(
{I}xml_common::SelfClosingWriter& writer,
{I}const nlohmann::json& value
);"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Serialize the JSON array \\p value's body, embedded within a larger
 * XML document which is already being written through \\p writer.
 *
 * This writes exactly one \\c \\<data\\> element. \\p value must be
 * a JSON array, or a \\ref SerializationError is returned.
 */
common::optional<SerializationError> SerializeArrayBodyTo(
{I}xml_common::SelfClosingWriter& writer,
{I}const nlohmann::json& value
);"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Serialize the JSON object \\p value's body, embedded within
 * a larger XML document which is already being written through \\p writer.
 *
 * This writes zero or more \\c \\<member\\> elements, with no enclosing
 * element of its own. \\p value must be a JSON object, or
 * a \\ref SerializationError is returned.
 */
common::optional<SerializationError> SerializeStructBodyTo(
{I}xml_common::SelfClosingWriter& writer,
{I}const nlohmann::json& value
);"""
        ),
    ]


# endregion


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(library_namespace: Stripped) -> str:
    """Generate header for de/serializing JSON-able values to and from XML."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.XML_RPC_NAMESPACE}")

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
#include "xml_common.hpp"

#include "{include_prefix_path}/common.hpp"

#pragma warning(push, 0)
#include <nlohmann/json.hpp>

#include <deque>
#include <iosfwd>
#include <memory>
#include <string>
#include <utility>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(f"namespace {cpp_common.XML_RPC_NAMESPACE} {{"),
        Stripped("// region Path"),
        *_generate_path_declaration(),
        Stripped("// endregion Path"),
        Stripped("// region De-serialization"),
        *_generate_deserialization_error_declaration(),
        *_generate_deserialize_definitions(),
        Stripped("// endregion De-serialization"),
        Stripped("// region Serialization"),
        *_generate_serialization_error_declaration(),
        *_generate_serialize_definitions(),
        Stripped("// endregion Serialization"),
        Stripped(f"}}  // namespace {cpp_common.XML_RPC_NAMESPACE}"),
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


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)


# region Implementation


def _generate_path_helper_implementation() -> List[Stripped]:
    """Generate the impl. of ``DeserializationError``/``SerializationError``."""
    return [
        Stripped(
            f"""\
DeserializationError::DeserializationError(
{I}std::wstring a_cause
) :
{I}cause(std::move(a_cause)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
DeserializationError::DeserializationError(
{I}std::wstring a_cause,
{I}Path a_path
) :
{I}cause(std::move(a_cause)),
{I}path(std::move(a_path)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
SerializationError::SerializationError(
{I}std::wstring a_cause
) :
{I}cause(std::move(a_cause)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
SerializationError::SerializationError(
{I}std::wstring a_cause,
{I}Path a_path
) :
{I}cause(std::move(a_cause)),
{I}path(std::move(a_path)) {{
{I}// Intentionally empty.
}}"""
        ),
    ]


def _generate_reading_helpers_implementation() -> List[Stripped]:
    """Generate small helpers shared by the de-serialization functions."""
    return [
        Stripped(
            f"""\
DeserializationError DeserializationErrorFromReader(
{I}const xml_common::ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected an error node at the reader cursor, but got ",
{IIII}xml_common::NodeToHumanReadableString(reader.node())
{III})
{II});
{I}}}

{I}const auto& error_node(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::ErrorNode&
{II}>(reader.node())
{I});

{I}return DeserializationError(
{II}common::Utf8ToWstring(error_node.cause)
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Return `true` if all characters are whitespace in the UTF-8-encoded text.
 */
bool IsWhitespace(const std::string& utf8_text) {{
{I}for (const char character : utf8_text) {{
{II}switch (character) {{
{III}case '\\t':
{III}case '\\n':
{III}case '\\r':
{III}case ' ':
{IIII}break;
{III}default:
{IIII}return false;
{II}}}
{I}}}

{I}return true;
}}"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Skip all whitespace text nodes.
 *
 * Do nothing if the cursor points to a non-text node.
 */
common::optional<DeserializationError> SkipWhitespace(
{I}xml_common::ReaderMergingText& reader
) {{
{I}while (reader.node().kind() == xml_common::NodeKind::Text) {{
{II}const xml_common::TextNode& text_node(
{III}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIII}const xml_common::TextNode&
{III}>(reader.node())
{II});

{II}if (!IsWhitespace(text_node.text)) {{
{III}break;
{II}}}

{II}reader.Read();
{I}}}

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return DeserializationErrorFromReader(reader);
{I}}}

{I}return common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
common::optional<DeserializationError> CheckReaderAtEof(
{I}const xml_common::ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != xml_common::NodeKind::Eof) {{
{II}return common::make_optional<DeserializationError>(
{III}common::Concat(
{IIII}L"Expected end-of-input, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}return common::nullopt;
}}"""
        ),
    ]


def _generate_deserialize_scalar_bodies_implementation() -> List[Stripped]:
    """
    Generate the impl. of the scalar discriminator body readers.

    Each of these functions assumes that ``reader`` is positioned right after
    the discriminator's own start element has already been consumed by
    the caller (:py:func:`DeserializeValueFrom`), *i.e.*, at the text content
    (or, for a ``<string>``, possibly already at the stop element if the
    string is empty). None of them consume the discriminator's own stop
    element -- that is uniformly handled by ``DeserializeValueFrom`` for all
    five discriminators alike.
    """
    return [
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeBooleanBodyFrom(
{I}xml_common::ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != xml_common::NodeKind::Text) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected \\"0\\" or \\"1\\" as the text of a <boolean> element, "
{IIIII}L"but got ",
{IIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIII})
{III})
{II});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::TextNode&
{II}>(reader.node()).text
{I});

{I}bool deserialized;
{I}if (text == "1") {{
{II}deserialized = true;
{I}}} else if (text == "0") {{
{II}deserialized = false;
{I}}} else {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected \\"0\\" or \\"1\\" as the text of a <boolean> element, "
{IIIII}L"but got: ",
{IIIII}common::Utf8ToWstring(text)
{IIII})
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}return std::make_pair(nlohmann::json(deserialized), common::nullopt);
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeDoubleBodyFrom(
{I}xml_common::ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != xml_common::NodeKind::Text) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a number as the text of a <double> element, but got ",
{IIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIII})
{III})
{II});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::TextNode&
{II}>(reader.node()).text
{I});

{I}double deserialized;

{I}try {{
{II}deserialized = std::stod(text);
{I}}} catch (std::invalid_argument&) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a number as the text of a <double> element, "
{IIIII}L"but got an invalid value: ",
{IIIII}common::Utf8ToWstring(text)
{IIII})
{III})
{II});
{I}}} catch (std::out_of_range&) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a number as the text of a <double> element, "
{IIIII}L"but got a value out of the double range: ",
{IIIII}common::Utf8ToWstring(text)
{IIII})
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We follow the same strictness for the special values as xs:double,
{I}// see: https://www.w3.org/TR/xmlschema11-2/#double
{I}const bool invalid_text(
{II}(
{III}deserialized == std::numeric_limits<double>::infinity()
{III}&& text != "INF"
{II}) || (
{III}deserialized == -std::numeric_limits<double>::infinity()
{III}&& text != "-INF"
{II}) || (
{III}std::isnan(deserialized)
{III}&& text != "NaN"
{II})
{I});

{I}if (invalid_text) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a number as the text of a <double> element, "
{IIIII}L"but got an invalid value: ",
{IIIII}common::Utf8ToWstring(text)
{IIII})
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}return std::make_pair(nlohmann::json(deserialized), common::nullopt);
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeStringBodyFrom(
{I}xml_common::ReaderMergingText& reader
) {{
{I}switch (reader.node().kind()) {{
{II}case xml_common::NodeKind::Stop:
{III}// NOTE (mristin):
{III}// Encountering a stop node means that the string is empty.
{III}return std::make_pair(
{IIII}nlohmann::json(std::string()),
{IIII}common::nullopt
{III});
{II}case xml_common::NodeKind::Text:
{III}break;
{II}default:
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}common::make_optional<DeserializationError>(
{IIIII}common::Concat(
{IIIIII}L"Expected text as the content of a <string> element, "
{IIIIII}L"but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII})
{III});
{I}}}

{I}const std::string text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::TextNode&
{II}>(reader.node()).text
{I});

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}return std::make_pair(nlohmann::json(text), common::nullopt);
}}"""
        ),
    ]


def _generate_deserialize_value_from_implementation() -> Stripped:
    """Generate the impl. of the discriminated-value de-serialization."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeValueFrom(
{I}xml_common::ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != xml_common::NodeKind::Start) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected one of <boolean>, <double>, <string>, <array> "
{IIIII}L"or <struct>, but got ",
{IIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIII})
{III})
{II});
{I}}}

{I}const std::string discriminator(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name
{I});

{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}common::optional<nlohmann::json> value;
{I}common::optional<DeserializationError> error;

{I}if (discriminator == "boolean") {{
{II}std::tie(value, error) = DeserializeBooleanBodyFrom(reader);
{I}}} else if (discriminator == "double") {{
{II}std::tie(value, error) = DeserializeDoubleBodyFrom(reader);
{I}}} else if (discriminator == "string") {{
{II}std::tie(value, error) = DeserializeStringBodyFrom(reader);
{I}}} else if (discriminator == "array") {{
{II}std::tie(value, error) = DeserializeArrayBodyFrom(reader);
{I}}} else if (discriminator == "struct") {{
{II}std::tie(value, error) = DeserializeStructBodyFrom(reader);
{I}}} else {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected one of <boolean>, <double>, <string>, <array> "
{IIIII}L"or <struct>, but got a start element <",
{IIIII}common::Utf8ToWstring(discriminator),
{IIIII}L">"
{IIII})
{III})
{II});
{I}}}

{I}if (error.has_value()) {{
{II}return std::make_pair(common::nullopt, std::move(error));
{I}}}

{I}if (!xml_common::IsStopNodeWithName(reader.node(), discriminator)) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a stop element </",
{IIIII}common::Utf8ToWstring(discriminator),
{IIIII}L">, but got ",
{IIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIII})
{III})
{II});
{I}}}

{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}return std::make_pair(std::move(value), common::nullopt);
}}"""
    )


def _generate_deserialize_array_body_from_implementation() -> Stripped:
    """Generate the impl. of the ``<data>`` de-serialization."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeArrayBodyFrom(
{I}xml_common::ReaderMergingText& reader
) {{
{I}if (
{II}reader.node().kind() != xml_common::NodeKind::Start
{II}|| static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name != "data"
{I}) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a start element <data>, but got ",
{IIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIII})
{III})
{II});
{I}}}

{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}nlohmann::json result(nlohmann::json::array());
{I}size_t index = 0;

{I}while (
{II}reader.node().kind() == xml_common::NodeKind::Start
{II}&& static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name == "value"
{I}) {{
{II}reader.Read();
{II}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}DeserializationErrorFromReader(reader)
{III});
{II}}}

{II}common::optional<nlohmann::json> item;
{II}common::optional<DeserializationError> error;
{II}std::tie(item, error) = DeserializeValueFrom(reader);

{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<IndexSegment>(index)
{III});
{III}return std::make_pair(common::nullopt, std::move(error));
{II}}}

{II}if (!xml_common::IsStopNodeWithName(reader.node(), "value")) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}common::make_optional<DeserializationError>(
{IIIII}common::Concat(
{IIIIII}L"Expected a stop element </value>, but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII})
{III});
{II}}}

{II}reader.Read();
{II}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}DeserializationErrorFromReader(reader)
{III});
{II}}}

{II}result.push_back(std::move(*item));
{II}++index;
{I}}}

{I}if (!xml_common::IsStopNodeWithName(reader.node(), "data")) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a start element <value> or a stop element </data>, "
{IIIII}L"but got ",
{IIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIII})
{III})
{II});
{I}}}

{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}return std::make_pair(std::move(result), common::nullopt);
}}"""
    )


def _generate_deserialize_struct_body_from_implementation() -> Stripped:
    """Generate the impl. of the ``<member>*`` de-serialization."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeStructBodyFrom(
{I}xml_common::ReaderMergingText& reader
) {{
{I}nlohmann::json result(nlohmann::json::object());

{I}while (
{II}reader.node().kind() == xml_common::NodeKind::Start
{II}&& static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name == "member"
{I}) {{
{II}reader.Read();
{II}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}DeserializationErrorFromReader(reader)
{III});
{II}}}

{II}if (
{III}reader.node().kind() != xml_common::NodeKind::Start
{III}|| static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIII}const xml_common::StartNode&
{III}>(reader.node()).name != "name"
{II}) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}common::make_optional<DeserializationError>(
{IIIII}common::Concat(
{IIIIII}L"Expected a start element <name>, but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII})
{III});
{II}}}

{II}reader.Read();
{II}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}DeserializationErrorFromReader(reader)
{III});
{II}}}

{II}std::string key;
{II}switch (reader.node().kind()) {{
{III}case xml_common::NodeKind::Stop:
{IIII}key = std::string();
{IIII}break;
{III}case xml_common::NodeKind::Text:
{IIII}key = static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const xml_common::TextNode&
{IIII}>(reader.node()).text;

{IIII}reader.Read();
{IIII}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{IIIII}return std::make_pair(
{IIIIII}common::nullopt,
{IIIIII}DeserializationErrorFromReader(reader)
{IIIII});
{IIII}}}
{IIII}break;
{III}default:
{IIII}return std::make_pair(
{IIIII}common::nullopt,
{IIIII}common::make_optional<DeserializationError>(
{IIIIII}common::Concat(
{IIIIIII}L"Expected text as the content of a <name> element, "
{IIIIIII}L"but got ",
{IIIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIIII})
{IIIII})
{IIII});
{II}}}

{II}if (!xml_common::IsStopNodeWithName(reader.node(), "name")) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}common::make_optional<DeserializationError>(
{IIIII}common::Concat(
{IIIIII}L"Expected a stop element </name>, but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII})
{III});
{II}}}

{II}reader.Read();
{II}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}DeserializationErrorFromReader(reader)
{III});
{II}}}

{II}if (
{III}reader.node().kind() != xml_common::NodeKind::Start
{III}|| static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIII}const xml_common::StartNode&
{III}>(reader.node()).name != "value"
{II}) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}common::make_optional<DeserializationError>(
{IIIII}common::Concat(
{IIIIII}L"Expected a start element <value>, but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII})
{III});
{II}}}

{II}reader.Read();
{II}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}DeserializationErrorFromReader(reader)
{III});
{II}}}

{II}common::optional<nlohmann::json> item;
{II}common::optional<DeserializationError> error;
{II}std::tie(item, error) = DeserializeValueFrom(reader);

{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<MemberSegment>(
{IIIII}common::Utf8ToWstring(key)
{IIII})
{III});
{III}return std::make_pair(common::nullopt, std::move(error));
{II}}}

{II}if (!xml_common::IsStopNodeWithName(reader.node(), "value")) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}common::make_optional<DeserializationError>(
{IIIII}common::Concat(
{IIIIII}L"Expected a stop element </value>, but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII})
{III});
{II}}}

{II}reader.Read();
{II}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}DeserializationErrorFromReader(reader)
{III});
{II}}}

{II}if (!xml_common::IsStopNodeWithName(reader.node(), "member")) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}common::make_optional<DeserializationError>(
{IIIII}common::Concat(
{IIIIII}L"Expected a stop element </member>, but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII})
{III});
{II}}}

{II}reader.Read();
{II}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}DeserializationErrorFromReader(reader)
{III});
{II}}}

{II}// NOTE (mristin):
{II}// A member with a repeated key overwrites the previous value for that
{II}// key, mirroring ``nlohmann::json``'s own ``operator[]`` assignment
{II}// semantics.
{II}result[key] = std::move(*item);
{I}}}

{I}return std::make_pair(std::move(result), common::nullopt);
}}"""
    )


def _generate_deserialize_value_implementation() -> Stripped:
    """Generate the impl. of the stand-alone de-serialization entry point."""
    return Stripped(
        f"""\
common::expected<
{I}nlohmann::json,
{I}DeserializationError
> DeserializeValue(
{I}std::istream& is,
{I}const std::string& expected_namespace,
{I}const ReadingOptions& options
) {{
{I}xml_common::ReaderMergingText reader(
{II}is,
{II}options.additional_attributes,
{II}options.buffer_size,
{II}expected_namespace
{I});

{I}reader.Initialize();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return common::make_unexpected(DeserializationErrorFromReader(reader));
{I}}}

{I}if (
{II}reader.node().kind() != xml_common::NodeKind::Start
{II}|| static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name != "value"
{I}) {{
{II}return common::make_unexpected(
{III}DeserializationError(
{IIII}common::Concat(
{IIIII}L"Expected a start element <value>, but got ",
{IIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIII})
{III})
{II});
{I}}}

{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return common::make_unexpected(DeserializationErrorFromReader(reader));
{I}}}

{I}common::optional<nlohmann::json> value;
{I}common::optional<DeserializationError> error;
{I}std::tie(value, error) = DeserializeValueFrom(reader);

{I}if (error.has_value()) {{
{II}return common::make_unexpected(std::move(*error));
{I}}}

{I}if (!xml_common::IsStopNodeWithName(reader.node(), "value")) {{
{II}return common::make_unexpected(
{III}DeserializationError(
{IIII}common::Concat(
{IIIII}L"Expected a stop element </value>, but got ",
{IIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIII})
{III})
{II});
{I}}}

{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return common::make_unexpected(DeserializationErrorFromReader(reader));
{I}}}

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}return common::make_unexpected(std::move(*error));
{I}}}

{I}error = CheckReaderAtEof(reader);
{I}if (error.has_value()) {{
{II}return common::make_unexpected(std::move(*error));
{I}}}

{I}return std::move(*value);
}}"""
    )


def _generate_writing_helpers_implementation() -> List[Stripped]:
    """Generate small helpers shared by the serialization functions."""
    return [
        Stripped(
            f"""\
/**
 * Check that the output stream is not in a bad state. If so, create an error.
 */
common::optional<SerializationError> CheckOstreamState(
{I}const std::ostream& os
) {{
{I}if (os.bad()) {{
{II}return common::make_optional<SerializationError>(
{III}std::wstring(L"The output stream is in a bad state.")
{II});
{I}}}

{I}return common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Convert a low-level writer error, if any, to a \\ref
 * SerializationError.
 */
common::optional<SerializationError> ConvertWriterError(
{I}xml_common::SelfClosingWriter& writer
) {{
{I}if (!writer.error().has_value()) {{
{II}return common::nullopt;
{I}}}

{I}xml_common::SerializationError underlying(
{II}std::move(*writer.move_error())
{I});

{I}return common::make_optional<SerializationError>(
{II}std::move(underlying.cause)
{I});
}}"""
        ),
    ]


def _generate_serialize_value_body_to_implementation() -> Stripped:
    """Generate the impl. of the discriminated-value serialization."""
    return Stripped(
        f"""\
common::optional<SerializationError> SerializeValueBodyTo(
{I}xml_common::SelfClosingWriter& writer,
{I}const nlohmann::json& value
) {{
{I}if (value.is_boolean()) {{
{II}writer.StartElement("boolean");
{II}// NOTE (mristin):
{II}// We deliberately do *not* use ``writer.SerializeBool``, as it writes
{II}// ``true``/``false`` -- the lexical form expected everywhere else in
{II}// this code base -- whereas real XML-RPC tooling expects a strict
{II}// ``1``/``0``, which is also what ``DeserializeBooleanBodyFrom``
{II}// requires.
{II}writer.SerializeString(value.get<bool>() ? "1" : "0");
{II}writer.StopElement("boolean");
{I}}} else if (value.is_number()) {{
{II}writer.StartElement("double");
{II}writer.SerializeDouble(value.get<double>());
{II}writer.StopElement("double");
{I}}} else if (value.is_string()) {{
{II}writer.StartElement("string");
{II}writer.SerializeString(
{III}*value.get_ptr<const std::string*>()
{II});
{II}writer.StopElement("string");
{I}}} else if (value.is_array()) {{
{II}writer.StartElement("array");

{II}common::optional<SerializationError> error = SerializeArrayBodyTo(
{III}writer, value
{II});
{II}if (error.has_value()) {{
{III}return error;
{II}}}

{II}writer.StopElement("array");
{I}}} else if (value.is_object()) {{
{II}writer.StartElement("struct");

{II}common::optional<SerializationError> error = SerializeStructBodyTo(
{III}writer, value
{II});
{II}if (error.has_value()) {{
{III}return error;
{II}}}

{II}writer.StopElement("struct");
{I}}} else {{
{II}// NOTE (mristin):
{II}// This covers ``null``, a binary value and a discarded value -- none of
{II}// which are representable as a ``JSONValue``.
{II}return common::make_optional<SerializationError>(
{III}std::wstring(
{IIII}L"Expected a JSON-able value (a boolean, a number, a string, "
{IIII}L"an array or an object), but got a value of a different, "
{IIII}L"non-JSON-able type (possibly null)"
{III})
{II});
{I}}}

{I}return ConvertWriterError(writer);
}}"""
    )


def _generate_serialize_array_body_to_implementation() -> Stripped:
    """Generate the impl. of the ``<data>`` serialization."""
    return Stripped(
        f"""\
common::optional<SerializationError> SerializeArrayBodyTo(
{I}xml_common::SelfClosingWriter& writer,
{I}const nlohmann::json& value
) {{
{I}if (!value.is_array()) {{
{II}return common::make_optional<SerializationError>(
{III}std::wstring(
{IIII}L"Expected a JSON array, but got a value of a different JSON type"
{III})
{II});
{I}}}

{I}writer.StartElement("data");

{I}size_t index = 0;
{I}for (const nlohmann::json& item : value) {{
{II}writer.StartElement("value");

{II}common::optional<SerializationError> error = SerializeValueBodyTo(
{III}writer, item
{II});
{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<IndexSegment>(index)
{III});
{III}return error;
{II}}}

{II}writer.StopElement("value");
{II}++index;
{I}}}

{I}writer.StopElement("data");

{I}return ConvertWriterError(writer);
}}"""
    )


def _generate_serialize_struct_body_to_implementation() -> Stripped:
    """Generate the impl. of the ``<member>*`` serialization."""
    return Stripped(
        f"""\
common::optional<SerializationError> SerializeStructBodyTo(
{I}xml_common::SelfClosingWriter& writer,
{I}const nlohmann::json& value
) {{
{I}if (!value.is_object()) {{
{II}return common::make_optional<SerializationError>(
{III}std::wstring(
{IIII}L"Expected a JSON object, but got a value of a different JSON type"
{III})
{II});
{I}}}

{I}for (const auto& item : value.items()) {{
{II}writer.StartElement("member");

{II}writer.StartElement("name");
{II}writer.SerializeString(item.key());
{II}writer.StopElement("name");

{II}writer.StartElement("value");

{II}common::optional<SerializationError> error = SerializeValueBodyTo(
{III}writer, item.value()
{II});
{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<MemberSegment>(
{IIIII}common::Utf8ToWstring(item.key())
{IIII})
{III});
{III}return error;
{II}}}

{II}writer.StopElement("value");

{II}writer.StopElement("member");
{I}}}

{I}return ConvertWriterError(writer);
}}"""
    )


def _generate_serialize_value_implementation() -> Stripped:
    """Generate the impl. of the stand-alone serialization entry point."""
    return Stripped(
        f"""\
common::optional<SerializationError> SerializeValue(
{I}std::ostream& os,
{I}const nlohmann::json& value,
{I}const std::string& xml_namespace
) {{
{I}os << "<value xmlns=\\"" << xml_namespace << "\\">";

{I}common::optional<SerializationError> error = CheckOstreamState(os);
{I}if (error.has_value()) {{
{II}return error;
{I}}}

{I}xml_common::SelfClosingWriter writer(os, "");

{I}error = SerializeValueBodyTo(writer, value);
{I}if (error.has_value()) {{
{II}return error;
{I}}}

{I}writer.Finish();

{I}error = ConvertWriterError(writer);
{I}if (error.has_value()) {{
{II}return error;
{I}}}

{I}os << "</value>";

{I}return CheckOstreamState(os);
}}"""
    )


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(library_namespace: Stripped) -> str:
    """Generate implementation for de/serializing JSON-able values to and from XML."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.XML_RPC_NAMESPACE}")

    blocks = [
        cpp_common.WARNING,
        Stripped(
            """\
#include "xml_rpc.hpp"
#include "xml_common.hpp"

#pragma warning(push, 0)
#include <cmath>
#include <istream>
#include <limits>
#include <ostream>
#include <stdexcept>
#include <string>
#include <utility>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        Stripped("// region Path"),
        *_generate_path_implementation(),
        Stripped("// endregion Path"),
        *_generate_path_helper_implementation(),
        Stripped("// region De-serialization"),
        *_generate_reading_helpers_implementation(),
        *_generate_deserialize_scalar_bodies_implementation(),
        _generate_deserialize_value_from_implementation(),
        _generate_deserialize_array_body_from_implementation(),
        _generate_deserialize_struct_body_from_implementation(),
        _generate_deserialize_value_implementation(),
        Stripped("// endregion De-serialization"),
        Stripped("// region Serialization"),
        *_generate_writing_helpers_implementation(),
        _generate_serialize_value_body_to_implementation(),
        _generate_serialize_array_body_to_implementation(),
        _generate_serialize_struct_body_to_implementation(),
        _generate_serialize_value_implementation(),
        Stripped("// endregion Serialization"),
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


assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)


# endregion
