"""Generate code for JSON de/serialization."""

import io
import textwrap
from typing import Final, List, Mapping, Optional, Sequence, Set, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)

#: Maximal length of a generated line before a call is broken over two lines
_MAX_LINE_LENGTH: Final[int] = 100

#: Indentation, in characters, of the body of a function of
#: the de-serialization implementation or of the transformer. The body sits four
#: levels deep either way: the class ``Jsonization``, the class
#: (``_DeserializeImplementation`` or ``_Transformer``), the function and finally
#: its body.
_FUNCTION_BODY_INDENTATION: Final[int] = len(I) * 4

# region De-serialization

#: Indentation, in characters, of the body of a ``case`` of a property loop.
#: The body sits seven levels deep: the class ``Jsonization``, the class
#: ``_DeserializeImplementation``, the function, its body, the loop body,
#: the ``switch`` body and finally the ``case`` body.
_CASE_BODY_INDENTATION: Final[int] = len(I) * 7

#: Name of the class through which the de-serialization is dispatched. A method
#: reference to one of its static parsers has to be qualified by it.
_DESERIALIZE_IMPL_NAME: Final[Identifier] = Identifier("_DeserializeImplementation")


# region Names of the generated parsers


_PARSE_METHOD_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "tryBooleanFrom",
    intermediate.PrimitiveType.INT: "tryLongFrom",
    intermediate.PrimitiveType.FLOAT: "tryDoubleFrom",
    intermediate.PrimitiveType.STR: "tryStringFrom",
    intermediate.PrimitiveType.BYTEARRAY: "tryBytesFrom",
}
assert all(
    literal in _PARSE_METHOD_BY_PRIMITIVE_TYPE for literal in intermediate.PrimitiveType
)


def _parse_method_for_atomic_value(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Identifier:
    """Determine the parse method for deserializing an atomic non-optional value."""
    parse_method: Optional[str] = None

    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        parse_method = _PARSE_METHOD_BY_PRIMITIVE_TYPE[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type
        if isinstance(our_type, intermediate.Enumeration):
            enum_name = java_naming.enum_name(our_type.name)
            parse_method = f"try{enum_name}From"

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            parse_method = _PARSE_METHOD_BY_PRIMITIVE_TYPE[our_type.constrainee]

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if our_type.interface is not None:
                interface_name = java_naming.interface_name(our_type.interface.name)
                parse_method = f"try{interface_name}From"
            else:
                cls_name = java_naming.class_name(our_type.name)
                parse_method = f"try{cls_name}From"

        elif isinstance(our_type, intermediate.NamedUnion):
            union_name = java_naming.union_name(our_type.name)
            parse_method = f"try{union_name}From"

        else:
            assert_never(our_type)

    elif isinstance(type_annotation, intermediate.JsonValueTypeAnnotation):
        parse_method = "tryJsonValueFrom"

    elif isinstance(type_annotation, intermediate.JsonArrayTypeAnnotation):
        parse_method = "tryJsonArrayFrom"

    elif isinstance(type_annotation, intermediate.JsonObjectTypeAnnotation):
        parse_method = "tryJsonObjectFrom"

    else:
        assert_never(type_annotation)

    return Identifier(parse_method)


def _parse_method_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Name the function parsing a value of ``type_anno`` from a JSON node.

    An atomic value already has a function of its own to be named after. A list,
    a set and a tuple do not, so they are composed out of the parsers of their
    items and named by the moniker of the type (see
    :py:func:`aas_core_codegen.java.common.type_moniker`).
    """
    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        return Identifier(f"parse{java_common.type_moniker(type_anno)}")

    assert isinstance(
        type_anno, intermediate.AtomicTypeAnnotationAsTuple
    ), f"Expected an atomic type annotation, but got: {type_anno}"

    return _parse_method_for_atomic_value(type_anno)


def _item_parser_reference(type_anno: intermediate.TypeAnnotationUnion) -> Stripped:
    """
    Reference the parser of a single item of a list or of a tuple.

    A method reference to a static method captures nothing, so the JVM
    instantiates it once and caches it at the call site. Naming a composed
    parser (see :py:func:`_parse_method_name`) instead of composing it at every
    property therefore costs nothing at run-time, and leaves one call site per
    item type instead of one per property.
    """
    return Stripped(
        f"{_DESERIALIZE_IMPL_NAME}::"
        f"{_parse_method_name(intermediate.beneath_optional(type_anno))}"
    )


def _from_method_name(cls: intermediate.ClassUnion) -> Identifier:
    """Name the function parsing an instance of ``cls`` from a JSON node."""
    return Identifier(f"try{java_naming.class_name(cls.name)}From")


def _from_object_method_name(cls: intermediate.ConcreteClass) -> Identifier:
    """
    Name the function parsing ``cls`` from a JSON object of a checked model type.

    A dispatcher has already read the model type in order to dispatch on it, so
    the function it dispatches to must not read it a second time. A class which
    carries no model type has nothing to check in the first place, so this is
    then simply :py:func:`_from_method_name`.
    """
    if not cls.serialization.with_model_type:
        return _from_method_name(cls)

    return Identifier(f"try{java_naming.class_name(cls.name)}FromObject")


# endregion

# region Shared errors and helpers


def _generate_prepend_name() -> Stripped:
    """Generate the helper marking an error as coming from a named property."""
    return Stripped(
        f"""\
/**
 * Mark the error of {{@code result}} as coming from the property {{@code name}}.
 *
 * <p>A {{@code case}} of a property loop is matched exactly when the key of
 * the property equals its literal, so the key already names the property and
 * no {{@code case}} has to spell it out a second time.
 */
private static <T> Reporting.Result<T> prependName(
{I}Reporting.Result<?> result, String name) {{
{I}final Reporting.Error error = result.getError();
{I}error.prependSegment(new Reporting.NameSegment(name));
{I}return Reporting.Result.failure(error);
}}"""
    )


def _generate_prepend_index() -> Stripped:
    """Generate the helper marking an error as coming from an indexed item."""
    return Stripped(
        f"""\
/**
 * Mark the error of {{@code result}} as coming from the item at {{@code index}}.
 */
private static <T> Reporting.Result<T> prependIndex(
{I}Reporting.Result<?> result, int index) {{
{I}final Reporting.Error error = result.getError();
{I}error.prependSegment(new Reporting.IndexSegment(index));
{I}return Reporting.Result.failure(error);
}}"""
    )


def _generate_not_a_json_object() -> Stripped:
    """Generate the error for a node which is no JSON object."""
    return Stripped(
        f"""\
/**
 * Report that {{@code node}} is no JSON object.
 */
private static <T> Reporting.Result<T> notAJsonObject(JsonNode node) {{
{I}return Reporting.Result.failure(
{II}new Reporting.Error(
{III}"Expected a JsonObject, but got " +
{III}(node == null ? "null" : node.getNodeType())));
}}"""
    )


def _generate_not_a_json_array() -> Stripped:
    """Generate the error for a node which is no JSON array."""
    return Stripped(
        f"""\
/**
 * Report that {{@code node}} is no JSON array.
 */
private static <T> Reporting.Result<T> notAJsonArray(JsonNode node) {{
{I}return Reporting.Result.failure(
{II}new Reporting.Error(
{III}"Expected a JsonArray, but got " + node.getNodeType()));
}}"""
    )


def _generate_unexpected_property() -> Stripped:
    """Generate the error for a property which the class does not have."""
    return Stripped(
        f"""\
/**
 * Report a property which the class does not have.
 */
private static <T> Reporting.Result<T> unexpectedProperty(String name) {{
{I}return Reporting.Result.failure(
{II}new Reporting.Error("Unexpected property: " + name));
}}"""
    )


def _generate_missing_required_property() -> Stripped:
    """Generate the error for a required property which the object omitted."""
    return Stripped(
        f"""\
/**
 * Report a required property which the JSON object did not give.
 */
private static <T> Reporting.Result<T> missingRequiredProperty(String name) {{
{I}return Reporting.Result.failure(
{II}new Reporting.Error(
{III}"Required property \\"" + name + "\\" is missing"));
}}"""
    )


def _generate_try_enum_from_helper() -> Stripped:
    """Generate the generic helper parsing a JSON string as an enumeration literal."""
    return Stripped(
        f"""\
/**
 * Parse {{@code node}} as a literal of the enumeration {{@code enumType}},
 * converted from its text by {{@code fromString}}.
 *
 * <p>The stringification is passed in as a function value so that this one
 * helper does the whole plumbing for every enumeration, and a single statement
 * parses one. The literal and the class constrain each other, so the name in
 * the error message can not drift from the type of the literal.
 *
 * @param node JSON node to be parsed
 * @param fromString to convert the text into a literal
 * @param enumType enumeration whose literal is expected
 */
private static <T> Reporting.Result<T> tryEnumFrom(
{I}JsonNode node,
{I}Function<String, Optional<T>> fromString,
{I}Class<T> enumType) {{
{I}final Reporting.Result<String> text = tryStringFrom(node);
{I}if (text.isError()) {{
{II}return text.castTo(enumType);
{I}}}

{I}final Optional<T> parsed = fromString.apply(text.getResult());
{I}if (!parsed.isPresent()) {{
{II}return Reporting.Result.failure(
{III}new Reporting.Error(
{IIII}"Not a valid JSON representation of " + enumType.getSimpleName()));
{I}}}

{I}return Reporting.Result.success(parsed.get());
}}"""
    )


def _generate_try_model_type_from() -> Stripped:
    """Generate the extraction of the ``modelType`` property."""
    return Stripped(
        f"""\
/**
 * Extract the {{@code modelType}} property of {{@code node}} as a string.
 *
 * <p>This is the only place which knows how the model type is spelled on
 * the wire. Both the dispatch on the model type and its check in a concrete
 * class go through it.
 *
 * @param node JSON object to be inspected
 */
private static Reporting.Result<String> tryModelTypeFrom(JsonNode node) {{
{I}final JsonNode modelTypeNode = node.get("modelType");
{I}if (modelTypeNode == null) {{
{II}return missingRequiredProperty("modelType");
{I}}}

{I}final Reporting.Result<String> result = tryStringFrom(modelTypeNode);
{I}if (result.isError()) {{
{II}return prependName(result, "modelType");
{I}}}

{I}return result;
}}"""
    )


def _generate_check_model_type() -> Stripped:
    """Generate the check of the ``modelType`` property against the expected one."""
    return Stripped(
        f"""\
/**
 * Check that {{@code node}} gives the {{@code expected}} model type, and return
 * the error if it does not.
 *
 * <p>The model type is checked before the properties are read, so that a wrong
 * one is reported without de-serializing any of them first, and so that
 * the property loop carries nothing but the properties.
 *
 * @param node JSON object to be inspected
 * @param expected model type of the class being de-serialized
 */
private static Reporting.Error checkModelType(JsonNode node, String expected) {{
{I}final Reporting.Result<String> result = tryModelTypeFrom(node);
{I}if (result.isError()) {{
{II}return result.getError();
{I}}}

{I}final String modelType = result.getResult();
{I}if (!modelType.equals(expected)) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected the model type '" + expected + "', " +
{III}"but got '" + modelType + "'");
{II}// NOTE (mristin):
{II}// A wrong model type is reported at the instance, as an unknown one is,
{II}// and as in the other SDKs.
{II}return error;
{I}}}

{I}return null;
}}"""
    )


def _generate_parse_array_helper() -> Stripped:
    """Generate the generic helper to parse a JSON array as a list."""
    return Stripped(
        f"""\
/**
 * Parse {{@code node}} as a JSON array, and every of its items with
 * {{@code parseItem}}.
 *
 * @param node JSON node to be parsed
 * @param parseItem to parse a single item of the array
 */
private static <T> Reporting.Result<List<T>> parseArray(
{I}JsonNode node,
{I}Function<JsonNode, Reporting.Result<? extends T>> parseItem) {{
{I}if (!node.isArray()) {{
{II}return notAJsonArray(node);
{I}}}

{I}final List<T> result = new ArrayList<>(node.size());

{I}int index = 0;
{I}for (JsonNode item : node) {{
{II}final Reporting.Result<? extends T> parsedItem = parseItem.apply(item);
{II}if (parsedItem.isError()) {{
{III}return prependIndex(parsedItem, index);
{II}}}

{II}result.add(parsedItem.getResult());
{II}index++;
{I}}}

{I}return Reporting.Result.success(result);
}}"""
    )


def _generate_parse_set_helper() -> Stripped:
    """Generate the generic helper to parse a JSON array as a set."""
    return Stripped(
        f"""\
/**
 * Parse {{@code node}} as a JSON array, and every of its items with
 * {{@code parseItem}}, into a set.
 *
 * <p>The items can come in any order, but a duplicate item is an error, so that
 * no item is silently dropped.
 *
 * @param node JSON node to be parsed
 * @param parseItem to parse a single item of the array
 */
private static <T> Reporting.Result<Set<T>> parseSet(
{I}JsonNode node,
{I}Function<JsonNode, Reporting.Result<? extends T>> parseItem) {{
{I}if (!node.isArray()) {{
{II}return notAJsonArray(node);
{I}}}

{I}final Set<T> result = new HashSet<>();

{I}int index = 0;
{I}for (JsonNode item : node) {{
{II}final Reporting.Result<? extends T> parsedItem = parseItem.apply(item);
{II}if (parsedItem.isError()) {{
{III}return prependIndex(parsedItem, index);
{II}}}

{II}if (!result.add(parsedItem.getResult())) {{
{III}final Reporting.Error error = new Reporting.Error(
{IIII}"Expected unique items in the set, but the item is a duplicate");
{III}error.prependSegment(new Reporting.IndexSegment(index));
{III}return Reporting.Result.failure(error);
{II}}}

{II}index++;
{I}}}

{I}return Reporting.Result.success(result);
}}"""
    )


def _generate_parse_tuple_helper(arity: int) -> Stripped:
    """Generate the generic helper to parse a JSON array as a tuple."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    tuple_type = f"Tuple{arity}<{', '.join(type_params)}>"

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Parse {{@code node}} as a JSON array of exactly {arity} item(s), each
 * de-serialized with the corresponding {{@code parseItemI}}.
 *
 * @param node JSON node to be parsed
 */
private static <{", ".join(type_params)}> Reporting.Result<{tuple_type}> parseTuple{arity}(
{I}JsonNode node,
"""
    )

    for i in range(arity):
        writer.write(
            f"{I}Function<JsonNode, Reporting.Result<? extends T{i + 1}>> "
            f"parseItem{i + 1}"
        )
        writer.write(",\n" if i < arity - 1 else ") {\n")

    writer.write(
        f"""\
{I}if (!node.isArray()) {{
{II}return notAJsonArray(node);
{I}}}

{I}if (node.size() != {arity}) {{
{II}return Reporting.Result.failure(
{III}new Reporting.Error(
{IIII}"Expected exactly {arity} item(s), but got " + node.size()));
{I}}}

"""
    )

    for i in range(arity):
        writer.write(
            f"""\
{I}final Reporting.Result<? extends T{i + 1}> item{i + 1} =
{II}parseItem{i + 1}.apply(node.get({i}));
{I}if (item{i + 1}.isError()) {{
{II}return prependIndex(item{i + 1}, {i});
{I}}}

"""
        )

    tuple_literal = java_common.generate_tuple_literal(
        item_exprs=[Stripped(f"item{i + 1}.getResult()") for i in range(arity)]
    )

    writer.write(
        f"""\
{I}return Reporting.Result.success(
{II}{indent_but_first_line(tuple_literal, II)});
}}"""
    )

    return Stripped(writer.getvalue())


# endregion

# region Composed parsers


def _composed_type_annotations(
    symbol_table: intermediate.SymbolTable,
) -> List[intermediate.TypeAnnotationUnion]:
    """
    List the list- and tuple-typed values which need a parser of their own.

    Only a list and a tuple have no function of their own to be named after, so
    only they are composed out of the parsers of their items.

    The result is de-duplicated by the moniker, which is injective (see
    :py:func:`aas_core_codegen.java.common.type_moniker`), so that two distinct
    types can never be conflated into one parser.

    An implementation-specific class is scanned as well, although its own
    function is given as a snippet: the snippet still parses the properties of
    that very class, and hence may well call the parsers of their types.
    """
    result: List[intermediate.TypeAnnotationUnion] = []
    observed: Set[str] = set()

    for cls in symbol_table.concrete_classes:
        for arg in cls.constructor.arguments:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                arg.type_annotation
            ):
                if not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ):
                    continue

                moniker = java_common.type_moniker(type_anno)
                if moniker not in observed:
                    observed.add(moniker)
                    result.append(type_anno)

    return result


def _generate_composed_parser(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """Generate the parser of the list or of the tuple ``type_anno``."""
    name = _parse_method_name(type_anno)
    value_type = java_common.generate_type(type_anno)

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_parser = _item_parser_reference(type_anno.items)

        items_type = java_common.generate_type(type_anno.items)

        # NOTE (mristin):
        # A Javadoc comment can not carry a type broken over several lines, as
        # ``generate_type`` breaks a long tuple, so we describe it in words.
        description = (
            f"a list of {{@code {items_type}}}"
            if "\n" not in items_type
            else "a list of nested collections"
        )

        body = Stripped(f"return parseArray(node, {item_parser});")
        if _FUNCTION_BODY_INDENTATION + len(body) > _MAX_LINE_LENGTH:
            body = Stripped(
                f"""\
return parseArray(
{I}node,
{I}{item_parser});"""
            )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        item_parser = _item_parser_reference(type_anno.items)

        description = f"a set of {{@code {java_common.generate_type(type_anno.items)}}}"

        body = Stripped(f"return parseSet(node, {item_parser});")
        if _FUNCTION_BODY_INDENTATION + len(body) > _MAX_LINE_LENGTH:
            body = Stripped(
                f"""\
return parseSet(
{I}node,
{I}{item_parser});"""
            )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_parsers_joined = ",\n".join(
            _item_parser_reference(item_type_anno) for item_type_anno in type_anno.items
        )

        description = f"a tuple of {len(type_anno.items)} item(s)"

        body = Stripped(
            f"""\
return parseTuple{len(type_anno.items)}(
{I}node,
{I}{indent_but_first_line(item_parsers_joined, I)});"""
        )

    else:
        raise AssertionError(
            f"Expected a list, a set or a tuple type annotation, but got: {type_anno}"
        )

    # NOTE (mristin):
    # We describe the type in words rather than spelling it out, since
    # ``generate_type`` breaks a long tuple over several lines, which a Javadoc
    # comment can not carry.
    return Stripped(
        f"""\
/**
 * Parse {{@code node}} as {description}.
 *
 * @param node JSON node to be parsed
 */
private static Reporting.Result<{value_type}> {name}(JsonNode node) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


# endregion

# region Parsers of a single type


def _generate_from_method_for_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the deserialization method for an enumeration."""
    name = java_naming.enum_name(identifier=enumeration.name)
    method_name = java_naming.method_name(Identifier(f"{enumeration.name}_from_string"))

    call = f"return tryEnumFrom(node, Stringification::{method_name}, {name}.class);"
    if _FUNCTION_BODY_INDENTATION + len(call) > _MAX_LINE_LENGTH:
        call = f"""\
return tryEnumFrom(
{I}node,
{I}Stringification::{method_name},
{I}{name}.class);"""

    return Stripped(
        f"""\
/**
 * Deserialize the enumeration {name} from the {{@code node}}.
 *
 * @param node JSON node to be parsed
 */
private static Reporting.Result<{name}> try{name}From(JsonNode node) {{
{I}{indent_but_first_line(Stripped(call), I)}
}}"""
    )


def _generate_json_object_guard() -> Stripped:
    """Generate the guard rejecting a node which is no JSON object."""
    return Stripped(
        f"""\
if (node == null || !node.isObject()) {{
{I}return notAJsonObject(node);
}}"""
    )


def _generate_from_method_for_interface(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate the deserialization method for an interface."""
    name = java_naming.interface_name(interface.name)

    switch_writer = io.StringIO()
    switch_writer.write("switch (modelTypeResult.getResult()) {\n")

    for implementer in interface.implementers:
        model_type = naming.json_model_type(implementer.name)
        switch_writer.write(
            f"""\
{I}case {java_common.string_literal(model_type)}:
{II}return {_from_object_method_name(implementer)}(node);
"""
        )

    switch_writer.write(
        f"""\
{I}default: {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Unexpected model type for {name}: " + modelTypeResult.getResult());
{II}return Reporting.Result.failure(error);
{I}}}
}}"""
    )

    return Stripped(
        f"""\
/**
 * Deserialize an instance of {name} by dispatching
 * based on {{@code modelType}} property of the {{@code node}}.
 *
 * @param node JSON node to be parsed
 */
public static Reporting.Result<? extends {name}> try{name}From(JsonNode node) {{
{I}{indent_but_first_line(_generate_json_object_guard(), I)}

{I}final Reporting.Result<String> modelTypeResult = tryModelTypeFrom(node);
{I}if (modelTypeResult.isError()) {{
{II}return modelTypeResult.castTo({name}.class);
{I}}}

{I}{indent_but_first_line(Stripped(switch_writer.getvalue()), I)}
}}"""
    )


def _generate_check_model_type_call(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the check of the model type preceding the property loop of ``cls``."""
    model_type_literal = java_common.string_literal(naming.json_model_type(cls.name))

    call = f"final Reporting.Error modelTypeError = checkModelType(node, {model_type_literal});"
    if _FUNCTION_BODY_INDENTATION + len(call) > _MAX_LINE_LENGTH:
        call = f"""\
final Reporting.Error modelTypeError = checkModelType(
{I}node, {model_type_literal});"""

    return Stripped(
        f"""\
{call}
if (modelTypeError != null) {{
{I}return Reporting.Result.failure(modelTypeError);
}}"""
    )


def _generate_case_for_argument(
    arg: intermediate.Argument,
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the ``case`` of the property loop de-serializing ``arg``."""
    type_anno = intermediate.beneath_optional(arg.type_annotation)

    # Prefix the variables to avoid naming conflicts
    target_var = java_naming.variable_name(Identifier(f"the_{arg.name}"))

    json_name = cls.properties_by_name[arg.name].json_name
    assert not java_common.needs_escaping(json_name)

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        # NOTE (mristin):
        # A list, a set and a tuple are parsed into their exact type, whereas an atomic
        # value of one of our classes is parsed by the function of the concrete
        # class and hence only *extends* the type of the property.
        result_type = java_common.generate_type(type_anno)
    else:
        result_type = Stripped(f"? extends {java_common.generate_type(type_anno)}")

    call = f"{_parse_method_name(type_anno)}(value)"

    declaration = f"final Reporting.Result<{result_type}> parsed = {call};"
    if _CASE_BODY_INDENTATION + len(declaration) > _MAX_LINE_LENGTH:
        declaration = f"""\
final Reporting.Result<{result_type}> parsed =
{I}{call};"""

    return Stripped(
        f"""\
case {java_common.string_literal(json_name)}: {{
{I}{indent_but_first_line(Stripped(declaration), I)}
{I}if (parsed.isError()) {{
{II}return prependName(parsed, key);
{I}}}
{I}{target_var} = parsed.getResult();
{I}break;
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_from_object_body(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[List[Stripped]], Optional[List[Error]]]:
    """Generate the blocks reading the properties of ``cls`` from a JSON object."""
    errors: List[Error] = []

    name = java_naming.class_name(cls.name)

    blocks: List[Stripped] = []

    # region Initialize argument variables to null

    if len(cls.constructor.arguments) > 0:
        args_init_writer = io.StringIO()
        for i, arg in enumerate(cls.constructor.arguments):
            arg_var = java_naming.variable_name(Identifier(f"the_{arg.name}"))
            type_anno = intermediate.beneath_optional(arg.type_annotation)
            arg_type = java_common.generate_type(type_anno)

            if i > 0:
                args_init_writer.write("\n")
            args_init_writer.write(f"{arg_type} {arg_var} = null;")

        blocks.append(Stripped(args_init_writer.getvalue()))

    # endregion

    # region Switch on property name

    cases: List[Stripped] = [
        _generate_case_for_argument(arg=arg, cls=cls)
        for arg in cls.constructor.arguments
    ]

    if cls.serialization.with_model_type:
        cases.append(
            Stripped(
                f"""\
case "modelType":
{I}// The model type has already been checked before the loop.
{I}break;"""
            )
        )

    cases.append(
        Stripped(
            f"""\
default:
{I}return unexpectedProperty(key);"""
        )
    )

    foreach_writer = io.StringIO()
    foreach_writer.write(
        f"""\
for (Iterator<Map.Entry<String, JsonNode>> iterator = node.fields(); iterator.hasNext(); ) {{
{I}final Map.Entry<String, JsonNode> keyValue = iterator.next();
{I}final String key = keyValue.getKey();
"""
    )

    if len(cls.constructor.arguments) > 0:
        foreach_writer.write(f"{I}final JsonNode value = keyValue.getValue();\n")

    foreach_writer.write(f"\n{I}switch (key) {{")

    for case_block in cases:
        foreach_writer.write("\n")
        foreach_writer.write(textwrap.indent(case_block, II))

    foreach_writer.write(f"\n{I}}}\n}}")

    blocks.append(Stripped(foreach_writer.getvalue()))

    # endregion

    # region Check required

    for arg in cls.constructor.arguments:
        if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        arg_var = java_naming.variable_name(Identifier(f"the_{arg.name}"))
        json_name = cls.properties_by_name[arg.name].json_name
        assert not java_common.needs_escaping(json_name)

        blocks.append(
            Stripped(
                f"""\
if ({arg_var} == null) {{
{I}return missingRequiredProperty({java_common.string_literal(json_name)});
}}"""
            )
        )

    # endregion

    # region Pass in arguments to the constructor

    property_names = [prop.name for prop in cls.properties]
    constructor_argument_names = [arg.name for arg in cls.constructor.arguments]

    # fmt: off
    assert (
            {prop.name for prop in cls.properties}
            == {arg.name for arg in cls.constructor.arguments}
    ), (
        f"Expected the properties to coincide with constructor arguments, "
        f"but they do not for {cls.name!r}:"
        f"{property_names=}, {constructor_argument_names=}"
    )
    # fmt: on

    if len(cls.constructor.arguments) == 0:
        blocks.append(Stripped(f"return Reporting.Result.success(new {name}());"))
    else:
        init_writer = io.StringIO()
        init_writer.write(f"return Reporting.Result.success(new {name}(\n")

        for i, arg in enumerate(cls.constructor.arguments):
            prop = cls.properties_by_name[arg.name]

            # NOTE (empwilli):
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

            arg_var = java_naming.variable_name(Identifier(f"the_{arg.name}"))

            init_writer.write(f"{I}{arg_var}")

            if i < len(cls.constructor.arguments) - 1:
                init_writer.write(",\n")
            else:
                init_writer.write("));")

        if len(errors) > 0:
            return None, errors

        blocks.append(Stripped(init_writer.getvalue()))

    # endregion

    return blocks, None


def _wrap_from_method(
    name: str,
    method_name: Identifier,
    blocks: List[Stripped],
    doc: Stripped,
) -> Stripped:
    """Wrap the ``blocks`` into the de-serialization method ``method_name``."""
    writer = io.StringIO()
    writer.write(doc)
    writer.write(
        f"""
private static Reporting.Result<{name}> {method_name}(JsonNode node) {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_from_methods_for_class(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[List[Stripped]], Optional[List[Error]]]:
    """Generate the deserialization method(s) for a concrete class."""
    name = java_naming.class_name(cls.name)

    body_blocks, errors = _generate_from_object_body(cls=cls)
    if errors is not None:
        return None, errors

    assert body_blocks is not None

    if not cls.serialization.with_model_type:
        # NOTE (mristin):
        # There is no model type to check, so the function reading the properties
        # is the entry point itself.
        blocks = [_generate_json_object_guard()] + body_blocks

        return (
            [
                _wrap_from_method(
                    name=name,
                    method_name=_from_method_name(cls),
                    blocks=blocks,
                    doc=Stripped(
                        f"""\
/**
 * Deserialize an instance of {name} from {{@code node}}.
 *
 * @param node JSON node to be parsed
 */"""
                    ),
                )
            ],
            None,
        )

    entry_point = _wrap_from_method(
        name=name,
        method_name=_from_method_name(cls),
        blocks=[
            _generate_json_object_guard(),
            _generate_check_model_type_call(cls=cls),
            Stripped(f"return {_from_object_method_name(cls)}(node);"),
        ],
        doc=Stripped(
            f"""\
/**
 * Deserialize an instance of {name} from {{@code node}}.
 *
 * @param node JSON node to be parsed
 */"""
        ),
    )

    from_object = _wrap_from_method(
        name=name,
        method_name=_from_object_method_name(cls),
        blocks=body_blocks,
        doc=Stripped(
            f"""\
/**
 * Deserialize an instance of {name} from the JSON object {{@code node}} whose
 * model type has already been checked.
 *
 * @param node JSON object to be parsed
 */"""
        ),
    )

    return [entry_point, from_object], None


def _generate_from_method_for_named_union(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the deserialization method for the named union ``named_union``.

    Dispatch on ``modelType`` for every implementer which sets it, and fall
    back to testing which implementer's required properties are all present
    for the remaining implementers. This mirrors the per-implementer
    partitioning already verified in the intermediate representation, so
    every implementer is covered by exactly one of the two strategies.

    The de-serialized implementer is wrapped as its most specific root of
    the union.
    """
    name = java_naming.union_name(named_union.name)

    with_model_type = [
        implementer
        for implementer in named_union.implementers
        if implementer.serialization.with_model_type
    ]
    without_model_type = [
        implementer
        for implementer in named_union.implementers
        if not implementer.serialization.with_model_type
    ]

    blocks: List[Stripped] = [
        _generate_json_object_guard(),
    ]

    if len(with_model_type) > 0:
        switch_writer = io.StringIO()
        switch_writer.write("switch (modelTypeResult.getResult()) {\n")

        for implementer in with_model_type:
            model_type = naming.json_model_type(implementer.name)
            implementer_name = java_naming.class_name(implementer.name)
            root_name = java_naming.class_name(
                named_union.most_specific_root_of(implementer).name
            )
            switch_writer.write(
                f"""\
{I}case {java_common.string_literal(model_type)}: {{
{II}final Reporting.Result<{implementer_name}> result =
{III}{_from_object_method_name(implementer)}(node);
{II}if (result.isError()) {{
{III}return result.castTo({name}.class);
{II}}}
{II}return Reporting.Result.success({name}.from{root_name}(result.getResult()));
{I}}}
"""
            )

        switch_writer.write(
            f"""\
{I}default: {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Unexpected model type for {name}: " + modelTypeResult.getResult());
{II}return Reporting.Result.failure(error);
{I}}}
}}"""
        )

        blocks.append(
            Stripped(
                f"""\
final JsonNode modelTypeNode = node.get("modelType");
if (modelTypeNode != null) {{
{I}final Reporting.Result<String> modelTypeResult = tryStringFrom(modelTypeNode);
{I}if (modelTypeResult.isError()) {{
{II}return prependName(modelTypeResult, "modelType");
{I}}}
{I}{indent_but_first_line(Stripped(switch_writer.getvalue()), I)}
}}"""
            )
        )

    for implementer in without_model_type:
        implementer_name = java_naming.class_name(implementer.name)
        root_name = java_naming.class_name(
            named_union.most_specific_root_of(implementer).name
        )

        required_json_names = [
            implementer.properties_by_name[arg.name].json_name
            for arg in implementer.constructor.arguments
            if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation)
        ]
        assert len(required_json_names) > 0, (
            f"Expected the structurally-dispatched implementer "
            f"{implementer.name!r} of the named union {named_union.name!r} "
            f"to have at least one required property; "
            f"this should have already been verified in the intermediate "
            f"representation."
        )

        condition = " && ".join(
            f"node.get({java_common.string_literal(json_name)}) != null"
            for json_name in required_json_names
        )

        blocks.append(
            Stripped(
                f"""\
if ({condition}) {{
{I}final Reporting.Result<{implementer_name}> result = {_from_method_name(implementer)}(node);
{I}if (result.isError()) {{
{II}return result.castTo({name}.class);
{I}}}
{I}return Reporting.Result.success({name}.from{root_name}(result.getResult()));
}}"""
            )
        )

    blocks.append(
        Stripped(
            f"""\
final Reporting.Error error = new Reporting.Error(
{I}"Could not determine the concrete type of {name} for the given JSON object");
return Reporting.Result.failure(error);"""
        )
    )

    writer = io.StringIO()

    writer.write(
        f"""\
/**
 * Deserialize an instance of {name} from the {{@code node}}.
 *
 * @param node JSON node to be parsed
 */
public static Reporting.Result<{name}> try{name}From(JsonNode node) {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


# endregion


def _generate_try_long_from() -> Stripped:
    """
    Generate the parser of a 64-bit integer.

    The integer has to lie in the safe integer range, as checked by
    ``Verification.isSafeInteger``, so that the parsed instance can be
    written back to JSON.
    """
    return Stripped(
        f"""\
/** Convert {{@code value}} to a long 64-bit integer.
 *
 * <p>A whole number such as {{@code 5.0}} or {{@code 1e2}} is accepted as
 * an integer, since JSON has a single number type. The integer has to lie in
 * the safe integer range [-2^53 + 1, 2^53 - 1].
 *
 * @param node JSON node to be parsed
 */
private static Reporting.Result<Long> tryLongFrom(JsonNode value) {{
{I}if (!value.isNumber()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected an integer, but got: " + value.getNodeType());
{II}return Reporting.Result.failure(error);
{I}}}

{I}switch (value.numberType()) {{
{II}case INT:
{II}case LONG: {{
{III}final long integer = value.longValue();
{III}if (Verification.isSafeInteger(integer)) {{
{IIII}return Reporting.Result.success(integer);
{III}}}
{III}break;
{II}}}

{II}case BIG_INTEGER: {{
{III}final BigInteger integer = value.bigIntegerValue();
{III}if (Verification.isSafeInteger(integer)) {{
{IIII}return Reporting.Result.success(integer.longValue());
{III}}}
{III}break;
{II}}}

{II}default: {{
{III}final double number = value.doubleValue();
{III}if (!Double.isFinite(number) || Math.rint(number) != number) {{
{IIII}return Reporting.Result.failure(new Reporting.Error(
{IIIII}"Expected an integer, but got " + number +
{IIIIII}", which is not a whole number"));
{III}}}
{III}if (Verification.isSafeInteger(number)) {{
{IIII}return Reporting.Result.success((long) number);
{III}}}
{III}break;
{II}}}
{I}}}

{I}return Reporting.Result.failure(new Reporting.Error(
{II}Verification.integerOutsideSafeRangeMessage(value)));
}}"""
    )


def _generate_primitive_parsers(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the parsers of the primitive JSON values."""
    result: List[Stripped] = [
        Stripped(
            f"""\
/** Convert {{@code value}} to a string.
 * @param node JSON node to be parsed
 */
private static Reporting.Result<String> tryStringFrom(JsonNode value) {{
{I}if (!value.isTextual()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a JsonValue of String, but got " + value.getNodeType());
{II}return Reporting.Result.failure(error);
{I}}}
{I}return Reporting.Result.success(value.asText());
}}"""
        ),
        Stripped(
            f"""\
/** Convert {{@code value}} to a boolean.
 * @param node JSON node to be parsed
 */
private static Reporting.Result<Boolean> tryBooleanFrom(JsonNode value) {{
{I}if (!value.isBoolean()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a JsonValue of Boolean, but got " + value.getNodeType());
{II}return Reporting.Result.failure(error);
{I}}}
{I}return Reporting.Result.success(value.asBoolean());
}}"""
        ),
    ]

    # NOTE (mristin):
    # The parser of an integer relies on ``Verification.isSafeInteger`` and
    # ``Verification.integerOutsideSafeRangeMessage``, the latter of which is
    # only generated if an instance can hold an integer.
    if intermediate_uses.integers(symbol_table):
        result.append(_generate_try_long_from())

    result.extend(
        [
            Stripped(
                f"""\
/** Convert {{@code value}} to a double-precision 64-bit float.
 * @param node JSON node to be parsed
 */
private static Reporting.Result<Double> tryDoubleFrom(JsonNode value) {{
{I}// NOTE (mristin):
{I}// We deliberately ask for a number, and not for a floating-point number.
{I}// JSON has a single number type, so ``3`` is every bit as good a double as
{I}// ``3.0`` is, and every other SDK reads it as one.
{I}if (!value.isNumber()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a JsonValue of Double, but got " + value.getNodeType());
{II}return Reporting.Result.failure(error);
{I}}}

{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so a conformant parser
{I}// can never give us one. Jackson parses them when
{I}// JsonReadFeature.ALLOW_NON_NUMERIC_NUMBERS is enabled, and the caller can
{I}// construct such a node programmatically in any case, so we check here.
{I}final double asDouble = value.asDouble();
{I}if (!Double.isFinite(asDouble)) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a finite number, but got " + asDouble);
{II}return Reporting.Result.failure(error);
{I}}}

{I}return Reporting.Result.success(asDouble);
}}"""
            ),
            Stripped(
                f"""\
private static Reporting.Result<byte[]> tryBytesFrom(JsonNode value) {{
{I}if (!value.isTextual()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a JsonValue of String, but got " + value.getNodeType());
{II}return Reporting.Result.failure(error);
{I}}}
{I}final byte[] decodedData;
{I}Base64.Decoder decoder = Base64.getDecoder();

{I}try {{
{II}decodedData = decoder.decode(value.textValue());
{I}}} catch (Exception exception) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected Base-64 encoded bytes, but the conversion failed " +
{IIII}"because: " + exception.getMessage());
{II}return Reporting.Result.failure(error);
{I}}}

{I}return Reporting.Result.success(decodedData);
}}"""
            ),
        ]
    )

    return result


def _generate_json_able_helpers(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the de/serialization of the JSON-able values, if the model uses them.

    A JSON-able value needs no conversion at all -- it already *is* a Jackson
    node. It does need to be checked, since a node rules out neither a null nor
    a non-finite number, and copied, so that the instance and the document it
    came from do not share a mutable tree.
    """
    if not intermediate_uses.json_types(symbol_table):
        return []

    return [
        Stripped(
            f"""\
/**
 * Parse {{@code node}} as a JSON-able value.
 *
 * <p>A JSON-able value is, recursively, exactly as JSON itself is defined:
 * a null node (JSON null), a boolean, a number, a string, an array of
 * JSON-able values or an object of JSON-able values with string keys.
 * An infinity, a not-a-number and an integer outside the safe integer
 * range [-2^53 + 1, 2^53 - 1] are rejected at any depth.
 *
 * <p>The result is a deep copy, and never {{@code node}} itself, so that
 * the parsed instance does not share a tree with the document it came from.
 *
 * <p>The path of an error is relative to {{@code node}}.
 *
 * @param node to be parsed
 * @return the parsed value, or an error
 */
private static Reporting.Result<JsonNode> tryJsonValueFrom(JsonNode node) {{
{I}if (node == null || node.isMissingNode()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected a JSON-able value, but got: " + node));
{I}}}

{I}if (node.isNull()) {{
{II}return Reporting.Result.success(JsonNodeFactory.instance.nullNode());
{I}}}

{I}if (node.isNumber()) {{
{II}final String cause = Verification.checkJsonAbleNumber(node);
{II}if (cause != null) {{
{III}return Reporting.Result.failure(new Reporting.Error(cause));
{II}}}
{II}return Reporting.Result.success(node.deepCopy());
{I}}}

{I}if (node.isBoolean() || node.isTextual()) {{
{II}return Reporting.Result.success(node.deepCopy());
{I}}}

{I}if (node.isArray()) {{
{II}final ArrayNode result = JsonNodeFactory.instance.arrayNode();
{II}int index = 0;
{II}for (JsonNode item : node) {{
{III}final Reporting.Result<JsonNode> itemResult = tryJsonValueFrom(item);
{III}if (itemResult.isError()) {{
{IIII}itemResult.getError().prependSegment(
{IIIII}new Reporting.IndexSegment(index));
{IIII}return itemResult;
{III}}}
{III}result.add(itemResult.getResult());
{III}index++;
{II}}}
{II}return Reporting.Result.success(result);
{I}}}

{I}if (node.isObject()) {{
{II}final ObjectNode result = JsonNodeFactory.instance.objectNode();
{II}final Iterator<String> names = node.fieldNames();
{II}while (names.hasNext()) {{
{III}final String name = names.next();
{III}final Reporting.Result<JsonNode> valueResult = tryJsonValueFrom(
{IIII}node.get(name));
{III}if (valueResult.isError()) {{
{IIII}valueResult.getError().prependSegment(
{IIIII}new Reporting.KeySegment(name));
{IIII}return valueResult;
{III}}}
{III}result.set(name, valueResult.getResult());
{II}}}
{II}return Reporting.Result.success(result);
{I}}}

{I}return Reporting.Result.failure(new Reporting.Error(
{II}"Expected a JSON-able value (a null, a boolean, a number, a string, " +
{II}"an array or an object), but got: " + node.getNodeType()));
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse {{@code node}} as a JSON-able array.
 *
 * @param node to be parsed
 * @return the parsed array, or an error
 */
private static Reporting.Result<ArrayNode> tryJsonArrayFrom(JsonNode node) {{
{I}if (node == null || !node.isArray()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected a JSON-able array, but got: " + node));
{I}}}

{I}final Reporting.Result<JsonNode> result = tryJsonValueFrom(node);
{I}return result.isError()
{II}? Reporting.Result.failure(result.getError())
{II}: Reporting.Result.success((ArrayNode) result.getResult());
}}"""
        ),
        Stripped(
            f"""\
/**
 * Parse {{@code node}} as a JSON-able object.
 *
 * @param node to be parsed
 * @return the parsed object, or an error
 */
private static Reporting.Result<ObjectNode> tryJsonObjectFrom(JsonNode node) {{
{I}if (node == null || !node.isObject()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected a JSON-able object, but got: " + node));
{I}}}

{I}final Reporting.Result<JsonNode> result = tryJsonValueFrom(node);
{I}return result.isError()
{II}? Reporting.Result.failure(result.getError())
{II}: Reporting.Result.success((ObjectNode) result.getResult());
}}"""
        ),
    ]


def _generate_json_able_serializer(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the serializer of the JSON-able values, if the model uses them."""
    if not intermediate_uses.json_types(symbol_table):
        return []

    return [
        Stripped(
            f"""\
/**
 * Serialize {{@code that}} as a JSON node.
 *
 * <p>A JSON-able value is almost a JSON node as it comes, but not quite: its
 * type rules out neither a missing node, a non-finite number nor an integer
 * outside the safe integer range [-2^53 + 1, 2^53 - 1]. Each is refused
 * here, at any depth. A null node is written as a JSON null.
 *
 * <p>The result is a deep copy, and never {{@code that}} itself, so that
 * the serialized document does not share a tree with the instance it came
 * from.
 *
 * @param that to be serialized
 * @return {{@code that}}, as a node of a JSON document
 */
private static JsonNode jsonValueToJsonNode(JsonNode that) {{
{I}if (that == null || that.isMissingNode()) {{
{II}throw new _SerializeFailure(
{III}new Reporting.Error(
{IIII}"Expected a JSON-able value, but got: " + that));
{I}}}

{I}if (that.isNull()) {{
{II}return JsonNodeFactory.instance.nullNode();
{I}}}

{I}if (that.isNumber()) {{
{II}final String cause = Verification.checkJsonAbleNumber(that);
{II}if (cause != null) {{
{III}throw new _SerializeFailure(new Reporting.Error(cause));
{II}}}
{II}return that.deepCopy();
{I}}}

{I}if (that.isBoolean() || that.isTextual()) {{
{II}return that.deepCopy();
{I}}}

{I}if (that.isArray()) {{
{II}final ArrayNode result = JsonNodeFactory.instance.arrayNode();
{II}int index = 0;
{II}for (JsonNode item : that) {{
{III}try {{
{IIII}result.add(jsonValueToJsonNode(item));
{III}}} catch (_SerializeFailure failure) {{
{IIII}failure.getError().prependSegment(
{IIIII}new Reporting.IndexSegment(index));
{IIII}throw failure;
{III}}}
{III}index++;
{II}}}
{II}return result;
{I}}}

{I}if (that.isObject()) {{
{II}final ObjectNode result = JsonNodeFactory.instance.objectNode();
{II}final Iterator<String> names = that.fieldNames();
{II}while (names.hasNext()) {{
{III}final String name = names.next();
{III}try {{
{IIII}result.set(name, jsonValueToJsonNode(that.get(name)));
{III}}} catch (_SerializeFailure failure) {{
{IIII}failure.getError().prependSegment(
{IIIII}new Reporting.KeySegment(name));
{IIII}throw failure;
{III}}}
{II}}}
{II}return result;
{I}}}

{I}throw new _SerializeFailure(
{II}new Reporting.Error(
{III}"Expected a JSON-able value (a null, a boolean, a number, a string, " +
{III}"an array or an object), but got: " + that.getNodeType()));
}}"""
        ),
    ]


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_deserialize_impl(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the implementation of the deserialization."""
    errors: List[Error] = []

    # region Decide which of the shared helpers are needed

    # NOTE (mristin):
    # The helpers follow the call graph: a model which never composes a list
    # pays for neither the composition nor the errors which only it can report.

    parsed_classes = list(symbol_table.concrete_classes)

    interfaces = [
        our_type.interface
        for our_type in symbol_table.our_types
        if isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        )
        and our_type.interface is not None
    ]

    named_unions = [
        our_type
        for our_type in symbol_table.our_types
        if isinstance(our_type, intermediate.NamedUnion)
    ]

    composed_type_annotations = _composed_type_annotations(symbol_table)

    needs_parse_array = any(
        isinstance(type_anno, intermediate.ListTypeAnnotation)
        for type_anno in composed_type_annotations
    )

    needs_parse_set = any(
        isinstance(type_anno, intermediate.SetTypeAnnotation)
        for type_anno in composed_type_annotations
    )

    tuple_arities = intermediate.tuple_arities(symbol_table)

    #: The array, the set and the tuple helpers all report a non-array and mark
    #: the index of the item which failed.
    needs_array_helpers = needs_parse_array or needs_parse_set or len(tuple_arities) > 0

    needs_check_model_type = any(
        cls.serialization.with_model_type for cls in parsed_classes
    )

    needs_try_model_type_from = needs_check_model_type or len(interfaces) > 0

    needs_not_a_json_object = (
        len(parsed_classes) > 0 or len(interfaces) > 0 or len(named_unions) > 0
    )

    needs_prepend_name = (
        needs_try_model_type_from
        or any(
            implementer.serialization.with_model_type
            for named_union in named_unions
            for implementer in named_union.implementers
        )
        or any(len(cls.constructor.arguments) > 0 for cls in parsed_classes)
    )

    needs_try_enum_from = len(symbol_table.enumerations) > 0

    needs_missing_required_property = needs_try_model_type_from or any(
        not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation)
        for cls in parsed_classes
        for arg in cls.constructor.arguments
    )

    # endregion

    blocks: List[Stripped] = _generate_primitive_parsers(symbol_table)

    if needs_prepend_name:
        blocks.append(_generate_prepend_name())

    if needs_array_helpers:
        blocks.append(_generate_prepend_index())

    if needs_not_a_json_object:
        blocks.append(_generate_not_a_json_object())

    if needs_array_helpers:
        blocks.append(_generate_not_a_json_array())

    if len(parsed_classes) > 0:
        blocks.append(_generate_unexpected_property())

    if needs_missing_required_property:
        blocks.append(_generate_missing_required_property())

    if needs_try_model_type_from:
        blocks.append(_generate_try_model_type_from())

    if needs_check_model_type:
        blocks.append(_generate_check_model_type())

    if needs_try_enum_from:
        blocks.append(_generate_try_enum_from_helper())

    if needs_parse_array:
        blocks.append(_generate_parse_array_helper())

    if needs_parse_set:
        blocks.append(_generate_parse_set_helper())

    for arity in tuple_arities:
        blocks.append(_generate_parse_tuple_helper(arity=arity))

    blocks.extend(_generate_json_able_helpers(symbol_table=symbol_table))

    for type_anno in composed_type_annotations:
        blocks.append(_generate_composed_parser(type_anno))

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
                cls_blocks, cls_errors = _generate_from_methods_for_class(cls=our_type)
                if cls_errors is not None:
                    errors.extend(cls_errors)
                    continue

                assert cls_blocks is not None
                blocks.extend(cls_blocks)
        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(_generate_from_method_for_named_union(named_union=our_type))

        else:
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()

    writer.write(
        """\
/**
 * Implement the deserialization of meta-model classes from JSON nodes.
 *
 * <p>The implementation propagates an {@link Reporting.Error} instead
 * of relying on exceptions. Under the assumption that incorrect data is much
 * less frequent than correct data, this makes the deserialization more
 * efficient.
 *
 * However, we do not want to force the client to deal with
 * the {@link Reporting.Error} class as this is not intuitive. Therefore
 * we distinguish the implementation, realized in
 * {@link _DeserializeImplementation}, and the facade given in
 * {@link Deserialize} class.
 *
 * <p>Every value is parsed through a function which takes a single
 * {@link JsonNode} and gives back a {@link Reporting.Result}, so that a list
 * and a tuple can be composed out of the parsers of their items. Only they
 * need such a composition -- every other value already has a function named
 * after its very type.
 */
private static class _DeserializeImplementation {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_deserialize_from(name: str) -> Stripped:
    """Generate the facade deserialization method for the type with C# ``name``."""
    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Deserialize an instance of {name} from {{@code node}}.
 *
 * @param node JSON node to be parsed
 */
"""
    )

    writer.write(
        f"""\
public static {name} deserialize{name}(JsonNode node) {{
{I}final Reporting.Result<? extends {name}> result =
{II}_DeserializeImplementation.try{name}From(
{III}node);

{I}return result.onError(error -> {{
{II}throw new DeserializeException(
{III}Reporting.generateJsonPath(error.getPathSegments()),
{III}error.getCause());
{I}}});
}}"""
    )

    return Stripped(writer.getvalue())


def _generate_deserialize_json_able(name: str, result_type: str) -> Stripped:
    """
    Generate the facade deserialization method for the JSON-able ``name``.

    The ``name`` is ``JsonValue``, ``JsonArray`` or ``JsonObject``, and
    the method gives back a node of ``result_type``.
    """
    what = name[len("Json") :].lower()

    return Stripped(
        f"""\
/**
 * Deserialize a JSON-able {what} from {{@code node}}.
 *
 * <p>A JSON-able value is, recursively, exactly as JSON itself is defined:
 * a null node (JSON null), a boolean, a number, a string, an array of
 * JSON-able values or an object of JSON-able values with string keys.
 * An infinity, a not-a-number and an integer outside the safe integer
 * range [-2^53 + 1, 2^53 - 1] are rejected at any depth.
 *
 * <p>The result is a deep copy, and never {{@code node}} itself.
 *
 * @param node JSON node to be parsed
 * @throws DeserializeException if {{@code node}} is not a JSON-able {what}
 */
public static {result_type} deserialize{name}(JsonNode node) {{
{I}final Reporting.Result<{result_type}> result =
{II}_DeserializeImplementation.try{name}From(
{III}node);

{I}return result.onError(error -> {{
{II}throw new DeserializeException(
{III}Reporting.generateJsonPath(error.getPathSegments()),
{III}error.getCause());
{I}}});
}}"""
    )


def _generate_deserialize(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the deserializer with a deserialization method for each class."""
    blocks: List[Stripped] = []

    if intermediate_uses.json_types(symbol_table):
        blocks.append(
            _generate_deserialize_json_able(name="JsonValue", result_type="JsonNode")
        )
        blocks.append(
            _generate_deserialize_json_able(name="JsonArray", result_type="ArrayNode")
        )
        blocks.append(
            _generate_deserialize_json_able(name="JsonObject", result_type="ObjectNode")
        )
    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(
                _generate_deserialize_from(name=java_naming.enum_name(our_type.name))
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            continue

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if our_type.interface is not None:
                blocks.append(
                    _generate_deserialize_from(
                        name=java_naming.interface_name(our_type.interface.name)
                    )
                )

            if isinstance(our_type, intermediate.ConcreteClass):
                blocks.append(
                    _generate_deserialize_from(
                        name=java_naming.class_name(our_type.name)
                    )
                )

        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(
                _generate_deserialize_from(name=java_naming.union_name(our_type.name))
            )

        else:
            assert_never(our_type)

    writer = io.StringIO()

    writer.write(
        """\
/**
 * Deserialize instances of meta-model classes from JSON nodes.
 *
"""
    )

    first_cls: Optional[intermediate.ClassUnion] = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )

    if first_cls is not None:
        cls_name: Optional[str] = None
        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = java_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = java_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = java_naming.variable_name(Identifier("an_instance"))

        writer.write(
            f"""\
 * Here is an example how to parse an instance of {cls_name}:
 * <pre>{{@code
 * String someString = "... some JSON ...";
 * ObjectMapper objectMapper = new ObjectMapper();
 * JsonNode node = objectMapper.readTree(someString);
 * {cls_name} {an_instance_variable} = Deserialize.deserialize{cls_name}(
 * {I}node);
 * }}</pre>
 */
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

    writer.write("\n}")

    return Stripped(writer.getvalue())


# endregion

# region Serialization

# NOTE (mristin):
# The three functions which follow answer, for a value which is neither
# a list nor a tuple, what serializes it and how it is spelled. They are
# the writing twins of :py:func:`_parse_method_for_atomic_value`, and like it
# they dispatch on the type annotation and need no notion of their own.
#
# Several types give the same answer -- every class serializes through
# ``transformClass``, every enumeration through ``Serialize.toJsonValue`` --
# and that is the whole of what makes a serializer shared. The reading can
# not share this way: it has to decide what to construct before it has read
# anything, so it needs one parser per type where the writing needs one
# function per answer.


_SERIALIZE_FUNCTION_BY_PRIMITIVE_TYPE: Final[
    Mapping[intermediate.PrimitiveType, Stripped]
] = {
    intermediate.PrimitiveType.BOOL: Stripped("boolToJsonNode"),
    intermediate.PrimitiveType.INT: Stripped("longToJsonNode"),
    intermediate.PrimitiveType.FLOAT: Stripped("doubleToJsonNode"),
    intermediate.PrimitiveType.STR: Stripped("stringToJsonNode"),
    intermediate.PrimitiveType.BYTEARRAY: Stripped("bytesToJsonNode"),
}
assert all(
    literal in _SERIALIZE_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


def _serialize_function(type_anno: intermediate.AtomicTypeAnnotation) -> Stripped:
    """
    Name the function converting a single value of ``type_anno`` into a JSON node.

    None of them is generic, so a call is a direct one and needs neither
    a ``Function`` nor the lambda which creating one would allocate.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return _SERIALIZE_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type]

    # NOTE (mristin):
    # A JSON-able value is almost a JSON node as it comes, but not quite: its
    # type rules out neither a non-finite number nor a null, so it is checked
    # and copied. All three shapes go through the one function: an array and
    # an object are only JSON-able values whose top-level shape is known.
    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return Stripped("jsonValueToJsonNode")

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Expected one of our types, but got: {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return Stripped("Serialize.toJsonValue")

    if isinstance(our_type, intermediate.NamedUnion):
        return Stripped("transformUnion")

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class, but got: {our_type}"

    return Stripped("transformClass")


@ensure(lambda result: "_" not in result)
def _serialized_leaf_moniker(type_anno: intermediate.AtomicTypeAnnotation) -> str:
    """
    Name what ``type_anno`` is serialized *as*, for a composed serializer to be named after.

    This is the writing counterpart of
    :py:func:`aas_core_codegen.java.common.leaf_moniker`, which names a leaf by
    its very type. Here every class collapses onto ``IClass``, every
    enumeration onto ``IEnum`` and every named union onto ``IUnion``, so that
    the serializers of a list of any class, of any enumeration or of any union
    are one apiece.

    ``IClass``, ``IEnum`` and ``IUnion`` are the fixed names of our own
    interfaces and are never generated from the meta-model, and a scalar's
    moniker is lower-case, so none of them can be confused with the moniker of
    one of our types. None contains an underscore, as the moniker grammar
    requires (see :py:func:`aas_core_codegen.java.common.list_moniker`).
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return java_common.PRIMITIVE_TYPE_TO_MONIKER[primitive_type]

    # NOTE (mristin):
    # All three JSON-able shapes collapse onto one moniker: every one of them
    # is serialized by ``jsonValueToJsonNode``, which gives the node back
    # whatever its shape happens to be.
    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return "jsonValue"

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Expected one of our types, but got: {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return "IEnum"

    if isinstance(our_type, intermediate.NamedUnion):
        return "IUnion"

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class, but got: {our_type}"

    return "IClass"


def _serialized_value_type(type_anno: intermediate.TypeAnnotationUnion) -> Stripped:
    """
    Render the type of a value of ``type_anno`` as its serializer takes it.

    A scalar keeps its own Java type; everything else widens to the interface
    it is serialized through, so that one serializer serves them all. A list,
    a set and a tuple are rendered as their serializers take them, see
    :py:func:`_container_type`.
    """
    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        return _container_type(type_anno)

    assert isinstance(
        type_anno, intermediate.AtomicTypeAnnotationAsTuple
    ), f"Expected an atomic type annotation, but got: {type_anno}"

    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return java_common.PRIMITIVE_TYPE_MAP[primitive_type]

    # NOTE (mristin):
    # A JSON-able value widens to nothing: ``jsonValueToJsonNode`` takes
    # the very Jackson node which the property holds.
    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return java_common.generate_type(type_anno)

    moniker = _serialized_leaf_moniker(type_anno)

    # NOTE (mristin):
    # ``IUnion`` is generic in the union's own type, which is exactly what we
    # are widening away here, so the wildcard stands for it.
    return Stripped("IUnion<?>" if moniker == "IUnion" else moniker)


def _item_type_annotations(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Sequence[intermediate.TypeAnnotationExceptOptional]:
    """Give the items of the list, the set or the tuple ``type_anno``, in order."""
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        return [type_anno.items]

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return type_anno.items

    assert_never(type_anno)


def _serialized_moniker(type_anno: intermediate.TypeAnnotationExceptOptional) -> str:
    """
    Name what ``type_anno`` is serialized *as*, at any depth.

    The monikers follow the grammar of
    :py:func:`aas_core_codegen.java.common.type_moniker` over the leaves named by
    :py:func:`_serialized_leaf_moniker`, so the encoding stays injective.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return java_common.list_moniker(_serialized_moniker(type_anno.items))

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        # NOTE (mristin):
        # The items of a set are sorted before they are serialized, and they
        # are sorted each in their own way, so we can not name the serializer
        # after what the items are serialized as.
        return java_common.set_moniker(java_common.set_items_moniker(type_anno.items))

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return java_common.tuple_moniker(
            [
                _serialized_moniker(item_type_anno)
                for item_type_anno in _item_type_annotations(type_anno)
            ]
        )

    return _serialized_leaf_moniker(type_anno)


def _serializer_name(type_anno: intermediate.ContainerTypeAnnotation) -> Identifier:
    """
    Name the function serializing the list, the set or the tuple ``type_anno``.

    Only a list, a set and a tuple have no function of their own to be named
    after, so only they are composed out of the serialization of their items.
    The name follows what those items are serialized *as* and not their types
    (see :py:func:`_serialized_moniker`), so one function serves every list,
    and every tuple, whose items are serialized the same way.
    """
    return Identifier(f"serialize{_serialized_moniker(type_anno)}")


def _container_type(type_anno: intermediate.ContainerTypeAnnotation) -> Stripped:
    """Render the list or the tuple ``type_anno`` as its serializer takes it."""
    # NOTE (mristin):
    # Java generics are invariant, so a ``List<IExtension>`` is *not*
    # a ``List<IClass>`` and a ``Tuple2<IExtension, IKey>`` is *not*
    # a ``Tuple2<IClass, IClass>``. Wherever the value type widens, the bound
    # has to be spelled out for the container to accept the list or the tuple
    # which a property actually holds. A scalar widens to nothing, so it needs
    # none.
    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        # NOTE (mristin):
        # The items of a set are sorted before they are serialized, so the set
        # must keep its items as precise as the sorting needs them.
        return Stripped(f"Set<{java_common.generate_type(type_anno.items)}>")

    argument_types: List[Stripped] = []
    for item_type_anno in _item_type_annotations(type_anno):
        value_type = _serialized_value_type(item_type_anno)

        argument_types.append(
            value_type
            if intermediate.try_primitive_type(item_type_anno) is not None
            else Stripped(f"? extends {value_type}")
        )

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return Stripped(f"List<{argument_types[0]}>")

    return java_common.tuple_type(argument_types)


def _serialize_call(
    type_anno: intermediate.TypeAnnotationExceptOptional,
    source_expr: Stripped,
    indentation: int,
) -> Stripped:
    """
    Generate the expression converting ``source_expr`` into a JSON node.

    A nested list, set or tuple is converted by its own composed serializer.

    ``indentation`` is where the expression starts, so that a call which does
    not fit the line is broken after the opening parenthesis.
    """
    function = (
        Stripped(_serializer_name(type_anno))
        if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple)
        else _serialize_function(type_anno)
    )

    one_liner = Stripped(f"{function}({source_expr})")
    if "\n" not in one_liner and indentation + len(one_liner) <= _MAX_LINE_LENGTH:
        return one_liner

    # We can not use textwrap due to indent_but_first_line.
    return Stripped(
        f"""\
{function}(
{I}{indent_but_first_line(source_expr, I)})"""
    )


def _generate_composed_serializer(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """
    Generate the serializer of the list or of the tuple ``type_anno``.

    The signature and the body are spelled by what the items are serialized
    *as*, never by their types, so that the one function really does serve
    every list, and every tuple, whose items are serialized the same way --
    ``type_anno`` is only the first representative which reached it.

    The parameter is therefore wider than the list or the tuple a property
    holds, which means ``javac`` no longer rejects a value handed to the wrong
    serializer: a ``List<byte[]>`` passed to ``serializeListOf_string``
    compiles, and would emit ``[B@1a2b3c`` instead of base64. What keeps that
    from happening is that :py:func:`_serialized_leaf_moniker` names
    the serializer and :py:func:`_serialize_function` fills its body, and both
    answer a byte array with something of its own -- the same discipline
    :py:func:`aas_core_codegen.java.common.leaf_moniker` already relies on.

    There is no combinator, and hence no ``Function``: the loop and the item
    conversions are written out, so every call is a direct one. A generic
    helper shared by everything would have to be handed the conversion as
    a ``Function``, whose ``apply`` would then be megamorphic -- one
    implementation per item type at a single call site -- so it would neither
    inline nor stay free of allocation.
    """
    name = _serializer_name(type_anno)
    value_type = _container_type(type_anno)
    item_type_annos = _item_type_annotations(type_anno)

    body_indentation = _FUNCTION_BODY_INDENTATION

    stmts: List[Stripped] = [
        Stripped("final ArrayNode result = JsonNodeFactory.instance.arrayNode();")
    ]

    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        item_type = _serialized_value_type(item_type_annos[0])

        # NOTE (mristin):
        # A set is serialized as an array of its items sorted in the same order
        # in all the targets, so that the index on the error path points to
        # the item in the written array.
        items_expr = (
            java_common.sorted_set_items(item_type_annos[0], Stripped("that"))
            if isinstance(type_anno, intermediate.SetTypeAnnotation)
            else Stripped("that")
        )

        conversion = _serialize_call(
            type_anno=item_type_annos[0],
            source_expr=Stripped("item"),
            # The conversion sits inside ``result.add(`` in the loop body,
            # one level deeper than the body of the function.
            indentation=body_indentation + len(I) + len("result.add("),
        )

        # NOTE (mristin):
        # The loop counts so that the failure can name the item which was
        # refused. Every item is guarded, and not only the ones which can
        # fail today: nothing below the loop knows which item it was in.
        stmts.append(
            Stripped(
                f"""\
int i = 0;
for ({item_type} item : {items_expr}) {{
{I}try {{
{II}result.add({indent_but_first_line(conversion, II)});
{I}}} catch (_SerializeFailure failure) {{
{II}failure.getError().prependSegment(
{III}new Reporting.IndexSegment(i));
{II}throw failure;
{I}}}
{I}i++;
}}"""
            )
        )
    else:
        for i, item_type_anno in enumerate(item_type_annos):
            conversion = _serialize_call(
                type_anno=item_type_anno,
                source_expr=Stripped(f"that.item{i + 1}()"),
                indentation=body_indentation + len("result.add("),
            )

            statement = Stripped(f"result.add({conversion});")

            statement = Stripped(
                f"""\
try {{
{I}{indent_but_first_line(statement, I)}
}} catch (_SerializeFailure failure) {{
{I}failure.getError().prependSegment(
{II}new Reporting.IndexSegment({i}));
{I}throw failure;
}}"""
            )

            stmts.append(statement)

    stmts.append(Stripped("return result;"))

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        description = "every item of {@code that}"
    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        description = "every item of {@code that}, in the sorted order,"
    else:
        description = f"each of the {len(item_type_annos)} items of {{@code that}}"

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Serialize {description} into a JSON array.
 *
 * @param that to be serialized
 */
private static ArrayNode {name}(
{I}{indent_but_first_line(value_type, I)} that) {{
"""
    )

    for stmt in stmts:
        writer.write(textwrap.indent(stmt, I))
        writer.write("\n")

    writer.write("}")

    return Stripped(writer.getvalue())


def _generate_transform_class_helper() -> Stripped:
    """Generate the static entry dispatching over the run-time type."""
    return Stripped(
        f"""\
/**
 * Serialize {{@code that}} into a JSON object.
 *
 * <p>Which JSON object that is, is decided by the run-time type of
 * {{@code that}}, so this one serializer serves every abstract class, every
 * concrete class with descendants, and the item of a list or of a tuple of
 * any class at all. The de-serialization, which has to decide what to
 * construct before it has read anything, needs a dispatcher per interface
 * instead.
 *
 * <p>It is static, so that a composed serializer -- which is static as well,
 * since it carries no state either -- can reach it.
 */
static JsonNode transformClass(IClass that) {{
{I}return INSTANCE.transform(that);
}}"""
    )


def _generate_transform_union_helper() -> Stripped:
    """Generate a single serializer shared by every named union."""
    return Stripped(
        f"""\
/**
 * Serialize the named union {{@code that}} into a JSON object.
 *
 * <p>A named union is not itself an {{@link IClass}}, so it can not be
 * dispatched by {{@link #transformClass}} directly. Dispatching over
 * the common {{@code IUnion<?>}} instead of the union's own type means
 * a single serializer for *all* the named unions, and not one per union.
 *
 * <p>Should a named union ever be allowed to flatten a primitive or an
 * enumeration alternative, only this body has to change -- every call site
 * stays the same.
 */
private static JsonNode transformUnion(IUnion<?> that) {{
{I}return transformClass(that.getUnderlying());
}}"""
    )


def _generate_transform_property(
    prop: intermediate.Property,
) -> Stripped:
    """
    Generate the snippet to transform a property into a JSON node.

    Every property is now the very same statement -- a key and the value
    serialized by the function of its kind -- because a list and a tuple have
    a named serializer of their own just like everything else (see
    :py:func:`_serializer_name`). They used to be the exception, composing
    their item serializers at the call site into a named temporary which
    the next line then handed over.

    We set instead of putting, for a ``String`` as much as for anything else:
    ``ObjectNode.put(String, JsonNode)`` is deprecated in Jackson, and
    a constrained ``String`` already went through ``set``.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    getter_name = java_naming.getter_name(prop.name)
    prop_literal = java_common.string_literal(prop.json_name)

    is_optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

    serializer: Stripped

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        serializer = Stripped(_serializer_name(type_anno))
    else:
        serializer = _serialize_function(type_anno)

    # NOTE (mristin):
    # Every serializer is a static method, so the reference to one captures
    # nothing and the JVM hands out a single instance for it -- the lambda is
    # created once at the call site and never again. A method of this very
    # class is qualified by it; ``Serialize.toJsonValue`` already names
    # the class it lives in.
    serializer_reference = (
        Stripped(serializer.replace(".", "::"))
        if "." in serializer
        else Stripped(f"_Transformer::{serializer}")
    )

    # NOTE (mristin):
    # The path names the getter, and not the JSON property: a serialization
    # error is reported on an *instance*, which the caller holds, and not on
    # a document which has not been written yet.
    getter_literal = java_common.string_literal(f"{getter_name}()")

    function_name = "setOptionalProperty" if is_optional else "setProperty"

    arguments = [
        Stripped("result"),
        prop_literal,
        getter_literal,
        Stripped(f"that.{getter_name}()"),
        serializer_reference,
    ]

    one_liner = Stripped(f"{function_name}({', '.join(arguments)});")
    if _FUNCTION_BODY_INDENTATION + len(one_liner) <= _MAX_LINE_LENGTH:
        return one_liner

    # NOTE (mristin):
    # The call is broken into the two halves it reads as -- where the value
    # goes, and what it is -- before it is broken into one argument per line.
    where = ", ".join(arguments[:3])
    what = ", ".join(arguments[3:])

    indentation = _FUNCTION_BODY_INDENTATION + len(I)
    if (
        indentation + max(len(where) + len(","), len(what) + len(");"))
        <= _MAX_LINE_LENGTH
    ):
        return Stripped(
            f"""\
{function_name}(
{I}{where},
{I}{what});"""
        )

    # We can not use textwrap due to indent_but_first_line.
    arguments_joined = Stripped(",\n".join(arguments))

    return Stripped(
        f"""\
{function_name}(
{I}{indent_but_first_line(arguments_joined, I)});"""
    )


def _generate_transform_for_class(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the transform method to a JSON object for the given concrete class."""
    blocks: List[Stripped] = [
        Stripped("final ObjectNode result = JsonNodeFactory.instance.objectNode();"),
    ]

    for prop in cls.properties:
        blocks.append(
            _generate_transform_property(
                prop=prop,
            )
        )

    if cls.serialization is not None and cls.serialization.with_model_type:
        model_type = java_common.string_literal(naming.json_model_type(cls.name))
        blocks.append(Stripped(f"""result.put("modelType", {model_type});"""))

    blocks.append(Stripped("return result;"))

    writer = io.StringIO()

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    writer.write(
        f"""\
@Override
public JsonNode {transform_name}(
{I}{interface_name} that
) {{
"""
    )

    for i, stmt in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(stmt, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _composed_serializer_type_annotations(
    symbol_table: intermediate.SymbolTable,
) -> List[intermediate.ContainerTypeAnnotation]:
    """
    List the list- and tuple-typed values which need a serializer of their own.

    This is the writing twin of :py:func:`_composed_type_annotations`, and
    deliberately not the same function.

    Only a list and a tuple have no function of their own to be named after,
    so only they are composed out of the serialization of their items.

    The result is de-duplicated by the name of the serializer, which follows
    the kinds of the items (see :py:func:`_serializer_name`), so it is
    strictly shorter than the de-serialization's list of the same shape: every
    list of a class collapses onto one entry here, where each item type still
    needs a parser of its own there.

    An implementation-specific class is scanned as well, although its own
    method is given as a snippet: the snippet still serializes the properties
    of that very class, and hence may well call the serializers of their
    types.
    """
    result: List[intermediate.ContainerTypeAnnotation] = []
    observed: Set[str] = set()

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ):
                    continue

                name = _serializer_name(type_anno)
                if name not in observed:
                    observed.add(name)
                    result.append(type_anno)

    return result


def _called_serialize_functions(
    symbol_table: intermediate.SymbolTable,
) -> Set[Stripped]:
    """
    Collect the conversion functions the meta-model actually calls.

    This is the gating, and it follows the call graph literally: the very
    function which names a call decides whether that call can occur at all, so
    a helper can not be gated on one condition and called under another.
    A property is collected as well as an item, since a conversion is the same
    call in either position.
    """
    result: Set[Stripped] = set()

    # NOTE (mristin):
    # We descend only into the items of the lists, the sets and the tuples. The key
    # of a ``JSONObject`` is not serialized by a conversion function of its own.
    stack: List[intermediate.TypeAnnotationExceptOptional] = [
        intermediate.beneath_optional(prop.type_annotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ]

    while len(stack) > 0:
        type_anno = stack.pop()

        if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
            stack.extend(_item_type_annotations(type_anno))
        else:
            result.add(_serialize_function(type_anno))

    return result


def _generate_set_property_helpers() -> Stripped:
    """
    Generate the framers which set a property and name it on the error path.

    Every property goes through one of the two, and not only the ones which
    can fail today: the property is recorded here and nowhere below, as
    nothing below knows through which property the value was reached, so
    a serializer which grows a new way of failing would quietly lose the way
    to the culprit.

    The serializer is handed over as a method reference. Every one of them is
    a static method, so the reference captures nothing and the JVM hands out
    a single instance for it, created once at the call site -- which is what
    lets the framer cost no more than the statement it replaces.
    """
    return Stripped(
        f"""\
/**
 * Convert a single value into a JSON node.
 */
@FunctionalInterface
private interface Serializer<T> {{
{I}JsonNode serialize(T that);
}}

/**
 * Set the property {{@code jsonName}} of {{@code result}} to
 * {{@code that}}, serialized by {{@code serialize}}.
 *
 * <p>{{@code getterName}} names the property on the path of a failure. It is
 * the getter, and not the JSON property: a serialization error is reported
 * on an <em>instance</em>, which the caller holds, and not on a document
 * which has not been written yet.
 */
private static <T> void setProperty(
{I}ObjectNode result,
{I}String jsonName,
{I}String getterName,
{I}T that,
{I}Serializer<? super T> serialize) {{
{I}try {{
{II}result.set(jsonName, serialize.serialize(that));
{I}}} catch (_SerializeFailure failure) {{
{II}failure.getError().prependSegment(
{III}new Reporting.NameSegment(getterName));
{II}throw failure;
{I}}}
}}

/**
 * Set the property {{@code jsonName}} of {{@code result}} if {{@code that}}
 * has been given, and set nothing at all otherwise.
 *
 * <p>The {{@link Optional}} is taken apart here, once, instead of at every
 * optional property: asking it and then unwrapping it at the call site would
 * call the getter twice, and every call allocates an {{@link Optional}} of
 * its own.
 */
private static <T> void setOptionalProperty(
{I}ObjectNode result,
{I}String jsonName,
{I}String getterName,
{I}Optional<T> that,
{I}Serializer<? super T> serialize) {{
{I}final T value = that.orElse(null);
{I}if (value != null) {{
{II}setProperty(result, jsonName, getterName, value, serialize);
{I}}}
}}"""
    )


def _generate_bool_to_json_node_helper() -> Stripped:
    """Generate the conversion of a boolean."""
    return Stripped(
        f"""\
/**
 * Convert {{@code that}} boolean to a JSON value.
 *
 * <p>This wraps {{@link JsonNodeFactory}}, which is an object, so that
 * the conversion is a static method like every other one here and
 * a reference to it captures nothing.
 *
 * @param that value to be converted
 */
private static JsonNode boolToJsonNode(Boolean that) {{
{I}return JsonNodeFactory.instance.booleanNode(that);
}}"""
    )


def _generate_string_to_json_node_helper() -> Stripped:
    """Generate the conversion of a string."""
    return Stripped(
        f"""\
/**
 * Convert {{@code that}} string to a JSON value.
 *
 * <p>See the note on {{@link #boolToJsonNode}} on why this wrapper exists.
 *
 * @param that value to be converted
 */
private static JsonNode stringToJsonNode(String that) {{
{I}return JsonNodeFactory.instance.textNode(that);
}}"""
    )


def _generate_long_to_json_node_helper() -> Stripped:
    """Generate the conversion of a 64-bit integer, which JSON can not hold."""
    return Stripped(
        f"""\
/**
 * Convert {{@code that}} 64-bit long integer to a JSON value.
 *
 * @param that value to be converted
 */
private static JsonNode longToJsonNode(Long that) {{
{I}final long primitiveThat = that.longValue();
{I}if (!Verification.isSafeInteger(primitiveThat)) {{
{II}throw new _SerializeFailure(
{III}new Reporting.Error(
{IIII}Verification.integerOutsideSafeRangeMessage(primitiveThat)));
{I}}}
{I}return JsonNodeFactory.instance.numberNode(primitiveThat);
}}"""
    )


def _generate_double_to_json_node_helper() -> Stripped:
    """Generate the conversion of a double, which JSON can not always hold."""
    return Stripped(
        f"""\
/**
 * Convert {{@code that}} double-precision 64-bit float to a JSON value.
 *
 * <p>JSON knows neither an infinity nor a not-a-number, so we refuse to
 * serialize them instead of leaving it to Jackson, which writes them out as
 * the quoted strings {{@code "NaN"}} and {{@code "Infinity"}} -- valid JSON,
 * but no longer a number.
 *
 * @param that value to be converted
 */
private static JsonNode doubleToJsonNode(Double that) {{
{I}if (!Double.isFinite(that)) {{
{II}throw new _SerializeFailure(
{III}new Reporting.Error(
{IIII}"JSON knows neither an infinity nor a not-a-number, so the value "
{IIIII}+ "can not be serialized: " + that));
{I}}}
{I}return JsonNodeFactory.instance.numberNode(that);
}}"""
    )


def _generate_bytes_to_json_node_helper() -> Stripped:
    """Generate the conversion of a byte array into a base64 JSON string."""
    return Stripped(
        f"""\
/**
 * Convert {{@code that}} byte array to a JSON value.
 *
 * @param that value to be converted
 */
private static JsonNode bytesToJsonNode(byte[] that) {{
{I}return JsonNodeFactory.instance.textNode(
{II}Base64.getEncoder().encodeToString(that));
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transformer(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a transformer which transforms instances of the meta-model to JSON."""
    errors: List[Error] = []

    # NOTE (mristin):
    # The gating follows the call graph, exactly as it does on the reading
    # side: a model which never serializes a byte array pays for neither
    # the base64 conversion nor the import it needs.
    called = _called_serialize_functions(symbol_table)

    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Dispatch the serialization over the run-time type of an instance.
 *
 * <p>The transformer carries no state, so a single instance serves
 * the whole program.
 */
private static final _Transformer INSTANCE = new _Transformer();"""
        ),
        _generate_transform_class_helper(),
        _generate_set_property_helpers(),
    ]

    if Stripped("transformUnion") in called:
        blocks.append(_generate_transform_union_helper())

    if Stripped("boolToJsonNode") in called:
        blocks.append(_generate_bool_to_json_node_helper())

    if Stripped("stringToJsonNode") in called:
        blocks.append(_generate_string_to_json_node_helper())

    if Stripped("longToJsonNode") in called:
        blocks.append(_generate_long_to_json_node_helper())

    if Stripped("doubleToJsonNode") in called:
        blocks.append(_generate_double_to_json_node_helper())

    if Stripped("bytesToJsonNode") in called:
        blocks.append(_generate_bytes_to_json_node_helper())

    blocks.extend(_generate_json_able_serializer(symbol_table=symbol_table))

    for type_anno in _composed_serializer_type_annotations(symbol_table):
        blocks.append(_generate_composed_serializer(type_anno))

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
            blocks.append(
                _generate_transform_for_class(
                    cls=our_type,
                )
            )
        elif isinstance(our_type, intermediate.NamedUnion):
            # A named union is never double-dispatched here directly -- it
            # is unwrapped by the single shared ``transformUnion`` instead
            # (see :py:func:`_generate_transform_union_helper`).
            pass

        else:
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    writer.write(
        """\
private static class _Transformer extends AbstractTransformer<JsonNode> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_serialize(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the static serializer."""
    blocks: List[Stripped] = [
        Stripped(
            f"""\
/**
 * Serialize an instance of the meta-model into a JSON object.
 *
 * @throws SerializeException if a value within {{@code that}} instance can
 * not be represented in JSON
 */
public static JsonNode toJsonObject(IClass that) {{
{I}try {{
{II}return _Transformer.transformClass(that);
{I}}} catch (_SerializeFailure failure) {{
{II}final Reporting.Error error = failure.getError();
{II}throw new SerializeException(
{III}Reporting.generateJavaPath(error.getPathSegments()),
{III}error.getCause());
{I}}}
}}"""
        ),
    ]

    if intermediate_uses.json_types(symbol_table):
        blocks.append(
            Stripped(
                f"""\
/**
 * Serialize the JSON-able value {{@code that}} into a JSON node.
 *
 * <p>The result is a deep copy, and never {{@code that}} itself. A null node
 * is written as a JSON null.
 *
 * @throws SerializeException if {{@code that}} contains, at any depth,
 * a missing node, an infinity, a not-a-number or an integer outside
 * the safe integer range [-2^53 + 1, 2^53 - 1]
 */
public static JsonNode jsonValueToJsonNode(JsonNode that) {{
{I}try {{
{II}return _Transformer.jsonValueToJsonNode(that);
{I}}} catch (_SerializeFailure failure) {{
{II}final Reporting.Error error = failure.getError();
{II}throw new SerializeException(
{III}Reporting.generateJavaPath(error.getPathSegments()),
{III}error.getCause());
{I}}}
}}"""
            )
        )

    if len(symbol_table.enumerations) > 0:
        # NOTE (mristin):
        # A literal carries its own text, so a single non-generic method
        # serializes a literal of any enumeration. The methods which follow
        # are kept for the sake of the type safety at the call site -- each
        # one admits only the literals of its own enumeration -- but they all
        # delegate here, so the serialization itself lives in one place.
        #
        # The name cannot collide with any of them: they are all named
        # ``{enumeration}ToJsonValue``, and an enumeration is never nameless.
        enum_to_json_value_name = java_naming.method_name(Identifier("to_json_value"))

        blocks.append(
            Stripped(
                f"""\
/**
 * Serialize a literal of any enumeration of the meta-model
 * into a JSON string.
 *
 * @throws IllegalArgumentException if {{@code that}} is not a valid literal
 */
public static JsonNode {enum_to_json_value_name}(IEnum that) {{
{I}if (that == null) {{
{II}throw new IllegalArgumentException("Invalid literal: " + that);
{I}}}
{I}return JsonNodeFactory.instance.textNode(that.literalText());
}}"""
            )
        )

        for enumeration in symbol_table.enumerations:
            name = java_naming.enum_name(enumeration.name)
            method_name = java_naming.method_name(
                Identifier(f"{enumeration.name}_to_json_value")
            )
            blocks.append(
                Stripped(
                    f"""\
/**
 * Serialize a literal of {name} into a JSON string.
 */
public static JsonNode {method_name}({name} that) {{
{I}return {enum_to_json_value_name}(that);
}}"""
                )
            )

    writer = io.StringIO()

    writer.write(
        """\
/**
 * Serialize instances of meta-model classes to JSON elements.
 *
"""
    )

    first_cls: Optional[intermediate.ClassUnion] = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )

    if first_cls is not None:
        cls_name: Optional[str] = None
        if isinstance(first_cls, intermediate.AbstractClass):
            cls_name = java_naming.interface_name(first_cls.name)
        elif isinstance(first_cls, intermediate.ConcreteClass):
            cls_name = java_naming.class_name(first_cls.name)
        else:
            assert_never(first_cls)

        an_instance_variable = java_naming.variable_name(Identifier("an_instance"))

        writer.write(
            f"""\
 * Here is an example how to serialize an instance of {cls_name}:
 * <pre>{{@code
 * {cls_name} {an_instance_variable} = new {cls_name}(
 *     // ... some constructor arguments ...
 * );
 * JsonNode element = Jsonization.Serialize.toJsonObject(
 * {II}{an_instance_variable}));
 * }}</pre>
 */
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

    writer.write("\n}")

    return Stripped(writer.getvalue())


# endregion

# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code for JSON de/serialization.
    """
    errors: List[Error] = []

    # NOTE (mristin):
    # An ``ArrayNode`` is only ever built by a composed serializer, and
    # a ``Function`` is only ever taken by ``tryEnumFrom`` and by the array and
    # the tuple parsers, so a model which composes nothing needs neither
    # import. The serialization no longer takes a ``Function`` at all -- every
    # composed serializer writes out its loop and calls the conversions
    # directly (see :py:func:`_generate_composed_serializer`).
    composes_a_container = len(_composed_serializer_type_annotations(symbol_table)) > 0

    needs_function = (
        len(symbol_table.enumerations) > 0
        or len(_composed_type_annotations(symbol_table)) > 0
    )

    imports: List[Stripped] = [
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.reporting.Reporting;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.impl.*;"),
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.stringification.Stringification;"),
        Stripped(f"import {package}.visitation.AbstractTransformer;"),
        Stripped("import com.fasterxml.jackson.databind.JsonNode;"),
    ]

    if composes_a_container or intermediate_uses.json_types(symbol_table):
        imports.append(
            Stripped("import com.fasterxml.jackson.databind.node.ArrayNode;")
        )

    # NOTE (mristin):
    # We import the types of ``java.util`` one by one, and not on demand with
    # a wildcard, since a class of the meta-model imported on demand as well,
    # *e.g.*, ``Collection``, would make every reference to it ambiguous.
    imports.extend(
        [
            Stripped("import com.fasterxml.jackson.databind.node.JsonNodeFactory;"),
            Stripped("import com.fasterxml.jackson.databind.node.ObjectNode;"),
        ]
    )

    if intermediate_uses.json_types(symbol_table) or intermediate_uses.integers(
        symbol_table
    ):
        imports.append(Stripped(f"import {package}.verification.Verification;"))

    if intermediate_uses.integers(symbol_table):
        imports.append(Stripped("import java.math.BigInteger;"))

    imports.extend(
        [
            Stripped("import java.util.ArrayList;"),
            Stripped("import java.util.Base64;"),
            Stripped("import java.util.HashSet;"),
            Stripped("import java.util.Iterator;"),
            Stripped("import java.util.List;"),
            Stripped("import java.util.Map;"),
            Stripped("import java.util.Optional;"),
            Stripped("import java.util.Set;"),
        ]
    )

    if needs_function:
        imports.append(Stripped("import java.util.function.Function;"))

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
/**
* Represent a critical error during the deserialization.
*/
@SuppressWarnings("serial")
{I}public static class DeserializeException extends RuntimeException {{
{II}private final String path;
{II}private final String reason;

{II}public DeserializeException(String path, String reason) {{
{III}super(reason + " at: " + ("".equals(path) ? "the beginning" : path));
{III}this.path = path;
{III}this.reason = reason;
{II}}}

{II}public Optional<String> getPath() {{
{III}return Optional.ofNullable(path);
{II}}}

{II}public Optional<String> getReason() {{
{III}return Optional.ofNullable(reason);
{II}}}
{I}}}

/**
* Represent a critical error during the serialization.
*/
@SuppressWarnings("serial")
{I}public static class SerializeException extends RuntimeException {{
{II}private final String path;
{II}private final String reason;

{II}public SerializeException(String path, String reason) {{
{III}super(reason + " at: " + ("".equals(path) ? "the beginning" : path));
{III}this.path = path;
{III}this.reason = reason;
{II}}}

{II}public Optional<String> getPath() {{
{III}return Optional.ofNullable(path);
{II}}}

{II}public Optional<String> getReason() {{
{III}return Optional.ofNullable(reason);
{II}}}
{I}}}

/**
* Signal a failure of the serialization, carrying the path to the culprit.
*
* <p>The path is built as the stack unwinds -- every container prepends
* the one segment it knows, the property its name and the list the index
* of the item -- which is why this can not be a
* {{@link SerializeException}} already: that one renders its message in
* its constructor, so its path has to be complete by then.
* {{@link Serialize#toJsonObject}} renders and converts.
*/
@SuppressWarnings("serial")
{I}private static class _SerializeFailure extends RuntimeException {{
{II}private final Reporting.Error error;

{II}_SerializeFailure(Reporting.Error error) {{
{III}super(error.getCause());
{III}this.error = error;
{II}}}

{II}Reporting.Error getError() {{
{III}return error;
{II}}}
{I}}}"""
    )

    jsonization_blocks: List[Stripped] = [
        deserialize_impl_block,
        exception_block,
        deserialize_block,
        transformer_block,
        serialize_block,
    ]

    jsonization_writer = io.StringIO()
    jsonization_writer.write(
        """\
/**
 * Provide de/serialization of meta-model classes to/from JSON.
 *
 * <p>We can not use one-pass deserialization for JSON since the object
 * properties do not have fixed order, and hence we can not read
 * {@code modelType} property ahead of the remaining properties.
 */
public class Jsonization {
"""
    )

    for i, deserialize_block in enumerate(jsonization_blocks):
        if i > 0:
            jsonization_writer.write("\n\n")

        jsonization_writer.write(textwrap.indent(deserialize_block, II))

    jsonization_writer.write("\n}")

    if len(errors) > 0:
        return None, errors

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.jsonization;"),
        Stripped("\n".join(imports)),
        Stripped(jsonization_writer.getvalue()),
        java_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return [java_common.JavaFile("Jsonization.java", writer.getvalue())], None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
