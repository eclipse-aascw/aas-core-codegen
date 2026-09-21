"""Generate the XML primitives shared by the de/serialization modules."""

import io
import textwrap
from typing import List, Set

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    assert_never,
)
from aas_core_codegen.csharp import common as csharp_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


class NeededCombinators:
    """Capture which of the shared combinators a model actually needs."""

    def __init__(
        self,
        primitive_types: Set[intermediate.PrimitiveType],
        enumerations: bool,
        polymorphic: bool,
        lists: bool,
        v_elements: bool,
        json_shapes: bool,
    ) -> None:
        """Initialize with the given values."""
        self.primitive_types = primitive_types
        self.enumerations = enumerations
        self.polymorphic = polymorphic
        self.lists = lists
        self.v_elements = v_elements
        self.json_shapes = json_shapes

    @property
    def text(self) -> bool:
        """Check whether the skeleton reading a content as text is needed."""
        # NOTE (mristin):
        # Every primitive is read as a text, so any primitive at all calls for
        # the skeleton.
        return len(self.primitive_types) > 0


def needed_combinators(
    symbol_table: intermediate.SymbolTable,
) -> NeededCombinators:
    """
    Determine which shared combinators need to be generated.

    The reading and the writing are composed out of the very same shapes --
    a text, an enumeration literal, a list, a tuple, a self-describing
    element -- so one pass answers for both. Only the properties of
    the concrete classes matter, as they are the only thing de/serialized as
    a sequence of XML elements.

    The pass recurses into the items of a list and of a tuple: an item is
    de/serialized by the same combinators, only one nesting level deeper, and
    the combinator it needs may occur nowhere else in the model.

    This mirrors how the tuple helpers are already emitted only for
    the arities which actually occur (see
    :py:func:`aas_core_codegen.intermediate.tuple_arities`) -- without it,
    a model would pay for the combinators it never calls.

    This lives here, and not in the xmlization, because ``XmlCommon`` is gated
    on the very same answer: the XSD lexical helpers are only emitted for
    a model which has a float or a byte array somewhere in it.
    """
    primitive_types = set()  # type: Set[intermediate.PrimitiveType]
    enumerations = False
    polymorphic = False
    lists = False
    v_elements = False
    json_shapes = False

    def register(type_anno: intermediate.TypeAnnotationUnion, nested: bool) -> None:
        """
        Register what ``type_anno`` needs.

        ``nested`` tells whether the value is an item of a list or of
        a tuple. Everything but a class, an interface and a named union is
        then wrapped in a ``<v>`` element of its own, while those three
        de/serialize their own, self-describing element and hence need no
        dispatching combinator.
        """
        nonlocal enumerations, polymorphic, lists, v_elements, json_shapes

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            primitive_types.add(type_anno.a_type)
            v_elements = v_elements or nested

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type

            if isinstance(our_type, intermediate.Enumeration):
                enumerations = True
                primitive_types.add(intermediate.PrimitiveType.STR)
                v_elements = v_elements or nested

            elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                primitive_types.add(our_type.constrainee)
                v_elements = v_elements or nested

            elif isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                if not nested and (
                    isinstance(our_type, intermediate.AbstractClass)
                    or len(our_type.concrete_descendants) > 0
                ):
                    polymorphic = True

            elif isinstance(our_type, intermediate.NamedUnion):
                polymorphic = polymorphic or not nested

            else:
                assert_never(our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            lists = True
            v_elements = v_elements or nested
            register(type_anno.items, nested=True)

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            v_elements = v_elements or nested
            for item_type_anno in type_anno.items:
                register(item_type_anno, nested=True)

        elif isinstance(type_anno, intermediate.OptionalTypeAnnotation):
            register(type_anno.value, nested=nested)

        elif isinstance(
            type_anno,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            # NOTE (mristin):
            # A JSON-able value reads and writes its own content through
            # ``XmlRpc``, so it needs no combinator of its own -- only
            # the three shared content readers, which are emitted whenever
            # the model uses a JSON-able type at all.
            json_shapes = True
            v_elements = v_elements or nested

        else:
            assert_never(type_anno)

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            register(intermediate.beneath_optional(prop.type_annotation), nested=False)

    return NeededCombinators(
        primitive_types=primitive_types,
        enumerations=enumerations,
        polymorphic=polymorphic,
        lists=lists,
        v_elements=v_elements,
        json_shapes=json_shapes,
    )


def _generate_skip_whitespace_and_comments() -> Stripped:
    """Generate the function to skip whitespace text and XML comments."""
    return Stripped(
        f"""\
/// <summary>
/// Move <paramref name="reader" /> past the nodes which carry no
/// information -- the whitespace between the tags and the comments.
/// </summary>
internal static void SkipNoneWhitespaceAndComments(
{I}Xml.XmlReader reader)
{{
{I}while (
{II}!reader.EOF
{II}&& (
{III}reader.NodeType == Xml.XmlNodeType.None
{III}|| reader.NodeType == Xml.XmlNodeType.Whitespace
{III}|| reader.NodeType == Xml.XmlNodeType.Comment))
{I}{{
{II}reader.Read();
{I}}}
}}"""
    )


def _generate_extract_element_name() -> Stripped:
    """Generate the function to strip the prefix and check the namespace."""
    return Stripped(
        f"""\
/// <summary>
/// Check that the element resides in <paramref name="ns" /> and extract
/// its name.
/// </summary>
private static string TryElementNameInNamespace(
{I}Xml.XmlReader reader,
{I}string ns,
{I}out Reporting.Error? error
{I})
{{
{I}// Pre-condition
{I}if (reader.NodeType != Xml.XmlNodeType.Element
{II}&& reader.NodeType != Xml.XmlNodeType.EndElement)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Expected to be at a start or an end element " +
{III}$"in {{nameof(TryElementNameInNamespace)}}, " +
{III}$"but got: {{reader.NodeType}}");
{I}}}

{I}error = null;
{I}if (reader.NamespaceURI != ns)
{I}{{
{II}string expected = (
{III}(ns.Length == 0)
{IIII}? "no namespace"
{IIII}: $"the namespace {{ns}}");
{II}string got = (
{III}(reader.NamespaceURI.Length == 0)
{IIII}? "no namespace"
{IIII}: $"the namespace {{reader.NamespaceURI}}");

{II}error = new Reporting.Error(
{III}$"Expected an element within {{expected}}, " +
{III}$"but got an element within {{got}}");
{II}return "";
{I}}}

{I}return reader.LocalName;
}}"""
    )


def _generate_peek_element_name() -> Stripped:
    """
    Generate the shared helper looking ahead the name of the current element.

    Nothing is consumed, so the caller can still decide what to do with
    the element. This is what a de-serialization dispatching on
    a discriminator element needs, as it has no single name to expect --
    where there is one, :py:func:`_generate_read_start_element` says so in
    its error messages instead.
    """
    return Stripped(
        f"""\
/// <summary>
/// Look ahead the name of the element at the current position of
/// <paramref name="reader" />, without consuming anything.
/// </summary>
internal static string PeekElementName(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error
{I})
{{
{I}error = null;

{I}SkipNoneWhitespaceAndComments(reader);

{I}if (reader.EOF)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected an XML element, but reached the end-of-file");
{II}return "";
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.Element)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected an XML element, " +
{III}$"but got a node of type {{reader.NodeType}} " +
{III}$"with value {{reader.Value}}");
{II}return "";
{I}}}

{I}return TryElementNameInNamespace(
{II}reader, NS, out error);
}}"""
    )


def _generate_read_start_element() -> Stripped:
    """
    Generate the shared helper consuming the start tag of an expected element.

    Whether the element came self-closing is the one thing the caller can not
    find out afterwards -- the reader has already moved on -- so it is
    returned instead of being left to be looked up.
    """
    return Stripped(
        f"""\
/// <summary>
/// Consume the start tag of an element named
/// <paramref name="expectedName" /> and tell whether that element was
/// self-closing and hence has no content and no end tag.
/// </summary>
/// <remarks>
/// On failure the returned value is meaningless; the caller checks
/// <paramref name="error" /> first.
/// </remarks>
private static bool ReadStartElementInNamespace(
{I}Xml.XmlReader reader,
{I}string ns,
{I}string expectedName,
{I}out Reporting.Error? error
{I})
{{
{I}error = null;

{I}SkipNoneWhitespaceAndComments(reader);

{I}if (reader.EOF)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> element, " +
{III}"but reached the end-of-file");
{II}return false;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.Element)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> element, " +
{III}$"but got a node of type {{reader.NodeType}} " +
{III}$"with value {{reader.Value}}");
{II}return false;
{I}}}

{I}string observedName = TryElementNameInNamespace(
{II}reader, ns, out error);
{I}if (error != null)
{I}{{
{II}return false;
{I}}}

{I}if (observedName != expectedName)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> element, " +
{III}$"but got a <{{observedName}}> element");
{II}return false;
{I}}}

{I}bool isEmptyElement = reader.IsEmptyElement;

{I}// Consume the start tag and go to the content.
{I}reader.Read();

{I}return isEmptyElement;
}}"""
    )


def _generate_consume_end_element() -> Stripped:
    """
    Generate the shared helper consuming the end tag of an element.

    Reading a whole element, reading a property of a sequence and reading
    an XML-RPC value all conclude in exactly the same way.
    """
    return Stripped(
        f"""\
/// <summary>
/// Consume the end tag matching <paramref name="elementName" />, unless
/// <paramref name="isEmptyElement" /> tells that the element was
/// self-closing and thus has no end tag at all.
/// </summary>
private static void ConsumeEndElementInNamespace(
{I}Xml.XmlReader reader,
{I}string ns,
{I}string elementName,
{I}bool isEmptyElement,
{I}out Reporting.Error? error
{I})
{{
{I}error = null;

{I}if (isEmptyElement)
{I}{{
{II}return;
{I}}}

{I}SkipNoneWhitespaceAndComments(reader);

{I}if (reader.EOF)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a closing element </{{elementName}}>, " +
{III}"but reached the end-of-file");
{II}return;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.EndElement)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a closing element </{{elementName}}>, " +
{III}$"but got a node of type {{reader.NodeType}} " +
{III}$"with value {{reader.Value}}");
{II}return;
{I}}}

{I}string endElementName = TryElementNameInNamespace(
{II}reader, ns, out error);
{I}if (error != null)
{I}{{
{II}return;
{I}}}

{I}if (endElementName != elementName)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a closing element </{{elementName}}>, " +
{III}$"but got a closing element </{{endElementName}}>");
{II}return;
{I}}}

{I}// Consume the end tag.
{I}reader.Read();
}}"""
    )


def _generate_namespace_constant(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the constant of the XML namespace of the whole document."""
    xml_namespace_literal = csharp_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    return Stripped(
        f"""\
/// <summary>
/// XML namespace in which all the elements of a document reside
/// </summary>
/// <remarks>
/// The elements of the XML-RPC subset, over which a JSON-able value is
/// de/serialized, are the one exception: they reside in no namespace at all.
/// </remarks>
internal static readonly string NS = (
{I}{xml_namespace_literal});"""
    )


def _generate_element_name_and_framing_wrappers(
    uses_json_types: bool,
) -> List[Stripped]:
    """
    Generate the primitives which bind the namespace of an element.

    The namespace is no argument of the de-serialization. An element of
    the document resides in :py:func:`_generate_namespace_constant`'s ``NS``,
    and an element of the XML-RPC subset in no namespace at all, so each
    primitive comes in the one or the two flavors which are actually called.
    """
    result = [
        Stripped(
            f"""\
/// <summary>
/// Check that the element resides in <see cref="NS" /> and extract its name.
/// </summary>
internal static string TryElementName(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error
{I})
{{
{I}return TryElementNameInNamespace(reader, NS, out error);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Consume the start tag of an element named
/// <paramref name="expectedName" /> in <see cref="NS" />, and tell whether
/// that element was self-closing.
/// </summary>
internal static bool ReadStartElement(
{I}Xml.XmlReader reader,
{I}string expectedName,
{I}out Reporting.Error? error
{I})
{{
{I}return ReadStartElementInNamespace(
{II}reader, NS, expectedName, out error);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Consume the end tag matching <paramref name="elementName" /> in
/// <see cref="NS" />, unless the element was self-closing.
/// </summary>
internal static void ConsumeEndElement(
{I}Xml.XmlReader reader,
{I}string elementName,
{I}bool isEmptyElement,
{I}out Reporting.Error? error
{I})
{{
{I}ConsumeEndElementInNamespace(
{II}reader, NS, elementName, isEmptyElement, out error);
}}"""
        ),
    ]  # type: List[Stripped]

    if not uses_json_types:
        return result

    result.extend(
        [
            Stripped(
                f"""\
/// <summary>
/// Check that the element resides in no namespace at all, and extract its
/// name.
/// </summary>
internal static string TryElementNameInNoNamespace(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error
{I})
{{
{I}return TryElementNameInNamespace(reader, "", out error);
}}"""
            ),
            Stripped(
                f"""\
/// <summary>
/// Consume the start tag of an element named
/// <paramref name="expectedName" /> in no namespace at all, and tell whether
/// that element was self-closing.
/// </summary>
internal static bool ReadStartElementInNoNamespace(
{I}Xml.XmlReader reader,
{I}string expectedName,
{I}out Reporting.Error? error
{I})
{{
{I}return ReadStartElementInNamespace(
{II}reader, "", expectedName, out error);
}}"""
            ),
            Stripped(
                f"""\
/// <summary>
/// Consume the end tag matching <paramref name="elementName" /> in no
/// namespace at all, unless the element was self-closing.
/// </summary>
internal static void ConsumeEndElementInNoNamespace(
{I}Xml.XmlReader reader,
{I}string elementName,
{I}bool isEmptyElement,
{I}out Reporting.Error? error
{I})
{{
{I}ConsumeEndElementInNamespace(
{II}reader, "", elementName, isEmptyElement, out error);
}}"""
            ),
        ]
    )

    return result


def _generate_whitespace_run_regex() -> Stripped:
    """Generate the regular expression matching a run of XML whitespace."""
    return Stripped(
        f"""\
/// <summary>
/// Match a run of the four characters which XML calls whitespace.
/// </summary>
internal static readonly RegularExpressions.Regex WhitespaceRunRegex = (
{I}new RegularExpressions.Regex(
{II}@"[ \\t\\n\\r]+",
{II}RegularExpressions.RegexOptions.Compiled));"""
    )


def _generate_matches_xs_base_64_binary() -> Stripped:
    """Generate the matcher of the ``xs:base64Binary`` lexical space."""
    return Stripped(
        f"""\
/// <summary>
/// Tell whether <paramref name="text" /> is a lexical form of
/// <c>xs:base64Binary</c>.
/// </summary>
/// <remarks>
/// The whitespace is expected to be gone already. What is left has to match
/// <c>(B64 B64 B64 B64)* ((B64 B64 B64 B64) | (B64 B64 B16 '=')
/// | (B64 B04 '=='))?</c> -- a length which is a multiple of four,
/// the alphabet and nothing else, an equals sign only at the very end, and,
/// easily missed, a constrained character <i>before</i> the padding, as
/// the bits which the padding drops have to be zero.
///
/// The decoders do not agree on any of this, so every target does the same
/// check of its own and refuses the same texts.
///
/// See: https://www.w3.org/TR/xmlschema-2/#base64Binary
/// </remarks>
internal static bool MatchesXsBase64Binary(string text)
{{
{I}if (text.Length % 4 != 0)
{I}{{
{II}return false;
{I}}}

{I}if (text.Length == 0)
{I}{{
{II}return true;
{I}}}

{I}int pads = 0;
{I}if (text[text.Length - 1] == '=')
{I}{{
{II}pads = 1;
{II}if (text[text.Length - 2] == '=')
{II}{{
{III}pads = 2;
{II}}}
{I}}}

{I}for (int i = 0; i < text.Length - pads; i++)
{I}{{
{II}char character = text[i];
{II}bool inAlphabet =
{III}(character >= 'A' && character <= 'Z')
{IIII}|| (character >= 'a' && character <= 'z')
{IIII}|| (character >= '0' && character <= '9')
{IIII}|| character == '+'
{IIII}|| character == '/';
{II}if (!inAlphabet)
{II}{{
{III}return false;
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// Only these sixteen characters leave the two dropped bits at zero, and
{I}// only these four leave the four dropped bits at zero.
{I}if (pads == 1)
{I}{{
{II}return "AEIMQUYcgkosw048".IndexOf(text[text.Length - 2]) >= 0;
{I}}}

{I}if (pads == 2)
{I}{{
{II}return "AQgw".IndexOf(text[text.Length - 3]) >= 0;
{I}}}

{I}return true;
}}"""
    )


def _generate_parse_xs_double() -> Stripped:
    """Generate the parser of the ``xs:double`` lexical space."""
    return Stripped(
        f"""\
/// <summary>
/// Match the lexical space of <c>xs:double</c>, save for the three named
/// literals, which <see cref="ParseXsDouble" /> takes care of.
/// </summary>
/// <remarks>
/// The pattern ends in <c>\\z</c>, and not in <c>$</c>: <c>$</c> matches not
/// only at the end of the text but also just before a trailing newline, so
/// <c>"1.0\\n"</c> would pass.
///
/// See: https://www.w3.org/TR/xmlschema-2/#double
/// </remarks>
private static readonly RegularExpressions.Regex XsDoubleRegex = (
{I}new RegularExpressions.Regex(
{II}@"^(\\+|-)?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([Ee](\\+|-)?[0-9]+)?\\z",
{II}RegularExpressions.RegexOptions.Compiled));

/// <summary>
/// Parse <paramref name="text" /> as a <c>xs:double</c>.
/// </summary>
/// <remarks>
/// <c>XmlReader.ReadContentAsDouble</c> can not be used directly. It reads
/// the three named literals correctly, but it also takes <c>Infinity</c>,
/// <c>-Infinity</c>, <c>nan</c> and <c>NAN</c>, none of which
/// <c>xs:double</c> admits -- it spells them <c>INF</c>, <c>-INF</c> and
/// <c>NaN</c>, and it is case-sensitive.
/// </remarks>
/// <exception cref="System.FormatException">
/// Thrown when <paramref name="text" /> is not a <c>xs:double</c>
/// </exception>
internal static double ParseXsDouble(string rawText)
{{
{I}// NOTE (mristin):
{I}// Every atomic XSD type except a string fixes whiteSpace to collapse,
{I}// and a schema author can not change it, so the text is normalized
{I}// before it is matched: a tab, a line feed and a carriage return each
{I}// become a space, a run of spaces becomes one space, and the leading
{I}// and trailing spaces go. Mind that this strips only the whitespace
{I}// *around* the value: a space within it survives as a single space, so
{I}// "2  3" becomes "2 3", which is still no number.
{I}//
{I}// The other readers of the xmlization need no such thing -- XmlConvert,
{I}// which XmlReader.ReadContentAs* goes through, already collapses.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace
{I}string text = WhitespaceRunRegex.Replace(rawText, " ").Trim(' ');

{I}switch (text)
{I}{{
{II}// NOTE (mristin):
{II}// "+INF" is read although it is written as "INF": XSD 1.1 admits it,
{II}// its production being (\\+|-)?INF, and being liberal in what we
{II}// accept costs nothing here.
{II}case "INF":
{II}case "+INF":
{III}return System.Double.PositiveInfinity;
{II}case "-INF":
{III}return System.Double.NegativeInfinity;
{II}case "NaN":
{III}return System.Double.NaN;
{II}default:
{III}break;
{I}}}

{I}if (!XsDoubleRegex.IsMatch(text))
{I}{{
{II}throw new System.FormatException(
{III}$"Expected a value as xs:double, but got: {{text}}");
{I}}}

{I}return System.Double.Parse(
{II}text,
{II}Globalization.NumberStyles.Float,
{II}Globalization.CultureInfo.InvariantCulture);
}}"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    namespace: csharp_common.NamespaceIdentifier,
) -> str:
    """
    Generate the XML primitives shared by the de/serialization modules.

    The XML-RPC de/serialization of the JSON-able values and the xmlization of
    the meta-model classes read the very same documents, one embedded in
    the other, and hence need the very same low-level primitives: the skipping
    of what carries no information, the check of the XML namespace, and
    the consuming of a start and of an end tag. They are given here, once, so
    that the two modules agree by construction instead of by inspection.

    The class is ``internal``: nothing of this is meant for the user of
    the library, who sees only ``Xmlization`` and ``XmlRpc``.

    The XML namespace is a constant here, ``NS``, and no argument of these
    primitives: ``Xmlization`` re-exports it, and ``XmlRpc`` needs none, as
    the XML-RPC elements reside in no namespace at all.

    The ``namespace`` defines the base C# namespace of the generated code.
    """
    needed = needed_combinators(symbol_table)

    # NOTE (mristin):
    # ``XmlRpc`` reads the text of a ``<double>`` as a xs:double as well, so
    # the parser is needed as soon as the model uses a JSON-able type, even
    # if no property of it is a float.
    needs_xs_double = (
        intermediate.PrimitiveType.FLOAT in needed.primitive_types
        or intermediate.uses_json_types(symbol_table)
    )

    needs_xs_base_64_binary = (
        intermediate.PrimitiveType.BYTEARRAY in needed.primitive_types
    )

    blocks = [
        _generate_namespace_constant(symbol_table),
        _generate_skip_whitespace_and_comments(),
        _generate_extract_element_name(),
        _generate_read_start_element(),
        _generate_consume_end_element(),
        *_generate_element_name_and_framing_wrappers(
            uses_json_types=intermediate.uses_json_types(symbol_table)
        ),
        _generate_peek_element_name(),
    ]  # type: List[Stripped]

    # NOTE (mristin):
    # The xs:double parser normalizes the whitespace itself, and the base-64
    # reader of the xmlization strips it before it calls the matcher, so
    # the regular expression is emitted for either of them.
    if needs_xs_double or needs_xs_base_64_binary:
        blocks.append(_generate_whitespace_run_regex())

    if needs_xs_base_64_binary:
        blocks.append(_generate_matches_xs_base_64_binary())

    if needs_xs_double:
        blocks.append(_generate_parse_xs_double())

    writer = io.StringIO()

    writer.write(
        f"""\
namespace {namespace}
{{
{I}/// <summary>
{I}/// Provide the XML primitives shared by <see cref="Xmlization" /> and
{I}/// the de/serialization of the JSON-able values.
{I}/// </summary>
{I}internal static class XmlCommon
{I}{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, II))

    writer.write(f"\n{I}}}  // internal static class XmlCommon")

    # NOTE (mristin):
    # The two error types sit beside the class, and not within it: an error
    # raised deep inside ``XmlRpc`` is caught and converted in ``Xmlization``,
    # so both modules have to name them.
    writer.write(
        f"""\


{I}/// <summary>
{I}/// Signal a failure of the serialization, carrying the path to the culprit.
{I}/// </summary>
{I}/// <remarks>
{I}/// The path is built as the stack unwinds -- every container prepends the one
{I}/// segment it knows, the property its name and the list the index of the item
{I}/// -- which is why this can not be a <see cref="SerializationException" />
{I}/// already: that one renders its message in its constructor, so its path has
{I}/// to be complete by then. <see cref="Xmlization.Serialize.To" /> renders and
{I}/// converts.
{I}/// </remarks>
{I}internal class SerializationFailure : System.Exception
{I}{{
{II}public readonly Reporting.Error Error;
{II}public SerializationFailure(Reporting.Error error)
{III}: base(error.Cause)
{II}{{
{III}Error = error;
{II}}}
{I}}}

{I}/// <summary>
{I}/// Represent a critical error during the serialization to XML.
{I}/// </summary>
{I}public class SerializationException : System.Exception
{I}{{
{II}public readonly string Path;
{II}public readonly string Cause;
{II}public SerializationException(string path, string cause)
{III}: base($"{{cause}} at: {{(path == "" ? "the instance itself" : path)}}")
{II}{{
{III}Path = path;
{III}Cause = cause;
{II}}}
{I}}}"""
    )

    writer.write(f"\n}}  // namespace {namespace}")

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    if needs_xs_double:
        using_directives.append(Stripped("using Globalization = System.Globalization;"))

    if needs_xs_double or needs_xs_base_64_binary:
        using_directives.append(
            Stripped("using RegularExpressions = System.Text.RegularExpressions;")
        )

    using_directives.append(Stripped("using Xml = System.Xml;"))

    file_blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(writer.getvalue()),
        csharp_common.WARNING,
    ]

    file_writer = io.StringIO()
    for i, file_block in enumerate(file_blocks):
        if i > 0:
            file_writer.write("\n\n")

        assert not file_block.startswith("\n")
        assert not file_block.endswith("\n")
        file_writer.write(file_block)

    file_writer.write("\n")

    return file_writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
