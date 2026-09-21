"""Generate code for the low-level XML tokenizer and writer."""

# NOTE (mristin):
# This module is private (it is emitted to ``src/``, never installed alongside
# the public headers in ``include/``). It provides the generic, meta-model-
# independent building blocks -- a streaming Expat-based reader emitting
# a small set of node kinds, and a self-closing-element writer -- shared by
# both ``xmlization`` (which reads/writes the meta-model's own classes) and
# ``xml_rpc`` (which reads/writes JSON-able values in the XML-RPC subset).
# Neither of those two modules duplicates this code; they both depend on it.
#
# Unlike most of the other C++ library modules, the content generated here does
# not depend on the meta-model (``symbol_table``) at all -- it is always
# the same, exactly as with ``revm`` or ``pattern``.

import io
from typing import List

from aas_core_codegen import intermediate
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


# region Node kind


def _generate_node_kind_declaration() -> List[Stripped]:
    """Generate the declaration of the XML node kind and its human-readable form."""
    return [
        Stripped(
            f"""\
enum class NodeKind : std::uint32_t {{
{I}// Nodes of the kind `Bof` represent the beginning-of-input, before any read.
{I}Bof = 0,
{I}// Nodes of the kind `Start` and `Stop` represent an element which resides in
{I}// \\ref kNamespace.
{I}Start = 1,
{I}Stop = 2,
{I}Text = 3,
{I}// Nodes of the kind `Eof` represent the end-of-input.
{I}Eof = 4,
{I}// Nodes of the kind `Error` represent low-level errors in the XML parsing.
{I}Error = 5,
{I}// Nodes of the kind `StartInNoNamespace` and `StopInNoNamespace` represent
{I}// an element which resides in no namespace at all. Only the XML-RPC subset,
{I}// over which a JSON-able value is de/serialized, is written like that.
{I}StartInNoNamespace = 6,
{I}StopInNoNamespace = 7
}};  // enum class NodeKind"""
        ),
        Stripped(
            """\
extern const std::unordered_map<
    NodeKind,
    std::string
> kNodeKindToHumanReadableString;"""
        ),
        Stripped(
            """\
const std::string& NodeKindToHumanReadableString(NodeKind kind);"""
        ),
    ]


def _generate_node_kind_implementation() -> List[Stripped]:
    """Generate the implementation of the XML node kind handling."""
    return [
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
{I}{{NodeKind::StartInNoNamespace, "a start element in no namespace"}},
{I}{{NodeKind::StopInNoNamespace, "a stop element in no namespace"}},
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


# endregion

# region Nodes


def _generate_node_classes() -> List[Stripped]:
    """
    Generate the definition of the XML nodes.

    These are trivial enough (mostly one-liner accessors) that we define them
    directly in the header, as ordinary inline member functions -- this is
    valid, idiomatic C++ and avoids an otherwise pointless header/implementation
    split for a handful of one-liners.
    """
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
{I}StartNode(
{II}std::string a_name,
{II}bool an_in_namespace
{I}) :
{II}name(std::move(a_name)),
{II}in_namespace(an_in_namespace) {{
{II}// Intentionally empty.
{I}}}

{I}NodeKind kind() const override {{
{II}return in_namespace
{III}? NodeKind::Start
{III}: NodeKind::StartInNoNamespace;
{I}}}

{I}/**
{I} * Name of the start element, stripped of the XML namespace
{I} */
{I}const std::string name;

{I}/**
{I} * True if the element resides in \\ref kNamespace, and false if it resides
{I} * in no namespace at all
{I} */
{I}const bool in_namespace;

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
{I}StopNode(
{II}std::string a_name,
{II}bool an_in_namespace
{I}) :
{II}name(std::move(a_name)),
{II}in_namespace(an_in_namespace) {{
{II}// Intentionally empty.
{I}}}

{I}NodeKind kind() const override {{
{II}return in_namespace
{III}? NodeKind::Stop
{III}: NodeKind::StopInNoNamespace;
{I}}}

{I}/**
{I} * Name of the stop element, stripped of the XML namespace
{I} */
{I}const std::string name;

{I}/**
{I} * True if the element resides in \\ref kNamespace, and false if it resides
{I} * in no namespace at all
{I} */
{I}const bool in_namespace;

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


def _generate_node_helpers_declaration() -> List[Stripped]:
    """Generate the declaration of the generic, node-level helper functions."""
    return [
        Stripped(
            """\
/**
 * Render the node in a human-readable form, meant for error messages.
 */
std::string NodeToHumanReadableString(const INode& node);"""
        ),
        Stripped(
            """\
/**
 * Render the node in a human-readable form, meant for error messages.
 */
std::wstring NodeToHumanReadableWstring(const INode& node);"""
        ),
        Stripped(
            """\
/**
 * Check that the given node is a stop node residing in \\ref kNamespace and
 * that its name corresponds to the expected name.
 */
bool IsStopNodeWithName(
    const INode& node,
    const std::string& expected_name
);"""
        ),
        Stripped(
            """\
/**
 * Check that the given node is a stop node residing in no namespace at all and
 * that its name corresponds to the expected name.
 */
bool IsStopNodeWithNameInNoNamespace(
    const INode& node,
    const std::string& expected_name
);"""
        ),
    ]


def _generate_node_helpers_implementation() -> List[Stripped]:
    """Generate the implementation of the generic, node-level helper functions."""
    # NOTE (mristin):
    # We have to keep ``NodeToHumanReadableString`` and ``NodeToHumanReadableWstring``
    # in semantic sync. We simply copy/paste code to avoid C++ template magic.
    return [
        Stripped(
            f"""\
std::string NodeToHumanReadableString(
{I}const INode& node
) {{
{I}switch (node.kind()) {{
{II}case NodeKind::Bof:
{III}return "beginning-of-input";

{II}case NodeKind::Start:
{II}case NodeKind::StartInNoNamespace: {{
{III}const StartNode& start_node(
{IIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const StartNode&
{IIII}>(node)
{III});

{III}return common::Concat(
{IIII}"a start node <",
{IIII}start_node.name,
{IIII}start_node.in_namespace ? ">" : "> in no namespace"
{III});
{II}}}

{II}case NodeKind::Stop:
{II}case NodeKind::StopInNoNamespace: {{
{III}const StopNode& stop_node(
{IIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const StopNode&
{IIII}>(node)
{III});

{III}return common::Concat(
{IIII}"a stop node </",
{IIII}stop_node.name,
{IIII}stop_node.in_namespace ? ">" : "> in no namespace"
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
{IIIIII}static_cast<std::uint32_t>(node.kind())
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

{II}case NodeKind::Start:
{II}case NodeKind::StartInNoNamespace: {{
{III}const StartNode& start_node(
{IIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const StartNode&
{IIII}>(node)
{III});

{III}return common::Concat(
{IIII}L"a start node <",
{IIII}common::Utf8ToWstring(start_node.name),
{IIII}start_node.in_namespace ? L">" : L"> in no namespace"
{III});
{II}}}

{II}case NodeKind::Stop:
{II}case NodeKind::StopInNoNamespace: {{
{III}const StopNode& stop_node(
{IIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const StopNode&
{IIII}>(node)
{III});

{III}return common::Concat(
{IIII}L"a stop node </",
{IIII}common::Utf8ToWstring(stop_node.name),
{IIII}stop_node.in_namespace ? L">" : L"> in no namespace"
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
{IIIIII}static_cast<std::uint32_t>(node.kind())
{IIIII})
{IIII})
{III});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
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
        ),
        Stripped(
            f"""\
bool IsStopNodeWithNameInNoNamespace(
{I}const INode& node,
{I}const std::string& expected_name
) {{
{I}if (node.kind() != NodeKind::StopInNoNamespace) {{
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
        ),
    ]


# endregion

# region Reading


def _generate_xsd_lexical_helpers_declaration() -> List[Stripped]:
    """
    Generate the declaration of the XSD lexical helpers.

    These normalize and match the text of an element against the lexical
    space that XSD prescribes. They live here, and not in the xmlization,
    because both the xmlization and the XML-RPC de-serialization need them,
    and the xmlization is the one which includes the XML-RPC, not the other
    way around.
    """
    return [
        Stripped(
            """\
/**
 * \\brief Normalize \\p text the way `whiteSpace="collapse"` prescribes.
 *
 * Every atomic XSD type except a string, and every type derived from one by
 * restriction, fixes `whiteSpace` to `collapse`, and a schema author can not
 * change it. A tab, a line feed and a carriage return each become a space,
 * a run of spaces becomes one space, and the leading and trailing spaces go.
 * Only the result of that is a lexical representation to be matched.
 *
 * Mind that this strips only the whitespace *around* the value: a space
 * within it survives as a single space, so `2  3` becomes `2 3`, which is
 * still no number.
 *
 * See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace
 */
std::string CollapseWhitespace(const std::string& text);"""
        ),
        Stripped(
            """\
/**
 * \\brief Tell whether \\p text is a numeral of the `xs:long` lexical space.
 *
 *     [-+]?[0-9]+
 *
 * The range is left to the parser, which refuses what does not fit
 * a 64-bit integer.
 *
 * See: https://www.w3.org/TR/xmlschema-2/#long
 */
bool MatchesXsLongNumeral(const std::string& text);"""
        ),
        Stripped(
            """\
/**
 * \\brief Tell whether \\p text is a numeral of the `xs:double` lexical space.
 *
 * The three named literals -- `INF`, `-INF` and `NaN` -- are matched by
 * the caller, so only the numeral is considered here:
 *
 *     (\\+|-)? ( [0-9]+ (\\.[0-9]*)? | \\.[0-9]+ ) ([Ee](\\+|-)?[0-9]+)?
 *
 * This is spelled out rather than left to `std::regex` so that no pattern has
 * to be compiled, and rather than left to `std::stod` because that one reads
 * far more than XSD admits.
 *
 * See: https://www.w3.org/TR/xmlschema-2/#double
 */
bool MatchesXsDoubleNumeral(const std::string& text);"""
        ),
        Stripped(
            """\
/**
 * \\brief Tell whether \\p text is a lexical form of `xs:base64Binary`.
 *
 * The whitespace is expected to be gone already. What is left has to match
 * `(B64 B64 B64 B64)* ((B64 B64 B64 B64) | (B64 B64 B16 '=') | (B64 B04 '=='))?`
 * -- a length which is a multiple of four, the alphabet and nothing else,
 * an equals sign only at the very end, and, easily missed, a constrained
 * character *before* the padding, as the bits which the padding drops have to
 * be zero.
 *
 * The decoders do not agree on any of this, so every target does the same
 * check of its own and refuses the same texts.
 *
 * See: https://www.w3.org/TR/xmlschema-2/#base64Binary
 */
bool MatchesXsBase64Binary(const std::string& text);"""
        ),
        Stripped(
            """\
/**
 * \\brief Drop every whitespace character of \\p text.
 *
 * This is what `xs:base64Binary` needs: it allows whitespace between
 * the characters and not only around them, so collapsing is not enough --
 * the decoder accepts none of it.
 *
 * See: https://www.w3.org/TR/xmlschema-2/#base64Binary
 */
std::string RemoveWhitespace(const std::string& text);"""
        ),
    ]


def _generate_xsd_lexical_helpers_implementation() -> List[Stripped]:
    """Generate the implementation of the XSD lexical helpers."""
    return [
        Stripped(
            f"""\
std::string CollapseWhitespace(const std::string& text) {{
{I}std::string result;
{I}result.reserve(text.size());

{I}bool pending_space = false;
{I}for (const char character : text) {{
{II}if (
{III}character == ' '
{III}|| character == '\\t'
{III}|| character == '\\n'
{III}|| character == '\\r'
{II}) {{
{III}// NOTE (mristin):
{III}// A space is only worth keeping once something has come before it,
{III}// which trims the leading ones, and it is written out only when
{III}// something follows, which trims the trailing ones.
{III}pending_space = !result.empty();
{II}}} else {{
{III}if (pending_space) {{
{IIII}result += ' ';
{IIII}pending_space = false;
{III}}}
{III}result += character;
{II}}}
{I}}}

{I}return result;
}}"""
        ),
        Stripped(
            f"""\
bool MatchesXsLongNumeral(const std::string& text) {{
{I}std::size_t cursor = 0;
{I}const std::size_t size = text.size();

{I}if (cursor < size && (text[cursor] == '+' || text[cursor] == '-')) {{
{II}++cursor;
{I}}}

{I}std::size_t digits = 0;
{I}while (cursor < size && text[cursor] >= '0' && text[cursor] <= '9') {{
{II}++cursor;
{II}++digits;
{I}}}

{I}return digits > 0 && cursor == size;
}}"""
        ),
        Stripped(
            f"""\
bool MatchesXsDoubleNumeral(const std::string& text) {{
{I}std::size_t cursor = 0;
{I}const std::size_t size = text.size();

{I}if (cursor < size && (text[cursor] == '+' || text[cursor] == '-')) {{
{II}++cursor;
{I}}}

{I}std::size_t digits_before_the_point = 0;
{I}while (cursor < size && text[cursor] >= '0' && text[cursor] <= '9') {{
{II}++cursor;
{II}++digits_before_the_point;
{I}}}

{I}std::size_t digits_after_the_point = 0;
{I}if (cursor < size && text[cursor] == '.') {{
{II}++cursor;
{II}while (cursor < size && text[cursor] >= '0' && text[cursor] <= '9') {{
{III}++cursor;
{III}++digits_after_the_point;
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// A numeral needs a digit somewhere, but on either side of the point will
{I}// do: both "1." and ".5" are good xs:double numerals.
{I}if (digits_before_the_point == 0 && digits_after_the_point == 0) {{
{II}return false;
{I}}}

{I}if (cursor < size && (text[cursor] == 'e' || text[cursor] == 'E')) {{
{II}++cursor;

{II}if (cursor < size && (text[cursor] == '+' || text[cursor] == '-')) {{
{III}++cursor;
{II}}}

{II}std::size_t digits_in_the_exponent = 0;
{II}while (cursor < size && text[cursor] >= '0' && text[cursor] <= '9') {{
{III}++cursor;
{III}++digits_in_the_exponent;
{II}}}

{II}if (digits_in_the_exponent == 0) {{
{III}return false;
{II}}}
{I}}}

{I}return cursor == size;
}}"""
        ),
        Stripped(
            f"""\
bool MatchesXsBase64Binary(const std::string& text) {{
{I}if (text.size() % 4 != 0) {{
{II}return false;
{I}}}

{I}if (text.empty()) {{
{II}return true;
{I}}}

{I}std::size_t pads = 0;
{I}if (text[text.size() - 1] == '=') {{
{II}pads = 1;
{II}if (text[text.size() - 2] == '=') {{
{III}pads = 2;
{II}}}
{I}}}

{I}for (std::size_t i = 0; i < text.size() - pads; ++i) {{
{II}const char character = text[i];
{II}const bool in_alphabet(
{III}(character >= 'A' && character <= 'Z')
{IIII}|| (character >= 'a' && character <= 'z')
{IIII}|| (character >= '0' && character <= '9')
{IIII}|| character == '+'
{IIII}|| character == '/'
{II});
{II}if (!in_alphabet) {{
{III}return false;
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// Only these sixteen characters leave the two dropped bits at zero, and
{I}// only these four leave the four dropped bits at zero.
{I}if (pads == 1) {{
{II}return std::string("AEIMQUYcgkosw048").find(text[text.size() - 2])
{III}!= std::string::npos;
{I}}}

{I}if (pads == 2) {{
{II}return std::string("AQgw").find(text[text.size() - 3])
{III}!= std::string::npos;
{I}}}

{I}return true;
}}"""
        ),
        Stripped(
            f"""\
std::string RemoveWhitespace(const std::string& text) {{
{I}std::string result;
{I}result.reserve(text.size());

{I}for (const char character : text) {{
{II}if (
{III}character != ' '
{III}&& character != '\\t'
{III}&& character != '\\n'
{III}&& character != '\\r'
{II}) {{
{III}result += character;
{II}}}
{I}}}

{I}return result;
}}"""
        ),
    ]


def _generate_reader_declaration() -> List[Stripped]:
    """Generate the declaration of the readers."""
    return [
        Stripped("// region class Reader"),
        Stripped(
            """\
// NOTE (mristin):
// The full definition is given in the implementation file, and only forward-declared
// here since it is passed around exclusively through ``std::unique_ptr``.
struct OurData;"""
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
{I}/**
{I} * \\param is stream to read the XML from
{I} * \\param additional_attributes if set, unexpected XML attributes are ignored
{I} * instead of being reported as errors
{I} * \\param buffer_size size of the chunk to be read from \\p is and passed to
{I} * the underlying XML parser
{I} *
{I} * Every element is expected to reside either in \\ref kNamespace or in no
{I} * namespace at all -- the latter is how the XML-RPC subset, over which
{I} * a JSON-able value is de/serialized, is written. An element in any other
{I} * namespace is reported as an error. Which of the two an element is expected
{I} * to reside in depends on the grammar, so the node says which one it was, and
{I} * the caller decides.
{I} */
{I}Reader(
{II}std::istream& is,
{II}bool additional_attributes,
{II}size_t buffer_size
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
{II}bool additional_attributes,
{II}size_t buffer_size
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
        Stripped("// endregion class ReaderMergingText"),
    ]


def _generate_reader_implementation() -> List[Stripped]:
    """Generate the implementation of the readers."""
    return [
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
{II}buffer_size(a_buffer_size),
{II}parser(a_parser),
{II}node_buffer(a_node_buffer) {{
{II}// Intentionally empty.
{I}}}
}};  // struct OurData"""
        ),
        Stripped(
            f"""\
Reader::Reader(
{I}std::istream& is,
{I}bool additional_attributes,
{I}size_t buffer_size
) :
{I}additional_attributes_(additional_attributes),
{I}buffer_size_(buffer_size),
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

{I}// NOTE (mristin):
{I}// Expat spells a namespaced element as `namespace|local`, and an element
{I}// in no namespace as the bare local name. We accept the both: the elements
{I}// of the document reside in \\ref kNamespace, and the elements of
{I}// the XML-RPC subset in no namespace at all. Which of the two is expected
{I}// where is decided by the caller, as it depends on the grammar and not on
{I}// the document.
{I}size_t separator_i = name_str.find(kNamespaceSeparator);

{I}const bool in_namespace = separator_i != std::string::npos;

{I}if (separator_i == 0) {{
{II}std::string message = common::Concat(
{III}"The namespace is empty in the start element <",
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

{I}const std::string local_name(
{II}in_namespace
{III}? name_str.substr(separator_i + 1)
{III}: name_str
{I});

{I}if (
{II}in_namespace
{II}&& name_str.compare(0, separator_i, kNamespace) != 0
{I}) {{
{II}std::string message = common::Concat(
{III}"We expected the XML namespace ",
{III}kNamespace,
{III}", or no namespace at all, but we got the namespace ",
{III}name_str.substr(0, separator_i),
{III}" in the start element <",
{III}local_name,
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
{III}local_name,
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
{III}local_name,
{III}in_namespace
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

{I}const bool in_namespace = separator_i != std::string::npos;

{I}if (separator_i == 0) {{
{II}std::string message = common::Concat(
{III}"The namespace is empty in the stop element </",
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

{I}const std::string local_name(
{II}in_namespace
{III}? name_str.substr(separator_i + 1)
{III}: name_str
{I});

{I}if (
{II}in_namespace
{II}&& name_str.compare(0, separator_i, kNamespace) != 0
{I}) {{
{II}std::string message = common::Concat(
{III}"We expected the XML namespace ",
{III}kNamespace,
{III}", or no namespace at all, but we got the namespace ",
{III}name_str.substr(0, separator_i),
{III}" in the stop element </",
{III}local_name,
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
{III}local_name,
{III}in_namespace
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
ReaderMergingText::ReaderMergingText(
{II}std::istream& is,
{II}bool additional_attributes,
{II}size_t buffer_size
) :
{I}initialized_(false),
{I}reader_(is, additional_attributes, buffer_size),
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
    ]


# endregion

# region Serialization error


def _generate_serialization_error_declaration() -> List[Stripped]:
    """Generate the declaration of the generic writer error and its helper."""
    return [
        Stripped(
            f"""\
/**
 * Represent an error caught by \\ref SelfClosingWriter.
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
{I});
}};  // struct SerializationError"""
        ),
        Stripped("extern const std::wstring kTheOutputStreamIsInABadState;"),
        Stripped(
            f"""\
/**
 * Check that the output stream is not in a bad state. If so, create an error.
 */
common::optional<SerializationError> CheckOstreamState(
{I}const std::ostream& os
);"""
        ),
    ]


def _generate_serialization_error_implementation() -> List[Stripped]:
    """Generate the implementation of the generic writer error and its helper."""
    return [
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
            """\
const std::wstring kTheOutputStreamIsInABadState(
    L"The output stream is in a bad state."
);"""
        ),
        Stripped(
            f"""\
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
    ]


# endregion

# region Writing


def _generate_self_closing_writer_declaration(
    uses_json_types: bool,
) -> List[Stripped]:
    """Generate the declaration of the self-closing-element XML writer."""
    # NOTE (mristin):
    # Only the XML-RPC subset, over which a JSON-able value is de/serialized,
    # writes elements which reside in no namespace at all.
    in_no_namespace_declarations = (
        f"""

{I}/**
{I} * Queue a start element which resides in no namespace at all.
{I} *
{I} * \\p undeclare_namespace tells whether this is the outermost such element.
{I} * That one undeclares the default namespace of the enclosing document, and
{I} * the elements nested in it inherit that.
{I} */
{I}void StartElementInNoNamespace(
{II}std::string name,
{II}bool undeclare_namespace
{I});

{I}/**
{I} * Write a stop element which resides in no namespace at all.
{I} */
{I}void StopElementInNoNamespace(
{II}const std::string& name
{I});"""
        if uses_json_types
        else ""
    )

    return [
        Stripped("// region class SelfClosingWriter"),
        Stripped(
            f"""\
/**
 * \\brief Write XML elements, shortening an element with no content to
 * a self-closing element.
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
{I});{in_no_namespace_declarations}

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
{I} * Prefix of the pending start element; empty for an element which resides
{I} * in no namespace
{I} */
{I}const char* pending_prefix_;

{I}/**
{I} * Attributes of the pending start element; the undeclaration of the default
{I} * namespace for the outermost element which resides in no namespace, and
{I} * nothing otherwise
{I} */
{I}const char* pending_attributes_;

{I}/**
{I} * Write the stop element with the given \\p prefix, or shorten the pending
{I} * start element to a self-closing one.
{I} */
{I}void StopElementWithPrefix(
{II}const std::string& name,
{II}const char* prefix
{I});

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
        Stripped("// endregion class SelfClosingWriter"),
    ]


def _generate_self_closing_writer_implementation(
    uses_json_types: bool,
) -> List[Stripped]:
    """Generate the implementation of the self-closing-element XML writer."""
    # NOTE (mristin):
    # Only the XML-RPC subset, over which a JSON-able value is de/serialized,
    # writes elements which reside in no namespace at all.
    in_no_namespace_blocks = (
        [
            Stripped(
                f"""\
void SelfClosingWriter::StartElementInNoNamespace(
{I}std::string name,
{I}bool undeclare_namespace
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
{I}pending_prefix_ = "";
{I}pending_attributes_ = undeclare_namespace ? " xmlns=\\"\\"" : "";
}}"""
            ),
            Stripped(
                f"""\
void SelfClosingWriter::StopElementInNoNamespace(
{I}const std::string& name
) {{
{I}StopElementWithPrefix(name, "");
}}"""
            ),
        ]
        if uses_json_types
        else []
    )  # type: List[Stripped]

    return [
        Stripped("// region class SelfClosingWriter"),
        Stripped(
            f"""\
SelfClosingWriter::SelfClosingWriter(
{I}std::ostream& os,
{I}std::string prefix
) :
{I}os_(os),
{I}prefix_(std::move(prefix)),
{I}pending_prefix_(""),
{I}pending_attributes_("") {{
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
{I}pending_prefix_ = prefix_.c_str();
{I}pending_attributes_ = "";
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::StopElement(
{I}const std::string& name
) {{
{I}StopElementWithPrefix(name, prefix_.c_str());
}}"""
        ),
        Stripped(
            f"""\
void SelfClosingWriter::StopElementWithPrefix(
{I}const std::string& name,
{I}const char* prefix
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
{IIII}pending_prefix_,
{IIII}name,
{IIII}pending_attributes_,
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
{IIII}prefix,
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
{II}//
{II}// A stream left at its default precision is no good either: that is six
{II}// *significant* digits, so 1.2345678901234567 would go out as 1.23457, and
{II}// the value could never be read back. We have to write as many digits as it
{II}// takes for the text to read back as the very same double, and no more.
{II}//
{II}// std::to_chars would give us exactly that in one call, but it is C++17,
{II}// and the library has to compile as C++11. Seventeen significant digits
{II}// always suffice, and fewer usually do, so the candidates are tried in
{II}// turn and the first one which round-trips is kept. The stream strips
{II}// the trailing zeros of each, so a short value stays short.
{II}//
{II}// The classic locale is imposed on both streams: a global locale with
{II}// a decimal comma would otherwise write 1,2345, which no XML parser reads
{II}// back as a number.
{II}std::ostringstream oss;
{II}oss.imbue(std::locale::classic());

{II}for (int precision = 15; precision <= 17; ++precision) {{
{III}oss.str("");
{III}oss.clear();
{III}oss << std::setprecision(precision) << value;

{III}std::istringstream iss(oss.str());
{III}iss.imbue(std::locale::classic());
{III}double round_tripped = 0.0;
{III}iss >> round_tripped;

{III}// NOTE (mristin):
{III}// The failbit has to be consulted, and not only the value. On overflow
{III}// the stream stores the largest representable double and *fails*, so
{III}// comparing the value alone would accept a text which every correctly
{III}// rounding parser reads as an infinity: 15 significant digits of
{III}// the largest double give 1.79769313486232e+308, which lies above
{III}// the overflow threshold.
{III}if (!iss.fail() && round_tripped == value) {{
{IIII}break;
{III}}}
{II}}}

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
{III}pending_prefix_,
{III}*pending_start_wo_text_,
{III}pending_attributes_,
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
        *in_no_namespace_blocks,
        Stripped("// endregion class SelfClosingWriter"),
    ]


# endregion


def generate_header(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate header for the low-level XML tokenizer and writer."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.XML_COMMON_NAMESPACE}")

    uses_json_types = intermediate.uses_json_types(symbol_table)

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

#pragma warning(push, 0)
#include <expat.h>

#include <cstdint>
#include <deque>
#include <iosfwd>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(f"namespace {cpp_common.XML_COMMON_NAMESPACE} {{"),
        Stripped(
            """\
/**
 * \\brief The XML namespace in which all the elements of a document reside.
 *
 * The elements of the XML-RPC subset, over which a JSON-able value is
 * de/serialized, are the one exception: they reside in no namespace at all.
 */
extern const char* const kNamespace;"""
        ),
        Stripped("// region Node kind"),
        *_generate_node_kind_declaration(),
        Stripped("// endregion Node kind"),
        *_generate_node_classes(),
        *_generate_node_helpers_declaration(),
        Stripped("// region XSD lexical forms"),
        *_generate_xsd_lexical_helpers_declaration(),
        Stripped("// endregion XSD lexical forms"),
        Stripped("// region Reading"),
        *_generate_reader_declaration(),
        Stripped("// endregion Reading"),
        Stripped("// region Writing"),
        *_generate_serialization_error_declaration(),
        *_generate_self_closing_writer_declaration(uses_json_types=uses_json_types),
        Stripped("// endregion Writing"),
        Stripped(f"}}  // namespace {cpp_common.XML_COMMON_NAMESPACE}"),
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


def generate_implementation(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate implementation for the low-level XML tokenizer and writer."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.XML_COMMON_NAMESPACE}")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    namespace_literal = cpp_common.string_literal(symbol_table.meta_model.xml_namespace)

    uses_json_types = intermediate.uses_json_types(symbol_table)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "xml_common.hpp"

#include "{include_prefix_path}/stringification.hpp"

#pragma warning(push, 0)
#include <expat.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <istream>
#include <limits>
#include <locale>
#include <ostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <type_traits>
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
        Stripped(f"const char* const kNamespace = {namespace_literal};"),
        Stripped("// region Node kind"),
        *_generate_node_kind_implementation(),
        Stripped("// endregion Node kind"),
        *_generate_node_helpers_implementation(),
        Stripped("// region XSD lexical forms"),
        *_generate_xsd_lexical_helpers_implementation(),
        Stripped("// endregion XSD lexical forms"),
        *_generate_reader_implementation(),
        *_generate_serialization_error_implementation(),
        *_generate_self_closing_writer_implementation(uses_json_types=uses_json_types),
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
