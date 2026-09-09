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
    INDENT7 as IIIIIII,
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


def _generate_node_kind() -> List[Stripped]:
    """Generate the definition and handling of XML node kinds."""
    return [
        Stripped(
            f"""\
enum class NodeKind : std::uint32_t {{
{I}// Nodes of the kind `Bof` represent the beginning-of-input, before any read.
{I}Bof = 0,
{I}Start = 1,
{I}Stop = 2,
{I}Text = 3,
{I}// Nodes of the kind `Eof` represent the end-of-input.
{I}Eof = 4,
{I}// Nodes of the kind `Error` represent low-level errors in the XML parsing.
{I}Error = 5
}};  // enum class NodeKind"""
        ),
        Stripped(
            f"""\
const std::unordered_map<
{I}NodeKind,
{I}std::string
> kNodeKindToHumanReadableString = {{
{I}{{NodeKind::Bof, "a beginning-of-input"}},
{I}{{NodeKind::Start, "a start element"}},
{I}{{NodeKind::Stop, "a stop element"}},
{I}{{NodeKind::Text, "a text"}},
{I}{{NodeKind::Eof, "an end-of-input"}},
{I}{{NodeKind::Error, "an error"}},
}};"""
        ),
        Stripped(
            f"""\
const std::string& NodeKindToHumanReadableString(NodeKind kind) {{
{I}auto it = kNodeKindToHumanReadableString.find(kind);
{I}if (it == kNodeKindToHumanReadableString.end()) {{
{II}throw std::invalid_argument(
{III}common::Concat(
{IIII}"Unexpected node kind: ",
{IIII}std::to_string(
{IIIII}static_cast<std::uint32_t>(kind)
{IIII})
{III})
{II});
{I}}}

{I}return it->second;
}}"""
        ),
    ]


def _generate_node_classes() -> List[Stripped]:
    """Generate the definition and implementation of XML nodes."""
    return [
        Stripped("// region Nodes"),
        Stripped(
            f"""\
/**
 * Model a node in an XML document.
 */
class INode {{
 public:
{I}/**
{I} * @return the kind of the node, used instead of much slower RTTI.
{I} */
{I}virtual NodeKind kind() const = 0;
{I}virtual ~INode() = default;
}};  // class INode"""
        ),
        Stripped(
            f"""\
/**
 * Model the beginning of the input, before anything was read.
 */
class BofNode : public INode {{
 public:
{I}NodeKind kind() const override {{ return NodeKind::Bof; }}

{I}~BofNode() override = default;
}}; // class StartNode"""
        ),
        Stripped(
            f"""\
/**
 * Model a start of an XML element.
 */
class StartNode : public INode {{
 public:
{I}explicit StartNode(
{II}std::string a_name
{I}) :
{II}name(std::move(a_name)) {{
{II}// Intentionally empty.
{I}}}

{I}NodeKind kind() const override {{ return NodeKind::Start; }}

{I}/**
{I} * Name of the start element, stripped of the expected XML namespace
{I} */
{I}const std::string name;

{I}~StartNode() override = default;
}};  // class StartNode"""
        ),
        Stripped(
            f"""\
/**
 * Model a stop of an XML element.
 */
class StopNode : public INode {{
 public:
{I}explicit StopNode(
{II}std::string a_name
{I}) :
{II}name(std::move(a_name)) {{
{II}// Intentionally empty.
{I}}}

{I}NodeKind kind() const override {{ return NodeKind::Stop; }}

{I}/**
{I} * Name of the stop element, stripped of the expected XML namespace
{I} */
{I}const std::string name;

{I}~StopNode() override = default;
}};  // class StopNode"""
        ),
        Stripped(
            f"""\
/**
 * Model a text node.
 */
class TextNode : public INode {{
 public:
{I}explicit TextNode(
{II}std::string a_text
{I}) :
{II}text(std::move(a_text)) {{
{II}// Intentionally empty.
{I}}}

{I}NodeKind kind() const override {{ return NodeKind::Text; }}

{I}/**
{I} * UTF-8 encoded XML text somewhere within an XML element
{I} */
{I}const std::string text;

{I}~TextNode() override = default;
}};  // class TextNode"""
        ),
        Stripped(
            f"""\
/**
 * Model an end-of-input.
 */
class EofNode : public INode {{
 public:
{I}NodeKind kind() const override {{ return NodeKind::Eof; }}

{I}~EofNode() override = default;
}};  // class EofNode"""
        ),
        Stripped(
            f"""\
/**
 * Model a low-level XML parsing error.
 */
class ErrorNode : public INode {{
 public:
{I}ErrorNode(
{II}size_t a_line,
{II}size_t a_column,
{II}std::string a_cause
{I}) :
{II}line(a_line),
{II}column(a_column),
{II}cause(std::move(a_cause)) {{
{II}// Intentionally empty.
{I}}}

{I}NodeKind kind() const override {{ return NodeKind::Error; }}

{I}const size_t line;
{I}const size_t column;

{I}// Cause of the error as UTF-8 encoded string
{I}const std::string cause;

{I}~ErrorNode() override = default;
}};  // class ErrorNode"""
        ),
        Stripped("// endregion Nodes"),
    ]


def _generate_readers() -> List[Stripped]:
    """Generate the def. and impl. of the XML readers."""
    return [
        Stripped("// region Reading"),
        Stripped("// region class Reader"),
        Stripped(
            f"""\
/**
 * Structure the data passed over to Expat XML reader.
 */
struct OurData {{
{I}bool additional_attributes;
{I}size_t buffer_size;
{I}XML_Parser parser;

{I}std::deque<std::unique_ptr<INode> >& node_buffer;

{I}bool stopped = false;

{I}OurData(
{II}bool the_additional_attributes,
{II}size_t a_buffer_size,
{II}XML_Parser a_parser,
{II}std::deque<std::unique_ptr<INode> >& a_node_buffer
{I}) :
{II}additional_attributes(the_additional_attributes),
{II}buffer_size(a_buffer_size), parser(a_parser),
{II}node_buffer(a_node_buffer) {{
{II}// Intentionally empty.
{I}}}
}};  // struct OurData"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Read XML in form of nodes, whereas text nodes are fragmented.
 *
 * We need a more abstract approach since the Expat library is too low-level
 * to parse complex models.
 *
 * Expat does not read the whole content of a text node in memory, but
 * we need to process the whole text during the XML de-serialization. Hence,
 * we keep on reading until we read the complete text. This has repercussions
 * on memory usage, as the the text will be held in three copies(one copy in
 * the Expat buffer, second copy in our internal buffer in which we
 * incrementally feed in the fragments, and the third copy is the final merged
 * text).
 */
class Reader {{
 public:
{I}Reader(
{II}std::istream& is,
{II}const ReadingOptions& options
{I});

{I}/**
{I} * Set up the reader for the XML parsing and read the first node.
{I} */
{I}void Initialize();

{I}/**
{I} * Read the next node in the document.
{I} */
{I}void Read();

{I}/**
{I} * @return the node which has been read last
{I} */
{I}const INode& node() const;

{I}/**
{I} * @return the node which has been read last moved out of this reader
{I} */
{I}std::unique_ptr<INode> moved_node();

{I}~Reader();

 private:
{I}const bool additional_attributes_;
{I}const size_t buffer_size_;
{I}std::istream& is_;

{I}XML_Parser parser_;
{I}std::unique_ptr<OurData> our_data_;

{I}// Node buffer does not include the current node.
{I}std::deque<std::unique_ptr<INode>> node_buffer_;

{I}// Current node is never null.
{I}std::unique_ptr<INode> current_;

{I}// Set if the current node is end-of-input
{I}bool eof_;

{I}// Set if the current node is an error
{I}bool error_;

{I}void SetCurrentAndEofAndError(std::unique_ptr<INode> node);

{I}// Re-usable buffer to keep a chunk of the data read from the input
{I}std::vector<char> chunk_;
}};  // class Reader"""
        ),
        Stripped(
            f"""\
Reader::Reader(
{I}std::istream& is,
{I}const ReadingOptions& options
) :
{I}additional_attributes_(options.additional_attributes),
{I}buffer_size_(options.buffer_size),
{I}is_(is),
{I}parser_(nullptr),
{I}current_(common::make_unique<BofNode>()),
{I}eof_(false),
{I}error_(false) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped("const char kNamespaceSeparator = '|';"),
        Stripped(
            f"""\
void XMLCALL OnStartElement(
{I}void* user_data,
{I}const char* name,
{I}const char* attributes[]
) {{
{I}auto our_data = static_cast<OurData*>(user_data);

{I}// NOTE (mristin):
{I}// Since Expat continues parsing and adding nodes even if the parsing is
{I}// suspended (see the documentation of `XML_StopParser`), we have to ignore
{I}// any further events.
{I}if (our_data->stopped) {{
{II}return;
{I}}}

{I}const std::string name_str(name);

{I}size_t separator_i = name_str.find(kNamespaceSeparator);
{I}if (separator_i == std::string::npos || separator_i == 0) {{
{II}std::string message = common::Concat(
{III}"The namespace is missing in the start element <",
{III}name_str,
{III}">"
{II});

{II}our_data->node_buffer.emplace_back(
{III}common::make_unique<ErrorNode>(
{IIII}XML_GetCurrentLineNumber(our_data->parser),
{IIII}XML_GetCurrentColumnNumber(our_data->parser),
{IIII}message
{III})
{II});

{II}XML_StopParser(our_data->parser, false);
{II}our_data->stopped = true;
{II}return;
{I}}}

{I}if (name_str.compare(0, separator_i, kNamespace) != 0) {{
{II}std::string message = common::Concat(
{III}"We expected the XML namespace ",
{III}kNamespace,
{III}", but we got the namespace ",
{III}name_str.substr(0, separator_i),
{III}" in the start element <",
{III}name_str.substr(separator_i + 1),
{III}">"
{II});

{II}our_data->node_buffer.emplace_back(
{III}common::make_unique<ErrorNode>(
{IIII}XML_GetCurrentLineNumber(our_data->parser),
{IIII}XML_GetCurrentColumnNumber(our_data->parser),
{IIII}message
{III})
{II});

{II}XML_StopParser(our_data->parser, false);
{II}our_data->stopped = true;
{II}return;
{I}}}

{I}if (
{II}attributes[0] != nullptr
{II}&& !(our_data->additional_attributes)
{I}) {{
{II}std::string message = common::Concat(
{III}"Additional attributes are not allowed, "
{III}"but the attribute ",
{III}attributes[0],
{III}" was read in the start element <",
{III}name_str.substr(separator_i + 1),
{III}">"
{II});

{II}our_data->node_buffer.emplace_back(
{III}common::make_unique<ErrorNode>(
{IIII}XML_GetCurrentLineNumber(our_data->parser),
{IIII}XML_GetCurrentColumnNumber(our_data->parser),
{IIII}message
{III})
{II});

{II}XML_StopParser(our_data->parser, false);
{II}our_data->stopped = true;
{II}return;
{I}}}

{I}our_data->node_buffer.emplace_back(
{II}common::make_unique<StartNode>(
{III}name_str.substr(separator_i + 1)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
void XMLCALL OnStopElement(
{I}void* user_data,
{I}const char* name
) {{
{I}auto* our_data = static_cast<OurData*>(user_data);

{I}// NOTE (mristin):
{I}// Since Expat continues parsing and adding nodes even if the parsing is
{I}// suspended (see the documentation of `XML_StopParser`), we have to ignore
{I}// any further events.
{I}if (our_data->stopped) {{
{II}return;
{I}}}

{I}const std::string name_str(name);

{I}size_t separator_i = name_str.find(kNamespaceSeparator);
{I}if (separator_i == std::string::npos || separator_i == 0) {{
{II}std::string message = common::Concat(
{III}"The namespace is missing in the stop element </",
{III}name_str,
{III}">"
{II});

{II}our_data->node_buffer.emplace_back(
{III}common::make_unique<ErrorNode>(
{IIII}XML_GetCurrentLineNumber(our_data->parser),
{IIII}XML_GetCurrentColumnNumber(our_data->parser),
{IIII}message
{III})
{II});

{II}XML_StopParser(our_data->parser, false);
{II}our_data->stopped = true;
{II}return;
{I}}}

{I}if (name_str.compare(0, separator_i, kNamespace) != 0) {{
{II}std::string message = common::Concat(
{III}"We expected the XML namespace ",
{III}kNamespace,
{III}", but we got the namespace ",
{III}name_str.substr(0, separator_i),
{III}" in the stop element </",
{III}name_str.substr(separator_i + 1),
{III}">"
{II});

{II}our_data->node_buffer.emplace_back(
{III}common::make_unique<ErrorNode>(
{IIII}XML_GetCurrentLineNumber(our_data->parser),
{IIII}XML_GetCurrentColumnNumber(our_data->parser),
{IIII}message
{III})
{II});

{II}XML_StopParser(our_data->parser, false);
{II}our_data->stopped = true;
{II}return;
{I}}}

{I}our_data->node_buffer.emplace_back(
{II}common::make_unique<StopNode>(
{III}name_str.substr(separator_i + 1)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
void XMLCALL OnText(
{I}void* user_data,
{I}const char* val,
{I}int len
) {{
{I}auto our_data = static_cast<OurData*>(user_data);

{I}// NOTE (mristin):
{I}// Since Expat continues parsing and adding nodes even if the parsing is
{I}// suspended (see the documentation of `XML_StopParser`), we have to ignore
{I}// any further events.
{I}if (our_data->stopped) {{
{II}return;
{I}}}

{I}our_data->node_buffer.emplace_back(
{II}common::make_unique<TextNode>(
{III}std::string(val, len)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
void Reader::Initialize() {{
{I}// NOTE (mristin):
{I}// We set up the underlying parser here instead of the constructor
{I}// to avoid throwing exceptions in the constructor.

{I}if (parser_ != nullptr) {{
{II}throw std::logic_error(
{III}"You are trying to re-initialize an initialized XML reader."
{II});
{I}}}

{I}if (
{II}buffer_size_
{II}> static_cast<size_t>(
{III}(std::numeric_limits<int>::max)()
{II})
{I}) {{
{II}throw std::invalid_argument(
{III}common::Concat(
{IIII}"Expat library expects the buffer size as int, "
{IIII}"but the given buffer size ",
{IIII}std::to_string(buffer_size_),
{IIII}" does not fit in an int as it is larger than the maximum int ",
{IIII}std::to_string(std::numeric_limits<int>::max())
{III})
{II});
{I}}}

{I}parser_ = XML_ParserCreateNS(nullptr, kNamespaceSeparator);
{I}our_data_ = common::make_unique<OurData>(
{II}additional_attributes_,
{II}buffer_size_,
{II}parser_,
{II}node_buffer_
{I});

{I}XML_SetUserData(parser_, our_data_.get());
{I}XML_SetElementHandler(
{II}parser_,
{II}OnStartElement,
{II}OnStopElement
{I});
{I}XML_SetCharacterDataHandler(parser_, OnText);

{I}chunk_.resize(buffer_size_);

{I}Read();
}}"""
        ),
        Stripped(
            f"""\
void Reader::Read() {{
{I}if (parser_ == nullptr) {{
{II}throw std::logic_error(
{III}"You are trying to read from an uninitialized XML reader"
{II});
{I}}}

{I}if (eof_) {{
{II}throw std::logic_error(
{III}"The XML reader reached the end-of-input, "
{III}"but you called Read()"
{II});
{I}}}

{I}if (error_) {{
{II}throw std::logic_error(
{III}"There was an error while reading XML, "
{III}"but you called Read() again"
{II});
{I}}}

{I}while (node_buffer_.empty()) {{
{II}// NOTE (mristin):
{II}// We read and parse the next chunk of input, until we parsed a whole node.
{II}// The text, however, will be fragmented by Expat's design.

{II}is_.read(&(chunk_[0]), buffer_size_);

{II}const std::streamsize actual_bytes_read = is_.gcount();

{II}if (is_.bad()) {{
{III}SetCurrentAndEofAndError(
{IIII}common::make_unique<ErrorNode>(
{IIIII}0,
{IIIII}0,
{IIIII}"Failed to read from the input"
{IIII})
{III});
{III}return;
{II}}}

{II}if (actual_bytes_read == 0) {{
{III}if (is_.eof()) {{
{IIII}SetCurrentAndEofAndError(common::make_unique<EofNode>());
{IIII}return;
{III}}} else {{
{IIII}SetCurrentAndEofAndError(
{IIIII}common::make_unique<ErrorNode>(
{IIIIII}0,
{IIIIII}0,
{IIIIII}"Read zero bytes from the input, "
{IIIIII}"but the input is neither eof() nor bad()"
{IIIII})
{IIII});
{IIII}return;
{III}}}
{II}}} else {{
{III}const bool done = is_.eof();

{III}if (actual_bytes_read > std::numeric_limits<int>::max()) {{
{IIII}std::string message = common::Concat(
{IIIII}"Expat library expects the buffer size as int, ",
{IIIII}"but the actual number of bytes read ",
{IIIII}std::to_string(actual_bytes_read),
{IIIII}" does not fit in an int as it is larger than the maximum int ",
{IIIII}std::to_string(std::numeric_limits<int>::max())
{IIII});

{IIII}throw std::runtime_error(message);
{III}}}

{III}const auto actual_bytes_read_int = static_cast<int>(actual_bytes_read);

{III}XML_Status status = XML_Parse(
{IIII}parser_,
{IIII}&(chunk_[0]),
{IIII}actual_bytes_read_int,
{IIII}done
{III});

{III}if (status == XML_STATUS_ERROR) {{
{IIII}XML_Error error_code = XML_GetErrorCode(parser_);

{IIII}if (error_code == XML_ERROR_ABORTED) {{
{IIIII}if (node_buffer_.empty()) {{
{IIIIII}throw std::logic_error(
{IIIIIII}"The XML parsing was aborted, "
{IIIIIII}"so we expected an error node on the buffer, "
{IIIIIII}"but the buffer was empty"
{IIIIII});
{IIIII}}}

{IIIII}if (node_buffer_.back()->kind() != NodeKind::Error) {{
{IIIIII}std::string message = common::Concat(
{IIIIIII}"The XML parsing was aborted, "
{IIIIIII}"so we expected an error node on the buffer, "
{IIIIIII}"but we got ",
{IIIIIII}NodeKindToHumanReadableString(node_buffer_.back()->kind())
{IIIIII});

{IIIIII}throw std::logic_error(message);
{IIIII}}}
{IIII}}} else {{
{IIIII}const XML_LChar* error_str = XML_ErrorString(error_code);

{IIIII}node_buffer_.emplace_back(
{IIIIII}common::make_unique<ErrorNode>(
{IIIIIII}XML_GetCurrentLineNumber(parser_),
{IIIIIII}XML_GetCurrentColumnNumber(parser_),
{IIIIIII}std::string(error_str)
{IIIIII})
{IIIII});
{IIII}}}
{III}}} else {{
{IIII}if (done) {{
{IIIII}node_buffer_.emplace_back(common::make_unique<EofNode>());
{IIII}}}
{III}}}
{II}}}
{I}}}

{I}SetCurrentAndEofAndError(std::move(node_buffer_.front()));
{I}node_buffer_.pop_front();
}}"""
        ),
        Stripped(
            f"""\
const INode& Reader::node() const {{
{I}return *current_;
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<INode> Reader::moved_node() {{
{I}return std::move(current_);
}}"""
        ),
        Stripped(
            f"""\
Reader::~Reader() {{
{I}if (parser_ != nullptr) {{
{II}XML_ParserFree(parser_);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
void Reader::SetCurrentAndEofAndError(
{I}std::unique_ptr<INode> node
) {{
{I}current_ = std::move(node);

{I}#ifdef __clang__
{I}#pragma clang diagnostic push
{I}#pragma clang diagnostic ignored "-Wswitch"
{I}#endif
{I}switch (current_->kind()) {{
{II}case NodeKind::Eof:
{III}eof_ = true;
{III}break;
{II}case NodeKind::Error:
{III}error_ = true;
{III}break;
{I}}}
{I}#ifdef __clang__
{I}#pragma clang diagnostic pop
{I}#endif
}}"""
        ),
        Stripped("// endregion class Reader"),
        Stripped("// region class ReaderMergingText"),
        Stripped(
            f"""\
/**
 * \\brief Read XML in forms of nodes, with text nodes read in whole.
 *
 * This is a reader on top of the \\ref Reader which keeps the text fragments
 * in the buffer. We need to process the text in whole during the XML
 * de-serialization, so this buffering is necessary. However, this means that
 * the text is kept in four copies (one partial copy in Expat buffer,
 * another partial copy as fragmented text nodes in the underlying \\ref Reader
 * instance, yet another copy in the internal buffer of this instance, and
 * finally the fourth copy as the merged complete text).
 */
class ReaderMergingText {{
 public:
{I}ReaderMergingText(
{II}std::istream& is,
{II}const ReadingOptions& options
{I});

{I}/**
{I} * Set up the reader for the XML parsing and read the first node.
{I} */
{I}void Initialize();

{I}/**
{I} * Read the next node in the document.
{I} */
{I}void Read();

{I}/**
{I} * @return the node which has been read last
{I} */
{I}const INode& node() const;

{I}/**
{I} * @return set if the current node represents an error
{I} */
{I}bool error() const;

{I}/**
{I} * @return set if the current node represents an end-of-input
{I} */
{I}bool eof() const;

 private:
{I}bool initialized_;
{I}Reader reader_;

{I}std::unique_ptr<INode> current_;
{I}std::unique_ptr<INode> look_ahead_;

{I}// Assuming that the underlying reader points to a text node,
{I}// read all the consecutive text nodes and set the look-ahead node
{I}void ReadAndMergeAllTextAndSetLookahead();

{I}bool error_;
{I}bool eof_;
{I}void SetCurrentAndEofAndError(
{II}std::unique_ptr<INode> node
{I});
}};  // class ReaderMergingText"""
        ),
        Stripped(
            f"""\
ReaderMergingText::ReaderMergingText(
{II}std::istream& is,
{II}const ReadingOptions& options
) :
{I}initialized_(false),
{I}reader_(is, options),
{I}current_(common::make_unique<BofNode>()),
{I}error_(false),
{I}eof_(false) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
void ReaderMergingText::Initialize() {{
{I}if (initialized_) {{
{II}throw std::logic_error(
{III}"You are trying to initialize "
{III}"an already initialized ReaderMergingText"
{II});
{I}}}

{I}reader_.Initialize();

{I}// NOTE (mristin):
{I}// The `reader_` has already read a node. Hence, we need to parse it here
{I}// separately from `ReaderMergingText::Read` method.

{I}if (reader_.node().kind() != NodeKind::Text) {{
{II}SetCurrentAndEofAndError(reader_.moved_node());
{I}}} else {{
{II}ReadAndMergeAllTextAndSetLookahead();
{I}}}

{I}initialized_ = true;
}}"""
        ),
        Stripped(
            f"""\
void ReaderMergingText::Read() {{
{I}if (!initialized_) {{
{II}throw std::logic_error(
{III}"You are reading from an uninitialized ReaderMergingText"
{II});
{I}}}

{I}if (eof()) {{
{II}throw std::logic_error(
{III}"You are trying to read from a ReaderMergingText, "
{III}"but it reached the end-of-input"
{II});
{I}}}

{I}if (error()) {{
{II}throw std::logic_error(
{III}"You are trying to read from a ReaderMergingText, "
{III}"but an error already occurred"
{II});
{I}}}

{I}if (look_ahead_ != nullptr) {{
{II}SetCurrentAndEofAndError(std::move(look_ahead_));
{II}return;
{I}}}

{I}reader_.Read();
{I}if (reader_.node().kind() != NodeKind::Text) {{
{II}SetCurrentAndEofAndError(reader_.moved_node());
{I}}} else {{
{II}ReadAndMergeAllTextAndSetLookahead();
{I}}}
}}"""
        ),
        Stripped(
            f"""\
const INode& ReaderMergingText::node() const {{
{I}return *current_;
}}"""
        ),
        Stripped(
            f"""\
bool ReaderMergingText::error() const {{
{I}return error_;
}}"""
        ),
        Stripped(
            f"""\
bool ReaderMergingText::eof() const {{
{I}return eof_;
}}"""
        ),
        Stripped(
            f"""\
void ReaderMergingText::ReadAndMergeAllTextAndSetLookahead() {{
{I}if (reader_.node().kind() != NodeKind::Text) {{
{II}std::string message = common::Concat(
{III}"Expected the current node in the reader "
{III}"underlying ReaderMergingText to be a text, "
{III}"but it was ",
{III}NodeKindToHumanReadableString(reader_.node().kind())
{II});

{II}throw std::logic_error(message);
{I}}}

{I}std::deque<std::string> text_buffer;

{I}while (reader_.node().kind() == NodeKind::Text) {{
{II}const TextNode& fragment_text_node(
{III}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIII}const TextNode&
{III}>(
{IIII}reader_.node()
{III})
{II});

{II}text_buffer.emplace_back(fragment_text_node.text);

{II}reader_.Read();
{I}}}
{I}look_ahead_ = reader_.moved_node();

{I}size_t size = 0;
{I}for (const std::string& fragment : text_buffer) {{
{II}size += fragment.size();
{I}}}

{I}std::string text;
{I}text.reserve(size);
{I}while (!text_buffer.empty()) {{
{II}text.append(text_buffer.front());
{II}text_buffer.pop_front();
{I}}}

{I}SetCurrentAndEofAndError(common::make_unique<TextNode>(text));
}}"""
        ),
        Stripped(
            f"""\
void ReaderMergingText::SetCurrentAndEofAndError(std::unique_ptr<INode> node) {{
{I}current_ = std::move(node);

{I}#ifdef __clang__
{I}#pragma clang diagnostic push
{I}#pragma clang diagnostic ignored "-Wswitch"
{I}#endif
{I}switch (current_->kind()) {{
{II}case NodeKind::Eof:eof_ = true;
{III}break;
{II}case NodeKind::Error:error_ = true;
{III}break;
{I}}}
{I}#ifdef __clang__
{I}#pragma clang diagnostic pop
{I}#endif
}}"""
        ),
        Stripped("// endregion class ReaderMergingText"),
        Stripped("// endregion Reading"),
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
{I}ReaderMergingText& reader
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
{I}ReaderMergingText& reader
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


def _generate_node_to_human_readable_string() -> List[Stripped]:
    """Generate the function which checks the node kind at the reader cursor."""
    # NOTE (mristin):
    # We have to keep the two functions in semantic sync. We simply copy/paste code
    # to avoid C++ template magic.

    return [
        Stripped(
            f"""\
std::string NodeToHumanReadableString(
{I}const INode& node
) {{
{I}switch (node.kind()) {{
{II}case NodeKind::Bof:
{III}return "beginning-of-input";

{II}case NodeKind::Start: {{
{III}const StartNode& start_node(
{IIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const StartNode&
{IIII}>(node)
{III});

{III}return common::Concat(
{IIII}"a start node <",
{IIII}start_node.name,
{IIII}">"
{III});
{II}}}

{II}case NodeKind::Stop: {{
{III}const StopNode& stop_node(
{IIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const StopNode&
{IIII}>(node)
{III});

{III}return common::Concat(
{IIII}"a stop node </",
{IIII}stop_node.name,
{IIII}">"
{III});
{II}}}

{II}case NodeKind::Text:
{III}return "an XML text";

{II}case NodeKind::Eof:
{III}return "end-of-input";

{II}case NodeKind::Error:
{III}return "an XML error";

{II}default:
{III}throw std::invalid_argument(
{IIII}common::Concat(
{IIIII}"Unexpected node kind: ",
{IIIII}std::to_string(
{IIIIII}static_cast<uint32_t>(node.kind())
{IIIII})
{IIII})
{III});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
std::wstring NodeToHumanReadableWstring(
{I}const INode& node
) {{
{I}switch (node.kind()) {{
{II}case NodeKind::Bof:
{III}return L"beginning-of-input";

{II}case NodeKind::Start: {{
{III}const StartNode& start_node(
{IIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const StartNode&
{IIII}>(node)
{III});

{III}return common::Concat(
{IIII}L"a start node <",
{IIII}common::Utf8ToWstring(start_node.name),
{IIII}L">"
{III});
{II}}}

{II}case NodeKind::Stop: {{
{III}const StopNode& stop_node(
{IIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const StopNode&
{IIII}>(node)
{III});

{III}return common::Concat(
{IIII}L"a stop node </",
{IIII}common::Utf8ToWstring(stop_node.name),
{IIII}L">"
{III});
{II}}}

{II}case NodeKind::Text:
{III}return L"an XML text";

{II}case NodeKind::Eof:
{III}return L"end-of-input";

{II}case NodeKind::Error:
{III}return L"an XML error";

{II}default:
{III}throw std::invalid_argument(
{IIII}common::Concat(
{IIIII}"Unexpected node kind: ",
{IIIII}std::to_string(
{IIIIII}static_cast<uint32_t>(node.kind())
{IIIII})
{IIII})
{III});
{I}}}
}}"""
        ),
    ]


def _generate_check_is_stop_node_with_name() -> Stripped:
    """Generate the function to check for the stop node with the given name."""
    return Stripped(
        f"""\
/**
 * Check that the given node is a stop node and that its name corresponds to
 * the expected name.
 */
bool IsStopNodeWithName(
{I}const INode& node,
{I}const std::string& expected_name
) {{
{I}if (node.kind() != NodeKind::Stop) {{
{II}return false;
{I}}}

{I}const std::string& name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const StopNode&
{II}>(node).name
{I});
{I}if (name != expected_name) {{
{II}return false;
{I}}}

{I}return true;
}}"""
    )


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
{I}ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != NodeKind::Error) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected an error node at the reader cursor, but got ",
{IIII}NodeToHumanReadableString(reader.node())
{III})
{II});
{I}}}

{I}const auto error_node(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const ErrorNode&
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
{I}ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != NodeKind::Error) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected an error node at the reader cursor, but got ",
{IIII}NodeToHumanReadableString(reader.node())
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
{I}const ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in CheckReaderAtEof. "
{III}"CheckReaderAtEof expects no reader error at entry."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != NodeKind::Eof) {{
{II}return common::make_optional<DeserializationError>(
{III}common::Concat(
{IIII}L"Expected end-of-input, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
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
{I}ReaderMergingText& reader
) {{
{I}if (reader.node().kind() != NodeKind::Bof) {{
{II}return common::nullopt;
{I}}}

{I}reader.Read();
{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader
) {{
{I}while (reader.node().kind() == NodeKind::Text) {{
{II}const TextNode& text_node(
{III}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIII}const TextNode&
{III}>(
{IIII}reader.node()
{III})
{II});

{II}if (!IsWhitespace(text_node.text)) {{
{III}break;
{II}}}

{II}reader.Read();
{I}}}

{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader,
{I}const std::wstring& interface_name,
{I}const DispatchT& dispatch
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
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

{I}if (reader.node().kind() != NodeKind::Start) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}std::shared_ptr<T>
{II}>(
{III}common::Concat(
{IIII}L"Expected a start element opening an instance of ",
{IIII}interface_name,
{IIII}L", but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const StartNode&
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

{I}if (reader.node().kind() == NodeKind::Error) {{
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

{I}if (!IsStopNodeWithName(reader.node(), name)) {{
{II}error = DeserializationError(
{III}common::Concat(
{IIII}L"Expected a stop element </",
{IIII}common::Utf8ToWstring(name),
{IIII}L"> closing an instance of ",
{IIII}interface_name,
{IIII}L", but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
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
{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader
) {{
{I}return {deserialize_class_from_element}<types::{interface_name}>(
{II}reader,
{II}L"{interface_name}",
{II}[](
{III}ReaderMergingText& a_reader,
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
{I}ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeBool. "
{III}"DeserializeBool expects no error node."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != NodeKind::Text) {{
{II}return NoInstanceAndDeserializationErrorWithCause<bool>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:boolean from XML text, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const TextNode&
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

{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeInt64. "
{III}"DeserializeInt64 expects no error node."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != NodeKind::Text) {{
{II}return NoInstanceAndDeserializationErrorWithCause<int64_t>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:long from XML text, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const TextNode&
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

{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader
) {{
{I}static_assert(
{II}sizeof(double) == 8,
{II}"DeserializeDouble expects double to be 8 bytes, "
{II}"but the size of the double is not 8 bytes"
{I});

{I}#ifdef DEBUG
{I}if (node.kind() == NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeDouble. "
{III}"DeserializeDouble expects no error node."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != NodeKind::Text) {{
{II}return NoInstanceAndDeserializationErrorWithCause<double>(
{III}common::Concat(
{IIII}L"Expected to parse an xs:double from XML text, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const TextNode&
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

{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeWstring. "
{III}"DeserializeWstring expects no error node."
{II});
{I}}}
{I}#endif

{I}switch (reader.node().kind()) {{
{II}case NodeKind::Stop:
{III}// Encountering a stop node means that the string is empty.
{III}return std::make_pair(std::wstring(), common::nullopt);
{II}case NodeKind::Text:
{III}// We pass and continue decoding the text.
{III}break;
{II}default:
{III}return NoInstanceAndDeserializationErrorWithCause<std::wstring>(
{IIII}common::Concat(
{IIIII}L"Expected to parse an xs:string from XML text, but got ",
{IIIIII}NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const TextNode&
{II}>(reader.node()).text
{I});

{I}std::wstring deserialized = common::Utf8ToWstring(text);

{I}// NOTE (mristin):
{I}// We consume the text node.
{I}reader.Read();

{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeByteArray. "
{III}"DeserializeByteArray expects no error node."
{II});
{I}}}
{I}#endif

{I}switch (reader.node().kind()) {{
{II}case NodeKind::Stop:
{III}// Encountering a stop node means empty byte array.
{III}return std::make_pair(
{IIII}std::vector<std::uint8_t>(),
{IIII}common::nullopt
{III});
{II}case NodeKind::Text:
{III}// We pass and continue decoding the byte array.
{III}break;
{II}default:
{III}return NoInstanceAndDeserializationErrorWithCause<
{IIII}std::vector<std::uint8_t>
{III}>(
{IIII}common::Concat(
{IIIII}L"Expected to parse an xs:base64Binary from XML text, but got ",
{IIIIII}NodeToHumanReadableWstring(reader.node())
{IIIII})
{IIII});
{I}}}

{I}const std::string& text(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const TextNode&
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

{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader,
{I}const DeserializeT& deserialize_content,
{I}const std::string& expected_name
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
{II}throw std::logic_error(
{III}"Unexpected unhandled XML error in DeserializeWstring. "
{III}"DeserializeWstring expects no error node."
{II});
{I}}}
{I}#endif

{I}if (reader.node().kind() != NodeKind::Start) {{
{II}return NoInstanceAndDeserializationErrorWithCause<T>(
{III}common::Concat(
{IIII}L"Expected a start element <",
{IIII}common::Utf8ToWstring(expected_name),
{IIII}L"> enclosing a value, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& start_name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const StartNode&
{II}>(reader.node()).name
{I});

{I}if (start_name != expected_name) {{
{II}return NoInstanceAndDeserializationErrorWithCause<T>(
{III}common::Concat(
{IIII}L"Expected a start element <",
{IIII}common::Utf8ToWstring(expected_name),
{IIII}L"> enclosing a value, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the start element.
{I}reader.Read();

{I}if (reader.node().kind() == NodeKind::Error) {{
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

{I}if (reader.node().kind() != NodeKind::Stop) {{
{II}return NoInstanceAndDeserializationErrorWithCause<T>(
{III}common::Concat(
{IIII}L"Expected a closing element </",
{IIII}common::Utf8ToWstring(expected_name),
{IIII}L"> closing a value, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string& stop_name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const StopNode&
{II}>(reader.node()).name
{I});


{I}if (stop_name != expected_name) {{
{II}return NoInstanceAndDeserializationErrorWithCause<T>(
{III}common::Concat(
{IIII}L"Expected a closing element </",
{IIII}common::Utf8ToWstring(expected_name),
{IIII}L"> closing a value, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We consume the closing element.
{I}reader.Read();

{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader,
{I}const DeserializeT& deserialize_item
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}if (reader.node().kind() == NodeKind::Stop) {{
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

{III}if (reader.node().kind() == NodeKind::Stop) {{
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
{I}ReaderMergingText& reader,
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
{I}ReaderMergingText& reader
) {{
{I}#ifdef DEBUG
{I}if (reader.node().kind() == NodeKind::Error) {{
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
[](ReaderMergingText& a_reader) {{
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
[](ReaderMergingText& a_reader) {{
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

        else:
            # noinspection PyTypeChecker
            assert_never(item_type_anno.our_type)

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
if (reader.node().kind() == NodeKind::Error) {{
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

{I}if (reader.node().kind() == NodeKind::Stop) {{
{II}// NOTE (mristin):
{II}// We reached a closing element of an instance, so we know that
{II}// the sequence ended.
{II}break;
{I}}} else if (reader.node().kind() != NodeKind::Start) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}std::shared_ptr<T>
{II}>(
{III}common::Concat(
{IIII}L"Expected a start element opening a property "
{IIII}L"of {interface_name}, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
{III})
{II});
{I}}}

{I}const std::string name(
{II}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{III}const StartNode&
{II}>(reader.node()).name
{I});

{I}// NOTE (mristin):
{I}// We consume the start element.
{I}reader.Read();

{I}if (reader.node().kind() == NodeKind::Error) {{
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

{I}if (!IsStopNodeWithName(reader.node(), name)) {{
{II}error = DeserializationError(
{III}common::Concat(
{IIII}L"Expected a stop element </",
{IIII}common::Utf8ToWstring(name),
{IIII}L"> closing the property "
{IIII}L"of {interface_name}, but got ",
{IIII}NodeToHumanReadableWstring(reader.node())
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

{I}if (reader.node().kind() == NodeKind::Error) {{
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
{I}ReaderMergingText& reader
) {{
{I}{indent_but_first_line(body, I)}
}}"""
        ),
        None,
    )


def _generate_deserialize_from(
    function_name: Identifier, from_element_name: Identifier, interface_name: Identifier
) -> Stripped:
    """
    Generate the impl. of a public de-serialization for an interface.

    We deliberately do not pass in a class object, and pass names instead, in order to
    be able to generate the function both for the most abstract ``IClass`` and
    the classes defined in the symbol table.
    """
    return Stripped(
        f"""\
common::expected<
{I}std::shared_ptr<types::{interface_name}>,
{I}DeserializationError
> {function_name}(
{I}std::istream& is,
{I}const ReadingOptions& options
) {{
{I}ReaderMergingText reader(is, options);

{I}reader.Initialize();
{I}if (reader.node().kind() == NodeKind::Error) {{
{II}return common::make_unexpected(
{III}DeserializationErrorFromReader(reader)
{II});
{I}}}

{I}common::optional<
{II}std::shared_ptr<types::{interface_name}>
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


def _generate_self_closing_writer() -> List[Stripped]:
    """
    Generate the class which writes the nodes to the output stream.

    If an XML element is empty, it will be automatically shortened to a self-closing
    element.
    """
    return [
        Stripped("// region SelfClosingWriter"),
        Stripped(
            f"""\
/**
 * \\brief Write XML nodes to the UTF-8-encoded output stream.
 *
 * The start elements are put on hold until we observe a text, a stop element or
 * end-of-input. This allows us to continuously shorten the XML elements to self-closing
 * tags.
 *
 * The prefix is appended to each element name. If you do not need the prefix,
 * specify it as empty string. In most cases, you put a colon, `:` at the end of
 * the prefix.
 *
 * Each writing method captures any errors and obvious exceptions as
 * serialization errors.
 *
 * Use \\ref error() to check if there is any error.
 */
class SelfClosingWriter {{
 public:
{I}SelfClosingWriter(
{II}std::ostream& os,
{II}std::string prefix
{I});

{I}/**
{I} * Queue a start element for an eventual write.
{I} */
{I}void StartElement(
{II}std::string name
{I});

{I}/**
{I} * Write a stop element.
{I} *
{I} * If there is a pending start element with no content, shorten it to
{I} * a self-closing XML element.
{I} */
{I}void StopElement(
{II}const std::string& name
{I});

{I}/**
{I} * \\brief Serialize the given boolean to an xs:bool value.
{I} *
{I} * We explicitly write longer text, `true` and `false`, to make the values explicit,
{I} * and not potentially confusing with numbers, in the XML.
{I} */
{I}void SerializeBool(
{II}bool value
{I});

{I}/**
{I} * \\brief Serialize the given number to an xs:long value.
{I} *
{I} * We do not check that the number is within a range representable as 64-bit
{I} * floats, as the value can be de-serialized correctly from XML. However, this
{I} * means that XML and JSON serializations are not interoperable. If you need
{I} * interoperability, you have to ensure that range yourself (<i>e.g.</i>, through
{I} * \\ref validation, see also
{I} * https://github.com/aas-core-works/aas-core-meta/issues/298).
{I} */
{I}void SerializeInt64(
{II}int64_t value
{I});

{I}/**
{I} * \\brief Serialize the given number to an xs:double value.
{I} */
{I}void SerializeDouble(
{II}double value
{I});

{I}/**
{I} * \\brief Write the text while escaping special characters for XML.
{I} */
{I}void SerializeWstring(
{II}const std::wstring& text
{I});

{I}/**
{I} * \\brief Write the text while escaping special characters for XML.
{I} */
{I}void SerializeString(
{II}const std::string& text
{I});

{I}/**
{I} * \\brief Encode bytes to Base64 and write them.
{I} */
{I}void SerializeByteArray(
{I}const std::vector<std::uint8_t>& byte_array
{I});

{I}/**
{I} * Finish and flush any pending start nodes.
{I} */
{I}void Finish();

{I}/**
{I} * Get an error, if any, caught during the serialization.
{I} */
{I}const common::optional<SerializationError>& error() const;

{I}/**
{I} * Transfer the ownership of the error.
{I} */
{I}common::optional<SerializationError>&& move_error();

 private:
{I}std::ostream& os_;
{I}std::string prefix_;
{I}common::optional<SerializationError> error_;
{I}common::optional<std::string> pending_start_wo_text_;

{I}/**
{I} * \\brief Escape the given text to XML.
{I} *
{I} * Return nothing if no escaping was needed.
{I} */
{I}static common::optional<std::wstring> EscapeForXml(
{II}const std::wstring& text
{I});

{I}/**
{I} * \\brief Escape the given text to XML.
{I} *
{I} * Return nothing if no escaping was needed.
{I} */
{I}static common::optional<std::string> EscapeForXml(
{II}const std::string& text
{I});

{I}void WritePendingStartElementIfAvailable();

{I}/**
{I} * Write the text without any XML escaping or flushing of pending start elements.
{I} */
{I}void WriteStringWithoutEscapingNorFlushing(
{II}const std::string& text
{I});
}};  // class SelfClosingWriter"""
        ),
        Stripped(
            f"""\
SelfClosingWriter::SelfClosingWriter(
{I}std::ostream& os,
{I}std::string prefix
) :
{I}os_(os),
{I}prefix_(std::move(prefix)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::StartElement(
{I}std::string name
) {{
{I}#ifdef DEBUG
{I}if (error_.has_value()) {{
{II}throw std::logic_error(
{III}"You are trying to queue a start element with a SelfClosingWriter "
{III}"which caught an error."
{II});
{I}#endif

{I}WritePendingStartElementIfAvailable();
{I}if (error_.has_value()) {{
{I}return;
{I}}}

{I}pending_start_wo_text_ = std::move(name);
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::StopElement(
{I}const std::string& name
) {{
{I}#ifdef DEBUG
{I}if (error_.has_value()) {{
{II}throw std::logic_error(
{III}"You are trying to write a stop element with a SelfClosingWriter "
{III}"which caught an error before."
{II});
{I}#endif

{I}if (pending_start_wo_text_.has_value()) {{
{II}#ifdef DEBUG
{II}if (*pending_start_wo_text_ != name) {{
{III}throw std::logic_error(
{IIII}common::Concat(
{IIIII}"The start element <",
{IIIII}*pending_start_wo_text_,
{IIIII}"> is pending for writing, "
{IIIII}"but you are trying to write a stop element </",
{IIIII}name
{IIIII}">"
{IIII})
{III});
{II}}}
{II}#endif

{II}pending_start_wo_text_ = common::nullopt;

{II}WriteStringWithoutEscapingNorFlushing(
{III}common::Concat(
{IIII}"<",
{IIII}prefix_,
{IIII}name,
{IIII}" />"
{III})
{II});
{I}}} else {{
{II}WritePendingStartElementIfAvailable();
{II}if (error_.has_value()) {{
{III}return;
{II}}}

{II}WriteStringWithoutEscapingNorFlushing(
{III}common::Concat(
{IIII}"</",
{IIII}prefix_,
{IIII}name,
{IIII}">"
{III})
{II});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::SerializeBool(
{I}bool value
) {{
{I}WritePendingStartElementIfAvailable();
{I}if (error_.has_value()) {{
{II}return;
{I}}}

{I}WriteStringWithoutEscapingNorFlushing(
{II}value ? "true" : "false"
{I});
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::SerializeInt64(
{I}int64_t value
) {{
{I}WritePendingStartElementIfAvailable();
{I}if (error_.has_value()) {{
{II}return;
{I}}}

{I}WriteStringWithoutEscapingNorFlushing(
{II}std::to_string(value)
{I});
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::SerializeDouble(
{I}double value
) {{
{I}WritePendingStartElementIfAvailable();
{I}if (error_.has_value()) {{
{II}return;
{I}}}

{I}// NOTE (mristin):
{I}// We handle edge values infinity and not-a-number explicitly here
{I}// as some C/C++ implementations might not convert them to XML-conformant
{I}// strings.

{I}if (std::isinf(value)) {{
{II}if (value < 0) {{
{III}WriteStringWithoutEscapingNorFlushing("-INF");
{II}}} else {{
{III}WriteStringWithoutEscapingNorFlushing("INF");
{II}}}
{I}}} else if(std::isnan(value)) {{
{II}WriteStringWithoutEscapingNorFlushing("NaN");
{I}}} else {{
{II}// NOTE (mristin):
{II}// We have to use a stream to avoid trailing zeros. std::to_string always
{II}// outputs trailing zeros up to a certain number of decimal places (usually 6).
{II}std::ostringstream oss;
{II}oss << value;
{II}WriteStringWithoutEscapingNorFlushing(
{III}oss.str()
{II});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::SerializeString(
{I}const std::string& text
) {{
{I}WritePendingStartElementIfAvailable();
{I}if (error_.has_value()) {{
{II}return;
{I}}}

{I}// NOTE (mristin):
{I}// We optimize here for short and long texts, respectively.
{I}// The main assumption is that the short texts can be escaped and converted
{I}// in one go, while the longer texts need to be converted in chunks.

{I}if (text.size() < 1024) {{
{II}common::optional<std::string> escaped = EscapeForXml(text);

{II}if (escaped.has_value()) {{
{III}WriteStringWithoutEscapingNorFlushing(
{IIII}*escaped
{III});
{III}return;
{II}}} else {{
{III}WriteStringWithoutEscapingNorFlushing(
{IIII}text
{III});
{III}return;
{II}}}
{I}}}

{I}size_t start = 0;
{I}while (start < text.size()) {{
{II}const size_t end = std::min(start + 1024, text.size());
{II}const size_t chunk_size = end - start;

{II}// NOTE (mristin):
{II}// We assume that making short copies of text substrings does not hurt
{II}// the performance here, but makes the code more readable.

{II}const std::string chunk = text.substr(start, chunk_size);

{II}common::optional<std::string> escaped = EscapeForXml(chunk);

{II}if (escaped.has_value()) {{
{III}WriteStringWithoutEscapingNorFlushing(
{IIII}*escaped
{III});
{II}}} else {{
{III}WriteStringWithoutEscapingNorFlushing(
{IIII}chunk
{III});
{II}}}

{II}if (error_.has_value()) {{
{III}return;
{II}}}

{II}start += chunk_size;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::SerializeWstring(
{I}const std::wstring& text
) {{
{I}WritePendingStartElementIfAvailable();
{I}if (error_.has_value()) {{
{II}return;
{I}}}

{I}// NOTE (mristin):
{I}// We optimize here for short and long texts, respectively.
{I}// The main assumption is that the short texts can be escaped and converted
{I}// in one go, while the longer texts need to be converted in chunks.

{I}if (text.size() < 1024) {{
{II}common::optional<std::wstring> escaped = EscapeForXml(text);

{II}if (escaped.has_value()) {{
{III}WriteStringWithoutEscapingNorFlushing(
{IIII}common::WstringToUtf8(*escaped)
{III});
{III}return;
{II}}} else {{
{III}WriteStringWithoutEscapingNorFlushing(
{IIII}common::WstringToUtf8(text)
{III});
{III}return;
{II}}}
{I}}}

{I}size_t start = 0;
{I}while (start < text.size()) {{
{II}const size_t end = std::min(start + 1024, text.size());
{II}const size_t chunk_size = end - start;

{II}// NOTE (mristin):
{II}// We assume that making short copies of text substrings does not hurt
{II}// the performance here, but makes the code more readable.

{II}const std::wstring chunk = text.substr(start, chunk_size);

{II}common::optional<std::wstring> escaped = EscapeForXml(chunk);

{II}if (escaped.has_value()) {{
{III}WriteStringWithoutEscapingNorFlushing(
{IIII}common::WstringToUtf8(*escaped)
{III});
{II}}} else {{
{III}WriteStringWithoutEscapingNorFlushing(
{IIII}common::WstringToUtf8(chunk)
{III});
{II}}}

{II}if (error_.has_value()) {{
{III}return;
{II}}}

{II}start += chunk_size;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::SerializeByteArray(
{I}const std::vector<std::uint8_t>& byte_array
) {{
{I}WritePendingStartElementIfAvailable();
{I}if (error_.has_value()) {{
{II}return;
{I}}}

{I}// NOTE (mristin):
{I}// We optimize here for short and long byte arrays, respectively.
{I}// The main assumption is that the short texts can be escaped and converted
{I}// in one go, while the longer texts need to be converted in chunks.
{I}//
{I}// Optimally, we would write an encoding function such that it encodes directly
{I}// to the output stream. As we lack the time resources for that at the moment,
{I}// we go for the compromise with one pass and chunking, respectively.

{I}if (byte_array.size() <= 1536) {{
{II}WriteStringWithoutEscapingNorFlushing(
{III}stringification::Base64Encode(byte_array)
{II});
{II}return;
{I}}}

{I}// NOTE (mristin):
{I}// We assume here that making copies of small sub-arrays does not hurt
{I}// the performance, but makes the code substantially more readable.

{I}size_t start = 0;
{I}while (start < byte_array.size()) {{
{II}// NOTE (mristin):
{II}// We pick a multiple of 3 for the chunk size in order to make the encoding
{II}// of chunking identical to the output as we encoded all bytes at the same time.
{II}//
{II}// See: https://stackoverflow.com/questions/7920780/is-it-possible-to-base64-encode-a-file-in-chunks

{II}const size_t end = std::min(start + 1536, byte_array.size());

{II}const std::vector<std::uint8_t> chunk(
{III}byte_array.begin() + start,
{III}byte_array.begin() + end
{II});

{II}WriteStringWithoutEscapingNorFlushing(
{III}stringification::Base64Encode(chunk)
{II});
{II}if (error_.has_value()) {{
{III}return;
{II}}}
{I}}}
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::Finish() {{
{I}WritePendingStartElementIfAvailable();
}}"""
        ),
        Stripped(
            f"""\
const common::optional<SerializationError>& SelfClosingWriter::error() const {{
{I}return error_;
}}"""
        ),
        Stripped(
            f"""\
common::optional<SerializationError>&& SelfClosingWriter::move_error() {{
{I}return std::move(error_);
}}"""
        ),
        Stripped(
            f"""\
common::optional<std::wstring> SelfClosingWriter::EscapeForXml(
{I}const std::wstring& text
) {{
{I}size_t out_len = 0;

{I}// NOTE (mristin):
{I}// We use sizeof on *strings* instead of *wide strings* to get
{I}// the number of *characters*. Otherwise, if we used wide strings,
{I}// we would obtain the wrong number of characters as we would count
{I}// bytes instead of characters with `sizeof`, which differ in wide strings
{I}// due to encoding.

{I}for (wchar_t character : text ) {{
{II}switch (character) {{
{III}case L'&': {{
{IIII}out_len += sizeof("&amp;");
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
{II}return common::nullopt;
{I}}}

{I}std::wstring out;
{I}out.reserve(out_len);

{I}for (wchar_t character : text ) {{
{II}switch (character) {{
{III}case L'&':
{IIII}out.append(L"&amp;");
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

{I}return common::make_optional<std::wstring>(
{II}std::move(out)
{I});
}}"""
        ),
        Stripped(
            f"""\
common::optional<std::string> SelfClosingWriter::EscapeForXml(
{I}const std::string& text
) {{
{I}size_t out_len = 0;

{I}for (char character : text ) {{
{II}switch (character) {{
{III}case '&': {{
{IIII}out_len += sizeof("&amp;");
{IIII}break;
{III}}}
{III}case '<': {{
{IIII}out_len += sizeof("&lt;");
{IIII}break;
{III}}}
{III}case '>': {{
{IIII}out_len += sizeof("&gt;");
{IIII}break;
{III}}}
{III}case '"': {{
{IIII}out_len += sizeof("&quot;");
{IIII}break;
{III}}}
{III}case '\\'': {{
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
{II}return common::nullopt;
{I}}}

{I}std::string out;
{I}out.reserve(out_len);

{I}for (char character : text ) {{
{II}switch (character) {{
{III}case '&':
{IIII}out.append("&amp;");
{IIII}break;
{III}case '<':
{IIII}out.append("&lt;");
{IIII}break;
{III}case '>':
{IIII}out.append("&gt;");
{IIII}break;
{III}case '"':
{IIII}out.append("&quot;");
{IIII}break;
{III}case '\\'':
{IIII}out.append("&apos;");
{IIII}break;
{III}default:
{IIII}out.push_back(character);
{IIII}break;
{II}}}
{I}}}

{I}return common::make_optional<std::string>(
{II}std::move(out)
{I});
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::WritePendingStartElementIfAvailable() {{
{I}if (!pending_start_wo_text_.has_value()) {{
{II}return;
{I}}}

{I}WriteStringWithoutEscapingNorFlushing(
{II}common::Concat(
{III}"<",
{III}prefix_,
{III}*pending_start_wo_text_,
{III}">"
{II})
{I});

{I}pending_start_wo_text_ = common::nullopt;
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::WriteStringWithoutEscapingNorFlushing(
{I}const std::string& text
) {{
{I}#ifdef DEBUG
{I}if (error_.has_value()) {{
{II}throw std::logic_error(
{III}"You are trying to write to a SelfClosingWriter which "
{III}"caught an error"
{II});
{I}}}
{I}#endif

{I}if (os_.bad()) {{
{II}error_ = common::make_optional<SerializationError>(
{III}kTheOutputStreamIsInABadState
{II});
{II}return;
{I}}}

{I}os_ << text;

{I}if (os_.bad()) {{
{II}error_ = common::make_optional<SerializationError>(
{III}kTheOutputStreamIsInABadState
{II});
{II}return;
{I}}}
}}"""
        ),
        Stripped("// endregion SelfClosingWriter"),
    ]


def _generate_serialize_primitives() -> List[Stripped]:
    return [
        Stripped(
            f"""\
common::optional<SerializationError> SerializeBool(
{I}bool value,
{I}SelfClosingWriter& writer
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
common::optional<SerializationError> SerializeInt64(
{I}int64_t value,
{I}SelfClosingWriter& writer
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
common::optional<SerializationError> SerializeDouble(
{I}double value,
{I}SelfClosingWriter& writer
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
common::optional<SerializationError> SerializeWstring(
{I}const std::wstring& value,
{I}SelfClosingWriter& writer
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
common::optional<SerializationError> SerializeByteArray(
{I}const std::vector<std::uint8_t>& value,
{I}SelfClosingWriter& writer
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
common::optional<SerializationError> SerializeListOfVElements(
{I}const std::vector<T>& list,
{I}SelfClosingWriter& writer,
{I}const SerializeT& serialize_item
) {{
{I}for (size_t i = 0; i < list.size(); ++i) {{
{II}writer.StartElement("v");
{II}if (writer.error().has_value()) {{
{III}common::optional<SerializationError>&& error = writer.move_error();
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<iteration::IndexSegment>(i)
{III});

{III}return error;
{II}}}

{II}common::optional<SerializationError> error = serialize_item(
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
{III}common::optional<SerializationError>&& error = writer.move_error();
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
common::optional<SerializationError> SerializeListOfInstances(
{I}const std::vector<T>& list,
{I}SelfClosingWriter& writer,
{I}const SerializeT& serialize_item
) {{
{I}for (size_t i = 0; i < list.size(); ++i) {{
{II}common::optional<SerializationError> error = serialize_item(
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
common::optional<SerializationError> {function_name}(
{I}const std::tuple<
{II}{indent_but_first_line(item_types_joined, II)}
{I}>& value,
{I}SelfClosingWriter& writer,
{I}{indent_but_first_line(parameters, I)}
) {{
{I}common::optional<SerializationError> error;

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
common::optional<SerializationError> {function_name}(
{I}types::{enum_name} that,
{I}SelfClosingWriter& writer
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
common::optional<SerializationError> SerializePropertyAsElement(
{I}const std::string& name,
{I}const T& value,
{I}SelfClosingWriter& writer,
{I}iteration::Property property,
{I}const SerializeT& serialize_value
) {{
{I}writer.StartElement(name);
{I}if (writer.error().has_value()) {{
{II}return writer.move_error();
{I}}}

{I}common::optional<SerializationError> error = serialize_value(value, writer);
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
    Build the ``(list, writer) -> optional<SerializationError>`` callable for
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
{I}SelfClosingWriter& a_writer
) {{
{I}return {list_helper}(a_list, a_writer, {serialize_item});
}}"""
    )


def _xml_serialize_tuple_value_expr(
    type_anno: intermediate.TupleTypeAnnotation,
) -> Stripped:
    """
    Build the ``(tuple, writer) -> optional<SerializationError>`` callable for
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

        is_class_item = isinstance(
            item_type_anno, intermediate.OurTypeAnnotation
        ) and isinstance(
            item_type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        )

        if not is_class_item:
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
            else:
                # noinspection PyTypeChecker
                assert_never(item_type_anno)

            v_name_literal = cpp_common.string_literal(f"v{i + 1}")

            item_exprs.append(
                Stripped(
                    f"""\
[](
{I}const {indent_but_first_line(item_type, I)}& item,
{I}SelfClosingWriter& a_writer
) -> common::optional<SerializationError> {{
{I}a_writer.StartElement(
{II}{v_name_literal}
{I});
{I}if (a_writer.error().has_value()) {{
{II}common::optional<SerializationError>&& error = a_writer.move_error();
{II}return error;
{I}}}

{I}common::optional<SerializationError> error = {serialize_function}(
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
{II}common::optional<SerializationError>&& error = a_writer.move_error();
{II}return error;
{I}}}

{I}return common::nullopt;
}}"""
                )
            )
        else:
            assert isinstance(item_type_anno, intermediate.OurTypeAnnotation)
            serialize_function = cpp_naming.function_name(
                Identifier(f"serialize_{item_type_anno.our_type.name}_ptr_as_element")
            )

            item_exprs.append(Stripped(serialize_function))

    item_exprs_joined = ",\n".join(item_exprs)

    function_name = f"SerializeTuple{len(type_anno.items)}"

    return Stripped(
        f"""\
[](
{I}const {indent_but_first_line(tuple_type, I)}& a_tuple,
{I}SelfClosingWriter& a_writer
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
common::optional<SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}SelfClosingWriter& writer
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
        blocks.append(Stripped("common::optional<SerializationError> error;"))

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
common::optional<SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}SelfClosingWriter& writer
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
common::optional<SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}SelfClosingWriter& writer
);"""
        ),
        Stripped(
            f"""\
/** @copybrief {function_name}(const types::{interface_name}&, SelfClosingWriter& */
common::optional<SerializationError> {function_name_ptr}(
{I}const std::shared_ptr<types::{interface_name}>& that,
{I}SelfClosingWriter& writer
);"""
        ),
    ]


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
common::optional<SerializationError> error;

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
{description_comment_prefix}common::optional<SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}SelfClosingWriter& writer
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
common::optional<SerializationError> {function_name}(
{I}const types::{interface_name}& that,
{I}SelfClosingWriter& writer
) {{
{I}// NOTE (mristin):
{I}// The dynamic casts are necessary due to virtual inheritance. Otherwise,
{I}// we would have used static casts.

{I}switch (that.model_type()) {{
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
common::optional<SerializationError> {function_name_ptr}(
{I}const std::shared_ptr<types::{interface_name}>& that,
{I}SelfClosingWriter& writer
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

{I}error = CheckOstreamState(os);
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

{I}error = CheckOstreamState(os);
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
{IIII}kTheOutputStreamIsInABadState
{III});
{II}}}
{I}}}

{I}SelfClosingWriter writer(
{II}os,
{II}options.prefix
{I});

{I}common::optional<SerializationError> error;

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

        return False

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        return _type_annotation_contains_tuple_with_atomic_non_class_item(
            type_annotation.value
        )

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

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/stringification.hpp"
#include "{include_prefix_path}/wstringification.hpp"
#include "{include_prefix_path}/xmlization.hpp"

#pragma warning(push, 0)
#include <expat.h>

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
        Stripped(
            f"""\
static_assert(
{I}!std::is_same<XML_Char, wchar_t>::value,
{I}"Expected Expat to be compiled with UTF-8 support, i.e., that character is "
{I}"stored as char internally, "
{I}"but Expat was compiled to store characters internally as UTF-16."
);"""
        ),
        Stripped(
            f"""\
static_assert(
{I}std::is_same<XML_Char, char>::value,
{I}"Expected Expat to be compiled with UTF-8 support, i.e., that "
{I}"character is stored as char internally, "
{I}"but it was not."
);"""
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
        *_generate_node_kind(),
        *_generate_node_classes(),
        *_generate_readers(),
        *_generate_forward_declarations_of_deserialization_functions(
            symbol_table=symbol_table
        ),
        *_generate_element_name_to_model_type(symbol_table=symbol_table),
        *_generate_node_to_human_readable_string(),
        _generate_check_is_stop_node_with_name(),
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

    blocks.extend(_generate_functions_to_deserialize_primitives())

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
            interface_name=Identifier("IClass"),
        )
    )

    for cls in symbol_table.classes:
        blocks.append(
            _generate_deserialize_from(
                function_name=cpp_naming.function_name(Identifier(f"{cls.name}_from")),
                from_element_name=cpp_naming.function_name(
                    Identifier(f"{cls.name}_from_element")
                ),
                interface_name=cpp_naming.interface_name(cls.name),
            )
        )

    output_stream_is_in_a_bad_state_name = cpp_naming.constant_name(
        Identifier("the_output_stream_is_in_a_bad_state")
    )

    blocks.extend(
        [
            Stripped("// endregion De-serialization"),
            Stripped("// region Serialization"),
            Stripped(
                f"""\
/**
 * Represent a serialization error.
 *
 * We use this error internally to avoid unnecessary stack unwinding,
 * but throw the \\ref SerializationException at the final site of
 * the serialization for the user.
 */
struct SerializationError {{
{I}/**
{I} * Human-readable description of the error
{I} */
{I}std::wstring cause;

{I}/**
{I} * Path to the value that caused the error
{I} */
{I}iteration::Path path;

{I}explicit SerializationError(
{II}std::wstring a_cause
{I}) :
{II}cause(std::move(a_cause)) {{
{II}// Intentionally empty.
{I}}}
}};  // struct SerializationError"""
            ),
            Stripped(
                f"""\
const std::wstring {output_stream_is_in_a_bad_state_name}(
{I}L"The output stream is in a bad state."
    );"""
            ),
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
{III}kTheOutputStreamIsInABadState
{II});
{I}}}

{I}return common::nullopt;
}}"""
            ),
            *_generate_serialization_exception_implementation(),
            *_generate_self_closing_writer(),
            *_generate_serialize_primitives(),
        ]
    )

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
