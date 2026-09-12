"""Generate code for XML de/serialization."""

import io
from typing import List, Tuple, Optional, Sequence, Final, Mapping

from icontract import ensure, require

from aas_core_codegen import intermediate, specific_implementations, naming
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    Identifier,
    Error,
    assert_never,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


def _generate_deserialize_definitions(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the definitions of the de-serialization functions ``*From``."""
    result = [
        Stripped(
            f"""\
/**
 * Deserialize the instance from an XML read from the stream \\p is.
 *
 * \\param is stream of ASCII, ISO-8859-1 or UTF-8-encoded characters to read XML from
 * \\param options reading options to be tweaked for special cases. The defaults should
 * work in most cases.
 * \\return the parsed instance, or an error if any
 */
common::expected<
{I}std::shared_ptr<types::IClass>,
{I}DeserializationError
> From(
{I}std::istream& is,
{I}const ReadingOptions& options = {{}}
);"""
        ),
    ]

    for cls in symbol_table.classes:
        interface_name = cpp_naming.interface_name(cls.name)
        function_name = cpp_naming.function_name(Identifier(f"{cls.name}_from"))
        result.append(
            Stripped(
                f"""\
/**
 * Deserialize an instance of types::{interface_name} from an XML
 * read from the stream \\p is.
 *
 * \\param is stream to read XML from
 * \\param options reading options to be tweaked for special cases. The defaults should
 * work in most cases.
 * \\return the parsed types::{interface_name}, or an error if any
 */
common::expected<
{I}std::shared_ptr<types::{interface_name}>,
{I}DeserializationError
> {function_name}(
{I}std::istream& is,
{I}const ReadingOptions& options = {{}}
);"""
            )
        )

    for named_union in symbol_table.named_unions:
        union_name = cpp_naming.union_name(named_union.name)
        function_name = cpp_naming.function_name(Identifier(f"{named_union.name}_from"))
        result.append(
            Stripped(
                f"""\
/**
 * Deserialize an instance of types::{union_name} from an XML
 * read from the stream \\p is.
 *
 * \\param is stream to read XML from
 * \\param options reading options to be tweaked for special cases. The defaults should
 * work in most cases.
 * \\return the parsed types::{union_name}, or an error if any
 */
common::expected<
{I}types::{union_name},
{I}DeserializationError
> {function_name}(
{I}std::istream& is,
{I}const ReadingOptions& options = {{}}
);"""
            )
        )

    return result


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
    """Generate header for XML de/serialization."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.XMLIZATION_NAMESPACE}")

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
#include "{include_prefix_path}/iteration.hpp"
#include "{include_prefix_path}/types.hpp"

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
 * \\defgroup xmlization De/serialize instances from and to XML.
 * @{{
 */
namespace {cpp_common.XMLIZATION_NAMESPACE} {{"""
        ),
        Stripped(
            """\
/**
 * Specify the expected XML namespace of all the XML elements.
 */
extern const std::string kNamespace;"""
        ),
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
        Stripped("// region De-serialization"),
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
{I} * Usually, attributes are considered errors and reported as such. However,
{I} * some implementations add their own custom attributes, and we sometimes
{I} * still want to parse such XML. If `additional_attributes` is set,
{I} * the unexpected XML attributes will be ignored during parsing, and not
{I} * reported.
{I} */
{I}bool additional_attributes = false;

{I}/**
{I} * Size of the chunk to be read from the input stream and passed to
{I} * the XML parser.
{I} */
{I}size_t buffer_size = 1024;
}};  // struct ReadingOptions"""
        ),
        *_generate_deserialize_definitions(symbol_table=symbol_table),
        Stripped("// endregion Deserialization"),
        Stripped("// region Serialization"),
        Stripped(
            f"""\
/**
 * Represent an error in the serialization of an instance to XML.
 */
class SerializationException : public std::exception {{
 public:
{I}SerializationException(
{II}std::wstring cause
{I});

{I}SerializationException(
{II}std::wstring cause,
{II}iteration::Path path
{I});

{I}const char* what() const noexcept override;

{I}const std::wstring& cause() const noexcept;
{I}const iteration::Path& path() const noexcept;

{I}~SerializationException() noexcept override = default;

 private:
{I}const std::wstring cause_;
{I}const iteration::Path path_;
{I}const std::string msg_;
}};  // class SerializationException"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Customize how instances should be serialized to XML.
 *
 * We selected the defaults so that they can be used when you serialize to
 * a file.
 *
 * Usually, you want to write the namespace at the root element, and no
 * prefixes are written in the XML names. However, if you are embedding
 * the XML in a larger XML structure, you specify the namespace
 * aliases and then use them as XML name prefixes. The prefix usually ends
 * with a full colon (`:`).
 *
 * We can not imagine in what situation you would want to write both
 * the namespace <em>and</em> the prefix. Nevertheless, we allow for that
 * possibility and do not throw any exception if you specify the both.
 */
struct WritingOptions {{
{I}/**
{I} * If set, the XML declaration is written at the beginning.
{I} */
{I}bool write_declaration = true;

{I}/**
{I} * If set, the root XML element is written with the XML namespace
{I} * set as the XML attribute `xmlns`.
{I} */
{I}bool write_namespace = true;

{I}/**
{I} * The prefix is prepended to the name of each XML element.
{I} */
{I} std::string prefix = "";
}};  // struct WritingOptions"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Serialize \\p that instance to XML.
 *
 * \\param that instance to be serialized
 * \\param options  to be tweaked for special cases. The defaults should
 * work in most cases.
 * \\param os The UTF8-encoded output stream where XML will be written
 * \\throw \\ref SerializationException if \\p that instance could not be serialized
 */
void Serialize(
{I}const types::IClass& that,
{I}const WritingOptions& options,
{I}std::ostream& os
);"""
        ),
        Stripped("// endregion Serialization"),
        Stripped(
            f"""\
}}  // namespace {cpp_common.XMLIZATION_NAMESPACE}
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
{I}size_t out_len = 0;
{I}for (const wchar_t character : name) {{
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
{I}if (out_len == name.size()) {{
{II}return name;
{I}}}

{I}std::wstring out;
{I}out.reserve(out_len);

{I}for (const wchar_t character : name) {{
{II}switch (character) {{
{III}case L'&':
{IIII}out.append(L"&amp;");
{IIII}break;
{III}case L'/':
{IIII}out.append(L"&#47;");
{IIII}break;
{III}case L'<':
{III}out.append(L"&lt;");
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


def _generate_deserialization_error_implementation() -> List[Stripped]:
    """Generate the impl. of the ``DeserializationError`` class."""
    return [
        Stripped("// region DeserializationError"),
        Stripped(
            f"""\
DeserializationError::DeserializationError(
{I}std::wstring a_cause
) :
{I}cause(a_cause) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
DeserializationError::DeserializationError(
{I}std::wstring a_cause,
{I}Path a_path
) :
{I}cause(a_cause),
{I}path(a_path) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped("// endregion DeserializationError"),
    ]


def _generate_forward_declarations_of_deserialization_functions(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate forward declarations of all the de-serialization functions.

    The forward declarations are necessary so that we can use them in any calling
    order.
    """
    result = [
        Stripped("// region Forward declarations of de-serialization functions"),
        Stripped(
            """\
// NOTE (mristin):
// We make forward declarations of de-serialization functions so that they can be
// called in any order."""
        ),
    ]

    for cls in symbol_table.classes:
        interface_name = cpp_naming.interface_name(cls.name)

        from_element_name = cpp_naming.function_name(
            Identifier(f"{cls.name}_from_element")
        )

        result.append(
            Stripped(
                f"""\
std::pair<
{I}common::optional<
{II}std::shared_ptr<types::{interface_name}>
{I}>,
{I}common::optional<DeserializationError>
> {from_element_name}(
{I}xml_common::ReaderMergingText& reader
);"""
            )
        )

        if isinstance(cls, intermediate.ConcreteClass):
            from_sequence_name = cpp_naming.function_name(
                Identifier(f"{cls.name}_from_sequence")
            )

            # NOTE (mristin):
            # We have to introduce the template so that we do not have to
            # unnecessarily upcast the instance to ancestor classes.
            prefix = Stripped(
                f"""\
template <
{I}typename T,
{I}typename std::enable_if<
{II}std::is_base_of<T, types::{interface_name}>::value
{I}>::type* = nullptr
>
std::pair<
{I}common::optional<std::shared_ptr<T> >,
{I}common::optional<DeserializationError>
>"""
            )

            result.append(
                Stripped(
                    f"""\
{prefix} {from_sequence_name}(
{I}xml_common::ReaderMergingText& reader
);"""
                )
            )

    for named_union in symbol_table.named_unions:
        union_name = cpp_naming.union_name(named_union.name)

        from_element_name = cpp_naming.function_name(
            Identifier(f"{named_union.name}_from_element")
        )

        result.append(
            Stripped(
                f"""\
std::pair<
{I}common::optional<types::{union_name}>,
{I}common::optional<DeserializationError>
> {from_element_name}(
{I}xml_common::ReaderMergingText& reader
);"""
            )
        )

    result.append(
        Stripped("// endregion Forward declarations of de-serialization functions")
    )

    return result


def _generate_element_name_to_model_type(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the mapping XML element name 🠒 model type."""
    items = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        literal_name = cpp_naming.enum_literal_name(cls.name)

        xml_name = naming.xml_class_name(cls.name)

        items.append(
            Stripped(
                f"""\
{{
{I}{cpp_common.string_literal(xml_name)},
{I}types::ModelType::{literal_name}
}}"""
            )
        )

    map_name = cpp_naming.constant_name(Identifier("element_name_to_model_type"))

    items_joined = ",\n".join(items)

    function_name = cpp_naming.function_name(Identifier("model_type_from_element_name"))

    return [
        Stripped(
            f"""\
/**
 * Map XML class names to model types.
 */
const std::unordered_map<
{I}std::string,
{I}types::ModelType
> {map_name} = {{
{I}{indent_but_first_line(items_joined, I)}
}};"""
        ),
        Stripped(
            f"""\
common::optional<types::ModelType> {function_name}(
{I}const std::string& element_name
) {{
{I}auto it = {map_name}.find(element_name);
{I}if (it == {map_name}.end()) {{
{II}return common::nullopt;
{I}}}

{I}return it->second;
}}"""
        ),
    ]


def _generate_instance_and_no_error() -> Stripped:
    """Generate the factory for pairs of no instance and de-serialization errors."""
    return Stripped(
        f"""\
template <
{I}typename T
>
std::pair<
{I}common::optional<T>,
{I}common::optional<DeserializationError>
> InstanceAndNoDeserializationError(
{I}T&& instance
) {{
{I}return std::make_pair<
{II}common::optional<T>,
{II}common::optional<DeserializationError>
{I}>(
{II}std::move(instance),
{II}common::nullopt
{I});
}}"""
    )


def _generate_instance_and_error_factories_and_manipulations() -> List[Stripped]:
    """
    Generate the factories and manipulations for instances and de-serialization errors.

    We generate these functions to shorten the generated code in other places as much as
    possible. This is particularly necessary for readability, as too many lines of code
    are simply unreadable.
    """
    return [
        Stripped(
            f"""\
template <
{I}typename T
> std::pair<
{I}common::optional<T>,
{I}common::optional<DeserializationError>
> NoInstanceAndDeserializationErrorWithCause(
{I}std::wstring cause
) {{
{I}return std::make_pair<
{II}common::optional<T>,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}common::make_optional<DeserializationError>(
{III}std::move(cause)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
DeserializationError DeserializationErrorFromReader(
{I}xml_common::ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected an error node at the reader cursor, but got ",
{IIII}xml_common::NodeToHumanReadableString(reader.node())
{III})
{II});
{I}}}

{I}const auto error_node(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::ErrorNode&
{II}>(reader.node())
{I});

{I}return DeserializationError(
{II}common::Utf8ToWstring(
{III}error_node.cause
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
template <
{I}typename T
>
std::pair<
{I}common::optional<T>,
{I}common::optional<DeserializationError>
> NoInstanceAndDeserializationErrorFromReader(
{I}xml_common::ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected an error node at the reader cursor, but got ",
{IIII}xml_common::NodeToHumanReadableString(reader.node())
{III})
{II});
{I}}}

{I}DeserializationError error = DeserializationErrorFromReader(
{II}reader
{I});

{I}return std::make_pair(
{II}common::nullopt,
{II}common::make_optional<DeserializationError>(
{III}std::move(error)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
template <
{I}typename T
>
std::pair<
{I}common::optional<T>,
{I}common::optional<DeserializationError>
> NoInstanceAndDeserializationError(
{I}DeserializationError error
) {{
{I}return std::make_pair(
{II}common::nullopt,
{II}common::make_optional<DeserializationError>(
{III}std::move(error)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
void PrependElementSegmentToDeserializationError(
{I}const std::string& name,
{I}DeserializationError& deserialization_error
) {{
{I}deserialization_error.path.segments.emplace_front(
{II}common::make_unique<ElementSegment>(
{III}common::Utf8ToWstring(name)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
common::optional<DeserializationError> CheckReaderAtEof(
{I}const xml_common::ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in CheckReaderAtEof. "
{III}"CheckReaderAtEof expects no reader error at entry."
{II});
{I}}}
{I}#endif

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


def _generate_skip_bof() -> Stripped:
    """Generate the function to skip the beginning-of-file and read the first node."""
    return Stripped(
        f"""\
/**
 * \\brief Skip the beginning-of-file (BoF) and read a node.
 *
 * Do nothing if the cursor points to a non-BoF node.
 *
 * Return an error if the reader produced an error.
 */
common::optional<DeserializationError> SkipBof(
{I}xml_common::ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != xml_common::NodeKind::Bof) {{
{II}return common::nullopt;
{I}}}

{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return DeserializationErrorFromReader(reader);
{I}}}

{I}return common::nullopt;
}}"""
    )


def _generate_skip_whitespace() -> List[Stripped]:
    """Generate the function to skip text nodes which contain only whitespace."""
    return [
        Stripped(
            f"""\
/**
 * Return `true` if all characters are whitespace in the UTF-8-encoded text.
 */
bool IsWhitespace(const std::string& utf8_text) {{
{I}for (const char character : utf8_text) {{
{II}switch (character) {{
{III}// NOTE (mristin):
{III}// The characters are ordered by their ASCII codes so that
{III}// we allow compilers to optimize.

{III}// NOTE (mristin):
{III}// Text nodes contain text in UTF-8 which is compatible with ASCII.
{III}// In particular, all characters above ASCII (>127) are encoded with
{III}// all the leading bits set. Hence, it is safe to check for whitespace
{III}// characters in an UTF-8-encoded string using one-byte characters.
{III}//
{III}// See: https://stackoverflow.com/questions/15965811/why-utf8-is-compatible-with-ascii

{III}case '\\t':
{III}case '\\n':
{III}case '\\r':
{III}case ' ':
{IIII}// Pass
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
 *
 * The whitespace includes space, tab, carriage return and newline.
 *
 * Return an error if the reader produced an error.
 */
common::optional<DeserializationError> SkipWhitespace(
{I}xml_common::ReaderMergingText& reader
) {{
{I}while (reader.node().kind() == xml_common::NodeKind::Text) {{
{II}const xml_common::TextNode& text_node(
{III}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIII}const xml_common::TextNode&
{III}>(
{IIII}reader.node()
{III})
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
    ]


def _generate_deserialize_class_from_element_generic() -> Stripped:
    """
    Generate a generic function to de-serialize an instance of a class from an element.

    The function factors out the common structure shared by all
    the ``{Cls}FromElement`` functions -- reading the start element, looking up
    the model type, dispatching to the concrete de-serialization and reading
    the corresponding stop element -- so that the individual ``{Cls}FromElement``
    functions only need to supply the dispatch specific to their interface.
    """
    model_type_from_element_name = cpp_naming.function_name(
        Identifier("model_type_from_element_name")
    )

    return Stripped(
        f"""\
template <typename T, typename DispatchT>
std::pair<
{I}common::optional<std::shared_ptr<T> >,
{I}common::optional<DeserializationError>
> DeserializeClassFromElement(
{I}xml_common::ReaderMergingText& reader,
{I}const std::wstring& interface_name,
{I}const DispatchT& dispatch
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeClassFromElement. "
{III}"DeserializeClassFromElement expects no reader error at entry."
{II});
{I}}}
{I}#endif

{I}common::optional<DeserializationError> error;

{I}error = SkipBof(reader);
{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(std::move(*error));
{I}}}

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(std::move(*error));
{I}}}

{I}if (reader.node().kind() != xml_common::NodeKind::Start) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}std::shared_ptr<T>
{II}>(
{III}common::Concat(
{IIII}L"Expected a start element opening an instance of ",
{IIII}interface_name,
{IIII}L", but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name
{I});

{I}common::optional<types::ModelType> model_type(
{II}{model_type_from_element_name}(name)
{I});
{I}if (!model_type.has_value()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}std::shared_ptr<T>
{II}>(
{III}common::Concat(
{III}L"Unexpected start element as its name does not correspond "
{III}L"to any model type: ",
{III}common::Utf8ToWstring(name)
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the start element.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}auto noInstanceAndError = NoInstanceAndDeserializationErrorFromReader<
{III}std::shared_ptr<T>
{II}>(
{III}reader
{II});

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*(noInstanceAndError.second)
{II});

{II}return noInstanceAndError;
{I}}}

{I}common::optional<std::shared_ptr<T> > instance;
{I}std::tie(
{II}instance,
{II}error
{I}) = dispatch(reader, *model_type, name);

{I}if (error.has_value()) {{
{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(std::move(*error));
{I}}}

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(std::move(*error));
{I}}}

{I}if (!xml_common::IsStopNodeWithName(reader.node(), name)) {{
{II}error = DeserializationError(
{III}common::Concat(
{IIII}L"Expected a stop element </",
{IIII}common::Utf8ToWstring(name),
{IIII}L"> closing an instance of ",
{IIII}interface_name,
{IIII}L", but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(std::move(*error));
{I}}}

{I}// NOTE (mristin):
{I}// We consume the stop element.
{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}error = DeserializationErrorFromReader(reader);

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(std::move(*error));
{I}}}

{I}return InstanceAndNoDeserializationError(
{II}std::move(*instance)
{I});
}}"""
    )


def _generate_class_from_element(
    interface_name: Identifier,
    function_name: Identifier,
    concrete_classes: Sequence[intermediate.ConcreteClass],
) -> Stripped:
    """
    Generate the de-serialization function from element.

    We pass in the interface and function name instead of the class so that we can also
    generate the function for the most general ``IClass``.
    """
    case_blocks = []  # type: List[Stripped]
    for cls in concrete_classes:
        cls_from_sequence = cpp_naming.function_name(
            Identifier(f"{cls.name}_from_sequence")
        )

        model_type_enum = cpp_naming.enum_name(Identifier("Model_type"))
        model_type_literal = cpp_naming.enum_literal_name(cls.name)

        case_blocks.append(
            Stripped(
                f"""\
case types::{model_type_enum}::{model_type_literal}:
{I}return {cls_from_sequence}<
{II}types::{interface_name}
{I}>(a_reader);"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}return NoInstanceAndDeserializationErrorWithCause<
{II}std::shared_ptr<types::{interface_name}>
{I}>(
{II}common::Concat(
{III}L"Impossible to de-serialize an instance "
{III}L"of {interface_name} from <",
{III}common::Utf8ToWstring(a_name),
{III}L">"
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    deserialize_class_from_element = cpp_naming.function_name(
        Identifier("deserialize_class_from_element")
    )

    return Stripped(
        f"""\
std::pair<
{I}common::optional<
{II}std::shared_ptr<types::{interface_name}>
{I}>,
{I}common::optional<DeserializationError>
> {function_name}(
{I}xml_common::ReaderMergingText& reader
) {{
{I}return {deserialize_class_from_element}<types::{interface_name}>(
{II}reader,
{II}L"{interface_name}",
{II}[](
{III}xml_common::ReaderMergingText& a_reader,
{III}types::ModelType a_model_type,
{III}const std::string& a_name
{II}) -> std::pair<
{III}common::optional<std::shared_ptr<types::{interface_name}> >,
{III}common::optional<DeserializationError>
{II}> {{
{III}switch (a_model_type) {{
{IIII}{indent_but_first_line(case_blocks_joined, IIII)}
{III}}}
{II}}}
{I});
}}"""
    )


def _generate_deserialize_union_from_element_generic() -> Stripped:
    """
    Generate a generic function to de-serialize a named union from an element.

    This mirrors :py:func:`_generate_deserialize_class_from_element_generic`,
    but returns ``optional<VariantT>`` directly instead of
    ``optional<shared_ptr<T>>`` -- a named union is a ``std::variant``, not
    a polymorphic pointer, so there is no pointer to wrap. The dispatch
    lambda supplied by the caller is responsible for constructing the right
    variant alternative.
    """
    model_type_from_element_name = cpp_naming.function_name(
        Identifier("model_type_from_element_name")
    )

    return Stripped(
        f"""\
template <typename VariantT, typename DispatchT>
std::pair<
{I}common::optional<VariantT>,
{I}common::optional<DeserializationError>
> DeserializeUnionFromElement(
{I}xml_common::ReaderMergingText& reader,
{I}const std::wstring& union_name,
{I}const DispatchT& dispatch
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeUnionFromElement. "
{III}"DeserializeUnionFromElement expects no reader error at entry."
{II});
{I}}}
{I}#endif

{I}common::optional<DeserializationError> error;

{I}error = SkipBof(reader);
{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationError<VariantT>(std::move(*error));
{I}}}

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationError<VariantT>(std::move(*error));
{I}}}

{I}if (reader.node().kind() != xml_common::NodeKind::Start) {{
{II}return NoInstanceAndDeserializationErrorWithCause<VariantT>(
{III}common::Concat(
{IIII}L"Expected a start element opening an instance of ",
{IIII}union_name,
{IIII}L", but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name
{I});

{I}common::optional<types::ModelType> model_type(
{II}{model_type_from_element_name}(name)
{I});
{I}if (!model_type.has_value()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<VariantT>(
{III}common::Concat(
{IIII}L"Unexpected start element as its name does not correspond "
{IIII}L"to any model type: ",
{IIII}common::Utf8ToWstring(name)
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the start element.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}auto noInstanceAndError = NoInstanceAndDeserializationErrorFromReader<
{III}VariantT
{II}>(
{III}reader
{II});

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*(noInstanceAndError.second)
{II});

{II}return noInstanceAndError;
{I}}}

{I}common::optional<VariantT> instance;
{I}std::tie(
{II}instance,
{II}error
{I}) = dispatch(reader, *model_type, name);

{I}if (error.has_value()) {{
{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<VariantT>(std::move(*error));
{I}}}

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<VariantT>(std::move(*error));
{I}}}

{I}if (!xml_common::IsStopNodeWithName(reader.node(), name)) {{
{II}error = DeserializationError(
{III}common::Concat(
{IIII}L"Expected a stop element </",
{IIII}common::Utf8ToWstring(name),
{IIII}L"> closing an instance of ",
{IIII}union_name,
{IIII}L", but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<VariantT>(std::move(*error));
{I}}}

{I}// NOTE (mristin):
{I}// We consume the stop element.
{I}reader.Read();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}error = DeserializationErrorFromReader(reader);

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<VariantT>(std::move(*error));
{I}}}

{I}return InstanceAndNoDeserializationError(
{II}std::move(*instance)
{I});
}}"""
    )


def _generate_wrap_deserialized_as_variant_function() -> Stripped:
    """
    Generate the generic helper to wrap a de-serialized pointer as a variant.

    Every implementer of a named union is de-serialized through its own
    ``*FromSequence`` function, and the resulting
    ``pair<optional<shared_ptr<T>>, ...>`` then needs to be wrapped into
    the union's ``std::variant`` alternative matching its own interface.
    This shape is identical for every implementer of every union (only the
    types differ), so we factor it out into a single generic function
    instead of unrolling it at each dispatch case, mirroring how
    ``DeserializeTupleN``/``SerializeTupleN`` factor out the per-item
    boilerplate for tuples.
    """
    return Stripped(
        f"""\
/**
 * \\brief Wrap a de-serialized pointer as a named union's variant alternative.
 *
 * Every implementer of a named union is de-serialized through its own
 * *FromSequence function, and the resulting
 * pair<optional<shared_ptr<T>>, ...> then needs to be wrapped into the
 * union's std::variant alternative matching its own interface.
 *
 * \\param result the result of a de-serialization call for one implementer
 * \\return the result wrapped as a variant, or the propagated error
 */
template <typename VariantT, typename T>
std::pair<
{I}common::optional<VariantT>,
{I}common::optional<DeserializationError>
> WrapDeserializedAsVariant(
{I}std::pair<
{II}common::optional<std::shared_ptr<T> >,
{II}common::optional<DeserializationError>
{I}> result
) {{
{I}if (result.first.has_value()) {{
{II}return std::make_pair<
{III}common::optional<VariantT>,
{III}common::optional<DeserializationError>
{II}>(
{III}VariantT(std::move(*result.first)),
{III}common::nullopt
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<VariantT>,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(result.second)
{I});
}}"""
    )


def _generate_deserialize_and_wrap_snippet_for_named_union_implementer(
    implementer: intermediate.ConcreteClass, union_name: Identifier
) -> Stripped:
    """
    Generate the snippet to de-serialize a single implementer and wrap it.

    The implementer's own properties are read directly through its
    ``*FromSequence`` function (no separate start/stop element -- the outer
    ``DeserializeUnionFromElement`` already consumed those), and the
    resulting pair is wrapped into the union's ``std::variant`` in one call
    via :py:func:`_generate_wrap_deserialized_as_variant_function`.
    """
    from_sequence_name = cpp_naming.function_name(
        Identifier(f"{implementer.name}_from_sequence")
    )

    implementer_interface_name = cpp_naming.interface_name(implementer.name)

    return Stripped(
        f"""\
return WrapDeserializedAsVariant<types::{union_name}>(
{I}{from_sequence_name}<
{II}types::{implementer_interface_name}
{I}>(a_reader)
);"""
    )


@require(lambda named_union: len(named_union.implementers) > 0)
def _generate_named_union_from_element(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the de-serialization function for a named union from an element.

    Every flattened implementer is self-tagging (its own XML element name),
    so dispatch is uniformly by tag regardless of whether the implementer
    also happens to carry a JSON ``modelType`` -- unlike the JSON side, there
    is no structural/modelType distinction here at all.
    """
    union_name = cpp_naming.union_name(named_union.name)

    function_name = cpp_naming.function_name(
        Identifier(f"{named_union.name}_from_element")
    )

    case_blocks = []  # type: List[Stripped]
    for implementer in named_union.implementers:
        model_type_enum = cpp_naming.enum_name(Identifier("Model_type"))
        model_type_literal = cpp_naming.enum_literal_name(implementer.name)

        snippet = _generate_deserialize_and_wrap_snippet_for_named_union_implementer(
            implementer=implementer, union_name=union_name
        )

        case_blocks.append(
            Stripped(
                f"""\
case types::{model_type_enum}::{model_type_literal}: {{
{I}{indent_but_first_line(snippet, I)}
}}"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}return NoInstanceAndDeserializationErrorWithCause<
{II}types::{union_name}
{I}>(
{II}common::Concat(
{III}L"Impossible to de-serialize an instance "
{III}L"of {union_name} from <",
{III}common::Utf8ToWstring(a_name),
{III}L">"
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
std::pair<
{I}common::optional<types::{union_name}>,
{I}common::optional<DeserializationError>
> {function_name}(
{I}xml_common::ReaderMergingText& reader
) {{
{I}return DeserializeUnionFromElement<types::{union_name}>(
{II}reader,
{II}L"{union_name}",
{II}[](
{III}xml_common::ReaderMergingText& a_reader,
{III}types::ModelType a_model_type,
{III}const std::string& a_name
{II}) -> std::pair<
{III}common::optional<types::{union_name}>,
{III}common::optional<DeserializationError>
{II}> {{
{III}switch (a_model_type) {{
{IIII}{indent_but_first_line(case_blocks_joined, IIII)}
{III}}}
{II}}}
{I});
}}"""
    )


def _generate_functions_to_deserialize_primitives() -> List[Stripped]:
    """Generate functions to parse text nodes to primitives."""
    return [
        Stripped("// region De-serialize primitives"),
        Stripped(
            f"""\
const std::unordered_map<
{I}std::string,
{I}bool
> kTextToBool = {{
{I}{{"true", true}},
{I}{{"false", false}},
{I}{{"1", true}},
{I}{{"0", false}}
}};"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<bool>,
{I}common::optional<DeserializationError>
> DeserializeBool(
{I}xml_common::ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeBool. "
{III}"DeserializeBool expects no error node."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != xml_common::NodeKind::Text) {{
{II}return NoInstanceAndDeserializationErrorWithCause<bool>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:boolean from XML text, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::TextNode&
{II}>(reader.node()).text
{I});

{I}auto it = kTextToBool.find(text);
{I}if (it == kTextToBool.end()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<bool>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:boolean from text, "
{IIII}L"but got an invalid value: ",
{IIII}common::Utf8ToWstring(text)
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return NoInstanceAndDeserializationErrorFromReader<bool>(reader);
{I}}}

{I}return std::make_pair(
{II}it->second,
{II}common::nullopt
{I});
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<int64_t>,
{I}common::optional<DeserializationError>
> DeserializeInt64(
{I}xml_common::ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeInt64. "
{III}"DeserializeInt64 expects no error node."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != xml_common::NodeKind::Text) {{
{II}return NoInstanceAndDeserializationErrorWithCause<int64_t>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:long from XML text, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::TextNode&
{II}>(reader.node()).text
{I});

{I}common::optional<int64_t> deserialized;

{I}static_assert(
{II}sizeof(int) == 8
{II}|| sizeof(long) == 8
{II}|| sizeof(long long) == 8,
{II}"Neither int nor long nor long long are 8 bytes long, "
{II}"so we do not know how to parse an xs:long."
{I});

{I}try {{
{II}// NOTE (mristin):
{II}// We remove the warning C4101 in MSVC with constants.
{II}// See: https://stackoverflow.com/questions/25573996/c4127-conditional-expression-is-constant
{II}const bool sizeof_int_is_8 = sizeof(int) == 8;
{II}const bool sizeof_long_is_8 = sizeof(long) == 8;
{II}const bool sizeof_long_long_is_8 = sizeof(long long) == 8;

{II}if (sizeof_int_is_8) {{
{III}deserialized = std::stoi(text);
{II}}} else if (sizeof_long_is_8) {{
{III}deserialized = std::stol(text);
{II}}} else if (sizeof_long_long_is_8) {{
{III}deserialized = std::stoll(text);
{II}}}
{I}}} catch (std::invalid_argument&) {{
{II}return NoInstanceAndDeserializationErrorWithCause<int64_t>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:long from text, "
{IIII}L"but got an invalid value: ",
{IIII}common::Utf8ToWstring(text)
{III})
{II});
{I}}} catch (std::out_of_range&) {{
{II}return NoInstanceAndDeserializationErrorWithCause<int64_t>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:long from text, "
{IIII}L"but got a value out of the xs:long range: ",
{IIII}common::Utf8ToWstring(text)
{III})
{II});
{I}}}

{I}if (!deserialized.has_value()) {{
{II}throw std::logic_error(
{III}"Neither int nor long nor long long are 8 bytes long, "
{III}"but this should have been caught earlier in the static assert"
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return NoInstanceAndDeserializationErrorFromReader<int64_t>(reader);
{I}}}

{I}return std::make_pair(
{II}deserialized,
{II}common::nullopt
{I});
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<double>,
{I}common::optional<DeserializationError>
> DeserializeDouble(
{I}xml_common::ReaderMergingText& reader
) {{
{I}static_assert(
{II}sizeof(double) == 8,
{II}"DeserializeDouble expects double to be 8 bytes, "
{II}"but the size of the double is not 8 bytes"
{I});

{I}#ifdef DEBUG
{I}if (node.kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeDouble. "
{III}"DeserializeDouble expects no error node."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != xml_common::NodeKind::Text) {{
{II}return NoInstanceAndDeserializationErrorWithCause<double>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:double from XML text, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
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
{II}return NoInstanceAndDeserializationErrorWithCause<double>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:double from text, "
{IIII}L"but got an invalid value: ",
{IIII}common::Utf8ToWstring(text)
{III})
{II});
{I}}} catch (std::out_of_range&) {{
{II}return NoInstanceAndDeserializationErrorWithCause<double>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:double from text, "
{IIII}L"but got a value out of the xs:double range: ",
{IIII}common::Utf8ToWstring(text)
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// XSD basic types are not case insensitive and quite strict.
{I}// We follow this strictness in the parsing as well.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema11-2/#double

{I}const bool invalid_xml(
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

{I}if (invalid_xml) {{
{II}return NoInstanceAndDeserializationErrorWithCause<double>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:double from text, "
{IIII}L"but got an invalid value: ",
{IIII}common::Utf8ToWstring(text)
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return NoInstanceAndDeserializationErrorFromReader<double>(reader);
{I}}}

{I}return std::make_pair(
{II}deserialized,
{II}common::nullopt
{I});
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<std::wstring>,
{I}common::optional<DeserializationError>
> DeserializeWstring(
{I}xml_common::ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeWstring. "
{III}"DeserializeWstring expects no error node."
{II});
{I}}}
{I}#endif

{I}switch (reader.node().kind()) {{
{II}case xml_common::NodeKind::Stop:
{III}// Encountering a stop node means that the string is empty.
{III}return std::make_pair(std::wstring(), common::nullopt);
{II}case xml_common::NodeKind::Text:
{III}// We pass and continue decoding the text.
{III}break;
{II}default:
{III}return NoInstanceAndDeserializationErrorWithCause<std::wstring>(
{IIII}common::Concat(
{IIIII}L"Expected to parse an xs:string from XML text, but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::TextNode&
{II}>(reader.node()).text
{I});

{I}std::wstring deserialized = common::Utf8ToWstring(text);

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return NoInstanceAndDeserializationErrorFromReader<std::wstring>(reader);
{I}}}

{I}return std::make_pair(std::move(deserialized), common::nullopt);
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<std::vector<std::uint8_t> >,
{I}common::optional<DeserializationError>
> DeserializeByteArray(
{I}xml_common::ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeByteArray. "
{III}"DeserializeByteArray expects no error node."
{II});
{I}}}
{I}#endif

{I}switch (reader.node().kind()) {{
{II}case xml_common::NodeKind::Stop:
{III}// Encountering a stop node means empty byte array.
{III}return std::make_pair(
{IIII}std::vector<std::uint8_t>(),
{IIII}common::nullopt
{III});
{II}case xml_common::NodeKind::Text:
{III}// We pass and continue decoding the byte array.
{III}break;
{II}default:
{III}return NoInstanceAndDeserializationErrorWithCause<
{IIII}std::vector<std::uint8_t>
{III}>(
{IIII}common::Concat(
{IIIII}L"Expected to parse an xs:base64Binary from XML text, but got ",
{IIIIII}xml_common::NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::TextNode&
{II}>(reader.node()).text
{I});

{I}common::expected<
{II}std::vector<std::uint8_t>,
{II}std::string
{I}> deserialized = stringification::Base64Decode(text);

{I}if (!deserialized.has_value()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}std::vector<std::uint8_t>
{II}>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:base64Binary from text, "
{IIII}L"but the value was invalid: ",
{IIII}common::Utf8ToWstring(deserialized.error())
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return NoInstanceAndDeserializationErrorFromReader<
{III}std::vector<std::uint8_t>
{II}>(reader);
{I}}}

{I}return std::make_pair(
{II}std::move(*deserialized),
{II}common::nullopt
{I});
}}"""
        ),
        Stripped("// endregion De-serialize primitives"),
    ]


def _generate_deserialize_atomic_value_from_v_element() -> Stripped:
    """
    Generate the function to deserialize non-class atomic values from a named
    element such as ``<v>`` (for list items) or ``<v1>``, ``<v2>``, *etc.*
    (for tuple items).
    """
    return Stripped(
        f"""\
template <typename T, typename DeserializeT>
std::pair<
{I}common::optional<T>,
{I}common::optional<DeserializationError>
> DeserializeValueFromVElement(
{I}xml_common::ReaderMergingText& reader,
{I}const DeserializeT& deserialize_content,
{I}const std::string& expected_name
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeWstring. "
{III}"DeserializeWstring expects no error node."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != xml_common::NodeKind::Start) {{
{II}return NoInstanceAndDeserializationErrorWithCause<T>(
{III}common::Concat(
{IIII}L"Expected a start element <",
{IIII}common::Utf8ToWstring(expected_name),
{IIII}L"> enclosing a value, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& start_name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name
{I});

{I}if (start_name != expected_name) {{
{II}return NoInstanceAndDeserializationErrorWithCause<T>(
{III}common::Concat(
{IIII}L"Expected a start element <",
{IIII}common::Utf8ToWstring(expected_name),
{IIII}L"> enclosing a value, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the start element.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return NoInstanceAndDeserializationErrorFromReader<T>(reader);
{I}}}

{I}common::optional<T> value;
{I}common::optional<DeserializationError> error;
{I}std::tie(
{II}value,
{II}error
{I}) = deserialize_content(reader);

{I}if (error.has_value()) {{
{II}error->path.segments.emplace_front(
{III}common::make_unique<ElementSegment>(
{IIII}common::Utf8ToWstring(expected_name)
{III})
{II});

{II}return NoInstanceAndDeserializationError<T>(
{III}std::move(*error)
{II});
{I}}}

{I}if (reader.node().kind() != xml_common::NodeKind::Stop) {{
{II}return NoInstanceAndDeserializationErrorWithCause<T>(
{III}common::Concat(
{IIII}L"Expected a closing element </",
{IIII}common::Utf8ToWstring(expected_name),
{IIII}L"> closing a value, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& stop_name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StopNode&
{II}>(reader.node()).name
{I});


{I}if (stop_name != expected_name) {{
{II}return NoInstanceAndDeserializationErrorWithCause<T>(
{III}common::Concat(
{IIII}L"Expected a closing element </",
{IIII}common::Utf8ToWstring(expected_name),
{IIII}L"> closing a value, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the closing element.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return NoInstanceAndDeserializationErrorFromReader<T>(reader);
{I}}}

{I}return std::make_pair(std::move(value), common::nullopt);
}}"""
    )


def _generate_deserialize_list() -> Stripped:
    """Generate a generic function to deserialize the lists."""
    return Stripped(
        f"""\
template <typename T, typename DeserializeT>
std::pair<
{I}common::optional<std::vector<T> >,
{I}common::optional<DeserializationError>
> DeserializeList(
{I}xml_common::ReaderMergingText& reader,
{I}const DeserializeT& deserialize_item
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeWstring. "
{III}"DeserializeWstring expects no error node."
{II});
{I}}}
{I}#endif

{I}common::optional<DeserializationError> error;

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}std::move(error)
{II});
{I}}}

{I}// If we encounter the stop element then we reached the end of the list. If this is
{I}// the first node we encounter then the list is empty, *i.e.*, contains no items.
{I}if (reader.node().kind() == xml_common::NodeKind::Stop) {{
{II}return std::make_pair(
{III}std::vector<T>(),
{III}common::nullopt
{II});
{I}}} else {{
{II}// NOTE (mristin):
{II}// We use std::deque here as it is a buffered list, while a std::list
{II}// would incur a memory allocation on each push. We do not want to use
{II}// std::vector as the number of elements in a list can be arbitrarily large
{II}// leading potentially to out-of-memory errors since std::vector's double
{II}// their size for amortized time complexity of O(1) for insertions.

{II}std::deque<T> items;

{II}size_t i = 0;

{II}while (true) {{
{III}common::optional<T> item;

{III}std::tie(
{IIII}item,
{IIII}error
{III}) = deserialize_item(reader);

{III}if (error.has_value()) {{
{IIII}error->path.segments.emplace_front(
{IIIII}common::make_unique<IndexSegment>(i)
{IIII});
{IIII}break;
{III}}}

{III}error = SkipWhitespace(reader);
{III}if (error.has_value()) {{
{IIII}break;
{III}}}

{III}items.emplace_back(*item);

{III}if (reader.node().kind() == xml_common::NodeKind::Stop) {{
{IIII}break;
{III}}}

{III}++i;
{II}}}

{II}if (!error.has_value()) {{
{III}auto result = std::vector<T>();
{III}result.reserve(items.size());

{III}for (auto& item : items) {{
{IIII}result.emplace_back(
{IIIII}std::move(item)
{IIII});
{II}}}

{III}return std::make_pair(
{IIII}std::move(result),
{IIII}common::nullopt
{III});
{II}}} else {{
{III}return std::make_pair(
{IIII}common::nullopt,
{IIII}std::move(error)
{III});
{II}}}
{I}}}
}}"""
    )


def _generate_deserialize_tuple_function(arity: int) -> Stripped:
    """
    Generate a generic function to de-serialize a tuple of the given ``arity``.

    Each positional item is de-serialized by its own ``deserialize_item{i}``
    callable, which is expected to have already consumed its own opening and
    closing tags (if any) -- see, for example, ``DeserializeValueFromVElement``
    or a ``*_from_element`` function, both of which conform to this shape.
    """
    assert arity > 0

    # NOTE (mristin):
    # ``T{i}`` only appears in the return type (a non-deduced context), so it
    # must always be given explicitly at the call site, while ``DeserializeT{i}``
    # is deduced from the corresponding callable argument. Explicit template
    # arguments bind positionally to the *first* declared template parameters,
    # so all the ``T{i}`` must precede all the ``DeserializeT{i}`` for a call
    # site that only specifies ``T0, ..., T{arity-1}`` to work.
    template_params_joined = ",\n".join(
        [f"typename T{i}" for i in range(arity)]
        + [f"typename DeserializeT{i}" for i in range(arity)]
    )

    item_types_joined = ",\n".join(f"T{i}" for i in range(arity))

    parameters = ",\n".join(
        f"const DeserializeT{i}& deserialize_item{i}" for i in range(arity)
    )

    item_declarations = "\n".join(
        f"common::optional<T{i}> item{i};" for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
std::tie(
{I}item{i},
{I}error
) = deserialize_item{i}(reader);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<IndexSegment>(
{III}{i}
{II})
{I});
{I}return std::make_pair(
{II}common::nullopt,
{II}std::move(error)
{I});
}}

error = SkipWhitespace(reader);
if (error.has_value()) {{
{I}return std::make_pair(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    tuple_items_joined = ",\n".join(f"std::move(*item{i})" for i in range(arity))

    function_name = f"DeserializeTuple{arity}"

    return Stripped(
        f"""\
template <
{I}{indent_but_first_line(template_params_joined, I)}
>
std::pair<
{I}common::optional<std::tuple<
{II}{indent_but_first_line(item_types_joined, II)}
{I}> >,
{I}common::optional<DeserializationError>
> {function_name}(
{I}xml_common::ReaderMergingText& reader,
{I}{indent_but_first_line(parameters, I)}
) {{
{I}common::optional<DeserializationError> error;

{I}{indent_but_first_line(item_declarations, I)}

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}std::move(error)
{II});
{I}}}

{I}{indent_but_first_line(item_blocks_joined, I)}

{I}return std::make_pair(
{II}std::make_tuple(
{III}{indent_but_first_line(tuple_items_joined, III)}
{II}),
{II}common::nullopt
{I});
}}"""
    )


def _generate_deserialize_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    function_name = cpp_naming.function_name(
        Identifier(f"deserialize_{enumeration.name}")
    )

    enum_name = cpp_naming.enum_name(enumeration.name)

    enum_from_wstring = cpp_naming.function_name(
        Identifier(f"{enumeration.name}_from_wstring")
    )

    return Stripped(
        f"""\
std::pair<
{I}common::optional<types::{enum_name}>,
{I}common::optional<DeserializationError>
> {function_name}(
{I}xml_common::ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeByteArray. "
{III}"DeserializeByteArray expects no error node."
{II});
{I}}}
{I}#endif

{I}common::optional<std::wstring> text;
{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}text,
{II}error
{I}) = DeserializeWstring(reader);

{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}types::{enum_name}
{II}>(
{III}common::Concat(
{IIII}L"Failed to de-serialize a literal of {enum_name}: ",
{IIII}error->cause
{III})
{II});
{I}}}

{I}common::optional<
{II}types::{enum_name}
{I}> deserialized = wstringification::{enum_from_wstring}(
{II}*text
{I});

{I}if (!deserialized.has_value()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}types::{enum_name}
{II}>(
{III}common::Concat(
{IIII}L"Expected a literal of {enum_name}, but got: ",
{IIII}*text
{III})
{II});
{I}}}

{I}return std::make_pair(std::move(deserialized), common::nullopt);
}}"""
    )


_PRIMITIVE_TYPE_TO_DESERIALIZE: Final[Mapping[intermediate.PrimitiveType, Stripped]] = {
    intermediate.PrimitiveType.BOOL: Stripped("DeserializeBool"),
    intermediate.PrimitiveType.INT: Stripped("DeserializeInt64"),
    intermediate.PrimitiveType.FLOAT: Stripped("DeserializeDouble"),
    intermediate.PrimitiveType.STR: Stripped("DeserializeWstring"),
    intermediate.PrimitiveType.BYTEARRAY: Stripped("DeserializeByteArray"),
}
assert all(
    primitive_type in _PRIMITIVE_TYPE_TO_DESERIALIZE
    for primitive_type in intermediate.PrimitiveType
)


def _xml_json_deserialize_function_for(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """
    Determine the function to de-serialize the given JSON-able ``type_anno``.

    Each of these functions wraps the corresponding ``xml_rpc`` function,
    converting a caught ``xml_rpc::DeserializationError`` into this module's
    own ``DeserializationError`` -- see
    :py:func:`_generate_deserialize_json_from_xml_rpc_implementation`.
    """
    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return Stripped("DeserializeJsonValueFromXmlRpc")
    elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return Stripped("DeserializeJsonArrayFromXmlRpc")
    elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        return Stripped("DeserializeJsonObjectFromXmlRpc")
    else:
        raise AssertionError(
            f"Expected a JSON-able type annotation, but got: {type_anno}"
        )


def _xml_json_serialize_function_for(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """
    Determine the function to serialize the given JSON-able ``type_anno``.

    Each of these functions wraps the corresponding ``xml_rpc`` function,
    converting a caught ``xml_rpc::SerializationError`` into this module's
    own ``xml_common::SerializationError`` -- see
    :py:func:`_generate_serialize_json_to_xml_rpc_implementation`.
    """
    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return Stripped("SerializeJsonValueToXmlRpc")
    elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return Stripped("SerializeJsonArrayToXmlRpc")
    elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        return Stripped("SerializeJsonObjectToXmlRpc")
    else:
        raise AssertionError(
            f"Expected a JSON-able type annotation, but got: {type_anno}"
        )


def _generate_convert_xml_rpc_deserialization_error_implementation() -> Stripped:
    """
    Generate the conversion of ``xml_rpc``'s own de-serialization error.

    ``xml_rpc`` is meant to be usable independent of any particular
    meta-model, so it necessarily has its own, separate ``DeserializationError``
    (with its own path vocabulary, over JSON array indices and object keys,
    instead of this module's own class properties). We fold that JSON-relative
    path into the message here instead of trying to unify the two incompatible
    path vocabularies.
    """
    return Stripped(
        f"""\
DeserializationError ConvertXmlRpcDeserializationError(
{I}xml_rpc::DeserializationError&& error
) {{
{I}std::wstring path_str = error.path.ToWstring();

{I}if (path_str.empty()) {{
{II}return DeserializationError(std::move(error.cause));
{I}}}

{I}return DeserializationError(
{II}common::Concat(
{III}std::move(error.cause),
{III}L" (at the JSON path ",
{III}path_str,
{III}L")"
{II})
{I});
}}"""
    )


def _generate_convert_xml_rpc_serialization_error_implementation() -> Stripped:
    """
    Generate the conversion of ``xml_rpc``'s own serialization error.

    See :py:func:`_generate_convert_xml_rpc_deserialization_error_implementation`
    for why this conversion (rather than a unified path vocabulary) is necessary.
    """
    return Stripped(
        f"""\
xml_common::SerializationError ConvertXmlRpcSerializationError(
{I}xml_rpc::SerializationError&& error
) {{
{I}std::wstring path_str = error.path.ToWstring();

{I}if (path_str.empty()) {{
{II}return xml_common::SerializationError(std::move(error.cause));
{I}}}

{I}return xml_common::SerializationError(
{II}common::Concat(
{III}std::move(error.cause),
{III}L" (at the JSON path ",
{III}path_str,
{III}L")"
{II})
{I});
}}"""
    )


def _generate_deserialize_json_from_xml_rpc_implementation() -> List[Stripped]:
    """Generate the ``xml_rpc``-wrapping JSON-able de-serialization functions."""
    return [
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeJsonValueFromXmlRpc(
{I}xml_common::ReaderMergingText& reader
) {{
{I}common::optional<nlohmann::json> value;
{I}common::optional<xml_rpc::DeserializationError> xml_rpc_error;
{I}std::tie(value, xml_rpc_error) = xml_rpc::DeserializeValueFrom(reader);

{I}if (xml_rpc_error.has_value()) {{
{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}ConvertXmlRpcDeserializationError(std::move(*xml_rpc_error))
{II});
{I}}}

{I}return std::make_pair(std::move(value), common::nullopt);
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeJsonArrayFromXmlRpc(
{I}xml_common::ReaderMergingText& reader
) {{
{I}common::optional<nlohmann::json> value;
{I}common::optional<xml_rpc::DeserializationError> xml_rpc_error;
{I}std::tie(value, xml_rpc_error) = xml_rpc::DeserializeArrayBodyFrom(reader);

{I}if (xml_rpc_error.has_value()) {{
{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}ConvertXmlRpcDeserializationError(std::move(*xml_rpc_error))
{II});
{I}}}

{I}return std::make_pair(std::move(value), common::nullopt);
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeJsonObjectFromXmlRpc(
{I}xml_common::ReaderMergingText& reader
) {{
{I}common::optional<nlohmann::json> value;
{I}common::optional<xml_rpc::DeserializationError> xml_rpc_error;
{I}std::tie(value, xml_rpc_error) = xml_rpc::DeserializeStructBodyFrom(reader);

{I}if (xml_rpc_error.has_value()) {{
{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}ConvertXmlRpcDeserializationError(std::move(*xml_rpc_error))
{II});
{I}}}

{I}return std::make_pair(std::move(value), common::nullopt);
}}"""
        ),
    ]


def _generate_serialize_json_to_xml_rpc_implementation() -> List[Stripped]:
    """Generate the ``xml_rpc``-wrapping JSON-able serialization functions."""
    return [
        Stripped(
            f"""\
common::optional<xml_common::SerializationError> SerializeJsonValueToXmlRpc(
{I}const nlohmann::json& value,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}common::optional<xml_rpc::SerializationError> xml_rpc_error(
{II}xml_rpc::SerializeValueBodyTo(writer, value)
{I});

{I}if (xml_rpc_error.has_value()) {{
{II}return common::make_optional<xml_common::SerializationError>(
{III}ConvertXmlRpcSerializationError(std::move(*xml_rpc_error))
{II});
{I}}}

{I}return common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
common::optional<xml_common::SerializationError> SerializeJsonArrayToXmlRpc(
{I}const nlohmann::json& value,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}common::optional<xml_rpc::SerializationError> xml_rpc_error(
{II}xml_rpc::SerializeArrayBodyTo(writer, value)
{I});

{I}if (xml_rpc_error.has_value()) {{
{II}return common::make_optional<xml_common::SerializationError>(
{III}ConvertXmlRpcSerializationError(std::move(*xml_rpc_error))
{II});
{I}}}

{I}return common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
common::optional<xml_common::SerializationError> SerializeJsonObjectToXmlRpc(
{I}const nlohmann::json& value,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}common::optional<xml_rpc::SerializationError> xml_rpc_error(
{II}xml_rpc::SerializeStructBodyTo(writer, value)
{I});

{I}if (xml_rpc_error.has_value()) {{
{II}return common::make_optional<xml_common::SerializationError>(
{III}ConvertXmlRpcSerializationError(std::move(*xml_rpc_error))
{II});
{I}}}

{I}return common::nullopt;
}}"""
        ),
    ]


def _generate_property_enums_from_strings(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the property enums for each class and their mapping from strings."""
    result = [
        Stripped("namespace properties {"),
    ]

    for cls in symbol_table.concrete_classes:
        enum_name = cpp_naming.enum_name(Identifier(f"Of_{cls.name}"))

        literals = []  # type: List[Stripped]
        for i, prop in enumerate(cls.properties):
            literal_name = cpp_naming.enum_literal_name(prop.name)
            literals.append(Stripped(f"{literal_name} = {i}"))

        literals_joined = ",\n".join(literals)

        result.append(
            Stripped(
                f"""\
enum class {enum_name} : std::uint32_t {{
{I}{indent_but_first_line(literals_joined, I)}
}};  // enum class {enum_name}"""
            )
        )

    for cls in symbol_table.concrete_classes:
        enum_name = cpp_naming.enum_name(Identifier(f"Of_{cls.name}"))

        map_name = cpp_naming.constant_name(Identifier(f"map_of_{cls.name}"))

        items = []  # type: List[Stripped]
        for prop in cls.properties:
            literal_name = cpp_naming.enum_literal_name(prop.name)
            xml_prop = prop.xml_name

            items.append(
                Stripped(
                    f"""\
{{
{I}{cpp_common.string_literal(xml_prop)},
{I}{enum_name}::{literal_name}
}}"""
                )
            )

        items_joined = ",\n".join(items)

        result.append(
            Stripped(
                f"""\
const std::unordered_map<
{I}std::string,
{I}{enum_name}
> {map_name} = {{
{I}{indent_but_first_line(items_joined, I)}
}};"""
            )
        )

    result.append(Stripped("}  // namespace properties"))

    return result


def _xml_deserialize_item_expr(
    item_type_anno: intermediate.AtomicTypeAnnotation,
    item_type: Stripped,
    v_element_name: str,
) -> Stripped:
    """
    Generate the expression of the callable to de-serialize an atomic item from XML.

    The ``v_element_name`` denotes the wrapping element expected for a non-class
    atomic value (*e.g.*, ``v`` for a list item or ``v1``, ``v2``, *etc.* for
    a tuple item). Class items ignore ``v_element_name`` as they are de-serialized
    directly from their own element.
    """
    items_primitive_type = intermediate.try_primitive_type(item_type_anno)

    if items_primitive_type is not None:
        deserialize_text = _PRIMITIVE_TYPE_TO_DESERIALIZE[items_primitive_type]

        v_element_name_literal = cpp_common.string_literal(v_element_name)

        return Stripped(
            f"""\
[](xml_common::ReaderMergingText& a_reader) {{
{I}return DeserializeValueFromVElement<
{II}{indent_but_first_line(item_type, II)}
{I}>(
{II}a_reader,
{II}{deserialize_text},
{II}{v_element_name_literal}
{I});
}}"""
        )

    if isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("Expected to handle this case before")

    elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
        if isinstance(item_type_anno.our_type, intermediate.Enumeration):
            deserialize_text = cpp_naming.function_name(
                Identifier(f"deserialize_{item_type_anno.our_type.name}")
            )

            v_element_name_literal = cpp_common.string_literal(v_element_name)

            return Stripped(
                f"""\
[](xml_common::ReaderMergingText& a_reader) {{
{I}return DeserializeValueFromVElement<
{II}{indent_but_first_line(item_type, II)}
{I}>(
{II}a_reader,
{II}{deserialize_text},
{II}{v_element_name_literal}
{I});
}}"""
            )

        elif isinstance(item_type_anno.our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(
            item_type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            return cpp_naming.function_name(
                Identifier(f"{item_type_anno.our_type.name}_from_element")
            )

        elif isinstance(item_type_anno.our_type, intermediate.NamedUnion):
            return cpp_naming.function_name(
                Identifier(f"{item_type_anno.our_type.name}_from_element")
            )

        else:
            # noinspection PyTypeChecker
            assert_never(item_type_anno.our_type)

    elif isinstance(
        item_type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        deserialize_json = _xml_json_deserialize_function_for(item_type_anno)

        v_element_name_literal = cpp_common.string_literal(v_element_name)

        return Stripped(
            f"""\
[](xml_common::ReaderMergingText& a_reader) {{
{I}return DeserializeValueFromVElement<
{II}{indent_but_first_line(item_type, II)}
{I}>(
{II}a_reader,
{II}{deserialize_json},
{II}{v_element_name_literal}
{I});
}}"""
        )

    else:
        # noinspection PyTypeChecker
        assert_never(item_type_anno)

    raise AssertionError("Should not have gotten here")


def _generate_deserialize_list_property(
    prop: intermediate.Property,
) -> Stripped:
    """
    Generate the de-serialization snippet for a property annotated with a list type.

    Return the code as well as whether the snippet needs a proper scope as it will
    define its own variables.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.ListTypeAnnotation)

    # NOTE (mristin):
    # The variable corresponding to the list property is an optional std::vector.

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

    item_type = cpp_common.generate_type(
        type_annotation=type_anno.items, types_namespace=cpp_common.TYPES_NAMESPACE
    )

    if not isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple):
        raise NotImplementedError(
            "NOTE (mristin): We currently generate XML de-serialization only for "
            f"the lists of atomic values, but we got: {prop.type_annotation}. "
            f"Please contact the developers if you need this feature."
        )

    deserialize_item_expr = _xml_deserialize_item_expr(
        item_type_anno=type_anno.items, item_type=item_type, v_element_name="v"
    )

    return Stripped(
        f"""\
std::tie(
{I}{var_name},
{I}error
) = DeserializeList<
{I}{indent_but_first_line(item_type, I)}
>(
{I}reader,
{I}{indent_but_first_line(deserialize_item_expr, I)}
);"""
    )


def _generate_deserialize_tuple_property(
    prop: intermediate.Property,
) -> Stripped:
    """
    Generate the de-serialization snippet for a property annotated with a tuple type.

    Non-class items are wrapped in ``<v1>``, ``<v2>``, *etc.* elements (1-based),
    while class items are de-serialized directly from their own element, mirroring
    how lists of classes are handled. The actual per-item de-serialization and
    error-path bookkeeping is delegated to the generic ``DeserializeTupleN``
    function generated once for the tuple's arity by
    :py:func:`_generate_deserialize_tuple_function`.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.TupleTypeAnnotation)

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

    item_types = []  # type: List[Stripped]
    item_exprs = []  # type: List[Stripped]

    for i, item_type_anno in enumerate(type_anno.items):
        assert isinstance(item_type_anno, intermediate.AtomicTypeAnnotationAsTuple), (
            "Tuple items are restricted to atomic types (primitives, "
            "constrained primitives, classes and enumerations) by "
            "intermediate._translate._verify_only_simple_type_patterns, so no "
            "nested optionals, lists or tuples are expected here."
        )

        item_type = cpp_common.generate_type(
            type_annotation=item_type_anno, types_namespace=cpp_common.TYPES_NAMESPACE
        )
        item_types.append(item_type)

        item_exprs.append(
            _xml_deserialize_item_expr(
                item_type_anno=item_type_anno,
                item_type=item_type,
                v_element_name=f"v{i + 1}",
            )
        )

    item_types_joined = ",\n".join(item_types)
    item_exprs_joined = ",\n".join(item_exprs)

    function_name = f"DeserializeTuple{len(type_anno.items)}"

    return Stripped(
        f"""\
std::tie(
{I}{var_name},
{I}error
) = {function_name}<
{I}{indent_but_first_line(item_types_joined, I)}
>(
{I}reader,
{I}{indent_but_first_line(item_exprs_joined, I)}
);"""
    )


def _generate_deserialize_property(
    prop: intermediate.Property,
) -> Stripped:
    """
    Generate the de-serialization snippet for the given property.

    The ``ok_type`` denotes the type of the return value if no errors. This includes
    upcast template parameter if the class contains ancestors.
    """
    # NOTE (mristin):
    # The variable ``name`` denotes the start element opening the property.

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    primitive_type = intermediate.try_primitive_type(type_anno)

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

    if primitive_type is not None:
        deserialize_function = _PRIMITIVE_TYPE_TO_DESERIALIZE[primitive_type]

        return Stripped(
            f"""\
std::tie(
{I}{var_name},
{I}error
) = {deserialize_function}(reader);"""
        )

    else:
        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                deserialize_function = cpp_naming.function_name(
                    Identifier(f"deserialize_{type_anno.our_type.name}")
                )

                return Stripped(
                    f"""\
std::tie(
{I}{var_name},
{I}error
) = {deserialize_function}(reader);"""
                )

            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError("Expected to handle this case before")

            elif isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                if len(type_anno.our_type.concrete_descendants) == 0:
                    from_sequence_name = cpp_naming.function_name(
                        Identifier(f"{type_anno.our_type.name}_from_sequence")
                    )

                    interface_name = cpp_naming.interface_name(type_anno.our_type.name)
                    return Stripped(
                        f"""\
std::tie(
{I}{var_name},
{I}error
) = {from_sequence_name}<
{I}types::{interface_name}
>(reader);"""
                    )
                else:
                    from_element_name = cpp_naming.function_name(
                        Identifier(f"{type_anno.our_type.name}_from_element")
                    )

                    return Stripped(
                        f"""\
std::tie(
{I}{var_name},
{I}error
) = {from_element_name}(reader);"""
                    )

            elif isinstance(type_anno.our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # A named union always takes the dispatching ``*FromElement`` path,
                # regardless of how many implementers it flattens to -- it must
                # always be de/serialized with an explicit discriminator tag.
                from_element_name = cpp_naming.function_name(
                    Identifier(f"{type_anno.our_type.name}_from_element")
                )

                return Stripped(
                    f"""\
std::tie(
{I}{var_name},
{I}error
) = {from_element_name}(reader);"""
                )

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            return _generate_deserialize_list_property(
                prop=prop,
            )
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            return _generate_deserialize_tuple_property(
                prop=prop,
            )
        elif isinstance(
            type_anno,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            deserialize_function = _xml_json_deserialize_function_for(type_anno)

            return Stripped(
                f"""\
std::tie(
{I}{var_name},
{I}error
) = {deserialize_function}(reader);"""
            )
        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_from_sequence(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the de-serialization of a sequence of XML elements as properties."""
    if cls.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"xmlization/{cls.name}_from_sequence.cpp"
        )

        code = spec_impls.get(implementation_key, None)
        if code is None:
            return None, Error(
                cls.parsed.node,
                f"The implementation is missing for the XML de-serialization "
                f"of {cls.name!r}: {implementation_key}",
            )
        return code, None

    function_name = cpp_naming.function_name(Identifier(f"{cls.name}_from_sequence"))

    blocks = [
        Stripped(
            f"""\
#ifdef DEBUG
if (reader.node().kind() == xml_common::NodeKind::Error) {{
{I}throw std::logic_error(
{II}"Unexpected unhandled XML error in {function_name}. "
{II}"{function_name} expects no reader error at entry."
{I});
}}
#endif"""
        ),
        Stripped("common::optional<DeserializationError> error;"),
        Stripped(
            f"""\
error = SkipBof(reader);
if (error.has_value()) {{
{I}return NoInstanceAndDeserializationError<
{II}std::shared_ptr<T>
{I}>(
{II}std::move(*error)
{I});
}}"""
        ),
    ]  # type: List[Stripped]

    interface_name = cpp_naming.interface_name(cls.name)

    # region Initialization
    if len(cls.properties) > 0:
        blocks.append(Stripped("// region Initialization"))

        init_statements = []  # type: List[Stripped]

        for prop in cls.properties:
            var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))
            var_type = cpp_common.generate_type(
                type_annotation=prop.type_annotation,
                types_namespace=cpp_common.TYPES_NAMESPACE,
            )

            if not isinstance(
                prop.type_annotation, intermediate.OptionalTypeAnnotation
            ):
                if "\n" in var_type:
                    var_type = Stripped(
                        f"""\
common::optional<
{I}{indent_but_first_line(var_type, I)}
>"""
                    )
                else:
                    if var_type.endswith(">"):
                        var_type = Stripped(f"common::optional<{var_type} >")
                    else:
                        var_type = Stripped(f"common::optional<{var_type}>")

            init_statements.append(Stripped(f"{var_type} {var_name};"))

        blocks.append(Stripped("\n\n".join(init_statements)))
        blocks.append(Stripped("// endregion Initialization"))
    # endregion

    # region Case blocks for respective properties
    case_blocks = []  # type: List[Stripped]

    prop_enum_name = cpp_naming.enum_name(Identifier(f"Of_{cls.name}"))

    for prop in cls.properties:
        code = _generate_deserialize_property(prop=prop)

        prop_literal = cpp_naming.enum_literal_name(prop.name)

        case_blocks.append(
            Stripped(
                f"""\
case properties::{prop_enum_name}::{prop_literal}: {{
{I}{indent_but_first_line(code, I)}
{I}break;
}}"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::logic_error(
{II}common::Concat(
{III}"Unexpected properties literal of "
{III}"properties::{prop_enum_name}: ",
{III}std::to_string(
{IIII}static_cast<uint32_t>(property)
{III})
{II})
{I});"""
        )
    )
    # endregion

    # region While loop
    case_blocks_joined = "\n".join(case_blocks)

    map_name = cpp_naming.constant_name(Identifier(f"map_of_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
while (true) {{
{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(
{III}std::move(*error)
{II});
{I}}}

{I}if (reader.node().kind() == xml_common::NodeKind::Stop) {{
{II}// NOTE (mristin):
{II}// We reached a closing element of an instance, so we know that
{II}// the sequence ended.
{II}break;
{I}}} else if (reader.node().kind() != xml_common::NodeKind::Start) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}std::shared_ptr<T>
{II}>(
{III}common::Concat(
{IIII}L"Expected a start element opening a property "
{IIII}L"of {interface_name}, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const xml_common::StartNode&
{II}>(reader.node()).name
{I});

{I}// NOTE (mristin):
{I}// We consume the start element.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}error = DeserializationErrorFromReader(reader);

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(
{III}std::move(*error)
{II});
{I}}}

{I}auto it = properties::{map_name}.find(
{II}name
{I});
{I}if (it == properties::{map_name}.end()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}std::shared_ptr<T>
{II}>(
{III}common::Concat(
{IIII}L"Expected a start element opening a property "
{IIII}L"of {interface_name}, "
{IIII}L"but got a start element "
{IIII}L"which does not correspond to any of its properties: <",
{IIII}common::Utf8ToWstring(name),
{IIII}L">"
{III})
{II});
{I}}}

{I}const properties::{prop_enum_name} property(
{II}it->second
{I});

{I}switch (property) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}}

{I}if (error.has_value()) {{
{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(
{III}std::move(*error)
{II});
{I}}}

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(
{III}std::move(*error)
{II});
{I}}}

{I}if (!xml_common::IsStopNodeWithName(reader.node(), name)) {{
{II}error = DeserializationError(
{III}common::Concat(
{IIII}L"Expected a stop element </",
{IIII}common::Utf8ToWstring(name),
{IIII}L"> closing the property "
{IIII}L"of {interface_name}, but got ",
{IIII}xml_common::NodeToHumanReadableWstring(reader.node())
{III})
{II});

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(
{III}std::move(*error)
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the stop element.
{I}reader.Read();

{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}error = DeserializationErrorFromReader(reader);

{II}PrependElementSegmentToDeserializationError(
{III}name,
{III}*error
{II});

{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<T>
{II}>(
{III}std::move(*error)
{II});
{I}}}
}}"""
        )
    )
    # endregion

    class_name = cpp_naming.class_name(cls.name)

    if len(cls.properties) == 0:
        blocks.append(
            Stripped(
                f"""\
return std::make_pair(
{I}common::make_optional<
{II}std::shared_ptr<T>
{I}>(
{II}// NOTE (mristin):
{II}// We deliberately do not use std::make_shared here to avoid an unnecessary
{II}// upcast.
{II}new types::{class_name}()
{I}),
{I}common::nullopt
);"""
            )
        )
    else:
        # region Check required arguments
        required_properties = [
            prop
            for prop in cls.properties
            if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        ]

        if len(required_properties) > 0:
            blocks.append(Stripped("// region Check required properties"))

            for prop in required_properties:
                var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))
                xml_prop_name = prop.xml_name

                blocks.append(
                    Stripped(
                        f"""\
if (!{var_name}.has_value()) {{
{I}return NoInstanceAndDeserializationErrorWithCause<
{II}std::shared_ptr<T>
{I}>(
{II}L"The required property {xml_prop_name} is missing"
{I});
}}"""
                    )
                )

            blocks.append(Stripped("// endregion Check required properties"))

        # endregion

        # region Pass arguments to the constructor
        property_names = [prop.name for prop in cls.properties]
        constructor_argument_names = [arg.name for arg in cls.constructor.arguments]

        # fmt: off
        assert (
                set(prop.name for prop in cls.properties)
                == set(arg.name for arg in cls.constructor.arguments)
        ), (
            f"Expected the properties to coincide with constructor arguments, "
            f"but they do not for {cls.name!r}:"
            f"{property_names=}, {constructor_argument_names=}"
        )
        # fmt: on

        constructor_args = []  # type: List[Stripped]
        for arg in cls.constructor.arguments:
            prop = cls.properties_by_name[arg.name]

            var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))
            if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
                constructor_args.append(Stripped(f"std::move({var_name})"))
            else:
                constructor_args.append(Stripped(f"std::move(*{var_name})"))

        constructor_args_joined = ",\n".join(constructor_args)

        blocks.append(
            Stripped(
                f"""\
return std::make_pair(
{I}common::make_optional<
{II}std::shared_ptr<T>
{I}>(
{II}// NOTE (mristin):
{II}// We deliberately do not use std::make_shared here to avoid an unnecessary
{II}// upcast.
{II}new types::{class_name}(
{III}{indent_but_first_line(constructor_args_joined, III)}
{II})
{I}),
{I}common::nullopt
);"""
            )
        )
        # endregion

    body = "\n\n".join(blocks)

    return (
        Stripped(
            f"""\
template <
{I}typename T,
{I}typename std::enable_if<
{II}std::is_base_of<T, types::{interface_name}>::value
{I}>::type*
>
std::pair<
{I}common::optional<std::shared_ptr<T> >,
{I}common::optional<DeserializationError>
> {function_name}(
{I}xml_common::ReaderMergingText& reader
) {{
{I}{indent_but_first_line(body, I)}
}}"""
        ),
        None,
    )


def _generate_deserialize_from(
    function_name: Identifier, from_element_name: Identifier, value_type: Stripped
) -> Stripped:
    """
    Generate the impl. of a public de-serialization for a value type.

    We deliberately do not pass in a class or named union object, and pass
    names/the value type instead, in order to be able to generate the
    function both for the most abstract ``IClass``, the classes defined in
    the symbol table, and the named unions (whose value type is a
    ``std::variant``, not a ``shared_ptr``-wrapped interface).
    """
    return Stripped(
        f"""\
common::expected<
{I}{indent_but_first_line(value_type, I)},
{I}DeserializationError
> {function_name}(
{I}std::istream& is,
{I}const ReadingOptions& options
) {{
{I}xml_common::ReaderMergingText reader(
{II}is,
{II}options.additional_attributes,
{II}options.buffer_size,
{II}kNamespace
{I});

{I}reader.Initialize();
{I}if (reader.node().kind() == xml_common::NodeKind::Error) {{
{II}return common::make_unexpected(
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}common::optional<
{II}{indent_but_first_line(value_type, II)}
{I}> instance;

{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}instance,
{II}error
{I}) = {from_element_name}(reader);

{I}if (error.has_value()) {{
{II}return common::make_unexpected(
{III}std::move(*error)
{II});
{I}}}

{I}error = SkipWhitespace(reader);
{I}if (error.has_value()) {{
{II}return common::make_unexpected(
{III}std::move(*error)
{II});
{I}}}

{I}error = CheckReaderAtEof(reader);
{I}if (error.has_value()) {{
{II}return common::make_unexpected(
{III}std::move(*error)
{II});
{I}}}

{I}return std::move(*instance);
}}"""
    )


def _generate_serialization_exception_implementation() -> List[Stripped]:
    """Generate the impl. of the exception we throw during serialization."""
    # NOTE (mristin):
    # This code has been copy/pasted from jsonization implementation. We keep it here
    # in separate since we anticipate that implementations might most probably diverge
    # in the future.
    return [
        Stripped("// region SerializationException"),
        Stripped(
            f"""\
std::string RenderSerializationErrorMessage(
{I}const std::wstring& cause,
{I}const iteration::Path& path
) {{
{I}return common::WstringToUtf8(
{II}common::Concat(
{III}L"Serialization failed at ",
{III}path.ToWstring(),
{III}L": ",
{III}cause
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
SerializationException::SerializationException(
{I}std::wstring cause
) :
{I}cause_(std::move(cause)),
{I}path_(),
{I}msg_(RenderSerializationErrorMessage(cause, path_)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
SerializationException::SerializationException(
{I}std::wstring cause,
{I}iteration::Path path
) :
{I}cause_(std::move(cause)),
{I}path_(std::move(path)),
{I}msg_(RenderSerializationErrorMessage(cause, path)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
const char* SerializationException::what() const noexcept {{
{I}return msg_.c_str();
}}"""
        ),
        Stripped(
            f"""\
const std::wstring& SerializationException::cause() const noexcept {{
{I}return cause_;
}}"""
        ),
        Stripped(
            f"""\
const iteration::Path& SerializationException::path() const noexcept {{
{I}return path_;
}}"""
        ),
        Stripped("// endregion SerializationException"),
    ]


def _generate_serialize_primitives() -> List[Stripped]:
    return [
        Stripped(
            f"""\
common::optional<xml_common::SerializationError> SerializeBool(
{I}bool value,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}writer.SerializeBool(value);
{I}if (writer.error().has_value()) {{
{II}return writer.move_error();
{I}}}

{I}return common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
common::optional<xml_common::SerializationError> SerializeInt64(
{I}int64_t value,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}writer.SerializeInt64(value);
{I}if (writer.error().has_value()) {{
{II}return writer.move_error();
{I}}}

{I}return common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
common::optional<xml_common::SerializationError> SerializeDouble(
{I}double value,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}writer.SerializeDouble(value);
{I}if (writer.error().has_value()) {{
{II}return writer.move_error();
{I}}}

{I}return common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
common::optional<xml_common::SerializationError> SerializeWstring(
{I}const std::wstring& value,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}writer.SerializeWstring(value);
{I}if (writer.error().has_value()) {{
{II}return writer.move_error();
{I}}}

{I}return common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
common::optional<xml_common::SerializationError> SerializeByteArray(
{I}const std::vector<std::uint8_t>& value,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}writer.SerializeByteArray(value);
{I}if (writer.error().has_value()) {{
{II}return writer.move_error();
{I}}}

{I}return common::nullopt;
}}"""
        ),
    ]


_PRIMITIVE_TYPE_TO_SERIALIZE = {
    intermediate.PrimitiveType.BOOL: "SerializeBool",
    intermediate.PrimitiveType.INT: "SerializeInt64",
    intermediate.PrimitiveType.FLOAT: "SerializeDouble",
    intermediate.PrimitiveType.STR: "SerializeWstring",
    intermediate.PrimitiveType.BYTEARRAY: "SerializeByteArray",
}
assert all(
    primitive_type in _PRIMITIVE_TYPE_TO_SERIALIZE
    for primitive_type in intermediate.PrimitiveType
)


def _generate_serialize_list_of_v_elements() -> Stripped:
    """Generate the generic function to serialize lists of <v> elements."""
    return Stripped(
        f"""\
/**
 * Serialize a list of items enclosed in <v> elements.
 */
template <typename T, typename SerializeT>
common::optional<xml_common::SerializationError> SerializeListOfVElements(
{I}const std::vector<T>& list,
{I}xml_common::SelfClosingWriter& writer,
{I}const SerializeT& serialize_item
) {{
{I}for (size_t i = 0; i < list.size(); ++i) {{
{II}writer.StartElement("v");
{II}if (writer.error().has_value()) {{
{III}common::optional<xml_common::SerializationError>&& error = writer.move_error();
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<iteration::IndexSegment>(i)
{III});

{III}return error;
{II}}}

{II}common::optional<xml_common::SerializationError> error = serialize_item(
{III}list[i],
{III}writer
{II});

{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<iteration::IndexSegment>(i)
{III});

{III}return error;
{II}}}

{II}writer.StopElement("v");
{II}if (writer.error().has_value()) {{
{III}common::optional<xml_common::SerializationError>&& error = writer.move_error();
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<iteration::IndexSegment>(i)
{III});

{III}return error;
{II}}}
{I}}}

{I}return common::nullopt;
}}"""
    )


def _generate_serialize_list_of_instances() -> Stripped:
    """Generate the generic function to serialize lists of instances."""
    return Stripped(
        f"""\
/**
 * Serialize a list of instances.
 */
template <typename T, typename SerializeT>
common::optional<xml_common::SerializationError> SerializeListOfInstances(
{I}const std::vector<T>& list,
{I}xml_common::SelfClosingWriter& writer,
{I}const SerializeT& serialize_item
) {{
{I}for (size_t i = 0; i < list.size(); ++i) {{
{II}common::optional<xml_common::SerializationError> error = serialize_item(
{III}list[i],
{III}writer
{II});

{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<iteration::IndexSegment>(i)
{III});

{III}return error;
{II}}}
{I}}}

{I}return common::nullopt;
}}"""
    )


def _generate_serialize_tuple_function(arity: int) -> Stripped:
    """
    Generate a generic function to serialize a tuple of the given ``arity``.

    Each positional item is serialized by its own ``serialize_item{i}``
    callable, which is expected to write its own opening and closing tags (if
    any) -- mirroring how :py:func:`_generate_serialize_list_of_instances`
    delegates the actual item serialization to a caller-supplied callable.
    """
    assert arity > 0

    template_params_joined = ",\n".join(
        [f"typename T{i}" for i in range(arity)]
        + [f"typename SerializeT{i}" for i in range(arity)]
    )

    item_types_joined = ",\n".join(f"T{i}" for i in range(arity))

    parameters = ",\n".join(
        f"const SerializeT{i}& serialize_item{i}" for i in range(arity)
    )

    item_stmts = []  # type: List[Stripped]
    for i in range(arity):
        item_stmts.append(
            Stripped(
                f"""\
error = serialize_item{i}(
{I}std::get<{i}>(value),
{I}writer
);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<iteration::IndexSegment>(
{III}{i}
{II})
{I});
{I}return error;
}}"""
            )
        )

    item_stmts_joined = "\n\n".join(item_stmts)

    function_name = f"SerializeTuple{arity}"

    return Stripped(
        f"""\
/**
 * Serialize a tuple of {arity} item(s).
 */
template <
{I}{indent_but_first_line(template_params_joined, I)}
>
common::optional<xml_common::SerializationError> {function_name}(
{I}const std::tuple<
{II}{indent_but_first_line(item_types_joined, II)}
{I}>& value,
{I}xml_common::SelfClosingWriter& writer,
{I}{indent_but_first_line(parameters, I)}
) {{
{I}common::optional<xml_common::SerializationError> error;

{I}{indent_but_first_line(item_stmts_joined, I)}

{I}return common::nullopt;
}}"""
    )


def _generate_serialize_enumeration(enumeration: intermediate.Enumeration) -> Stripped:
    function_name = cpp_naming.function_name(
        Identifier(f"serialize_{enumeration.name}")
    )

    enum_name = cpp_naming.enum_name(enumeration.name)

    return Stripped(
        f"""\
/**
 * Serialize the literal of {enum_name}
 * to XML text.
 */
common::optional<xml_common::SerializationError> {function_name}(
{I}types::{enum_name} that,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}writer.SerializeString(
{II}stringification::to_string(
{III}that
{II})
{I});
{I}if (writer.error()) {{
{II}return writer.move_error();
{I}}}

{I}return common::nullopt;
}}"""
    )


def _generate_serialize_property_as_element() -> Stripped:
    """
    Generate the generic function to serialize a property wrapped in its own
    named XML element.

    This factors out the ``StartElement``/serialize-call/``StopElement``
    skeleton shared by every property regardless of kind (primitive, enum,
    class or list), so that :py:func:`_generate_serialize_property` only
    needs to supply the element name, the value and a value-specific
    ``serialize_value`` callable.
    """
    return Stripped(
        f"""\
/**
 * Serialize a property wrapped in its own named XML element.
 */
template <typename T, typename SerializeT>
common::optional<xml_common::SerializationError> SerializePropertyAsElement(
{I}const std::string& name,
{I}const T& value,
{I}xml_common::SelfClosingWriter& writer,
{I}iteration::Property property,
{I}const SerializeT& serialize_value
) {{
{I}writer.StartElement(name);
{I}if (writer.error().has_value()) {{
{II}return writer.move_error();
{I}}}

{I}common::optional<xml_common::SerializationError> error = serialize_value(value, writer);
{I}if (error.has_value()) {{
{II}error->path.segments.emplace_front(
{III}common::make_unique<iteration::PropertySegment>(property)
{II});
{II}return error;
{I}}}

{I}writer.StopElement(name);
{I}if (writer.error().has_value()) {{
{II}error = writer.move_error();
{II}error->path.segments.emplace_front(
{III}common::make_unique<iteration::PropertySegment>(property)
{II});
{II}return error;
{I}}}

{I}return common::nullopt;
}}"""
    )


def _xml_serialize_list_value_expr(
    item_type_annotation: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """
    Build the ``(list, writer) -> optional<xml_common::SerializationError>`` callable for
    a list-typed property, to be plugged into ``SerializePropertyAsElement``.
    """
    item_type = cpp_common.generate_type(
        type_annotation=item_type_annotation, types_namespace=cpp_common.TYPES_NAMESPACE
    )

    items_primitive_type = intermediate.try_primitive_type(item_type_annotation)

    list_helper: str
    serialize_item: str

    if items_primitive_type is not None:
        serialize_item = _PRIMITIVE_TYPE_TO_SERIALIZE[items_primitive_type]
        list_helper = "SerializeListOfVElements"

    else:
        if isinstance(item_type_annotation, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(item_type_annotation, intermediate.OurTypeAnnotation):
            if isinstance(item_type_annotation.our_type, intermediate.Enumeration):
                serialize_item = cpp_naming.function_name(
                    Identifier(f"serialize_{item_type_annotation.our_type.name}")
                )
                list_helper = "SerializeListOfVElements"

            elif isinstance(
                item_type_annotation.our_type, intermediate.ConstrainedPrimitive
            ):
                raise AssertionError("Expected to handle this case before")

            elif isinstance(
                item_type_annotation.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                serialize_item = cpp_naming.function_name(
                    Identifier(
                        f"serialize_{item_type_annotation.our_type.name}_ptr_as_element"
                    )
                )
                list_helper = "SerializeListOfInstances"

            elif isinstance(item_type_annotation.our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # A named union has no ``*PtrAsElement`` counterpart -- its own
                # value is already a ``std::variant``, not a pointer -- so we
                # reference its ``*AsElement`` function directly.
                serialize_item = cpp_naming.function_name(
                    Identifier(
                        f"serialize_{item_type_annotation.our_type.name}_as_element"
                    )
                )
                list_helper = "SerializeListOfInstances"

            else:
                # noinspection PyTypeChecker
                assert_never(item_type_annotation.our_type)

        else:
            raise NotImplementedError(
                "NOTE (mristin): We currently implement only XML serialization of "
                "lists of atomic values (primitive types, enumerations, instances), "
                f"but we got list of item type: {item_type_annotation}. "
                f"Please contact the developers if you need this feature."
            )

    return Stripped(
        f"""\
[](
{I}const std::vector<{indent_but_first_line(item_type, I)}>& a_list,
{I}xml_common::SelfClosingWriter& a_writer
) {{
{I}return {list_helper}(a_list, a_writer, {serialize_item});
}}"""
    )


def _xml_serialize_tuple_value_expr(
    type_anno: intermediate.TupleTypeAnnotation,
) -> Stripped:
    """
    Build the ``(tuple, writer) -> optional<xml_common::SerializationError>`` callable for
    a tuple-typed property, to be plugged into ``SerializePropertyAsElement``.

    Non-class items are wrapped in ``<v1>``, ``<v2>``, *etc.* elements (1-based),
    while class items write their own element directly, mirroring how lists of
    classes are handled. The actual per-item error-path bookkeeping is
    delegated to the generic ``SerializeTupleN`` function generated once for
    the tuple's arity by :py:func:`_generate_serialize_tuple_function`.
    """
    tuple_type = cpp_common.generate_type(
        type_annotation=type_anno, types_namespace=cpp_common.TYPES_NAMESPACE
    )

    item_exprs = []  # type: List[Stripped]

    for i, item_type_anno in enumerate(type_anno.items):
        assert isinstance(item_type_anno, intermediate.AtomicTypeAnnotationAsTuple), (
            "Tuple items are restricted to atomic types (primitives, "
            "constrained primitives, classes and enumerations) by "
            "intermediate._translate._verify_only_simple_type_patterns, so no "
            "nested optionals, lists or tuples are expected here."
        )

        item_type = cpp_common.generate_type(
            type_annotation=item_type_anno, types_namespace=cpp_common.TYPES_NAMESPACE
        )

        items_primitive_type = intermediate.try_primitive_type(item_type_anno)

        # NOTE (mristin):
        # Both classes and named unions are self-tagging (dispatched through
        # their own element tag), unlike primitives/enumerations, which are
        # wrapped in a synthetic ``<v1>``, ``<v2>``, *etc.* element.
        is_class_item = isinstance(
            item_type_anno, intermediate.OurTypeAnnotation
        ) and isinstance(
            item_type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        )
        is_named_union_item = isinstance(
            item_type_anno, intermediate.OurTypeAnnotation
        ) and isinstance(item_type_anno.our_type, intermediate.NamedUnion)

        if not (is_class_item or is_named_union_item):
            if items_primitive_type is not None:
                serialize_function = _PRIMITIVE_TYPE_TO_SERIALIZE[items_primitive_type]
            elif isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
                raise AssertionError("Expected to handle this case before")
            elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                if isinstance(item_type_anno.our_type, intermediate.Enumeration):
                    serialize_function = cpp_naming.function_name(
                        Identifier(f"serialize_{item_type_anno.our_type.name}")
                    )
                elif isinstance(
                    item_type_anno.our_type, intermediate.ConstrainedPrimitive
                ):
                    raise AssertionError("Expected to handle this case before")
                else:
                    # NOTE (mristin):
                    # This branch is unreachable in practice: ``is_class_item`` is
                    # ``False`` here, so ``item_type_anno.our_type`` can not be
                    # an ``AbstractClass``/``ConcreteClass``, but mypy can not
                    # correlate the ``is_class_item`` boolean with the narrowing
                    # of ``item_type_anno.our_type``, so we can not use
                    # ``assert_never`` here.
                    raise AssertionError(
                        f"Expected to handle this case above: {item_type_anno.our_type}"
                    )
            elif isinstance(
                item_type_anno,
                (
                    intermediate.JsonValueTypeAnnotation,
                    intermediate.JsonArrayTypeAnnotation,
                    intermediate.JsonObjectTypeAnnotation,
                ),
            ):
                serialize_function = _xml_json_serialize_function_for(item_type_anno)
            else:
                # noinspection PyTypeChecker
                assert_never(item_type_anno)

            v_name_literal = cpp_common.string_literal(f"v{i + 1}")

            item_exprs.append(
                Stripped(
                    f"""\
[](
{I}const {indent_but_first_line(item_type, I)}& item,
{I}xml_common::SelfClosingWriter& a_writer
) -> common::optional<xml_common::SerializationError> {{
{I}a_writer.StartElement(
{II}{v_name_literal}
{I});
{I}if (a_writer.error().has_value()) {{
{II}common::optional<xml_common::SerializationError>&& error = a_writer.move_error();
{II}return error;
{I}}}

{I}common::optional<xml_common::SerializationError> error = {serialize_function}(
{II}item,
{II}a_writer
{I});
{I}if (error.has_value()) {{
{II}return error;
{I}}}

{I}a_writer.StopElement(
{II}{v_name_literal}
{I});
{I}if (a_writer.error().has_value()) {{
{II}common::optional<xml_common::SerializationError>&& error = a_writer.move_error();
{II}return error;
{I}}}

{I}return common::nullopt;
}}"""
                )
            )
        else:
            assert isinstance(item_type_anno, intermediate.OurTypeAnnotation)

            if isinstance(item_type_anno.our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # A named union has no ``*PtrAsElement`` counterpart -- its
                # own value is already a ``std::variant``, not a pointer.
                serialize_function = cpp_naming.function_name(
                    Identifier(f"serialize_{item_type_anno.our_type.name}_as_element")
                )
            else:
                serialize_function = cpp_naming.function_name(
                    Identifier(
                        f"serialize_{item_type_anno.our_type.name}_ptr_as_element"
                    )
                )

            item_exprs.append(Stripped(serialize_function))

    item_exprs_joined = ",\n".join(item_exprs)

    function_name = f"SerializeTuple{len(type_anno.items)}"

    return Stripped(
        f"""\
[](
{I}const {indent_but_first_line(tuple_type, I)}& a_tuple,
{I}xml_common::SelfClosingWriter& a_writer
) {{
{I}return {function_name}(
{II}a_tuple,
{II}a_writer,
{II}{indent_but_first_line(item_exprs_joined, II)}
{I});
}}"""
    )


def _generate_serialize_property(prop: intermediate.Property) -> Stripped:
    """
    Generate code to serialize a property.

    The property is wrapped in its own named XML element via the generic
    :py:func:`_generate_serialize_property_as_element`; this function only
    needs to determine the value expression and the value-specific
    ``serialize_value`` callable for the property's kind.
    """
    getter_name = cpp_naming.getter_name(prop.name)

    getter_expr: Stripped

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        getter_expr = Stripped(f"*(that.{getter_name}())")
    else:
        getter_expr = Stripped(f"that.{getter_name}()")

    xml_name_literal = cpp_common.string_literal(prop.xml_name)

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    primitive_type = intermediate.try_primitive_type(type_anno)

    value_expr: Stripped
    serialize_value_expr: Stripped

    if primitive_type is not None:
        value_expr = getter_expr
        serialize_value_expr = Stripped(_PRIMITIVE_TYPE_TO_SERIALIZE[primitive_type])

    else:
        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                value_expr = getter_expr
                serialize_value_expr = Stripped(
                    cpp_naming.function_name(
                        Identifier(f"serialize_{type_anno.our_type.name}")
                    )
                )

            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError("Expected to handle this case before")

            elif isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                value_expr = Stripped(f"*({getter_expr})")

                if len(type_anno.our_type.concrete_descendants) == 0:
                    serialize_value_expr = Stripped(
                        cpp_naming.function_name(
                            Identifier(
                                f"serialize_{type_anno.our_type.name}_as_sequence"
                            )
                        )
                    )
                else:
                    serialize_value_expr = Stripped(
                        cpp_naming.function_name(
                            Identifier(
                                f"serialize_{type_anno.our_type.name}_as_element"
                            )
                        )
                    )

            elif isinstance(type_anno.our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # A named union's own value is already a ``std::variant``,
                # not a pointer, so -- unlike a class -- there is nothing
                # to dereference here.
                value_expr = getter_expr

                serialize_value_expr = Stripped(
                    cpp_naming.function_name(
                        Identifier(f"serialize_{type_anno.our_type.name}_as_element")
                    )
                )

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            value_expr = getter_expr

            serialize_value_expr = _xml_serialize_list_value_expr(
                item_type_annotation=type_anno.items
            )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            value_expr = getter_expr

            serialize_value_expr = _xml_serialize_tuple_value_expr(type_anno=type_anno)

        elif isinstance(
            type_anno,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            value_expr = getter_expr

            serialize_value_expr = _xml_json_serialize_function_for(type_anno)

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

    prop_literal = cpp_naming.enum_literal_name(prop.name)

    code = Stripped(
        f"""\
error = SerializePropertyAsElement(
{I}{xml_name_literal},
{I}{indent_but_first_line(value_expr, I)},
{I}writer,
{I}iteration::Property::{prop_literal},
{I}{indent_but_first_line(serialize_value_expr, I)}
);
if (error.has_value()) {{
{I}return error;
}}"""
    )

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        code = Stripped(
            f"""\
if (that.{getter_name}().has_value()) {{
{I}{indent_but_first_line(code, I)}
}}"""
        )

    return code


def _generate_serialize_cls_as_sequence_definition(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the impl. to serialize an instance as a sequence of XML elements.

    Each XML element corresponds to a property.
    """
    function_name = cpp_naming.function_name(
        Identifier(f"serialize_{cls.name}_as_sequence")
    )

    interface_name = cpp_naming.interface_name(cls.name)

    return Stripped(
        f"""\
/**
 * \\brief Serialize \\p that instance as a sequence of XML elements.
 *
 * Each XML element corresponds to a property.
 *
 * \\param that instance to be serialized
 * \\param writer to write to
 * \\return error, if any
 */
common::optional<xml_common::SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}xml_common::SelfClosingWriter& writer
);"""
    )


def _generate_serialize_cls_as_sequence_implementation(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the impl. to serialize an instance as a sequence of XML elements.

    Each XML element corresponds to a property.
    """
    if cls.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"xmlization/serialize_{cls.name}_as_sequence.cpp"
        )

        code = spec_impls.get(implementation_key, None)
        if code is None:
            return None, Error(
                cls.parsed.node,
                f"The implementation is missing for the XML serialization "
                f"of {cls.name!r}: {implementation_key}",
            )
        return code, None

    blocks = []  # type: List[Stripped]
    if len(cls.properties) > 0:
        blocks.append(
            Stripped("common::optional<xml_common::SerializationError> error;")
        )

        for prop in cls.properties:
            blocks.append(_generate_serialize_property(prop=prop))

        blocks.append(
            Stripped(
                f"""\
writer.Finish();
if (writer.error().has_value()) {{
{I}return writer.move_error();
}}"""
            )
        )

    blocks.append(Stripped("return common::nullopt;"))

    function_name = cpp_naming.function_name(
        Identifier(f"serialize_{cls.name}_as_sequence")
    )

    interface_name = cpp_naming.interface_name(cls.name)

    body = Stripped("\n\n".join(blocks))

    return (
        Stripped(
            f"""\
/**
 * \\brief Serialize \\p that instance as a sequence of XML elements.
 *
 * Each XML element corresponds to a property.
 *
 * \\param that instance to be serialized
 * \\param writer to write to
 * \\return error, if any
 */
common::optional<xml_common::SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}{indent_but_first_line(body, I)}
}}"""
        ),
        None,
    )


def _generate_serialize_cls_as_element_definition(
    cls: intermediate.ClassUnion,
) -> List[Stripped]:
    """Generate the def. to serialize an instance to an XML element."""
    xml_class = naming.xml_class_name(cls.name)

    function_name = cpp_naming.function_name(
        Identifier(f"serialize_{cls.name}_as_element")
    )

    interface_name = cpp_naming.interface_name(cls.name)

    description_comment: Stripped

    if len(cls.concrete_descendants) > 0:
        description_comment = Stripped(
            """\
/**
 * \\brief Serialize \\p that instance by dispatching to the appropriate concrete
 * serialization function.
 *
 * \\param that instance to be serialized
 * \\param writer to be write to
 * \\return error, if any
 */"""
        )
    else:
        description_comment = Stripped(
            f"""\
/**
 * Serialize \\p that instance to an XML element
 * `<{xml_class}>`.
 *
 * \\param that instance to be serialized
 * \\return an error, if any
 */"""
        )

    function_name_ptr = cpp_naming.function_name(
        Identifier(f"serialize_{cls.name}_ptr_as_element")
    )

    return [
        Stripped(
            f"""\
{description_comment}
common::optional<xml_common::SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}xml_common::SelfClosingWriter& writer
);"""
        ),
        Stripped(
            f"""\
/** @copybrief {function_name}(const types::{interface_name}&, xml_common::SelfClosingWriter& */
common::optional<xml_common::SerializationError> {function_name_ptr}(
{I}const std::shared_ptr<types::{interface_name}>& that,
{I}xml_common::SelfClosingWriter& writer
);"""
        ),
    ]


def _generate_serialize_named_union_as_element_definition(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the def. to serialize a named union to an XML element.

    Unlike a class, a named union has no ``*PtrAsElement`` counterpart --
    the union's own value is already a ``std::variant``, not a pointer, so
    a single by-const-ref function suffices for every use site (property,
    list item, tuple item).
    """
    union_name = cpp_naming.union_name(named_union.name)

    function_name = cpp_naming.function_name(
        Identifier(f"serialize_{named_union.name}_as_element")
    )

    return Stripped(
        f"""\
/**
 * \\brief Serialize \\p that instance by dispatching to the appropriate concrete
 * serialization function.
 *
 * \\param that instance to be serialized
 * \\param writer to be write to
 * \\return error, if any
 */
common::optional<xml_common::SerializationError> {function_name}(
{I}const types::{union_name}& that,
{I}xml_common::SelfClosingWriter& writer
);"""
    )


def _generate_concrete_serialize_cls_as_element(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the impl. to serialize an instance to an XML element.

    The execution is not dispatched, and the model type of the argument is expected
    to coincide with the compile-time interface type.
    """
    xml_class_literal = cpp_common.string_literal(naming.xml_class_name(cls.name))
    serialize_as_sequence = cpp_naming.function_name(
        Identifier(f"serialize_{cls.name}_as_sequence")
    )

    body = Stripped(
        f"""\
common::optional<xml_common::SerializationError> error;

writer.StartElement(
{I}{xml_class_literal}
);
if (writer.error().has_value()) {{
{I}return writer.move_error();
}}

error = {serialize_as_sequence}(
{I}that,
{I}writer
);
if (error.has_value()) {{
{I}return error;
}}

writer.StopElement(
{I}{xml_class_literal}
);
if (writer.error().has_value()) {{
{I}return writer.move_error();
}}

writer.Finish();
if (writer.error().has_value()) {{
{I}return writer.move_error();
}}

return common::nullopt;"""
    )

    function_name: Identifier
    description_comment_prefix: str

    xml_class = naming.xml_class_name(cls.name)

    if len(cls.concrete_descendants) == 0:
        function_name = cpp_naming.function_name(
            Identifier(f"serialize_{cls.name}_as_element")
        )
        description_comment_prefix = ""
    else:
        function_name = cpp_naming.function_name(
            Identifier(f"serialize_concrete_{cls.name}_as_element")
        )

        dispatch_name = cpp_naming.function_name(
            Identifier(f"serialize_{cls.name}_as_element")
        )

        description_comment_prefix = (
            Stripped(
                f"""\
/**
 * Serialize \\p that instance to an XML element
 * `<{xml_class}>`.
 *
 * No dispatch is performed in this function. It is expected that you call
 * \\ref {dispatch_name}, which will then dispatch into this function.
 *
 * \\param that instance to be serialized
 * \\param writer to write to
 * \\return an error, if any
 */"""
            )
            + "\n"
        )

    interface_name = cpp_naming.interface_name(cls.name)

    return Stripped(
        f"""\
{description_comment_prefix}common::optional<xml_common::SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


@require(lambda cls: len(cls.concrete_descendants) > 0)
def _generate_dispatching_serialize_cls_as_element(
    cls: intermediate.ClassUnion,
) -> Stripped:
    """Generate the impl. for a dispatching serialization for an instance."""
    case_blocks = []  # type: List[Stripped]

    # fmt: off
    concrete_classes = (
        [cls]
        if isinstance(cls, intermediate.ConcreteClass)
        else []
    ) + list(cls.concrete_descendants)
    # fmt: on

    interface_name = cpp_naming.interface_name(cls.name)

    for concrete_cls in concrete_classes:
        model_type_enum = cpp_naming.enum_name(Identifier("Model_type"))
        model_type_literal = cpp_naming.enum_literal_name(concrete_cls.name)

        if concrete_cls is not cls:
            serialize_cls_as_element = cpp_naming.function_name(
                Identifier(f"serialize_{concrete_cls.name}_as_element")
            )

            concrete_interface_name = cpp_naming.interface_name(concrete_cls.name)

            case_blocks.append(
                Stripped(
                    f"""\
case types::{model_type_enum}::{model_type_literal}:
{I}return {serialize_cls_as_element}(
{II}dynamic_cast<
{III}const types::{concrete_interface_name}&
{II}>(that),
{II}writer
{I});"""
                )
            )
        else:
            serialize_concrete_cls_as_element = cpp_naming.function_name(
                Identifier(f"serialize_concrete_{concrete_cls.name}_as_element")
            )

            case_blocks.append(
                Stripped(
                    f"""\
case types::{model_type_enum}::{model_type_literal}:
{I}return {serialize_concrete_cls_as_element}(
{II}that,
{II}writer
{I});"""
                )
            )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::invalid_argument(
{II}common::Concat(
{III}"Invalid model type: ",
{III}stringification::to_string(that.model_type())
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    function_name = cpp_naming.function_name(
        Identifier(f"serialize_{cls.name}_as_element")
    )

    return Stripped(
        f"""\
common::optional<xml_common::SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}// NOTE (mristin):
{I}// The dynamic casts are necessary due to virtual inheritance. Otherwise,
{I}// we would have used static casts.

{I}switch (that.model_type()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}};
}}"""
    )


def _generate_dispatching_serialize_named_union_as_element(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the impl. for a dispatching serialization for a named union.

    Unlike :py:func:`_generate_dispatching_serialize_cls_as_element`, the
    value here is a ``std::variant``, not a polymorphic pointer, so there is
    no ``model_type()``/``dynamic_cast`` dance -- the variant already knows
    which alternative it holds through its own ``index()``, so we switch on
    that directly and delegate to the corresponding implementer's own
    ``*PtrAsElement`` function (one case per alternative, in the exact same
    order the variant's alternatives were declared).
    """
    union_name = cpp_naming.union_name(named_union.name)

    case_blocks = []  # type: List[Stripped]
    for i, implementer in enumerate(named_union.implementers):
        serialize_ptr_as_element = cpp_naming.function_name(
            Identifier(f"serialize_{implementer.name}_ptr_as_element")
        )

        case_blocks.append(
            Stripped(
                f"""\
case {i}:
{I}return {serialize_ptr_as_element}(
{II}std::get<{i}>(that),
{II}writer
{I});"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::logic_error(
{II}common::Concat(
{III}"Invalid variant index for {union_name}: ",
{III}std::to_string(that.index())
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    function_name = cpp_naming.function_name(
        Identifier(f"serialize_{named_union.name}_as_element")
    )

    return Stripped(
        f"""\
common::optional<xml_common::SerializationError> {function_name}(
{I}const types::{union_name}& that,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}switch (that.index()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}};
}}"""
    )


def _generate_serialize_cls_ptr_as_element(cls: intermediate.ClassUnion) -> Stripped:
    """Generate the serialization function which simply dispatches the instance."""
    function_name_ptr = cpp_naming.function_name(
        Identifier(f"serialize_{cls.name}_ptr_as_element")
    )

    interface_name = cpp_naming.interface_name(cls.name)

    function_name = cpp_naming.function_name(
        Identifier(f"serialize_{cls.name}_as_element")
    )

    return Stripped(
        f"""\
common::optional<xml_common::SerializationError> {function_name_ptr}(
{I}const std::shared_ptr<types::{interface_name}>& that,
{I}xml_common::SelfClosingWriter& writer
) {{
{I}return {function_name}(*that, writer);
}}"""
    )


def _generate_serialize_implementation(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the impl. of the public serialize function."""
    case_blocks = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        serialize_cls_as_sequence = cpp_naming.function_name(
            Identifier(f"serialize_{cls.name}_as_sequence")
        )

        model_type_enum = cpp_naming.enum_name(Identifier("Model_type"))
        model_type_literal = cpp_naming.enum_literal_name(cls.name)

        xml_name = naming.xml_class_name(cls.name)

        start_element_with_namespace_expr = Stripped(
            f"""\
(
{I}"<{xml_name} "
{I}"xmlns=\\"{symbol_table.meta_model.xml_namespace}\\">"
)"""
        )

        start_element_wo_namespace_literal = cpp_common.string_literal(f"<{xml_name}>")

        stop_element = cpp_common.string_literal(f"</{xml_name}>")

        interface_name = cpp_naming.interface_name(cls.name)

        case_blocks.append(
            Stripped(
                f"""\
case types::{model_type_enum}::{model_type_literal}:
{I}if (options.write_namespace) {{
{II}os << {indent_but_first_line(start_element_with_namespace_expr, II)};
{I}}} else {{
{II}os << {start_element_wo_namespace_literal};
{I}}}

{I}error = xml_common::CheckOstreamState(os);
{I}if (error.has_value()) {{
{II}break;
{I}}}

{I}error = {serialize_cls_as_sequence}(
{II}dynamic_cast<
{III}const types::{interface_name}&
{II}>(that),
{II}writer
{I});
{I}if (error.has_value()) {{
{II}break;
{I}}}

{I}os << {stop_element};

{I}error = xml_common::CheckOstreamState(os);
{I}if (error.has_value()) {{
{II}break;
{I}}}

{I}break;"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::invalid_argument(
{II}common::Concat(
{III}"Invalid model type: ",
{III}stringification::to_string(that.model_type())
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
void Serialize(
{I}const types::IClass& that,
{I}const WritingOptions& options,
{I}std::ostream& os
) {{
{I}if (options.write_declaration) {{
{II}os << "<?xml version=\\"1.0\\" encoding=\\"utf-8\\"?>\\n";
{II}if (os.bad()) {{
{III}throw SerializationException(
{IIII}xml_common::kTheOutputStreamIsInABadState
{III});
{II}}}
{I}}}

{I}xml_common::SelfClosingWriter writer(
{II}os,
{II}options.prefix
{I});

{I}common::optional<xml_common::SerializationError> error;

{I}// NOTE (mristin):
{I}// Instead of using `Serialize*AsElement`, we write the root XML element
{I}// in this functions so that we check for the XML namespace only once, namely
{I}// here. Otherwise, we would have a condition check in <em>every</em> nested
{I}// `Serialize*AsElement` which could cause a significant efficiency hit.

{I}// NOTE (mristin):
{I}// The dynamic casts are necessary due to virtual inheritance. Otherwise,
{I}// we would have used static casts.

{I}switch (that.model_type()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}}

{I}if (error.has_value()) {{
{II}throw SerializationException(
{III}std::move(error->cause),
{III}std::move(error->path)
{II});
{I}}}
}}"""
    )


def _type_annotation_contains_list(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> bool:
    """Check whether the type annotation has a list type annotation."""
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        return True

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # Tuples are heterogeneous and fixed-length, so their items are always
        # de-serialized one by one, without ever looping over ``DeserializeList``.
        return False

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        return _type_annotation_contains_list(type_annotation.value)

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return False

    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


def _type_annotation_contains_tuple_with_atomic_non_class_item(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> bool:
    """
    Check whether the type annotation is a tuple with a non-class atomic item.

    Such tuples need ``DeserializeValueFromVElement`` for their non-class items,
    just as lists of non-class atomic values do.
    """
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        for item in type_annotation.items:
            assert isinstance(item, intermediate.AtomicTypeAnnotationAsTuple)

            if isinstance(item, intermediate.PrimitiveTypeAnnotation):
                return True

            elif isinstance(item, intermediate.OurTypeAnnotation):
                if isinstance(
                    item.our_type,
                    (intermediate.Enumeration, intermediate.ConstrainedPrimitive),
                ):
                    return True

            elif isinstance(
                item,
                (
                    intermediate.JsonValueTypeAnnotation,
                    intermediate.JsonArrayTypeAnnotation,
                    intermediate.JsonObjectTypeAnnotation,
                ),
            ):
                return True

        return False

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        return _type_annotation_contains_tuple_with_atomic_non_class_item(
            type_annotation.value
        )

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return False

    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


def _type_annotation_contains_list_of_atomic_non_class_values(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> bool:
    """
    Check whether the type annotation has a list of non-class atomic values.

    These are, for example, lists of enumerations or lists of primitives.
    """
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        if isinstance(type_annotation.items, intermediate.PrimitiveTypeAnnotation):
            return True

        elif isinstance(type_annotation.items, intermediate.OurTypeAnnotation):
            if isinstance(type_annotation.items.our_type, intermediate.Enumeration):
                return True

            elif isinstance(
                type_annotation.items.our_type, intermediate.ConstrainedPrimitive
            ):
                return True

            elif isinstance(
                type_annotation.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                return False

            elif isinstance(type_annotation.items.our_type, intermediate.NamedUnion):
                return False

            else:
                # noinspection PyTypeChecker
                assert_never(type_annotation.items.our_type)

        elif isinstance(type_annotation.items, intermediate.ListTypeAnnotation):
            return _type_annotation_contains_list_of_atomic_non_class_values(
                type_annotation.items.items
            )

        elif isinstance(type_annotation.items, intermediate.OptionalTypeAnnotation):
            return _type_annotation_contains_list_of_atomic_non_class_values(
                type_annotation.items.value
            )

        elif isinstance(type_annotation.items, intermediate.TupleTypeAnnotation):
            # NOTE (mristin):
            # No meta-model currently declares a list of tuples, and other parts of
            # the code generation would already reject it defensively, so this can
            # not actually occur in practice, but we still handle it explicitly for
            # exhaustiveness. A tuple is not itself an atomic non-class value, so
            # we return ``False``.
            return False

        elif isinstance(
            type_annotation.items,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            # NOTE (mristin):
            # A JSON-able list item is wrapped in its own ``<v>`` element via
            # ``DeserializeValueFromVElement``/``SerializeListOfVElements``,
            # exactly like a primitive or an enumeration.
            return True

        else:
            # noinspection PyTypeChecker
            assert_never(type_annotation.items)

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # Tuples never loop over ``SerializeListOfVElements``/
        # ``DeserializeValueFromVElement`` through a list-like generic function;
        # see :py:func:`_type_annotation_contains_tuple_with_atomic_non_class_item`
        # for the tuple-specific check.
        return False

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        return _type_annotation_contains_list_of_atomic_non_class_values(
            type_annotation.value
        )

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return False

    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


def _type_annotation_contains_list_of_instances(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> bool:
    """Check whether the type annotation has a list of instances."""
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        if isinstance(type_annotation.items, intermediate.PrimitiveTypeAnnotation):
            return False

        elif isinstance(type_annotation.items, intermediate.OurTypeAnnotation):
            if isinstance(type_annotation.items.our_type, intermediate.Enumeration):
                return False

            elif isinstance(
                type_annotation.items.our_type, intermediate.ConstrainedPrimitive
            ):
                return False

            elif isinstance(
                type_annotation.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                return True

            elif isinstance(type_annotation.items.our_type, intermediate.NamedUnion):
                return True

            else:
                # noinspection PyTypeChecker
                assert_never(type_annotation.items.our_type)

        elif isinstance(type_annotation.items, intermediate.ListTypeAnnotation):
            return _type_annotation_contains_list_of_instances(
                type_annotation.items.items
            )

        elif isinstance(type_annotation.items, intermediate.OptionalTypeAnnotation):
            return _type_annotation_contains_list_of_instances(
                type_annotation.items.value
            )

        elif isinstance(type_annotation.items, intermediate.TupleTypeAnnotation):
            # NOTE (mristin):
            # No meta-model currently declares a list of tuples, and other parts of
            # the code generation would already reject it defensively, so this can
            # not actually occur in practice, but we still handle it explicitly for
            # exhaustiveness. A tuple is not itself an instance, so we return
            # ``False``.
            return False

        elif isinstance(
            type_annotation.items,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            # NOTE (mristin):
            # A JSON-able value is plain data (``nlohmann::json``), never
            # a reference to one of our own classes.
            return False

        else:
            # noinspection PyTypeChecker
            assert_never(type_annotation.items)

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # Tuple class items are de-serialized/serialized directly, one by one,
        # without ever looping over ``SerializeListOfInstances``.
        return False

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        return _type_annotation_contains_list_of_instances(type_annotation.value)

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return False

    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
    library_namespace: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate implementation for XML de/serialization."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.XMLIZATION_NAMESPACE}")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    xml_namespace_literal = cpp_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    xml_rpc_include = (
        '#include "xml_rpc.hpp"\n'
        if intermediate.model_uses_json_types(symbol_table)
        else ""
    )

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/stringification.hpp"
#include "{include_prefix_path}/wstringification.hpp"
#include "{include_prefix_path}/xmlization.hpp"

#include "xml_common.hpp"
{xml_rpc_include}\

#pragma warning(push, 0)
#include <cmath>
#include <cstdint>
#include <deque>
#include <memory>
#include <limits>
#include <unordered_map>
#include <string>
#include <vector>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        Stripped(
            f"""\
const std::string kNamespace(  // NOLINT(cert-err58-cpp)
{I}{xml_namespace_literal}
);"""
        ),
        Stripped("// region De-serialization"),
        *_generate_element_segment_implementation(),
        *_generate_index_segment_implementation(),
        *_generate_path_implementation(),
        *_generate_deserialization_error_implementation(),
        *_generate_forward_declarations_of_deserialization_functions(
            symbol_table=symbol_table
        ),
        *_generate_element_name_to_model_type(symbol_table=symbol_table),
        _generate_instance_and_no_error(),
        *_generate_instance_and_error_factories_and_manipulations(),
        _generate_skip_bof(),
        *_generate_skip_whitespace(),
        _generate_deserialize_class_from_element_generic(),
        _generate_class_from_element(
            interface_name=Identifier("IClass"),
            function_name=cpp_naming.function_name(Identifier("class_from_element")),
            concrete_classes=symbol_table.concrete_classes,
        ),
    ]

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_deserialize_union_from_element_generic())
        blocks.append(_generate_wrap_deserialized_as_variant_function())

    for cls in symbol_table.classes:
        concrete_classes = []
        if isinstance(cls, intermediate.ConcreteClass):
            concrete_classes.append(cls)

        concrete_classes.extend(cls.concrete_descendants)

        blocks.append(
            _generate_class_from_element(
                interface_name=cpp_naming.interface_name(cls.name),
                function_name=cpp_naming.function_name(
                    Identifier(f"{cls.name}_from_element")
                ),
                concrete_classes=concrete_classes,
            )
        )

    for named_union in symbol_table.named_unions:
        # NOTE (mristin):
        # XML dispatch is always by the element's own tag name -- unlike JSON,
        # there is no distinction between a ``modelType``-dispatched and
        # a structurally-dispatched implementer here. However, a named union
        # is a ``std::variant``, not a polymorphic pointer, so we still need
        # our own dispatch function to construct the right alternative.
        blocks.append(_generate_named_union_from_element(named_union=named_union))

    blocks.extend(_generate_functions_to_deserialize_primitives())

    if intermediate.model_uses_json_types(symbol_table):
        # NOTE (mristin):
        # Both conversion functions are placed here, early in the file, since
        # ``xml_common::SerializationError`` is already a complete type at this point (it is
        # aliased from ``xml_common`` right at the top of this file, unlike
        # jsonization's own ``xml_common::SerializationError``, which is only declared much
        # later, alongside the rest of the serialization machinery).
        blocks.append(_generate_convert_xml_rpc_deserialization_error_implementation())
        blocks.append(_generate_convert_xml_rpc_serialization_error_implementation())
        blocks.extend(_generate_deserialize_json_from_xml_rpc_implementation())

    if any(
        _type_annotation_contains_list_of_atomic_non_class_values(prop.type_annotation)
        or _type_annotation_contains_tuple_with_atomic_non_class_item(
            prop.type_annotation
        )
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.append(_generate_deserialize_atomic_value_from_v_element())

    if any(
        _type_annotation_contains_list(prop.type_annotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.append(_generate_deserialize_list())

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_deserialize_tuple_function(arity))

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_deserialize_enumeration(enumeration))

    blocks.extend(_generate_property_enums_from_strings(symbol_table=symbol_table))

    errors = []  # type: List[Error]

    for concrete_cls in symbol_table.concrete_classes:
        block, error = _generate_from_sequence(cls=concrete_cls, spec_impls=spec_impls)
        if error is not None:
            errors.append(error)
        else:
            assert block is not None
            blocks.append(block)

    blocks.append(
        _generate_deserialize_from(
            function_name=cpp_naming.function_name(Identifier("from")),
            from_element_name=cpp_naming.function_name(
                Identifier("class_from_element")
            ),
            value_type=Stripped("std::shared_ptr<types::IClass>"),
        )
    )

    for cls in symbol_table.classes:
        blocks.append(
            _generate_deserialize_from(
                function_name=cpp_naming.function_name(Identifier(f"{cls.name}_from")),
                from_element_name=cpp_naming.function_name(
                    Identifier(f"{cls.name}_from_element")
                ),
                value_type=Stripped(
                    f"std::shared_ptr<types::{cpp_naming.interface_name(cls.name)}>"
                ),
            )
        )

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_deserialize_from(
                function_name=cpp_naming.function_name(
                    Identifier(f"{named_union.name}_from")
                ),
                from_element_name=cpp_naming.function_name(
                    Identifier(f"{named_union.name}_from_element")
                ),
                value_type=Stripped(
                    f"types::{cpp_naming.union_name(named_union.name)}"
                ),
            )
        )

    blocks.extend(
        [
            Stripped("// endregion De-serialization"),
            Stripped("// region Serialization"),
            *_generate_serialization_exception_implementation(),
            *_generate_serialize_primitives(),
        ]
    )

    if intermediate.model_uses_json_types(symbol_table):
        blocks.extend(_generate_serialize_json_to_xml_rpc_implementation())

    if any(len(cls.properties) > 0 for cls in symbol_table.concrete_classes):
        blocks.append(_generate_serialize_property_as_element())

    if any(
        _type_annotation_contains_list_of_atomic_non_class_values(prop.type_annotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.append(_generate_serialize_list_of_v_elements())

    if any(
        _type_annotation_contains_list_of_instances(prop.type_annotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.append(_generate_serialize_list_of_instances())

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_serialize_tuple_function(arity))

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_serialize_enumeration(enumeration))

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.ConcreteClass):
            blocks.append(_generate_serialize_cls_as_sequence_definition(cls=cls))

        blocks.extend(_generate_serialize_cls_as_element_definition(cls=cls))

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_serialize_named_union_as_element_definition(
                named_union=named_union
            )
        )

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.ConcreteClass):
            block, error = _generate_serialize_cls_as_sequence_implementation(
                cls=cls, spec_impls=spec_impls
            )
            if error is not None:
                errors.append(error)
            else:
                assert block is not None
                blocks.append(block)

            blocks.append(_generate_concrete_serialize_cls_as_element(cls=cls))

        if len(cls.concrete_descendants) > 0:
            blocks.append(_generate_dispatching_serialize_cls_as_element(cls=cls))

        blocks.append(_generate_serialize_cls_ptr_as_element(cls=cls))

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_dispatching_serialize_named_union_as_element(
                named_union=named_union
            )
        )

    if len(errors) > 0:
        return None, errors

    blocks.append(_generate_serialize_implementation(symbol_table=symbol_table))

    blocks.extend(
        [
            Stripped("// endregion Serialization"),
            cpp_common.generate_namespace_closing(namespace),
            cpp_common.WARNING,
        ]
    )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
