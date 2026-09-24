"""Generate code for common XML de/serialization shared across the tests."""

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
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
    INDENT7 as IIIIIII,
    INDENT8 as IIIIIIII,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(library_namespace: Stripped) -> str:
    """Generate header for common XML de/serialization shared across the tests."""
    include_guard_var = cpp_common.include_guard_var(
        Stripped("test::common::xmlization")
    )

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

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
            f"""\
#include <{include_prefix_path}/types.hpp>"""
        ),
        Stripped(
            """\
#include <filesystem>
#include <string>
#include <vector>"""
        ),
        Stripped(
            """\
namespace test {
namespace common {
namespace xmlization {"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of the `path` and parse it as XML representation of an instance.
 */
std::shared_ptr<
{I}{library_namespace}::types::IClass
> MustReadInstance(
{I}const std::filesystem::path& path
);"""
        ),
        Stripped(
            f"""\
/**
 * Canonicalize the `xml` by stripping away any XML text between the stop and start
 * nodes.
 */
std::string CanonicalizeXml(
{I}const std::string& xml
);"""
        ),
        Stripped(
            f"""\
std::shared_ptr<
{I}{library_namespace}::types::IClass
> MustDeserializeFile(
{I}const std::filesystem::path& path
);"""
        ),
        Stripped(
            """\
}  // namespace xmlization
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
    """Generate implementation for common XML de/serialization shared across the tests."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            '''\
#include "./common_xmlization.hpp"
#include "./common.hpp"'''
        ),
        Stripped(
            f"""\
#include <{include_prefix_path}/xmlization.hpp>"""
        ),
        Stripped(
            """\
#pragma warning(push, 0)
#include <expat.h>
#pragma warning(pop)"""
        ),
        Stripped(
            """\
#include <fstream>"""
        ),
        Stripped(
            f"""\
namespace aas = {library_namespace};"""
        ),
        Stripped(
            """\
namespace test {
namespace common {
namespace xmlization {"""
        ),
        Stripped(
            f"""\
std::shared_ptr<
{I}{library_namespace}::types::IClass
> MustReadInstance(
{I}const std::filesystem::path& path
) {{
{I}std::ifstream ifs(path);

{I}aas::common::expected<
{II}std::shared_ptr<aas::types::IClass>,
{II}aas::xmlization::DeserializationError
{I}> instance = aas::xmlization::From(
{II}ifs
{I});

{I}if (ifs.bad()) {{
{II}throw std::runtime_error(
{III}aas::common::Concat(
{IIII}"Failed to read XML from ",
{IIII}path.string(),
{IIII}"; the bad bit of the file stream is set"
{III})
{II});
{I}}}

{I}if (!instance.has_value()) {{
{II}throw std::runtime_error(
{III}aas::common::Concat(
{IIII}"Failed to parse the instance from the XML file ",
{IIII}path.string(),
{IIII}": ",
{IIII}aas::common::WstringToUtf8(instance.error().path.ToWstring()),
{IIII}": ",
{IIII}aas::common::WstringToUtf8(instance.error().cause)
{III})
{II});
{I}}}

{I}return *instance;
}}"""
        ),
        Stripped(
            """\
namespace canonicalizer {"""
        ),
        Stripped(
            f"""\
struct INode {{
{I}std::string text;

{I}INode(
{II}std::string a_text
{I}) :
{II}text(a_text) {{
{II}// Intentionally empty.
{I}}}

{I}virtual std::unique_ptr<INode> Copy() const = 0;
{I}virtual ~INode() = default;
}};"""
        ),
        Stripped(
            f"""\
struct StartNode : INode {{
{I}std::string name;

{I}StartNode(
{II}std::string a_name,
{II}std::string a_text
{I}) :
{II}INode(std::move(a_text)),
{II}name(std::move(a_name)) {{
{II}// Intentionally empty.
{I}}}

{I}std::unique_ptr<INode> Copy() const override {{
{II}return std::make_unique<StartNode>(*this);
{I}}}

{I}~StartNode() override = default;
}};"""
        ),
        Stripped(
            f"""\
struct TextNode : INode {{
{I}TextNode(
{II}std::string a_text
{I}) : INode(std::move(a_text)) {{
{II}// Intentionally empty.
{I}}}

{I}std::unique_ptr<INode> Copy() const override {{
{II}return std::make_unique<TextNode>(*this);
{I}}}

{I}~TextNode() override = default;
}};"""
        ),
        Stripped(
            f"""\
struct StopNode : INode {{
{I}std::string name;

{I}StopNode(
{II}std::string a_name,
{II}std::string a_text
{I}) :
{II}INode(std::move(a_text)),
{II}name(std::move(a_name)) {{
{II}// Intentionally empty.
{I}}}

{I}std::unique_ptr<INode> Copy() const override {{
{II}return std::make_unique<StopNode>(*this);
{I}}}

{I}~StopNode() override = default;
}};"""
        ),
        Stripped(
            f"""\
/**
 * Structure the data passed over to Expat XML reader.
 */
struct OurData {{
{I}XML_Parser parser;
{I}std::optional<std::string> error;

{I}std::deque<std::unique_ptr<INode> > nodes;

{I}OurData(
{II}XML_Parser a_parser
{I}) :
{II}parser(a_parser) {{
{II}// Intentionally empty.
{I}}}
}};  // struct OurData"""
        ),
        Stripped(
            f"""\
aas::common::expected<
{I}std::string,
{I}std::string
> EscapeForXmlAttribute(const std::string_view& text) {{
{I}// NOTE (mristin):
{I}// See: https://stackoverflow.com/questions/19766669/which-characters-are-permitted-in-xml-attributes
{I}//
{I}// In addition, we assume that we will always surround an attribute by a double-quote.

{I}size_t size = 0;
{I}for (char character : text
{II}) {{
{II}switch (character) {{
{III}case '<':size += sizeof("&lt;");
{IIII}break;
{III}case '"':size += sizeof("&quot;");
{IIII}break;
{III}case '\\0':
{IIII}return aas::common::unexpected<std::string>(
{IIIII}"Unexpected zero character in the text to be escaped "
{IIIII}"for XML attribute. The XML format does not allow zero characters, "
{IIIII}"not even in escaped form."
{IIII});
{III}default:++size;
{II}}}
{I}}}

{I}std::string result;
{I}result.reserve(size);

{I}for (char character : text
{II}) {{
{II}switch (character) {{
{III}case '<':result.append("&lt;");
{IIII}break;
{III}case '"':result.append("&quot;");
{IIII}break;
{III}default:result.push_back(character);
{II}}}
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
aas::common::expected<
{I}std::string,
{I}std::string
> EscapeForXmlText(const std::string_view& text) {{
{I}size_t size = 0;
{I}for (char character : text
{II}) {{
{II}switch (character) {{
{III}case '<':size += sizeof("&lt;");
{IIII}break;
{III}case '>':size += sizeof("&gt;");
{IIII}break;
{III}case '&':size += sizeof("&amp;");
{IIII}break;
{III}case '\\'':size += sizeof("&apos;");
{IIII}break;
{III}case '"':size += sizeof("&quot;");
{IIII}break;
{III}case '\\0':
{IIII}return aas::common::unexpected(
{IIIII}"Unexpected zero character in the text to be escaped "
{IIIII}"for XML attribute. The XML format does not allow zero characters, "
{IIIII}"not even in escaped form."
{IIII});
{III}default:++size;
{II}}}
{I}}}

{I}if (text.size() == size) {{
{II}return std::string(text);
{I}}}

{I}std::string result;
{I}result.reserve(size);

{I}for (char character : text
{II}) {{
{II}switch (character) {{
{III}case '<':result.append("&lt;");
{IIII}break;
{III}case '>':result.append("&gt;");
{IIII}break;
{III}case '&':result.append("&amp;");
{IIII}break;
{III}case '\\'':result.append("&apos;");
{IIII}break;
{III}case '"':result.append("&quot;");
{IIII}break;
{III}default:result.push_back(character);
{II}}}
{I}}}

{I}return result;
}}"""
        ),
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
{I}if (our_data->error.has_value()) {{
{II}return;
{I}}}

{I}std::stringstream ss;
{I}ss << "<" << name;

{I}for (size_t i = 0; attributes[i] != nullptr; i += 2
{II}) {{
{II}const char* attribute_name = attributes[i];
{II}const char* attribute_value = attributes[i + 1];

{II}aas::common::expected<
{III}std::string,
{III}std::string
{II}> escaped = EscapeForXmlAttribute(
{III}std::string_view(
{IIII}attribute_value,
{IIII}strlen(attribute_value)
{III})
{II});
{II}if (!escaped.has_value()) {{
{III}our_data->error = escaped.error();
{III}XML_StopParser(our_data->parser, false);
{III}return;
{II}}}

{II}ss
{III}<< " "
{III}<< attribute_name << "=\\""
{III}<< *escaped
{III}<< "\\"";
{I}}}

{I}ss << ">";

{I}our_data->nodes.emplace_back(
{II}aas::common::make_unique<StartNode>(
{III}name,
{III}ss.str()
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
{I}if (our_data->error.has_value()) {{
{II}return;
{I}}}

{I}our_data->nodes.emplace_back(
{II}aas::common::make_unique<StopNode>(
{III}name,
{III}aas::common::Concat(
{IIII}"</", name, ">"
{III})
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
{I}if (our_data->error.has_value()) {{
{II}return;
{I}}}

{I}aas::common::expected<
{II}std::string,
{II}std::string
{I}> escaped = EscapeForXmlText(std::string_view(val, len));

{I}if (!escaped.has_value()) {{
{II}our_data->error = std::move(escaped.error());
{II}XML_StopParser(our_data->parser, false);
{II}return;
{I}}}

{I}our_data->nodes.emplace_back(
{II}aas::common::make_unique<TextNode>(
{III}std::move(*escaped)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
std::deque<std::unique_ptr<INode> > MergeTextNodes(
{I}const std::deque<std::unique_ptr<INode> >& nodes
) {{
{I}std::deque<std::string> parts;

{I}std::deque<std::unique_ptr<INode> > result;

{I}for (const std::unique_ptr<INode>& node : nodes
{II}) {{
{II}auto start_node = dynamic_cast<const StartNode*>(node.get());
{II}auto stop_node = dynamic_cast<const StopNode*>(node.get());

{II}if (start_node != nullptr || stop_node != nullptr) {{
{III}if (!parts.empty()) {{
{IIII}result.emplace_back(
{IIIII}std::make_unique<TextNode>(
{IIIIII}test::common::JoinStrings(parts, "")
{IIIII})
{IIII});
{IIII}parts.clear();
{III}}}

{III}result.emplace_back(node->Copy());

{III}continue;
{II}}}

{II}auto text_node = dynamic_cast<const TextNode*>(node.get());
{II}if (text_node != nullptr) {{
{III}parts.push_back(text_node->text);
{II}}}
{I}}}

{I}if (!parts.empty()) {{
{II}result.emplace_back(
{III}std::make_unique<TextNode>(
{IIII}test::common::JoinStrings(parts, "")
{III})
{II});
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
bool IsWhitespace(const std::string& text) {{
{I}for (const char character : text
{II}) {{
{II}switch (character) {{
{III}case '\\n':continue;
{III}case '\\t':continue;
{III}case '\\r':continue;
{III}case ' ':continue;
{III}default:return false;
{II}}}
{I}}}
{I}return true;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Remove the whitespace between two start/stop nodes with differing names.
 */
std::deque<std::unique_ptr<INode> > RemoveNonSemanticWhiteSpace(
{I}const std::deque<std::unique_ptr<INode> >& nodes
) {{
{I}std::deque<std::unique_ptr<INode> > result;

{I}if (nodes.size() <= 2) {{
{II}for (const auto& node : nodes
{III}) {{
{III}result.emplace_back(node->Copy());
{II}}}
{II}return result;
{I}}}

{I}INode* previous = nullptr;
{I}StartNode* previous_as_start = nullptr;

{I}auto it = nodes.begin();
{I}INode* current = it->get();
{I}StartNode* current_as_start = dynamic_cast<StartNode*>(current);
{I}TextNode* current_as_text = dynamic_cast<TextNode*>(current);

{I}++it;
{I}INode* lookahead = it->get();
{I}StartNode* lookahead_as_start = dynamic_cast<StartNode*>(lookahead);
{I}StopNode* lookahead_as_stop = dynamic_cast<StopNode*>(lookahead);
{I}TextNode* lookahead_as_text = dynamic_cast<TextNode*>(lookahead);

{I}++it;

{I}while (true) {{
{II}// region Determine what to do

{II}// If not set, we include the current node in the result.
{II}bool ignore = (
{III}current_as_text != nullptr
{IIII}&& IsWhitespace(current_as_text->text)
{IIII}&& (
{IIIII}previous == nullptr
{IIIIII}|| lookahead == nullptr
{IIIIII}|| !(
{IIIIIII}previous_as_start != nullptr
{IIIIIIII}&& lookahead_as_stop != nullptr
{IIIIIIII}&& previous_as_start->name == lookahead_as_stop->name
{IIIIII})
{IIII})
{II});
{II}// endregion

{II}// region Act
{II}if (!ignore) {{
{III}result.emplace_back(current->Copy());
{II}}}
{II}// endregion

{II}// region Shift
{II}previous = current;
{II}previous_as_start = current_as_start;

{II}current = lookahead;
{II}current_as_start = lookahead_as_start;
{II}current_as_text = lookahead_as_text;

{II}if (current == nullptr) {{
{III}break;
{II}}}

{II}if (it == nodes.end()) {{
{III}lookahead = nullptr;
{III}lookahead_as_start = nullptr;
{III}lookahead_as_stop = nullptr;
{III}lookahead_as_text = nullptr;
{II}}} else {{
{III}lookahead = it->get();
{III}lookahead_as_start = dynamic_cast<StartNode*>(lookahead);
{III}lookahead_as_stop = dynamic_cast<StopNode*>(lookahead);
{III}lookahead_as_text = dynamic_cast<TextNode*>(lookahead);

{III}++it;
{II}}}
{II}// endregion
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            """\
}  // namespace canonicalizer"""
        ),
        Stripped(
            f"""\
std::string CanonicalizeXml(
{I}const std::string& xml
) {{
{I}const char namespace_separator = ':';
{I}XML_Parser parser = XML_ParserCreateNS(nullptr, namespace_separator);

{I}std::unique_ptr<canonicalizer::OurData> our_data(
{II}aas::common::make_unique<canonicalizer::OurData>(
{III}parser
{II})
{I});

{I}XML_SetUserData(parser, our_data.get());
{I}XML_SetElementHandler(
{II}parser,
{II}canonicalizer::OnStartElement,
{II}canonicalizer::OnStopElement
{I});
{I}XML_SetCharacterDataHandler(parser, canonicalizer::OnText);

{I}XML_Status status = XML_Parse(
{II}parser,
{II}xml.data(),
{II}static_cast<int>(xml.size()),
{II}true
{I});

{I}if (status == XML_STATUS_ERROR) {{
{II}XML_Error error_code = XML_GetErrorCode(parser);

{II}std::string message;

{II}if (error_code == XML_ERROR_ABORTED) {{
{III}if (!our_data->error.has_value()) {{
{IIII}throw std::logic_error(
{IIIII}"The XML parsing was aborted, "
{IIIII}"but the error in our_data was empty"
{IIII});
{III}}}

{III}message = std::move(*our_data->error);
{II}}} else {{
{III}const XML_LChar* error_str = XML_ErrorString(error_code);
{III}message = error_str;
{II}}}

{II}throw std::invalid_argument(
{III}aas::common::Concat(
{IIII}"Failed to parse XML for canonicalization: ",
{IIII}std::to_string(XML_GetCurrentLineNumber(parser)),
{IIII}":",
{IIII}std::to_string(XML_GetCurrentColumnNumber(parser)),
{IIII}": ",
{IIII}message
{III})
{II});
{I}}}

{I}std::deque<
{II}std::unique_ptr<canonicalizer::INode>
{I}> nodes(
{II}std::move(our_data->nodes)
{I});

{I}nodes = canonicalizer::MergeTextNodes(nodes);

{I}nodes = canonicalizer::RemoveNonSemanticWhiteSpace(nodes);

{I}size_t size = 0;
{I}for (const auto& node : nodes) {{
{II}size += node->text.size();
{I}}}

{I}std::string result;
{I}result.reserve(size);

{I}for (const auto& node : nodes) {{
{II}result.append(node->text);
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
std::shared_ptr<
{I}{library_namespace}::types::IClass
> MustDeserializeFile(
{I}const std::filesystem::path& path
) {{
{I}std::ifstream ifs(path, std::ios::binary);

{I}aas::common::expected<
{II}std::shared_ptr<aas::types::IClass>,
{II}aas::xmlization::DeserializationError
{I}> deserialized = aas::xmlization::From(
{II}ifs
{I});

{I}if (ifs.bad()) {{
{II}throw std::runtime_error(
{III}aas::common::Concat(
{IIII}"The file stream is in the bad mode after "
{IIII}"reading and parsing the file as XML: ",
{IIII}path.string()
{III})
{II});
{I}}}

{I}if (!deserialized.has_value()) {{
{II}throw std::runtime_error(
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
{II});
{I}}}

{I}return std::move(deserialized.value());
}}"""
        ),
        Stripped(
            """\
}  // namespace xmlization
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
