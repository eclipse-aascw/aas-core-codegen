"""Generate code for XML de/serialization."""

import io
from typing import Tuple, Optional, List, Dict

from icontract import ensure, require

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
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


# region De-serialization


_PARSE_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: Identifier("parseBooleanText"),
    intermediate.PrimitiveType.INT: Identifier("parseIntegerText"),
    intermediate.PrimitiveType.FLOAT: Identifier("parseFloatText"),
    intermediate.PrimitiveType.STR: Identifier("parseStringText"),
    intermediate.PrimitiveType.BYTEARRAY: Identifier("parseBase64EncodedBytesText"),
}


def _generate_parse_text_for_primitive_type(
    primitive_type: intermediate.PrimitiveType,
) -> Stripped:
    """Generate parser for a primitive XML text representation."""
    if primitive_type is intermediate.PrimitiveType.BOOL:
        return Stripped(
            f"""\
function parseBooleanText(
{I}text: string
): AasCommon.Either<boolean, DeserializationError> {{
{I}if (text === "true" || text === "1") {{
{II}return new AasCommon.Either<boolean, DeserializationError>(true, null);
{I}}}
{I}if (text === "false" || text === "0") {{
{II}return new AasCommon.Either<boolean, DeserializationError>(false, null);
{I}}}

{I}return newDeserializationError<boolean>(
{II}`Expected xs:boolean text, but got: ${{text}}`
{I});
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.INT:
        return Stripped(
            f"""\
function parseIntegerText(
{I}text: string
): AasCommon.Either<number, DeserializationError> {{
{I}if (!/^[+-]?\\d+$/.test(text)) {{
{II}return newDeserializationError<number>(
{III}`Expected integer text, but got: ${{text}}`
{II});
{I}}}

{I}const value = Number(text);
{I}if (!Number.isInteger(value)) {{
{II}return newDeserializationError<number>(
{III}`Expected integer text, but got: ${{text}}`
{II});
{I}}}

{I}return new AasCommon.Either<number, DeserializationError>(value, null);
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        return Stripped(
            f"""\
function parseFloatText(
{I}text: string
): AasCommon.Either<number, DeserializationError> {{
{I}if (text === "INF") {{
{II}return new AasCommon.Either<number, DeserializationError>(Infinity, null);
{I}}}
{I}if (text === "-INF") {{
{II}return new AasCommon.Either<number, DeserializationError>(-Infinity, null);
{I}}}
{I}if (text === "NaN") {{
{II}return new AasCommon.Either<number, DeserializationError>(NaN, null);
{I}}}

{I}const value = Number(text);
{I}if (Number.isNaN(value)) {{
{II}return newDeserializationError<number>(
{III}`Expected xs:double text, but got: ${{text}}`
{II});
{I}}}

{I}return new AasCommon.Either<number, DeserializationError>(value, null);
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.STR:
        return Stripped(
            f"""\
function parseStringText(
{I}text: string
): AasCommon.Either<string, DeserializationError> {{
{I}return new AasCommon.Either<string, DeserializationError>(text, null);
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Stripped(
            f"""\
function parseBase64EncodedBytesText(
{I}text: string
): AasCommon.Either<Uint8Array, DeserializationError> {{
{I}const decodedOrError = AasCommon.base64Decode(text);
{I}if (decodedOrError.error !== null) {{
{II}return newDeserializationError<Uint8Array>(
{III}decodedOrError.error
{II});
{I}}}

{I}return new AasCommon.Either<Uint8Array, DeserializationError>(
{II}decodedOrError.mustValue(),
{II}null
{I});
}}"""
        )

    else:
        assert_never(primitive_type)


def _parse_function_for_atomic_type(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Identifier:
    """Resolve the generated parse helper for an atomic XML text value."""
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return _PARSE_FUNCTION_BY_PRIMITIVE_TYPE[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        assert not isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        )

        if isinstance(our_type, intermediate.Enumeration):
            return typescript_naming.function_name(
                Identifier(f"parse_{our_type.name}_text")
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return _PARSE_FUNCTION_BY_PRIMITIVE_TYPE[our_type.constrainee]

        else:
            assert_never(our_type)

    else:
        assert_never(type_annotation)


def _parse_sequence_function_name_for_concrete_class(
    cls: intermediate.ConcreteClass,
) -> Identifier:
    """
    Generate the name of the function to parse the sequence of properties of ``cls``.

    The function assumes that the opening tag has been already read and parses
    only the properties, breaking (without consuming) at the closing tag. The
    caller is responsible for reading the opening tag beforehand and consuming
    the closing tag afterwards.
    """
    return typescript_naming.function_name(
        Identifier(f"parse_{cls.name}_from_sequence")
    )


def _generate_parse_text_as_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate parser for text representation of an enumeration literal."""
    enum_name = typescript_naming.enum_name(enumeration.name)
    parse_function_name = typescript_naming.function_name(
        Identifier(f"parse_{enumeration.name}_text")
    )
    from_string_function = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    return Stripped(
        f"""\
function {parse_function_name}(
{I}text: string
): AasCommon.Either<AasTypes.{enum_name}, DeserializationError> {{
{I}const literal = AasStringification.{from_string_function}(text);
{I}if (literal === null) {{
{II}return newDeserializationError<AasTypes.{enum_name}>(
{III}`Unexpected literal of {enum_name}: ${{text}}`
{II});
{I}}}

{I}return new AasCommon.Either<AasTypes.{enum_name}, DeserializationError>(
{II}literal,
{II}null
{I});
}}"""
    )


def _dispatch_parse_element_function_name(
    interface: intermediate.Interface,
) -> Identifier:
    """Generate the name of the function to dispatch-parse an ``interface``."""
    return typescript_naming.function_name(
        Identifier(f"dispatch_parse_{interface.name}_element")
    )


def _parse_atomic_property(
    type_anno: intermediate.AtomicTypeAnnotation,
) -> Tuple[Stripped, Stripped]:
    """
    Generate the statements to parse a property of an atomic (non-list, non-tuple)
    type, and the expression of the parsed value.

    The closing tag of the property is *not* consumed by the generated
    statements; the caller is expected to read and verify it afterwards, and
    assign the returned value expression to the property's variable.

    :param type_anno:
        the property's (optional- and list/tuple-stripped) type annotation --
        a primitive, an enumeration, or a single class/interface
    :return: generated TS statements, and the expression of the parsed value
    """
    if not (
        isinstance(type_anno, intermediate.OurTypeAnnotation)
        and isinstance(
            type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        )
    ):
        parse_function = _parse_function_for_atomic_type(type_anno)
        return (
            Stripped(
                f"""\
const text = parseTextContent(cursor);

const parsedOrError = {parse_function}(text);
if (parsedOrError.error !== null) {{
{I}propertyError = parsedOrError.error;
{I}break;
}}"""
            ),
            Stripped("parsedOrError.mustValue()"),
        )

    our_type = type_anno.our_type

    if (
        isinstance(our_type, intermediate.ConcreteClass)
        and len(our_type.concrete_descendants) == 0
    ):
        # NOTE (mristin):
        # The concrete type is statically known, so ``{parse_sequence_function_name}``
        # already guarantees the correct runtime type -- no dispatch, and no
        # cast-with-null-check, is necessary.
        parse_sequence_function_name = _parse_sequence_function_name_for_concrete_class(
            cls=our_type
        )

        return (
            Stripped(
                f"""\
const classOrError = {parse_sequence_function_name}(cursor);
if (classOrError.error !== null) {{
{I}propertyError = classOrError.error;
{I}break;
}}"""
            ),
            Stripped("classOrError.mustValue()"),
        )

    # NOTE (mristin):
    # We reject an XML element of an unexpected type based on its local name
    # alone -- see {_dispatch_parse_element_function_name.__name__} -- instead
    # of wastefully parsing its full content only to discover the type
    # mismatch afterwards through a runtime cast.
    assert our_type.interface is not None, (
        "Expected an interface on an abstract class, or on a concrete class "
        "with concrete descendants"
    )

    dispatch_function_name = _dispatch_parse_element_function_name(our_type.interface)

    return (
        Stripped(
            f"""\
const instanceOrError = {dispatch_function_name}(cursor);
if (instanceOrError.error !== null) {{
{I}propertyError = instanceOrError.error;
{I}break;
}}"""
        ),
        Stripped("instanceOrError.mustValue()"),
    )


def _parse_list_property(
    type_anno: intermediate.ListTypeAnnotation,
) -> Tuple[Stripped, Stripped]:
    """
    Generate the statements to parse a property of a list type, and the
    expression of the parsed value.

    The closing tag of the property is *not* consumed by the generated
    statements; the caller is expected to read and verify it afterwards, and
    assign the returned value expression to the property's variable.

    :param type_anno: the property's (optional-stripped) list type annotation
    :return: generated TS statements, and the expression of the parsed value
    """
    assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
        f"(mristin) We only handle XML de/serialization of lists "
        f"containing atomic values, but you want to generate the code "
        f"for a list of type {type_anno}. Please contact the "
        f"developers if you need this feature."
    )

    if not (
        isinstance(type_anno.items, intermediate.OurTypeAnnotation)
        and isinstance(
            type_anno.items.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        )
    ):
        parse_item_function = _parse_function_for_atomic_type(type_anno.items)
        v_literal = typescript_common.string_literal("v")

        item_type = typescript_common.generate_type(
            type_anno.items,
            types_module=Identifier("AasTypes"),
        )
        parse_item_expr = Stripped(
            f"(aCursor) => parseNamedVElement(aCursor, {v_literal}, "
            f"{parse_item_function})"
        )
    else:
        items_our_type = type_anno.items.our_type

        if (
            isinstance(items_our_type, intermediate.ConcreteClass)
            and len(items_our_type.concrete_descendants) == 0
        ):
            # NOTE (mristin):
            # The concrete type is statically known, so we can directly check
            # the local name of the element and parse it with the concrete
            # class's own parse function -- no dispatch is necessary.
            expected_name = typescript_naming.class_name(items_our_type.name)
            items_xml_name_literal = typescript_common.string_literal(
                naming.xml_class_name(items_our_type.name)
            )
            parse_sequence_function_name = (
                _parse_sequence_function_name_for_concrete_class(cls=items_our_type)
            )

            parse_item_expr = Stripped(
                f"(aCursor) => parseNamedClassElement(\n"
                f"{I}aCursor,\n"
                f"{I}{items_xml_name_literal},\n"
                f"{I}{parse_sequence_function_name}\n"
                f")"
            )
        else:
            assert items_our_type.interface is not None, (
                "Expected an interface on an abstract class, or on a concrete "
                "class with concrete descendants"
            )

            if isinstance(items_our_type, intermediate.AbstractClass):
                expected_name = typescript_naming.interface_name(items_our_type.name)
            else:
                expected_name = typescript_naming.class_name(items_our_type.name)

            parse_item_expr = _dispatch_parse_element_function_name(
                items_our_type.interface
            )

        item_type = Stripped(f"AasTypes.{expected_name}")

    return (
        Stripped(
            f"""\
const parsedItemsOrError = parseList<{item_type}>(
{I}cursor,
{I}{indent_but_first_line(parse_item_expr, I)}
);
if (parsedItemsOrError.error !== null) {{
{I}propertyError = parsedItemsOrError.error;
{I}break;
}}"""
        ),
        Stripped("parsedItemsOrError.mustValue()"),
    )


@require(lambda cls, prop: id(prop) in cls.property_id_set)
def _generate_parse_case_for_property(
    cls: intermediate.ConcreteClass,
    prop: intermediate.Property,
    var_name: Identifier,
) -> Stripped:
    """
    Generate a switch case to parse a property from XML element content.

    The generated code stores the parsed property value into ``var_name``.
    """
    xml_name_literal = typescript_common.string_literal(prop.xml_name)

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    duplicate_check = Stripped(
        f"""\
if ({var_name} !== null) {{
{I}propertyError = new DeserializationError(
{II}"Property " +
{III}{xml_name_literal} +
{III}" occurred more than once"
{I});
{I}break;
}}"""
    )

    if isinstance(
        type_anno,
        (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
    ):
        statements, value_expr = _parse_atomic_property(type_anno=type_anno)
    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        statements, value_expr = _parse_list_property(type_anno=type_anno)
    else:
        assert_never(type_anno)

    # NOTE (mristin):
    # None of the three functions above consumes the property's own closing
    # tag -- we do it here, uniformly, once the property's content has been
    # successfully parsed.
    parse_body = Stripped(
        f"""\
{statements}

const propertyCloseError = consumeCloseTag(
{I}cursor,
{I}propertyLocalName
);
if (propertyCloseError !== null) {{
{I}propertyError = propertyCloseError;
{I}break;
}}

{var_name} = {value_expr};"""
    )

    return Stripped(
        f"""\
case {xml_name_literal}: {{
{I}{indent_but_first_line(duplicate_check, I)}

{I}{indent_but_first_line(parse_body, I)}
{I}break;
}}"""
    )


def _generate_parse_concrete_class(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate parser for a concrete class from a start XML tag."""
    function_name = _parse_sequence_function_name_for_concrete_class(cls=cls)
    cls_name = typescript_naming.class_name(cls.name)

    var_declarations = []  # type: List[Stripped]
    required_checks = []  # type: List[Stripped]
    parse_cases = []  # type: List[Stripped]

    var_name_by_property = {}  # type: Dict[Identifier, Identifier]

    for prop in cls.properties:
        var_name = typescript_naming.variable_name(Identifier(f"the_{prop.name}"))
        var_name_by_property[prop.name] = var_name

        var_type = typescript_common.generate_type(
            prop.type_annotation,
            types_module=Identifier("AasTypes"),
        )
        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            var_type = Stripped(f"{var_type} | null")

        var_declarations.append(Stripped(f"let {var_name}: {var_type} = null;"))

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            message_literal = typescript_common.string_literal(
                f"The required property {prop.xml_name!r} is missing"
            )
            required_checks.append(
                Stripped(
                    f"""\
if ({var_name} === null) {{
{I}return newDeserializationError<AasTypes.{cls_name}>(
{II}{message_literal}
{I});
}}"""
                )
            )

        parse_cases.append(
            _generate_parse_case_for_property(cls=cls, prop=prop, var_name=var_name)
        )

    parse_cases.append(
        Stripped(
            """\
default: {
  propertyError = new DeserializationError(
    `Unexpected XML property: ${propertyLocalName}`
  );
  break;
}"""
        )
    )

    parse_cases_joined = "\n\n".join(parse_cases)

    if len(cls.constructor.arguments) == 0:
        construct = Stripped(
            f"""\
const instance = new AasTypes.{cls_name}();
return new AasCommon.Either<AasTypes.{cls_name}, DeserializationError>(
{I}instance,
{I}null
);"""
        )
    else:
        writer = io.StringIO()
        writer.write(f"const instance = new AasTypes.{cls_name}(\n")
        for i, arg in enumerate(cls.constructor.arguments):
            var_name = var_name_by_property[arg.name]
            writer.write(f"{I}{var_name}")
            if i < len(cls.constructor.arguments) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")
        writer.write(
            f"""\
);
return new AasCommon.Either<AasTypes.{cls_name}, DeserializationError>(
{I}instance,
{I}null
);"""
        )
        construct = Stripped(writer.getvalue())

    declarations = (
        Stripped("\n".join(var_declarations))
        if len(var_declarations) > 0
        else Stripped("// No properties")
    )
    required_checks_block = (
        Stripped("\n\n".join(required_checks))
        if len(required_checks) > 0
        else Stripped("// No required properties")
    )

    return Stripped(
        f"""\
/**
 * Parse the sequence of properties of an instance
 * of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}}.
 *
 * The opening tag is expected to have been already read by the caller, and
 * the caller is expected to read and verify the corresponding closing tag
 * after this function returns successfully.
 */
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.{cls_name}, DeserializationError> {{
{I}{indent_but_first_line(declarations, I)}

{I}const className = AasTypes.{cls_name}.name;

{I}cursor.skipIgnorable();
{I}// eslint-disable-next-line no-constant-condition
{I}while (true) {{
{II}const nextTagOrError = nextPropertyOpenTag(cursor, className);
{II}if (nextTagOrError === null) {{
{III}break;
{II}}}
{II}if (nextTagOrError instanceof DeserializationError) {{
{III}return new AasCommon.Either<AasTypes.{cls_name}, DeserializationError>(
{IIII}null,
{IIII}nextTagOrError
{III});
{II}}}

{II}const propertyLocalName = localNameOfTag(nextTagOrError.tag);

{II}let propertyError: DeserializationError | null = null;
{II}switch (propertyLocalName) {{
{III}{indent_but_first_line(parse_cases_joined, III)}
{II}}}

{II}if (propertyError !== null) {{
{III}propertyError.path.prepend(new NameSegment(propertyLocalName));
{III}return new AasCommon.Either<AasTypes.{cls_name}, DeserializationError>(
{IIII}null,
{IIII}propertyError
{III});
{II}}}

{II}cursor.skipIgnorable();
{I}}}

{I}{indent_but_first_line(required_checks_block, I)}

{I}{indent_but_first_line(construct, I)}
}}"""
    )


# endregion

# region Serialization


_SERIALIZE_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: Identifier("serializeBooleanText"),
    intermediate.PrimitiveType.INT: Identifier("serializeIntegerText"),
    intermediate.PrimitiveType.FLOAT: Identifier("serializeFloatText"),
    intermediate.PrimitiveType.STR: Identifier("serializeStringText"),
    intermediate.PrimitiveType.BYTEARRAY: Identifier("serializeBase64EncodedBytesText"),
}


def _serialize_function_for_atomic_type(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Identifier:
    """Resolve the name of the serialization function name for an atomic XML text value."""
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return _SERIALIZE_FUNCTION_BY_PRIMITIVE_TYPE[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        assert not isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        )

        if isinstance(our_type, intermediate.Enumeration):
            return typescript_naming.function_name(
                Identifier(f"serialize_{our_type.name}_text")
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return _SERIALIZE_FUNCTION_BY_PRIMITIVE_TYPE[our_type.constrainee]

        else:
            assert_never(our_type)

    else:
        assert_never(type_annotation)


def _generate_serialize_text_as_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate serializer for text representation of an enumeration literal."""
    enum_name = typescript_naming.enum_name(enumeration.name)
    serialize_function_name = typescript_naming.function_name(
        Identifier(f"serialize_{enumeration.name}_text")
    )
    to_string_function = typescript_naming.function_name(
        Identifier(f"must_{enumeration.name}_to_string")
    )

    return Stripped(
        f"""\
function {serialize_function_name}(
{I}value: AasTypes.{enum_name}
): string {{
{I}return escapeXmlText(AasStringification.{to_string_function}(value));
}}"""
    )


def _generate_serialize_text_for_primitive_type(
    primitive_type: intermediate.PrimitiveType,
) -> Stripped:
    """Generate serializer for a primitive XML text representation."""
    if primitive_type is intermediate.PrimitiveType.BOOL:
        return Stripped(
            f"""\
function serializeBooleanText(value: boolean): string {{
{I}return value ? "true" : "false";
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.INT:
        return Stripped(
            f"""\
function serializeIntegerText(value: number): string {{
{I}if (!Number.isInteger(value)) {{
{II}throw new Error(`Expected an integer, but got: ${{value}}`);
{I}}}

{I}return `${{value}}`;
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        return Stripped(
            f"""\
function serializeFloatText(value: number): string {{
{I}if (Number.isNaN(value)) {{
{II}return "NaN";
{I}}}
{I}if (value === Infinity) {{
{II}return "INF";
{I}}}
{I}if (value === -Infinity) {{
{II}return "-INF";
{I}}}

{I}return `${{value}}`;
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.STR:
        return Stripped(
            f"""\
function serializeStringText(value: string): string {{
{I}return escapeXmlText(value);
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Stripped(
            f"""\
function serializeBase64EncodedBytesText(value: Uint8Array): string {{
{I}return escapeXmlText(AasCommon.base64Encode(value));
}}"""
        )

    else:
        assert_never(primitive_type)


def _generate_serialize_atomic_element(
    element_name_literal: Stripped,
    serialize_function: Identifier,
    access_expr: Stripped,
) -> Stripped:
    """
    Generate the statement to write an atomic value wrapped in an element.

    This is used both for a single atomic property and for an atomic item of
    a list or a tuple, where ``element_name_literal`` is either the property's
    own XML name or a fixed item element name (*e.g.*, ``"v"`` or ``"v1"``).
    """
    return Stripped(
        f"writeVElement(parts, {element_name_literal}, "
        f"{serialize_function}({access_expr}));"
    )


def _generate_serialize_class_element(access_expr: Stripped) -> Stripped:
    """
    Generate the statement to write a class instance using its own element tag.

    This is used whenever the runtime type of the value is not statically known
    to be a concrete class without descendants (*i.e.*, for polymorphic
    properties, and for every item of a list or a tuple of class instances).
    """
    return Stripped(f"writeClassElement(parts, this.transform({access_expr}));")


def _generate_serialize_block_for_property(
    prop: intermediate.Property,
) -> Stripped:
    """Generate serialization statements for a property."""
    xml_name_literal = typescript_common.string_literal(prop.xml_name)
    prop_name = typescript_naming.property_name(prop.name)
    access_expr = Stripped(f"that.{prop_name}")

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    if isinstance(
        type_anno,
        (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
    ):
        if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            our_type = type_anno.our_type
            if (
                isinstance(our_type, intermediate.ConcreteClass)
                and len(our_type.concrete_descendants) == 0
            ):
                serialized_var = typescript_naming.variable_name(
                    Identifier(f"serialized_{prop.name}")
                )
                body = Stripped(
                    f"""\
const {serialized_var} = this.transform({access_expr});
parts.push(openTag({xml_name_literal}));
parts.push({serialized_var}.innerXml);
parts.push(closeTag({xml_name_literal}));"""
                )
            else:
                body = Stripped(
                    f"""\
parts.push(openTag({xml_name_literal}));
{indent_but_first_line(
    _generate_serialize_class_element(access_expr=access_expr),
    I,
)}
parts.push(closeTag({xml_name_literal}));"""
                )
        else:
            serialize_function = _serialize_function_for_atomic_type(type_anno)
            body = _generate_serialize_atomic_element(
                element_name_literal=xml_name_literal,
                serialize_function=serialize_function,
                access_expr=access_expr,
            )

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        if isinstance(
            type_anno.items,
            (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
        ) and not (
            isinstance(type_anno.items, intermediate.OurTypeAnnotation)
            and isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            )
        ):
            serialize_item_function = _serialize_function_for_atomic_type(
                type_anno.items
            )
            item_var = typescript_naming.variable_name(Identifier(f"item_{prop.name}"))
            v_literal = typescript_common.string_literal("v")

            body = Stripped(
                f"""\
parts.push(openTag({xml_name_literal}));
for (const {item_var} of {access_expr}) {{
{I}{indent_but_first_line(
    _generate_serialize_atomic_element(
        element_name_literal=v_literal,
        serialize_function=serialize_item_function,
        access_expr=Stripped(item_var),
    ),
    I,
)}
}}
parts.push(closeTag({xml_name_literal}));"""
            )

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.items.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            item_var = typescript_naming.variable_name(Identifier(f"item_{prop.name}"))

            body = Stripped(
                f"""\
parts.push(openTag({xml_name_literal}));
for (const {item_var} of {access_expr}) {{
{I}{indent_but_first_line(
    _generate_serialize_class_element(access_expr=Stripped(item_var)),
    I,
)}
}}
parts.push(closeTag({xml_name_literal}));"""
            )

        else:
            # NOTE (mristin):
            # This is a limitation of our code generation, not of the input
            # instances, so we fail immediately at generation time instead of
            # emitting code which would only fail at runtime -- see how the
            # other languages (*e.g.*, C# and C++) handle this same case.
            raise NotImplementedError(
                f"(mristin) We only handle XML serialization of lists "
                f"containing atomic values, but you want to generate the code "
                f"for a list of type {type_anno}. Please contact the "
                f"developers if you need this feature."
            )

    else:
        assert_never(type_anno)

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return Stripped(
            f"""\
if ({access_expr} !== null) {{
{I}{indent_but_first_line(body, I)}
}}"""
        )

    return body


def _generate_transform_of_concrete_class(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate ``transformX`` to serialize a concrete class to XML parts."""
    method_name = typescript_naming.method_name(Identifier(f"transform_{cls.name}"))
    cls_name = typescript_naming.class_name(cls.name)
    local_name_literal = typescript_common.string_literal(
        naming.xml_class_name(cls.name)
    )

    blocks = [Stripped("const parts = new Array<string>();")]  # type: List[Stripped]

    for prop in cls.properties:
        blocks.append(_generate_serialize_block_for_property(prop=prop))

    blocks.append(
        Stripped(
            f"""\
return {{
{I}localName: {local_name_literal},
{I}innerXml: parts.join("")
}};"""
        )
    )

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Serialize `that` to an XML element representation.
 *
 * @param that - instance to be serialized
 * @returns serialized XML element representation
 */
{method_name}(
{I}that: AasTypes.{cls_name}
): SerializedElement {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(indent_but_first_line(block, I))

    writer.write("\n}")
    return Stripped(writer.getvalue())


def _generate_serializer(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the serializer transformer over all concrete classes."""
    methods = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        methods.append(_generate_transform_of_concrete_class(cls=cls))

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Serialize an AAS instance to XML parts.
 */
class Serializer extends AasTypes.AbstractTransformer<SerializedElement> {
"""
    )

    for method in methods:
        writer.write("\n\n")
        writer.write(indent_but_first_line(method, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_dispatch_parse_interface_element(
    interface: intermediate.Interface,
) -> Stripped:
    """
    Generate a function to dispatch-parse an ``interface`` from an XML element.

    Unlike :py:func:`_generate_root_dispatch_map`, which has to account for
    every concrete class in the meta-model, this dispatches only over the
    concrete classes which actually implement ``interface``. This lets us
    reject an XML element of an unexpected type based on its local name alone,
    without wastefully parsing its full (possibly deeply nested) content only
    to discover the type mismatch afterwards.
    """
    if isinstance(interface.base, intermediate.AbstractClass):
        expected_name = typescript_naming.interface_name(interface.name)
    else:
        expected_name = typescript_naming.class_name(interface.name)

    function_name = _dispatch_parse_element_function_name(interface)

    case_writer = io.StringIO()
    for implementer in interface.implementers:
        implementer_local_name_literal = typescript_common.string_literal(
            naming.xml_class_name(implementer.name)
        )
        parse_function_name = _parse_sequence_function_name_for_concrete_class(
            cls=implementer
        )

        case_writer.write(
            f"""\
{II}case {implementer_local_name_literal}:
{III}instanceOrError = {parse_function_name}(cursor);
{III}break;
"""
        )

    return Stripped(
        f"""\
/**
 * Dispatch-parse an instance
 * of {{@link {typescript_common.TYPES_MODULE}!{expected_name}}} from the next
 * XML element in `cursor`, based on the element's local name.
 *
 * @param cursor - to read from
 * @returns the parsed instance, or an error
 */
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.{expected_name}, DeserializationError> {{
{I}const startTagOrError = readNextOpenTag(cursor);
{I}if (startTagOrError.error !== null) {{
{II}return new AasCommon.Either<AasTypes.{expected_name}, DeserializationError>(
{III}null,
{III}startTagOrError.error
{II});
{I}}}
{I}const startTag = startTagOrError.mustValue();

{I}const localName = localNameOfTag(startTag.tag);
{I}cursor.advance();

{I}let instanceOrError: AasCommon.Either<AasTypes.{expected_name}, DeserializationError>;
{I}switch (localName) {{
{case_writer.getvalue().rstrip()}
{II}default:
{III}return newDeserializationError<AasTypes.{expected_name}>(
{IIII}`Expected an instance of {expected_name}, but got: ${{localName}}`
{III});
{I}}}

{I}if (instanceOrError.error !== null) {{
{II}return instanceOrError;
{I}}}

{I}const closeError = consumeCloseTag(cursor, localName);
{I}if (closeError !== null) {{
{II}return new AasCommon.Either<AasTypes.{expected_name}, DeserializationError>(
{III}null,
{III}closeError
{II});
{I}}}

{I}return instanceOrError;
}}"""
    )


def _generate_from_xml_string_for_interface(
    interface: intermediate.Interface,
) -> Stripped:
    """
    Generate a public function to parse a whole XML string as an ``interface``.

    This gives the callers a way to de-serialize an instance of a known
    interface directly, without going through ``fromXmlString``.
    """
    if isinstance(interface.base, intermediate.AbstractClass):
        expected_name = typescript_naming.interface_name(interface.name)
    else:
        expected_name = typescript_naming.class_name(interface.name)

    function_name = typescript_naming.function_name(
        Identifier(f"{interface.name}_from_xml_string")
    )
    dispatch_function_name = _dispatch_parse_element_function_name(interface)

    return Stripped(
        f"""\
/**
 * Parse an XML string as an instance
 * of {{@link {typescript_common.TYPES_MODULE}!{expected_name}}}.
 *
 * @param xml - XML string to parse
 * @returns parsed instance, or an error
 */
export function {function_name}(
{I}xml: string
): AasCommon.Either<AasTypes.{expected_name}, DeserializationError> {{
{I}if (xml.length === 0) {{
{II}return newDeserializationError<AasTypes.{expected_name}>(
{III}"Expected an XML document, but got an empty string"
{II});
{I}}}

{I}const tokensOrError = tokenizeXml(xml);
{I}if (tokensOrError.error !== null) {{
{II}return new AasCommon.Either<AasTypes.{expected_name}, DeserializationError>(
{III}null,
{III}tokensOrError.error
{II});
{I}}}

{I}const cursor = new XmlCursor(tokensOrError.mustValue());

{I}const instanceOrError = {dispatch_function_name}(cursor);
{I}if (instanceOrError.error !== null) {{
{II}return instanceOrError;
{I}}}

{I}cursor.skipIgnorable();
{I}if (cursor.current() !== null) {{
{II}return newDeserializationError<AasTypes.{expected_name}>(
{III}"Expected no tokens after the root XML element, but got token kind: " +
{IIII}currentTokenKind(cursor)
{II});
{I}}}

{I}return instanceOrError;
}}"""
    )


def _generate_root_dispatch_map(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the dispatch map from root XML local names to parse functions."""
    writer = io.StringIO()
    writer.write(
        f"""\
const ROOT_DISPATCH_BY_LOCAL_NAME =
{I}new Map<
{II}string,
{II}(cursor: XmlCursor) => AasCommon.Either<AasTypes.Class, DeserializationError>
{I}>([
"""
    )

    for i, cls in enumerate(symbol_table.concrete_classes):
        local_name_literal = typescript_common.string_literal(
            naming.xml_class_name(cls.name)
        )
        parse_function_name = _parse_sequence_function_name_for_concrete_class(cls=cls)

        writer.write(
            f"""\
{II}[
{III}{local_name_literal},
{III}{parse_function_name}
{II}]"""
        )

        if i < len(symbol_table.concrete_classes) - 1:
            writer.write(",\n")
        else:
            writer.write("\n")

    writer.write(
        f"""\
{I}]);"""
    )

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
    """Generate code for XML de/serialization."""
    del spec_impls

    namespace_literal = typescript_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    blocks = [
        Stripped(
            """\
/**
 * Provide de/serialization of AAS classes to/from XML.
 *
 * The implementation is incremental and follows a SAX-style parsing approach.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasCommon from "./common";
import * as AasTypes from "./types";
import * as AasStringification from "./stringification";

import {
  CdataToken,
  CloseTagToken,
  CommentToken,
  EndToken,
  OpenTagToken,
  TextToken,
  XmlAnyToken,
  XmlSaxParser
} from "xmlsax-typescript";"""
        ),
        Stripped(
            f"""\
const NAMESPACE = {namespace_literal};"""
        ),
        Stripped(
            f"""\
/**
 * Represent a property name segment in an XML path.
 */
export class NameSegment {{
{I}readonly name: string;

{I}constructor(name: string) {{
{II}this.name = name;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent an index segment in an XML path.
 */
export class IndexSegment {{
{I}readonly index: number;

{I}constructor(index: number) {{
{II}this.index = index;
{I}}}
}}"""
        ),
        Stripped(
            """\
export type Segment = NameSegment | IndexSegment;"""
        ),
        Stripped(
            f"""\
/**
 * Represent a relative path to the erroneous XML value.
 */
export class Path {{
{I}private readonly _segments = new Array<Segment>();

{I}segments(): Array<Segment> {{
{II}return this._segments;
{I}}}

{I}prepend(segment: Segment): void {{
{II}this._segments.unshift(segment);
{I}}}

{I}toString(): string {{
{II}if (this._segments.length === 0) {{
{III}return "";
{II}}}

{II}const parts = new Array<string>();
{II}for (const segment of this._segments) {{
{III}if (segment instanceof NameSegment) {{
{IIII}if (parts.length === 0) {{
{IIIII}parts.push(segment.name);
{IIII}}} else {{
{IIIII}parts.push(`.${{segment.name}}`);
{IIII}}}
{III}}} else if (segment instanceof IndexSegment) {{
{IIII}parts.push(`[${{segment.index}}]`);
{III}}}
{II}}}

{II}return parts.join("");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Signal that XML de-serialization could not be performed.
 */
export class DeserializationError {{
{I}readonly message: string;
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
 * Signal that XML serialization could not be performed.
 */
export class SerializationError {{
{I}readonly message: string;
{I}readonly path: Path;

{I}constructor(message: string, path: Path | null = null) {{
{II}this.message = message;
{II}this.path = path ?? new Path();
{I}}}
}}"""
        ),
        Stripped(
            f"""\
function newDeserializationError<T>(
{I}message: string
): AasCommon.Either<T, DeserializationError> {{
{I}return new AasCommon.Either<T, DeserializationError>(
{II}null,
{II}new DeserializationError(message)
{I});
}}

function currentTokenKind(cursor: XmlCursor): string {{
{I}const token = cursor.current();
{I}if (token === null) {{
{II}return "end-of-token-stream";
{I}}}

{I}return token.kind;
}}

function localNameOfTag(tag: unknown): string {{
{I}const aTag = tag as {{
{II}name?: unknown,
{II}local?: unknown,
{II}localName?: unknown
{I}}};

{I}if (typeof aTag.local === "string") {{
{II}return aTag.local;
{I}}}
{I}if (typeof aTag.localName === "string") {{
{II}return aTag.localName;
{I}}}
{I}if (typeof aTag.name === "string") {{
{II}const colonIndex = aTag.name.indexOf(":");
{II}if (colonIndex >= 0) {{
{III}return aTag.name.substring(colonIndex + 1);
{II}}}
{II}return aTag.name;
{I}}}

{I}return "";
}}

function namespaceOfTag(tag: unknown): string {{
{I}const aTag = tag as {{ uri?: unknown, namespaceURI?: unknown }};
{I}if (typeof aTag.uri === "string") {{
{II}return aTag.uri;
{I}}}
{I}if (typeof aTag.namespaceURI === "string") {{
{II}return aTag.namespaceURI;
{I}}}
{I}return "";
}}

function checkExpectedOpenTagNamespace(
{I}openTag: OpenTagToken
): DeserializationError | null {{
{I}const namespace = namespaceOfTag(openTag.tag);
{I}if (namespace !== NAMESPACE) {{
{II}return new DeserializationError(
{III}"Expected XML namespace " +
{IIII}`'${{NAMESPACE}}', but got '${{namespace}}'`
{II});
{I}}}

{I}return null;
}}

/**
 * Read the next property's opening tag while parsing the sequence of
 * properties of `className`, advancing `cursor` past it.
 *
 * @param cursor - to be read from
 * @param className - name of the class being parsed, for error reporting
 * @returns
 * the next property's opening tag, or `null` if the closing tag of
 * `className` was reached instead, or an error
 */
function nextPropertyOpenTag(
{I}cursor: XmlCursor,
{I}className: string
): OpenTagToken | DeserializationError | null {{
{I}const token = cursor.current();
{I}if (token === null) {{
{II}return new DeserializationError(
{III}`Unexpected end of token stream while parsing ${{className}}`
{II});
{I}}}

{I}if (token instanceof CloseTagToken) {{
{II}return null;
{I}}}

{I}if (!(token instanceof OpenTagToken)) {{
{II}return new DeserializationError(
{III}"Expected an XML property start element or the closing element of " +
{III}`${{className}}, but got token kind: ${{token.kind}}`
{II});
{I}}}

{I}const namespaceError = checkExpectedOpenTagNamespace(token);
{I}if (namespaceError !== null) {{
{II}return namespaceError;
{I}}}

{I}cursor.advance();
{I}return token;
}}

function checkExpectedCloseTag(
{I}closeTag: CloseTagToken,
{I}expectedLocalName: string
): DeserializationError | null {{
{I}const namespace = namespaceOfTag(closeTag.tag);
{I}if (namespace !== NAMESPACE) {{
{II}return new DeserializationError(
{III}"Expected XML namespace " +
{IIII}`'${{NAMESPACE}}', but got '${{namespace}}'`
{II});
{I}}}

{I}const observedLocalName = localNameOfTag(closeTag.tag);
{I}if (observedLocalName !== expectedLocalName) {{
{II}return new DeserializationError(
{III}`Expected closing XML element '${{expectedLocalName}}', ` +
{III}`but got '${{observedLocalName}}'`
{II});
{I}}}

{I}return null;
}}

/**
 * Read the next token from `cursor`, expecting it to be the closing XML
 * element named `expectedLocalName`, and consume it.
 */
function consumeCloseTag(
{I}cursor: XmlCursor,
{I}expectedLocalName: string
): DeserializationError | null {{
{I}const closeTag = cursor.current();
{I}if (!(closeTag instanceof CloseTagToken)) {{
{II}return new DeserializationError(
{III}`Expected a closing element '${{expectedLocalName}}', ` +
{III}`but got token kind: ${{currentTokenKind(cursor)}}`
{II});
{I}}}

{I}const closeError = checkExpectedCloseTag(closeTag, expectedLocalName);
{I}if (closeError !== null) {{
{II}return closeError;
{I}}}

{I}cursor.advance();
{I}return null;
}}

/**
 * Read the next non-ignorable token from `cursor`, expecting it to be
 * an opening XML element in the expected namespace.
 *
 * This is shared by the parsing of a single list item, a single tuple
 * item, and the dispatch-parsing of an interface.
 *
 * @param cursor - to read from
 * @returns the opening tag, or an error
 */
function readNextOpenTag(
{I}cursor: XmlCursor
): AasCommon.Either<OpenTagToken, DeserializationError> {{
{I}cursor.skipIgnorable();
{I}const token = cursor.current();
{I}if (token === null) {{
{II}return newDeserializationError<OpenTagToken>(
{III}"Expected an XML element, but got end of token stream"
{II});
{I}}}
{I}if (!(token instanceof OpenTagToken)) {{
{II}return newDeserializationError<OpenTagToken>(
{III}`Expected an XML element, but got token kind: ${{token.kind}}`
{II});
{I}}}

{I}const namespaceError = checkExpectedOpenTagNamespace(token);
{I}if (namespaceError !== null) {{
{II}return new AasCommon.Either<OpenTagToken, DeserializationError>(
{III}null,
{III}namespaceError
{II});
{I}}}

{I}return new AasCommon.Either<OpenTagToken, DeserializationError>(token, null);
}}

/**
 * Read the next XML element from `cursor`, expecting it to be named
 * `expectedLocalName`, parse its text content with `parseTextFn` and
 * consume the matching closing element.
 *
 * This is shared by the parsing of a single list item (with a fixed
 * local name, *e.g.*, `"v"`) and the parsing of a single tuple item (with
 * a positional local name, *e.g.*, `"v1"`).
 *
 * @param cursor - to read from
 * @param expectedLocalName - the expected local name of the element
 * @param parseTextFn - parses the text content of the element
 * @returns parsed value, or an error
 * @typeParam T - type of the parsed value
 */
function parseNamedVElement<T>(
{I}cursor: XmlCursor,
{I}expectedLocalName: string,
{I}parseTextFn: (text: string) => AasCommon.Either<T, DeserializationError>
): AasCommon.Either<T, DeserializationError> {{
{I}const startTagOrError = readNextOpenTag(cursor);
{I}if (startTagOrError.error !== null) {{
{II}return new AasCommon.Either<T, DeserializationError>(
{III}null,
{III}startTagOrError.error
{II});
{I}}}
{I}const startTag = startTagOrError.mustValue();

{I}const observedLocalName = localNameOfTag(startTag.tag);
{I}if (observedLocalName !== expectedLocalName) {{
{II}return newDeserializationError<T>(
{III}`Expected the element '${{expectedLocalName}}', ` +
{IIII}`but got '${{observedLocalName}}'`
{II});
{I}}}

{I}cursor.advance();

{I}const text = parseTextContent(cursor);

{I}const closeError = consumeCloseTag(cursor, expectedLocalName);
{I}if (closeError !== null) {{
{II}return new AasCommon.Either<T, DeserializationError>(null, closeError);
{I}}}

{I}return parseTextFn(text);
}}

/**
 * Read the next XML element from `cursor`, expecting it to be named
 * `expectedLocalName`, parse its content with `parseFn` and consume the
 * matching closing element.
 *
 * This is used for a list or a tuple item whose concrete type is statically
 * known (*i.e.*, it has no further descendants), so we can reject
 * an unexpected element based on its local name alone, without wastefully
 * parsing its full (possibly deeply nested) content.
 *
 * @param cursor - to read from
 * @param expectedLocalName - the expected local name of the element
 * @param parseFn - parses the sequence of properties of the class instance
 * @returns the parsed instance, or an error
 * @typeParam T - type of the parsed instance
 */
function parseNamedClassElement<T>(
{I}cursor: XmlCursor,
{I}expectedLocalName: string,
{I}parseFn: (cursor: XmlCursor) => AasCommon.Either<T, DeserializationError>
): AasCommon.Either<T, DeserializationError> {{
{I}const startTagOrError = readNextOpenTag(cursor);
{I}if (startTagOrError.error !== null) {{
{II}return new AasCommon.Either<T, DeserializationError>(
{III}null,
{III}startTagOrError.error
{II});
{I}}}
{I}const startTag = startTagOrError.mustValue();

{I}const observedLocalName = localNameOfTag(startTag.tag);
{I}if (observedLocalName !== expectedLocalName) {{
{II}return newDeserializationError<T>(
{III}`Expected the element '${{expectedLocalName}}', ` +
{IIII}`but got '${{observedLocalName}}'`
{II});
{I}}}

{I}cursor.advance();

{I}const instanceOrError = parseFn(cursor);
{I}if (instanceOrError.error !== null) {{
{II}return instanceOrError;
{I}}}

{I}const closeError = consumeCloseTag(cursor, expectedLocalName);
{I}if (closeError !== null) {{
{II}return new AasCommon.Either<T, DeserializationError>(null, closeError);
{I}}}

{I}return instanceOrError;
}}

/**
 * Parse a sequence of list items from `cursor`, stopping (without consuming)
 * at the first closing element.
 *
 * The caller is expected to read and verify the property's own closing
 * element afterwards.
 *
 * @param cursor - to read from
 * @param parseItem - parses a single list item
 * @returns the parsed items, or an error
 * @typeParam T - type of a single list item
 */
function parseList<T>(
{I}cursor: XmlCursor,
{I}parseItem: (cursor: XmlCursor) => AasCommon.Either<T, DeserializationError>
): AasCommon.Either<Array<T>, DeserializationError> {{
{I}const items = new Array<T>();
{I}let itemIndex = 0;

{I}cursor.skipIgnorable();
{I}// eslint-disable-next-line no-constant-condition
{I}while (true) {{
{II}const maybeClose = cursor.current();
{II}if (maybeClose === null) {{
{III}return newDeserializationError<Array<T>>(
{IIII}"Expected an XML element corresponding to a list item " +
{IIIII}"or property closing element, but got end of token stream"
{III});
{II}}}

{II}if (maybeClose instanceof CloseTagToken) {{
{III}break;
{II}}}

{II}const itemOrError = parseItem(cursor);
{II}if (itemOrError.error !== null) {{
{III}itemOrError.error.path.prepend(new IndexSegment(itemIndex));
{III}return new AasCommon.Either<Array<T>, DeserializationError>(
{IIII}null,
{IIII}itemOrError.error
{III});
{II}}}

{II}items.push(itemOrError.mustValue());
{II}itemIndex++;
{II}cursor.skipIgnorable();
{I}}}

{I}return new AasCommon.Either<Array<T>, DeserializationError>(items, null);
}}

/**
 * Cursor over parsed XML SAX tokens.
 */
class XmlCursor {{
{I}private readonly _tokens: Array<XmlAnyToken>;
{I}private _index = 0;

{I}constructor(tokens: Array<XmlAnyToken>) {{
{II}this._tokens = tokens;
{I}}}

{I}current(): XmlAnyToken | null {{
{II}if (this._index >= this._tokens.length) {{
{III}return null;
{II}}}
{II}return this._tokens[this._index];
{I}}}

{I}advance(): void {{
{II}if (this._index < this._tokens.length) {{
{III}this._index++;
{II}}}
{I}}}

{I}skipIgnorable(): void {{
{II}// eslint-disable-next-line no-constant-condition
{II}while (true) {{
{III}const token = this.current();
{III}if (token === null) {{
{IIII}break;
{III}}}

{III}if (token instanceof CommentToken) {{
{IIII}this.advance();
{IIII}continue;
{III}}}

{III}if (token instanceof TextToken || token instanceof CdataToken) {{
{IIII}if (token.text.trim().length === 0) {{
{IIIII}this.advance();
{IIIII}continue;
{IIII}}}
{III}}}

{III}break;
{II}}}
{I}}}
}}

function tokenizeXml(
{I}xml: string
): AasCommon.Either<Array<XmlAnyToken>, DeserializationError> {{
{I}const parser = new XmlSaxParser({{ allowDoctype: false, xmlns: true }});
{I}const tokens = new Array<XmlAnyToken>();

{I}try {{
{II}for (const token of parser.feed(xml)) {{
{III}tokens.push(token);
{II}}}
{II}for (const token of parser.close()) {{
{III}if (!(token instanceof EndToken)) {{
{IIII}tokens.push(token);
{III}}}
{II}}}
{I}}} catch (error) {{
{II}return newDeserializationError<Array<XmlAnyToken>>(
{III}`Failed to parse XML: ${{error}}`
{II});
{I}}}

{I}return new AasCommon.Either<Array<XmlAnyToken>, DeserializationError>(
{II}tokens,
{II}null
{I});
}}

function readRequiredRootOpenTag(
{I}cursor: XmlCursor
): AasCommon.Either<OpenTagToken, DeserializationError> {{
{I}cursor.skipIgnorable();

{I}const token = cursor.current();
{I}if (token === null) {{
{II}return newDeserializationError<OpenTagToken>(
{III}"Expected a root XML element, but got an empty token stream"
{II});
{I}}}

{I}if (!(token instanceof OpenTagToken)) {{
{II}return newDeserializationError<OpenTagToken>(
{III}`Expected a root XML start element, but got token kind: ${{token.kind}}`
{II});
{I}}}

{I}const namespaceError = checkExpectedOpenTagNamespace(token);
{I}if (namespaceError !== null) {{
{II}return new AasCommon.Either<OpenTagToken, DeserializationError>(
{III}null,
{III}namespaceError
{II});
{I}}}

{I}cursor.advance();

{I}return new AasCommon.Either<OpenTagToken, DeserializationError>(
{II}token,
{II}null
{I});
}}

/**
 * Consume the text (or CDATA) content at `cursor`, if any.
 *
 * The caller is responsible for reading and verifying the closing element
 * afterwards.
 */
function parseTextContent(cursor: XmlCursor): string {{
{I}cursor.skipIgnorable();

{I}let text = "";
{I}const maybeText = cursor.current();
{I}if (maybeText instanceof TextToken || maybeText instanceof CdataToken) {{
{II}text = maybeText.text;
{II}cursor.advance();
{II}cursor.skipIgnorable();
{I}}}

{I}return text;
}}"""
        ),
    ]  # type: List[Stripped]

    for primitive_type in intermediate.PrimitiveType:
        blocks.append(_generate_parse_text_for_primitive_type(primitive_type))

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_parse_text_as_enumeration(enumeration))

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_serialize_text_as_enumeration(enumeration))

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_parse_concrete_class(cls=concrete_cls))

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.AbstractClass):
            blocks.append(
                _generate_dispatch_parse_interface_element(interface=cls.interface)
            )
            blocks.append(
                _generate_from_xml_string_for_interface(interface=cls.interface)
            )
        elif isinstance(cls, intermediate.ConcreteClass):
            if len(cls.concrete_descendants) > 0:
                assert (
                    cls.interface is not None
                ), "Expected an interface on a class with concrete descendants"

                blocks.append(
                    _generate_dispatch_parse_interface_element(interface=cls.interface)
                )
                blocks.append(
                    _generate_from_xml_string_for_interface(interface=cls.interface)
                )
        else:
            assert_never(cls)

    blocks.extend(
        [
            _generate_root_dispatch_map(symbol_table=symbol_table),
            Stripped(
                f"""\
/**
 * Parse an XML string as an AAS instance.
 *
 * @param xml - XML string to parse
 * @returns parsed AAS instance or an error
 */
export function fromXmlString(
{I}xml: string
): AasCommon.Either<AasTypes.Class, DeserializationError> {{
{I}if (xml.length === 0) {{
{II}return newDeserializationError<AasTypes.Class>(
{III}"Expected an XML document, but got an empty string"
{II});
{I}}}

{I}const tokensOrError = tokenizeXml(xml);
{I}if (tokensOrError.error !== null) {{
{II}return new AasCommon.Either<AasTypes.Class, DeserializationError>(
{III}null,
{III}tokensOrError.error
{II});
{I}}}

{I}const cursor = new XmlCursor(tokensOrError.mustValue());

{I}const rootOpenTagOrError = readRequiredRootOpenTag(cursor);
{I}if (rootOpenTagOrError.error !== null) {{
{II}return new AasCommon.Either<AasTypes.Class, DeserializationError>(
{III}null,
{III}rootOpenTagOrError.error
{II});
{I}}}

{I}const rootOpenTag = rootOpenTagOrError.mustValue();
{I}const rootLocalName = localNameOfTag(rootOpenTag.tag);

{I}const dispatch = ROOT_DISPATCH_BY_LOCAL_NAME.get(rootLocalName);
{I}if (dispatch === undefined) {{
{II}return newDeserializationError<AasTypes.Class>(
{III}`Unexpected root XML element: ${{rootLocalName}}`
{II});
{I}}}

{I}const instanceOrError = dispatch(cursor);
{I}if (instanceOrError.error !== null) {{
{II}return instanceOrError;
{I}}}

{I}const closeError = consumeCloseTag(cursor, rootLocalName);
{I}if (closeError !== null) {{
{II}return new AasCommon.Either<AasTypes.Class, DeserializationError>(
{III}null,
{III}closeError
{II});
{I}}}

{I}cursor.skipIgnorable();
{I}if (cursor.current() !== null) {{
{II}return newDeserializationError<AasTypes.Class>(
{III}"Expected no tokens after the root XML element, but got token kind: " +
{IIII}currentTokenKind(cursor)
{II});
{I}}}

{I}return instanceOrError;
}}"""
            ),
            Stripped(
                f"""\
type SerializedElement = {{
{I}localName: string;
{I}innerXml: string;
}};

function openTag(localName: string, withNamespace = false): string {{
{I}if (withNamespace) {{
{II}return `<${{localName}} xmlns="${{NAMESPACE}}">`;
{I}}}

{I}return `<${{localName}}>`;
}}

function closeTag(localName: string): string {{
{I}return `</${{localName}}>`;
}}

/**
 * Push `content` wrapped in its own `localName` element onto `parts`.
 *
 * We push the opening tag, the content and the closing tag as three separate
 * entries instead of pre-concatenating them, so that ``parts.join("")`` at
 * the top level copies the (possibly large, deeply nested) `content` exactly
 * once.
 */
function writeVElement(
{I}parts: Array<string>,
{I}localName: string,
{I}content: string
): void {{
{I}parts.push(openTag(localName));
{I}parts.push(content);
{I}parts.push(closeTag(localName));
}}

/**
 * Push a class instance already serialized to XML parts onto `parts`, wrapped
 * in its own element as given by {{@link SerializedElement.localName}}.
 */
function writeClassElement(
{I}parts: Array<string>,
{I}serialized: SerializedElement
): void {{
{I}parts.push(openTag(serialized.localName));
{I}parts.push(serialized.innerXml);
{I}parts.push(closeTag(serialized.localName));
}}

function escapeXmlText(text: string): string {{
{I}return text
{II}.replace(/&/g, "&amp;")
{II}.replace(/</g, "&lt;")
{II}.replace(/>/g, "&gt;")
{II}.replace(/\"/g, "&quot;")
{II}.replace(/'/g, "&apos;");
}}"""
            ),
        ]
    )

    for primitive_type in intermediate.PrimitiveType:
        blocks.append(_generate_serialize_text_for_primitive_type(primitive_type))

    blocks.extend(
        [
            _generate_serializer(symbol_table=symbol_table),
            Stripped("const SERIALIZER = new Serializer();"),
            Stripped(
                f"""\
/**
 * Serialize an AAS instance as an XML string.
 *
 * @param that - AAS instance to serialize
 * @returns serialized XML string
 */
export function toXmlString(that: AasTypes.Class): string {{
{I}const serialized = SERIALIZER.transform(that);
{I}const parts = new Array<string>();
{I}parts.push(openTag(serialized.localName, true));
{I}parts.push(serialized.innerXml);
{I}parts.push(closeTag(serialized.localName));
{I}return parts.join("");
}}"""
            ),
            typescript_common.WARNING,
        ]
    )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert __doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
