"""Generate code for JSON de/serialization."""

import io
import textwrap
from typing import Final, List, Mapping, Optional, Sequence, Set, Tuple

from icontract import ensure, require

from aas_core_codegen import intermediate, naming
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


# NOTE (mristin):
# The generated code is indented by the emitter after the fact, so
# the generator has to compare against what is left of a line at the depth
# where the snippet will end up. That depth is spelled out as ``len(I) * N``
# at the comparison: a de-serializer field lands three levels in -- the
# namespace, ``Jsonization`` and ``DeserializeImplementation``.
#
# The name of a de-serializer field spells out the name of its type, so both
# occur twice in its declaration -- a list of a long class name alone runs to
# some 145 characters. Where a declaration does not fit, the type argument is
# broken out onto a line of its own.
_MAX_LINE_LENGTH: Final[int] = 100


def _generate_describe_helper() -> Stripped:
    """Generate the helper describing a node in an error message."""
    return Stripped(
        f"""\
/// <summary>
/// Describe <paramref name="node" /> in an error message.
/// </summary>
/// <remarks>
/// A JSON null is represented as a null node, so every "expected ..., but
/// got ..." message has to account for it. Doing so here, once, is what lets
/// a de-serializer take a nullable node and reject a null itself, instead of
/// every one of its callers checking for a null before calling it.
/// </remarks>
/// <param name="node">JSON node to be described</param>
private static string Describe(Nodes.JsonNode? node)
{{
{I}return (node == null)
{II}? "a null"
{II}: node.GetType().ToString();
}}"""
    )


def _generate_deserializer_delegate() -> Stripped:
    """Generate the one delegate shared by every de-serialization."""
    return Stripped(
        f"""\
/// <summary>
/// De-serialize a value from <paramref name="node" />.
/// </summary>
/// <remarks>
/// This is the one shape of every de-serialization, which is what lets
/// the de-serializations be composed: an <c>As*</c> combinator turns
/// the de-serializers of the items into the de-serializer of a list or
/// of a tuple of them, and the <c>...From</c> function of a primitive,
/// an enumeration, a class, an interface or a named union already is one.
///
/// Return the value; on failure it is meaningless and
/// <paramref name="error" /> says why. A plain <c>T</c> rather than
/// a <c>T?</c>, so that one unconstrained delegate serves both the value
/// and the reference types: for a value type an unconstrained <c>T?</c>
/// erases to plain <c>T</c> rather than to <c>System.Nullable&lt;T&gt;</c>,
/// so a <c>T?</c> would have to be split into a <c>class</c>- and
/// a <c>struct</c>-constrained variant, and anything ranging over both --
/// such as the items of a tuple -- would then need an adapter between them.
///
/// The <paramref name="node" /> is nullable since a JSON null is represented
/// as a null node. Each de-serializer rejects it with a message of its own,
/// so that the check is paid once per type instead of once per property.
///
/// <typeparamref name="T" /> is covariant, so that the de-serializer of
/// a concrete class can be used as the de-serializer of an item of a list of
/// its interface.
/// </remarks>
/// <typeparam name="T">Type of the de-serialized value</typeparam>
private delegate T Deserializer<out T>(
{I}Nodes.JsonNode? node,
{I}out Reporting.Error? error);"""
    )


def _generate_as_array_of_helper() -> Stripped:
    """Generate the combinator de-serializing a JSON array."""
    return Stripped(
        f"""\
/// <summary>
/// De-serialize every item of a JSON array with
/// <paramref name="deserializeItem" />.
/// </summary>
/// <remarks>
/// This is shared by all the list-typed constructor arguments, regardless of
/// whether their items de-serialize into a reference or into a value type.
/// The result is cached in a <c>static readonly</c> field per item type
/// (see <c>Parse_ListOf_*</c>), so that composing it costs nothing at
/// the point of use.
/// </remarks>
/// <typeparam name="T">Type of a single array item</typeparam>
private static Deserializer<List<T>> AsArrayOf<T>(
{I}Deserializer<T> deserializeItem)
{{
{I}return (
{II}Nodes.JsonNode? node,
{II}out Reporting.Error? error) =>
{II}{{
{III}error = null;

{III}Nodes.JsonArray? array = node as Nodes.JsonArray;
{III}if (array == null)
{III}{{
{IIII}error = new Reporting.Error(
{IIIII}$"Expected a JsonArray, but got {{Describe(node)}}");
{IIII}return default!;
{III}}}

{III}List<T> result = new List<T>(array.Count);

{III}int index = 0;
{III}foreach (Nodes.JsonNode? item in array)
{III}{{
{IIII}T parsedItem = deserializeItem(item, out error);
{IIII}if (error != null)
{IIII}{{
{IIIII}error.PrependSegment(
{IIIII}{I}new Reporting.IndexSegment(
{IIIII}{II}index));
{IIIII}return default!;
{IIII}}}

{IIII}result.Add(parsedItem);

{IIII}index++;
{III}}}

{III}return result;
{II}}};
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_as_tuple_helper(arity: int) -> Stripped:
    """
    Generate the combinator de-serializing a tuple of the given ``arity``.

    Unlike a list, a tuple is heterogeneous: each position has its own type,
    possibly a mix of reference and value types. One unconstrained
    ``Deserializer<T>`` per position is what lets a single ``AsTuple{N}``
    serve every tuple-typed property of that arity -- see the remarks
    on ``Deserializer<T>``.
    """
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(type_params)

    if arity == 1:
        tuple_type = f"System.ValueTuple<{type_params[0]}>"
    else:
        tuple_type = f"({type_params_joined})"

    params_joined = ",\n".join(
        f"Deserializer<T{i}> deserializeItem{i}" for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
T{i} item{i} = deserializeItem{i}(array[{i}], out error);
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

    return Stripped(
        f"""\
/// <summary>
/// De-serialize a JSON array as a tuple of {arity} item(s).
/// </summary>
/// <remarks>
/// This is shared by all the tuple-typed properties of arity {arity}.
/// </remarks>
private static Deserializer<{tuple_type}> AsTuple{arity}<{type_params_joined}>(
{I}{indent_but_first_line(params_joined, I)})
{{
{I}return (
{II}Nodes.JsonNode? node,
{II}out Reporting.Error? error) =>
{II}{{
{III}error = null;

{III}Nodes.JsonArray? array = node as Nodes.JsonArray;
{III}if (array == null)
{III}{{
{IIII}error = new Reporting.Error(
{IIIII}$"Expected a JsonArray, but got {{Describe(node)}}");
{IIII}return default!;
{III}}}

{III}if (array.Count != {arity})
{III}{{
{IIII}error = new Reporting.Error(
{IIIII}$"Expected exactly {arity} item(s) in the JsonArray, " +
{IIIII}$"but got: {{array.Count}}");
{IIII}return default!;
{III}}}

{III}{indent_but_first_line(item_blocks_joined, III)}

{III}return {indent_but_first_line(return_expr, III)};
{II}}};
}}"""
    )


def _generate_model_type_from_helper() -> Stripped:
    """Generate the helper extracting the ``modelType`` of a JSON object."""
    return Stripped(
        f"""\
/// <summary>
/// Extract the <c>modelType</c> property of <paramref name="obj" />.
/// </summary>
/// <param name="obj">JSON object to be inspected</param>
/// <param name="error">Error, if any, during the deserialization</param>
private static string ModelTypeFrom(
{I}Nodes.JsonObject obj,
{I}out Reporting.Error? error)
{{
{I}Nodes.JsonNode? modelTypeNode = obj["modelType"];
{I}if (modelTypeNode == null)
{I}{{
{II}error = new Reporting.Error(
{III}"Expected a model type, but none is present");
{II}return default!;
{I}}}

{I}return StringFrom(modelTypeNode, out error);
}}"""
    )


# NOTE (mristin):
# The de-serializer of an atomic value is a function named after the type, so
# that a call site can simply name it. Only a list and a tuple have no type of
# ours to be named after; they are composed by a combinator and cached in
# a field, see :py:func:`_deserializer_name`.
_FROM_METHOD_BY_PRIMITIVE_TYPE: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.BOOL: "BoolFrom",
    intermediate.PrimitiveType.INT: "LongFrom",
    intermediate.PrimitiveType.FLOAT: "DoubleFrom",
    intermediate.PrimitiveType.STR: "StringFrom",
    intermediate.PrimitiveType.BYTEARRAY: "BytesFrom",
}

# NOTE (mristin):
# How a primitive is called in an error message. This is what the reader of
# the message is after -- "a boolean" says what was expected, whereas
# the name of the underlying ``System.Text.Json`` node type does not.
_PRIMITIVE_TYPE_DESCRIPTION: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.BOOL: "a boolean",
    intermediate.PrimitiveType.INT: "a 64-bit long integer",
    intermediate.PrimitiveType.FLOAT: "a 64-bit double-precision float",
    intermediate.PrimitiveType.STR: "a string",
    intermediate.PrimitiveType.BYTEARRAY: "Base-64 encoded bytes",
}

assert all(
    primitive_type in _FROM_METHOD_BY_PRIMITIVE_TYPE
    and primitive_type in _PRIMITIVE_TYPE_DESCRIPTION
    for primitive_type in intermediate.PrimitiveType
)


def _generate_primitive_converter(
    primitive_type: intermediate.PrimitiveType,
) -> Stripped:
    """Generate the function converting a JSON node to the ``primitive_type``."""
    name = _FROM_METHOD_BY_PRIMITIVE_TYPE[primitive_type]
    description = _PRIMITIVE_TYPE_DESCRIPTION[primitive_type]
    value_type = csharp_common.PRIMITIVE_TYPE_MAP[primitive_type]

    conversion_failed = Stripped(
        f"""\
error = new Reporting.Error(
{I}"Expected {description}, but the conversion failed " +
{I}$"from {{value.ToJsonString()}}");
return default!;"""
    )

    body: Stripped

    if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        body = Stripped(
            f"""\
bool ok = value.TryGetValue<string>(out string? text);
if (!ok)
{{
{I}{indent_but_first_line(conversion_failed, I)}
}}
if (text == null)
{{
{I}error = new Reporting.Error(
{II}"Expected {description}, but got a null");
{I}return default!;
}}
try
{{
{I}return System.Convert.FromBase64String(text);
}}
catch (System.FormatException exception)
{{
{I}error = new Reporting.Error(
{II}"Expected {description}, but the conversion failed " +
{II}$"because: {{exception}}");
{I}return default!;
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.STR:
        body = Stripped(
            f"""\
bool ok = value.TryGetValue<string>(out string? result);
if (!ok)
{{
{I}{indent_but_first_line(conversion_failed, I)}
}}
if (result == null)
{{
{I}error = new Reporting.Error(
{II}"Expected {description}, but got a null");
{I}return default!;
}}
return result;"""
        )

    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        # NOTE (mristin):
        # JSON knows neither an infinity nor a not-a-number, so a conformant
        # parser can never give us one. The caller can still hand us a node
        # which has been constructed programmatically, so we check here.
        body = Stripped(
            f"""\
bool ok = value.TryGetValue<{value_type}>(out {value_type} result);
if (!ok)
{{
{I}{indent_but_first_line(conversion_failed, I)}
}}
if (!System.Double.IsFinite(result))
{{
{I}error = new Reporting.Error(
{II}$"Expected a finite number, but got {{result}}");
{I}return default!;
}}
return result;"""
        )

    else:
        body = Stripped(
            f"""\
bool ok = value.TryGetValue<{value_type}>(out {value_type} result);
if (!ok)
{{
{I}{indent_but_first_line(conversion_failed, I)}
}}
return result;"""
        )

    return Stripped(
        f"""\
/// <summary>
/// Convert <paramref name="node" /> to {description}.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
internal static {value_type} {name}(
{I}Nodes.JsonNode? node,
{I}out Reporting.Error? error)
{{
{I}error = null;

{I}Nodes.JsonValue? value = node as Nodes.JsonValue;
{I}if (value == null)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected {description}, but got {{Describe(node)}}");
{II}return default!;
{I}}}

{I}{indent_but_first_line(body, I)}
}}"""
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
internal static Aas.{name} {name}From(
{I}Nodes.JsonNode? node,
{I}out Reporting.Error? error)
{{
{I}string text = StringFrom(node, out error);
{I}if (error != null)
{I}{{
{II}return default!;
{I}}}

{I}Aas.{name}? result = Stringification.{name}FromString(text);
{I}if (result == null)
{I}{{
{II}error = new Reporting.Error(
{III}{message_literal});
{II}return default!;
{I}}}

{I}return result.Value;
}}  // internal static {name}From"""
    )


def _generate_from_method_for_interface(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate the deserialization method for an interface."""
    name = csharp_naming.interface_name(interface.name)

    case_blocks = []  # type: List[Stripped]
    for implementer in interface.implementers:
        model_type = naming.json_model_type(implementer.name)
        implementer_name = csharp_naming.class_name(implementer.name)
        case_blocks.append(
            Stripped(
                f"""\
case {csharp_common.string_literal(model_type)}:
{I}return {implementer_name}From(
{II}node, out error);"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}error = new Reporting.Error(
{II}$"Unexpected model type for {name}: {{modelType}}");
{I}return default!;"""
        )
    )

    cases_joined = "\n".join(
        textwrap.indent(case_block, I) for case_block in case_blocks
    )

    return Stripped(
        f"""\
/// <summary>
/// Deserialize an instance of {name} by dispatching
/// based on <c>modelType</c> property of the <paramref name="node" />.
/// </summary>
/// <param name="node">JSON node to be parsed</param>
/// <param name="error">Error, if any, during the deserialization</param>
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
public static Aas.{name} {name}From(
{I}Nodes.JsonNode? node,
{I}out Reporting.Error? error)
{{
{I}Nodes.JsonObject? obj = node as Nodes.JsonObject;
{I}if (obj == null)
{I}{{
{II}error = new Reporting.Error(
{III}$"Expected a JsonObject representing {name}, but got {{Describe(node)}}");
{II}return default!;
{I}}}

{I}string modelType = ModelTypeFrom(obj, out error);
{I}if (error != null)
{I}{{
{II}return default!;
{I}}}

{I}switch (modelType)
{I}{{
{cases_joined}
{I}}}
}}  // public static Aas.{name} {name}From"""
    )


def _generate_from_method_for_named_union(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """Generate the deserialization method for a named union."""
    name = csharp_naming.class_name(named_union.name)

    blocks = [
        Stripped(
            f"""\
Nodes.JsonObject? obj = node as Nodes.JsonObject;
if (obj == null)
{{
{I}error = new Reporting.Error(
{II}$"Expected a JsonObject representing {name}, but got {{Describe(node)}}");
{I}return default!;
}}"""
        )
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
        case_blocks = []  # type: List[Stripped]

        for implementer in implementers_with_model_type:
            model_type = naming.json_model_type(implementer.name)
            implementer_name = csharp_naming.class_name(implementer.name)
            from_method_name = csharp_naming.method_name(
                Identifier(f"from_{implementer.name}")
            )

            case_blocks.append(
                Stripped(
                    f"""\
case {csharp_common.string_literal(model_type)}:
{{
{I}Aas.{implementer_name} instance = {implementer_name}From(
{II}node, out error);
{I}if (error != null)
{I}{{
{II}return default!;
{I}}}
{I}return Aas.{name}.{from_method_name}(instance);
}}"""
                )
            )

        case_blocks.append(
            Stripped(
                f"""\
default:
{I}error = new Reporting.Error(
{II}$"Unexpected model type for the union {name}: {{modelType}}");
{I}return default!;"""
            )
        )

        cases_joined = "\n".join(
            textwrap.indent(case_block, II) for case_block in case_blocks
        )

        blocks.append(
            Stripped(
                f"""\
Nodes.JsonNode? modelTypeNode = obj["modelType"];
if (modelTypeNode != null)
{{
{I}string modelType = StringFrom(modelTypeNode, out error);
{I}if (error != null)
{I}{{
{II}return default!;
{I}}}

{I}switch (modelType)
{I}{{
{cases_joined}
{I}}}
}}"""
            )
        )

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
{I}Aas.{implementer_name} instance = {implementer_name}From(
{II}node, out error);
{I}if (error != null)
{I}{{
{II}return default!;
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
return default!;"""
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
public static Aas.{name} {name}From(
{I}Nodes.JsonNode? node,
{I}out Reporting.Error? error)
{{
{I}error = null;

"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write(f"\n}}  // public static Aas.{name} {name}From")

    return Stripped(writer.getvalue())


def _deserializer_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Name the field holding the de-serializer of a list or of a tuple.

    The moniker comes last, after an underscore, so that the name of a field
    can never coincide with one of the ``...From`` functions: those are keyed
    by one of our symbols, and a symbol is named through
    :py:func:`aas_core_codegen.naming.capitalized_camel_case`, which never
    emits an underscore.
    """
    return Identifier(f"Parse_{csharp_common.type_moniker(type_anno)}")


def _deserializer_expr(type_anno: intermediate.TypeAnnotationUnion) -> Stripped:
    """
    Generate the expression de-serializing a value of ``type_anno``.

    An atomic value is de-serialized by a function named after its type, and
    a list or a tuple by the cached field composing the de-serializers of
    its items. Either way the expression is a plain name, so that a call site
    neither allocates a delegate nor composes anything.
    """
    if isinstance(
        type_anno,
        (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
    ):
        return Stripped(_deserializer_name(type_anno))

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        return Stripped(_FROM_METHOD_BY_PRIMITIVE_TYPE[type_anno.a_type])

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Expected an atomic type annotation, but got {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return Stripped(f"{csharp_naming.enum_name(our_type.name)}From")

    if isinstance(our_type, intermediate.ConstrainedPrimitive):
        return Stripped(_FROM_METHOD_BY_PRIMITIVE_TYPE[our_type.constrainee])

    if isinstance(our_type, intermediate.NamedUnion):
        return Stripped(f"{csharp_naming.class_name(our_type.name)}From")

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    )

    if our_type.interface is not None:
        return Stripped(f"{csharp_naming.interface_name(our_type.interface.name)}From")

    return Stripped(f"{csharp_naming.class_name(our_type.name)}From")


def _composed_types_in_initialization_order(
    symbol_table: intermediate.SymbolTable,
) -> List[intermediate.TypeAnnotationUnion]:
    """
    List the list- and tuple-typed values which need a de/serializer of their own.

    Only a list and a tuple have no function of their own to be named after
    (a ``...From`` when de-serializing, a ``...ToJsonValue``, ``TransformIClass``
    or ``TransformIUnion`` when serializing), so only they are composed by
    a combinator and cached in a ``static readonly`` field. The fields are
    emitted in this order and a field initializer may reference only the fields
    declared before it -- hence the post-order: the items first, then the
    container that composes them.

    The result is de-duplicated by the moniker, which is injective (see
    :py:func:`aas_core_codegen.csharp.common.type_moniker`), so that two
    distinct types can never be conflated into one field.
    """
    result = []  # type: List[intermediate.TypeAnnotationUnion]
    observed = set()  # type: Set[str]

    def register(type_anno: intermediate.TypeAnnotationUnion) -> None:
        """Register what ``type_anno`` needs, its items first."""
        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            register(type_anno.items)
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            for item_type_anno in type_anno.items:
                register(item_type_anno)
        else:
            # NOTE (mristin):
            # An atomic value de/serializes through a function of its own, so
            # it needs no field.
            return

        moniker = csharp_common.type_moniker(type_anno)
        if moniker not in observed:
            observed.add(moniker)
            result.append(type_anno)

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            register(intermediate.beneath_optional(prop.type_annotation))

    return result


def _generate_deserializer_field(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """Generate the cached de-serializer of the list or the tuple ``type_anno``."""
    name = _deserializer_name(type_anno)
    value_type = csharp_common.generate_type(type_anno)

    composition: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_type = csharp_common.generate_type(type_anno.items)
        composition = Stripped(
            f"""\
AsArrayOf<{item_type}>(
{I}{_deserializer_expr(type_anno.items)})"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_types_joined = ", ".join(
            csharp_common.generate_type(item_type_anno)
            for item_type_anno in type_anno.items
        )
        item_deserializers_joined = ",\n".join(
            _deserializer_expr(item_type_anno) for item_type_anno in type_anno.items
        )
        composition = Stripped(
            f"""\
AsTuple{len(type_anno.items)}<{item_types_joined}>(
{I}{indent_but_first_line(item_deserializers_joined, I)})"""
        )

    else:
        raise AssertionError(
            f"Expected a list or a tuple type annotation, but got {type_anno}"
        )

    declaration = f"private static readonly Deserializer<{value_type}> {name} = ("
    if len(declaration) + len(I) * 3 > _MAX_LINE_LENGTH:
        declaration = f"""\
private static readonly Deserializer<
{I}{value_type}
> {name} = ("""

    return Stripped(
        f"""\
{declaration}
{I}{indent_but_first_line(composition, I)});"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_from_method_for_class(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the deserialization method for a concrete class."""
    errors = []  # type: List[Error]

    name = csharp_naming.class_name(cls.name)

    blocks = [
        Stripped(
            f"""\
error = null;

Nodes.JsonObject? obj = node as Nodes.JsonObject;
if (obj == null)
{{
{I}error = new Reporting.Error(
{II}$"Expected a JsonObject representing {name}, but got {{Describe(node)}}");
{I}return default!;
}}"""
        )
    ]  # type: List[Stripped]

    # region Initialize argument variables to null

    args_init_writer = io.StringIO()
    for i, arg in enumerate(cls.constructor.arguments):
        arg_var = csharp_naming.variable_name(Identifier(f"the_{arg.name}"))
        arg_type = csharp_common.generate_type(arg.type_annotation)

        # NOTE (mristin):
        # We make all the argument variables optional since we switch over
        # the properties. Even the mandatory constructor arguments can be omitted
        # during an invalid deserialization!
        if not arg_type.endswith("?"):
            arg_type = Stripped(f"{arg_type}?")

        if i > 0:
            args_init_writer.write("\n")
        args_init_writer.write(f"{arg_type} {arg_var} = null;")

    if len(cls.constructor.arguments) > 0:
        blocks.append(Stripped(args_init_writer.getvalue()))

    if cls.serialization.with_model_type:
        blocks.append(Stripped("string? modelType = null;"))

    # endregion

    # region Switch on property name

    cases = []  # type: List[Stripped]
    for arg in cls.constructor.arguments:
        json_name = cls.properties_by_name[arg.name].json_name
        assert not csharp_common.needs_escaping(json_name)

        target_var = csharp_naming.variable_name(Identifier(f"the_{arg.name}"))

        deserializer_expr = _deserializer_expr(
            intermediate.beneath_optional(arg.type_annotation)
        )

        cases.append(
            Stripped(
                f"""\
case {csharp_common.string_literal(json_name)}:
{I}{target_var} = {deserializer_expr}(
{II}keyValue.Value, out error);
{I}break;"""
            )
        )

    if cls.serialization.with_model_type:
        model_type = naming.json_model_type(cls.name)

        cases.append(
            Stripped(
                f"""\
case "modelType":
{I}modelType = StringFrom(
{II}keyValue.Value, out error);
{I}if (error == null && modelType != "{model_type}")
{I}{{
{II}error = new Reporting.Error(
{III}"Expected the model type '{model_type}', " +
{III}$"but got {{modelType}}");
{I}}}
{I}break;"""
            )
        )

    cases.append(
        Stripped(
            f"""\
default:
{I}error = new Reporting.Error(
{II}$"Unexpected property: {{keyValue.Key}}");
{I}return default!;"""
        )
    )

    cases_joined = "\n".join(textwrap.indent(case_block, II) for case_block in cases)

    # NOTE (mristin):
    # A class without a single property switches on nothing but its ``default``,
    # which returns, so the marking below would be unreachable code.
    mark_the_property = (
        ""
        if len(cases) == 1
        else f"""\

{I}if (error != null)
{I}{{
{II}error.PrependSegment(
{III}new Reporting.NameSegment(
{IIII}keyValue.Key));
{II}return default!;
{I}}}"""
    )

    # NOTE (mristin):
    # The error is marked with the name of the property once, here, instead of
    # in every single ``case``: a ``case`` is matched exactly when
    # ``keyValue.Key`` is its literal, so the two are one and the same name.
    # The ``default`` returns before this, as its message already names
    # the unexpected property.
    blocks.append(
        Stripped(
            f"""\
foreach (var keyValue in obj)
{{
{I}switch (keyValue.Key)
{I}{{
{cases_joined}
{I}}}
{mark_the_property}
}}"""
        )
    )

    # endregion

    # region Check required

    required_checks = []  # type: List[Stripped]
    for arg in cls.constructor.arguments:
        if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        arg_var = csharp_naming.variable_name(Identifier(f"the_{arg.name}"))
        json_name = cls.properties_by_name[arg.name].json_name
        assert not csharp_common.needs_escaping(json_name)

        required_checks.append(
            Stripped(
                f"""\
if ({arg_var} == null)
{{
{I}error = new Reporting.Error(
{II}"Required property \\"{json_name}\\" is missing");
{I}return default!;
}}"""
            )
        )

    if cls.serialization.with_model_type:
        required_checks.append(
            Stripped(
                f"""\
if (modelType == null)
{{
{I}error = new Reporting.Error(
{II}"Required property \\"modelType\\" is missing");
{I}return default!;
}}"""
            )
        )

    if len(required_checks) > 0:
        blocks.append(Stripped("\n\n".join(required_checks)))

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

            # NOTE (mristin):
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
internal static Aas.{name} {name}From(
{I}Nodes.JsonNode? node,
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
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the implementation of the deserialization."""
    errors = []  # type: List[Error]

    blocks = [_generate_describe_helper()]  # type: List[Stripped]

    for primitive_type in intermediate.PrimitiveType:
        blocks.append(_generate_primitive_converter(primitive_type))

    # region Shared combinators and the de-serializers they compose

    # NOTE (mristin):
    # Only a list and a tuple are composed, so a model without any of them pays
    # for neither the delegate nor the combinators. The gating follows what is
    # actually called: every other de-serializer is a function emitted for
    # the very type it de-serializes, and hence can never be missing.
    composed_types = _composed_types_in_initialization_order(symbol_table)

    if len(composed_types) > 0:
        blocks.append(_generate_deserializer_delegate())

    if any(
        isinstance(type_anno, intermediate.ListTypeAnnotation)
        for type_anno in composed_types
    ):
        blocks.append(_generate_as_array_of_helper())

    tuple_arities = sorted(
        {
            len(type_anno.items)
            for type_anno in composed_types
            if isinstance(type_anno, intermediate.TupleTypeAnnotation)
        }
    )
    for arity in tuple_arities:
        blocks.append(_generate_as_tuple_helper(arity))

    if any(our_type.interface is not None for our_type in symbol_table.classes):
        blocks.append(_generate_model_type_from_helper())

    for type_anno in composed_types:
        blocks.append(_generate_deserializer_field(type_anno))

    # endregion

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
///
/// Every value is de-serialized through one and the same shape,
/// <c>Deserializer&lt;T&gt;</c>, so that the de-serialization of a list or of
/// a tuple can be composed out of the de-serialization of its items. A value
/// is returned as a plain <c>T</c>, meaningless unless the <c>error</c> is
/// null, since a <c>T?</c> can not be written down for an unconstrained
/// <c>T</c>.
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
{I}Aas.{name} result = DeserializeImplementation.{name}From(
{II}node,
{II}out Reporting.Error? error);
{I}if (error != null)
{I}{{
{II}throw new Jsonization.Exception(
{III}Reporting.GenerateJsonPath(error.PathSegments),
{III}error.Cause);
{I}}}
{I}return result;
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


def _serializer_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Name the field holding the serializer of a list or of a tuple.

    The moniker comes last, after an underscore, so that the name of a field
    can never coincide with one of the ``...ToJsonValue`` functions: those are
    keyed by one of our symbols, and a symbol is named through
    :py:func:`aas_core_codegen.naming.capitalized_camel_case`, which never
    emits an underscore.
    """
    return Identifier(f"Serialize_{csharp_common.type_moniker(type_anno)}")


def _atomic_serializer_name(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Identifier:
    """
    Name the field holding the serializer of the atomic ``type_anno``.

    The name is keyed by the serializer and not by the type: every class goes
    through ``TransformIClass`` and a constrained primitive through
    the ``ToJsonValue`` of its constrainee, so the types which share
    a serializer share the field as well.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return Identifier(
            f"Serialize_{csharp_common.PRIMITIVE_TYPE_TO_MONIKER[primitive_type]}"
        )

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Expected an atomic type annotation, but got {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return Identifier(f"Serialize_{csharp_naming.enum_name(our_type.name)}")

    if isinstance(our_type, intermediate.NamedUnion):
        return Identifier("Serialize_IUnion")

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class, but got {our_type}"

    return Identifier("Serialize_IClass")


def _serializer_expr(type_anno: intermediate.TypeAnnotationUnion) -> Stripped:
    """
    Generate the expression serializing a value of ``type_anno``.

    An atomic value is serialized by a function named after its type, and
    a list or a tuple by the cached field composing the serializers of its
    items. Either way the expression is a plain name, so that a call site
    neither allocates a delegate nor composes anything.
    """
    if isinstance(
        type_anno,
        (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
    ):
        return Stripped(_serializer_name(type_anno))

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        return Stripped("ToJsonValue")

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Expected an atomic type annotation, but got {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        name = csharp_naming.enum_name(our_type.name)
        return Stripped(f"Serialize.{name}ToJsonValue")

    if isinstance(our_type, intermediate.ConstrainedPrimitive):
        return Stripped("ToJsonValue")

    if isinstance(our_type, intermediate.NamedUnion):
        return Stripped("TransformIUnion")

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    )

    return Stripped("TransformIClass")


def _generate_atomic_serializer_helpers(
    primitive_types: Set[intermediate.PrimitiveType],
) -> List[Stripped]:
    """
    Generate ``ToJsonValue`` overloads so every composed atomic item is a bare name.

    ``SerializeList`` and ``SerializeTuple{N}`` take a :py:class:`Serializer` per
    item, and :py:func:`_serializer_expr` names one with a plain identifier, so
    that the field composing them converts the delegates once and a call site
    allocates none. An item whose serialization is already a single call to one
    of our own methods (the existing ``Transformer.ToJsonValue``, a class's
    ``TransformIClass``, an enumeration's ``...ToJsonValue``) can therefore be
    named directly, with no wrapping lambda.

    ``bool``, ``float`` (``double``), ``str`` and ``bytearray`` (the latter
    additionally composing a base64 encoding step) route through the BCL's
    ``Nodes.JsonValue.Create`` at a direct call site, which can NOT be named
    directly -- verified against the compiler: ``Nodes.JsonValue.Create`` is
    a *generic* method with an optional second parameter
    (``Create<T>(T value, JsonNodeOptions? options = null)``), and the C#
    compiler refuses to convert a method group to a delegate in that
    combination (CS1503), regardless of whether ``T`` would otherwise be
    inferable from the target delegate.

    So we add more overloads of the already-existing, single-purpose,
    non-generic ``Transformer.ToJsonValue`` here -- one per such primitive
    type -- exactly so that *an overload of ours*, not
    ``Nodes.JsonValue.Create`` itself, can be named; unlike a generic method,
    a plain overload set is resolved by the compiler purely from the
    (already-known, at every composition) target delegate type, which is
    exactly the case that fails for ``Nodes.JsonValue.Create`` -- also
    verified against the compiler.

    Only the overloads which are actually composed are emitted. The ``long``
    overload is not among them, as it is emitted unconditionally: a direct
    call site converting an integer property needs it as well.
    """
    result = []  # type: List[Stripped]

    for primitive_type, csharp_type, conversion_expr in (
        (intermediate.PrimitiveType.BOOL, "bool", "Nodes.JsonValue.Create(that)"),
        (intermediate.PrimitiveType.STR, "string", "Nodes.JsonValue.Create(that)"),
        (
            intermediate.PrimitiveType.BYTEARRAY,
            "byte[]",
            "Nodes.JsonValue.Create(System.Convert.ToBase64String(that))",
        ),
    ):
        if primitive_type not in primitive_types:
            continue

        result.append(
            Stripped(
                f"""\
/// <summary>
/// Convert <paramref name="that" /> to a JSON value.
/// </summary>
private static Nodes.JsonValue ToJsonValue({csharp_type} that)
{{
{I}return {conversion_expr};
}}"""
            )
        )

    return result


def _property_serializer_type_annotations(
    symbol_table: intermediate.SymbolTable,
) -> List[intermediate.TypeAnnotationUnion]:
    """
    Collect the atomic types which a property is serialized as.

    Each of them gets a cached serializer of its own, so that
    ``SetProperty`` is handed a field and never a method group -- a method
    group converted to a delegate allocates at every call under
    ``LangVersion 8``.

    A list and a tuple already have such a field (see
    :py:func:`_generate_serializer_field`), so neither is collected here.

    The types are de-duplicated by their serializer, and not by themselves:
    every class goes through ``TransformIClass``, and a constrained primitive
    through the ``ToJsonValue`` of its constrainee, so one field serves them
    all. ``Serializer<in T>`` is contravariant, which is what lets the field
    of ``IClass`` be handed over where one of a more specific interface is
    expected.
    """
    result = []  # type: List[intermediate.TypeAnnotationUnion]
    observed = set()  # type: Set[Identifier]

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(
                type_anno,
                (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
            ):
                continue

            name = _atomic_serializer_name(type_anno)
            if name in observed:
                continue

            observed.add(name)
            result.append(type_anno)

    return result


def _property_primitive_types(
    type_annos: Sequence[intermediate.TypeAnnotationUnion],
) -> Set[intermediate.PrimitiveType]:
    """
    Collect the primitive types among ``type_annos``.

    These need a ``ToJsonValue`` overload of their own, exactly as the items
    of a list or of a tuple do.
    """
    result = set()  # type: Set[intermediate.PrimitiveType]

    for type_anno in type_annos:
        primitive_type = intermediate.try_primitive_type(type_anno)
        if primitive_type is not None:
            result.add(primitive_type)

    return result


def _composed_primitive_types(
    composed_types: Sequence[intermediate.TypeAnnotationUnion],
) -> Set[intermediate.PrimitiveType]:
    """
    Collect the primitive types serialized as an item of a list or of a tuple.

    Only these need a ``ToJsonValue`` overload of their own -- see
    :py:func:`_generate_atomic_serializer_helpers`.
    """
    result = set()  # type: Set[intermediate.PrimitiveType]

    def register(item_type_anno: intermediate.TypeAnnotationUnion) -> None:
        """Register the primitive type of ``item_type_anno``, if it has one."""
        if isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
            result.add(item_type_anno.a_type)
        elif isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
            item_type_anno.our_type, intermediate.ConstrainedPrimitive
        ):
            result.add(item_type_anno.our_type.constrainee)

    for composed_type in composed_types:
        if isinstance(composed_type, intermediate.ListTypeAnnotation):
            register(composed_type.items)
        elif isinstance(composed_type, intermediate.TupleTypeAnnotation):
            for item_type_anno in composed_type.items:
                register(item_type_anno)
        else:
            raise AssertionError(
                f"Expected a list or a tuple type annotation, "
                f"but got {composed_type}"
            )

    return result


def _generate_serializer_delegate() -> Stripped:
    """Generate the delegate which every serialization step implements."""
    return Stripped(
        """\
/// <summary>
/// Serialize <paramref name="that" /> into a JSON value.
/// </summary>
/// <remarks>
/// This is the shape shared by every serialization step, so that the steps
/// can be composed. Unlike the XML side, no combinator is needed to frame
/// the value -- a JSON value stands on its own -- so the only composition
/// is over the items of a list or of a tuple.
/// </remarks>
/// <typeparam name="T">Type of the value to be serialized</typeparam>
private delegate Nodes.JsonNode? Serializer<in T>(T that);"""
    )


def _generate_transform_iunion_helper() -> Stripped:
    """Generate a single serializer shared by every named union."""
    return Stripped(
        f"""\
/// <summary>
/// Serialize the named union <paramref name="that" /> into a JSON object.
/// </summary>
/// <remarks>
/// A named union is not an <see cref="Aas.IClass" />, so it can not be
/// dispatched by <see cref="TransformIClass" />. Dispatching over the
/// common, non-generic <see cref="Aas.IUnion" /> means we need only this one
/// serializer for *all* named unions, and not one per union.
///
/// Should a named union ever be allowed to flatten primitive or enumeration
/// alternatives, only the body of this method has to change (to dispatch on
/// the underlying value's kind) -- every call site stays the same.
/// </remarks>
private static Nodes.JsonObject TransformIUnion(Aas.IUnion that)
{{
{I}return TransformIClass(that.Underlying);
}}"""
    )


def _generate_serialize_list_helper() -> Stripped:
    """Generate the combinator composing the serializer of a list."""
    return Stripped(
        f"""\
/// <summary>
/// Compose the serializer of a list whose items are serialized with
/// <paramref name="serializeItem" />.
/// </summary>
/// <remarks>
/// This is shared by all the list-typed properties. The composition is
/// performed once, when the field holding the result is initialized, so
/// serializing a list allocates nothing besides the JSON array itself.
///
/// The parameter is a <c>List</c> rather than an <c>IEnumerable</c> so that
/// the iteration does not box the enumerator -- which is also the type that
/// every list-typed property actually has.
/// </remarks>
/// <typeparam name="T">Type of a single list item</typeparam>
private static Serializer<List<T>> SerializeList<T>(
{I}Serializer<T> serializeItem)
{{
{I}return (that) =>
{I}{{
{II}var result = new Nodes.JsonArray();
{II}int i = 0;
{II}foreach (T item in that)
{II}{{
{III}try
{III}{{
{IIII}result.Add(serializeItem(item));
{III}}}
{III}catch (SerializationFailure failure)
{III}{{
{IIII}failure.Error.PrependSegment(
{IIIII}new Reporting.IndexSegment(i));
{IIII}throw;
{III}}}
{III}i++;
{II}}}
{II}return result;
{I}}};
}}"""
    )


def _atomic_serializer_value_type(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """
    Generate the type of the value which the serializer of ``type_anno`` accepts.

    The type is keyed by the serializer, just like
    :py:func:`_atomic_serializer_name` is: the serializer of a class accepts
    any ``IClass``, and the one of a named union any ``IUnion``, as one field
    serves them all. ``Serializer<in T>`` is contravariant, so a field of
    the general type can be handed over where one of a specific type is
    expected -- but not the other way around, which is why the type can not
    simply be the one of the property.
    """
    our_type = (
        type_anno.our_type
        if isinstance(type_anno, intermediate.OurTypeAnnotation)
        else None
    )

    if isinstance(our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)):
        return Stripped("Aas.IClass")

    if isinstance(our_type, intermediate.NamedUnion):
        return Stripped("Aas.IUnion")

    return csharp_common.generate_type(type_anno)


def _generate_atomic_serializer_field(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """
    Generate the cached serializer of the atomic ``type_anno``.

    The field exists so that ``SetProperty`` is handed a delegate which was
    created once, and not a method group, which would be converted to
    a delegate -- and hence allocated -- at every call under
    ``LangVersion 8``.
    """
    name = _atomic_serializer_name(type_anno)
    value_type = _atomic_serializer_value_type(type_anno)
    function = _serializer_expr(type_anno)

    declaration = Stripped(f"private static readonly Serializer<{value_type}> {name} =")
    if len(declaration) + len(I) * 3 + len(f" {function};") <= _MAX_LINE_LENGTH:
        return Stripped(f"{declaration} {function};")

    return Stripped(
        f"""\
{declaration}
{I}{function};"""
    )


def _generate_set_property_helper() -> Stripped:
    """
    Generate the framer which sets a property and names it on the error path.

    Every property goes through it, and not only the ones which can fail
    today: the property is recorded here and nowhere below, as nothing below
    knows through which property the value was reached, so a serializer which
    grows a new way of failing would quietly lose the way to the culprit.

    An optional property keeps the ``if`` at the call site. C# has two kinds
    of optional -- a reference type tested against ``null`` and
    a ``System.Nullable`` tested with ``HasValue`` and unwrapped with
    ``Value`` -- so a framer of its own would have to come in two overloads to
    say what one ``if`` already says.
    """
    return Stripped(
        f"""\
/// <summary>
/// Set the property <paramref name="jsonName" /> of
/// <paramref name="result" /> to <paramref name="that" />, serialized by
/// <paramref name="serialize" />.
/// </summary>
/// <remarks>
/// <paramref name="propertyName" /> names the property on the path of
/// a failure. It is the C# property, and not the JSON one: a serialization
/// error is reported on an <em>instance</em>, which the caller holds, and
/// not on a document which has not been written yet.
/// </remarks>
/// <typeparam name="T">Type of the value to serialize</typeparam>
private static void SetProperty<T>(
{I}Nodes.JsonObject result,
{I}string jsonName,
{I}string propertyName,
{I}T that,
{I}Serializer<T> serialize)
{{
{I}try
{I}{{
{II}result[jsonName] = serialize(that);
{I}}}
{I}catch (SerializationFailure failure)
{I}{{
{II}failure.Error.PrependSegment(
{III}new Reporting.NameSegment(propertyName));
{II}throw;
{I}}}
}}"""
    )


def _generate_serializer_field(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """Generate the cached serializer of the list or the tuple ``type_anno``."""
    name = _serializer_name(type_anno)
    value_type = csharp_common.generate_type(type_anno)

    composition: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_type = csharp_common.generate_type(type_anno.items)
        composition = Stripped(
            f"""\
SerializeList<{item_type}>(
{I}{_serializer_expr(type_anno.items)})"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_types_joined = ", ".join(
            csharp_common.generate_type(item_type_anno)
            for item_type_anno in type_anno.items
        )
        item_serializers_joined = ",\n".join(
            _serializer_expr(item_type_anno) for item_type_anno in type_anno.items
        )
        composition = Stripped(
            f"""\
SerializeTuple{len(type_anno.items)}<{item_types_joined}>(
{I}{indent_but_first_line(item_serializers_joined, I)})"""
        )

    else:
        raise AssertionError(
            f"Expected a list or a tuple type annotation, but got {type_anno}"
        )

    declaration = f"private static readonly Serializer<{value_type}> {name} = ("
    if len(declaration) + len(I) * 3 > _MAX_LINE_LENGTH:
        declaration = f"""\
private static readonly Serializer<
{I}{value_type}
> {name} = ("""

    return Stripped(
        f"""\
{declaration}
{I}{indent_but_first_line(composition, I)});"""
    )


@require(lambda arity: arity > 0)
def _generate_serialize_tuple_helper(arity: int) -> Stripped:
    """Generate the combinator composing the serializer of a tuple of ``arity``."""
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(type_params)

    if arity == 1:
        tuple_type = f"System.ValueTuple<{type_params[0]}>"
    else:
        tuple_type = f"({type_params_joined})"

    params_joined = ",\n".join(
        f"Serializer<T{i}> serializeItem{i}" for i in range(arity)
    )

    add_stmts_joined = "\n".join(
        f"""\
try
{{
{I}result.Add(serializeItem{i}(that.Item{i + 1}));
}}
catch (SerializationFailure failure)
{{
{I}failure.Error.PrependSegment(
{II}new Reporting.IndexSegment({i}));
{I}throw;
}}"""
        for i in range(arity)
    )

    function_name = f"SerializeTuple{arity}"

    return Stripped(
        f"""\
/// <summary>
/// Compose the serializer of a tuple of {arity} item(s), whose items are
/// serialized with <paramref name="serializeItem0" />,
/// <paramref name="serializeItem1" />, *etc.*
/// </summary>
/// <remarks>
/// This is shared by all the tuple-typed properties of arity {arity}. Just
/// like for a list, the composition is performed once, when the field
/// holding the result is initialized.
/// </remarks>
private static Serializer<{tuple_type}> {function_name}<{type_params_joined}>(
{I}{indent_but_first_line(params_joined, I)})
{{
{I}return (that) =>
{I}{{
{II}var result = new Nodes.JsonArray();
{II}{indent_but_first_line(add_stmts_joined, II)}
{II}return result;
{I}}};
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transform_property(
    prop: intermediate.Property,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the snippet to transform a property into a JSON node."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    name = csharp_naming.property_name(prop.name)
    prop_literal = csharp_common.string_literal(prop.json_name)

    # NOTE (mristin):
    # A serialization error is reported on an *instance*, which the caller
    # holds, and not on a document which has not been written yet -- so
    # the path names the C# property, and not the JSON one.
    segment_literal = csharp_common.string_literal(name)

    # NOTE (mristin):
    # An optional of a value type, such as an enumeration or a tuple, is
    # a ``System.Nullable`` of that type, and not the type itself, so it has to be
    # unwrapped before it can be converted. Every other optional property is of
    # a reference type, which needs no unwrapping.
    source_expr = Stripped(f"that.{name}")
    if isinstance(
        prop.type_annotation, intermediate.OptionalTypeAnnotation
    ) and csharp_common.is_value_type(type_anno):
        source_expr = Stripped(f"that.{name}.Value")

    serializer_name: Identifier

    if isinstance(
        type_anno,
        (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
    ):
        serializer_name = _atomic_serializer_name(type_anno)

    elif isinstance(
        type_anno,
        (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
    ):
        item_type_annos = (
            [type_anno.items]
            if isinstance(type_anno, intermediate.ListTypeAnnotation)
            else list(type_anno.items)
        )

        for item_type_anno in item_type_annos:
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"Expected an atomic item (a primitive, a constrained primitive, "
                f"an enumeration, a class or a named union) of {type_anno}, "
                f"but got {item_type_anno}. "
                f"This should have already been verified in "
                f"intermediate._translate._verify_only_simple_type_patterns."
            )

        serializer_name = _serializer_name(type_anno)

    else:
        assert_never(type_anno)

    arguments = [
        Stripped("result"),
        prop_literal,
        segment_literal,
        source_expr,
        Stripped(serializer_name),
    ]

    joined_arguments = ", ".join(arguments)
    one_liner = f"SetProperty({joined_arguments});"

    # NOTE (mristin):
    # The call lands four levels deep -- the namespace, the class, the nested
    # transformer and its method -- and one level deeper yet if the property is
    # optional, as it is then guarded by an ``if``.
    indention = len(I) * (
        5
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        else 4
    )

    serialize_block: Stripped
    if len(one_liner) + indention <= _MAX_LINE_LENGTH:
        serialize_block = Stripped(one_liner)
    else:
        arguments_block = ",\n".join(arguments)

        # We can not use textwrap due to indent_but_first_line.
        serialize_block = Stripped(
            f"""\
SetProperty(
{I}{indent_but_first_line(arguments_block, I)});"""
        )

    if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return serialize_block, None

    condition = (
        f"that.{name}.HasValue"
        if csharp_common.is_value_type(type_anno)
        else f"that.{name} != null"
    )

    return (
        Stripped(
            f"""\
if ({condition})
{{
{I}{indent_but_first_line(serialize_block, I)}
}}"""
        ),
        None,
    )


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


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transformer(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a transformer which transforms instances of the meta-model to JSON."""
    errors = []  # type: List[Error]

    blocks = [
        Stripped(
            """\
/// <summary>
/// Dispatch the serialization over the run-time type of an instance.
/// </summary>
/// <remarks>
/// The transformer carries no state, so a single instance serves the whole
/// program. No field initializer reads it, only
/// <see cref="TransformIClass" /> does, so it does not matter where among
/// the serializers it is initialized.
/// </remarks>
[CodeAnalysis.SuppressMessage("ReSharper", "InconsistentNaming")]
private static readonly Transformer _instance = new Transformer();"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Serialize <paramref name="that" /> into a JSON object.
/// </summary>
/// <remarks>
/// Which JSON object that is, is decided by the run-time type of
/// <paramref name="that" />, so this one serializer serves every abstract
/// class and every concrete class with descendants, as well as the item of
/// a list or of a tuple of any of them.
/// </remarks>
internal static Nodes.JsonObject TransformIClass(Aas.IClass that)
{{
{I}return _instance.Transform(that);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Convert <paramref name="that" /> 64-bit long integer to a JSON value.
/// </summary>
/// <param name="that">value to be converted</param>
/// <exception name="SerializationFailure">
/// Thrown if <paramref name="that" /> lies outside the range where it can be
/// exactly represented as a 64-bit floating-point number, which is what
/// the JSON de-serializers of the other languages read a number into.
/// </exception>
[CodeAnalysis.SuppressMessage("ReSharper", "UnusedMember.Local")]
private static Nodes.JsonValue ToJsonValue(long that)
{{
{I}if (that < -9007199254740991L || that > 9007199254740991L)
{I}{{
{II}throw new SerializationFailure(
{III}new Reporting.Error(
{IIII}"The integer can not be serialized to JSON as it is outside " +
{IIII}$"the range [-2^53 + 1, 2^53 - 1]: {{that}}"));
{I}}}
{I}return Nodes.JsonValue.Create(that);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Convert <paramref name="that" /> 64-bit floating-point number to a JSON
/// value.
/// </summary>
/// <param name="that">value to be converted</param>
/// <exception name="SerializationFailure">
/// Thrown if <paramref name="that" /> is not finite. JSON knows neither
/// an infinity nor a not-a-number, so we refuse them here instead of
/// leaving it to <c>System.Text.Json</c>, which throws much later -- when
/// the caller writes the document out -- and says nothing about where
/// the offending value sat.
/// </exception>
[CodeAnalysis.SuppressMessage("ReSharper", "UnusedMember.Local")]
private static Nodes.JsonValue ToJsonValue(double that)
{{
{I}if (!System.Double.IsFinite(that))
{I}{{
{II}throw new SerializationFailure(
{III}new Reporting.Error(
{IIII}"JSON knows neither an infinity nor a not-a-number, so " +
{IIII}$"the value can not be serialized: {{that}}"));
{I}}}
{I}return Nodes.JsonValue.Create(that);
}}"""
        ),
    ]  # type: List[Stripped]

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_transform_iunion_helper())

    # NOTE (mristin):
    # The gating follows the call graph: only a list and a tuple are composed,
    # so a model with neither pays for neither the delegate nor the
    # combinators. Every atomic value is serialized by a function emitted for
    # the very type it serializes, and hence can never be missing.
    composed_types = _composed_types_in_initialization_order(symbol_table)

    # NOTE (mristin):
    # Every property is handed a cached serializer as well, so the delegate
    # and the ``ToJsonValue`` overloads are needed as soon as the model has
    # a single property -- not only where a list or a tuple composes them.
    property_types = _property_serializer_type_annotations(symbol_table)

    has_properties = any(
        len(cls.properties) > 0 for cls in symbol_table.concrete_classes
    )

    if has_properties:
        blocks.append(_generate_serializer_delegate())

        blocks.extend(
            _generate_atomic_serializer_helpers(
                primitive_types=(
                    _composed_primitive_types(composed_types)
                    | _property_primitive_types(property_types)
                )
            )
        )

    if len(composed_types) > 0:
        if any(
            isinstance(composed_type, intermediate.ListTypeAnnotation)
            for composed_type in composed_types
        ):
            blocks.append(_generate_serialize_list_helper())

        for arity in intermediate.tuple_arities(symbol_table):
            blocks.append(_generate_serialize_tuple_helper(arity))

        for composed_type in composed_types:
            blocks.append(_generate_serializer_field(composed_type))

    # NOTE (mristin):
    for property_type in property_types:
        blocks.append(_generate_atomic_serializer_field(property_type))

    if has_properties:
        blocks.append(_generate_set_property_helper())

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
            block, cls_errors = _generate_transform_for_class(
                cls=our_type,
            )
            if cls_errors is not None:
                errors.extend(cls_errors)
            else:
                assert block is not None
                blocks.append(block)
        elif isinstance(our_type, intermediate.NamedUnion):
            # A named union is never double-dispatched here directly -- it
            # is unwrapped by the single shared ``TransformIUnion`` instead
            # (see :py:func:`_generate_transform_iunion_helper`).
            pass

        else:
            assert_never(our_type)

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
            f"""\
/// <summary>
/// Serialize an instance of the meta-model into a JSON object.
/// </summary>
/// <exception cref="SerializationException">
/// Thrown when a value within <paramref name="that" /> instance can not be
/// represented in JSON
/// </exception>
public static Nodes.JsonObject ToJsonObject(Aas.IClass that)
{{
{I}try
{I}{{
{II}return Transformer.TransformIClass(that);
{I}}}
{I}catch (SerializationFailure failure)
{I}{{
{II}throw new SerializationException(
{III}Reporting.GenerateCSharpPath(failure.Error.PathSegments),
{III}failure.Error.Cause);
{I}}}
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
/// <exception cref="SerializationFailure">
/// Thrown when <paramref name="that" /> is no literal of {name} at all.
/// <see cref="ToJsonObject" /> converts it, so a caller which serializes
/// a whole instance catches <see cref="SerializationException" /> instead.
/// </exception>
public static Nodes.JsonValue {name}ToJsonValue(Aas.{name} that)
{{
{I}string? text = Stringification.ToString(that);
{I}return Nodes.JsonValue.Create(text)
{II}?? throw new SerializationFailure(
{III}new Reporting.Error(
{IIII}$"Invalid {name}: {{that}}"));
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
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code for JSON de/serialization.

    The ``namespace`` defines the AAS C# namespace.
    """
    errors = []  # type: List[Error]

    deserialize_impl_block, deserialize_impl_errors = _generate_deserialize_impl(
        symbol_table=symbol_table
    )
    if deserialize_impl_errors is not None:
        errors.extend(deserialize_impl_errors)

    deserialize_block = _generate_deserialize(symbol_table=symbol_table)

    transformer_block, transformer_errors = _generate_transformer(
        symbol_table=symbol_table
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
}}

/// <summary>
/// Represent a critical error during the serialization.
/// </summary>
public class SerializationException : System.Exception
{{
{I}public readonly string Path;
{I}public readonly string Cause;
{I}public SerializationException(string path, string cause)
{II}: base($"{{cause}} at: {{path}}")
{I}{{
{II}Path = path;
{II}Cause = cause;
{I}}}
}}

/// <summary>
/// Signal a failure of the serialization, carrying the path to the culprit.
/// </summary>
/// <remarks>
/// The path is built as the stack unwinds -- every container prepends the one
/// segment it knows, the property its name and the list the index of the item
/// -- which is why this can not be a <see cref="SerializationException" />
/// already: that one renders its message in its constructor, so its path has
/// to be complete by then. <see cref="Serialize.ToJsonObject" /> renders and
/// converts.
/// </remarks>
internal class SerializationFailure : System.Exception
{{
{I}public readonly Reporting.Error Error;
{I}public SerializationFailure(Reporting.Error error)
{II}: base(error.Cause)
{I}{{
{II}Error = error;
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
