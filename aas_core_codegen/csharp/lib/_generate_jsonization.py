"""Generate code for JSON de/serialization."""

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


def _generate_from_method_for_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the deserialization method for an enumeration."""
    name = csharp_naming.enum_name(identifier=enumeration.name)

    message_literal = csharp_common.string_literal(
        f"Not a valid JSON representation of {name}"
    )

    return Stripped(
        f"""\
/// <summary>
/// Deserialize the enumeration {name} from the <paramref name="node" />.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
internal static Aas.{name}? {name}From(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
{I}error = null;
{I}string? text = DeserializeImplementation.StringFrom(
{II}node, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}
{I}if (text == null)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Unexpected text null if error null");
{I}}}
{I}Aas.{name}? result = Stringification.{name}FromString(text);
{I}if (result == null)
{I}{{
{II}error = new Reporting.Error(
{III}{message_literal});
{I}}}
{I}return result;
}}  // internal static {name}From"""
    )


def _generate_from_method_for_interface(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate the deserialization method for an interface."""
    name = csharp_naming.interface_name(interface.name)

    blocks = [
        Stripped("error = null;"),
        Stripped(
            f"""\
var obj = node as Nodes.JsonObject;
if (obj == null)
{{
{I}error = new Reporting.Error(
{II}$"Expected Nodes.JsonObject, but got {{node.GetType()}}");
{I}return null;
}}"""
        ),
        Stripped(
            f"""\
Nodes.JsonNode? modelTypeNode = obj["modelType"];
if (modelTypeNode == null)
{{
{I}error = new Reporting.Error(
{II}"Expected a model type, but none is present");
{I}return null;
}}
Nodes.JsonValue? modelTypeValue = modelTypeNode as Nodes.JsonValue;
if (modelTypeValue == null)
{{
{I}error = new Reporting.Error(
{II}"Expected JsonValue, " +
{II}$"but got {{modelTypeNode.GetType()}}");
{I}return null;
}}
modelTypeValue.TryGetValue<string>(out string? modelType);
if (modelType == null)
{{
{I}error = new Reporting.Error(
{II}"Expected a string, " +
{II}$"but the conversion failed from {{modelTypeValue}}");
{I}return null;
}}"""
        ),
    ]  # type: List[Stripped]

    # region Write the switch block

    switch_writer = io.StringIO()
    switch_writer.write(
        """\
switch (modelType)
{
"""
    )

    for implementer in interface.implementers:
        model_type = naming.json_model_type(implementer.name)
        implementer_name = csharp_naming.class_name(implementer.name)
        switch_writer.write(
            f"""\
{I}case {csharp_common.string_literal(model_type)}:
{II}return {implementer_name}From(
{III}node, out error);
"""
        )

    switch_writer.write(
        f"""\
{I}default:
{II}error = new Reporting.Error(
{III}$"Unexpected model type for {name}: {{modelType}}");
{II}return null;
}}"""
    )
    blocks.append(Stripped(switch_writer.getvalue()))

    # endregion

    writer = io.StringIO()

    writer.write(
        f"""\
/// <summary>
/// Deserialize an instance of {name} by dispatching
/// based on <c>modelType</c> property of the <paramref name="node" />.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
public static Aas.{name}? {name}From(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // public static Aas.{name} {name}From")

    return Stripped(writer.getvalue())


def _generate_from_method_for_named_union(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """Generate the deserialization method for a named union."""
    name = csharp_naming.class_name(named_union.name)

    blocks = [
        Stripped("error = null;"),
        Stripped(
            f"""\
var obj = node as Nodes.JsonObject;
if (obj == null)
{{
{I}error = new Reporting.Error(
{II}$"Expected Nodes.JsonObject, but got {{node.GetType()}}");
{I}return null;
}}"""
        ),
    ]  # type: List[Stripped]

    implementers_with_model_type = []  # type: List[intermediate.ConcreteClass]
    implementers_without_model_type = []  # type: List[intermediate.ConcreteClass]
    for implementer in named_union.implementers:
        if implementer.serialization.with_model_type:
            implementers_with_model_type.append(implementer)
        else:
            implementers_without_model_type.append(implementer)

    # region Dispatch by model type

    if len(implementers_with_model_type) > 0:
        switch_writer = io.StringIO()
        switch_writer.write(
            f"""\
Nodes.JsonNode? modelTypeNode = obj["modelType"];
if (modelTypeNode != null)
{{
{I}Nodes.JsonValue? modelTypeValue = modelTypeNode as Nodes.JsonValue;
{I}if (modelTypeValue == null)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected JsonValue, " +
{III}$"but got {{modelTypeNode.GetType()}}");
{II}return null;
{I}}}
{I}modelTypeValue.TryGetValue<string>(out string? modelType);
{I}if (modelType == null)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a string, " +
{III}$"but the conversion failed from {{modelTypeValue}}");
{II}return null;
{I}}}

{I}switch (modelType)
{I}{{
"""
        )

        for implementer in implementers_with_model_type:
            model_type = naming.json_model_type(implementer.name)
            implementer_name = csharp_naming.class_name(implementer.name)
            from_method_name = csharp_naming.method_name(
                Identifier(f"from_{implementer.name}")
            )

            case_stmt = Stripped(
                f"""\
case {csharp_common.string_literal(model_type)}:
{{
{I}Aas.{implementer_name}? instance = {implementer_name}From(
{II}node, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}
{I}if (instance == null)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Unexpected instance null when error null");
{I}}}
{I}return Aas.{name}.{from_method_name}(instance);
}}"""
            )
            switch_writer.write(textwrap.indent(case_stmt, II))
            switch_writer.write("\n")

        switch_writer.write(
            f"""\
{II}default:
{III}error = new Reporting.Error(
{IIII}$"Unexpected model type for the union {name}: {{modelType}}");
{III}return null;
{I}}}
}}"""
        )

        blocks.append(Stripped(switch_writer.getvalue()))

    # endregion

    # region Structural dispatch

    for implementer in implementers_without_model_type:
        implementer_name = csharp_naming.class_name(implementer.name)
        from_method_name = csharp_naming.method_name(
            Identifier(f"from_{implementer.name}")
        )

        required_props = [
            prop
            for prop in implementer.properties
            if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        ]
        assert len(required_props) > 0, (
            f"Expected at least one required property for the structurally "
            f"dispatched implementer {implementer.name!r} of "
            f"the named union {named_union.name!r}; this should have already "
            f"been verified in "
            f"intermediate._translate._verify_named_unions_are_dispatchable_in_json"
        )

        condition = " &&\n".join(
            f"obj.ContainsKey({csharp_common.string_literal(prop.json_name)})"
            for prop in required_props
        )

        blocks.append(
            Stripped(
                f"""\
if ({indent_but_first_line(condition, I)})
{{
{I}Aas.{implementer_name}? instance = {implementer_name}From(
{II}node, out error);
{I}if (error != null)
{I}{{
{II}return null;
{I}}}
{I}if (instance == null)
{I}{{
{II}throw new System.InvalidOperationException(
{III}"Unexpected instance null when error null");
{I}}}
{I}return Aas.{name}.{from_method_name}(instance);
}}"""
            )
        )

    # endregion

    blocks.append(
        Stripped(
            f"""\
error = new Reporting.Error(
{I}"Could not determine the concrete type of the union {name} " +
{I}"from the given JSON object; none of its implementers matched");
return null;"""
        )
    )

    writer = io.StringIO()

    writer.write(
        f"""\
/// <summary>
/// Deserialize an instance of {name} by dispatching
/// based on <c>modelType</c> or the properties present in
/// <paramref name="node" />.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
public static Aas.{name}? {name}From(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // public static Aas.{name} {name}From")

    return Stripped(writer.getvalue())


_PARSE_METHOD_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "DeserializeImplementation.BoolFrom",
    intermediate.PrimitiveType.INT: "DeserializeImplementation.LongFrom",
    intermediate.PrimitiveType.FLOAT: "DeserializeImplementation.DoubleFrom",
    intermediate.PrimitiveType.STR: "DeserializeImplementation.StringFrom",
    intermediate.PrimitiveType.BYTEARRAY: "DeserializeImplementation.BytesFrom",
}
assert all(
    literal in _PARSE_METHOD_BY_PRIMITIVE_TYPE for literal in intermediate.PrimitiveType
)


def _parse_method_for_atomic_value(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """Determine the parse method for deserializing an atomic non-optional value."""
    parse_method: str

    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        parse_method = _PARSE_METHOD_BY_PRIMITIVE_TYPE[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type
        if isinstance(our_type, intermediate.Enumeration):
            enum_name = csharp_naming.enum_name(our_type.name)
            parse_method = f"DeserializeImplementation.{enum_name}From"

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            parse_method = _PARSE_METHOD_BY_PRIMITIVE_TYPE[our_type.constrainee]

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if our_type.interface is not None:
                interface_name = csharp_naming.interface_name(our_type.interface.name)
                parse_method = f"DeserializeImplementation.{interface_name}From"
            else:
                cls_name = csharp_naming.class_name(our_type.name)
                parse_method = f"DeserializeImplementation.{cls_name}From"

        elif isinstance(our_type, intermediate.NamedUnion):
            union_name = csharp_naming.class_name(our_type.name)
            parse_method = f"DeserializeImplementation.{union_name}From"

        else:
            assert_never(our_type)
    else:
        assert_never(type_annotation)

    return Stripped(parse_method)


def _generate_parse_array_of_class_helper() -> Stripped:
    """Generate the generic helper to de-serialize an array of reference-type items."""
    return Stripped(
        f"""\
/// <summary>
/// Read a single array item.
/// </summary>
/// <typeparam name="T">Type of the parsed item</typeparam>
private delegate T? JsonClassItemDeserializer<T>(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error
{I}) where T : class;

/// <summary>
/// Parse every item of <paramref name="array" /> with
/// <paramref name="deserializeItem" />.
/// </summary>
/// <remarks>
/// This is shared by all the list-typed constructor arguments whose items are
/// de-serialized into a reference type (<em>e.g.</em>, a string, a byte array
/// or a class instance).
/// </remarks>
/// <typeparam name="T">Type of a single array item</typeparam>
private static List<T> ParseArrayOfClass<T>(
{I}Nodes.JsonArray array,
{I}JsonClassItemDeserializer<T> deserializeItem,
{I}out Reporting.Error? error
{I}) where T : class
{{
{I}error = null;
{I}List<T> result = new List<T>(array.Count);

{I}int index = 0;
{I}foreach (Nodes.JsonNode? item in array)
{I}{{
{II}if (item == null)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected a non-null item, but got a null");
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(
{IIIII}index));
{III}return result;
{II}}}

{II}T? parsedItem = deserializeItem(
{III}item ?? throw new System.InvalidOperationException(),
{III}out error);
{II}if (error != null)
{II}{{
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(
{IIIII}index));
{III}return result;
{II}}}

{II}result.Add(
{III}parsedItem
{IIII}?? throw new System.InvalidOperationException(
{IIIII}"Unexpected result null when error is null"));

{II}index++;
{I}}}

{I}return result;
}}"""
    )


def _generate_parse_array_of_struct_helper() -> Stripped:
    """Generate the generic helper to de-serialize an array of value-type items."""
    return Stripped(
        f"""\
/// <summary>
/// Read a single array item.
/// </summary>
/// <typeparam name="T">Type of the parsed item</typeparam>
private delegate T? JsonStructItemDeserializer<T>(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error
{I}) where T : struct;

/// <summary>
/// Parse every item of <paramref name="array" /> with
/// <paramref name="deserializeItem" />.
/// </summary>
/// <remarks>
/// This is shared by all the list-typed constructor arguments whose items are
/// de-serialized into a value type (<em>e.g.</em>, a bool, a number or
/// an enumeration literal).
/// </remarks>
/// <typeparam name="T">Type of a single array item</typeparam>
private static List<T> ParseArrayOfStruct<T>(
{I}Nodes.JsonArray array,
{I}JsonStructItemDeserializer<T> deserializeItem,
{I}out Reporting.Error? error
{I}) where T : struct
{{
{I}error = null;
{I}List<T> result = new List<T>(array.Count);

{I}int index = 0;
{I}foreach (Nodes.JsonNode? item in array)
{I}{{
{II}if (item == null)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected a non-null item, but got a null");
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(
{IIIII}index));
{III}return result;
{II}}}

{II}T? parsedItem = deserializeItem(
{III}item ?? throw new System.InvalidOperationException(),
{III}out error);
{II}if (error != null)
{II}{{
{III}error.PrependSegment(
{IIII}new Reporting.IndexSegment(
{IIIII}index));
{III}return result;
{II}}}

{II}result.Add(
{III}parsedItem
{IIII}?? throw new System.InvalidOperationException(
{IIIII}"Unexpected result null when error is null"));

{II}index++;
{I}}}

{I}return result;
}}"""
    )


def _generate_tuple_item_deserializer_helpers() -> Stripped:
    """Generate the delegate and adapters shared by all the generic tuple parsers."""
    return Stripped(
        f"""\
/// <summary>
/// Parse a single tuple item.
/// </summary>
/// <remarks>
/// A tuple-typed property is parsed by <c>ParseTupleN</c> (see
/// <see cref="ParseTuple2{{T0, T1}}" /> for the arity-2 case, *etc.*), one
/// function shared by *every* tuple-typed property of a given arity,
/// regardless of which mix of reference and value types appears at each
/// position. If <c>ParseTupleN</c> demanded the same
/// <c>JsonClassItemDeserializer&lt;T&gt;</c>/<c>JsonStructItemDeserializer&lt;T&gt;</c>
/// shape already used for list items (a nullable return, constrained to
/// <c>class</c> or <c>struct</c>), its own type parameters would need that
/// constraint fixed once per position -- which breaks the moment two
/// different tuple-typed properties of the same arity mix reference and
/// value types differently at the same position (<em>e.g.</em>,
/// <c>(string, long)</c> at one property and <c>(long, string)</c> at
/// another could not share one <c>ParseTuple2</c>).
///
/// A single unconstrained <c>T? Method(Nodes.JsonNode node, out Reporting.Error? error)</c>
/// shape shared by both reference and value types does not work around this
/// either: for a value type, an unconstrained <c>T?</c> erases to plain
/// <c>T</c> (not <c>System.Nullable&lt;T&gt;</c>), so a method returning
/// <c>long?</c> can not even be assigned to it.
///
/// <c>TupleItemDeserializer&lt;T&gt;</c> sidesteps the class/struct split
/// entirely by using an <c>out</c> parameter for the value instead of a
/// nullable return, at the cost of needing an adapter --
/// <see cref="AsTupleItemDeserializer{{T}}(JsonClassItemDeserializer{{T}})" /> --
/// to convert an existing item parser (such as a bare <c>StringFrom</c> or
/// <c>LongFrom</c> method group) into one.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private delegate void TupleItemDeserializer<T>(
{I}Nodes.JsonNode node,
{I}out T value,
{I}out Reporting.Error? error);

/// <summary>
/// Adapt <paramref name="deserializeItem" /> -- a reference-type item parser
/// as used for list-typed properties -- into a <see cref="TupleItemDeserializer{{T}}" />
/// for use in a tuple-typed property.
/// </summary>
/// <remarks>
/// See the remarks on <see cref="TupleItemDeserializer{{T}}" /> for why this
/// adapter -- rather than a shared constraint on <c>ParseTupleN</c> itself --
/// is necessary. This overload and its <c>JsonStructItemDeserializer&lt;T&gt;</c>
/// counterpart are dispatched on the parameter's delegate type alone, so a
/// caller never has to pick between them by name; each encapsulates the
/// "unwrap the nullable result, or propagate the error" check exactly once,
/// mirroring how <see cref="ParseArrayOfClass{{T}}" />/
/// <see cref="ParseArrayOfStruct{{T}}" /> encapsulate the very same check
/// once for lists instead of repeating it at every call site.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private static TupleItemDeserializer<T> AsTupleItemDeserializer<T>(
{I}JsonClassItemDeserializer<T> deserializeItem
{I}) where T : class
{{
{I}return (
{II}Nodes.JsonNode node,
{II}out T value,
{II}out Reporting.Error? error) =>
{II}{{
{III}T? parsed = deserializeItem(node, out error);
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
/// Adapt <paramref name="deserializeItem" /> -- a value-type item parser
/// as used for list-typed properties -- into a <see cref="TupleItemDeserializer{{T}}" />
/// for use in a tuple-typed property.
/// </summary>
/// <remarks>
/// See <see cref="AsTupleItemDeserializer{{T}}(JsonClassItemDeserializer{{T}})" />
/// for why this adapter is necessary.
/// </remarks>
/// <typeparam name="T">Type of the parsed item</typeparam>
private static TupleItemDeserializer<T> AsTupleItemDeserializer<T>(
{I}JsonStructItemDeserializer<T> deserializeItem
{I}) where T : struct
{{
{I}return (
{II}Nodes.JsonNode node,
{II}out T value,
{II}out Reporting.Error? error) =>
{II}{{
{III}T? parsed = deserializeItem(node, out error);
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

    Each positional item is parsed by its own ``deserializeItemI`` callback,
    which sets the ``out value`` only if it does not also set ``out error``.
    We can not reuse :py:func:`_generate_parse_array_of_class_helper`/
    :py:func:`_generate_parse_array_of_struct_helper` here since a tuple is
    heterogeneous: unlike a single generic ``T`` shared by every list item,
    each tuple position has its own type, possibly a mix of reference and
    value types, so the item delegate takes ``value`` as an ``out`` parameter
    instead of returning a nullable ``T?`` (which would need a ``class`` or
    ``struct`` constraint fixed once for all instantiations of this method).
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
        item_blocks.append(
            Stripped(
                f"""\
Nodes.JsonNode? node{i} = array[{i}];
if (node{i} == null)
{{
{I}error = new Reporting.Error(
{II}"Expected a non-null item, but got a null");
{I}error.PrependSegment(
{II}new Reporting.IndexSegment(
{III}{i}));
{I}return default!;
}}
deserializeItem{i}(node{i}, out T{i} item{i}, out error);
if (error != null)
{{
{I}error.PrependSegment(
{II}new Reporting.IndexSegment(
{III}{i}));
{I}return default!;
}}"""
            )
        )

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
/// Parse every item of <paramref name="array" /> as a tuple of {arity} item(s).
/// </summary>
/// <remarks>
/// This is shared by all the tuple-typed properties of arity {arity}.
/// </remarks>
private static {tuple_type} {function_name}<{type_params_joined}>(
{I}Nodes.JsonArray array,
{I}{indent_but_first_line(params_joined, I)},
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}if (array.Count != {arity})
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected exactly {arity} item(s) in the JsonArray, " +
{III}$"but got: {{array.Count}}");
{II}return default!;
{I}}}

{I}{indent_but_first_line(item_blocks_joined, I)}

{I}return {indent_but_first_line(return_expr, I)};
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_deserialize_constructor_argument(
    arg: intermediate.Argument,
    json_name: str,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the code snippet for de-serializing the constructor argument ``arg``."""
    type_anno = intermediate.beneath_optional(arg.type_annotation)

    # Prefix the variables to avoid naming conflicts
    target_var = csharp_naming.variable_name(Identifier(f"the_{arg.name}"))

    assert not csharp_common.needs_escaping(json_name)

    json_literal = csharp_common.string_literal(json_name)

    parse_block: Stripped

    if isinstance(
        type_anno,
        (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
    ):
        parse_method = _parse_method_for_atomic_value(type_anno)

        parse_block = Stripped(
            f"""\
{target_var} = {parse_method}(
{I}keyValue.Value,
{I}out error);
if (error != null)
{{
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{json_literal}));
{I}return null;
}}
if ({target_var} == null)
{{
{I}throw new System.InvalidOperationException(
{II}"Unexpected {target_var} null when error is also null");
}}"""
        )

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            f"(mristin): We generate only code for lists of atomic values in the JSON "
            f"de-serialization, but got a list of type {type_anno}. "
            f"Please contact the developers if you need this feature."
        )

        item_type = csharp_common.generate_type(type_anno.items)

        array_var = csharp_naming.variable_name(Identifier(f"array_{arg.name}"))

        parse_method = _parse_method_for_atomic_value(type_anno.items)

        primitive_type = intermediate.try_primitive_type(type_anno.items)
        if primitive_type is not None:
            is_value_type = primitive_type in (
                intermediate.PrimitiveType.BOOL,
                intermediate.PrimitiveType.INT,
                intermediate.PrimitiveType.FLOAT,
            )
        else:
            is_value_type = isinstance(
                type_anno.items, intermediate.OurTypeAnnotation
            ) and isinstance(type_anno.items.our_type, intermediate.Enumeration)

        parse_array_function = (
            "ParseArrayOfStruct" if is_value_type else "ParseArrayOfClass"
        )

        parse_block = Stripped(
            f"""\
Nodes.JsonArray? {array_var} = keyValue.Value as Nodes.JsonArray;
if ({array_var} == null)
{{
{I}error = new Reporting.Error(
{II}$"Expected a JsonArray, but got {{keyValue.Value.GetType()}}");
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{json_literal}));
{I}return null;
}}
{target_var} = {parse_array_function}<{item_type}>(
{I}{array_var},
{I}{parse_method},
{I}out error);
if (error != null)
{{
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{json_literal}));
{I}return null;
}}"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        array_var = csharp_naming.variable_name(Identifier(f"array_{arg.name}"))

        item_deserializer_exprs = []  # type: List[Stripped]

        for item_type_anno in type_anno.items:
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"Expected an atomic tuple item (a primitive, a constrained "
                f"primitive, an enumeration, a class or a named union), "
                f"but got {item_type_anno}. "
                f"This should have already been verified in "
                f"intermediate._translate._verify_only_simple_type_patterns."
            )

            parse_method = _parse_method_for_atomic_value(item_type_anno)

            item_deserializer_exprs.append(
                Stripped(f"AsTupleItemDeserializer({parse_method})")
            )

        item_deserializer_exprs_joined = ",\n".join(item_deserializer_exprs)

        arity = len(type_anno.items)

        parse_block = Stripped(
            f"""\
Nodes.JsonArray? {array_var} = keyValue.Value as Nodes.JsonArray;
if ({array_var} == null)
{{
{I}error = new Reporting.Error(
{II}$"Expected a JsonArray, but got {{keyValue.Value.GetType()}}");
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{json_literal}));
{I}return null;
}}
{target_var} = ParseTuple{arity}(
{I}{array_var},
{I}{indent_but_first_line(item_deserializer_exprs_joined, I)},
{I}out error);
if (error != null)
{{
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{json_literal}));
{I}return null;
}}"""
        )
    else:
        assert_never(arg.type_annotation)

    # NOTE (mristin):
    # We need to add a prologue to the parsing body to explicitly check for null
    # values as the null values are not allowed for optional properties by
    # specification.
    if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
        parse_block = Stripped(
            f"""\
if (keyValue.Value == null)
{{
{I}error = new Reporting.Error(
{II}"Expected optional property to be absent, " +
{II}"but got null instead");
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{json_literal}));
{I}return null;
}}

{parse_block}"""
        )
    else:
        parse_block = Stripped(
            f"""\
if (keyValue.Value == null)
{{
{I}error = new Reporting.Error(
{II}"Unexpected null for a required property");
{I}error.PrependSegment(
{II}new Reporting.NameSegment(
{III}{json_literal}));
{I}return null;
}}

{parse_block}"""
        )

    return parse_block, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_from_method_for_class(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the deserialization method for a concrete class."""
    errors = []  # type: List[Error]

    name = csharp_naming.class_name(cls.name)

    blocks = [
        Stripped("error = null;"),
        Stripped(
            f"""\
Nodes.JsonObject? obj = node as Nodes.JsonObject;
if (obj == null)
{{
{I}error = new Reporting.Error(
{II}$"Expected a JsonObject, but got {{node.GetType()}}");
{I}return null;
}}"""
        ),
    ]  # type: List[Stripped]

    # region Initialize argument variables to null

    args_init_writer = io.StringIO()
    for i, arg in enumerate(cls.constructor.arguments):
        arg_var = csharp_naming.variable_name(Identifier(f"the_{arg.name}"))
        arg_type = csharp_common.generate_type(arg.type_annotation)

        # NOTE (mristin, 2022-07-22):
        # We make all the argument variables optional since we switch over
        # the properties. Even the mandatory constructor arguments can be omitted
        # during an invalid deserialization!
        if not arg_type.endswith("?"):
            arg_type = Stripped(f"{arg_type}?")

        if i > 0:
            args_init_writer.write("\n")
        args_init_writer.write(f"{arg_type} {arg_var} = null;")

    blocks.append(Stripped(args_init_writer.getvalue()))

    if cls.serialization.with_model_type:
        blocks.append(Stripped("string? modelType = null;"))

    # endregion

    # region Switch on property name

    cases = []  # type: List[Stripped]
    for arg in cls.constructor.arguments:
        json_name = cls.properties_by_name[arg.name].json_name

        case_body, error = _generate_deserialize_constructor_argument(
            arg=arg, json_name=json_name
        )
        if error is not None:
            errors.append(error)
        else:
            assert case_body is not None

            cases.append(
                Stripped(
                    f"""\
case {csharp_common.string_literal(json_name)}:
{{
{I}{indent_but_first_line(case_body, I)}
{I}break;
}}"""
                )
            )

    if len(errors) > 0:
        return None, errors

    if cls.serialization.with_model_type:
        model_type = naming.json_model_type(cls.name)

        cases.append(
            Stripped(
                f"""\
case "modelType":
{I}{{
{II}if (keyValue.Value == null)
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected a model type, but got null");
{III}return null;
{II}}}
{II}modelType = DeserializeImplementation.StringFrom(
{III}keyValue.Value,
{III}out error);
{II}if (error != null)
{II}{{
{III}error.PrependSegment(
{IIII}new Reporting.NameSegment(
{IIIII}"modelType"));
{III}return null;
{II}}}

{II}if (modelType != "{model_type}")
{II}{{
{III}error = new Reporting.Error(
{IIII}"Expected the model type '{model_type}', " +
{IIII}$"but got {{modelType}}");
{III}error.PrependSegment(
{IIII}new Reporting.NameSegment(
{IIIII}"modelType"));
{III}return null;
{II}}}
{II}break;
{I}}}"""
            )
        )

    cases.append(
        Stripped(
            f"""\
default:
{I}error = new Reporting.Error(
{II}$"Unexpected property: {{keyValue.Key}}");
{I}return null;"""
        )
    )

    foreach_writer = io.StringIO()
    foreach_writer.write(
        f"""\
foreach (var keyValue in obj)
{{
{I}switch (keyValue.Key)
{I}{{"""
    )

    for case_block in cases:
        foreach_writer.write("\n")
        foreach_writer.write(textwrap.indent(case_block, II))

    foreach_writer.write(f"\n{I}}}\n}}")

    blocks.append(Stripped(foreach_writer.getvalue()))

    # endregion

    # region Check required

    required_check_writer = io.StringIO()
    for i, arg in enumerate(cls.constructor.arguments):
        if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        arg_var = csharp_naming.variable_name(Identifier(f"the_{arg.name}"))
        json_name = cls.properties_by_name[arg.name].json_name
        assert not csharp_common.needs_escaping(json_name)

        if i > 0:
            required_check_writer.write("\n\n")

        required_check_writer.write(
            f"""\
if ({arg_var} == null)
{{
{I}error = new Reporting.Error(
{II}"Required property \\"{json_name}\\" is missing");
{I}return null;
}}"""
        )

    blocks.append(Stripped(required_check_writer.getvalue()))

    if cls.serialization.with_model_type:
        blocks.append(
            Stripped(
                f"""\
if (modelType == null)
{{
{I}error = new Reporting.Error(
{II}"Required property \\"modelType\\" is missing");
{I}return null;
}}"""
            )
        )

    # endregion

    # region Pass in arguments to the constructor

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

    if len(cls.constructor.arguments) == 0:
        blocks.append(Stripped(f"return new Aas.{name}();"))
    else:
        init_writer = io.StringIO()
        init_writer.write(f"return new Aas.{name}(\n")

        for i, arg in enumerate(cls.constructor.arguments):
            prop = cls.properties_by_name[arg.name]

            # NOTE (mristin, 2022-03-11):
            # The argument to the constructor may be optional while the property
            # might be required, since we can set the default value in the body of
            # the constructor. However, we can not have an optional property and a
            # required constructor argument as we then would not know how to create
            # the instance.

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
            if not isinstance(
                prop.type_annotation, intermediate.OptionalTypeAnnotation
            ):
                init_writer.write("\n")

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

        blocks.append(Stripped(init_writer.getvalue()))
    # endregion

    writer = io.StringIO()

    writer.write(
        f"""\
/// <summary>
/// Deserialize an instance of {name} from <paramref name="node" />.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
internal static Aas.{name}? {name}From(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // internal static {name}From")

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_deserialize_impl(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the implementation of the deserialization."""
    errors = []  # type: List[Error]

    blocks = [
        Stripped(
            f"""\
/// <summary>Convert <paramref name="node" /> to a boolean.</summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
internal static bool? BoolFrom(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
{I}error = null;
{I}Nodes.JsonValue? value = node as Nodes.JsonValue;
{I}if (value == null)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a JsonValue, but got {{node.GetType()}}");
{II}return null;
{I}}}
{I}bool ok = value.TryGetValue<bool>(out bool result);
{I}if (!ok)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a boolean, but the conversion failed " +
{III}$"from {{value.ToJsonString()}}");
{II}return null;
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Convert the <paramref name="node" /> to a long 64-bit integer.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
internal static long? LongFrom(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
{I}error = null;
{I}Nodes.JsonValue? value = node as Nodes.JsonValue;
{I}if (value == null)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a JsonValue, but got {{node.GetType()}}");
{II}return null;
{I}}}
{I}bool ok = value.TryGetValue<long>(out long result);
{I}if (!ok)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a 64-bit long integer, but the conversion failed " +
{III}$"from {{value.ToJsonString()}}");
{II}return null;
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Convert the <paramref name="node" /> to a double-precision 64-bit float.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
internal static double? DoubleFrom(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
{I}error = null;
{I}Nodes.JsonValue? value = node as Nodes.JsonValue;
{I}if (value == null)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a JsonValue, but got {{node.GetType()}}");
{II}return null;
{I}}}
{I}bool ok = value.TryGetValue<double>(out double result);
{I}if (!ok)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a 64-bit double-precision float, " +
{III}"but the conversion failed " +
{III}$"from {{value.ToJsonString()}}");
{II}return null;
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Convert the <paramref name="node" /> to a string.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
internal static string? StringFrom(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
{I}error = null;
{I}Nodes.JsonValue? value = node as Nodes.JsonValue;
{I}if (value == null)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a JsonValue, but got {{node.GetType()}}");
{II}return null;
{I}}}
{I}bool ok = value.TryGetValue<string>(out string? result);
{I}if (!ok)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a string, but the conversion failed " +
{III}$"from {{value.ToJsonString()}}");
{II}return null;
{I}}}
{I}if (result == null)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a string, but got a null");
{II}return null;
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Convert the <paramref name="node" /> to bytes.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
internal static byte[]? BytesFrom(
{I}Nodes.JsonNode node,
{I}out Reporting.Error? error)
{{
{I}error = null;
{I}Nodes.JsonValue? value = node as Nodes.JsonValue;
{I}if (value == null)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a JsonValue, but got {{node.GetType()}}");
{II}return null;
{I}}}
{I}bool ok = value.TryGetValue<string>(out string? text);
{I}if (!ok)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a string, but the conversion failed " +
{III}$"from {{value.ToJsonString()}}");
{II}return null;
{I}}}
{I}if (text == null)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a string, but got a null");
{II}return null;
{I}}}
{I}try
{I}{{
{II}return System.Convert.FromBase64String(text);
{I}}}
{I}catch (System.FormatException exception)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected Base-64 encoded bytes, but the conversion failed " +
{III}$"because: {{exception}}");
{II}return null;
{I}}}
}}"""
        ),
        _generate_parse_array_of_class_helper(),
        _generate_parse_array_of_struct_helper(),
    ]  # type: List[Stripped]

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        blocks.append(_generate_tuple_item_deserializer_helpers())
        for arity in tuple_arities:
            blocks.append(_generate_parse_tuple_helper(arity))

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_from_method_for_enumeration(enumeration=our_type))

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            continue

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if our_type.interface is not None:
                blocks.append(
                    _generate_from_method_for_interface(interface=our_type.interface)
                )

            if isinstance(our_type, intermediate.ConcreteClass):
                if our_type.is_implementation_specific:
                    implementation_key = specific_implementations.ImplementationKey(
                        f"Jsonization/DeserializeImplementation/{our_type.name}_from.cs"
                    )

                    implementation = spec_impls.get(implementation_key, None)
                    if implementation is None:
                        errors.append(
                            Error(
                                our_type.parsed.node,
                                f"The jsonization snippet is missing "
                                f"for the implementation-specific "
                                f"class {our_type.name}: {implementation_key}",
                            )
                        )
                        continue

                    blocks.append(spec_impls[implementation_key])
                else:
                    block, cls_errors = _generate_from_method_for_class(cls=our_type)
                    if cls_errors is not None:
                        errors.extend(cls_errors)
                        continue
                    else:
                        assert block is not None
                        blocks.append(block)

        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(_generate_from_method_for_named_union(named_union=our_type))

        else:
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()

    writer.write(
        """\
/// <summary>
/// Implement the deserialization of meta-model classes from JSON nodes.
/// </summary>
/// <remarks>
/// The implementation propagates an <see cref="Reporting.Error" /> instead of relying
/// on exceptions. Under the assumption that incorrect data is much less
/// frequent than correct data, this makes the deserialization more
/// efficient.
///
/// However, we do not want to force the client to deal with
/// the <see cref="Reporting.Error" /> class as this is not intuitive. Therefore
/// we distinguish the implementation, realized in
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

    writer.write("\n}  // public static class DeserializeImplementation")

    return Stripped(writer.getvalue()), None


def _generate_deserialize_from(name: str) -> Stripped:
    """Generate the facade deserialization method for the type with C# ``name``."""
    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Deserialize an instance of {name} from <paramref name="node" />.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <exception cref="Jsonization.Exception">
/// Thrown when <paramref name="node" /> is not a valid JSON
/// representation of {name}.
/// </exception>
"""
    )

    if name.startswith("I"):
        writer.write(
            '[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]\n'
        )

    writer.write(
        f"""\
public static Aas.{name} {name}From(
{I}Nodes.JsonNode node)
{{
{I}Aas.{name}? result = DeserializeImplementation.{name}From(
{II}node,
{II}out Reporting.Error? error);
{I}if (error != null)
{I}{{
{II}throw new Jsonization.Exception(
{III}Reporting.GenerateJsonPath(error.PathSegments),
{III}error.Cause);
{I}}}
{I}return result
{II}?? throw new System.InvalidOperationException(
{III}"Unexpected output null when error is null");
}}"""
    )

    return Stripped(writer.getvalue())


def _generate_deserialize(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the deserializer with a deserialization method for each class."""
    blocks = []  # type: List[Stripped]
    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(
                _generate_deserialize_from(name=csharp_naming.enum_name(our_type.name))
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            continue

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if our_type.interface is not None:
                blocks.append(
                    _generate_deserialize_from(
                        name=csharp_naming.interface_name(our_type.interface.name)
                    )
                )

            if isinstance(our_type, intermediate.ConcreteClass):
                blocks.append(
                    _generate_deserialize_from(
                        name=csharp_naming.class_name(our_type.name)
                    )
                )

        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(
                _generate_deserialize_from(name=csharp_naming.class_name(our_type.name))
            )

        else:
            assert_never(our_type)

    writer = io.StringIO()

    writer.write(
        """\
/// <summary>
/// Deserialize instances of meta-model classes from JSON nodes.
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
/// Here is an example how to parse an instance of {cls_name}:
/// <code>
/// string someString = "... some JSON ...";
/// var node = System.Text.Json.Nodes.JsonNode.Parse(someString);
/// Aas.{cls_name} {an_instance_variable} = Deserialize.{cls_name}From(
/// {I}node);
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


def _generate_serialize_primitive_value(
    primitive_type: intermediate.PrimitiveType, source_expr: Stripped
) -> Stripped:
    """
    Generate the snippet to serialize ``source_expr`` to JSON.

    Source expression is expected to be of ``primitive_type``.
    """
    if (
        primitive_type is intermediate.PrimitiveType.BOOL
        or primitive_type is intermediate.PrimitiveType.FLOAT
        or primitive_type is intermediate.PrimitiveType.STR
    ):
        # We can not use textwrap due to indent_but_first_line.
        return Stripped(
            f"""\
Nodes.JsonValue.Create(
{I}{indent_but_first_line(source_expr, I)})"""
        )
    elif primitive_type is intermediate.PrimitiveType.INT:
        # We can not use textwrap due to indent_but_first_line.
        return Stripped(
            f"""\
Transformer.ToJsonValue(
{I}{indent_but_first_line(source_expr, I)})"""
        )
    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        # We can not use textwrap due to indent_but_first_line.
        return Stripped(
            f"""\
Nodes.JsonValue.Create(
{I}System.Convert.ToBase64String(
{II}{indent_but_first_line(source_expr, II)}))"""
        )
    else:
        assert_never(primitive_type)


def _generate_serialize_atomic_value(
    type_annotation: intermediate.AtomicTypeAnnotation, source_expr: Stripped
) -> Stripped:
    """Generate the snippet to serialize ``source_expr`` to JSON."""
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return _generate_serialize_primitive_value(
            primitive_type=type_annotation.a_type, source_expr=source_expr
        )
    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type
        if isinstance(our_type, intermediate.Enumeration):
            name = csharp_naming.enum_name(our_type.name)

            # We can not use textwrap due to indent_but_first_line.
            return Stripped(
                f"""\
Serialize.{name}ToJsonValue(
{I}{indent_but_first_line(source_expr, I)})"""
            )
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return _generate_serialize_primitive_value(
                primitive_type=our_type.constrainee, source_expr=source_expr
            )
        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            # NOTE (mristin):
            # A named union is not itself an ``Aas.IClass``, but the
            # ``Transformer`` class defines a ``Transform`` overload for every
            # named union (see :py:func:`_generate_union_transform_helper`)
            # that unwraps it to its underlying instance, so we can transform
            # it exactly like a class instance here.
            return Stripped(
                f"""\
Transform(
{I}{indent_but_first_line(source_expr, I)})"""
            )
        else:
            assert_never(our_type)
    else:
        assert_never(type_annotation)


def _generate_tuple_atomic_serializer_helpers() -> List[Stripped]:
    """
    Generate ``ToJsonValue`` overloads so every atomic tuple item is a bare method group.

    ``SerializeTupleN`` (see :py:func:`_generate_serialize_tuple_helper`)
    accepts a plain ``System.Func<T, Nodes.JsonNode?>`` per item, so a tuple
    item whose serialization is already a single call to one of our own
    methods (the existing ``Transformer.ToJsonValue(long)``, a class's own
    ``Transform``, an enum's own ``...ToJsonValue``) can be passed on
    directly, with no wrapping lambda -- see
    :py:func:`_tuple_item_serializer_expr`.

    ``bool``, ``float`` (``double``), ``str`` and ``bytearray`` (the latter
    additionally composing a base64 encoding step) route through the BCL's
    ``Nodes.JsonValue.Create`` instead, which can NOT be passed on directly
    as a bare method group -- verified against the compiler:
    ``Nodes.JsonValue.Create`` is a *generic* method with an optional second
    parameter (``Create<T>(T value, JsonNodeOptions? options = null)``), and
    the C# compiler refuses to convert a method group to a delegate in that
    combination (CS1503), regardless of whether ``T`` would otherwise be
    inferable from the target delegate.

    So we add more overloads of the already-existing, single-purpose,
    non-generic ``Transformer.ToJsonValue`` here -- one per such primitive
    type -- exactly so that *an overload of ours*, not
    ``Nodes.JsonValue.Create`` itself, can be forwarded as a bare method
    group; unlike a generic method, a plain overload set is resolved by the
    compiler purely from the (already-known, at every call site here) target
    delegate type, which is exactly the case that fails for
    ``Nodes.JsonValue.Create`` -- also verified against the compiler.
    """
    result = []  # type: List[Stripped]

    for csharp_type, conversion_expr in (
        ("bool", "Nodes.JsonValue.Create(that)"),
        ("double", "Nodes.JsonValue.Create(that)"),
        ("string", "Nodes.JsonValue.Create(that)"),
        ("byte[]", "Nodes.JsonValue.Create(System.Convert.ToBase64String(that))"),
    ):
        result.append(
            Stripped(
                f"""\
/// <summary>
/// Convert <paramref name="that" /> to a JSON value.
/// </summary>
[CodeAnalysis.SuppressMessage("ReSharper", "UnusedMember.Local")]
private static Nodes.JsonValue ToJsonValue({csharp_type} that)
{{
{I}return {conversion_expr};
}}"""
            )
        )

    return result


def _tuple_item_serializer_expr(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """
    Generate an expression usable directly as a tuple item's serializer.

    ``SerializeTupleN`` (see :py:func:`_generate_serialize_tuple_helper`)
    infers its type parameters from the tuple value itself (its first
    argument), so -- unlike the adapters needed on the deserialization side
    -- a bare method group already matching ``System.Func<T, Nodes.JsonNode?>``
    can be passed on directly here, without a wrapping lambda, for every
    atomic kind: every primitive routes through one of the
    ``Transformer.ToJsonValue`` overloads (see
    :py:func:`_generate_tuple_atomic_serializer_helpers` for why we route
    ``bool``/``float``/``str``/``bytearray`` through overloads of our own
    instead of the BCL's ``Nodes.JsonValue.Create`` directly), and classes,
    named unions and enums route through their own existing single-overload,
    non-generic ``Transform``/``...ToJsonValue`` methods.
    """
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        primitive_type = type_annotation.a_type
    elif isinstance(type_annotation, intermediate.OurTypeAnnotation) and isinstance(
        type_annotation.our_type, intermediate.ConstrainedPrimitive
    ):
        primitive_type = type_annotation.our_type.constrainee
    else:
        primitive_type = None

    if primitive_type is not None:
        return Stripped("Transformer.ToJsonValue")

    assert isinstance(type_annotation, intermediate.OurTypeAnnotation)
    our_type = type_annotation.our_type

    if isinstance(our_type, intermediate.Enumeration):
        name = csharp_naming.enum_name(our_type.name)
        return Stripped(f"Serialize.{name}ToJsonValue")
    elif isinstance(
        our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    ):
        # A named union has its own ``Transform`` overload in the
        # ``Transformer`` class (see
        # :py:func:`_generate_union_transform_helper`), so it can be
        # passed on as a bare method group just like a class.
        return Stripped("Transform")
    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        raise AssertionError(
            f"Unexpected {our_type=}: a constrained primitive should have "
            f"already been handled above through ``primitive_type``"
        )
    else:
        assert_never(our_type)


@require(lambda arity: arity > 0)
def _generate_serialize_tuple_helper(arity: int) -> Stripped:
    """Generate a generic function to serialize a tuple of the given ``arity``."""
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(type_params)

    if arity == 1:
        tuple_type = f"System.ValueTuple<{type_params[0]}>"
    else:
        tuple_type = f"({type_params_joined})"

    params_joined = ",\n".join(
        f"System.Func<T{i}, Nodes.JsonNode?> serializeItem{i}" for i in range(arity)
    )

    add_stmts_joined = "\n".join(
        f"result.Add(serializeItem{i}(that.Item{i + 1}));" for i in range(arity)
    )

    function_name = f"SerializeTuple{arity}"

    return Stripped(
        f"""\
/// <summary>
/// Serialize the tuple <paramref name="that" /> of {arity} item(s) with
/// <paramref name="serializeItem0" />, <paramref name="serializeItem1" />, *etc.*
/// into a JSON array.
/// </summary>
/// <remarks>
/// This is shared by all the tuple-typed properties of arity {arity}.
/// </remarks>
private static Nodes.JsonArray {function_name}<{type_params_joined}>(
{I}{tuple_type} that,
{I}{indent_but_first_line(params_joined, I)})
{{
{I}var result = new Nodes.JsonArray();
{I}{indent_but_first_line(add_stmts_joined, I)}
{I}return result;
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transform_property(
    prop: intermediate.Property,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the snippet to transform a property into a JSON node."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    stmts = []  # type: List[Stripped]

    name = csharp_naming.property_name(prop.name)
    prop_literal = csharp_common.string_literal(prop.json_name)

    # NOTE (mristin, 2022-03-12):
    # For some unexplainable reason, C# compiler can not infer that properties which
    # are enumerations are not null after an ``if (that.someProperty != null)``.
    # Hence, we need to add a null-coalescing for these particular cases.
    # Otherwise, we can just stick to ``that.someProperty``.

    needs_null_coalescing = (
        isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        and isinstance(prop.type_annotation.value, intermediate.OurTypeAnnotation)
        and isinstance(prop.type_annotation.value.our_type, intermediate.Enumeration)
    )
    if needs_null_coalescing:
        source_expr = Stripped("value")
    else:
        source_expr = Stripped(f"that.{name}")

    if isinstance(
        type_anno,
        (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
    ):
        conversion_expr = _generate_serialize_atomic_value(
            type_annotation=type_anno, source_expr=source_expr
        )
        stmts.append(Stripped(f"result[{prop_literal}] = {conversion_expr};"))
    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            f"(mristin): We generate only code for lists of atomic values in the JSON "
            f"serialization, but got a list of type {type_anno}. "
            f"Please contact the developers if you need this feature."
        )

        item_type = csharp_common.generate_type(type_anno.items)
        array_var = csharp_naming.variable_name(Identifier(f"array_{prop.name}"))

        item_conversion_expr = _generate_serialize_atomic_value(
            type_annotation=type_anno.items, source_expr=Stripped("item")
        )

        # We can not use textwrap due to indent_but_first_line.
        stmts.append(
            Stripped(
                f"""\
Nodes.JsonArray {array_var} = SerializeArray(
{I}{source_expr},
{I}({item_type} item) =>
{II}{indent_but_first_line(item_conversion_expr, II)});
result[{prop_literal}] = {array_var};"""
            )
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        array_var = csharp_naming.variable_name(Identifier(f"array_{prop.name}"))

        item_serializer_exprs = []  # type: List[Stripped]
        for item_type_anno in type_anno.items:
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"Expected an atomic tuple item (a primitive, a constrained "
                f"primitive, an enumeration, a class or a named union), "
                f"but got {item_type_anno}. "
                f"This should have already been verified in "
                f"intermediate._translate._verify_only_simple_type_patterns."
            )

            item_serializer_exprs.append(_tuple_item_serializer_expr(item_type_anno))

        item_serializer_exprs_joined = ",\n".join(item_serializer_exprs)

        arity = len(type_anno.items)

        stmts.append(
            Stripped(
                f"""\
Nodes.JsonArray {array_var} = SerializeTuple{arity}(
{I}{source_expr},
{I}{indent_but_first_line(item_serializer_exprs_joined, I)});
result[{prop_literal}] = {array_var};"""
            )
        )
    else:
        assert_never(type_anno)

    serialize_block = Stripped("\n".join(stmts))
    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        if needs_null_coalescing:
            value_type = csharp_common.generate_type(prop.type_annotation.value)
            if isinstance(prop.type_annotation.value, intermediate.OurTypeAnnotation):
                our_type = prop.type_annotation.value.our_type
                if isinstance(
                    our_type,
                    (
                        intermediate.Enumeration,
                        intermediate.AbstractClass,
                        intermediate.ConcreteClass,
                    ),
                ):
                    value_type = Stripped(f"Aas.{value_type}")

            return (
                Stripped(
                    f"""\
if (that.{name} != null)
{{
{I}// We need to help the static analyzer with a null coalescing.
{I}{value_type} value = that.{name}
{II}?? throw new System.InvalidOperationException();
{I}{indent_but_first_line(serialize_block, I)}
}}"""
                ),
                None,
            )

        else:
            return (
                Stripped(
                    f"""\
if (that.{name} != null)
{{
{I}{indent_but_first_line(serialize_block, I)}
}}"""
                ),
                None,
            )
    else:
        return serialize_block, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transform_for_class(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transform method to a JSON object for the given concrete class."""
    errors = []  # type: List[Error]

    blocks = [Stripped("var result = new Nodes.JsonObject();")]  # type: List[Stripped]

    for prop in cls.properties:
        block, error = _generate_transform_property(prop=prop)
        if error is not None:
            errors.append(error)
        else:
            assert block is not None
            blocks.append(block)

    if len(errors) > 0:
        return None, errors

    if cls.serialization is not None and cls.serialization.with_model_type:
        model_type = csharp_common.string_literal(naming.json_model_type(cls.name))
        blocks.append(Stripped(f'result["modelType"] = {model_type};'))

    blocks.append(Stripped("return result;"))

    writer = io.StringIO()

    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    writer.write(
        f"""\
public override Nodes.JsonObject {transform_name}(
{I}Aas.{interface_name} that
)
{{
"""
    )

    for i, stmt in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(stmt, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_union_transform_helper() -> Stripped:
    """
    Generate a single ``Transform`` overload shared by every named union.

    A named union is not itself an ``Aas.IClass``, so it can not be dispatched
    by the inherited, ``IClass``-typed ``Transform`` overload. We add this
    overload, single-purpose and non-virtual just like the tuple atomic
    serializer helpers above, so that call sites can keep passing ``Transform``
    around as a plain method group or calling it directly, regardless of
    whether the value at hand is a class instance or a named union -- see
    :py:func:`_generate_serialize_atomic_value` and
    :py:func:`_tuple_item_serializer_expr`.

    Dispatching over the common, non-generic ``Aas.IUnion`` (see ``generate()``
    in ``_generate_types.py``) instead of the union's own type means we need
    only this one overload for *all* named unions, not one per union.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
private Nodes.JsonObject Transform(Aas.IUnion that)
{{
{I}return Transform(that.Underlying);
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transformer(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a transformer which transforms instances of the meta-model to JSON."""
    errors = []  # type: List[Error]

    blocks = [
        Stripped(
            f"""\
/// <summary>
/// Convert <paramref name="that" /> 64-bit long integer to a JSON value.
/// </summary>
/// <param name="that">value to be converted</param>
/// <exception name="System.ArgumentException">
/// Thrown if <paramref name="that" /> is not within the range where it
/// can be losslessly converted to a double floating number.
/// </exception>
[CodeAnalysis.SuppressMessage("ReSharper", "UnusedMember.Local")]
private static Nodes.JsonValue ToJsonValue(long that)
{{
{I}// We need to check that we can perform a lossless conversion.
{I}if ((long)((double)that) != that)
{I}{{
{II}throw new System.ArgumentException(
{III}$"The number can not be losslessly represented in JSON: {{that}}");
{I}}}
{I}return Nodes.JsonValue.Create(that);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize every item of <paramref name="items" /> with
/// <paramref name="serializeItem" /> into a JSON array.
/// </summary>
/// <remarks>
/// This is shared by all the list-typed properties.
/// </remarks>
/// <typeparam name="T">Type of a single list item</typeparam>
private static Nodes.JsonArray SerializeArray<T>(
{I}IEnumerable<T> items,
{I}System.Func<T, Nodes.JsonNode?> serializeItem)
{{
{I}var result = new Nodes.JsonArray();
{I}foreach (T item in items)
{I}{{
{II}result.Add(
{III}serializeItem(item));
{I}}}
{I}return result;
}}"""
        ),
    ]  # type: List[Stripped]

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        blocks.extend(_generate_tuple_atomic_serializer_helpers())
        for arity in tuple_arities:
            blocks.append(_generate_serialize_tuple_helper(arity))

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            continue

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            continue

        elif isinstance(our_type, intermediate.AbstractClass):
            # The abstract classes are directly dispatched by the transformer,
            # so we do not need to handle them separately.
            pass

        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Jsonization/Transformer/transform_{our_type.name}.cs"
                )

                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The jsonization snippet is missing "
                            f"for the implementation-specific "
                            f"class {our_type.name}: {implementation_key}",
                        )
                    )
                    continue

                blocks.append(spec_impls[implementation_key])
            else:
                block, cls_errors = _generate_transform_for_class(cls=our_type)
                if cls_errors is not None:
                    errors.extend(cls_errors)
                else:
                    assert block is not None
                    blocks.append(block)

        elif isinstance(our_type, intermediate.NamedUnion):
            # A named union is never double-dispatched here directly -- it
            # is unwrapped by the single shared ``Transform(Aas.IUnion)``
            # overload instead (see :py:func:`_generate_union_transform_helper`).
            pass

        else:
            assert_never(our_type)

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_union_transform_helper())

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    writer.write(
        f"""\
internal class Transformer
{I}: Visitation.AbstractTransformer<Nodes.JsonObject>
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal class Transformer")

    return Stripped(writer.getvalue()), None


def _generate_serialize(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the static serializer."""
    blocks = [
        Stripped(
            "private static readonly Transformer Transformer = new Transformer();"
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize an instance of the meta-model into a JSON object.
/// </summary>
public static Nodes.JsonObject ToJsonObject(Aas.IClass that)
{{
{I}return Serialize.Transformer.Transform(that);
}}"""
        ),
    ]  # type: List[Stripped]

    for enum in symbol_table.enumerations:
        name = csharp_naming.enum_name(enum.name)
        blocks.append(
            Stripped(
                f"""\
/// <summary>
/// Serialize a literal of {name} into a JSON string.
/// </summary>
public static Nodes.JsonValue {name}ToJsonValue(Aas.{name} that)
{{
{I}string? text = Stringification.ToString(that);
{I}return Nodes.JsonValue.Create(text)
{II}?? throw new System.ArgumentException(
{III}$"Invalid {name}: {{that}}");
}}"""
            )
        )

    writer = io.StringIO()

    writer.write(
        """\
/// <summary>
/// Serialize instances of meta-model classes to JSON elements.
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
///     // ... some constructor arguments ...
/// );
/// System.Text.Json.Nodes.JsonObject element = (
/// {I}Serialize.ToJsonObject(
/// {II}{an_instance_variable}));
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
    Generate code for JSON de/serialization.

    The ``namespace`` defines the AAS C# namespace.
    """
    errors = []  # type: List[Error]

    deserialize_impl_block, deserialize_impl_errors = _generate_deserialize_impl(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if deserialize_impl_errors is not None:
        errors.extend(deserialize_impl_errors)

    deserialize_block = _generate_deserialize(symbol_table=symbol_table)

    transformer_block, transformer_errors = _generate_transformer(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if transformer_errors is not None:
        errors.extend(transformer_errors)

    if len(errors) > 0:
        return None, errors

    assert deserialize_impl_block is not None
    assert deserialize_block is not None
    assert transformer_block is not None

    serialize_block = _generate_serialize(
        symbol_table=symbol_table,
    )

    exception_block = Stripped(
        f"""\
/// <summary>
/// Represent a critical error during the deserialization.
/// </summary>
public class Exception : System.Exception
{{
{I}public readonly string Path;
{I}public readonly string Cause;
{I}public Exception(string path, string cause)
{II}: base($"{{cause}} at: {{path}}")
{I}{{
{II}Path = path;
{II}Cause = cause;
{I}}}
}}"""
    )

    jsonization_blocks = [
        deserialize_impl_block,
        exception_block,
        deserialize_block,
        transformer_block,
        serialize_block,
    ]  # type: List[Stripped]

    jsonization_writer = io.StringIO()
    jsonization_writer.write(
        f"""\
namespace {namespace}
{{
{I}/// <summary>
{I}/// Provide de/serialization of meta-model classes to/from JSON.
{I}/// </summary>
{I}/// <remarks>
{I}/// We can not use one-pass deserialization for JSON since the object
{I}/// properties do not have fixed order, and hence we can not read
{I}/// <c>modelType</c> property ahead of the remaining properties.
{I}/// </remarks>
{I}public static class Jsonization
{I}{{
"""
    )

    for i, deserialize_block in enumerate(jsonization_blocks):
        if i > 0:
            jsonization_writer.write("\n\n")

        jsonization_writer.write(textwrap.indent(deserialize_block, II))

    jsonization_writer.write(f"\n{I}}}  // public static class Jsonization")
    jsonization_writer.write(f"\n}}  // namespace {namespace}")

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using CodeAnalysis = System.Diagnostics.CodeAnalysis;
using Nodes = System.Text.Json.Nodes;

using System.Collections.Generic;  // can't alias"""
        )
    )

    # pylint: disable=line-too-long
    blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(jsonization_writer.getvalue()),
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
