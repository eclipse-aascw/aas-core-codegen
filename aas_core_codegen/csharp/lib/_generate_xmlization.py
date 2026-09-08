"""Generate code for XML de/serialization."""

import io
import textwrap
from typing import Tuple, Optional, List

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


def _generate_read_v_element() -> Stripped:
    return Stripped(
        f"""\
/// <summary>
/// Consume a start element named <paramref name="expectedName" /> from
/// the reader and return whether it was a self-closing (empty) element.
/// </summary>
private static bool ReadVElement(
{I}Xml.XmlReader reader,
{I}string expectedName,
{I}out Reporting.Error? error
{I})
{{
{I}if (reader.EOF) {{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> element, but got an end-of-file.");
{II}return false;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.Element)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> start element, " +
{III}$"but got the node of type {{reader.NodeType}} " +
{III}$"with the value {{reader.Value}}");
{II}return false;
{I}}}

{I}string elementName = TryElementName(
{II}reader, out error);
{I}if (error != null)
{I}{{
{II}return false;
{I}}}
{I}if (elementName != expectedName)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a <{{expectedName}}> element, " +
{III}$"but got an element {{elementName}}");
{II}return false;
{I}}}

{I}bool isEmpty = reader.IsEmptyElement;

{I}// We can consume now the start element.
{I}reader.Read();
{I}return isEmpty;
}}"""
    )


def _generate_read_v_end_element() -> Stripped:
    return Stripped(
        f"""\
/// <summary>
/// Consume an end element named <paramref name="expectedName" /> from
/// the reader.
/// </summary>
private static void ReadVEndElement(
{I}Xml.XmlReader reader,
{I}string expectedName,
{I}out Reporting.Error? error
{I})
{{
{I}if (reader.EOF) {{
{II}error = new Reporting.Error(
{III}$"Expected a </{{expectedName}}> element, but got an end-of-file.");
{II}return;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.EndElement)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a </{{expectedName}}> end element, " +
{III}$"but got the node of type {{reader.NodeType}} " +
{III}$"with the value {{reader.Value}}");
{II}return;
{I}}}

{I}string elementName = TryElementName(
{II}reader, out error);
{I}if (error != null)
{I}{{
{II}return;
{I}}}
{I}if (elementName != expectedName)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a </{{expectedName}}> element, " +
{III}$"but got an end element {{elementName}}");
{II}return;
{I}}}

{I}// We can consume now the end element.
{I}reader.Read();
}}"""
    )


def _generate_read_v_element_as_primitive_functions() -> List[Stripped]:
    result = []  # type: List[Stripped]

    for function_name, result_type, deserialization_expr in (
        ("ReadVElementAsBoolean", "bool", "reader.ReadContentAsBoolean()"),
        ("ReadVElementAsLong", "long", "reader.ReadContentAsLong()"),
        ("ReadVElementAsDouble", "double", "reader.ReadContentAsDouble()"),
    ):
        result.append(
            Stripped(
                f"""\
/// <summary>
/// Read the content of a <c>&lt;v&gt;</c> element
/// and parse it as {result_type}.
/// </summary>
private static {result_type}? {function_name}(
{I}Xml.XmlReader reader,
{I}string elementName,
{I}out Reporting.Error? error
{I})
{{
{I}bool isEmptyVElement = ReadVElement(reader, elementName, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}{result_type}? result = null;
{I}if (!isEmptyVElement)
{I}{{
{II}if (reader.EOF)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML content representing {result_type}, " +
{IIII}"but reached the end-of-file");
{III}return null;
{II}}}

{II}try
{II}{{
{III}result = {deserialization_expr};
{II}}}
{II}catch (System.Exception exception)
{IIII}when (exception is System.FormatException
{IIIII}|| exception is System.Xml.XmlException)
{II}{{
{III}error = new Reporting.Error(
{IIII}$"The content could not be de-serialized as {result_type}: {{exception}}");
{III}return null;
{II}}}

{II}ReadVEndElement(reader, elementName, out error);
{II}if (error != null)
{II}{{
{III}return null;
{II}}}
{I}}}

{I}if (result == null)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Unexpected result null when there is no error.");
{I}}}
{I}return result;
}}"""
            )
        )

    # A self-closing <v /> represents an empty string.
    result.append(
        Stripped(
            f"""\
/// <summary>
/// Read the content of a <c>&lt;v&gt;</c> element
/// and parse it as string.
/// </summary>
private static string? ReadVElementAsString(
{I}Xml.XmlReader reader,
{I}string elementName,
{I}out Reporting.Error? error
{I})
{{
{I}bool isEmptyVElement = ReadVElement(reader, elementName, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}string result;
{I}if (!isEmptyVElement)
{I}{{
{II}if (reader.EOF)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML content representing string, " +
{IIII}"but reached the end-of-file");
{III}return null;
{II}}}

{II}try
{II}{{
{III}result = reader.ReadContentAsString();
{II}}}
{II}catch (System.FormatException exception)
{II}{{
{III}error = new Reporting.Error(
{IIII}$"The content could not be de-serialized as string: {{exception}}");
{III}return null;
{II}}}

{II}ReadVEndElement(reader, elementName, out error);
{II}if (error != null)
{II}{{
{III}return null;
{II}}}
{I}}}
{I}else
{I}{{
{II}result = "";
{I}}}

{I}return result;
}}"""
        )
    )

    result.append(
        Stripped(
            f"""\
/// <summary>
/// Read a <c>&lt;v&gt;</c> element as base64-encoded bytes.
/// </summary>
private static byte[]? ReadVElementAsBytes(
{I}Xml.XmlReader reader,
{I}string elementName,
{I}out Reporting.Error? error
{I})
{{
{I}bool isEmptyVElement = ReadVElement(reader, elementName, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}byte[]? result;
{I}if (isEmptyVElement)
{I}{{
{II}result = new byte[0];
{I}}}
{I}else
{I}{{
{II}if (reader.EOF)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML content with base64-encoded bytes, " +
{IIII}"but reached the end-of-file");
{III}return null;
{II}}}

{II}try
{II}{{
{III}result = ReadWholeContentAsBase64(reader);
{II}}}
{II}catch (System.FormatException exception)
{II}{{
{III}error = new Reporting.Error(
{IIII}"The content could not be de-serialized as " +
{IIII}$"base64-encoded bytes: {{exception}}");
{III}return null;
{II}}}

{II}ReadVEndElement(reader, elementName, out error);
{II}if (error != null)
{II}{{
{III}return null;
{II}}}
{I}}}

{I}return result;
}}"""
        )
    )

    return result


def _generate_parse_list_of_class_helpers() -> Stripped:
    """Generate the generic helper to de-serialize a list of reference-type items."""
    return Stripped(
        f"""\
/// <summary>
/// Read a single list item, positioned at its start element.
/// </summary>
/// <typeparam name="T">Type of the parsed item</typeparam>
private delegate T? ClassItemDeserializer<T>(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error
{I}) where T : class;

/// <summary>
/// Parse a sequence of list items with <paramref name="deserializeItem" />,
/// stopping (without consuming) at the first non-element node.
/// </summary>
/// <remarks>
/// This is shared by all the list-typed properties whose items are
/// de-serialized into a reference type (<em>e.g.</em>, a string, a byte
/// array or a class instance).
/// </remarks>
/// <typeparam name="T">Type of a single list item</typeparam>
private static List<T> ParseListOfClass<T>(
{I}Xml.XmlReader reader,
{I}ClassItemDeserializer<T> deserializeItem,
{I}out Reporting.Error? error
{I}) where T : class
{{
{I}error = null;
{I}List<T> result = new List<T>();

{I}SkipNoneWhitespaceAndComments(reader);

{I}int index = 0;
{I}while (reader.NodeType == Xml.XmlNodeType.Element)
{I}{{
{II}T? item = deserializeItem(reader, out error);
{II}if (error != null)
{II}{{
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(
{IIIII}index));
{III}return result;
{II}}}

{II}result.Add(
{III}item
{IIII}?? throw new System.InvalidOperationException(
{IIIII}"Unexpected item null when error null"));

{II}index++;
{II}SkipNoneWhitespaceAndComments(reader);
{I}}}

{I}return result;
}}"""
    )


def _generate_parse_list_of_struct_helpers() -> Stripped:
    """Generate the generic helper to de-serialize a list of value-type items."""
    return Stripped(
        f"""\
/// <summary>
/// Read a single list item, positioned at its start element.
/// </summary>
/// <typeparam name="T">Type of the parsed item</typeparam>
private delegate T? StructItemDeserializer<T>(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error
{I}) where T : struct;

/// <summary>
/// Parse a sequence of list items with <paramref name="deserializeItem" />,
/// stopping (without consuming) at the first non-element node.
/// </summary>
/// <remarks>
/// This is shared by all the list-typed properties whose items are
/// de-serialized into a value type (<em>e.g.</em>, a bool, a number or
/// an enumeration literal).
/// </remarks>
/// <typeparam name="T">Type of a single list item</typeparam>
private static List<T> ParseListOfStruct<T>(
{I}Xml.XmlReader reader,
{I}StructItemDeserializer<T> deserializeItem,
{I}out Reporting.Error? error
{I}) where T : struct
{{
{I}error = null;
{I}List<T> result = new List<T>();

{I}SkipNoneWhitespaceAndComments(reader);

{I}int index = 0;
{I}while (reader.NodeType == Xml.XmlNodeType.Element)
{I}{{
{II}T? item = deserializeItem(reader, out error);
{II}if (error != null)
{II}{{
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(
{IIIII}index));
{III}return result;
{II}}}

{II}result.Add(
{III}item
{IIII}?? throw new System.InvalidOperationException(
{IIIII}"Unexpected item null when error null"));

{II}index++;
{II}SkipNoneWhitespaceAndComments(reader);
{I}}}

{I}return result;
}}"""
    )


def _generate_tuple_item_reader_delegate() -> Stripped:
    """Generate the delegate and adapters shared by all the generic tuple parsers."""
    return Stripped(
        f"""\
/// <summary>
/// Read a single tuple item from the current position of the reader.
/// </summary>
/// <remarks>
/// A tuple-typed property is parsed by <c>ParseTupleN</c> (see
/// <see cref="ParseTuple2{{T0, T1}}" /> for the arity-2 case, *etc.*), one
/// function shared by *every* tuple-typed property of a given arity,
/// regardless of which mix of reference and value types appears at each
/// position. If <c>ParseTupleN</c> demanded the same
/// <c>ClassItemDeserializer&lt;T&gt;</c>/<c>StructItemDeserializer&lt;T&gt;</c>
/// shape already used for list items (a nullable return, constrained to
/// <c>class</c> or <c>struct</c>), its own type parameters would need that
/// constraint fixed once per position -- which breaks the moment two
/// different tuple-typed properties of the same arity mix reference and
/// value types differently at the same position (<em>e.g.</em>,
/// <c>(string, long)</c> at one property and <c>(long, string)</c> at
/// another could not share one <c>ParseTuple2</c>).
///
/// A single unconstrained <c>T? Method(Xml.XmlReader reader, out Reporting.Error? error)</c>
/// shape shared by both reference and value types does not work around this
/// either: for a value type, an unconstrained <c>T?</c> erases to plain
/// <c>T</c> (not <c>System.Nullable&lt;T&gt;</c>), so a method returning
/// <c>long?</c> can not even be assigned to it.
///
/// <c>TupleItemDeserializer&lt;T&gt;</c> sidesteps the class/struct split
/// entirely by using an <c>out</c> parameter for the value instead of a
/// nullable return, at the cost of needing an adapter --
/// <see cref="AsTupleItemDeserializer{{T}}(ClassItemDeserializer{{T}})" /> --
/// to convert an existing item reader (such as a <c>ReadVElementAsString</c>
/// call or a class's own <c>...FromElement</c> method group) into one.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private delegate void TupleItemDeserializer<T>(
{I}Xml.XmlReader reader,
{I}out T value,
{I}out Reporting.Error? error);

/// <summary>
/// Adapt <paramref name="deserializeItem" /> -- a reference-type item reader
/// as used for list-typed properties -- into a <see cref="TupleItemDeserializer{{T}}" />
/// for use in a tuple-typed property.
/// </summary>
/// <remarks>
/// See the remarks on <see cref="TupleItemDeserializer{{T}}" /> for why this
/// adapter -- rather than a shared constraint on <c>ParseTupleN</c> itself --
/// is necessary. This overload and its <c>StructItemDeserializer&lt;T&gt;</c>
/// counterpart are dispatched on the parameter's delegate type alone, so a
/// caller never has to pick between them by name; each encapsulates the
/// "unwrap the nullable result, or propagate the error" check exactly once,
/// mirroring how <see cref="ParseListOfClass{{T}}" />/
/// <see cref="ParseListOfStruct{{T}}" /> encapsulate the very same check
/// once for lists instead of repeating it at every call site.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private static TupleItemDeserializer<T> AsTupleItemDeserializer<T>(
{I}ClassItemDeserializer<T> deserializeItem
{I}) where T : class
{{
{I}return (
{II}Xml.XmlReader reader,
{II}out T value,
{II}out Reporting.Error? error) =>
{II}{{
{III}T? parsed = deserializeItem(reader, out error);
{III}if (error != null)
{III}{{
{IIII}value = default!;
{IIII}return;
{III}}}
{III}value = parsed
{IIII}?? throw new System.InvalidOperationException(
{IIIII}"Unexpected result null when error is null");
{II}}};
}}

/// <summary>
/// Adapt <paramref name="deserializeItem" /> -- a value-type item reader
/// as used for list-typed properties -- into a <see cref="TupleItemDeserializer{{T}}" />
/// for use in a tuple-typed property.
/// </summary>
/// <remarks>
/// See <see cref="AsTupleItemDeserializer{{T}}(ClassItemDeserializer{{T}})" />
/// for why this adapter is necessary.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private static TupleItemDeserializer<T> AsTupleItemDeserializer<T>(
{I}StructItemDeserializer<T> deserializeItem
{I}) where T : struct
{{
{I}return (
{II}Xml.XmlReader reader,
{II}out T value,
{II}out Reporting.Error? error) =>
{II}{{
{III}T? parsed = deserializeItem(reader, out error);
{III}if (error != null)
{III}{{
{IIII}value = default;
{IIII}return;
{III}}}
{III}value = parsed
{IIII}?? throw new System.InvalidOperationException(
{IIIII}"Unexpected result null when error is null");
{II}}};
}}

/// <summary>
/// Read a single tuple item wrapped in a reference-type-valued named
/// element such as <c>&lt;v1&gt;</c>, <c>&lt;v2&gt;</c>, *etc.*
/// </summary>
/// <remarks>
/// This is the counterpart of <see cref="ClassItemDeserializer{{T}}" /> for
/// item readers that additionally need the expected element name passed in
/// -- such as <see cref="ReadVElementAsString" /> -- since a tuple item, unlike
/// a list item, is wrapped in a positional element name instead of always
/// the fixed <c>&lt;v&gt;</c>.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private delegate T? NamedClassItemDeserializer<T>(
{I}Xml.XmlReader reader,
{I}string elementName,
{I}out Reporting.Error? error
{I}) where T : class;

/// <summary>
/// Read a single tuple item wrapped in a value-type-valued named element
/// such as <c>&lt;v1&gt;</c>, <c>&lt;v2&gt;</c>, *etc.*
/// </summary>
/// <remarks>
/// See the remarks on <see cref="NamedClassItemDeserializer{{T}}" />.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private delegate T? NamedStructItemDeserializer<T>(
{I}Xml.XmlReader reader,
{I}string elementName,
{I}out Reporting.Error? error
{I}) where T : struct;

/// <summary>
/// Adapt <paramref name="deserializeItem" /> -- a reference-type item reader
/// which additionally expects the element name, such as
/// <see cref="ReadVElementAsString" /> -- into a
/// <see cref="TupleItemDeserializer{{T}}" /> bound to
/// <paramref name="elementName" />, for use in a tuple-typed property.
/// </summary>
/// <remarks>
/// See the remarks on <see cref="TupleItemDeserializer{{T}}" /> for why an
/// adapter is necessary in the first place. This overload additionally
/// closes over <paramref name="elementName" /> (<em>e.g.</em>, <c>"v1"</c>),
/// so that the tuple-typed property itself does not need to spell out a
/// lambda just to bind the positional element name.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private static TupleItemDeserializer<T> AsTupleItemDeserializer<T>(
{I}NamedClassItemDeserializer<T> deserializeItem,
{I}string elementName
{I}) where T : class
{{
{I}return (
{II}Xml.XmlReader reader,
{II}out T value,
{II}out Reporting.Error? error) =>
{II}{{
{III}T? parsed = deserializeItem(reader, elementName, out error);
{III}if (error != null)
{III}{{
{IIII}value = default!;
{IIII}return;
{III}}}
{III}value = parsed
{IIII}?? throw new System.InvalidOperationException(
{IIIII}"Unexpected result null when error is null");
{II}}};
}}

/// <summary>
/// Adapt <paramref name="deserializeItem" /> -- a value-type item reader
/// which additionally expects the element name, such as
/// <see cref="ReadVElementAsLong" /> -- into a
/// <see cref="TupleItemDeserializer{{T}}" /> bound to
/// <paramref name="elementName" />, for use in a tuple-typed property.
/// </summary>
/// <remarks>
/// See <see cref="AsTupleItemDeserializer{{T}}(NamedClassItemDeserializer{{T}}, string)" />
/// for why this adapter is necessary.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private static TupleItemDeserializer<T> AsTupleItemDeserializer<T>(
{I}NamedStructItemDeserializer<T> deserializeItem,
{I}string elementName
{I}) where T : struct
{{
{I}return (
{II}Xml.XmlReader reader,
{II}out T value,
{II}out Reporting.Error? error) =>
{II}{{
{III}T? parsed = deserializeItem(reader, elementName, out error);
{III}if (error != null)
{III}{{
{IIII}value = default;
{IIII}return;
{III}}}
{III}value = parsed
{IIII}?? throw new System.InvalidOperationException(
{IIIII}"Unexpected result null when error is null");
{II}}};
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_parse_tuple_helper(arity: int) -> Stripped:
    """
    Generate a generic function to parse a tuple of the given ``arity``.

    Each positional item is read by its own ``deserializeItemI`` callback,
    which is expected to have already consumed its own start and end tags (if
    any). We can not reuse :py:func:`_generate_parse_list_of_class_helpers`/
    :py:func:`_generate_parse_list_of_struct_helpers` here since a tuple is
    heterogeneous -- see :py:func:`TupleItemDeserializer` for why the item
    delegate uses an ``out`` parameter instead of a nullable return value.
    """
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(type_params)

    if arity == 1:
        tuple_type = f"System.ValueTuple<{type_params[0]}>"
    else:
        tuple_type = f"({type_params_joined})"

    params_joined = ",\n".join(
        f"TupleItemDeserializer<T{i}> deserializeItem{i}" for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_block = Stripped(
            f"""\
deserializeItem{i}(reader, out T{i} item{i}, out error);
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

    function_name = f"ParseTuple{arity}"

    return Stripped(
        f"""\
/// <summary>
/// Parse a tuple of {arity} item(s) from the current position
/// of <paramref name="reader" />.
/// </summary>
/// <remarks>
/// This is shared by all the tuple-typed properties of arity {arity}.
/// </remarks>
private static {tuple_type} {function_name}<{type_params_joined}>(
{I}Xml.XmlReader reader,
{I}{indent_but_first_line(params_joined, I)},
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}{indent_but_first_line(item_blocks_joined, I)}

{I}return {indent_but_first_line(return_expr, I)};
}}"""
    )


def _generate_read_v_element_as_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the function to de-serialize a literal from a ``<v>``."""
    enum_name = csharp_naming.enum_name(enumeration.name)
    return Stripped(
        f"""\
/// <summary>
/// Read a <c>&lt;v&gt;</c> and parse its content as a literal of
/// <see cref="Aas.{enum_name}"/>.
/// </summary>
private static Aas.{enum_name}? ReadVElementAs{enum_name}(
{I}Xml.XmlReader reader,
{I}string elementName,
{I}out Reporting.Error? error
{I})
{{
{I}string? text = ReadVElementAsString(reader, elementName, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}if (text == null)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Text must not be null if error is null.");
{I}}}

{I}Aas.{enum_name}? result = Stringification.{enum_name}FromString(
{II}text);

{I}if (result == null)
{I}{{
{II}error = new Reporting.Error(
{III}"The text could not be parsed as enumeration literal " +
{III}$"of {enum_name}: {{result}}");
{II}return null;
{I}}}

{I}return result;
}}"""
    )


def _generate_deserialize_primitive_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` of primitive type."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    a_type = intermediate.try_primitive_type(type_anno)
    assert a_type is not None, f"Unexpected type annotation: {prop.type_annotation}"

    deserialization_expr: str
    if a_type is intermediate.PrimitiveType.BOOL:
        deserialization_expr = "reader.ReadContentAsBoolean()"
    elif a_type is intermediate.PrimitiveType.INT:
        deserialization_expr = "reader.ReadContentAsLong()"
    elif a_type is intermediate.PrimitiveType.FLOAT:
        deserialization_expr = "reader.ReadContentAsDouble()"
    elif a_type is intermediate.PrimitiveType.STR:
        deserialization_expr = "reader.ReadContentAsString()"
    elif a_type is intermediate.PrimitiveType.BYTEARRAY:
        deserialization_expr = f"""\
DeserializeImplementation.ReadWholeContentAsBase64(
{I}reader)"""
    else:
        assert_never(a_type)

    target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))

    prop_name = csharp_naming.property_name(prop.name)
    cls_name = csharp_naming.class_name(cls.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    if a_type is intermediate.PrimitiveType.STR:
        empty_handling_body = Stripped(f'{target_var} = "";')
    else:
        empty_handling_body = Stripped(
            f"""\
error = new Reporting.Error(
{I}"The property {prop_name} of an instance of class {cls_name} " +
{I}"can not be de-serialized from a self-closing element " +
{I}"since it needs content");
error.PrependSegment(
{I}new Reporting.NameSegment(
{II}{xml_prop_name_literal}));
return null;"""
        )

    return Stripped(
        f"""\
if (isEmptyProperty)
{{
{I}{indent_but_first_line(empty_handling_body, I)}
}}
else
{{
{I}if (reader.EOF)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected an XML content representing " +
{III}"the property {prop_name} of an instance of class {cls_name}, " +
{III}"but reached the end-of-file");
{II}return null;
{I}}}

{I}try
{I}{{
{II}{target_var} = {indent_but_first_line(deserialization_expr, I)};
{I}}}
{I}catch (System.Exception exception)
{III}when (exception is System.FormatException
{IIII}|| exception is System.Xml.XmlException)
{I}{{
{II}error = new Reporting.Error(
{III}"The property {prop_name} of an instance of class {cls_name} " +
{III}$"could not be de-serialized: {{exception.Message}}");
{II}error.PrependSegment(
{III}new Reporting.NameSegment(
{IIII}{xml_prop_name_literal}));
{II}return null;
{I}}}
}}"""
    )


def _generate_deserialize_enumeration_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` as an enum."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.OurTypeAnnotation)

    our_type = type_anno.our_type
    assert isinstance(our_type, intermediate.Enumeration)

    target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))
    text_var = csharp_naming.variable_name(Identifier(f"text_{prop.name}"))

    prop_name = csharp_naming.property_name(prop.name)
    cls_name = csharp_naming.class_name(cls.name)
    enum_name = csharp_naming.enum_name(our_type.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    return Stripped(
        f"""\
if (isEmptyProperty)
{{
{I}error = new Reporting.Error(
{II}"The property {prop_name} of an instance of class {cls_name} " +
{II}"can not be de-serialized from a self-closing element " +
{II}"since it needs content");
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return null;
}}

{I}if (reader.EOF)
{{
{II}error = new Reporting.Error(
{III}"Expected an XML content representing " +
{III}"the property {prop_name} of an instance of class {cls_name}, " +
{III}"but reached the end-of-file");
{II}return null;
}}

string {text_var};
try
{{
{I}{text_var} = reader.ReadContentAsString();
}}
catch (System.FormatException exception)
{{
{I}error = new Reporting.Error(
{II}"The property {prop_name} of an instance of class {cls_name} " +
{II}$"could not be de-serialized as a string: {{exception}}");
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return null;
}}

{target_var} = Stringification.{enum_name}FromString(
{I}{text_var});

if ({target_var} == null)
{{
{I}error = new Reporting.Error(
{II}"The property {prop_name} of an instance of class {cls_name} " +
{II}"could not be de-serialized from an unexpected enumeration literal: " +
{II}{text_var});
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return null;
}}"""
    )


def _generate_deserialize_interface_property(
    prop: intermediate.Property,
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` as an interface."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.OurTypeAnnotation)

    our_type = type_anno.our_type
    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    )
    assert our_type.interface is not None

    prop_name = csharp_naming.property_name(prop.name)
    cls_name = csharp_naming.class_name(cls.name)

    interface_name = csharp_naming.interface_name(our_type.interface.name)

    target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    return Stripped(
        f"""\
if (isEmptyProperty)
{{
{I}error = new Reporting.Error(
{II}$"Expected an XML element within the element {{elementName}} representing " +
{II}"the property {prop_name} of an instance of class {cls_name}, " +
{II}"but encountered a self-closing element {{elementName}}");
{I}return null;
}}

// We need to skip the whitespace here in order to be able to look ahead
// the discriminator element shortly.
SkipNoneWhitespaceAndComments(reader);

if (reader.EOF)
{{
{I}error = new Reporting.Error(
{II}$"Expected an XML element within the element {{elementName}} representing " +
{II}"the property {prop_name} of an instance of class {cls_name}, " +
{II}"but reached the end-of-file");
{I}return null;
}}

// Try to look ahead the discriminator name;
// we need this name only for the error reporting below.
// {interface_name}FromElement will perform more sophisticated
// checks.
string? discriminatorElementName = null;
if (reader.NodeType == Xml.XmlNodeType.Element)
{{
{I}discriminatorElementName = reader.LocalName;
}}

{target_var} = {interface_name}FromElement(
{I}reader, out error);

if (error != null)
{{
{I}if (discriminatorElementName != null)
{I}{{
{II}error.PrependSegment(
{III}new Reporting.NameSegment(
{IIII}discriminatorElementName));
{I}}}

{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return null;
}}"""
    )


def _generate_deserialize_cls_property(prop: intermediate.Property) -> Stripped:
    """Generate the snippet to deserialize a property ``prop`` as a concrete class."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.OurTypeAnnotation)

    our_type = type_anno.our_type
    assert isinstance(our_type, intermediate.ConcreteClass)

    target_cls_name = csharp_naming.class_name(our_type.name)

    target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)

    return Stripped(
        f"""\
{target_var} = {target_cls_name}FromSequence(
{I}reader, isEmptyProperty, out error);

if (error != null)
{{
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return null;
}}"""
    )


def _generate_deserialize_list_property(prop: intermediate.Property) -> Stripped:
    """Generate the code to de-serialize a property ``prop`` as a list."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.ListTypeAnnotation), "Pre-condition"

    deserialize_method: Stripped
    is_v_element: bool
    is_value_type: bool

    primitive_type = intermediate.try_primitive_type(type_anno.items)

    if primitive_type is not None or (
        isinstance(type_anno.items, intermediate.OurTypeAnnotation)
        and isinstance(type_anno.items.our_type, intermediate.Enumeration)
    ):
        is_v_element = True

        if primitive_type is not None:
            if primitive_type is intermediate.PrimitiveType.BOOL:
                deserialize_method = Stripped("ReadVElementAsBoolean")
                is_value_type = True
            elif primitive_type is intermediate.PrimitiveType.INT:
                deserialize_method = Stripped("ReadVElementAsLong")
                is_value_type = True
            elif primitive_type is intermediate.PrimitiveType.FLOAT:
                deserialize_method = Stripped("ReadVElementAsDouble")
                is_value_type = True
            elif primitive_type is intermediate.PrimitiveType.STR:
                deserialize_method = Stripped("ReadVElementAsString")
                is_value_type = False
            elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                deserialize_method = Stripped("ReadVElementAsBytes")
                is_value_type = False
            else:
                assert_never(primitive_type)
        else:
            assert isinstance(
                type_anno.items, intermediate.OurTypeAnnotation
            ) and isinstance(type_anno.items.our_type, intermediate.Enumeration)

            enum_name = csharp_naming.enum_name(type_anno.items.our_type.name)
            deserialize_method = Stripped(f"ReadVElementAs{enum_name}")
            is_value_type = True

    elif isinstance(type_anno.items, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.items.our_type,
        (intermediate.AbstractClass, intermediate.ConcreteClass),
    ):
        is_v_element = False
        is_value_type = False

        if (
            isinstance(type_anno.items.our_type, intermediate.AbstractClass)
            or len(type_anno.items.our_type.concrete_descendants) > 0
        ):
            deserialize_method = Stripped(
                f"{csharp_naming.interface_name(type_anno.items.our_type.name)}FromElement"
            )
        else:
            deserialize_method = Stripped(
                f"{csharp_naming.class_name(type_anno.items.our_type.name)}FromElement"
            )
    else:
        raise NotImplementedError(
            f"(mristin) We only handle XML de/serialization of lists containing atomic "
            f"values, but you want to generate the code for a list of type {type_anno}. "
            f"Please contact the developers if you need this feature."
        )

    xml_prop_name = prop.xml_name
    xml_prop_name_literal = csharp_common.string_literal(xml_prop_name)

    target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))

    item_type = csharp_common.generate_type(type_anno.items)

    parse_list_function = "ParseListOfStruct" if is_value_type else "ParseListOfClass"

    # NOTE (mristin):
    # A method group such as ``FooFromElement`` already matches the expected
    # ``(Xml.XmlReader, out Reporting.Error?) -> T?`` signature of the item
    # deserializer, so we can pass it on directly. A ``<v>`` element, on the
    # other hand, needs its fixed local name "v" bound in a lambda.
    item_deserializer = (
        Stripped(
            f"""\
(Xml.XmlReader itemReader, out Reporting.Error? itemError) => {deserialize_method}(
{I}itemReader, "v", out itemError)"""
        )
        if is_v_element
        else deserialize_method
    )

    body_for_non_empty_property = Stripped(
        f"""\
{target_var} = {parse_list_function}<{item_type}>(
{I}reader,
{I}{indent_but_first_line(item_deserializer, I)},
{I}out error);

if (error != null)
{{
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return null;
}}"""
    )

    return Stripped(
        f"""\
{target_var} = new List<{item_type}>();

if (!isEmptyProperty)
{{
{I}{indent_but_first_line(body_for_non_empty_property, I)}
}}"""
    )


def _generate_deserialize_tuple_property(prop: intermediate.Property) -> Stripped:
    """Generate the code to de-serialize a property ``prop`` as a tuple."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.TupleTypeAnnotation), "Pre-condition"

    prop_name = csharp_naming.property_name(prop.name)
    xml_prop_name_literal = csharp_common.string_literal(prop.xml_name)
    target_var = csharp_naming.variable_name(Identifier(f"the_{prop.name}"))

    item_deserializer_exprs = []  # type: List[Stripped]

    for i, item_type_anno in enumerate(type_anno.items):
        primitive_type = intermediate.try_primitive_type(item_type_anno)

        if primitive_type is not None:
            v_name_literal = csharp_common.string_literal(f"v{i + 1}")

            method: str
            if primitive_type is intermediate.PrimitiveType.BOOL:
                method = "ReadVElementAsBoolean"
            elif primitive_type is intermediate.PrimitiveType.INT:
                method = "ReadVElementAsLong"
            elif primitive_type is intermediate.PrimitiveType.FLOAT:
                method = "ReadVElementAsDouble"
            elif primitive_type is intermediate.PrimitiveType.STR:
                method = "ReadVElementAsString"
            elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                method = "ReadVElementAsBytes"
            else:
                assert_never(primitive_type)

            item_deserializer_exprs.append(
                Stripped(f"AsTupleItemDeserializer({method}, {v_name_literal})")
            )
        elif isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
            item_type_anno.our_type, intermediate.Enumeration
        ):
            enum_name = csharp_naming.enum_name(item_type_anno.our_type.name)
            v_name_literal = csharp_common.string_literal(f"v{i + 1}")

            item_deserializer_exprs.append(
                Stripped(
                    f"AsTupleItemDeserializer(ReadVElementAs{enum_name}, {v_name_literal})"
                )
            )
        else:
            # NOTE (mristin):
            # A tuple item can only be a primitive value, a constrained primitive,
            # an enumeration literal or a class instance; see
            # intermediate._translate._verify_only_simple_type_patterns.
            assert isinstance(item_type_anno, intermediate.OurTypeAnnotation) and (
                isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                )
            ), (
                f"Unexpected tuple item type {item_type_anno} at index {i} "
                f"for the property {prop.name!r}"
            )

            our_type = item_type_anno.our_type
            if (
                isinstance(our_type, intermediate.AbstractClass)
                or len(our_type.concrete_descendants) > 0
            ):
                deserialize_method_name = (
                    f"{csharp_naming.interface_name(our_type.name)}FromElement"
                )
            else:
                deserialize_method_name = (
                    f"{csharp_naming.class_name(our_type.name)}FromElement"
                )

            item_deserializer_exprs.append(
                Stripped(f"AsTupleItemDeserializer({deserialize_method_name})")
            )

    item_deserializer_exprs_joined = ",\n".join(item_deserializer_exprs)

    arity = len(type_anno.items)

    return Stripped(
        f"""\
if (isEmptyProperty)
{{
{I}error = new Reporting.Error(
{II}"The property {prop_name} can not be de-serialized " +
{II}"from a self-closing element since it needs content");
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return null;
}}

SkipNoneWhitespaceAndComments(reader);

{target_var} = ParseTuple{arity}(
{I}reader,
{I}{indent_but_first_line(item_deserializer_exprs_joined, I)},
{I}out error);
if (error != null)
{{
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{xml_prop_name_literal}));
{I}return null;
}}"""
    )


@require(lambda prop, cls: id(prop) in cls.property_id_set)
def _generate_deserialize_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the snippet to deserialize the property ``prop`` from the content."""
    blocks = []  # type: List[Stripped]

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        blocks.append(_generate_deserialize_primitive_property(prop=prop, cls=cls))
    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(
                _generate_deserialize_enumeration_property(prop=prop, cls=cls)
            )
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin, 2022-04-13):
            # The constrained primitives are only verified, but not represented as
            # separate classes in the XSD.
            blocks.append(_generate_deserialize_primitive_property(prop=prop, cls=cls))
        elif isinstance(
            our_type, (intermediate.ConcreteClass, intermediate.AbstractClass)
        ):
            if (
                isinstance(our_type, intermediate.AbstractClass)
                or len(our_type.concrete_descendants) > 0
            ):
                blocks.append(
                    _generate_deserialize_interface_property(prop=prop, cls=cls)
                )
            else:
                blocks.append(_generate_deserialize_cls_property(prop=prop))
        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        blocks.append(_generate_deserialize_list_property(prop=prop))

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        blocks.append(_generate_deserialize_tuple_property(prop=prop))

    else:
        assert_never(type_anno)

    return Stripped("\n\n".join(blocks)), None


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
}}  // internal static Aas.{name}? {name}FromSequence"""
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
{I}return null;
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
        case_blocks.append(
            Stripped(
                f"""\
case {xml_prop_name_literal}:
{{
{I}{indent_but_first_line(case_body, I)}
{I}break;
}}"""
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
{I}return null;"""
        )
    )

    switch_body = "\n".join(case_blocks)

    blocks_for_non_empty.append(
        Stripped(
            f"""\
while (true)
{{
{I}SkipNoneWhitespaceAndComments(reader);

{I}if (reader.NodeType == Xml.XmlNodeType.EndElement || reader.EOF)
{I}{{
{II}break;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.Element)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected an XML start element representing " +
{III}"a property of an instance of class {name}, " +
{III}$"but got the node of type {{reader.NodeType}} " +
{III}$"with the value {{reader.Value}}");
{II}return null;
{I}}}

{I}string elementName = TryElementName(
{II}reader, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}

{I}bool isEmptyProperty = reader.IsEmptyElement;

{I}// Skip the expected element
{I}reader.Read();

{I}switch (elementName)
{I}{{
{II}{indent_but_first_line(switch_body, II)}
{I}}}

{I}SkipNoneWhitespaceAndComments(reader);

{I}if (!isEmptyProperty)
{I}{{
{II}// Read the end element

{II}if (reader.EOF)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML end element to conclude a property of class {name} " +
{IIII}$"with the element name {{elementName}}, " +
{IIII}"but got the end-of-file.");
{III}return null;
{II}}}
{II}if (reader.NodeType != Xml.XmlNodeType.EndElement)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML end element to conclude a property of class {name} " +
{IIII}$"with the element name {{elementName}}, " +
{IIII}$"but got the node of type {{reader.NodeType}} " +
{IIII}$"with the value {{reader.Value}}");
{III}return null;
{II}}}

{II}string endElementName = TryElementName(
{III}reader, out error);
{II}if (error != null)
{II}{{
{III}return null;
{II}}}

{II}if (endElementName != elementName)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected an XML end element to conclude a property of class {name} " +
{IIII}$"with the element name {{elementName}}, " +
{IIII}$"but got the end element with the name {{reader.Name}}");
{III}return null;
{II}}}
{II}// Skip the expected end element
{II}reader.Read();
{I}}}
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
{I}return null;
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
internal static Aas.{name}? {name}FromSequence(
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


def _generate_read_start_element_of_class() -> Stripped:
    """Generate the shared helper to read the opening tag of a class instance."""
    return Stripped(
        f"""\
/// <summary>
/// Read the opening tag of an XML element representing an instance of
/// <paramref name="className" />, without consuming its content.
/// </summary>
/// <remarks>
/// This is shared by the de-serialization of every concrete class from
/// an XML element.
/// </remarks>
private static string ReadStartElementOfClass(
{I}Xml.XmlReader reader,
{I}string className,
{I}out bool isEmptyElement,
{I}out Reporting.Error? error
{I})
{{
{I}error = null;
{I}isEmptyElement = false;

{I}SkipNoneWhitespaceAndComments(reader);

{I}if (reader.EOF)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected an XML element representing an instance of class {{className}}, " +
{III}"but reached the end-of-file");
{II}return "";
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.Element)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected an XML element representing an instance of class {{className}}, " +
{III}$"but got a node of type {{reader.NodeType}} " +
{III}$"with value {{reader.Value}}");
{II}return "";
{I}}}

{I}string elementName = TryElementName(
{II}reader, out error);
{I}if (error != null)
{I}{{
{II}return "";
{I}}}

{I}isEmptyElement = reader.IsEmptyElement;
{I}return elementName;
}}"""
    )


def _generate_consume_close_tag() -> Stripped:
    """Generate the shared helper to consume the closing tag of an XML element."""
    return Stripped(
        f"""\
/// <summary>
/// Consume the closing tag matching <paramref name="expectedElementName" />,
/// unless <paramref name="isEmptyElement" /> indicates that the element was
/// self-closing and thus has no separate closing tag to consume.
/// </summary>
/// <remarks>
/// This is shared by the de-serialization of every concrete class from
/// an XML element.
/// </remarks>
private static void ConsumeCloseTag(
{I}Xml.XmlReader reader,
{I}string expectedElementName,
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
{III}$"Expected a closing element </{{expectedElementName}}>, " +
{III}"but reached the end-of-file");
{II}return;
{I}}}

{I}if (reader.NodeType != Xml.XmlNodeType.EndElement)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a closing element </{{expectedElementName}}>, " +
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

{I}if (endElementName != expectedElementName)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a closing element </{{expectedElementName}}>, " +
{III}$"but got a closing element </{{endElementName}}>");
{II}return;
{I}}}

{I}// Skip the end element
{I}reader.Read();
}}"""
    )


def _generate_deserialize_impl_concrete_cls_from_element(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the function to de-serialize a concrete ``cls`` from an XML element."""
    name = csharp_naming.class_name(cls.name)
    xml_name = naming.xml_class_name(cls.name)
    xml_name_literal = csharp_common.string_literal(xml_name)

    # NOTE (mristin, 2022-06-21):
    # We need to propagate nullability. Otherwise, InspectCode complains.
    result_nullability = "?" if len(cls.constructor.arguments) > 0 else ""

    body = Stripped(
        f"""\
error = null;

string elementName = ReadStartElementOfClass(
{I}reader, {csharp_common.string_literal(name)}, out bool isEmptyElement, out error);
if (error != null)
{{
{I}return null;
}}

if (elementName != {xml_name_literal})
{{
{I}error = new Reporting.Error(
{II}"Expected an element representing an instance of class {name} " +
{II}$"with element name {xml_name}, but got: {{elementName}}");
{I}return null;
}}

// Skip the element node and go to the content
reader.Read();

Aas.{name}{result_nullability} result = (
{I}{name}FromSequence(
{II}reader, isEmptyElement, out error));
if (error != null)
{{
{I}return null;
}}

ConsumeCloseTag(
{I}reader,
{I}elementName,
{I}isEmptyElement,
{I}out error);
if (error != null)
{{
{I}return null;
}}

return result;"""
    )

    return Stripped(
        f"""\
/// <summary>
/// Deserialize an instance of class {name} from an XML element.
/// </summary>
internal static Aas.{name}? {name}FromElement(
{I}Xml.XmlReader reader,
{I}out Reporting.Error? error)
{{
{I}{indent_but_first_line(body, I)}
}}  // internal static Aas.{name}? {name}FromElement"""
    )


def _generate_deserialize_impl_interface_from_element(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate the function to de-serialize an ``interface`` from an XML element."""
    name = csharp_naming.interface_name(interface.name)

    blocks = [
        Stripped(
            f"""\
error = null;

SkipNoneWhitespaceAndComments(reader);

if (reader.EOF)
{{
{I}error = new Reporting.Error(
{II}"Expected an XML element, but reached end-of-file");
{I}return null;
}}

if (reader.NodeType != Xml.XmlNodeType.Element)
{{
{I}error = new Reporting.Error(
{II}"Expected an XML element, " +
{II}$"but got a node of type {{reader.NodeType}} " +
{II}$"with value {{reader.Value}}");
{I}return null;
}}"""
        )
    ]  # type: List[Stripped]

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
{I}return null;"""
        )
    )

    switch_writer = io.StringIO()
    switch_writer.write(
        f"""\
string elementName = TryElementName(
{I}reader, out error);
if (error != null)
{{
{I}return null;
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
internal static Aas.{name}? {name}FromElement(
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
        _generate_read_v_element(),
        _generate_read_v_end_element(),
        *_generate_read_v_element_as_primitive_functions(),
        _generate_parse_list_of_class_helpers(),
        _generate_parse_list_of_struct_helpers(),
        _generate_read_start_element_of_class(),
        _generate_consume_close_tag(),
    ]  # type: List[Stripped]

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        blocks.append(_generate_tuple_item_reader_delegate())
        for arity in tuple_arities:
            blocks.append(_generate_parse_tuple_helper(arity))

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_read_v_element_as_enumeration(enumeration))

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

            if isinstance(cls, intermediate.ConcreteClass):
                blocks.append(
                    _generate_deserialize_impl_concrete_cls_from_element(cls=cls)
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

{I}Aas.{name}? result = (
{II}DeserializeImplementation.{name}FromElement(
{III}reader,
{III}out Reporting.Error? error));
{I}if (error != null)
{I}{{
{II}throw new Xmlization.Exception(
{III}Reporting.GenerateRelativeXPath(error.PathSegments),
{III}error.Cause);
{I}}}
{I}return result
{II}?? throw new System.InvalidOperationException(
{III}"Unexpected output null when error is null");
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
/// interface, list) as they all wrap their content in exactly the same way.
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

    These mirror :py:func:`_generate_read_v_element_as_primitive_functions`
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
/// <see cref="ElementContentSerializer{{T}}" /> per item. A class item's own
/// <c>Visit</c> method already has that shape (writing its own element
/// directly, with no wrapping needed), so it can be passed on unchanged.
/// A primitive or enumeration item, on the other hand, first needs to be
/// wrapped in its own positional <c>v1</c>, <c>v2</c>, *etc.* element -- this
/// adapter closes over the element name so that a tuple-typed property does
/// not need to spell out that wrapping (start element/write value/end
/// element) at every item, mirroring how
/// <see cref="AsTupleItemDeserializer{{T}}(NamedClassItemDeserializer{{T}}, string)" />
/// avoids the equivalent on the read side.
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


def _generate_serialize_interface_property_as_content(
    prop: intermediate.Property,
) -> Stripped:
    """Generate the serialization of an interface as XML content."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    # fmt: off
    assert (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and (
                    isinstance(type_anno.our_type, intermediate.AbstractClass)
                    or (
                            isinstance(type_anno.our_type, intermediate.ConcreteClass)
                            and len(type_anno.our_type.concrete_descendants) > 0
                    )
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
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
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
        else:
            # NOTE (mristin):
            # A tuple item can only be a primitive value, a constrained primitive,
            # an enumeration literal or a class instance; see
            # intermediate._translate._verify_only_simple_type_patterns.
            assert isinstance(item_type_anno, intermediate.OurTypeAnnotation) and (
                isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                )
            ), (
                f"Unexpected tuple item type {item_type_anno} at index {i} "
                f"for the property {prop.name!r}"
            )

            # NOTE (mristin):
            # ``this.Visit`` already writes the item's own element directly
            # (with no positional wrapping needed), and its
            # ``(IClass, Xml.XmlWriter)`` signature is contravariantly
            # compatible with ``ElementContentSerializer<T>`` for any more
            # specific interface ``T``, so we can pass it on unchanged.
            item_serializer_exprs.append(Stripped("this.Visit"))

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
                body = _generate_serialize_interface_property_as_content(prop=prop)
            else:
                body = _generate_serialize_concrete_class_property_as_sequence(
                    prop=prop
                )

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
