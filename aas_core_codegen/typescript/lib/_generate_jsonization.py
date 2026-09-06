"""Generate code for JSON de/serialization."""

import io
import textwrap
from typing import Tuple, Optional, List

from icontract import ensure

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
    description as typescript_description,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


# region De-serialization


def _generate_parse_array() -> Stripped:
    """Generate the generic helper to parse a JSON array item-by-item."""
    return Stripped(
        f"""\
/**
 * Parse every item of `iterable` with `parseItem`.
 *
 * @param iterable - to be parsed item-by-item
 * @param parseItem - to parse a single item of `iterable`
 * @returns parsed items, or an error
 * @typeParam T - type of a single parsed item
 */
function parseArray<T>(
{I}iterable: Iterable<JsonValue>,
{I}parseItem: (
{II}jsonableItem: JsonValue
{I}) => AasCommon.Either<T, DeserializationError>
): AasCommon.Either<Array<T>, DeserializationError> {{
{I}const items = new Array<T>();
{I}let i = 0;
{I}for (const jsonableItem of iterable) {{
{II}const itemOrError = parseItem(jsonableItem);
{II}if (itemOrError.error !== null) {{
{III}itemOrError.error.path.prepend(new IndexSegment(iterable, i));
{III}return new AasCommon.Either<Array<T>, DeserializationError>(
{IIII}null,
{IIII}itemOrError.error
{III});
{II}}}
{II}items.push(itemOrError.mustValue());
{II}i++;
{I}}}
{I}return new AasCommon.Either<Array<T>, DeserializationError>(items, null);
}}"""
    )


def _generate_bool_from_jsonable() -> Stripped:
    """Generate the function to decode a ``bool`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as a boolean.
 *
 * @param jsonable - to be parsed
 * @returns parsed boolean value, or an error
 */
function booleanFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<boolean, DeserializationError> {{
{I}// `typeof` seems to be optimized these days, so we use it instead of
{I}// literal comparison, see:
{I}// https://stackoverflow.com/questions/61786250/is-typeof-faster-than-literal-comparison

{I}if (jsonable === null) {{
{II}return newDeserializationError<boolean>(
{III}"Expected a boolean, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "boolean") {{
{II}return newDeserializationError<boolean>(
{III}`Expected a boolean, but got ${{typeof jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<boolean, DeserializationError>(jsonable, null);
}}"""
    )


def _generate_int_from_jsonable() -> Stripped:
    """Generate the function to decode an ``int`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as an integer.
 *
 * @param jsonable - to be parsed
 * @returns parsed integer value, or an error
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function integerFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<number, DeserializationError> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<number>(
{III}"Expected an integer number, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "number") {{
{II}return newDeserializationError<number>(
{III}`Expected an integer number, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}if (!Number.isInteger(jsonable)) {{
{II}return newDeserializationError<number>(
{III}`Expected an integer number, but got: ${{jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<number, DeserializationError>(jsonable, null);
}}"""
    )


def _generate_float_from_jsonable() -> Stripped:
    """Generate the function to decode a ``float`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as a number.
 *
 * @param jsonable - to be parsed
 * @returns parsed numeric value, or an error
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function numberFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<number, DeserializationError> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<number>(
{III}"Expected a number, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "number") {{
{II}return newDeserializationError<number>(
{III}`Expected a number, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<number, DeserializationError>(jsonable, null);
}}"""
    )


def _generate_str_from_jsonable() -> Stripped:
    """Generate the function to decode a ``str`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as a string.
 *
 * @param jsonable - to be parsed
 * @returns parsed string value, or an error
 */
function stringFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<string, DeserializationError> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<string>(
{III}"Expected a string, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "string") {{
{II}return newDeserializationError<string>(
{III}`Expected a string, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<string, DeserializationError>(jsonable, null);
}}"""
    )


def _generate_bytes_from_jsonable() -> Stripped:
    """Generate the function to decode ``bytes`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as a byte array.
 *
 * @param jsonable - to be parsed
 * @returns parsed byte array, or an error
 */
function bytesFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<Uint8Array, DeserializationError> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<Uint8Array>(
{III}"Expected a base64-encoded string, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "string") {{
{II}return newDeserializationError<Uint8Array>(
{III}`Expected a base64-encoded string, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}const either = AasCommon.base64Decode(jsonable);
{I}if (either.error !== null) {{
{II}return newDeserializationError<Uint8Array>(either.error);
{I}}}
{I}return new AasCommon.Either<Uint8Array, DeserializationError>(
{II}either.mustValue(), null
{I});
}}"""
    )


def _generate_enumeration_from_jsonable(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the deserialization method for an enumeration."""
    enum_name = typescript_naming.enum_name(identifier=enumeration.name)

    function_name = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_from_jsonable")
    )

    enum_from_str = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    return Stripped(
        f"""\
/**
 * Parse `jsonable` structure as a literal
 * of {{@link {typescript_common.TYPES_MODULE}!{enum_name}}}.
 *
 * @param jsonable - to be parsed
 * @returns parsed literal, or an error if `jsonable` invalid
 */
export function {function_name}(
{I}jsonable: JsonValue
): AasCommon.Either<AasTypes.{enum_name}, DeserializationError> {{
{I}if (typeof jsonable !== "string") {{
{II}return newDeserializationError<AasTypes.{enum_name}>(
{III}`Expected a string, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}const literal = AasStringification.{enum_from_str}(jsonable);
{I}if (literal === null) {{
{II}return newDeserializationError<AasTypes.{enum_name}>(
{III}"Not a valid string representation of " +
{IIII}`a literal of {enum_name}: ${{jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<
{II}AasTypes.{enum_name},
{II}DeserializationError
{I}>(literal, null);
}}"""
    )


def _generate_dispatch_map_for_interface(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate a mapping model type 🠒 de-serialization function."""
    assert len(interface.base.concrete_descendants) > 0, (
        "Expected a class to have concrete descendants. "
        "Otherwise we do not know how to de-serialize it."
    )

    mapping_name = typescript_naming.constant_name(
        Identifier(f"{interface.name}_from_jsonable_dispatch")
    )

    interface_name = typescript_naming.interface_name(interface.name)

    mapping_writer = io.StringIO()
    mapping_writer.write(
        f"""\
const {mapping_name} =
{I}new Map<
{II}string,
{II}(JsonValue) => AasCommon.Either<
{III}AasTypes.{interface_name},
{III}DeserializationError
{II}>
{I}>(
{II}[
"""
    )

    for i, implementer in enumerate(interface.implementers):
        if len(implementer.concrete_descendants) == 0:
            function_name_for_implementer = typescript_naming.function_name(
                Identifier(f"{implementer.name}_from_jsonable")
            )
        else:
            # NOTE (mristin, 2022-11-25):
            # We can not use the public function as it would end in an endless dispatch
            # loop. Hence, we introduce a function which assumes the type and explicitly
            # does not dispatch.
            function_name_for_implementer = typescript_naming.function_name(
                Identifier(f"{implementer.name}_from_jsonable_without_dispatch")
            )

        implementer_literal = typescript_common.string_literal(
            naming.json_model_type(implementer.name)
        )

        mapping_writer.write(
            f"""\
{III}[
{IIII}{implementer_literal},
{IIII}{function_name_for_implementer}
{III}]"""
        )

        if i < len(interface.implementers) - 1:
            mapping_writer.write(",\n")
        else:
            mapping_writer.write("\n")

    mapping_writer.write(
        f"""\
{II}]
{I});"""
    )

    return Stripped(mapping_writer.getvalue())


def _generate_dispatch_from_jsonable(interface: intermediate.Interface) -> Stripped:
    """Generate the de-serialization dispatch for an abstract class."""
    function_name = typescript_naming.function_name(
        Identifier(f"{interface.name}_from_jsonable")
    )

    interface_name = typescript_naming.interface_name(interface.name)

    mapping_name = typescript_naming.constant_name(
        Identifier(f"{interface.name}_from_jsonable_dispatch")
    )

    return Stripped(
        f"""\
/**
 * Parse `jsonable` as an instance
 * of {{@link {typescript_common.TYPES_MODULE}!{interface_name}}}.
 *
 * @param jsonable - to be parsed
 * @returns parsed instance, or error if `jsonable` is invalid
 */
export function {function_name}(
{I}jsonable: JsonValue
): AasCommon.Either<
{I}AasTypes.{interface_name},
{I}DeserializationError
> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<AasTypes.{interface_name}>(
{III}"Expected a JSON object, but got null"
{II});
{I}}}
{I}if (Array.isArray(jsonable)) {{
{II}return newDeserializationError<AasTypes.{interface_name}>(
{III}"Expected a JSON object, but got a JSON array"
{II});
{I}}}
{I}if (typeof jsonable !== "object") {{
{II}return newDeserializationError<AasTypes.{interface_name}>(
{III}`Expected a JSON object, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}const modelType = jsonable["modelType"];
{I}if (modelType === undefined) {{
{II}return newDeserializationError<AasTypes.{interface_name}>(
{III}"The required property modelType is missing"
{II});
{I}}}

{I}if (typeof modelType !== "string") {{
{II}return newDeserializationError<AasTypes.{interface_name}>(
{III}`Expected the property modelType to be a string, but got: ${{typeof modelType}}`
{II});
{I}}}

{I}const dispatch = {mapping_name}.get(modelType);
{I}if (dispatch === undefined) {{
{II}return newDeserializationError<AasTypes.{interface_name}>(
{III}`Unexpected model type for {interface_name}: ${{modelType}}`
{II});
{I}}}

{I}return dispatch(jsonable);
}}"""
    )


_PARSE_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "booleanFromJsonable",
    intermediate.PrimitiveType.INT: "integerFromJsonable",
    intermediate.PrimitiveType.FLOAT: "numberFromJsonable",
    intermediate.PrimitiveType.STR: "stringFromJsonable",
    intermediate.PrimitiveType.BYTEARRAY: "bytesFromJsonable",
}
assert all(
    literal in _PARSE_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


def _parse_function_for_atomic_value(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """Determine the parse function for deserializing an atomic non-optional value."""
    function_name: str

    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        function_name = _PARSE_FUNCTION_BY_PRIMITIVE_TYPE[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            function_name = typescript_naming.function_name(
                Identifier(f"{our_type.name}_from_jsonable")
            )

        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            if our_type.interface is not None:
                assert our_type.interface.name == our_type.name, (
                    "Assume that the interface name and the class name in "
                    "the intermediate representation are the same, so that the "
                    "``*_from_jsonable`` name makes sense in all cases"
                )

            function_name = typescript_naming.function_name(
                Identifier(f"{our_type.name}_from_jsonable")
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            function_name = _PARSE_FUNCTION_BY_PRIMITIVE_TYPE[our_type.constrainee]

        else:
            assert_never(our_type)
    else:
        assert_never(type_annotation)

    return Stripped(function_name)


def _generate_setter(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate a class which allows us to dispatch de-serialization for properties."""
    blocks = []  # type: List[Stripped]

    for i, prop in enumerate(cls.properties):
        prop_name = typescript_naming.property_name(prop.name)
        prop_type = typescript_common.generate_type(
            prop.type_annotation, types_module=Identifier("AasTypes")
        )

        # NOTE (mristin, 2022-11-25):
        # We make all the properties optional since we switch over the properties
        # during the de-serialization.
        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            prop_type = Stripped(f"{prop_type} | null")

        blocks.append(Stripped(f"{prop_name}: {prop_type} = null;"))

    if cls.serialization.with_model_type:
        # NOTE (mristin):
        # If the serialization requires a model type, we consequently parse and set it
        # in the setter. The model type thus obtained is *not* used for any dispatch. We
        # only use this value for verification to make sure that the model type
        # of the instances is consistent with the expected value for its concrete
        # class. This will be performed even though the code might have had to parse
        # model type before for the dispatch. We decided to double-check to cover the
        # case where a dispatch is *unnecessary* (*e.g.*, the caller knows the expected
        # runtime type), but the model type might still be invalid in the input. Hence,
        # when the dispatch is *necessary*, the model type JSON property will be parsed
        # twice, which is a cost we currently find acceptable.
        prop_name = typescript_naming.property_name(Identifier("model_type"))
        blocks.append(
            Stripped(
                f"""\
// Used only for verification, not for dispatch!
{prop_name}: string | null = null;"""
            )
        )

    for i, prop in enumerate(cls.properties):
        prop_name = typescript_naming.property_name(prop.name)

        type_anno = intermediate.beneath_optional(prop.type_annotation)
        if isinstance(
            type_anno,
            (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
        ):
            function_name = _parse_function_for_atomic_value(type_anno)
            body = Stripped(
                f"""\
const parsedOrError = {function_name}(
{I}jsonable
);
if (parsedOrError.error !== null) {{
{I}return parsedOrError.error;
}} else {{
{I}this.{prop_name} = parsedOrError.mustValue();
{I}return null;
}}"""
            )

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert not isinstance(
                type_anno.items,
                (intermediate.OptionalTypeAnnotation, intermediate.ListTypeAnnotation),
            ), (
                "We chose to implement only a very limited pattern matching; "
                "see intermediate._translate_._verify_only_simple_type_patterns"
            )

            parse_function = _parse_function_for_atomic_value(type_anno.items)

            body = Stripped(
                f"""\
if (jsonable === null) {{
{I}return new DeserializationError(
{II}"Expected an iterable, but got null"
{I});
}}
if (typeof jsonable !== "object") {{
{I}return new DeserializationError(
{II}`Expected an iterable, but got: ${{typeof jsonable}}`
{I});
}}
if (typeof jsonable[Symbol.iterator] !== "function") {{
{I}return new DeserializationError(
{II}"Expected an iterable with iterator function, " +
{III}`but got iterator of type: ${{typeof jsonable[Symbol.iterator]}}`
{I});
}}

const iterable = <Iterable<JsonValue>>jsonable;

const itemsOrError = parseArray(
{I}iterable,
{I}{parse_function}
);
if (itemsOrError.error !== null) {{
{I}return itemsOrError.error;
}}

this.{prop_name} = itemsOrError.mustValue();
return null;"""
            )

        else:
            assert_never(type_anno)

        method_name = typescript_naming.method_name(
            Identifier(f"set_{prop.name}_from_jsonable")
        )

        method_writer = io.StringIO()
        method_writer.write(
            f"""\
/**
 * Parse `jsonable` as the value of {{@link {prop_name}}}.
 *
 * @param jsonable - to be parsed
 * @returns error, if any
 */
{method_name}(
{I}jsonable: JsonValue
): DeserializationError | null {{
{I}{indent_but_first_line(body, I)}
}}"""
        )

        blocks.append(Stripped(method_writer.getvalue()))

    if cls.serialization.with_model_type:
        method_name = typescript_naming.method_name(
            Identifier("set_model_type_from_jsonable")
        )
        prop_name = typescript_naming.property_name(Identifier("model_type"))

        blocks.append(
            Stripped(
                f"""\
/**
 * Parse `jsonable` as the model type of the concrete instance.
 *
 * This is intended only for verification, and no dispatch is performed.
 *
 * @param jsonable - to be parsed
 * @returns error, if any
 */
{method_name}(
{I}jsonable: JsonValue
): DeserializationError | null {{
{I}const parsedOrError = stringFromJsonable(
{II}jsonable
{I});
{I}if (parsedOrError.error !== null) {{
{II}return parsedOrError.error;
{I}}} else {{
{II}this.{prop_name} = parsedOrError.mustValue();
{II}return null;
{I}}}
}}"""
            )
        )

    cls_name = typescript_naming.class_name(cls.name)
    setter_cls_name = typescript_naming.class_name(Identifier(f"Setter_for_{cls.name}"))

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Provide de-serialize & set methods for properties
 * of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}}.
 */
class {setter_cls_name} {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_setter_map(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate a map ``JSON property name`` -> deserialization on a setter."""
    # fmt: off
    assert (
            sorted(
                (arg.name, str(arg.type_annotation))
                for arg in cls.constructor.arguments
            ) == sorted(
                (prop.name, str(prop.type_annotation))
                for prop in cls.properties
            )
    ), (
        "(mristin, 2022-11-25) We assume that the properties and constructor arguments "
        "are identical at this point. If this is not the case, we have to re-write the "
        "logic substantially! Please contact the developers if you see this."
    )
    # fmt: on

    identifiers_expressions = []  # type: List[Tuple[str, Stripped]]

    setter_cls_name = typescript_naming.class_name(Identifier(f"Setter_for_{cls.name}"))

    for prop in cls.properties:
        json_identifier: str = prop.json_name
        method_name = typescript_naming.method_name(
            Identifier(f"set_{prop.name}_from_jsonable")
        )

        identifiers_expressions.append(
            (json_identifier, Stripped(f"{setter_cls_name}.prototype.{method_name}"))
        )

    map_name = typescript_naming.constant_name(Identifier(f"setter_map_for_{cls.name}"))

    writer = io.StringIO()
    writer.write(
        f"""\
const {map_name} =
{I}new Map<
{II}string,
{II}(
{III}jsonable: JsonValue
{II}) => DeserializationError | null
{I}>(
{II}[
"""
    )

    for identifier, expression in identifiers_expressions:
        writer.write(
            f"""\
{III}[
{IIII}{typescript_common.string_literal(identifier)},
{IIII}{indent_but_first_line(expression, IIII)}
{III}],
"""
        )

    if cls.serialization.with_model_type:
        # NOTE (mristin):
        # If the serialization requires a model type, we consequently parse and set it
        # in the setter. The model type thus obtained is *not* used for any dispatch. We
        # only use this value for verification to make sure that the model type
        # of the instances is consistent with the expected value for its concrete
        # class. This will be performed even though the code might have had to parse
        # model type before for the dispatch. We decided to double-check to cover the
        # case where a dispatch is *unnecessary* (*e.g.*, the caller knows the expected
        # runtime type), but the model type might still be invalid in the input. Hence,
        # when the dispatch is *necessary*, the model type JSON property will be parsed
        # twice, which is a cost we currently find acceptable.
        json_identifier = naming.json_property(Identifier("model_type"))
        method_name = typescript_naming.method_name(
            Identifier("set_model_type_from_jsonable")
        )
        expression = Stripped(f"{setter_cls_name}.prototype.{method_name}")

        writer.write(
            f"""\
{III}[
{IIII}// The model type here is used only for verification, not for dispatch.
{IIII}{typescript_common.string_literal(json_identifier)},
{IIII}{indent_but_first_line(expression, IIII)}
{III}],
"""
        )

    writer.write(
        f"""\
{II}]
{I});"""
    )

    return Stripped(writer.getvalue())


def _generate_concrete_class_from_jsonable(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the deserialization function for a concrete class.

    This function performs no dispatch. If it de-serializes a concrete class with
    concrete descendants, we have to provide a different name. Otherwise, it would
    shadow the name for the dispatch function.
    """
    # fmt: off
    assert (
            sorted(
                (arg.name, str(arg.type_annotation))
                for arg in cls.constructor.arguments
            ) == sorted(
                (prop.name, str(prop.type_annotation))
                for prop in cls.properties
            )
    ), (
        "(mristin, 2022-11-30) We assume that the properties and constructor arguments "
        "are identical at this point. If this is not the case, we have to re-write the "
        "logic substantially! Please contact the developers if you see this."
    )
    # fmt: on

    cls_name = typescript_naming.class_name(cls.name)

    setter_cls_name = typescript_naming.class_name(Identifier(f"Setter_for_{cls.name}"))

    blocks = [
        Stripped(
            f"""\
if (jsonable === null) {{
{I}return newDeserializationError<AasTypes.{cls_name}>(
{II}"Expected a JSON object, but got null"
{I});
}}
if (Array.isArray(jsonable)) {{
{I}return newDeserializationError<AasTypes.{cls_name}>(
{II}"Expected a JSON object, but got a JSON array"
{I});
}}
if (typeof jsonable !== "object") {{
{I}return newDeserializationError<AasTypes.{cls_name}>(
{II}`Expected a JSON object, but got: ${{typeof jsonable}}`
{I});
}}"""
        ),
        Stripped(f"const setter = new {setter_cls_name}();"),
    ]  # type: List[Stripped]

    # region Switch on property name

    map_name = typescript_naming.constant_name(Identifier(f"setter_map_for_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
for (const key in jsonable) {{
{I}const jsonableValue = jsonable[key];
{I}const setterMethod =
{II}{map_name}.get(key);

{I}// NOTE (mristin, 2022-11-30):
{I}// Since we conflate here a JavaScript object with a JSON object, we ignore
{I}// properties which we do not know how to de-serialize and assume they are
{I}// related to the *JavaScript* properties of the object or `Object` prototype.
{I}if (setterMethod === undefined) {{
{II}continue;
{I}}}

{I}const error = setterMethod.call(setter, jsonableValue);
{I}if (error !== null) {{
{II}error.path.prepend(
{III}new PropertySegment(<JsonObject>jsonable, key)
{II});
{II}return new AasCommon.Either<
{III}AasTypes.{cls_name},
{III}DeserializationError
{II}>(
{IIII}null,
{IIII}error
{III});
{I}}}
}}"""
        )
    )

    # region Check required properties

    required_checks = []  # type: List[Stripped]
    for i, prop in enumerate(cls.properties):
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        prop_name = typescript_naming.property_name(prop.name)

        message_literal = typescript_common.string_literal(
            f"The required property {prop.json_name!r} is missing"
        )
        required_checks.append(
            Stripped(
                f"""\
if (setter.{prop_name} === null) {{
{I}return newDeserializationError<
{II}AasTypes.{cls_name}
{I}>(
{II}{message_literal}
{I});
}}"""
            )
        )

    if len(required_checks) > 0:
        blocks.append(Stripped("\n\n".join(required_checks)))

    # endregion

    if cls.serialization.with_model_type:
        model_type = naming.json_model_type(cls.name)
        prop_name = typescript_naming.property_name(Identifier("model_type"))

        blocks.append(
            Stripped(
                f"""\
if (setter.{prop_name} === null) {{
{I}return newDeserializationError<
{II}AasTypes.{cls_name}
{I}>(
{II}"The required property 'modelType' is missing"
{I});
}} else if (setter.{prop_name} != "{model_type}") {{
{I}return newDeserializationError<
{II}AasTypes.{cls_name}
{I}>(
{II}"Expected model type '{model_type}', " +
{II}`but got: ${{setter.{prop_name}}}`
{I});
}}"""
            )
        )

    # region Pass in arguments to the constructor

    cls_name = typescript_naming.class_name(cls.name)

    if len(cls.constructor.arguments) == 0:
        blocks.append(
            Stripped(
                f"""\
return new AasCommon.Either<
{I}AasTypes.{cls_name},
{I}DeserializationError
>(
{I}new AasTypes.{cls_name}(),
{I}null
);"""
            )
        )
    else:
        init_writer = io.StringIO()
        init_writer.write(
            f"""\
return new AasCommon.Either<
{I}AasTypes.{cls_name},
{I}DeserializationError
>(
{I}new AasTypes.{cls_name}(
"""
        )

        for i, arg in enumerate(cls.constructor.arguments):
            prop = cls.properties_by_name[arg.name]

            prop_name = typescript_naming.property_name(prop.name)

            init_writer.write(f"{II}setter.{prop_name}")

            if i < len(cls.constructor.arguments) - 1:
                init_writer.write(",\n")
            else:
                init_writer.write("\n")

        init_writer.write(
            f"""\
{I}),
{I}null
);"""
        )

        blocks.append(Stripped(init_writer.getvalue()))
    # endregion

    writer = io.StringIO()

    if len(cls._concrete_descendants) == 0:
        function_name = typescript_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )
    else:
        function_name = typescript_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable_without_dispatch")
        )

    description_blocks = [
        Stripped(
            f"""\
Parse an instance of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}} from the JSON-able
structure `jsonable`."""
        )
    ]  # type: List[Stripped]

    if len(cls.concrete_descendants) > 0:
        function_name_with_dispatch = typescript_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        description_blocks.append(
            Stripped(
                f"""\
This function performs no dispatch! It is used to parse the properties
as-are, and already assumes the exact model type. Usually, this function
is called from within a dispatching function, and you never call it
directly. If you want to de-serialize an instance of
{{@link {typescript_common.TYPES_MODULE}!{cls_name}}}, call
{{@link {function_name_with_dispatch}}}."""
            )
        )

    description_blocks.append(
        Stripped(
            f"""\
@param jsonable - structure to be parsed
@returns parsed instance of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}},
or an error if any"""
        )
    )

    description = "\n\n".join(description_blocks)
    description_comment = typescript_description.documentation_comment(
        Stripped(description)
    )

    # NOTE (mristin, 2022-11-30):
    # We export it only if the de-serialization of the class is equivalent to
    # the de-serialization without a dispatch.
    maybe_export_prefix = "export " if len(cls.concrete_descendants) == 0 else ""

    writer.write(
        f"""\
{description_comment}
{maybe_export_prefix}function {function_name}(
{I}jsonable: JsonValue
): AasCommon.Either<
{I}AasTypes.{cls_name},
{I}DeserializationError
> {{
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


def _generate_transform_atomic_value(
    access_expression: str, type_anno: intermediate.AtomicTypeAnnotation
) -> Stripped:
    """
    Generate the snippet to transform the ``access_expression``.

    The ``access_expression`` should either be a name or a member access.
    """
    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
        isinstance(type_anno, intermediate.OurTypeAnnotation)
        and isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive)
    ):
        a_type = intermediate.try_primitive_type(type_anno)
        assert a_type is not None

        if (
            a_type is intermediate.PrimitiveType.BOOL
            or a_type is intermediate.PrimitiveType.INT
            or a_type is intermediate.PrimitiveType.FLOAT
            or a_type is intermediate.PrimitiveType.STR
        ):
            return Stripped(f"{access_expression}")

        elif a_type is intermediate.PrimitiveType.BYTEARRAY:
            return Stripped(f"AasCommon.base64Encode({access_expression})")

        else:
            assert_never(a_type)

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            must_to_str_name = typescript_naming.function_name(
                Identifier(f"must_{type_anno.our_type.name}_to_string")
            )

            return Stripped(
                f"""\
AasStringification.{must_to_str_name}(
{I}{indent_but_first_line(access_expression, I)}
)"""
            )

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("This case should have been handled before.")

        elif isinstance(
            type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            return Stripped(f"this.transform({access_expression})")

        else:
            assert_never(type_anno.our_type)

    else:
        assert_never(type_anno.our_type)


def _generate_transform(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the ``transformX`` method to serialize an instance into a JSON-able."""
    blocks = [Stripped("const jsonable: JsonObject = {};")]  # type: List[Stripped]

    for prop in cls.properties:
        key_literal = typescript_common.string_literal(prop.json_name)
        prop_name = typescript_naming.property_name(prop.name)

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        block: Stripped

        if isinstance(
            type_anno,
            (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
        ):
            transformation_expression = _generate_transform_atomic_value(
                access_expression=Stripped(f"that.{prop_name}"), type_anno=type_anno
            )

            block = Stripped(
                f"""\
jsonable[{key_literal}] =
{I}{indent_but_first_line(transformation_expression, I)};"""
            )

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items,
                intermediate.AtomicTypeAnnotationAsTuple,
            ), (
                f"(mristin) We generate the JSON serialization code only for "
                f"the lists of atomic values at the moment, "
                f"but we got a list of type {type_anno}. "
                "Please contact the developers if you need this feature."
            )

            items_primitive_type = intermediate.try_primitive_type(type_anno.items)

            if items_primitive_type is not None and (
                items_primitive_type != intermediate.PrimitiveType.BYTEARRAY
            ):
                # NOTE (mristin):
                # No transformation is needed for these primitive types, so we
                # do not even need ``serializeArray`` -- a defensive copy of
                # the items suffices.
                block = Stripped(
                    f"jsonable[{key_literal}] = Array.from(that.{prop_name});"
                )

            elif items_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                block = Stripped(
                    f"""\
jsonable[{key_literal}] = serializeArray(
{I}that.{prop_name},
{I}AasCommon.base64Encode
);"""
                )

            elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                    must_to_str_name = typescript_naming.function_name(
                        Identifier(f"must_{type_anno.items.our_type.name}_to_string")
                    )

                    block = Stripped(
                        f"""\
jsonable[{key_literal}] = serializeArray(
{I}that.{prop_name},
{I}AasStringification.{must_to_str_name}
);"""
                    )

                elif isinstance(
                    type_anno.items.our_type, intermediate.ConstrainedPrimitive
                ):
                    raise AssertionError("This case should have been handled before.")

                elif isinstance(
                    type_anno.items.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    # NOTE (mristin):
                    # ``this.transform`` needs a bound ``this``, so this is the
                    # one case where we can not pass a bare function reference.
                    block = Stripped(
                        f"""\
jsonable[{key_literal}] = serializeArray(
{I}that.{prop_name},
{I}(item) => this.transform(item)
);"""
                    )

                else:
                    assert_never(type_anno.items.our_type)

            else:
                raise NotImplementedError(
                    f"(mristin) We generate the JSON serialization code only for "
                    f"the lists of atomic values at the moment, "
                    f"but we got a list of type {type_anno}. "
                    "Please contact the developers if you need this feature."
                )

        else:
            assert_never(type_anno)

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            block = Stripped(
                f"""\
if (that.{prop_name} !== null) {{
{I}{indent_but_first_line(block, I)}
}}"""
            )

        blocks.append(block)

    if cls.serialization.with_model_type:
        model_type_literal = typescript_common.string_literal(
            naming.json_model_type(cls.name)
        )
        blocks.append(Stripped(f"""jsonable["modelType"] = {model_type_literal};"""))

    blocks.append(Stripped("return jsonable;"))

    method_name = typescript_naming.method_name(Identifier(f"transform_{cls.name}"))

    cls_name = typescript_naming.class_name(cls.name)

    writer = io.StringIO()

    writer.write(
        f"""\
/**
 * Serialize `that` to a JSON-able representation.
 *
 * @param that - instance to be serialization
 * @returns JSON-able representation
 */
{method_name}(
{I}that: AasTypes.{cls_name}
): JsonObject {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_serialize_array() -> Stripped:
    """Generate the generic helper to serialize an iterable into a JSON array."""
    return Stripped(
        f"""\
/**
 * Serialize every item of `items` with `serializeItem` into a JSON-able
 * array.
 *
 * @param items - to be serialized
 * @param serializeItem - to serialize a single item of `items`
 * @returns JSON-able array
 * @typeParam T - type of a single item to be serialized
 * @typeParam J - type of a single item once serialized
 */
function serializeArray<T, J extends JsonValue>(
{I}items: Iterable<T>,
{I}serializeItem: (item: T) => J
): Array<J> {{
{I}const result = new Array<J>();
{I}for (const item of items) {{
{II}result.push(serializeItem(item));
{I}}}
{I}return result;
}}"""
    )


def _generate_transformer(symbol_table: intermediate.SymbolTable) -> Stripped:
    methods = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        methods.append(_generate_transform(cls))

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Transform the instance to its JSON-able representation.
 */
class Serializer extends AasTypes.AbstractTransformer<JsonObject> {
"""
    )

    for method in methods:
        writer.write("\n\n")
        writer.write(textwrap.indent(method, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


# endregion

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
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for JSON de/serialization."""
    blocks = [
        typescript_description.documentation_comment(
            Stripped(
                """\
Provide de/serialization of AAS classes to/from JSON.

We can not use one-pass deserialization for JSON since the object
properties do not have fixed order, and hence we can not read
`modelType` property ahead of the remaining properties."""
            )
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasCommon from "./common";
import * as AasTypes from "./types";
import * as AasStringification from "./stringification";"""
        ),
        Stripped(
            """\
export type JsonValue = string | number | boolean | JsonObject | JsonArray;

export type JsonArray = Iterable<JsonValue>;
export type JsonObject = { [prop: string]: JsonValue };"""
        ),
        Stripped(
            f"""\
/**
 * Represent a property on a path to the erroneous value.
 */
export class PropertySegment {{
{I}/**
{I} * Instance that contains the property
{I} */
{I}readonly instance: JsonObject;

{I}/**
{I} * Name of the property
{I} */
{I}readonly name: string;

{I}constructor(instance: JsonObject, name: string) {{
{II}this.instance = instance;
{II}this.name = name;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent an index access on a path to the erroneous value.
 */
export class IndexSegment {{
{I}/**
{I} * Container that contains the item
{I} */
{I}readonly container: JsonArray;

{I}/**
{I} * Index of the item
{I} */
{I}readonly index: number;

{I}constructor(container: JsonArray, index: number) {{
{II}if (!Number.isInteger(index)) {{
{III}throw new Error(`Expected an integer for the index, but got: ${{index}}`);
{II}}}

{II}this.container = container;
{II}this.index = index;
{I}}}
}}"""
        ),
        Stripped(
            """\
export type Segment = PropertySegment | IndexSegment;"""
        ),
        Stripped(
            f"""\
/**
 * Represent the relative path to the erroneous value.
 */
export class Path {{
{I}private readonly _segments = new Array<Segment>();

{I}/**
{I} * Get the segments of the path.
{I} */
{I}segments(): Array<Segment> {{
{II}return this._segments;
{I}}}

{I}/**
{I} * Insert the `segment` in front of the {{@link segments}}.
{I} *
{I} * @param segment - segment to be prepended to {{@link segments}}
{I} */
{I}prepend(segment: Segment): void {{
{II}this._segments.unshift(segment);
{I}}}

{I}toString(): string {{
{II}if (this._segments.length === 0) {{
{III}return "";
{II}}}

{II}const parts = new Array<string>();

{II}let segment = this._segments[0];

{II}if (segment instanceof PropertySegment) {{
{III}parts.push(segment.name);
{II}}} else if (segment instanceof IndexSegment) {{
{III}parts.push(`[${{segment.index}}]`);
{II}}} else {{
{III}throw new Error(`Unexpected segment: ${{segment}}`);
{II}}}

{II}for (let i = 1; i < this._segments.length; i++) {{
{III}segment = this._segments[i];
{III}if (segment instanceof PropertySegment) {{
{IIII}parts.push(`.${{segment.name}}`);
{III}}} else if (segment instanceof IndexSegment) {{
{IIII}parts.push(`[${{segment.index}}]`);
{III}}} else {{
{IIII}throw new Error(`Unexpected segment: ${{segment}}`);
{III}}}
{II}}}

{II}return parts.join("");
{I}}}
}}"""
        ),
        Stripped("// region De-serialization"),
        Stripped(
            f"""\
/**
 * Signal that the JSON de-serialization could not be performed.
 */
export class DeserializationError {{
{I}/**
{I} * Human-readable explanation of the error
{I} */
{I}readonly message: string;

{I}/**
{I} * Relative path to the erroneous value
{I} */
{I}readonly path: Path;

{I}constructor(message: string, path: Path | null = null) {{
{II}this.message = message;
{II}this.path = path ?? new Path();
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Create an error as {{@link common.Either}}.
 *
 * @param message - human-readable explanation of the error
 * @returns An {{@link common.Either }} with the error set
 * @typeParam T - type of the value if there had been no error
 */
function newDeserializationError<T>(
{I}message: string
): AasCommon.Either<T, DeserializationError> {{
{I}return new AasCommon.Either<T, DeserializationError>(
{II}null,
{II}new DeserializationError(message)
{I});
}}"""
        ),
        _generate_parse_array(),
        _generate_bool_from_jsonable(),
        _generate_int_from_jsonable(),
        _generate_float_from_jsonable(),
        _generate_str_from_jsonable(),
        _generate_bytes_from_jsonable(),
    ]  # type: List[Stripped]

    errors = []  # type: List[Error]

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_enumeration_from_jsonable(enumeration=our_type))
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            pass
        elif isinstance(our_type, intermediate.AbstractClass):
            blocks.append(
                _generate_dispatch_from_jsonable(interface=our_type.interface)
            )
        elif isinstance(our_type, intermediate.ConcreteClass):
            if len(our_type.concrete_descendants) > 0:
                assert our_type.interface is not None
                blocks.append(
                    _generate_dispatch_from_jsonable(interface=our_type.interface)
                )

            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Jsonization/{our_type.name}_from_jsonable.ts"
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
            else:
                # NOTE (mristin, 2022-11-25):
                # While TypeScript supports ``switch`` statement, it is not guaranteed
                # to run in sublinear time. Hence, we have to create a map with set
                # methods, see:
                # https://stackoverflow.com/questions/41109196/is-javascript-switch-statement-linear-or-constant-time
                blocks.append(_generate_setter(cls=our_type))

                blocks.append(_generate_concrete_class_from_jsonable(cls=our_type))
        else:
            assert_never(our_type)

    # NOTE (mristin, 2022-11-25):
    # We add all the dispatch mappings at the end as the functions might not have been
    # defined yet.
    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.AbstractClass):
            blocks.append(_generate_dispatch_map_for_interface(interface=cls.interface))
        elif isinstance(cls, intermediate.ConcreteClass):
            if len(cls.concrete_descendants) > 0:
                assert (
                    cls.interface is not None
                ), "Expected an interface on a class with concrete descendants"

                blocks.append(
                    _generate_dispatch_map_for_interface(interface=cls.interface)
                )

            if not cls.is_implementation_specific:
                blocks.append(_generate_setter_map(cls=cls))

        else:
            assert_never(cls)

    blocks.append(Stripped("// endregion"))

    blocks.append(Stripped("// region Serialization"))

    blocks.append(_generate_serialize_array())

    blocks.append(_generate_transformer(symbol_table=symbol_table))

    blocks.append(Stripped("const SERIALIZER = new Serializer();"))

    # pylint: disable=line-too-long
    blocks.append(
        Stripped(
            f"""\
/**
 * Convert `that` to a JSON-able structure.
 *
 * @param that - AAS data to be recursively converted to a JSON-able structure
 * @returns
 * JSON-able structure which can be further processed with, say,
 * {{@link https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/JSON/stringify|JSON.stringify}})
 */
export function toJsonable(that: AasTypes.Class): JsonObject {{
{I}return SERIALIZER.transform(that);
}}"""
        )
    )
    # pylint: enable=line-too-long

    blocks.append(Stripped("// endregion"))

    if len(errors) > 0:
        return None, errors

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
