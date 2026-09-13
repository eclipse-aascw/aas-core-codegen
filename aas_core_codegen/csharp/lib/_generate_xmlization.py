"""Generate code for XML de/serialization."""

import collections
import io
import textwrap
from typing import Tuple, Optional, List, Mapping, MutableMapping, Set, Final

from icontract import ensure, require

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.csharp import (
    common as csharp_common,
    naming as csharp_naming,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


def _generate_skip_whitespace_and_comments() -> Stripped:
    """Generate the function to skip whitespace text and XML comments."""
    return Stripped(
        f"""\
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


def _generate_read_whole_content_as_base_64() -> Stripped:
    """Generate the function to read the whole of element's content as bytes."""
    return Stripped(
        f"""\
/// <summary>
/// Read the whole content of an element into memory.
/// </summary>
private static byte[] ReadWholeContentAsBase64(
{I}Xml.XmlReader reader)
{{
{I}// The capacity of 1024 bytes is an arbitrary,
{I}// but plausible default capacity.
{I}byte[] buffer = new byte[1024];
{I}using System.IO.MemoryStream stream = (
{II}new System.IO.MemoryStream(1024));
{I}int readBytes;
{I}while ((readBytes = reader.ReadContentAsBase64(buffer, 0, 1024)) > 0)
{I}{{
{II}stream.Write(buffer, 0, readBytes);
{I}}}
{I}return stream.ToArray();
}}"""
    )


def _generate_extract_element_name() -> Stripped:
    """Generate the function to strip the prefix and check the namespace."""
    return Stripped(
        f"""\
/// <summary>
/// Check the namespace and extract the element's name.
/// </summary>
private static string TryElementName(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error
{I})
{{
{I}// Pre-condition
{I}if (reader.NodeType != Xml.XmlNodeType.Element
{II}&& reader.NodeType != Xml.XmlNodeType.EndElement)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Expected to be at a start or an end element " +
{III}$"in {{nameof(TryElementName)}}, " +
{III}$"but got: {{reader.NodeType}}");
{I}}}

{I}error = null;
{I}if (reader.NamespaceURI != NS)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected an element within a namespace {{NS}}, " +
{III}$"but got: {{reader.NamespaceURI}}");
{III}return "";
{I}}}

{I}return reader.LocalName;
}}"""
    )


def _generate_element_reader_delegates() -> Stripped:
    """
    Generate the two delegates through which every value is read.

    An :py:class:`ElementReader` reads a whole element, tags included;
    a :py:class:`ContentReader` reads what is between the tags. ``AtElement``
    converts the latter into the former and is the only thing that has to
    know an element's name.

    Both return a plain ``T``. A nullable return would have to be spelled
    ``T?``, which is a value type for a ``struct`` but a nullable reference
    for a ``class``, so it would have to be split in two (and, before C# 9,
    can not be written for an unconstrained ``T`` at all).

    ``ElementReader`` is declared covariant, so that a field holding
    the reader of a concrete class can be passed where the reader of its
    interface is expected -- with a method group that came for free, but
    a field is a value and needs the variance spelled out.
    """
    return Stripped(
        f"""\
/// <summary>
/// Read a single element, tags included, positioned at its start tag.
/// </summary>
/// <remarks>
/// Return the value; on failure it is meaningless and
/// <paramref name="error" /> says why. A plain <c>T</c> rather than
/// a <c>T?</c>, so that one unconstrained delegate serves both the value
/// and the reference types.
///
/// <typeparamref name="T" /> is covariant, so that the reader of
/// a concrete class can be used as the reader of an item of a list of
/// its interface. It is <c>internal</c> only because the readers of
/// the classes are, and a field may not be more accessible than its type.
/// </remarks>
/// <typeparam name="T">Type of the parsed value</typeparam>
internal delegate T ElementReader<out T>(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error);

/// <summary>
/// Read the content of an element, positioned after its start tag.
/// </summary>
/// <remarks>
/// Every value is read through this one shape, so that the reading can be
/// composed: an <c>As*</c> combinator turns a conversion, a literal parser,
/// an element reader or a list of them into one of these, and a class's own
/// <c>...FromSequence</c> already is one.
/// </remarks>
/// <typeparam name="T">Type of the value</typeparam>
private delegate T ContentReader<T>(
{I}Xml.XmlReader reader,
{I}bool isEmpty,
{I}out Reporting.Error? error);"""
    )


def _generate_read_list_helper() -> Stripped:
    """Generate the single generic helper to read a sequence of list items."""
    return Stripped(
        f"""\
/// <summary>
/// Read a sequence of list items with <paramref name="readItem" />,
/// stopping (without consuming) at the first non-element node.
/// </summary>
/// <remarks>
/// This is shared by everything of a list type, whatever its items are and
/// however deeply it is nested, since the items are read through
/// an <see cref="ElementReader{{T}}" /> like any other element.
/// </remarks>
/// <typeparam name="T">Type of a single list item</typeparam>
private static List<T> ReadList<T>(
{I}Xml.XmlReader reader,
{I}ElementReader<T> readItem,
{I}out Reporting.Error? error
{I})
{{
{I}error = null;
{I}var result = new List<T>();

{I}SkipNoneWhitespaceAndComments(reader);

{I}int index = 0;
{I}while (reader.NodeType == Xml.XmlNodeType.Element)
{I}{{
{II}T item = readItem(reader, out error);
{II}if (error != null)
{II}{{
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(
{IIIII}index));
{III}return result;
{II}}}

{II}result.Add(item);

{II}index++;
{II}SkipNoneWhitespaceAndComments(reader);
{I}}}

{I}return result;
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_as_tuple_combinator(arity: int) -> Stripped:
    """
    Generate the combinator reading a content as a tuple of the given ``arity``.

    Each positional item is read by its own ``readItemI`` callback, which is
    expected to have already consumed its own start and end tags (if any).
    We can not reuse :py:func:`_generate_read_list_helper` here, since
    a tuple is heterogeneous -- but the very same, unconstrained
    :py:class:`ElementReader` serves both.

    The content is not necessarily a property's. The result is a plain
    ``ContentReader``, so wrapping it in ``AtElement`` makes a tuple readable
    as an item of a list or of another tuple, arbitrarily deep.
    """
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(type_params)

    if arity == 1:
        tuple_type = f"System.ValueTuple<{type_params[0]}>"
    else:
        tuple_type = f"({type_params_joined})"

    params_joined = ",\n".join(f"ElementReader<T{i}> readItem{i}" for i in range(arity))

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_block = Stripped(
            f"""\
T{i} item{i} = readItem{i}(reader, out error);
if (error != null)
{{
{I}error.PrependSegment(
{II}new Reporting.IndexSegment(
{III}{i}));
{I}return default!;
}}"""
        )
        if i < arity - 1:
            item_block = Stripped(
                f"{item_block}\nSkipNoneWhitespaceAndComments(reader);"
            )
        item_blocks.append(item_block)

    item_blocks_joined = "\n\n".join(item_blocks)

    item_vars_joined = ",\n".join(f"item{i}" for i in range(arity))

    if arity == 1:
        return_expr = "System.ValueTuple.Create(item0)"
    else:
        return_expr = f"""\
(
{I}{indent_but_first_line(item_vars_joined, I)}
)"""

    return Stripped(
        f"""\
/// <summary>
/// Read a content as a tuple of {arity} item(s).
/// </summary>
/// <remarks>
/// This is shared by everything of a tuple type of arity {arity} -- be it
/// a property, or a value nested in a list or in another tuple.
/// </remarks>
private static ContentReader<{tuple_type}> AsTuple{arity}<{type_params_joined}>(
{I}{indent_but_first_line(params_joined, I)}
{I})
{{
{I}return (
{II}Xml.XmlReader reader,
{II}bool isEmptyProperty,
{II}out Reporting.Error? error
{I}) =>
{I}{{
{II}error = null;

{II}if (isEmptyProperty)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML content representing a tuple of {arity} item(s), " +
{IIII}"but the element was self-closing");
{III}return default!;
{II}}}

{II}SkipNoneWhitespaceAndComments(reader);

{II}{indent_but_first_line(item_blocks_joined, II)}

{II}return {indent_but_first_line(return_expr, II)};
{I}}};
}}"""
    )


_CONTENT_READER_BY_PRIMITIVE = {
    intermediate.PrimitiveType.BOOL: (
        "ReadContentAsBoolean",
        "bool",
        "reader.ReadContentAsBoolean()",
    ),
    intermediate.PrimitiveType.INT: (
        "ReadContentAsLong",
        "long",
        "reader.ReadContentAsLong()",
    ),
    intermediate.PrimitiveType.FLOAT: (
        "ReadContentAsDouble",
        "double",
        "reader.ReadContentAsDouble()",
    ),
    intermediate.PrimitiveType.STR: (
        "ReadContentAsString",
        "string",
        "reader.ReadContentAsString()",
    ),
    intermediate.PrimitiveType.BYTEARRAY: (
        "ReadContentAsBytes",
        "byte[]",
        f"ReadWholeContentAsBase64(\n{II}reader)",
    ),
}

assert all(
    literal in _CONTENT_READER_BY_PRIMITIVE for literal in intermediate.PrimitiveType
)

# NOTE (mristin):
# A self-closing element stands for an empty string and for empty bytes,
# whereas the other primitives have no content to convert at all and so it is
# an error. Where a primitive has such an empty value, it is spelled out here
# and the reading goes through the ``...OrEmpty`` variant of the skeleton.
_EMPTY_VALUE_BY_PRIMITIVE = {
    intermediate.PrimitiveType.STR: '""',
    intermediate.PrimitiveType.BYTEARRAY: "new byte[0]",
}


class _NeededContentReaders:
    """Capture which of the shared content readers a model actually needs."""

    def __init__(
        self,
        primitive_types: Set[intermediate.PrimitiveType],
        enumerations: bool,
        polymorphic: bool,
        lists: bool,
        v_elements: bool,
    ) -> None:
        """Initialize with the given values."""
        self.primitive_types = primitive_types
        self.enumerations = enumerations
        self.polymorphic = polymorphic
        self.lists = lists
        self.v_elements = v_elements

    @property
    def text(self) -> bool:
        """Check whether the skeleton reading a content as text is needed."""
        return any(
            a_type in self.primitive_types for a_type in _CONTENT_READER_BY_PRIMITIVE
        )


def _needed_content_readers(
    symbol_table: intermediate.SymbolTable,
) -> _NeededContentReaders:
    """
    Determine which shared content readers need to be generated.

    Only the properties of the concrete classes matter, as they are the only
    ones de-serialized from a sequence of XML elements. A list or a tuple
    contributes through its *items* as well, as they are read by the very
    same combinators, only one nesting level deeper.

    This mirrors how the tuple helpers are already emitted only for
    the arities which actually occur (see
    :py:func:`aas_core_codegen.intermediate.tuple_arities`) -- without it,
    a model would pay for the readers it never calls.
    """
    primitive_types = set()  # type: Set[intermediate.PrimitiveType]
    enumerations = False
    polymorphic = False
    lists = False
    v_elements = False

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
                primitive_types.add(type_anno.a_type)

            elif isinstance(type_anno, intermediate.OurTypeAnnotation):
                our_type = type_anno.our_type

                if isinstance(our_type, intermediate.Enumeration):
                    enumerations = True
                    primitive_types.add(intermediate.PrimitiveType.STR)

                elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                    primitive_types.add(our_type.constrainee)

                elif isinstance(
                    our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
                ):
                    if (
                        isinstance(our_type, intermediate.AbstractClass)
                        or len(our_type.concrete_descendants) > 0
                    ):
                        polymorphic = True

                elif isinstance(our_type, intermediate.NamedUnion):
                    polymorphic = True

                else:
                    assert_never(our_type)

            elif isinstance(
                type_anno,
                (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
            ):
                # NOTE (mristin):
                # A primitive or an enumeration item of a list or of a tuple
                # is wrapped in a ``<v>`` element of its own.
                if isinstance(type_anno, intermediate.ListTypeAnnotation):
                    lists = True
                    item_type_annotations = [
                        type_anno.items
                    ]  # type: List[intermediate.TypeAnnotationUnion]
                else:
                    item_type_annotations = list(type_anno.items)

                for item_type_anno in item_type_annotations:
                    item_primitive_type = intermediate.try_primitive_type(
                        item_type_anno
                    )

                    if item_primitive_type is not None:
                        primitive_types.add(item_primitive_type)
                        v_elements = True

                    elif isinstance(
                        item_type_anno, intermediate.OurTypeAnnotation
                    ) and isinstance(item_type_anno.our_type, intermediate.Enumeration):
                        primitive_types.add(intermediate.PrimitiveType.STR)
                        enumerations = True
                        v_elements = True

            else:
                pass

    return _NeededContentReaders(
        primitive_types=primitive_types,
        enumerations=enumerations,
        polymorphic=polymorphic,
        lists=lists,
        v_elements=v_elements,
    )


def _generate_as_text_combinators(
    needed: _NeededContentReaders,
) -> List[Stripped]:
    """
    Generate the shared skeletons for reading a content as text.

    The self-closing-element check, the end-of-file check and the ``try``/
    ``catch`` around the conversion are the same for every type, so they are
    generated here exactly once -- the type-specific part is passed in as
    a :py:class:`ContentConverter`. The content is that of *any* element --
    a property's, or a ``<v>`` element's of a list item or of a tuple item --
    so nothing here may speak of a property.

    There are two skeletons rather than one because a self-closing element is
    an error for most of the types, but the empty value for a couple of them
    (an empty string, no bytes).

    The type name in the messages comes from ``typeof(T).Name`` instead of
    being baked in by the generator, so that a call site costs no more than
    it did when there was one hand-rolled reader per type.
    """
    result = []  # type: List[Stripped]

    if not needed.text:
        return result

    result.append(
        Stripped(
            """\
/// <summary>
/// Convert the content at the current position of <paramref name="reader" />.
/// </summary>
/// <typeparam name="T">Type to convert the content to</typeparam>
private delegate T ContentConverter<T>(Xml.XmlReader reader);"""
        )
    )

    result.append(
        Stripped(
            f"""\
/// <summary>
/// Read the content between a start and an end tag and convert it
/// with <paramref name="readContent" />.
/// </summary>
/// <remarks>
/// This is the one skeleton for reading any content whatsoever -- of
/// a property, or of a <c>&lt;v&gt;</c> element of a list or a tuple item
/// (see <see cref="AtElement{{T}}" />). Only the conversion differs, so
/// only the conversion is passed in.
///
/// On failure the returned value is meaningless; the caller checks
/// <paramref name="error" /> and bails out before ever reading it. That is
/// what lets this return a plain <c>T</c> -- a <c>T?</c> would have to be
/// split into a variant for the value and one for the reference types.
/// </remarks>
/// <typeparam name="T">Type of the value</typeparam>
private static ContentReader<T> AsText<T>(
{I}ContentConverter<T> readContent
{I})
{{
{I}return (
{II}Xml.XmlReader reader,
{II}bool isEmpty,
{II}out Reporting.Error? error
{I}) =>
{I}{{
{II}error = null;

{II}if (isEmpty)
{II}{{
{III}error = new Reporting.Error(
{IIII}$"Expected an XML content representing {{typeof(T).Name}}, " +
{IIII}"but the element was self-closing");
{III}return default!;
{II}}}

{II}if (reader.EOF)
{II}{{
{III}error = new Reporting.Error(
{IIII}$"Expected an XML content representing {{typeof(T).Name}}, " +
{IIII}"but reached the end-of-file");
{III}return default!;
{II}}}

{II}try
{II}{{
{III}return readContent(reader);
{II}}}
{II}catch (System.Exception exception)
{IIII}when (exception is System.FormatException
{IIIII}|| exception is System.Xml.XmlException)
{II}{{
{III}error = new Reporting.Error(
{IIII}$"The content could not be de-serialized as {{typeof(T).Name}}: " +
{IIII}exception.Message);
{III}return default!;
{II}}}
{I}}};
}}"""
        )
    )

    result.append(
        Stripped(
            f"""\
/// <summary>
/// Read the content between a start and an end tag, or return
/// <paramref name="whenEmpty" /> if the element was self-closing.
/// </summary>
/// <typeparam name="T">Type of the value</typeparam>
[CodeAnalysis.SuppressMessage("ReSharper", "UnusedMember.Local")]
private static ContentReader<T> AsText<T>(
{I}ContentConverter<T> readContent,
{I}T whenEmpty
{I})
{{
{I}ContentReader<T> readText = AsText<T>(readContent);

{I}return (
{II}Xml.XmlReader reader,
{II}bool isEmpty,
{II}out Reporting.Error? error
{I}) =>
{I}{{
{II}if (isEmpty)
{II}{{
{III}error = null;
{III}return whenEmpty;
{II}}}

{II}return readText(reader, false, out error);
{I}}};
}}"""
        )
    )

    return result


def _generate_consume_end_element() -> Stripped:
    """
    Generate the shared helper consuming the end tag of an element.

    Reading a whole element and reading a property of a sequence conclude
    in exactly the same way, so this is shared by ``AtElement`` and by
    the property loop of every ``...FromSequence``.
    """
    return Stripped(
        f"""\
/// <summary>
/// Consume the end tag matching <paramref name="elementName" />, unless
/// <paramref name="isEmptyElement" /> tells that the element was
/// self-closing and thus has no end tag at all.
/// </summary>
private static void ConsumeEndElement(
{I}Xml.XmlReader reader,
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

{I}string endElementName = TryElementName(
{II}reader, out error);
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


def _generate_try_next_property() -> Stripped:
    """
    Generate the shared helper reading the start tag of the next property.

    The framing of the property loop -- where the sequence ends, what is not
    an element at all, what the property is called and whether it is
    self-closing -- says nothing about the class being read, so it is
    generated once here instead of once per class.

    Only the ``switch`` over the property names is left inline, because its
    branches assign the local variables which the constructor is called with
    afterwards.
    """
    return Stripped(
        f"""\
/// <summary>
/// Read the start tag of the next property of a sequence and return whether
/// there was one.
/// </summary>
/// <remarks>
/// A sequence ends at the end tag of the enclosing element or at the end of
/// the file, which is not a failure -- when this returns <c>false</c>,
/// <paramref name="error" /> tells the two apart.
///
/// The start tag is consumed, so the reader is left at the content of
/// the property.
/// </remarks>
private static bool TryNextProperty(
{I}Xml.XmlReader reader,
{I}out string elementName,
{I}out bool isEmptyProperty,
{I}out Reporting.Error? error
{I})
{{
{I}error = null;
{I}elementName = "";
{I}isEmptyProperty = false;

{I}SkipNoneWhitespaceAndComments(reader);

{I}if (reader.NodeType == Xml.XmlNodeType.EndElement || reader.EOF)
{I}{{
{II}return false;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.Element)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected an XML start element representing a property, " +
{III}$"but got the node of type {{reader.NodeType}} " +
{III}$"with the value {{reader.Value}}");
{II}return false;
{I}}}

{I}elementName = TryElementName(
{II}reader, out error);
{I}if (error != null)
{I}{{
{II}return false;
{I}}}

{I}isEmptyProperty = reader.IsEmptyElement;

{I}// Consume the start tag and go to the content.
{I}reader.Read();

{I}return true;
}}"""
    )


def _generate_at_element_combinator() -> Stripped:
    """
    Generate the combinator reading a whole element of an expected name.

    An element is only its start and end tag around a content, so the content
    is read by the very same :py:class:`ContentReader` as everything else --
    there is no separate reader per primitive, per enumeration or per class.

    The name is data, not a type: ``v`` for a list item, ``v1``, ``v2``,
    *etc.* by position in a tuple, and its own XML name for a class. So it is
    bound here rather than being spelled as a type argument, and the error
    messages are phrased in terms of it -- which is why the combinator needs
    nothing else to say what it expected.

    This is the hinge of the whole composition: it turns
    a :py:class:`ContentReader` back into an :py:class:`ElementReader`, which
    is what a list and a tuple take for their items, and what a class is read
    as. Any content reader can therefore be nested as deeply as the model
    needs.
    """
    return Stripped(
        f"""\
/// <summary>
/// Bind <paramref name="elementName" /> to <paramref name="readContent" />,
/// so that the result reads the whole element, tags included.
/// </summary>
/// <typeparam name="T">Type of the parsed value</typeparam>
private static ElementReader<T> AtElement<T>(
{I}ContentReader<T> readContent,
{I}string elementName
{I})
{{
{I}return (
{II}Xml.XmlReader reader,
{II}out Reporting.Error? error
{I}) =>
{I}{{
{II}string observedName = PeekElementName(
{III}reader, out error);
{II}if (error != null)
{II}{{
{III}return default!;
{II}}}

{II}if (observedName != elementName)
{II}{{
{III}error = new Reporting.Error(
{IIII}$"Expected a <{{elementName}}> element, " +
{IIII}$"but got a <{{observedName}}> element");
{III}return default!;
{II}}}

{II}bool isEmptyElement = reader.IsEmptyElement;

{II}// Consume the start tag and go to the content.
{II}reader.Read();

{II}T value = readContent(reader, isEmptyElement, out error);
{II}if (error != null)
{II}{{
{III}return default!;
{II}}}

{II}ConsumeEndElement(
{III}reader, elementName, isEmptyElement, out error);
{II}if (error != null)
{II}{{
{III}return default!;
{II}}}

{II}return value;
{I}}};
}}"""
    )


def _generate_content_converters(
    primitive_types: Set[intermediate.PrimitiveType],
) -> List[Stripped]:
    """Generate the conversions passed to the skeletons, one per primitive."""
    result = []  # type: List[Stripped]

    for a_type, (
        function_name,
        csharp_type,
        conversion_expr,
    ) in _CONTENT_READER_BY_PRIMITIVE.items():
        if a_type not in primitive_types:
            continue

        result.append(
            Stripped(
                f"""\
/// <summary>
/// Convert the content at the current position of <paramref name="reader" />
/// to {csharp_type}.
/// </summary>
private static {csharp_type} {function_name}(Xml.XmlReader reader)
{{
{I}return {conversion_expr};
}}"""
            )
        )

    return result


def _generate_literal_parser_delegate() -> Stripped:
    """Generate the delegate which parses the text of an enumeration literal."""
    return Stripped(
        """\
/// <summary>
/// Parse the text of a literal of <typeparamref name="T" />.
/// </summary>
/// <remarks>
/// Every <c>Stringification.*FromString</c> has this shape, so it can be
/// passed on directly -- which is what lets an enumeration be read by one
/// generated combinator instead of one per enumeration.
/// </remarks>
/// <typeparam name="T">Enumeration to parse the text as</typeparam>
private delegate T? LiteralParser<T>(string text) where T : struct;"""
    )


def _generate_as_enum_combinator() -> Stripped:
    """
    Generate the single combinator to read a content as an enumeration literal.

    The parsing of the literal is passed in as a
    ``Stringification.*FromString`` method group, so that this is generated
    once instead of once per enumeration.

    The content is not necessarily a property's -- an enumeration nested as
    an item of a list or of a tuple is read by this very combinator, wrapped
    in ``AtElement``.
    """
    return Stripped(
        f"""\
/// <summary>
/// Read a content and parse it as a literal of <typeparamref name="T" />
/// with <paramref name="parseLiteral" />.
/// </summary>
/// <typeparam name="T">Enumeration to parse the content as</typeparam>
private static ContentReader<T> AsEnum<T>(
{I}LiteralParser<T> parseLiteral
{I}) where T : struct
{{
{I}ContentReader<string> readText = AsText<string>(ReadContentAsString, "");

{I}return (
{II}Xml.XmlReader reader,
{II}bool isEmpty,
{II}out Reporting.Error? error
{I}) =>
{I}{{
{II}string text = readText(reader, isEmpty, out error);
{II}if (error != null)
{II}{{
{III}return default;
{II}}}

{II}T? result = parseLiteral(text);
{II}if (result == null)
{II}{{
{III}error = new Reporting.Error(
{IIII}$"The content could not be de-serialized as a literal " +
{IIII}$"of {{typeof(T).Name}}: {{text}}");
{III}return default;
{II}}}

{II}return result.Value;
{I}}};
}}"""
    )


def _generate_as_list_combinator() -> Stripped:
    """
    Generate the combinator to read a content as a list.

    This only adds the handling of a self-closing element (an empty list) on
    top of :py:func:`_generate_read_list_helper`, so that a list reads exactly
    like every other type -- a single call.

    The items are read by an :py:class:`ElementReader`, which is what
    ``AtElement`` produces, so a list of anything -- a list of lists
    included -- composes without any further combinator.
    """
    return Stripped(
        f"""\
/// <summary>
/// Read a content as a list of items, each read with
/// <paramref name="readItem" />.
/// </summary>
/// <remarks>
/// A self-closing element represents an empty list.
/// </remarks>
/// <typeparam name="T">Type of a single list item</typeparam>
private static ContentReader<List<T>> AsList<T>(
{I}ElementReader<T> readItem
{I})
{{
{I}return (
{II}Xml.XmlReader reader,
{II}bool isEmpty,
{II}out Reporting.Error? error
{I}) =>
{I}{{
{II}error = null;

{II}if (isEmpty)
{II}{{
{III}return new List<T>();
{II}}}

{II}return ReadList<T>(
{III}reader, readItem, out error);
{I}}};
}}"""
    )


def _generate_as_element_combinator() -> Stripped:
    """
    Generate the combinator to read a content which is a self-describing element.

    A value typed as an interface or as a named union is dispatched at
    run-time by its own discriminator element, so reading it is identical in
    both cases apart from *which* ``...FromElement`` does the dispatching --
    which is why this takes that function as a parameter instead of being
    generated once per interface and once per named union.

    The value is not necessarily a property's -- the same combinator reads
    the items of a list of an interface, one nesting level deeper.
    """
    return Stripped(
        f"""\
/// <summary>
/// Read a content whose value is dispatched by its own discriminator
/// element, such as an interface or a named union.
/// </summary>
/// <typeparam name="T">Type of the value</typeparam>
private static ContentReader<T> AsElement<T>(
{I}ElementReader<T> readFromElement
{I})
{{
{I}return (
{II}Xml.XmlReader reader,
{II}bool isEmpty,
{II}out Reporting.Error? error
{I}) =>
{I}{{
{II}error = null;

{II}if (isEmpty)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML element representing the value, " +
{IIII}"but the element was self-closing");
{III}return default!;
{II}}}

{II}// We need to skip the whitespace here in order to be able to look ahead
{II}// the discriminator element shortly.
{II}SkipNoneWhitespaceAndComments(reader);

{II}if (reader.EOF)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML element representing the value, " +
{IIII}"but reached the end-of-file");
{III}return default!;
{II}}}

{II}// Try to look ahead the discriminator name;
{II}// we need this name only for the error reporting below.
{II}// The de-serialization function will perform more sophisticated checks.
{II}string? discriminatorElementName = null;
{II}if (reader.NodeType == Xml.XmlNodeType.Element)
{II}{{
{III}discriminatorElementName = reader.LocalName;
{II}}}

{II}T result = readFromElement(reader, out error);
{II}if (error != null)
{II}{{
{III}if (discriminatorElementName != null)
{III}{{
{IIII}error.PrependSegment(
{IIIII}new Reporting.NameSegment(
{IIIIII}discriminatorElementName));
{III}}}
{III}return default!;
{II}}}

{II}return result;
{I}}};
}}"""
    )


# NOTE (mristin):
# A C# primitive is not a valid part of an identifier as it is spelled
# (``byte[]``, and the lower-case names read badly), so the primitives are
# the only types which have to be renamed. They are keyed by the meta-model
# primitive rather than by the C# spelling, so that the mapping is total by
# construction.
_PRIMITIVE_TYPE_TO_MONIKER: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.BOOL: "Bool",
    intermediate.PrimitiveType.INT: "Long",
    intermediate.PrimitiveType.FLOAT: "Double",
    intermediate.PrimitiveType.STR: "String",
    intermediate.PrimitiveType.BYTEARRAY: "Bytes",
}
assert all(
    primitive_type in _PRIMITIVE_TYPE_TO_MONIKER
    for primitive_type in intermediate.PrimitiveType
)


def _type_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name the type in a way usable as a part of a C# identifier.

    Everything which is not a primitive is named by
    ``csharp_common.generate_type``, so that the name of a reader can not
    drift apart from the type of that very reader -- spelling the names out
    here once caused exactly that.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ListOf{_type_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        joined = "".join(_type_moniker(item) for item in type_anno.items)
        return f"TupleOf{joined}"

    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return _PRIMITIVE_TYPE_TO_MONIKER[primitive_type]

    return csharp_common.generate_type(type_anno)


def _from_element_name(our_type: intermediate.OurType) -> str:
    """
    Name the function reading a whole element of ``our_type``.

    Mind that this is *not* the moniker of the type: a concrete class
    without any descendant is referred to by its interface, but reads
    through a function named after the class itself.
    """
    if isinstance(our_type, intermediate.NamedUnion):
        return f"{csharp_naming.class_name(our_type.name)}FromElement"

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    )

    if (
        isinstance(our_type, intermediate.AbstractClass)
        or len(our_type.concrete_descendants) > 0
    ):
        return f"{csharp_naming.interface_name(our_type.name)}FromElement"

    return f"{csharp_naming.class_name(our_type.name)}FromElement"


def _content_reader_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """Name the field holding the reader of the content of ``type_anno``."""
    return Identifier(f"Read{_type_moniker(type_anno)}")


def _element_reader_expr(
    type_anno: intermediate.TypeAnnotationUnion, v_name_literal: str
) -> Stripped:
    """
    Generate the expression reading a single element of ``type_anno``.

    This is what a list item and a tuple item are read with. A class, an
    interface or a named union reads its own, self-describing element,
    whereas everything else is wrapped in a ``<v>`` element whose content is
    read by the very same reader as a property of that type.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    ):
        return Stripped(_from_element_name(type_anno.our_type))

    return Stripped(
        f"""\
AtElement(
{I}{_content_reader_name(type_anno)}, {v_name_literal})"""
    )


def _content_reader_initializer(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """Generate the expression initializing the reader of ``type_anno``."""
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        content_reader, csharp_type, _ = _CONTENT_READER_BY_PRIMITIVE[primitive_type]
        empty_value = _EMPTY_VALUE_BY_PRIMITIVE.get(primitive_type, None)
        arguments = content_reader
        if empty_value is not None:
            arguments = f"{arguments}, {empty_value}"
        return Stripped(f"AsText<{csharp_type}>({arguments})")

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            enum_name = csharp_naming.enum_name(our_type.name)
            return Stripped(
                f"""\
AsEnum<Aas.{enum_name}>(
{I}Stringification.{enum_name}FromString)"""
            )

        if isinstance(our_type, intermediate.NamedUnion) or (
            isinstance(our_type, intermediate.AbstractClass)
            or (
                isinstance(our_type, intermediate.ConcreteClass)
                and len(our_type.concrete_descendants) > 0
            )
        ):
            return Stripped(
                f"""\
AsElement<Aas.{_type_moniker(type_anno)}>(
{I}{_from_element_name(our_type)})"""
            )

        # NOTE (mristin):
        # A concrete class without any descendant reads its own sequence,
        # which is already a ``ContentReader``.
        return Stripped(f"{csharp_naming.class_name(our_type.name)}FromSequence")

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_type = csharp_common.generate_type(type_anno.items)
        item_reader = _element_reader_expr(type_anno.items, '"v"')
        return Stripped(
            f"""\
AsList<{item_type}>(
{I}{indent_but_first_line(item_reader, I)})"""
        )

    assert isinstance(type_anno, intermediate.TupleTypeAnnotation)

    item_types = ", ".join(
        csharp_common.generate_type(item) for item in type_anno.items
    )
    item_readers = ",\n".join(
        _element_reader_expr(item, csharp_common.string_literal(f"v{i + 1}"))
        for i, item in enumerate(type_anno.items)
    )
    return Stripped(
        f"""\
AsTuple{len(type_anno.items)}<{item_types}>(
{I}{indent_but_first_line(item_readers, I)})"""
    )


def _generate_from_element_fields(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the readers of a whole element of every concrete class.

    Reading a class's element is nothing but binding its XML name to its own
    ``...FromSequence``, which already is a :py:class:`ContentReader`. There
    is therefore nothing to generate per class beyond that binding, and it is
    bound once here instead of at every read.

    A class whose de-serialization is implementation-specific brings its own
    function, so it is skipped.
    """
    result = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            continue

        name = csharp_naming.class_name(cls.name)
        xml_name_literal = csharp_common.string_literal(naming.xml_class_name(cls.name))

        result.append(
            Stripped(
                f"""\
/// <summary>
/// Read an instance of class {name} from its XML element.
/// </summary>
internal static readonly ElementReader<Aas.{name}> {name}FromElement = (
{I}AtElement<Aas.{name}>(
{II}{name}FromSequence, {xml_name_literal}));"""
            )
        )

    return result


def _generate_content_reader_fields(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the fields holding one reader per distinct property type.

    The readers are composed once, at the initialization of the class,
    instead of at every property of every instance -- composing them at
    the call site would allocate a delegate on every single read.
    """
    initializer_by_name = (
        collections.OrderedDict()
    )  # type: MutableMapping[Identifier, Tuple[Stripped, Stripped]]

    def register(type_anno: intermediate.TypeAnnotationUnion) -> None:
        """Register the reader of ``type_anno``, its items' readers first."""
        # NOTE (mristin):
        # A field initializer reads the fields it composes, so a reader has
        # to be declared after the readers it is composed of.
        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            item_type_annotations = [
                type_anno.items
            ]  # type: List[intermediate.TypeAnnotationUnion]
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_type_annotations = list(type_anno.items)
        else:
            item_type_annotations = []

        for item_type_anno in item_type_annotations:
            # NOTE (mristin):
            # A class reads its own element, so it needs no reader of its own.
            if isinstance(
                item_type_anno, intermediate.OurTypeAnnotation
            ) and isinstance(
                item_type_anno.our_type,
                (
                    intermediate.AbstractClass,
                    intermediate.ConcreteClass,
                    intermediate.NamedUnion,
                ),
            ):
                continue

            register(item_type_anno)

        name = _content_reader_name(type_anno)
        if name in initializer_by_name:
            return

        initializer_by_name[name] = (
            csharp_common.generate_type(type_anno),
            _content_reader_initializer(type_anno),
        )

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            register(intermediate.beneath_optional(prop.type_annotation))

    result = []  # type: List[Stripped]
    for name, (csharp_type, initializer) in initializer_by_name.items():
        result.append(
            Stripped(
                f"""\
private static readonly ContentReader<{csharp_type}> {name} = (
{I}{indent_but_first_line(initializer, I)});"""
            )
        )

    return result


@require(lambda prop, cls: id(prop) in cls.property_id_set)
def _generate_deserialize_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the snippet to deserialize the property ``prop``.

    Every property kind reads through the very same call -- only the reader
    differs, and it has been composed once into a field (see
    :py:func:`_generate_property_reader_fields`). The failure is not handled
    here: the error is marked with the property's own element name once,
    right after the ``switch``, see
    :py:func:`_generate_deserialize_impl_cls_from_sequence`.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    if isinstance(type_anno, intermediate.ListTypeAnnotation) and not isinstance(
        type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
    ):
        return None, Error(
            prop.parsed.node,
            f"(mristin) We only handle the XML de-serialization of lists of "
            f"atomic values, but you want to generate the code for a list of "
            f"type {type_anno}. Please contact the developers if you need "
            f"this feature.",
        )

    target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))
    reader_name = _content_reader_name(type_anno)

    return (
        Stripped(
            f"""\
{target_var} = {reader_name}(
{I}reader, isEmptyProperty, out error);"""
        ),
        None,
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_deserialize_impl_cls_from_sequence(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the function to de-serialize the ``cls`` from an XML sequence."""
    name = csharp_naming.class_name(identifier=cls.name)

    description = Stripped(
        f"""\
/// <summary>
/// Deserialize an instance of class {name} from a sequence of XML elements.
/// </summary>
/// <remarks>
/// If <paramref name="isEmptySequence" /> is set, we should try to deserialize
/// the instance from an empty sequence. That is, the parent element
/// was a self-closing element.
/// </remarks>"""
    )

    # NOTE (mristin, 2022-06-21):
    # Hard-wire for the case when no sequence is read
    if len(cls.constructor.arguments) == 0:
        return (
            Stripped(
                f"""\
{description}
internal static Aas.{name} {name}FromSequence(
{I}Xml.XmlReader reader,
{I}bool isEmptySequence,
{I}out Reporting.Error? error)
{{
{I}error = null;
{I}return new Aas.{name}();
}}  // internal static Aas.{name} {name}FromSequence"""
            ),
            None,
        )

    errors = []  # type: List[Error]

    blocks = [
        Stripped("error = null;"),
    ]  # type: List[Stripped]

    assert len(cls.constructor.arguments) > 0, "Otherwise expected hard-wiring above"
    init_target_var_stmts = []  # type: List[Stripped]
    for prop in cls.properties:
        target_type = csharp_common.generate_type(prop.type_annotation)
        target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))

        # NOTE (mristin, 2022-04-13):
        # This is a poor man's trick to make all temporary variables optional.
        # The required constructor arguments / properties will be checked just
        # before the constructor as we can not predict in advance which properties
        # were actually provided without any lookahead in XML reading.
        if not target_type.endswith("?"):
            target_type = Stripped(f"{target_type}?")

        init_target_var_stmts.append(Stripped(f"{target_type} {target_var} = null;"))
    blocks.append(Stripped("\n".join(init_target_var_stmts)))

    # noinspection PyListCreation
    blocks_for_non_empty = []  # type: List[Stripped]

    blocks_for_non_empty.append(
        Stripped(
            f"""\
SkipNoneWhitespaceAndComments(reader);
if (reader.EOF)
{{
{I}error = new Reporting.Error(
{II}"Expected an XML element representing " +
{II}"a property of an instance of class {name}, " +
{II}"but reached the end-of-file");
{I}return default!;
}}"""
        )
    )

    case_blocks = []  # type: List[Stripped]
    for prop in cls.properties:
        case_body, error = _generate_deserialize_property(prop=prop, cls=cls)
        if error is not None:
            errors.append(error)
            continue

        assert case_body is not None

        xml_prop_name = prop.xml_name
        xml_prop_name_literal = csharp_common.string_literal(xml_prop_name)

        # NOTE (mristin):
        # No braces are necessary, as no case declares a local of its own --
        # every one of them is a single assignment.
        case_blocks.append(
            Stripped(
                f"""\
case {xml_prop_name_literal}:
{I}{indent_but_first_line(case_body, I)}
{I}break;"""
            )
        )

    if len(errors) > 0:
        return None, errors

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}error = new Reporting.Error(
{II}"We expected properties of the class {name}, " +
{II}"but got an unexpected element " +
{II}$"with the name {{elementName}}");
{I}return default!;"""
        )
    )

    switch_body = "\n".join(case_blocks)

    blocks_for_non_empty.append(
        Stripped(
            f"""\
while (TryNextProperty(
{II}reader,
{II}out string elementName,
{II}out bool isEmptyProperty,
{II}out error))
{{
{I}switch (elementName)
{I}{{
{II}{indent_but_first_line(switch_body, II)}
{I}}}

{I}// NOTE (mristin):
{I}// Every property is read in this very loop, so we mark the error with
{I}// the property's own element name here, once, instead of at every
{I}// single case above. For a matched case, elementName *is* that name.
{I}if (error != null)
{I}{{
{II}error.PrependSegment(
{III}new Reporting.NameSegment(
{IIII}elementName));
{II}return default!;
{I}}}

{I}ConsumeEndElement(
{II}reader, elementName, isEmptyProperty, out error);
{I}if (error != null)
{I}{{
{II}return default!;
{I}}}
}}

// NOTE (mristin):
// The loop also ends when the next property could not be read at all,
// which is the only way out of it that is a failure.
if (error != null)
{{
{I}return default!;
}}"""
        )
    )

    body_for_non_empty_sequence = "\n".join(blocks_for_non_empty)
    blocks.append(
        Stripped(
            f"""\
if (!isEmptySequence)
{{
{I}{indent_but_first_line(body_for_non_empty_sequence, I)}
}}"""
        )
    )

    # region Check that the mandatory properties have been set

    for prop in cls.properties:
        prop_csharp = csharp_naming.property_name(prop.name)
        target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            blocks.append(
                Stripped(
                    f"""\
if ({target_var} == null)
{{
{I}error = new Reporting.Error(
{II}"The required property {prop_csharp} has not been given " +
{II}"in the XML representation of an instance of class {name}");
{I}return default!;
}}"""
                )
            )

    # endregion

    # region Pass in properties as arguments to the constructor

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

    init_writer = io.StringIO()
    init_writer.write(f"return new Aas.{name}(\n")

    for i, arg in enumerate(cls.constructor.arguments):
        prop = cls.properties_by_name[arg.name]

        # NOTE (mristin, 2022-04-13):
        # The argument to the constructor may be optional while the property might
        # be required, since we can set the default value in the body of the
        # constructor. However, we can not have an optional property and a required
        # constructor argument as we then would not know how to create the instance.

        if not (
            intermediate.type_annotations_equal(
                arg.type_annotation, prop.type_annotation
            )
            or intermediate.type_annotations_equal(
                intermediate.beneath_optional(arg.type_annotation),
                prop.type_annotation,
            )
        ):
            errors.append(
                Error(
                    arg.parsed.node,
                    f"Expected type annotation for property {prop.name!r} "
                    f"and constructor argument {arg.name!r} "
                    f"of the class {cls.name!r} to have matching types, "
                    f"but they do not: "
                    f"property type is {prop.type_annotation} "
                    f"and argument type is {arg.type_annotation}. "
                    f"Hence we do not know how to generate the call "
                    f"to the constructor in the JSON de-serialization.",
                )
            )
            continue

        arg_var = csharp_naming.variable_name(Identifier(f"the_{arg.name}"))

        init_writer.write(f"{I}{arg_var}")
        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            init_writer.write("\n")

            # Dedention could not work here due to prefix indention at the very
            # beginning.
            init_writer.write(
                f"""\
{II} ?? throw new System.InvalidOperationException(
{III}"Unexpected null, had to be handled before")"""
            )

        if i < len(cls.constructor.arguments) - 1:
            init_writer.write(",\n")
        else:
            init_writer.write(");")

    if len(errors) > 0:
        return None, errors

    # endregion

    blocks.append(Stripped(init_writer.getvalue()))

    writer = io.StringIO()
    writer.write(
        f"""\
{description}
internal static Aas.{name} {name}FromSequence(
{I}Xml.XmlReader reader,
{I}bool isEmptySequence,
{I}out Reporting.Error? error)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // internal static Aas.{name}? {name}FromSequence")

    return Stripped(writer.getvalue()), None


def _generate_peek_element_name() -> Stripped:
    """
    Generate the shared helper looking ahead the name of the current element.

    Nothing is consumed, so the caller can still decide what to do with
    the element: ``AtElement`` checks the name against the one it expects,
    while a de-serialization dispatching on a discriminator element uses
    the name to pick the reader.
    """
    return Stripped(
        f"""\
/// <summary>
/// Look ahead the name of the element at the current position of
/// <paramref name="reader" />, without consuming anything.
/// </summary>
private static string PeekElementName(
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

{I}return TryElementName(
{II}reader, out error);
}}"""
    )


def _generate_deserialize_impl_interface_from_element(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate the function to de-serialize an ``interface`` from an XML element."""
    name = csharp_naming.interface_name(interface.name)

    blocks = []  # type: List[Stripped]

    case_stmts = []  # type: List[Stripped]
    for implementer in interface.implementers:
        implementer_xml_name_literal = csharp_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        implementer_name = csharp_naming.class_name(implementer.name)

        case_stmts.append(
            Stripped(
                f"""\
case {implementer_xml_name_literal}:
{I}return {implementer_name}FromElement(
{II}reader, out error);"""
            )
        )

    case_stmts.append(
        Stripped(
            f"""\
default:
{I}error = new Reporting.Error(
{II}$"Unexpected element with the name {{elementName}}");
{I}return default!;"""
        )
    )

    switch_writer = io.StringIO()
    switch_writer.write(
        f"""\
string elementName = PeekElementName(
{I}reader, out error);
if (error != null)
{{
{I}return default!;
}}

switch (elementName)
{{
"""
    )
    for i, case_stmt in enumerate(case_stmts):
        if i > 0:
            switch_writer.write("\n")
        switch_writer.write(textwrap.indent(case_stmt, I))

    switch_writer.write("\n}")

    blocks.append(Stripped(switch_writer.getvalue()))

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Deserialize an instance of {name} from an XML element.
/// </summary>
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
internal static Aas.{name} {name}FromElement(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // internal static Aas.{name}? {name}FromElement")

    return Stripped(writer.getvalue())


def _generate_deserialize_impl_named_union_from_element(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """Generate the function to de-serialize a ``named_union`` from an XML element."""
    name = csharp_naming.class_name(named_union.name)

    blocks = []  # type: List[Stripped]

    case_stmts = []  # type: List[Stripped]
    for implementer in named_union.implementers:
        implementer_xml_name_literal = csharp_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        implementer_name = csharp_naming.class_name(implementer.name)
        from_method_name = csharp_naming.method_name(
            Identifier(f"from_{implementer.name}")
        )

        case_stmts.append(
            Stripped(
                f"""\
case {implementer_xml_name_literal}:
{{
{I}Aas.{implementer_name} instance = {implementer_name}FromElement(
{II}reader, out error);
{I}if (error != null)
{I}{{
{II}return default!;
{I}}}
{I}return Aas.{name}.{from_method_name}(instance);
}}"""
            )
        )

    case_stmts.append(
        Stripped(
            f"""\
default:
{I}error = new Reporting.Error(
{II}$"Unexpected element with the name {{elementName}}");
{I}return default!;"""
        )
    )

    switch_writer = io.StringIO()
    switch_writer.write(
        f"""\
string elementName = PeekElementName(
{I}reader, out error);
if (error != null)
{{
{I}return default!;
}}

switch (elementName)
{{
"""
    )
    for i, case_stmt in enumerate(case_stmts):
        if i > 0:
            switch_writer.write("\n")
        switch_writer.write(textwrap.indent(case_stmt, I))

    switch_writer.write("\n}")

    blocks.append(Stripped(switch_writer.getvalue()))

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Deserialize an instance of {name} from an XML element.
/// </summary>
internal static Aas.{name} {name}FromElement(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // internal static Aas.{name}? {name}FromElement")

    return Stripped(writer.getvalue())


def _generate_deserialize_impl(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the implementation for deserialization functions."""
    blocks = [
        _generate_skip_whitespace_and_comments(),
        _generate_read_whole_content_as_base_64(),
        _generate_extract_element_name(),
        _generate_peek_element_name(),
        _generate_element_reader_delegates(),
    ]  # type: List[Stripped]

    needed_readers = _needed_content_readers(symbol_table)
    from_element_fields = _generate_from_element_fields(symbol_table)

    blocks.extend(_generate_as_text_combinators(needed=needed_readers))
    blocks.extend(
        _generate_content_converters(primitive_types=needed_readers.primitive_types)
    )

    # NOTE (mristin):
    # A class reads its own element through ``AtElement`` as well, so this is
    # needed as soon as there is anything at all to read.
    if needed_readers.v_elements or len(from_element_fields) > 0:
        blocks.append(_generate_consume_end_element())
        blocks.append(_generate_at_element_combinator())

    if any(
        len(cls.constructor.arguments) > 0
        for cls in symbol_table.concrete_classes
        if not cls.is_implementation_specific
    ):
        blocks.append(_generate_try_next_property())

    if needed_readers.enumerations:
        blocks.append(_generate_literal_parser_delegate())
        blocks.append(_generate_as_enum_combinator())

    if needed_readers.lists:
        blocks.append(_generate_read_list_helper())
        blocks.append(_generate_as_list_combinator())

    if needed_readers.polymorphic:
        blocks.append(_generate_as_element_combinator())

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        for arity in tuple_arities:
            blocks.append(_generate_as_tuple_combinator(arity))

    # NOTE (mristin):
    # The readers are composed once, here, rather than at every property of
    # every instance -- composing them at the call site would allocate
    # a delegate on every single read.
    #
    # A field initializer reads the fields it composes, and a reader of
    # a list or of a tuple of a class composes that class's reader, so
    # the classes have to come first.
    blocks.extend(from_element_fields)
    blocks.extend(_generate_content_reader_fields(symbol_table))

    errors = []  # type: List[Error]

    # NOTE (mristin, 2022-04-13):
    # Enumerations are going to be directly deserialized using
    # ``Stringification``.

    # NOTE (mristin, 2022-04-13):
    # Constrained primitives are only verified, but do not represent a C# type.

    for cls in symbol_table.classes:
        if cls.is_implementation_specific:
            implementation_keys = [
                specific_implementations.ImplementationKey(
                    f"Xmlization/DeserializeImplementation/"
                    f"{cls.name}_from_element.cs"
                ),
                specific_implementations.ImplementationKey(
                    f"Xmlization/DeserializeImplementation/"
                    f"{cls.name}_from_sequence.cs"
                ),
            ]

            for implementation_key in implementation_keys:
                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            cls.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {cls.name}: {implementation_key}",
                        )
                    )
                    continue
                else:
                    blocks.append(spec_impls[implementation_key])
        else:
            if isinstance(cls, intermediate.ConcreteClass):
                (
                    block,
                    generation_errors,
                ) = _generate_deserialize_impl_cls_from_sequence(cls=cls)
                if generation_errors is not None:
                    errors.append(
                        Error(
                            cls.parsed.node,
                            f"Failed to generate the XML deserialization code "
                            f"for the class {cls.name}",
                            generation_errors,
                        )
                    )
                else:
                    assert block is not None
                    blocks.append(block)

            if cls.interface is not None:
                blocks.append(
                    _generate_deserialize_impl_interface_from_element(
                        interface=cls.interface
                    )
                )

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_deserialize_impl_named_union_from_element(named_union=named_union)
        )

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()

    writer.write(
        """\
/// <summary>
/// Implement the deserialization of meta-model classes from XML.
/// </summary>
/// <remarks>
/// The implementation propagates an <see cref="Reporting.Error" /> instead of
/// relying on exceptions. Under the assumption that incorrect data is much less
/// frequent than correct data, this makes the deserialization more
/// efficient.
///
/// However, we do not want to force the client to deal with
/// the <see cref="Reporting.Error" /> class as this is not intuitive.
/// Therefore we distinguish the implementation, realized in
/// <see cref="DeserializeImplementation" />, and the facade given in
/// <see cref="Deserialize" /> class.
/// </remarks>
internal static class DeserializeImplementation
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal static class DeserializeImplementation")

    return Stripped(writer.getvalue()), None


def _generate_deserialize_from(name: Identifier) -> Stripped:
    """Generate the facade method for deserialization of the class or interface."""
    writer = io.StringIO()

    writer.write(
        f"""\
/// <summary>
/// Deserialize an instance of {name} from <paramref name="reader" />.
/// </summary>
/// <param name="reader">Initialized XML reader with cursor set to the element</param>
/// <exception cref="Xmlization.Exception">
/// Thrown when the element is not a valid XML
/// representation of {name}.
/// </exception>
"""
    )

    if name.startswith("I"):
        writer.write(
            """\
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]"""
        )

    writer.write(
        f"""\
public static Aas.{name} {name}From(
{I}Xml.XmlReader reader)
{{
{I}DeserializeImplementation.SkipNoneWhitespaceAndComments(reader);

{I}if (!reader.EOF && reader.NodeType == Xml.XmlNodeType.XmlDeclaration)
{I}{{
{II}throw new Xmlization.Exception(
{III}"",
{III}"Unexpected XML declaration when reading an instance " +
{III}"of class {name}, as we expect the reader " +
{III}"to be set at content with MoveToContent");
{I}}}

{I}Aas.{name} result = DeserializeImplementation.{name}FromElement(
{II}reader,
{II}out Reporting.Error? error);
{I}if (error != null)
{I}{{
{II}throw new Xmlization.Exception(
{III}Reporting.GenerateRelativeXPath(error.PathSegments),
{III}error.Cause);
{I}}}
{I}return result;
}}"""
    )

    return Stripped(writer.getvalue())


def _generate_deserialize(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the public class ``Deserialize``."""
    blocks = []  # type: List[Stripped]

    # NOTE (mristin, 2022-04-13):
    # We use stringification for de-serialization of enumerations.

    # NOTE (mristin, 2022-04-13):
    # Constrained primitives are not handled as separate classes, but as
    # primitives, and only verified in the verification.

    for cls in symbol_table.classes:
        if cls.interface is not None:
            blocks.append(
                _generate_deserialize_from(
                    name=csharp_naming.interface_name(cls.interface.name)
                )
            )

        if isinstance(cls, intermediate.ConcreteClass):
            blocks.append(
                _generate_deserialize_from(name=csharp_naming.class_name(cls.name))
            )

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_deserialize_from(name=csharp_naming.class_name(named_union.name))
        )

    writer = io.StringIO()
    writer.write(
        """\
/// <summary>
/// Deserialize instances of meta-model classes from XML.
/// </summary>
"""
    )

    first_cls = symbol_table.classes[0] if len(symbol_table.classes) > 0 else None

    if first_cls is not None:
        cls_name: str
        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = csharp_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = csharp_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = csharp_naming.variable_name(Identifier("an_instance"))

        writer.write(
            f"""\
/// <example>
/// Here is an example how to parse an instance of class {cls_name}:
/// <code>
/// var reader = new System.Xml.XmlReader(/* some arguments */);
/// Aas.{cls_name} {an_instance_variable} = Deserialize.{cls_name}From(
/// {I}reader);
/// </code>
/// </example>
///
/// <example>
/// If the elements live in a namespace, you have to supply it. For example:
/// <code>
/// var reader = new System.Xml.XmlReader(/* some arguments */);
/// Aas.{cls_name} {an_instance_variable} = Deserialize.{cls_name}From(
/// {I}reader,
/// {I}"http://www.example.com/5/12");
/// </code>
/// </example>
"""
        )

    writer.write(
        """\
public static class Deserialize
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public static class Deserialize")

    return Stripped(writer.getvalue())


def _generate_serialize_element_helper() -> Stripped:
    """Generate the generic helper to write a property as a named XML element."""
    return Stripped(
        f"""\
/// <summary>
/// Write the content of a property, positioned between its start and end tag.
/// </summary>
/// <typeparam name="T">Type of the property value</typeparam>
private delegate void ElementContentSerializer<T>(
{I}T that, Xml.XmlWriter writer);

/// <summary>
/// Serialize <paramref name="that" /> as an XML element with
/// the given <paramref name="name" />, delegating the content in-between the
/// start and the end tag to <paramref name="serializeContent" />.
/// </summary>
/// <remarks>
/// This is shared by all the property kinds (primitive, enumeration, class,
/// interface, named union, list) as they all wrap their content in exactly
/// the same way.
/// </remarks>
/// <typeparam name="T">Type of the property value</typeparam>
private static void SerializeElement<T>(
{I}string name,
{I}T that,
{I}Xml.XmlWriter writer,
{I}ElementContentSerializer<T> serializeContent)
{{
{I}writer.WriteStartElement(name, NS);
{I}serializeContent(that, writer);
{I}writer.WriteEndElement();
}}"""
    )


def _generate_write_v_element_as_primitive_functions() -> List[Stripped]:
    """
    Generate the functions to write a primitive value as a named element.

    These mirror the read-side content readers
    on the write side: a tuple item, unlike a list item, is wrapped in a
    positional element name (<c>v1</c>, <c>v2</c>, *etc.*) instead of always
    the fixed <c>v</c>, so we generate one write function per primitive type,
    parameterized by the element name, instead of inlining the
    start-element/write-value/end-element sequence at every tuple item.
    """
    result = []  # type: List[Stripped]

    for function_name, csharp_type, write_value_statement in (
        ("WriteVElementAsBoolean", "bool", "writer.WriteValue(that);"),
        ("WriteVElementAsLong", "long", "writer.WriteValue(that);"),
        ("WriteVElementAsDouble", "double", "writer.WriteValue(that);"),
        ("WriteVElementAsString", "string", "writer.WriteValue(that);"),
        (
            "WriteVElementAsBytes",
            "byte[]",
            "writer.WriteBase64(that, 0, that.Length);",
        ),
    ):
        result.append(
            Stripped(
                f"""\
/// <summary>
/// Write <paramref name="that" /> as a named element.
/// </summary>
private static void {function_name}(
{I}{csharp_type} that,
{I}string elementName,
{I}Xml.XmlWriter writer)
{{
{I}writer.WriteStartElement(elementName, NS);
{I}{write_value_statement}
{I}writer.WriteEndElement();
}}"""
            )
        )

    return result


def _generate_write_v_element_as_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the function to write a literal of ``enumeration`` as a named element."""
    enum_name = csharp_naming.enum_name(enumeration.name)

    return Stripped(
        f"""\
/// <summary>
/// Write <paramref name="that" /> as a named element.
/// </summary>
private static void WriteVElementAs{enum_name}(
{I}Aas.{enum_name} that,
{I}string elementName,
{I}Xml.XmlWriter writer)
{{
{I}writer.WriteStartElement(elementName, NS);
{I}writer.WriteValue(
{II}Stringification.ToString(that)
{III}?? throw new System.ArgumentException(
{IIII}"Invalid literal for the enumeration {enum_name}: " +
{IIII}that.ToString()));
{I}writer.WriteEndElement();
}}"""
    )


def _generate_tuple_item_serializer_helpers() -> Stripped:
    """Generate the delegate and adapter shared by all the generic tuple serializers."""
    return Stripped(
        f"""\
/// <summary>
/// Write a single tuple item wrapped in a named element.
/// </summary>
/// <remarks>
/// A tuple-typed property is written by <c>SerializeTupleN</c> (see
/// <see cref="SerializeTuple2{{T0, T1}}" /> for the arity-2 case, *etc.*),
/// which -- like <see cref="SerializeElement{{T}}" /> -- expects an
/// <see cref="ElementContentSerializer{{T}}" /> per item. A class or named
/// union item's own <c>Visit</c> method (or overload) already has that shape
/// (writing its own element directly, with no wrapping needed), so it can be
/// passed on unchanged. A primitive or enumeration item, on the other hand,
/// first needs to be wrapped in its own positional <c>v1</c>, <c>v2</c>,
/// *etc.* element -- this adapter closes over the element name so that
/// a tuple-typed property does not need to spell out that wrapping (start
/// element/write value/end element) at every item.
/// </remarks>
/// <typeparam name="T">Type of the item to be written</typeparam>
private delegate void NamedElementSerializer<T>(
{I}T that, string elementName, Xml.XmlWriter writer);

/// <summary>
/// Adapt <paramref name="writeItem" /> -- a named-element item writer such as
/// <see cref="WriteVElementAsLong" /> -- into an
/// <see cref="ElementContentSerializer{{T}}" /> bound to
/// <paramref name="elementName" />, for use in a tuple-typed property.
/// </summary>
/// <typeparam name="T">Type of the item to be written</typeparam>
private static ElementContentSerializer<T> AsTupleItemSerializer<T>(
{I}NamedElementSerializer<T> writeItem,
{I}string elementName)
{{
{I}return (T that, Xml.XmlWriter writer) => writeItem(that, elementName, writer);
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_serialize_tuple_helper(arity: int) -> Stripped:
    """
    Generate a generic function to serialize a tuple of the given ``arity``.

    Each positional item is written by its own ``serializeItemI`` callable,
    re-using the very same :py:class:`ElementContentSerializer` delegate
    defined for :py:func:`_generate_serialize_element_helper`, since a tuple
    item writer has exactly the same shape (write the item's own content,
    positioned wherever the writer already is).
    """
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(type_params)

    if arity == 1:
        tuple_type = f"System.ValueTuple<{type_params[0]}>"
    else:
        tuple_type = f"({type_params_joined})"

    params_joined = ",\n".join(
        f"ElementContentSerializer<T{i}> serializeItem{i}" for i in range(arity)
    )

    write_stmts_joined = "\n".join(
        f"serializeItem{i}(that.Item{i + 1}, writer);" for i in range(arity)
    )

    function_name = f"SerializeTuple{arity}"

    return Stripped(
        f"""\
/// <summary>
/// Write the tuple <paramref name="that" /> of {arity} item(s) with
/// <paramref name="serializeItem0" />, <paramref name="serializeItem1" />,
/// *etc.*, positioned wherever <paramref name="writer" /> already is.
/// </summary>
/// <remarks>
/// This is shared by all the tuple-typed properties of arity {arity}.
/// </remarks>
private static void {function_name}<{type_params_joined}>(
{I}{tuple_type} that,
{I}Xml.XmlWriter writer,
{I}{indent_but_first_line(params_joined, I)})
{{
{I}{indent_but_first_line(write_stmts_joined, I)}
}}"""
    )


def _generate_serialize_primitive_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of the primitive-type ``prop`` as XML content."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    a_type = intermediate.try_primitive_type(type_anno)
    assert (
        a_type is not None
    ), f"Unexpected non-primitive type of the property {prop.name!r}: {type_anno}"

    prop_name = csharp_naming.property_name(prop.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    content_serializer: Stripped

    if (
        a_type is intermediate.PrimitiveType.BOOL
        or a_type is intermediate.PrimitiveType.INT
        or a_type is intermediate.PrimitiveType.FLOAT
        or a_type is intermediate.PrimitiveType.STR
    ):
        content_serializer = Stripped("(value, w) => w.WriteValue(value)")
    elif a_type is intermediate.PrimitiveType.BYTEARRAY:
        content_serializer = Stripped(
            "(value, w) => w.WriteBase64(value, 0, value.Length)"
        )
    else:
        assert_never(a_type)

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        if a_type in (
            intermediate.PrimitiveType.BOOL,
            intermediate.PrimitiveType.INT,
            intermediate.PrimitiveType.FLOAT,
        ):
            return Stripped(
                f"""\
if (that.{prop_name}.HasValue)
{{
{I}SerializeElement(
{II}{xml_prop_name_literal},
{II}that.{prop_name}.Value,
{II}writer,
{II}{indent_but_first_line(content_serializer, II)});
}}"""
            )
        else:
            return Stripped(
                f"""\
if (that.{prop_name} != null)
{{
{I}SerializeElement(
{II}{xml_prop_name_literal},
{II}that.{prop_name},
{II}writer,
{II}{indent_but_first_line(content_serializer, II)});
}}"""
            )

    return Stripped(
        f"""\
SerializeElement(
{I}{xml_prop_name_literal},
{I}that.{prop_name},
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )


def _generate_serialize_enumeration_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of an enumeration ``prop`` as XML content."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    )

    enumeration = type_anno.our_type

    prop_name = csharp_naming.property_name(prop.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    enum_name = csharp_naming.enum_name(enumeration.name)

    content_serializer = Stripped(
        f"""\
(value, w) =>
{{
{I}string? text = Stringification.ToString(value);
{I}w.WriteValue(
{II}text
{III}?? throw new System.ArgumentException(
{IIII}"Invalid literal for the enumeration {enum_name}: " +
{IIII}value.ToString()));
}}"""
    )

    result = Stripped(
        f"""\
SerializeElement(
{I}{xml_prop_name_literal},
{I}that.{prop_name},
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        result = Stripped(
            f"""\
if (that.{prop_name} != null)
{{
{I}{indent_but_first_line(result, I)}
}}"""
        )

    return result


def _generate_serialize_polymorphic_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """
    Generate the serialization of a polymorphic property as XML content.

    A property is polymorphic here if the element to write is picked at
    run-time from the value itself, dispatched through its own discriminator
    element -- this is the case both for an interface-typed property and for
    a named union, so we treat them uniformly.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    # fmt: off
    assert (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and (
                    # pylint: disable=consider-merging-isinstance
                    isinstance(type_anno.our_type, intermediate.AbstractClass)
                    or (
                            isinstance(type_anno.our_type, intermediate.ConcreteClass)
                            and len(type_anno.our_type.concrete_descendants) > 0
                    )
                    or isinstance(type_anno.our_type, intermediate.NamedUnion)
            )
    ), "See intermediate._translate._verify_only_simple_type_patterns"
    # fmt: on

    prop_name = csharp_naming.property_name(prop.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    content_serializer = Stripped("(value, w) => this.Visit(value, w)")

    result = Stripped(
        f"""\
SerializeElement(
{I}{xml_prop_name_literal},
{I}that.{prop_name},
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        result = Stripped(
            f"""\
if (that.{prop_name} != null)
{{
{I}{indent_but_first_line(result, I)}
}}"""
        )

    return result


def _generate_serialize_concrete_class_property_as_sequence(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of the class ``prop`` as a sequence of properties."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.OurTypeAnnotation)
    assert isinstance(type_anno.our_type, intermediate.ConcreteClass)

    cls_to_sequence = csharp_naming.method_name(
        Identifier(f"{type_anno.our_type.name}_to_sequence")
    )

    prop_name = csharp_naming.property_name(prop.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    content_serializer = Stripped(f"(value, w) => this.{cls_to_sequence}(value, w)")

    result = Stripped(
        f"""\
SerializeElement(
{I}{xml_prop_name_literal},
{I}that.{prop_name},
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        result = Stripped(
            f"""\
if (that.{prop_name} != null)
{{
{I}{indent_but_first_line(result, I)}
}}"""
        )

    return result


def _generate_serialize_list_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of a list ``prop`` as a sequence of elements."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.ListTypeAnnotation)

    primitive_type = intermediate.try_primitive_type(type_anno.items)

    item_write_block: Stripped

    if primitive_type is not None:
        write_item_statement: Stripped

        if (
            primitive_type is intermediate.PrimitiveType.BOOL
            or primitive_type is intermediate.PrimitiveType.INT
            or primitive_type is intermediate.PrimitiveType.FLOAT
            or primitive_type is intermediate.PrimitiveType.STR
        ):
            write_item_statement = Stripped(
                """\
w.WriteValue(item);"""
            )
        elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
            write_item_statement = Stripped(
                """\
w.WriteBase64(item, 0, item.Length);"""
            )
        else:
            assert_never(primitive_type)

        item_write_block = Stripped(
            f"""\
w.WriteStartElement("v", NS);
{write_item_statement}
w.WriteEndElement();"""
        )

    elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
        our_type = type_anno.items.our_type

        if isinstance(our_type, intermediate.Enumeration):
            enum_name = csharp_naming.enum_name(our_type.name)

            item_write_block = Stripped(
                f"""\
w.WriteStartElement("v", NS);
w.WriteValue(
{I}Stringification.ToString(item)
{II}?? throw new System.ArgumentException(
{III}"Invalid literal for the enumeration {enum_name}: " +
{III}item.ToString()));
w.WriteEndElement();"""
            )
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("This case should have been handled before.")

        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            # A named union has its own ``Visit`` overload in the visitor
            # (see :py:func:`_generate_union_visit_helper`), so it can be
            # visited exactly like a class instance here.
            item_write_block = Stripped(
                """\
this.Visit(item, w);"""
            )
        else:
            assert_never(our_type)
    else:
        raise NotImplementedError(
            "(mristin) We generate currently only the code for serializing lists of "
            "atomic values to XML, but you want to generate the code for a list of "
            f"type {type_anno}. "
            f"Please contact the developers if you need this feature."
        )

    content_serializer = Stripped(
        f"""\
(value, w) =>
{{
{I}foreach (var item in value)
{I}{{
{II}{indent_but_first_line(item_write_block, II)}
{I}}}
}}"""
    )

    prop_name = csharp_naming.property_name(prop.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    result = Stripped(
        f"""\
SerializeElement(
{I}{xml_prop_name_literal},
{I}that.{prop_name},
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        result = Stripped(
            f"""\
if (that.{prop_name} != null)
{{
{I}{indent_but_first_line(result, I)}
}}"""
        )

    return result


def _generate_serialize_tuple_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of a tuple ``prop`` as a sequence of elements."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.TupleTypeAnnotation)

    prop_name = csharp_naming.property_name(prop.name)

    item_serializer_exprs = []  # type: List[Stripped]

    for i, item_type_anno in enumerate(type_anno.items):
        primitive_type = intermediate.try_primitive_type(item_type_anno)

        if primitive_type is not None:
            item_type = csharp_common.generate_type(item_type_anno)
            v_name_literal = csharp_common.string_literal(f"v{i + 1}")

            write_function: str
            if primitive_type is intermediate.PrimitiveType.BOOL:
                write_function = "WriteVElementAsBoolean"
            elif primitive_type is intermediate.PrimitiveType.INT:
                write_function = "WriteVElementAsLong"
            elif primitive_type is intermediate.PrimitiveType.FLOAT:
                write_function = "WriteVElementAsDouble"
            elif primitive_type is intermediate.PrimitiveType.STR:
                write_function = "WriteVElementAsString"
            elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                write_function = "WriteVElementAsBytes"
            else:
                assert_never(primitive_type)

            item_serializer_exprs.append(
                Stripped(
                    f"AsTupleItemSerializer<{item_type}>({write_function}, {v_name_literal})"
                )
            )
        elif isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
            item_type_anno.our_type, intermediate.Enumeration
        ):
            item_type = csharp_common.generate_type(item_type_anno)
            enum_name = csharp_naming.enum_name(item_type_anno.our_type.name)
            v_name_literal = csharp_common.string_literal(f"v{i + 1}")

            item_serializer_exprs.append(
                Stripped(
                    f"AsTupleItemSerializer<{item_type}>("
                    f"WriteVElementAs{enum_name}, {v_name_literal})"
                )
            )
        elif isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
            item_type_anno.our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            # NOTE (mristin):
            # ``this.Visit`` already writes the item's own element directly
            # (with no positional wrapping needed), so we can pass it on
            # unchanged as a bare method group: for a class item, its
            # ``(IClass, Xml.XmlWriter)`` overload is contravariantly
            # compatible with ``ElementContentSerializer<T>`` for any more
            # specific interface ``T``; for a named union item, overload
            # resolution instead picks the union-specific ``Visit`` overload
            # (see :py:func:`_generate_union_visit_helper`), which matches
            # ``T`` exactly.
            item_serializer_exprs.append(Stripped("this.Visit"))

        else:
            # NOTE (mristin):
            # A tuple item can only be a primitive value, a constrained primitive,
            # an enumeration literal, a class instance or a named union; see
            # intermediate._translate._verify_only_simple_type_patterns.
            raise AssertionError(
                f"Unexpected tuple item type {item_type_anno} at index {i} "
                f"for the property {prop.name!r}"
            )

    item_serializer_exprs_joined = ",\n".join(item_serializer_exprs)

    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    arity = len(type_anno.items)

    content_serializer = Stripped(
        f"""\
(value, w) => SerializeTuple{arity}(
{I}value,
{I}w,
{I}{indent_but_first_line(item_serializer_exprs_joined, I)})"""
    )

    result = Stripped(
        f"""\
SerializeElement(
{I}{xml_prop_name_literal},
{I}that.{prop_name},
{I}writer,
{I}{indent_but_first_line(content_serializer, I)});"""
    )

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        result = Stripped(
            f"""\
if (that.{prop_name} != null)
{{
{I}{indent_but_first_line(result, I)}
}}"""
        )

    return result


def _generate_serialize_property_as_content(prop: intermediate.Property) -> Stripped:
    """Generate the code to serialize the ``prop`` as content of an XML element."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    body = None  # type: Optional[Stripped]

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        body = _generate_serialize_primitive_property_as_content(prop=prop)
    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            body = _generate_serialize_enumeration_property_as_content(prop=prop)

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            body = _generate_serialize_primitive_property_as_content(prop=prop)

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if (
                isinstance(our_type, intermediate.AbstractClass)
                or len(our_type.concrete_descendants) > 0
            ):
                body = _generate_serialize_polymorphic_property_as_content(prop=prop)
            else:
                body = _generate_serialize_concrete_class_property_as_sequence(
                    prop=prop
                )

        elif isinstance(our_type, intermediate.NamedUnion):
            body = _generate_serialize_polymorphic_property_as_content(prop=prop)

        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        body = _generate_serialize_list_property_as_content(prop=prop)

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = _generate_serialize_tuple_property_as_content(prop=prop)

    else:
        assert_never(type_anno)

    return body


def _generate_class_to_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method to write ``cls`` as a sequence of properties as XML."""
    blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        body = _generate_serialize_property_as_content(prop=prop)
        blocks.append(body)

    interface_name = csharp_naming.interface_name(cls.name)
    method_name = csharp_naming.method_name(Identifier(f"{cls.name}_to_sequence"))

    writer = io.StringIO()

    if len(cls.properties) == 0:
        blocks.append(Stripped("// Intentionally empty."))

        writer.write(
            '[CodeAnalysis.SuppressMessage("ReSharper", "UnusedParameter.Local")]\n'
        )

    writer.write(
        f"""\
private void {method_name}(
{I}Aas.{interface_name} that,
{I}Xml.XmlWriter writer)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // private void {method_name}")

    return Stripped(writer.getvalue())


def _generate_visit_for_class(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method to write the ``cls`` as an XML element."""
    interface_name = csharp_naming.interface_name(cls.name)
    visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

    cls_to_sequence_name = csharp_naming.method_name(
        Identifier(f"{cls.name}_to_sequence")
    )

    xml_cls_name_literal = csharp_common.string_literal(naming.xml_class_name(cls.name))

    return Stripped(
        f"""\
public override void {visit_name}(
{I}Aas.{interface_name} that,
{I}Xml.XmlWriter writer)
{{
{I}writer.WriteStartElement(
{II}{xml_cls_name_literal},
{II}NS);
{I}this.{cls_to_sequence_name}(
{II}that,
{II}writer);
{I}writer.WriteEndElement();
}}"""
    )


def _generate_union_visit_helper() -> Stripped:
    """
    Generate a single ``Visit`` overload shared by every named union.

    A named union is not itself an ``Aas.IClass``, so it can not be dispatched
    by the inherited, ``IClass``-typed ``Visit`` overload. We add this
    overload, single-purpose and non-virtual, so that call sites can keep
    passing ``this.Visit`` around as a plain method group or calling it
    directly, regardless of whether the value at hand is a class instance or
    a named union.

    Dispatching over the common, non-generic ``Aas.IUnion`` (see ``generate()``
    in ``_generate_types.py``) instead of the union's own type means we need
    only this one overload for *all* named unions, not one per union.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
private void Visit(
{I}Aas.IUnion that,
{I}Xml.XmlWriter writer)
{{
{I}this.Visit(
{II}that.Underlying,
{II}writer);
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_visitor(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a visitor which serializes instances of the meta-model to XML."""
    errors = []  # type: List[Error]

    blocks = [_generate_serialize_element_helper()]  # type: List[Stripped]

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        blocks.extend(_generate_write_v_element_as_primitive_functions())
        for enumeration in symbol_table.enumerations:
            blocks.append(_generate_write_v_element_as_enumeration(enumeration))
        blocks.append(_generate_tuple_item_serializer_helpers())
        for arity in tuple_arities:
            blocks.append(_generate_serialize_tuple_helper(arity))

    # The abstract classes are directly dispatched by the transformer,
    # so we do not need to handle them separately.

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_keys = [
                specific_implementations.ImplementationKey(
                    f"Xmlization/VisitorWithWriter/visit_{cls.name}.cs"
                ),
                specific_implementations.ImplementationKey(
                    f"Xmlization/VisitorWithWriter/{cls.name}_to_sequence.cs"
                ),
            ]

            for implementation_key in implementation_keys:
                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            cls.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {cls.name}: {implementation_key}",
                        )
                    )
                    continue

                blocks.append(spec_impls[implementation_key])
        else:
            blocks.append(_generate_class_to_sequence(cls=cls))

            blocks.append(_generate_visit_for_class(cls=cls))

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_union_visit_helper())

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Serialize recursively the instances as XML elements.
/// </summary>
internal class VisitorWithWriter
{I}: Visitation.AbstractVisitorWithContext<Xml.XmlWriter>
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal class VisitorWithWriter")

    return Stripped(writer.getvalue()), None


def _generate_serialize(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the static serializer."""
    blocks = [
        Stripped(
            f"""\
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
private static readonly VisitorWithWriter _visitorWithWriter = (
{I}new VisitorWithWriter());"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize an instance of the meta-model to XML.
/// </summary>
public static void To(
{I}Aas.IClass that,
{I}Xml.XmlWriter writer)
{{
{I}Serialize._visitorWithWriter.Visit(
{II}that, writer);
}}"""
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    writer.write(
        """\
/// <summary>
/// Serialize instances of meta-model classes to XML.
/// </summary>
"""
    )

    first_cls = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )  # type: Optional[intermediate.ClassUnion]

    if first_cls is not None:
        cls_name: str
        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = csharp_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = csharp_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = csharp_naming.variable_name(Identifier("an_instance"))

        writer.write(
            f"""\
/// <example>
/// Here is an example how to serialize an instance of {cls_name}:
/// <code>
/// var {an_instance_variable} = new Aas.{cls_name}(
///     /* ... some constructor arguments ... */
/// );
/// var writer = new System.Xml.XmlWriter( /* some arguments */ );
/// Serialize.To(
/// {I}{an_instance_variable},
/// {I}writer);
/// </code>
/// </example>
"""
        )

    writer.write(
        """\
public static class Serialize
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public static class Serialize")

    return Stripped(writer.getvalue())


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    namespace: csharp_common.NamespaceIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code for XML de/serialization.

    The ``namespace`` defines the AAS C# namespace.
    """
    xmlization_blocks = []  # type: List[Stripped]

    errors = []  # type: List[Error]

    deserialize_impl_block, deserialize_impl_errors = _generate_deserialize_impl(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if deserialize_impl_errors is not None:
        errors.extend(deserialize_impl_errors)
    else:
        assert deserialize_impl_block is not None
        xmlization_blocks.append(deserialize_impl_block)

    xmlization_blocks.append(
        Stripped(
            f"""\
/// <summary>
/// Represent a critical error during the deserialization.
/// </summary>
public class Exception : System.Exception
{{
{I}public readonly string Path;
{I}public readonly string Cause;
{I}public Exception(string path, string cause)
{II}: base($"{{cause}} at: {{(path == "" ? "the beginning" : path)}}")
{I}{{
{II}Path = path;
{II}Cause = cause;
{I}}}
}}"""
        )
    )

    xmlization_blocks.append(_generate_deserialize(symbol_table=symbol_table))

    visitor_block, visitor_errors = _generate_visitor(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if visitor_errors is not None:
        errors.extend(visitor_errors)
    else:
        assert visitor_block is not None
        xmlization_blocks.append(visitor_block)

    if len(errors) > 0:
        return None, errors

    xmlization_blocks.append(_generate_serialize(symbol_table=symbol_table))

    xmlization_writer = io.StringIO()

    xml_namespace_literal = csharp_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    xmlization_writer.write(
        f"""\
namespace {namespace}
{{
{I}/// <summary>
{I}/// Provide de/serialization of meta-model classes to/from XML.
{I}/// </summary>
{I}public static class Xmlization
{I}{{
{II}/// The XML namespace of the meta-model
{II}[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
{II}public static readonly string NS = (
{III}{xml_namespace_literal});

"""
    )

    for i, xmlization_block in enumerate(xmlization_blocks):
        if i > 0:
            xmlization_writer.write("\n\n")

        xmlization_writer.write(textwrap.indent(xmlization_block, II))

    xmlization_writer.write(f"\n{I}}}  // public static class Xmlization")
    xmlization_writer.write(f"\n}}  // namespace {namespace}")

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using CodeAnalysis = System.Diagnostics.CodeAnalysis;
using Xml = System.Xml;

using System.Collections.Generic;  // can't alias"""
        )
    )

    # pylint: disable=line-too-long
    blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(xmlization_writer.getvalue()),
        csharp_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
