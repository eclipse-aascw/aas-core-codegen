"""Generate code for JSON de/serialization."""

import io
import textwrap
from typing import Final, List, Optional, Set, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)

# region De-serialization

#: Maximal length of a generated line before a call is broken over two lines
_MAX_LINE_LENGTH: Final[int] = 100

#: Indentation, in characters, of the body of a function of
#: the de-serialization implementation. The body sits four levels deep: the class
#: ``Jsonization``, the class ``_DeserializeImplementation``, the function and
#: finally its body.
_FUNCTION_BODY_INDENTATION: Final[int] = len(I) * 4

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
    parse_method = None  # type: Optional[str]

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
    else:
        assert_never(type_annotation)

    return Identifier(parse_method)


def _parse_method_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Name the function parsing a value of ``type_anno`` from a JSON node.

    An atomic value already has a function of its own to be named after. A list
    and a tuple do not, so they are composed out of the parsers of their items
    and named by the moniker of the type (see
    :py:func:`aas_core_codegen.java.common.type_moniker`).
    """
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation)
    ):
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
    assert isinstance(type_anno, intermediate.AtomicTypeAnnotationAsTuple), (
        f"We only support lists and tuples of atomic values (primitives, "
        f"constrained primitives, enumeration literals) or classes when "
        f"de-serializing from JSON, but got the nested type {type_anno}. "
        f"Please contact the developers if you need this feature."
    )

    return Stripped(
        f"{_DESERIALIZE_IMPL_NAME}::{_parse_method_for_atomic_value(type_anno)}"
    )


def _from_method_name(cls: intermediate.ClassUnion) -> Identifier:
    """Name the function parsing an instance of ``cls`` from a JSON node."""
    return Identifier(f"try{java_naming.class_name(cls.name)}From")


def _from_object_method_name(cls: intermediate.ConcreteClass) -> Identifier:
    """
    Name the function parsing ``cls`` from a JSON object of a checked model type.

    A dispatcher has already read the model type in order to dispatch on it, so
    the function it dispatches to must not read it a second time. A class which
    carries no model type has nothing to check in the first place, and
    an implementation-specific class brings its own function, so in both cases
    this is simply :py:func:`_from_method_name`.
    """
    if not cls.serialization.with_model_type or cls.is_implementation_specific:
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
{II}error.prependSegment(new Reporting.NameSegment("modelType"));
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
    result = []  # type: List[intermediate.TypeAnnotationUnion]
    observed = set()  # type: Set[str]

    for cls in symbol_table.concrete_classes:
        for arg in cls.constructor.arguments:
            type_anno = intermediate.beneath_optional(arg.type_annotation)

            if not isinstance(
                type_anno,
                (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
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

        description = (
            f"a list of {{@code {java_common.generate_type(type_anno.items)}}}"
        )

        body = Stripped(f"return parseArray(node, {item_parser});")
        if _FUNCTION_BODY_INDENTATION + len(body) > _MAX_LINE_LENGTH:
            body = Stripped(
                f"""\
return parseArray(
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
            f"Expected a list or a tuple type annotation, but got: {type_anno}"
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

    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation)
    ):
        # NOTE (mristin):
        # A list and a tuple are parsed into their exact type, whereas an atomic
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
    errors = []  # type: List[Error]

    name = java_naming.class_name(cls.name)

    blocks = []  # type: List[Stripped]

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

    cases = [
        _generate_case_for_argument(arg=arg, cls=cls)
        for arg in cls.constructor.arguments
    ]  # type: List[Stripped]

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
            set(prop.name for prop in cls.properties)
            == set(arg.name for arg in cls.constructor.arguments)
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

    blocks = [
        _generate_json_object_guard(),
    ]  # type: List[Stripped]

    if len(with_model_type) > 0:
        switch_writer = io.StringIO()
        switch_writer.write("switch (modelTypeResult.getResult()) {\n")

        for implementer in with_model_type:
            model_type = naming.json_model_type(implementer.name)
            implementer_name = java_naming.class_name(implementer.name)
            switch_writer.write(
                f"""\
{I}case {java_common.string_literal(model_type)}: {{
{II}final Reporting.Result<{implementer_name}> result =
{III}{_from_object_method_name(implementer)}(node);
{II}if (result.isError()) {{
{III}return result.castTo({name}.class);
{II}}}
{II}return Reporting.Result.success({name}.from{implementer_name}(result.getResult()));
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
{I}return Reporting.Result.success({name}.from{implementer_name}(result.getResult()));
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


def _generate_primitive_parsers() -> List[Stripped]:
    """Generate the parsers of the primitive JSON values."""
    return [
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
        Stripped(
            f"""\
/** Convert {{@code value}} to a long 64-bit integer.
 * @param node JSON node to be parsed
 */
private static Reporting.Result<Long> tryLongFrom(JsonNode value) {{
{I}if (!value.isIntegralNumber()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a JsonValue of Long, but got " + value.getNodeType());
{II}return Reporting.Result.failure(error);
{I}}}
{I}return Reporting.Result.success(value.asLong());
}}"""
        ),
        Stripped(
            f"""\
/** Convert {{@code value}} to a double-precision 64-bit float.
 * @param node JSON node to be parsed
 */
private static Reporting.Result<Double> tryDoubleFrom(JsonNode value) {{
{I}if (!value.isFloatingPointNumber()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a JsonValue of Double, but got " + value.getNodeType());
{II}return Reporting.Result.failure(error);
{I}}}
{I}return Reporting.Result.success(value.asDouble());
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


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_deserialize_impl(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the implementation of the deserialization."""
    errors = []  # type: List[Error]

    # region Decide which of the shared helpers are needed

    # NOTE (mristin):
    # The helpers follow the call graph: a model which never composes a list
    # pays for neither the composition nor the errors which only it can report.

    parsed_classes = [
        cls
        for cls in symbol_table.concrete_classes
        if not cls.is_implementation_specific
    ]

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

    tuple_arities = intermediate.tuple_arities(symbol_table)

    #: Both the array helper and the tuple helpers report a non-array and mark
    #: the index of the item which failed.
    needs_array_helpers = needs_parse_array or len(tuple_arities) > 0

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

    blocks = _generate_primitive_parsers()  # type: List[Stripped]

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

    for arity in tuple_arities:
        blocks.append(_generate_parse_tuple_helper(arity=arity))

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
                if our_type.is_implementation_specific:
                    implementation_key = specific_implementations.ImplementationKey(
                        f"Jsonization/DeserializeImplementation/{our_type.name}_from.java"
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
                    cls_blocks, cls_errors = _generate_from_methods_for_class(
                        cls=our_type
                    )
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


def _generate_deserialize(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the deserializer with a deserialization method for each class."""
    blocks = []  # type: List[Stripped]
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

    first_cls = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )  # type: Optional[intermediate.ClassUnion]

    if first_cls is not None:
        cls_name = None  # type: Optional[str]
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


def _generate_serialize_primitive_value(
    primitive_type: intermediate.PrimitiveType, source_expr: Stripped
) -> Stripped:
    """
    Generate the snippet to serialize ``source_expr`` to JSON.

    Source expression is expected to be of ``primitive_type``.
    """
    if primitive_type is intermediate.PrimitiveType.BOOL:
        # We can not use textwrap due to indent_but_first_line.
        return Stripped(
            f"""\
JsonNodeFactory.instance.booleanNode(
{I}{indent_but_first_line(source_expr, I)})"""
        )
    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        # We can not use textwrap due to indent_but_first_line.
        return Stripped(
            f"""\
JsonNodeFactory.instance.numberNode(
{I}{indent_but_first_line(source_expr, I)})"""
        )
    elif primitive_type is intermediate.PrimitiveType.STR:
        # We can not use textwrap due to indent_but_first_line.
        return Stripped(
            f"""\
JsonNodeFactory.instance.textNode(
{I}{indent_but_first_line(source_expr, I)})"""
        )
    elif primitive_type is intermediate.PrimitiveType.INT:
        # We can not use textwrap due to indent_but_first_line.
        return Stripped(
            f"""\
_Transformer.toJsonNode(
{I}{indent_but_first_line(source_expr, I)})"""
        )
    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        # We can not use textwrap due to indent_but_first_line.
        return Stripped(
            f"""\
_Transformer.bytesToJsonNode(
{I}{indent_but_first_line(source_expr, I)})"""
        )
    else:
        assert_never(primitive_type)


def _serialize_method_reference_for_primitive_type(
    primitive_type: intermediate.PrimitiveType,
) -> Stripped:
    """Determine a bare method reference for serializing a primitive value."""
    if primitive_type is intermediate.PrimitiveType.BOOL:
        return Stripped("JsonNodeFactory.instance::booleanNode")
    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        return Stripped("JsonNodeFactory.instance::numberNode")
    elif primitive_type is intermediate.PrimitiveType.STR:
        return Stripped("JsonNodeFactory.instance::textNode")
    elif primitive_type is intermediate.PrimitiveType.INT:
        return Stripped("_Transformer::toJsonNode")
    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Stripped("_Transformer::bytesToJsonNode")
    else:
        assert_never(primitive_type)


def _serialize_method_reference_for_atomic_value(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """
    Determine a bare method reference for serializing an atomic value to JSON.

    The reference matches ``Function<T, JsonNode>`` for the item's Java type
    ``T``, so it can be passed on directly wherever such a function is
    expected (e.g. as an item serializer in a list or a tuple), with no
    closure needed.
    """
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return _serialize_method_reference_for_primitive_type(type_annotation.a_type)

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type
        if isinstance(our_type, intermediate.Enumeration):
            method_name = java_naming.method_name(
                Identifier(f"{our_type.name}_to_json_value")
            )
            return Stripped(f"Serialize::{method_name}")
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return _serialize_method_reference_for_primitive_type(our_type.constrainee)
        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            # NOTE (mristin):
            # ``transform`` is an instance method of the enclosing
            # ``_Transformer`` class itself, dispatching through the visitor
            # pattern, so it is referenced bound to ``this``. A named union
            # is matched by its own ``transform`` overload (see
            # :py:func:`_generate_union_transform_helper`), so it can
            # be referenced exactly like a class.
            return Stripped("this::transform")
        else:
            assert_never(our_type)
    else:
        assert_never(type_annotation)


def _generate_serialize_tuple_helper(arity: int) -> Stripped:
    """Generate the generic helper to serialize a tuple into a JSON array."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    tuple_type = f"Tuple{arity}<{', '.join(type_params)}>"

    param_lines = [f"{tuple_type} value"] + [
        f"Function<T{i + 1}, JsonNode> serializeItem{i + 1}" for i in range(arity)
    ]

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Serialize each item of {{@code value}} with the corresponding
 * {{@code serializeItemI}} into a JSON array.
 */
private static <{", ".join(type_params)}> ArrayNode serializeTuple{arity}(
"""
    )
    for i, param_line in enumerate(param_lines):
        writer.write(I)
        writer.write(param_line)
        writer.write(",\n" if i < len(param_lines) - 1 else ") {\n")

    writer.write(f"{I}final ArrayNode result = JsonNodeFactory.instance.arrayNode();\n")
    for i in range(arity):
        writer.write(
            f"""\
{I}result.add(
{II}serializeItem{i + 1}.apply(value.item{i + 1}()));
"""
        )
    writer.write(f"{I}return result;\n}}")

    return Stripped(writer.getvalue())


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
            method_name = java_naming.method_name(
                Identifier(f"{our_type.name}_to_json_value")
            )

            # We can not use textwrap due to indent_but_first_line.
            return Stripped(
                f"""\
Serialize.{method_name}(
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
            # A named union is matched by its own ``transform`` overload
            # (see :py:func:`_generate_union_transform_helper`), so it
            # can be transformed exactly like a class instance here.

            # We can not use textwrap due to indent_but_first_line.
            return Stripped(
                f"""\
transform(
{I}{indent_but_first_line(source_expr, I)})"""
            )
        else:
            assert_never(our_type)
    else:
        assert_never(type_annotation)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_transform_property(
    prop: intermediate.Property,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the snippet to transform a property into a JSON node."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    stmts = []  # type: List[Stripped]

    getter_name = java_naming.getter_name(prop.name)
    prop_literal = java_common.string_literal(prop.json_name)

    source_expr: Stripped

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        source_expr = Stripped(f"that.{getter_name}().get()")
    else:
        source_expr = Stripped(f"that.{getter_name}()")

    if isinstance(
        type_anno,
        intermediate.PrimitiveTypeAnnotation,
    ):
        conversion_expr = _generate_serialize_atomic_value(
            type_annotation=type_anno, source_expr=source_expr
        )

        # NOTE (empwilli):
        # We have to use ObjectNode.put for Strings but the function is deprecated for JsonObjects.
        if type_anno.a_type == intermediate.PrimitiveType.STR:
            stmts.append(Stripped(f"result.put({prop_literal}, {conversion_expr});"))
        else:
            stmts.append(Stripped(f"result.set({prop_literal}, {conversion_expr});"))
    elif isinstance(
        type_anno,
        intermediate.OurTypeAnnotation,
    ):
        conversion_expr = _generate_serialize_atomic_value(
            type_annotation=type_anno, source_expr=source_expr
        )
        stmts.append(Stripped(f"result.set({prop_literal}, {conversion_expr});"))
    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            f"We only support lists of atomic values (primitives, constrained "
            f"primitives, enumeration literals) or classes when serializing "
            f"to JSON, but the property {prop.name!r} has the unsupported "
            f"nested type {prop.type_annotation}. Please contact the "
            f"developers if you need this feature."
        )

        array_var = java_naming.variable_name(Identifier(f"array_{prop.name}"))

        item_serializer = _serialize_method_reference_for_atomic_value(type_anno.items)

        stmts.append(
            Stripped(
                f"""\
final ArrayNode {array_var} = serializeArray(
{I}{source_expr},
{I}{item_serializer});
result.set({prop_literal}, {array_var});"""
            )
        )
    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        arity = len(type_anno.items)
        array_var = java_naming.variable_name(Identifier(f"array_{prop.name}"))

        item_serializers = []  # type: List[Stripped]
        for item_type_anno in type_anno.items:
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"Expected an atomic tuple item (a primitive, a constrained "
                f"primitive, an enumeration or a class), but got {item_type_anno}. "
                f"This should have already been verified in "
                f"intermediate._translate._verify_only_simple_type_patterns."
            )

            item_serializers.append(
                _serialize_method_reference_for_atomic_value(item_type_anno)
            )

        joined_item_serializers = ",\n".join(item_serializers)

        stmts.append(
            Stripped(
                f"""\
final ArrayNode {array_var} = serializeTuple{arity}(
{I}{source_expr},
{I}{indent_but_first_line(joined_item_serializers, I)});
result.set({prop_literal}, {array_var});"""
            )
        )
    else:
        assert_never(type_anno)

    serialize_block = Stripped("\n".join(stmts))
    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return (
            Stripped(
                f"""\
if (that.{getter_name}().isPresent()) {{
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

    blocks = [
        Stripped("final ObjectNode result = JsonNodeFactory.instance.objectNode();"),
    ]  # type: List[Stripped]

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

    return Stripped(writer.getvalue()), None


def _generate_union_transform_helper() -> Stripped:
    """
    Generate a single ``transform`` overload shared by every named union.

    A named union is not itself an ``IClass``, so it can not be dispatched by
    the inherited, ``IClass``-typed ``transform(IClass)`` overload of
    ``AbstractTransformer``. We add this overload, single-purpose, next to
    the per-class ``transform_*`` overrides, so that call sites can keep
    passing ``transform`` around as a plain method reference or calling it
    directly, regardless of whether the value at hand is a class instance or
    a named union -- see :py:func:`_generate_serialize_atomic_value` and
    :py:func:`_serialize_method_reference_for_atomic_value`.

    Dispatching over the common ``IUnion<?>`` (see ``_generate_iunion`` in
    ``_generate_types.py``) instead of the union's own type means we need
    only this one overload for *all* named unions, not one per union.

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
private JsonNode transform(IUnion<?> that) {{
{I}return transform(that.getUnderlying());
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
/**
 * Convert {{@code that}} 64-bit long integer to a JSON value.
 *
 * @param that value to be converted
 */
private static JsonNode toJsonNode(Long that) {{
{I}// We need to check that we can perform a lossless conversion.
{I}long primitiveThat = that.longValue();
{I}if ((long)((double)primitiveThat) != primitiveThat) {{
{II}throw new IllegalArgumentException(
{III}"The number can not be losslessly represented in JSON: " + that);
{I}}}
{I}return JsonNodeFactory.instance.numberNode(that);
}}"""
        ),
        Stripped(
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
        ),
        Stripped(
            f"""\
/**
 * Serialize every item of {{@code items}} with {{@code serializeItem}} into
 * a JSON array.
 *
 * @param items to be serialized
 * @param serializeItem to serialize a single item of {{@code items}}
 */
private static <T> ArrayNode serializeArray(
{I}Iterable<T> items,
{I}Function<T, JsonNode> serializeItem) {{
{I}final ArrayNode result = JsonNodeFactory.instance.arrayNode();
{I}for (T item : items) {{
{II}result.add(
{III}serializeItem.apply(item));
{I}}}
{I}return result;
}}"""
        ),
    ]  # type: List[Stripped]

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_serialize_tuple_helper(arity=arity))

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
                    f"Jsonization/Transformer/transform_{our_type.name}.java"
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
            # is unwrapped by the single shared ``transform(IUnion<?>)``
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
    blocks = [
        Stripped("private static final _Transformer transformer = new _Transformer();"),
        Stripped(
            f"""\
/**
 * Serialize an instance of the meta-model into a JSON object.
 */
public static JsonNode toJsonObject(IClass that) {{
{I}return transformer.transform(that);
}}"""
        ),
    ]  # type: List[Stripped]

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

        for enum in symbol_table.enumerations:
            name = java_naming.enum_name(enum.name)
            method_name = java_naming.method_name(
                Identifier(f"{enum.name}_to_json_value")
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

    first_cls = (
        symbol_table.classes[0] if len(symbol_table.classes) > 0 else None
    )  # type: Optional[intermediate.ClassUnion]

    if first_cls is not None:
        cls_name = None  # type: Optional[str]
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
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code for JSON de/serialization.
    """
    errors = []  # type: List[Error]

    imports = [
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.reporting.Reporting;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.impl.*;"),
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.stringification.Stringification;"),
        Stripped(f"import {package}.visitation.AbstractTransformer;"),
        Stripped("import com.fasterxml.jackson.databind.JsonNode;"),
        Stripped("import com.fasterxml.jackson.databind.node.ArrayNode;"),
        Stripped("import com.fasterxml.jackson.databind.node.JsonNodeFactory;"),
        Stripped("import com.fasterxml.jackson.databind.node.ObjectNode;"),
        Stripped("import java.util.*;"),
        Stripped("import java.util.function.Function;"),
    ]  # type: List[Stripped]

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
{I}}}"""
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

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.jsonization;"),
        Stripped("\n".join(imports)),
        Stripped(jsonization_writer.getvalue()),
        java_common.WARNING,
    ]  # type: List[Stripped]

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
