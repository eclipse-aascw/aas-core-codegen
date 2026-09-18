"""Generate code for XML de/serialization."""

import io
import textwrap
from typing import Tuple, Optional, List, Mapping, Set, Final

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


_CONTENT_READER_BY_PRIMITIVE: Final[
    Mapping[intermediate.PrimitiveType, Tuple[str, str, str]]
] = {
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
        f"ParseXsDouble(\n{II}reader.ReadContentAsString())",
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
_EMPTY_VALUE_BY_PRIMITIVE: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.STR: '""',
    intermediate.PrimitiveType.BYTEARRAY: "new byte[0]",
}


class _NeededCombinators:
    """Capture which of the shared combinators a model actually needs."""

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


def _needed_combinators(
    symbol_table: intermediate.SymbolTable,
) -> _NeededCombinators:
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
    """
    primitive_types = set()  # type: Set[intermediate.PrimitiveType]
    enumerations = False
    polymorphic = False
    lists = False
    v_elements = False

    def register(type_anno: intermediate.TypeAnnotationUnion, nested: bool) -> None:
        """
        Register what ``type_anno`` needs.

        ``nested`` tells whether the value is an item of a list or of
        a tuple. Everything but a class, an interface and a named union is
        then wrapped in a ``<v>`` element of its own, while those three
        de/serialize their own, self-describing element and hence need no
        dispatching combinator.
        """
        nonlocal enumerations, polymorphic, lists, v_elements

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

        else:
            assert_never(type_anno)

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            register(intermediate.beneath_optional(prop.type_annotation), nested=False)

    return _NeededCombinators(
        primitive_types=primitive_types,
        enumerations=enumerations,
        polymorphic=polymorphic,
        lists=lists,
        v_elements=v_elements,
    )


def _is_value_type(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether ``type_anno`` is represented as a C# value type.

    An optional of such a type is a ``System.Nullable``, so it is tested with
    ``HasValue`` and unwrapped with ``Value``, whereas an optional of
    a reference type is simply compared against ``null``.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return primitive_type in (
            intermediate.PrimitiveType.BOOL,
            intermediate.PrimitiveType.INT,
            intermediate.PrimitiveType.FLOAT,
        )

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    ):
        return True

    # NOTE (mristin):
    # A tuple is a ``System.ValueTuple``.
    return isinstance(type_anno, intermediate.TupleTypeAnnotation)


def _generate_as_text_combinators(
    needed: _NeededCombinators,
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
{IIIII}|| exception is System.Xml.XmlException
{IIIII}// NOTE (mristin):
{IIIII}// An integer beyond the range of a long leaves
{IIIII}// ReadContentAsLong as an OverflowException, which is neither
{IIIII}// of the two above, so it used to escape this filter and leave
{IIIII}// the de-serialization through an exception we never declared.
{IIIII}|| exception is System.OverflowException)
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

    if intermediate.PrimitiveType.FLOAT in primitive_types:
        result.append(
            Stripped(
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
/// <summary>
/// Match a run of the four characters which XML calls whitespace.
/// </summary>
private static readonly RegularExpressions.Regex WhitespaceRunRegex = (
{I}new RegularExpressions.Regex(
{II}@"[ \t\n\r]+",
{II}RegularExpressions.RegexOptions.Compiled));

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
private static double ParseXsDouble(string rawText)
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
{I}// The other readers of this class need no such thing -- XmlConvert,
{I}// which XmlReader.ReadContentAs* goes through, already collapses.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace
{I}string text = WhitespaceRunRegex.Replace(rawText, " ").Trim(' ');

{I}switch (text)
{I}{{
{II}case "INF":
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
    """
    Name the field holding the reader of the content of ``type_anno``.

    The moniker comes last, after an underscore, so that the name of a reader
    can never coincide with one of the ``...FromElement`` and
    ``...FromSequence`` fields: those are keyed by one of our symbols, and
    a symbol is named through
    :py:func:`aas_core_codegen.naming.capitalized_camel_case`, which never
    emits an underscore.
    """
    return Identifier(f"Read_{csharp_common.type_moniker(type_anno)}")


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
AsElement<Aas.{csharp_common.generate_type(type_anno)}>(
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


# NOTE (mristin):
# The generated code is indented by the emitter after the fact, so
# the generator has to compare against what is left of a line at the depth
# where the snippet will end up. That depth is spelled out as ``len(I) * N``
# at each comparison, since it differs from one snippet to the next: a field
# lands three levels in -- the namespace, ``Xmlization`` and the inner class
# -- and the arguments of a property five, or six beneath a condition.
#
# The name of a de/serializer field spells out the name of its type, so both
# occur twice in its declaration -- a list of a long class name alone runs to
# some 145 characters. Where a declaration does not fit, the type argument is
# broken out onto a line of its own.
_MAX_LINE_LENGTH: Final[int] = 100


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

        declaration = (
            f"internal static readonly ElementReader<Aas.{name}> {name}FromElement = ("
        )
        if len(declaration) + len(I) * 3 > _MAX_LINE_LENGTH:
            declaration = f"""\
internal static readonly ElementReader<
{I}Aas.{name}
> {name}FromElement = ("""

        result.append(
            Stripped(
                f"""\
/// <summary>
/// Read an instance of class {name} from its XML element.
/// </summary>
{declaration}
{I}AtElement<Aas.{name}>(
{II}{name}FromSequence, {xml_name_literal}));"""
            )
        )

    return result


def _content_types_in_initialization_order(
    symbol_table: intermediate.SymbolTable,
) -> List[intermediate.TypeAnnotationUnion]:
    """
    Collect the distinct types de/serialized as the content of an element.

    A field initializer reads the fields it composes, so the items of a list
    and of a tuple come before the container itself. A class, an interface
    and a named union are left out: they de/serialize their own,
    self-describing element and are referred to by a function, not by
    a field.

    The order and the de-duplication are the same for the reading and for
    the writing, so both field generators walk this one list. The moniker is
    the de-duplication key, which is sound only because it is injective --
    see :py:func:`aas_core_codegen.csharp.common.type_moniker`.
    """
    observed = set()  # type: Set[str]
    result = []  # type: List[intermediate.TypeAnnotationUnion]

    def register(type_anno: intermediate.TypeAnnotationUnion) -> None:
        """Register ``type_anno``, its items first."""
        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            item_type_annotations = [
                type_anno.items
            ]  # type: List[intermediate.TypeAnnotationUnion]
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_type_annotations = list(type_anno.items)
        else:
            item_type_annotations = []

        for item_type_anno in item_type_annotations:
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

        moniker = csharp_common.type_moniker(type_anno)
        if moniker in observed:
            return

        observed.add(moniker)
        result.append(type_anno)

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            register(intermediate.beneath_optional(prop.type_annotation))

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
    result = []  # type: List[Stripped]

    for type_anno in _content_types_in_initialization_order(symbol_table):
        csharp_type = csharp_common.generate_type(type_anno)
        initializer = _content_reader_initializer(type_anno)

        name = _content_reader_name(type_anno)

        declaration = f"private static readonly ContentReader<{csharp_type}> {name} = ("
        if len(declaration) + len(I) * 3 > _MAX_LINE_LENGTH:
            declaration = f"""\
private static readonly ContentReader<
{I}{csharp_type}
> {name} = ("""

        result.append(
            Stripped(
                f"""\
{declaration}
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

    # NOTE (mristin):
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

        # NOTE (mristin):
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

        # NOTE (mristin):
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

    needed_readers = _needed_combinators(symbol_table)
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

    # NOTE (mristin):
    # Enumerations are going to be directly deserialized using
    # ``Stringification``.

    # NOTE (mristin):
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

    # NOTE (mristin):
    # We use stringification for de-serialization of enumerations.

    # NOTE (mristin):
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


def _generate_content_writer_delegate() -> Stripped:
    """
    Generate the single delegate through which every value is written.

    Unlike the reading, the writing needs no distinction between the content
    of an element and the whole element: both are "write something where
    the writer already is", the same signature with nothing to report back.
    :py:func:`_generate_wrap_in_element_combinator` converts between the two.

    The type parameter is contravariant -- the dual of the covariance of
    the :py:class:`ElementReader` -- so that the one writer of
    an ``Aas.IClass`` serves wherever the writer of a more specific interface
    is expected.
    """
    return Stripped(
        f"""\
/// <summary>
/// Write <paramref name="that" /> where <paramref name="writer" /> already
/// is.
/// </summary>
/// <remarks>
/// Every value is written through this one shape, so that the writing can
/// be composed: a <c>Write*</c> combinator turns a stringification, a list
/// or a tuple of them into one of these, and a class's own
/// <c>...ToSequence</c> already is one.
///
/// There is deliberately no second delegate for a whole element: an element
/// differs from a content only in what it writes, never in its shape, and
/// <c>WrapInElement</c> converts between the two.
///
/// <typeparamref name="T" /> is contravariant, so that
/// <see cref="WriteIClass" /> can be used wherever the writer of a more
/// specific interface is expected.
/// </remarks>
/// <typeparam name="T">Type of the value to write</typeparam>
private delegate void ContentWriter<in T>(
{I}T that,
{I}Xml.XmlWriter writer);"""
    )


def _generate_write_element_helper() -> Stripped:
    """Generate the shared helper writing a value as a named XML element."""
    return Stripped(
        f"""\
/// <summary>
/// Write <paramref name="that" /> as an XML element named
/// <paramref name="elementName" />, its content written by
/// <paramref name="writeContent" />.
/// </summary>
/// <remarks>
/// An element is nothing but a start and an end tag around a content, so
/// there is no writer per property kind -- only the content differs, and it
/// has been composed once into a field.
/// </remarks>
/// <typeparam name="T">Type of the value to write</typeparam>
private static void WriteElement<T>(
{I}string elementName,
{I}T that,
{I}Xml.XmlWriter writer,
{I}ContentWriter<T> writeContent)
{{
{I}writer.WriteStartElement(elementName, NS);
{I}writeContent(that, writer);
{I}writer.WriteEndElement();
}}"""
    )


def _generate_wrap_in_element_combinator() -> Stripped:
    """
    Generate the partially applied form of ``WriteElement``.

    The doc comment spells out why this exists next to ``WriteElement``,
    since its handful of call sites make its payoff invisible: it is what
    lets a list and a tuple take a *single* item-writer type even though
    a class item writes its own element while a primitive item has to be
    wrapped in a positional one.
    """
    return Stripped(
        f"""\
/// <summary>
/// Bind <paramref name="elementName" /> and <paramref name="writeContent" />
/// to <see cref="WriteElement{{T}}" />, so that the result writes the whole
/// element, tags included.
/// </summary>
/// <remarks>
/// This is <see cref="WriteElement{{T}}" /> partially applied, which C# does
/// not give for free. It is used <em>only</em> for the <c>&lt;v&gt;</c>
/// element of a list item and for the positional <c>v1</c>, <c>v2</c>,
/// <c>...</c> elements of a tuple item. At a property, where the name and
/// the value are both at hand, <see cref="WriteElement{{T}}" /> is applied
/// and called in one go instead.
///
/// It is needed because <c>WriteList</c> and <c>WriteTupleN</c> each take
/// exactly one item-writer type: an item which is a class, an interface or
/// a named union writes its own element, whose name is known only at
/// run-time, whereas a primitive or an enumeration item has to be wrapped in
/// a fixed positional name. Were those two different types, a tuple mixing
/// them -- and they do mix, item by item -- would need a combinator per
/// combination of the two.
/// </remarks>
/// <typeparam name="T">Type of the value to write</typeparam>
private static ContentWriter<T> WrapInElement<T>(
{I}ContentWriter<T> writeContent,
{I}string elementName
{I})
{{
{I}return (that, writer) => WriteElement<T>(
{II}elementName, that, writer, writeContent);
}}"""
    )


def _generate_literal_stringifier_delegate() -> Stripped:
    """Generate the delegate which renders a literal of an enumeration as text."""
    return Stripped(
        """\
/// <summary>
/// Render the literal <paramref name="that" /> of <typeparamref name="T" />
/// as text.
/// </summary>
/// <remarks>
/// Every <c>Stringification.ToString</c> overload has this shape, so it can
/// be passed on directly -- which is what lets an enumeration be written by
/// one generated combinator instead of one per enumeration. The parameter is
/// nullable because the overloads are generated that way; a literal converts
/// to it implicitly.
/// </remarks>
/// <typeparam name="T">Enumeration whose literal is rendered</typeparam>
private delegate string? LiteralStringifier<T>(T? that) where T : struct;"""
    )


def _generate_write_enum_combinator() -> Stripped:
    """
    Generate the single combinator to write a literal of an enumeration.

    The rendering of the literal is passed in as a
    ``Stringification.ToString`` method group, so that this is generated once
    instead of once per enumeration. The name of the enumeration comes from
    ``typeof(T).Name`` for the same reason.
    """
    return Stripped(
        f"""\
/// <summary>
/// Write a literal of <typeparamref name="T" />, rendered with
/// <paramref name="stringifyLiteral" />.
/// </summary>
/// <typeparam name="T">Enumeration to write the literal of</typeparam>
private static ContentWriter<T> WriteEnum<T>(
{I}LiteralStringifier<T> stringifyLiteral
{I}) where T : struct
{{
{I}return (that, writer) =>
{I}{{
{II}writer.WriteValue(
{III}stringifyLiteral(that)
{IIII}?? throw new System.ArgumentException(
{IIIII}$"Invalid literal for the enumeration {{typeof(T).Name}}: " +
{IIIII}that.ToString()));
{I}}};
}}"""
    )


def _generate_write_list_combinator() -> Stripped:
    """
    Generate the combinator to write a list.

    The items are written by a plain :py:class:`ContentWriter`, which is what
    ``WrapInElement`` and :py:func:`_generate_dispatch_helpers` produce, so
    a list of anything -- a list of lists included -- composes without any
    further combinator.
    """
    return Stripped(
        f"""\
/// <summary>
/// Write the items of a list, each with <paramref name="writeItem" />.
/// </summary>
/// <remarks>
/// An empty list writes no items at all, which the reading sees as
/// a self-closing element.
/// </remarks>
/// <typeparam name="T">Type of a single list item</typeparam>
private static ContentWriter<List<T>> WriteList<T>(
{I}ContentWriter<T> writeItem
{I})
{{
{I}return (that, writer) =>
{I}{{
{II}foreach (var item in that)
{II}{{
{III}writeItem(item, writer);
{II}}}
{I}}};
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_write_tuple_combinator(arity: int) -> Stripped:
    """
    Generate the combinator writing a tuple of the given ``arity``.

    Each positional item is written by its own ``writeItemI``, which is
    expected to write its own start and end tags (if any). We can not reuse
    :py:func:`_generate_write_list_combinator` here, since a tuple is
    heterogeneous -- but the very same :py:class:`ContentWriter` serves both.

    The result is a plain ``ContentWriter``, so wrapping it in
    ``WrapInElement`` makes a tuple writable as an item of a list or of
    another tuple, arbitrarily deep.
    """
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(type_params)

    if arity == 1:
        tuple_type = f"System.ValueTuple<{type_params[0]}>"
    else:
        tuple_type = f"({type_params_joined})"

    params_joined = ",\n".join(
        f"ContentWriter<T{i}> writeItem{i}" for i in range(arity)
    )

    write_stmts_joined = "\n".join(
        f"writeItem{i}(that.Item{i + 1}, writer);" for i in range(arity)
    )

    return Stripped(
        f"""\
/// <summary>
/// Write a tuple of {arity} item(s), each with its own <c>writeItem*</c>.
/// </summary>
/// <remarks>
/// This is shared by everything of a tuple type of arity {arity} -- be it
/// a property, or a value nested in a list or in another tuple.
/// </remarks>
private static ContentWriter<{tuple_type}> WriteTuple{arity}<{type_params_joined}>(
{I}{indent_but_first_line(params_joined, I)}
{I})
{{
{I}return (that, writer) =>
{I}{{
{II}{indent_but_first_line(write_stmts_joined, II)}
{I}}};
}}"""
    )


def _generate_dispatch_helpers(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the writers which pick the element from the value itself.

    An abstract class, a concrete class with descendants and a named union
    are all written as *their own* element, whose name is known only at
    run-time. One virtual call answers that for all of them at once, which is
    why the writing needs neither a dispatcher per interface nor
    a combinator to invoke one -- the reading, which has to decide what to
    construct before it has read anything, needs both.

    ``WriteIClass`` is contravariant in its argument, so it doubles as
    the item writer of a list or of a tuple of any of them.
    """
    result = [
        Stripped(
            f"""\
/// <summary>
/// The one instance through which the writing is dispatched.
/// </summary>
/// <remarks>
/// The visitor carries no state -- the writer is passed in as the context --
/// so a single instance serves the whole program. No field initializer reads
/// it, only <see cref="WriteIClass" /> does, so it does not matter where
/// among the writers it is initialized.
/// </remarks>
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
private static readonly VisitorWithWriter _instance = (
{I}new VisitorWithWriter());"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Write <paramref name="that" /> as its own XML element.
/// </summary>
/// <remarks>
/// Which element that is, is decided by the run-time type of
/// <paramref name="that" />, so this one writer serves every abstract class
/// and every concrete class with descendants, as well as the item of a list
/// or of a tuple of any of them.
/// </remarks>
internal static void WriteIClass(
{I}Aas.IClass that,
{I}Xml.XmlWriter writer)
{{
{I}that.Accept(_instance, writer);
}}"""
        ),
    ]  # type: List[Stripped]

    if len(symbol_table.named_unions) > 0:
        result.append(
            Stripped(
                f"""\
/// <summary>
/// Write the underlying instance of <paramref name="that" /> as its own XML
/// element.
/// </summary>
/// <remarks>
/// A named union is not itself an <c>Aas.IClass</c>, so it can not be
/// dispatched by <see cref="WriteIClass" /> directly. Going through
/// the common, non-generic <c>Aas.IUnion</c> instead of the union's own
/// type means one writer for *all* the named unions, not one per union.
///
/// Should a named union ever be allowed to flatten a primitive or
/// an enumeration alternative, only this body has to change.
/// </remarks>
private static void WriteIUnion(
{I}Aas.IUnion that,
{I}Xml.XmlWriter writer)
{{
{I}WriteIClass(that.Underlying, writer);
}}"""
            )
        )

    return result


# NOTE (mristin):
# A ``byte[]`` is the only primitive which is not written by
# ``Xml.XmlWriter.WriteValue``, so the writing has to be spelled out per
# primitive -- unlike the reading, which goes through a conversion function.
_WRITE_VALUE_BY_PRIMITIVE: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.BOOL: "writer.WriteValue(that)",
    intermediate.PrimitiveType.INT: "writer.WriteValue(that)",
    intermediate.PrimitiveType.FLOAT: "writer.WriteValue(that)",
    intermediate.PrimitiveType.STR: "writer.WriteValue(that)",
    intermediate.PrimitiveType.BYTEARRAY: "writer.WriteBase64(that, 0, that.Length)",
}
assert all(
    primitive_type in _WRITE_VALUE_BY_PRIMITIVE
    for primitive_type in intermediate.PrimitiveType
)


def _content_writer_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Name the field holding the writer of the content of ``type_anno``.

    The moniker comes last, after an underscore, for the same reason as in
    :py:func:`_content_reader_name`.
    """
    return Identifier(f"Write_{csharp_common.type_moniker(type_anno)}")


def _item_writer_expr(
    type_anno: intermediate.TypeAnnotationUnion, v_name_literal: str
) -> Stripped:
    """
    Generate the expression writing a single item of a list or of a tuple.

    A class, an interface or a named union writes its own, self-describing
    element, whereas everything else is wrapped in a ``<v>`` element whose
    content is written by the very same writer as a property of that type.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.NamedUnion):
            return Stripped("WriteIUnion")

        if isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            return Stripped("WriteIClass")

    return Stripped(
        f"""\
WrapInElement(
{I}{_content_writer_name(type_anno)}, {v_name_literal})"""
    )


def _content_writer_initializer(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """Generate the expression initializing the writer of ``type_anno``."""
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return Stripped(
            f"(that, writer) => {_WRITE_VALUE_BY_PRIMITIVE[primitive_type]}"
        )

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            enum_name = csharp_naming.enum_name(our_type.name)
            return Stripped(
                f"""\
WriteEnum<Aas.{enum_name}>(
{I}Stringification.ToString)"""
            )

        if isinstance(our_type, intermediate.NamedUnion):
            return Stripped("WriteIUnion")

        assert isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ), f"Unexpected our type for a content writer: {our_type}"

        if (
            isinstance(our_type, intermediate.AbstractClass)
            or len(our_type.concrete_descendants) > 0
        ):
            return Stripped("WriteIClass")

        # NOTE (mristin):
        # A concrete class without any descendant writes its own sequence,
        # which is already a ``ContentWriter``.
        return Stripped(
            csharp_naming.method_name(Identifier(f"{our_type.name}_to_sequence"))
        )

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_type = csharp_common.generate_type(type_anno.items)
        item_writer = _item_writer_expr(type_anno.items, '"v"')
        return Stripped(
            f"""\
WriteList<{item_type}>(
{I}{indent_but_first_line(item_writer, I)})"""
        )

    assert isinstance(type_anno, intermediate.TupleTypeAnnotation)

    item_types = ", ".join(
        csharp_common.generate_type(item) for item in type_anno.items
    )
    item_writers = ",\n".join(
        _item_writer_expr(item, csharp_common.string_literal(f"v{i + 1}"))
        for i, item in enumerate(type_anno.items)
    )
    return Stripped(
        f"""\
WriteTuple{len(type_anno.items)}<{item_types}>(
{I}{indent_but_first_line(item_writers, I)})"""
    )


def _generate_content_writer_fields(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the fields holding one writer per distinct property type.

    The writers are composed once, at the initialization of the class,
    instead of at every property of every instance -- composing them at
    the call site would allocate a closure on every single write.
    """
    result = []  # type: List[Stripped]

    for type_anno in _content_types_in_initialization_order(symbol_table):
        csharp_type = csharp_common.generate_type(type_anno)
        initializer = _content_writer_initializer(type_anno)

        name = _content_writer_name(type_anno)

        declaration = f"private static readonly ContentWriter<{csharp_type}> {name} = ("
        if len(declaration) + len(I) * 3 > _MAX_LINE_LENGTH:
            declaration = f"""\
private static readonly ContentWriter<
{I}{csharp_type}
> {name} = ("""

        result.append(
            Stripped(
                f"""\
{declaration}
{I}{indent_but_first_line(initializer, I)});"""
            )
        )

    return result


@require(lambda prop, cls: id(prop) in cls.property_id_set)
def _generate_serialize_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the snippet to serialize the property ``prop``.

    Every property kind is written by the very same call -- only the content
    writer differs, and it has been composed once into a field (see
    :py:func:`_generate_content_writer_fields`).
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    if isinstance(type_anno, intermediate.ListTypeAnnotation) and not isinstance(
        type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
    ):
        return None, Error(
            prop.parsed.node,
            f"(mristin) We only handle the XML serialization of lists of "
            f"atomic values, but you want to generate the code for a list of "
            f"type {type_anno}. Please contact the developers if you need "
            f"this feature.",
        )

    prop_name = csharp_naming.property_name(prop.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    value_expr = f"that.{prop_name}"
    condition = None  # type: Optional[str]

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        if _is_value_type(type_anno):
            condition = f"that.{prop_name}.HasValue"
            value_expr = f"that.{prop_name}.Value"
        else:
            condition = f"that.{prop_name} != null"

    arguments = [
        xml_prop_name_literal,
        value_expr,
        "writer",
        _content_writer_name(type_anno),
    ]

    # NOTE (mristin):
    # The arguments go on a single line, so that a property costs five lines
    # at most -- but not at the price of an unreadable one, so a property
    # whose names do not fit gets an argument per line instead.
    indentation = len(I) * 5
    if condition is not None:
        indentation += len(I)

    arguments_joined = ", ".join(arguments)
    if indentation + len(arguments_joined) + len(");") > _MAX_LINE_LENGTH:
        arguments_joined = ",\n".join(arguments)

    result = Stripped(
        f"""\
WriteElement(
{I}{indent_but_first_line(arguments_joined, I)});"""
    )

    if condition is not None:
        result = Stripped(
            f"""\
if ({condition})
{{
{I}{indent_but_first_line(result, I)}
}}"""
        )

    return result, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_class_to_sequence(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the method to write ``cls`` as a sequence of properties as XML."""
    blocks = []  # type: List[Stripped]
    errors = []  # type: List[Error]

    for prop in cls.properties:
        block, error = _generate_serialize_property(prop=prop, cls=cls)
        if error is not None:
            errors.append(error)
            continue

        assert block is not None
        blocks.append(block)

    if len(errors) > 0:
        return None, errors

    method_name = csharp_naming.method_name(Identifier(f"{cls.name}_to_sequence"))
    interface_name = csharp_naming.interface_name(cls.name)

    writer = io.StringIO()

    if len(cls.properties) == 0:
        blocks.append(Stripped("// Intentionally empty."))

        writer.write(
            '[CodeAnalysis.SuppressMessage("ReSharper", "UnusedParameter.Local")]\n'
        )

    writer.write(
        f"""\
private static void {method_name}(
{I}Aas.{interface_name} that,
{I}Xml.XmlWriter writer)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // private static void {method_name}")

    return Stripped(writer.getvalue()), None


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
{I}{cls_to_sequence_name}(
{II}that,
{II}writer);
{I}writer.WriteEndElement();
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_visitor(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a visitor which serializes instances of the meta-model to XML."""
    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    needed = _needed_combinators(symbol_table)

    if any(len(cls.properties) > 0 for cls in symbol_table.concrete_classes):
        blocks.append(_generate_content_writer_delegate())
        blocks.append(_generate_write_element_helper())

    if needed.v_elements:
        blocks.append(_generate_wrap_in_element_combinator())

    if needed.enumerations:
        blocks.append(_generate_literal_stringifier_delegate())
        blocks.append(_generate_write_enum_combinator())

    if needed.lists:
        blocks.append(_generate_write_list_combinator())

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_write_tuple_combinator(arity))

    blocks.extend(_generate_dispatch_helpers(symbol_table=symbol_table))

    # NOTE (mristin):
    # The writers are composed once, here, rather than at every property of
    # every instance -- composing them at the call site would allocate
    # a closure on every single write.
    #
    # A field initializer reads the fields it composes, so a writer of
    # a list or of a tuple has to be declared after the writers of its items.
    # A class's writer, in contrast, is a method group, which imposes no
    # order at all.
    blocks.extend(_generate_content_writer_fields(symbol_table=symbol_table))

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
            block, generation_errors = _generate_class_to_sequence(cls=cls)
            if generation_errors is not None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"Failed to generate the XML serialization code "
                        f"for the class {cls.name}",
                        generation_errors,
                    )
                )
            else:
                assert block is not None
                blocks.append(block)

            blocks.append(_generate_visit_for_class(cls=cls))

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
/// <summary>
/// Serialize an instance of the meta-model to XML.
/// </summary>
public static void To(
{I}Aas.IClass that,
{I}Xml.XmlWriter writer)
{{
{I}VisitorWithWriter.WriteIClass(
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
using Globalization = System.Globalization;
using RegularExpressions = System.Text.RegularExpressions;
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
