"""Generate code for XML de/serialization."""

import io
import re
from typing import Tuple, Optional, List, Dict, Sequence

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
)


# region De-serialization


def _generate_parse_content_for_primitive_type(
    primitive_type: intermediate.PrimitiveType,
) -> Stripped:
    """
    Generate the parser of the content of an element holding a primitive value.

    The text is read and validated in the very same function. We deliberately do not
    split the two: the element of a primitive is by far the commonest thing to parse,
    and a text parser of its own would be called from nowhere else -- a list item and
    a tuple item go through ``parseNamedElement``, which is given this parser.
    """
    function_name = Identifier(
        f"parse_{typescript_common.MONIKER_BY_PRIMITIVE_TYPE[primitive_type]}"
    )

    if primitive_type is intermediate.PrimitiveType.BOOL:
        return Stripped(
            f"""\
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<boolean, DeserializationError> {{
{I}const text = collapseWhitespace(parseTextContent(cursor));

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
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<number, DeserializationError> {{
{I}const text = collapseWhitespace(parseTextContent(cursor));

{I}if (!/^[+-]?\\d+$/.test(text)) {{
{II}return newDeserializationError<number>(
{III}`Expected integer text, but got: ${{text}}`
{II});
{I}}}

{I}const value = Number(text);

{I}// NOTE (mristin):
{I}// An integer is a ``number`` in TypeScript, and a ``number`` holds only
{I}// the integers up to 2^53 - 1 exactly. Beyond that ``Number`` rounds
{I}// silently -- 9007199254740993 comes back as 9007199254740992, and
{I}// 9223372036854775807 as 9223372036854776000, which is a perfectly
{I}// well-formed but *different* xs:long. We refuse instead of corrupting.
{I}//
{I}// ``Number.isSafeInteger`` covers ``Number.isInteger`` as well, so
{I}// a non-integer is refused here too.
{I}if (!Number.isSafeInteger(value)) {{
{II}return newDeserializationError<number>(
{III}`Expected an integer within the safe range of a number, `
{IIII}+ `but got: ${{text}}`
{II});
{I}}}

{I}return new AasCommon.Either<number, DeserializationError>(value, null);
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        return Stripped(
            f"""\
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<number, DeserializationError> {{
{I}const text = collapseWhitespace(parseTextContent(cursor));

{I}// NOTE (mristin):
{I}// `+INF` is read although it is written as `INF`: XSD 1.1 admits it, its
{I}// production being `(\\+|-)?INF`, and being liberal in what we accept
{I}// costs nothing here.
{I}if (text === "INF" || text === "+INF") {{
{II}return new AasCommon.Either<number, DeserializationError>(Infinity, null);
{I}}}
{I}if (text === "-INF") {{
{II}return new AasCommon.Either<number, DeserializationError>(-Infinity, null);
{I}}}
{I}if (text === "NaN") {{
{II}return new AasCommon.Either<number, DeserializationError>(NaN, null);
{I}}}

{I}// NOTE (mristin):
{I}// ``Number`` is far too permissive to be trusted with the text: it reads
{I}// an empty string and a run of whitespace as 0, a hexadecimal, binary or
{I}// octal prefix as the number it spells -- ``0x10`` as 16 -- and
{I}// ``Infinity`` as an infinity, none of which is a valid ``xs:double``.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#double
{I}if (!/^(\\+|-)?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([Ee](\\+|-)?[0-9]+)?$/.test(text)) {{
{II}return newDeserializationError<number>(
{III}`Expected xs:double text, but got: ${{text}}`
{II});
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
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<string, DeserializationError> {{
{I}return new AasCommon.Either<string, DeserializationError>(
{II}parseTextContent(cursor),
{II}null
{I});
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Stripped(
            f"""\
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<Uint8Array, DeserializationError> {{
{I}// NOTE (mristin):
{I}// ``xs:base64Binary`` allows whitespace between the characters, and not
{I}// only around them, while the decoder accepts none of it. So every
{I}// whitespace character is dropped, and not merely collapsed.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#base64Binary
{I}const text = removeWhitespace(parseTextContent(cursor));

{I}if (!matchesXsBase64Binary(text)) {{
{II}return newDeserializationError<Uint8Array>(
{III}`Expected a text as base64-encoded bytes, but got: ${{text}}`
{II});
{I}}}

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


def _content_parser_name_for_enumeration(
    enumeration: intermediate.Enumeration,
) -> Identifier:
    """Give out the name of the parser of an ``enumeration`` literal."""
    return Identifier(f"parse_{typescript_naming.enum_name(enumeration.name)}")


def _generate_parse_content_for_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """
    Generate the parser of the content of an element holding a literal.

    The work is done by the shared ``parseEnumerationContent``, which is given
    the ``fromString`` of the stringification module -- the lookup lives there
    already, and the only thing this function adds is the name of
    the enumeration for the error message.
    """
    enum_name = typescript_naming.enum_name(enumeration.name)
    function_name = _content_parser_name_for_enumeration(enumeration)
    from_string_function = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    return Stripped(
        f"""\
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.{enum_name}, DeserializationError> {{
{I}return parseEnumerationContent(
{II}cursor,
{II}{typescript_common.string_literal(enum_name)},
{II}AasStringification.{from_string_function}
{I});
}}"""
    )


def _parse_sequence_function_name_for_concrete_class(
    cls: intermediate.ConcreteClass,
) -> Identifier:
    """
    Generate the name of the function to parse the sequence of properties of ``cls``.

    The function assumes that the opening tag has been already read and parses
    only the properties, breaking (without consuming) at the closing tag. The
    caller is responsible for reading the opening tag beforehand and consuming
    the closing tag afterwards -- which is exactly the contract of
    a ``ContentParser``, so this function needs no wrapper to serve as one.
    """
    return typescript_naming.function_name(
        Identifier(f"parse_{cls.name}_from_sequence")
    )


def _dispatch_parse_element_function_name(
    interface: intermediate.Interface,
) -> Identifier:
    """Generate the name of the function to dispatch-parse an ``interface``."""
    return typescript_naming.function_name(
        Identifier(f"dispatch_parse_{interface.name}_element")
    )


def _dispatch_parse_element_function_name_for_named_union(
    named_union: intermediate.NamedUnion,
) -> Identifier:
    """Generate the name of the function to dispatch-parse the ``named_union``."""
    return typescript_naming.function_name(
        Identifier(f"dispatch_parse_{named_union.name}_element")
    )


def _dispatch_map_name(name: Identifier) -> Identifier:
    """
    Give out the name of the map from a local name to the parser of that element.

    The ``name`` is the name of the interface or of the named union *as it is spelled
    in the meta-model*, and not as it is spelled in TypeScript: the constant is
    upper-snake-cased, and a camel-cased type name would lose its word boundaries.
    """
    return typescript_naming.constant_name(Identifier(f"parsers_of_{name}"))


def _dispatch_parse_function_name(
    type_anno: intermediate.OurTypeAnnotation,
) -> Identifier:
    """Give out the dispatching parser of ``type_anno``, see :py:func:`typescript_common.is_dispatched`."""
    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.NamedUnion):
        return _dispatch_parse_element_function_name_for_named_union(
            named_union=our_type
        )

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class, but got: {our_type}"

    assert our_type.interface is not None, (
        "Expected an interface on an abstract class, or on a concrete class "
        "with concrete descendants"
    )

    return _dispatch_parse_element_function_name(our_type.interface)


def _content_parser_name(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> Identifier:
    """
    Give out the parser of the content of the element holding a value of
    the ``type_annotation``.

    Every parser shares the shape ``ContentParser<T>``: the opening tag has been read
    by the caller, and the parser stops right before the corresponding closing tag.
    Two of the five kinds need no generated parser at all, as the function which is
    generated together with the type already wears the shape -- a class embeds its
    properties directly, so ``parse{Cls}FromSequence`` *is* the content of
    the element, and a dispatched value nests an element of its own, which
    ``dispatchParse{X}Element`` reads whole. Those two are keyed by a *symbol* of
    the meta-model, and their names contain no underscore; everything else is keyed
    by a *type*, and its name ends in an underscore and the type's moniker, see
    :py:func:`typescript_common.type_moniker`.

    This is a pure function of its argument. The code of the parsers which have to be
    composed is generated by :py:class:`_ParserRegistry`.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    ):
        if typescript_common.is_dispatched(type_anno):
            return _dispatch_parse_function_name(type_anno)

        assert isinstance(type_anno.our_type, intermediate.ConcreteClass), (
            f"Unexpected abstract class with no concrete "
            f"descendants: {type_anno.our_type.name!r}"
        )

        return _parse_sequence_function_name_for_concrete_class(cls=type_anno.our_type)

    return Identifier(f"parse_{typescript_common.type_moniker(type_anno)}")


def _element_parser_name(
    type_anno: intermediate.AtomicTypeAnnotation, tag_suffix: str
) -> Identifier:
    """
    Give out the parser of a whole XML element, the tags included, holding a value of
    the ``type_anno``.

    This is what an item of a list or of a tuple is parsed with. A dispatched value
    picks the tag from its own model type, so it needs no name and no generated
    parser; a class picks the tag from its own model type as well, and everything
    else sits in an element tagged ``v``, ``v1``, ``v2``, *etc.*, prescribed by
    the position, which the ``tag_suffix`` gives.
    """
    if typescript_common.is_dispatched(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)
        return _dispatch_parse_function_name(type_anno)

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.ConcreteClass
    ):
        return Identifier(f"parseElement_{typescript_common.atomic_moniker(type_anno)}")

    return Identifier(
        f"parseAtV{tag_suffix}_{typescript_common.atomic_moniker(type_anno)}"
    )


class _ParserRegistry:
    """
    Generate the code of the parsers which a meta-model needs to be composed.

    All the parsers share the same shape, ``ContentParser<T>``, so a parser can be
    given to another parser as its item parser, and a list of enumeration literals --
    or anything deeper that a meta-model might grow -- falls out of the pieces which
    are already there.

    The composed parsers are de-duplicated by the type which they parse, so that all
    the classes share them, and they are named by :py:func:`_content_parser_name` and
    :py:func:`_element_parser_name`. Nothing is composed at the time of the parsing:
    a parser is a module-level function declaration, which is hoisted, so the order
    in which we emit them does not matter, and the de-serialization allocates no
    closure.

    The methods come grouped: first the queries, which give out what has been
    registered so far and change nothing, and then the commands, which register and
    give out nothing.
    """

    def __init__(self) -> None:
        """Initialize with nothing registered."""
        self._blocks_by_name = dict()  # type: Dict[Identifier, Stripped]

    @property
    def blocks(self) -> List[Stripped]:
        """Give out the code of the registered parsers, ordered by the parser name."""
        return [self._blocks_by_name[name] for name in sorted(self._blocks_by_name)]

    def _add(self, name: Identifier, block: Stripped) -> None:
        """Register the ``block`` which defines the parser ``name``."""
        self._blocks_by_name[name] = block

    def _register_element_parser(
        self, type_anno: intermediate.AtomicTypeAnnotation, tag_suffix: str
    ) -> None:
        """
        Register the parser of a whole element holding a value of the ``type_anno``.

        A dispatched value needs none, see :py:func:`_element_parser_name`.
        """
        if typescript_common.is_dispatched(type_anno):
            return

        name = _element_parser_name(type_anno, tag_suffix)

        value_type = typescript_common.generate_type(
            type_anno, types_module=Identifier("AasTypes")
        )

        if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.our_type, intermediate.ConcreteClass
        ):
            tag_literal = typescript_common.string_literal(
                naming.xml_class_name(type_anno.our_type.name)
            )
        else:
            tag_literal = typescript_common.string_literal(f"v{tag_suffix}")

        content_parser = _content_parser_name(type_anno)

        call = Stripped(
            f"""\
parseNamedElement(
{I}cursor,
{I}{tag_literal},
{I}{content_parser}
)"""
        )

        self._add(
            name,
            Stripped(
                f"""\
function {name}(
{I}cursor: XmlCursor
): AasCommon.Either<{value_type}, DeserializationError> {{
{I}return {indent_but_first_line(call, I)};
}}"""
            ),
        )

    def _register_list_parser(self, type_anno: intermediate.ListTypeAnnotation) -> None:
        """Register the parser of the content of an element holding a list."""
        items_type_anno = intermediate.beneath_optional(type_anno.items)

        assert isinstance(items_type_anno, intermediate.AtomicTypeAnnotationAsTuple), (
            f"(mristin) We only handle XML de/serialization of lists "
            f"containing atomic values, but you want to generate the code "
            f"for a list of type {type_anno}. Please contact the "
            f"developers if you need this feature."
        )

        self._register_element_parser(items_type_anno, tag_suffix="")

        name = _content_parser_name(type_anno)

        item_type = typescript_common.generate_type(
            items_type_anno, types_module=Identifier("AasTypes")
        )
        item_parser = _element_parser_name(items_type_anno, tag_suffix="")

        call = Stripped(
            f"""\
parseList<{item_type}>(
{I}cursor,
{I}{item_parser}
)"""
        )

        self._add(
            name,
            Stripped(
                f"""\
function {name}(
{I}cursor: XmlCursor
): AasCommon.Either<Array<{item_type}>, DeserializationError> {{
{I}return {indent_but_first_line(call, I)};
}}"""
            ),
        )

    def _register_tuple_parser(
        self, type_anno: intermediate.TupleTypeAnnotation
    ) -> None:
        """Register the parser of the content of an element holding a tuple."""
        arity = len(type_anno.items)

        item_types = []  # type: List[str]
        parse_items = []  # type: List[str]

        for i, item_type_anno in enumerate(type_anno.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, "
                "constrained primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so no "
                "nested optionals, lists or tuples are expected here."
            )

            self._register_element_parser(item_type_anno, tag_suffix=str(i + 1))

            item_types.append(
                typescript_common.generate_type(
                    item_type_anno, types_module=Identifier("AasTypes")
                )
            )
            parse_items.append(_element_parser_name(item_type_anno, str(i + 1)))

        name = _content_parser_name(type_anno)

        value_type = typescript_common.generate_type(
            type_anno, types_module=Identifier("AasTypes")
        )

        item_types_joined = ", ".join(item_types)

        arguments_joined = ",\n".join(f"{I}{argument}" for argument in parse_items)

        call = Stripped(
            f"""\
parseTuple{arity}<{item_types_joined}>(
{I}cursor,
{arguments_joined}
)"""
        )

        self._add(
            name,
            Stripped(
                f"""\
function {name}(
{I}cursor: XmlCursor
): AasCommon.Either<{value_type}, DeserializationError> {{
{I}return {indent_but_first_line(call, I)};
}}"""
            ),
        )

    def register_property_parser(
        self, type_annotation: intermediate.TypeAnnotationUnion
    ) -> None:
        """
        Register the parsers needed to parse the content of the element holding
        a value of the ``type_annotation``.
        """
        type_anno = intermediate.beneath_optional(type_annotation)

        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            self._register_list_parser(type_anno)

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            self._register_tuple_parser(type_anno)

        else:
            # NOTE (mristin):
            # An atomic value is parsed either by a parser which is generated
            # together with its type -- a class and a dispatched value -- or by one of
            # the parsers which we generate once for the whole module, for a primitive
            # and for an enumeration. There is nothing to compose in either case.
            pass


def _generate_parse_tuple_function(arity: int) -> Stripped:
    """
    Generate a generic function to parse a tuple of the given ``arity``.

    Each positional item is parsed by its own ``parseItem{i}``, which is expected to
    have already consumed its own opening and closing tags -- see, for example,
    ``parseNamedElement`` or a dispatch-parse function, both of which do.
    """
    type_params_joined = ", ".join(f"T{i}" for i in range(arity))
    tuple_type = f"[{', '.join(f'T{i}' for i in range(arity))}]"

    params_joined = ",\n".join(
        f"{I}parseItem{i}: ContentParser<T{i}>" for i in range(arity)
    )

    item_blocks = []  # type: List[str]
    for i in range(arity):
        item_blocks.append(
            f"""\
const item{i}OrError = parseItem{i}(cursor);
if (item{i}OrError.error !== null) {{
{I}item{i}OrError.error.path.prepend(new IndexSegment({i}));
{I}return new AasCommon.Either<{tuple_type}, DeserializationError>(
{II}null,
{II}item{i}OrError.error
{I});
}}"""
        )
    item_blocks_joined = "\n\n".join(item_blocks)

    values_joined = ",\n".join(f"item{i}OrError.mustValue()" for i in range(arity))

    return Stripped(
        f"""\
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function parseTuple{arity}<{type_params_joined}>(
{I}cursor: XmlCursor,
{params_joined}
): AasCommon.Either<{tuple_type}, DeserializationError> {{
{I}{indent_but_first_line(item_blocks_joined, I)}

{I}return new AasCommon.Either<{tuple_type}, DeserializationError>(
{II}[
{III}{indent_but_first_line(values_joined, III)}
{II}],
{II}null
{I});
}}"""
    )


@require(lambda cls, prop: intermediate.runtime_id(prop) in cls.property_id_set)
def _generate_parse_case_for_property(
    cls: intermediate.ConcreteClass,
    prop: intermediate.Property,
    var_name: Identifier,
) -> Stripped:
    """
    Generate a switch case to parse a property from XML element content.

    The generated code stores the parsed property value into ``var_name``.
    """
    del cls  # only used for the pre-condition

    xml_name_literal = typescript_common.string_literal(prop.xml_name)

    # NOTE (mristin):
    # A case sits two levels below the ``switch``, which the class's parser indents by
    # three, so the body of a case lands on the fourth level.
    content_parser = _content_parser_name(prop.type_annotation)

    call = Stripped(
        f"""\
parseElementContent(
{I}cursor,
{I}propertyLocalName,
{I}{content_parser}
)"""
    )

    # NOTE (mristin):
    # Both halves of the result are taken unconditionally. On a failure the value is
    # ``null``, and the property loop returns as soon as it sees the error, so what we
    # assign to the variable is never read -- see also ``parseElementContent``.
    return Stripped(
        f"""\
case {xml_name_literal}: {{
{I}if ({var_name} !== null) {{
{II}propertyError = duplicatePropertyError(propertyLocalName);
{II}break;
{I}}}

{I}const parsed = {indent_but_first_line(call, I)};
{I}propertyError = parsed.error;
{I}{var_name} = parsed.value;
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
 * after this function returns successfully. This is the contract of
 * a `ContentParser`, so this function is used as one wherever an instance
 * of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}} is embedded.
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
{III}propertyError.path.prepend(new ElementSegment(propertyLocalName));
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


def _generate_dispatch_map(
    map_name: Identifier,
    expected_name: Identifier,
    implementers: Sequence[intermediate.ConcreteClass],
) -> Stripped:
    """
    Generate the map from the local name of an XML element to the parser of
    the content of that element.

    The map replaces what used to be a ``switch`` in every dispatching function:
    the parsers are all of the same shape, so the only thing which distinguishes
    one dispatch from another is which local names it accepts.
    """
    entries = []  # type: List[str]
    for implementer in implementers:
        local_name_literal = typescript_common.string_literal(
            naming.xml_class_name(implementer.name)
        )
        parse_function_name = _parse_sequence_function_name_for_concrete_class(
            cls=implementer
        )

        entries.append(f"{I}[{local_name_literal}, {parse_function_name}]")

    entries_joined = ",\n".join(entries)

    return Stripped(
        f"""\
const {map_name} = new Map<
{I}string,
{I}ContentParser<AasTypes.{expected_name}>
>([
{entries_joined}
]);"""
    )


def _generate_dispatch_parse_element(
    map_name: Identifier,
    expected_name: Identifier,
    function_name: Identifier,
    may_be_unused: bool,
) -> Stripped:
    """
    Generate a function to dispatch-parse an element into ``expected_name``.

    The function is a shim over the shared ``dispatchParseElement`` and the map
    which :py:func:`_generate_dispatch_map` generates. Unlike
    :py:func:`_generate_root_dispatch_map`, which has to account for every concrete
    class in the meta-model, that map holds only the implementers of
    ``expected_name``. This lets us reject an XML element of an unexpected type
    based on its local name alone, without wastefully parsing its full (possibly
    deeply nested) content only to discover the type mismatch afterwards.

    If ``may_be_unused`` is set, we instruct the linter not to complain if
    the function is never called.
    """
    expected_name_literal = typescript_common.string_literal(expected_name)

    maybe_disable_unused = (
        "// eslint-disable-next-line @typescript-eslint/no-unused-vars\n"
        if may_be_unused
        else ""
    )

    call = Stripped(
        f"""\
dispatchParseElement(
{I}cursor,
{I}{expected_name_literal},
{I}{map_name}
)"""
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
{maybe_disable_unused}function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<AasTypes.{expected_name}, DeserializationError> {{
{I}return {indent_but_first_line(call, I)};
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
    entries = []  # type: List[str]
    for cls in symbol_table.concrete_classes:
        local_name_literal = typescript_common.string_literal(
            naming.xml_class_name(cls.name)
        )
        parse_function_name = _parse_sequence_function_name_for_concrete_class(cls=cls)

        entries.append(f"{I}[{local_name_literal}, {parse_function_name}]")

    entries_joined = ",\n".join(entries)

    return Stripped(
        f"""\
const ROOT_DISPATCH_BY_LOCAL_NAME = new Map<
{I}string,
{I}ContentParser<AasTypes.Class>
>([
{entries_joined}
]);"""
    )


# endregion

# region Serialization


def _is_instance_type(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether a value of ``type_anno`` is written as its own, self-describing
    XML element.

    This is the case for every class and for every named union: the element is
    picked by the run-time type of the value, which one virtual call answers for
    all of them at once. The reading needs a dispatcher per interface instead, as
    it has to decide what to construct before it has read anything.
    """
    return isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    )


def _write_sequence_function_name_for_concrete_class(
    cls: intermediate.ConcreteClass,
) -> Identifier:
    """
    Generate the name of the function writing the properties of ``cls``.

    The function writes only the properties, and neither the opening nor the closing
    tag of the element which holds them -- which is exactly the contract of
    a ``ContentWriter``, so this function needs no wrapper to serve as one.
    """
    return Identifier(f"write{typescript_naming.class_name(cls.name)}AsSequence")


def _content_writer_name(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> Identifier:
    """
    Give out the writer of the content of the element holding a value of
    the ``type_annotation``.

    Every writer shares the shape ``ContentWriter<T>``: it writes what sits between
    the opening and the closing tag, both of which the caller writes. As on
    the reading side, two kinds need no generated writer at all -- a class embeds
    its properties directly, so ``write{Cls}AsSequence`` *is* the content of
    the element, and an instance nests an element of its own, which ``writeClass``
    writes whole. A list of instances needs none either, since the item writer is
    ``writeClass`` whatever the item type is, so ``writeListOfInstances`` serves
    every such list.

    This is a pure function of its argument. The code of the writers which have to
    be composed is generated by :py:class:`_WriterRegistry`.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    if _is_instance_type(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)

        if typescript_common.is_dispatched(type_anno):
            return Identifier("writeClass")

        assert isinstance(type_anno.our_type, intermediate.ConcreteClass), (
            f"Unexpected abstract class with no concrete "
            f"descendants: {type_anno.our_type.name!r}"
        )

        return _write_sequence_function_name_for_concrete_class(cls=type_anno.our_type)

    if isinstance(type_anno, intermediate.ListTypeAnnotation) and _is_instance_type(
        intermediate.beneath_optional(type_anno.items)
    ):
        return Identifier("writeListOfInstances")

    return Identifier(f"write_{typescript_common.type_moniker(type_anno)}")


def _element_writer_name(
    type_anno: intermediate.AtomicTypeAnnotation, tag_suffix: str
) -> Identifier:
    """
    Give out the writer of a whole XML element, the tags included, holding a value
    of the ``type_anno``.

    This is what an item of a list or of a tuple is written with. An instance tags
    its element with its own model type, which ``writeClass`` reads off the value;
    everything else sits in an element tagged ``v``, ``v1``, ``v2``, *etc.*,
    prescribed by the position, which the ``tag_suffix`` gives.
    """
    if _is_instance_type(type_anno):
        return Identifier("writeClass")

    return Identifier(
        f"writeAtV{tag_suffix}_{typescript_common.atomic_moniker(type_anno)}"
    )


def _generate_write_content_for_primitive_type(
    primitive_type: intermediate.PrimitiveType,
) -> Stripped:
    """
    Generate the writer of the content of an element holding a primitive value.

    The value is rendered and pushed in the very same function. Unlike the reading,
    which has to validate the text before it can hand out a value, there is nothing
    left to separate here once the value is at hand.
    """
    function_name = Identifier(
        f"write_{typescript_common.MONIKER_BY_PRIMITIVE_TYPE[primitive_type]}"
    )

    if primitive_type is intermediate.PrimitiveType.BOOL:
        return Stripped(
            f"""\
function {function_name}(
{I}parts: Array<string>,
{I}value: boolean
): void {{
{I}parts.push(value ? "true" : "false");
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.INT:
        return Stripped(
            f"""\
function {function_name}(
{I}parts: Array<string>,
{I}value: number
): void {{
{I}// NOTE (mristin):
{I}// Beyond 2^53 - 1 a ``number`` no longer holds every integer, so the value
{I}// we were handed has already lost its identity -- writing it out would
{I}// record a different xs:long without a word. ``Number.isSafeInteger``
{I}// covers ``Number.isInteger`` as well.
{I}if (!Number.isSafeInteger(value)) {{
{II}throw new SerializationError(
{III}`Expected an integer within the safe range of a number, `
{IIII}+ `but got: ${{value}}`
{II});
{I}}}

{I}parts.push(`${{value}}`);
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        return Stripped(
            f"""\
function {function_name}(
{I}parts: Array<string>,
{I}value: number
): void {{
{I}if (Number.isNaN(value)) {{
{II}parts.push("NaN");
{I}}} else if (value === Infinity) {{
{II}parts.push("INF");
{I}}} else if (value === -Infinity) {{
{II}parts.push("-INF");
{I}}} else if (Object.is(value, -0)) {{
{II}// NOTE (mristin):
{II}// ``${{-0}}`` is "0", so the sign would be dropped, and a negative zero
{II}// would come back as a positive one. ``-0`` is a valid xs:double, and
{II}// the other SDKs keep the sign, so we keep it too. Mind that
{II}// ``value === -0`` is true for a positive zero as well, which is why
{II}// this asks ``Object.is``.
{II}parts.push("-0");
{I}}} else {{
{II}parts.push(`${{value}}`);
{I}}}
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.STR:
        return Stripped(
            f"""\
function {function_name}(
{I}parts: Array<string>,
{I}value: string
): void {{
{I}parts.push(escapeXmlText(value));
}}"""
        )

    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Stripped(
            f"""\
function {function_name}(
{I}parts: Array<string>,
{I}value: Uint8Array
): void {{
{I}parts.push(escapeXmlText(AasCommon.base64Encode(value)));
}}"""
        )

    else:
        assert_never(primitive_type)

    raise AssertionError("Should not have gotten here")


def _generate_write_content_for_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """
    Generate the writer of the content of an element holding a literal.

    The work is done by the shared ``writeEnumerationContent``, which is given
    the ``toString`` of the stringification module -- the lookup lives there
    already, and the only thing this function adds is the name of the enumeration
    for the error message.
    """
    enum_name = typescript_naming.enum_name(enumeration.name)
    function_name = Identifier(f"write_{enum_name}")
    to_string_function = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_to_string")
    )

    return Stripped(
        f"""\
function {function_name}(
{I}parts: Array<string>,
{I}value: AasTypes.{enum_name}
): void {{
{I}writeEnumerationContent(
{II}parts,
{II}value,
{II}{typescript_common.string_literal(enum_name)},
{II}AasStringification.{to_string_function}
{I});
}}"""
    )


def _generate_write_tuple_function(arity: int) -> Stripped:
    """
    Generate a generic function to write a tuple of the given ``arity``.

    Each positional item is written by its own ``writeItem{i}``, which writes its
    own opening and closing tags -- see, for example, a ``writeAtV{i}_{M}`` or
    ``writeClass``, both of which do. The index is advanced only after an item has
    been written, so that a failure reports the item which actually failed.
    """
    type_params_joined = ", ".join(f"T{i}" for i in range(arity))
    tuple_type = f"[{', '.join(f'T{i}' for i in range(arity))}]"

    params_joined = ",\n".join(
        f"{I}writeItem{i}: ContentWriter<T{i}>" for i in range(arity)
    )

    item_statements = []  # type: List[str]
    for i in range(arity):
        if i > 0:
            item_statements.append(f"index = {i};")
        item_statements.append(f"writeItem{i}(parts, value[{i}]);")

    item_statements_joined = "\n".join(item_statements)

    return Stripped(
        f"""\
function writeTuple{arity}<{type_params_joined}>(
{I}parts: Array<string>,
{I}value: {tuple_type},
{params_joined}
): void {{
{I}let index = 0;
{I}try {{
{II}{indent_but_first_line(item_statements_joined, II)}
{I}}} catch (error) {{
{II}if (error instanceof SerializationError) {{
{III}error.prependIndex(index);
{II}}}
{II}throw error;
{I}}}
}}"""
    )


class _WriterRegistry:
    """
    Generate the code of the writers which a meta-model needs to be composed.

    All the writers share the same shape, ``ContentWriter<T>``, so a writer can be
    given to another writer as its item writer, and a list of enumeration literals --
    or anything deeper that a meta-model might grow -- falls out of the pieces which
    are already there.

    The composed writers are de-duplicated by the type which they write, so that all
    the classes share them, and they are named by :py:func:`_content_writer_name` and
    :py:func:`_element_writer_name`. Nothing is composed at the time of the writing:
    a writer is a module-level function declaration, which is hoisted, so the order
    in which we emit them does not matter, and the serialization allocates no closure.

    The methods come grouped: first the queries, which give out what has been
    registered so far and change nothing, and then the commands, which register and
    give out nothing.
    """

    def __init__(self) -> None:
        """Initialize with nothing registered."""
        self._blocks_by_name = dict()  # type: Dict[Identifier, Stripped]

    @property
    def blocks(self) -> List[Stripped]:
        """Give out the code of the registered writers, ordered by the writer name."""
        return [self._blocks_by_name[name] for name in sorted(self._blocks_by_name)]

    def _add(self, name: Identifier, block: Stripped) -> None:
        """Register the ``block`` which defines the writer ``name``."""
        self._blocks_by_name[name] = block

    def _register_element_writer(
        self, type_anno: intermediate.AtomicTypeAnnotation, tag_suffix: str
    ) -> None:
        """
        Register the writer of a whole element holding a value of the ``type_anno``.

        An instance needs none, see :py:func:`_element_writer_name`.
        """
        if _is_instance_type(type_anno):
            return

        name = _element_writer_name(type_anno, tag_suffix)

        value_type = typescript_common.generate_type(
            type_anno, types_module=Identifier("AasTypes")
        )

        tag_literal = typescript_common.string_literal(f"v{tag_suffix}")
        content_writer = _content_writer_name(type_anno)

        call = Stripped(
            f"""\
writeElement(
{I}parts,
{I}{tag_literal},
{I}value,
{I}{content_writer}
)"""
        )

        self._add(
            name,
            Stripped(
                f"""\
function {name}(
{I}parts: Array<string>,
{I}value: {value_type}
): void {{
{I}{indent_but_first_line(call, I)};
}}"""
            ),
        )

    def _register_list_writer(self, type_anno: intermediate.ListTypeAnnotation) -> None:
        """Register the writer of the content of an element holding a list."""
        items_type_anno = intermediate.beneath_optional(type_anno.items)

        assert isinstance(items_type_anno, intermediate.AtomicTypeAnnotationAsTuple), (
            f"(mristin) We only handle XML de/serialization of lists "
            f"containing atomic values, but you want to generate the code "
            f"for a list of type {type_anno}. Please contact the "
            f"developers if you need this feature."
        )

        if _is_instance_type(items_type_anno):
            # NOTE (mristin):
            # Every item of every list of instances is written by ``writeClass``,
            # so the one shared ``writeListOfInstances`` serves them all.
            return

        self._register_element_writer(items_type_anno, tag_suffix="")

        name = _content_writer_name(type_anno)

        item_type = typescript_common.generate_type(
            items_type_anno, types_module=Identifier("AasTypes")
        )
        item_writer = _element_writer_name(items_type_anno, tag_suffix="")

        call = Stripped(
            f"""\
writeList(
{I}parts,
{I}values,
{I}{item_writer}
)"""
        )

        self._add(
            name,
            Stripped(
                f"""\
function {name}(
{I}parts: Array<string>,
{I}values: Array<{item_type}>
): void {{
{I}{indent_but_first_line(call, I)};
}}"""
            ),
        )

    def _register_tuple_writer(
        self, type_anno: intermediate.TupleTypeAnnotation
    ) -> None:
        """Register the writer of the content of an element holding a tuple."""
        arity = len(type_anno.items)

        write_items = []  # type: List[str]

        for i, item_type_anno in enumerate(type_anno.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, "
                "constrained primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so no "
                "nested optionals, lists or tuples are expected here."
            )

            self._register_element_writer(item_type_anno, tag_suffix=str(i + 1))

            write_items.append(_element_writer_name(item_type_anno, str(i + 1)))

        name = _content_writer_name(type_anno)

        value_type = typescript_common.generate_type(
            type_anno, types_module=Identifier("AasTypes")
        )

        arguments_joined = ",\n".join(f"{I}{argument}" for argument in write_items)

        call = Stripped(
            f"""\
writeTuple{arity}(
{I}parts,
{I}value,
{arguments_joined}
)"""
        )

        self._add(
            name,
            Stripped(
                f"""\
function {name}(
{I}parts: Array<string>,
{I}value: {value_type}
): void {{
{I}{indent_but_first_line(call, I)};
}}"""
            ),
        )

    def register_property_writer(
        self, type_annotation: intermediate.TypeAnnotationUnion
    ) -> None:
        """
        Register the writers needed to write the content of the element holding
        a value of the ``type_annotation``.
        """
        type_anno = intermediate.beneath_optional(type_annotation)

        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            self._register_list_writer(type_anno)

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            self._register_tuple_writer(type_anno)

        else:
            # NOTE (mristin):
            # An atomic value is written either by a writer which is generated
            # together with its type -- a class and an instance -- or by one of
            # the writers which we generate once for the whole module, for a
            # primitive and for an enumeration. There is nothing to compose in
            # either case.
            pass


@require(lambda cls, prop: intermediate.runtime_id(prop) in cls.property_id_set)
def _generate_write_property(
    cls: intermediate.ConcreteClass,
    prop: intermediate.Property,
) -> Stripped:
    """Generate the statement writing the XML element of a property."""
    del cls  # only used for the pre-condition

    function_name = (
        "writeOptionalProperty"
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        else "writeProperty"
    )

    xml_name_literal = typescript_common.string_literal(prop.xml_name)
    prop_name = typescript_naming.property_name(prop.name)
    content_writer = _content_writer_name(prop.type_annotation)

    # NOTE (mristin):
    # A failure is reported at a path into the *instance*, so the path names
    # the TypeScript property and not the XML element. The two coincide unless
    # the meta-model prescribes a serialization name of its own, and the framer
    # falls back to the element name, so the property is spelled out only where
    # it actually differs.
    trailing_property_name = (
        f",\n{I}{typescript_common.string_literal(prop_name)}"
        if str(prop.xml_name) != str(prop_name)
        else ""
    )

    call = Stripped(
        f"""\
{function_name}(
{I}parts,
{I}{xml_name_literal},
{I}that.{prop_name},
{I}{content_writer}{trailing_property_name}
)"""
    )

    return Stripped(f"{call};")


def _generate_write_sequence_of_concrete_class(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the writer of the properties of a concrete class."""
    function_name = _write_sequence_function_name_for_concrete_class(cls=cls)
    cls_name = typescript_naming.class_name(cls.name)

    if len(cls.properties) == 0:
        body = Stripped("// No properties")
    else:
        body = Stripped(
            "\n".join(
                _generate_write_property(cls=cls, prop=prop) for prop in cls.properties
            )
        )

    return Stripped(
        f"""\
/**
 * Write the properties of an instance
 * of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}}, and neither the opening
 * nor the closing tag of the element which holds them -- which is the contract of
 * a `ContentWriter`, so this function is used as one.
 */
function {function_name}(
{I}parts: Array<string>,
{I}that: AasTypes.{cls_name}
): void {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_serializer(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the visitor dispatching on the run-time type of an instance."""
    methods = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        method_name = typescript_naming.method_name(
            Identifier(f"visit_{cls.name}_with_context")
        )
        cls_name = typescript_naming.class_name(cls.name)
        local_name_literal = typescript_common.string_literal(
            naming.xml_class_name(cls.name)
        )

        write_sequence = _write_sequence_function_name_for_concrete_class(cls=cls)

        call = Stripped(
            f"""\
writeElement(
{I}parts,
{I}{local_name_literal},
{I}that,
{I}{write_sequence}
)"""
        )

        methods.append(
            Stripped(
                f"""\
{method_name}(
{I}that: AasTypes.{cls_name},
{I}parts: Array<string>
): void {{
{I}{indent_but_first_line(call, I)};
}}"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Write the XML element of an instance, dispatching on its run-time type.
 *
 * Each method writes the whole element -- the tags included -- since the element
 * is picked by the run-time type, which this dispatch has just established. The
 * properties are written by the corresponding module-level `write{Cls}AsSequence`,
 * which is the content writer of that very element.
 */
class Serializer extends AasTypes.AbstractVisitorWithContext<Array<string>> {"""
    )

    for method in methods:
        writer.write("\n")
        writer.write(f"{I}{indent_but_first_line(method, I)}\n")

    writer.write("}")

    return Stripped(writer.getvalue())


# endregion


#: Names which ``xmlcommon`` gives out and which this module may name
_XML_COMMON_NAMES = (
    "ContentParser",
    "ContentWriter",
    "DeserializationError",
    "ElementSegment",
    "IndexSegment",
    "KeySegment",
    "SerializationError",
    "XmlCursor",
    "collapseWhitespace",
    "consumeCloseTag",
    "currentTokenKind",
    "escapeXmlText",
    "localNameOfTag",
    "matchesXsBase64Binary",
    "newDeserializationError",
    "nextPropertyOpenTag",
    "parseElementContent",
    "parseList",
    "parseNamedElement",
    "parseTextContent",
    "readNextOpenTag",
    "readRequiredRootOpenTag",
    "removeWhitespace",
    "tokenizeXml",
    "writeElement",
    "writeList",
    "writeOptionalProperty",
    "writeProperty",
)

#: Names which ``xmlrpc`` gives out, each with the name under which this module
#: knows it -- the XML-RPC module speaks of a ``<value>`` and of a ``<struct>``,
#: while here everything is named after the type which it de/serializes, see
#: :py:func:`_content_parser_name`
_XML_RPC_NAMES_AND_ALIASES = (
    ("parseArrayBody", "parse_jsonArray"),
    ("parseStructBody", "parse_jsonObject"),
    ("parseValueContent", "parse_jsonValue"),
    ("writeArrayBody", "write_jsonArray"),
    ("writeStructBody", "write_jsonObject"),
    ("writeValueContent", "write_jsonValue"),
)

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"^[ \t]*//.*$", re.MULTILINE)


def _generate_imports(body: str) -> Stripped:
    """
    Generate the imports which the ``body`` of the module actually names.

    ESLint refuses an import which nothing names, and what a meta-model reaches
    differs from one model to the next -- one which has no JSON-able type names
    nothing of the XML-RPC at all. The list is therefore read off the code
    instead of being spelled out. The comments go first, as a name which occurs
    only in a doc comment is no use of it.
    """
    code = _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", body))

    def is_named(name: str) -> bool:
        """Check whether the ``code`` names the ``name``."""
        return re.search(r"\b" + name + r"\b", code) is not None

    blocks = [
        Stripped(
            """\
import * as AasCommon from "./common";
import * as AasTypes from "./types";
import * as AasStringification from "./stringification";"""
        )
    ]  # type: List[Stripped]

    xml_common_names = [name for name in _XML_COMMON_NAMES if is_named(name)]
    assert len(xml_common_names) > 0, "Expected at least one XML primitive to be named"

    names_joined = ",\n".join(f"{I}{name}" for name in xml_common_names)
    blocks.append(
        Stripped(
            f"""\
import {{
{names_joined}
}} from "./xmlcommon";"""
        )
    )

    xml_rpc_aliases = [
        f"{I}{name} as {alias}"
        for name, alias in _XML_RPC_NAMES_AND_ALIASES
        if is_named(alias)
    ]
    if len(xml_rpc_aliases) > 0:
        aliases_joined = ",\n".join(xml_rpc_aliases)
        blocks.append(
            Stripped(
                f"""\
import {{
{aliases_joined}
}} from "./xmlrpc";"""
            )
        )

    return Stripped("\n\n".join(blocks))


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

    blocks = []  # type: List[Stripped]

    # NOTE (mristin):
    # A meta-model which has no interface and no named union dispatches nowhere, and
    # an unused function would make ESLint unhappy. The shims which this function
    # serves are generated further below, one per interface and per named union.
    if len(symbol_table.named_unions) > 0 or any(
        cls.interface is not None for cls in symbol_table.classes
    ):
        blocks.append(
            Stripped(
                f"""\
/**
 * Read the next XML element from `cursor` and parse it with the parser which
 * `parsersByLocalName` gives for the element's local name.
 *
 * An abstract class, a concrete class with descendants and a named union all
 * prescribe no element tag of their own, so the tag is what tells us which
 * parser to use. The set of local names which are accepted is the only thing
 * which distinguishes one such dispatch from another, so it is the only thing
 * which is generated -- the reading itself lives here.
 *
 * @param cursor - to read from
 * @param expectedWhat - what we expected to read, for the error message
 * @param parsersByLocalName - parser of the content, by the element's local name
 * @returns parsed instance, or an error
 * @typeParam T - type of the parsed instance
 */
function dispatchParseElement<T>(
{I}cursor: XmlCursor,
{I}expectedWhat: string,
{I}parsersByLocalName: ReadonlyMap<string, ContentParser<T>>
): AasCommon.Either<T, DeserializationError> {{
{I}const startTagOrError = readNextOpenTag(cursor);
{I}if (startTagOrError.error !== null) {{
{II}return new AasCommon.Either<T, DeserializationError>(
{III}null,
{III}startTagOrError.error
{II});
{I}}}

{I}const localName = localNameOfTag(startTagOrError.mustValue().tag);

{I}const parseContent = parsersByLocalName.get(localName);
{I}if (parseContent === undefined) {{
{II}return newDeserializationError<T>(
{III}`Expected an instance of ${{expectedWhat}}, but got: ${{localName}}`
{II});
{I}}}

{I}cursor.advance();

{I}return parseElementContent(cursor, localName, parseContent);
}}"""
            )
        )

    if len(symbol_table.enumerations) > 0:
        blocks.append(
            Stripped(
                f"""\
/**
 * Parse the content of an XML element as a literal of the enumeration called
 * `enumerationName`, looking the text up with `fromString`.
 *
 * The lookup lives in the stringification module already, so this function is
 * generic over it, and every enumeration of the meta-model shares it. The name
 * of the enumeration is the only thing it adds, for the error message.
 *
 * @param cursor - to read from
 * @param enumerationName - name of the enumeration, for the error message
 * @param fromString - gives the literal for the text, or `null`
 * @returns parsed literal, or an error
 * @typeParam T - type of the enumeration
 */
function parseEnumerationContent<T>(
{I}cursor: XmlCursor,
{I}enumerationName: string,
{I}fromString: (text: string) => T | null
): AasCommon.Either<T, DeserializationError> {{
{I}const text = parseTextContent(cursor);

{I}const literal = fromString(text);
{I}if (literal === null) {{
{II}return newDeserializationError<T>(
{III}`Unexpected literal of ${{enumerationName}}: ${{text}}`
{II});
{I}}}

{I}return new AasCommon.Either<T, DeserializationError>(literal, null);
}}"""
            )
        )

    # NOTE (mristin):
    # A property which occurs twice is reported by the one shared function, so it is
    # needed as soon as any class has a property at all -- and not needed otherwise,
    # where an unused function would make ESLint unhappy.
    if any(
        len(concrete_cls.properties) > 0
        for concrete_cls in symbol_table.concrete_classes
    ):
        blocks.append(
            Stripped(
                f"""\
/**
 * Report that the property `localName` occurred more than once.
 *
 * The check itself sits in the property loop, right in front of the parse, since
 * only the loop knows whether the property's variable has been set already. This
 * is only the error, so that the message is written once instead of at every one
 * of the property cases.
 */
function duplicatePropertyError(localName: string): DeserializationError {{
{I}return new DeserializationError(
{II}"Property " + localName + " occurred more than once"
{I});
}}"""
            )
        )

    for primitive_type in intermediate.PrimitiveType:
        blocks.append(_generate_parse_content_for_primitive_type(primitive_type))

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_parse_content_for_enumeration(enumeration))

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_write_content_for_enumeration(enumeration))

    for arity in intermediate.tuple_arities(symbol_table=symbol_table):
        blocks.append(_generate_parse_tuple_function(arity))
        blocks.append(_generate_write_tuple_function(arity))

    # NOTE (mristin):
    # We compose the parsers first, so that we know which of them a meta-model
    # actually reaches. They are de-duplicated by the type which they parse, so that
    # all the classes share them, and they are hoisted function declarations, so
    # the order in which we emit them does not matter.
    parser_registry = _ParserRegistry()

    for concrete_cls in symbol_table.concrete_classes:
        for prop in concrete_cls.properties:
            parser_registry.register_property_parser(prop.type_annotation)

    blocks.extend(parser_registry.blocks)

    # NOTE (mristin):
    # The writers are composed in the same way, and for the same reasons, as
    # the parsers just above.
    writer_registry = _WriterRegistry()

    for concrete_cls in symbol_table.concrete_classes:
        for prop in concrete_cls.properties:
            writer_registry.register_property_writer(prop.type_annotation)

    blocks.extend(writer_registry.blocks)

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_parse_concrete_class(cls=concrete_cls))

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_write_sequence_of_concrete_class(cls=concrete_cls))

    for cls in symbol_table.classes:
        interface = None  # type: Optional[intermediate.Interface]

        if isinstance(cls, intermediate.AbstractClass):
            interface = cls.interface
        elif isinstance(cls, intermediate.ConcreteClass):
            if len(cls.concrete_descendants) > 0:
                assert (
                    cls.interface is not None
                ), "Expected an interface on a class with concrete descendants"

                interface = cls.interface
        else:
            assert_never(cls)

        if interface is None:
            continue

        if isinstance(interface.base, intermediate.AbstractClass):
            expected_name = typescript_naming.interface_name(interface.name)
        else:
            expected_name = typescript_naming.class_name(interface.name)

        map_name = _dispatch_map_name(interface.name)

        blocks.append(
            _generate_dispatch_map(
                map_name=map_name,
                expected_name=expected_name,
                implementers=interface.implementers,
            )
        )
        blocks.append(
            _generate_dispatch_parse_element(
                map_name=map_name,
                expected_name=expected_name,
                function_name=_dispatch_parse_element_function_name(interface),
                may_be_unused=False,
            )
        )
        blocks.append(_generate_from_xml_string_for_interface(interface=interface))

    # NOTE (mristin):
    # We keep the named unions' own dispatch functions in a loop of their
    # own, separate from the loop above, since a named union is never
    # a member of ``symbol_table.classes``.
    for named_union in symbol_table.named_unions:
        # NOTE (mristin):
        # Unlike an interface, a named union has no ``from...XmlString`` of its
        # own, so its dispatch function is unused if no property refers to it,
        # *e.g.*, when the named union is only nested in another named union.
        union_name = typescript_naming.union_name(named_union.name)

        map_name = _dispatch_map_name(named_union.name)

        blocks.append(
            _generate_dispatch_map(
                map_name=map_name,
                expected_name=union_name,
                implementers=named_union.implementers,
            )
        )
        blocks.append(
            _generate_dispatch_parse_element(
                map_name=map_name,
                expected_name=union_name,
                function_name=(
                    _dispatch_parse_element_function_name_for_named_union(
                        named_union=named_union
                    )
                ),
                may_be_unused=True,
            )
        )

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
/**
 * Write the instances of `values`, each as its own, self-describing XML element.
 *
 * @remarks
 *
 * Every item goes through {{@link writeClass}} whatever its declared type is, so
 * this one writer serves every list of instances in the meta-model.
 */
function writeListOfInstances(
{I}parts: Array<string>,
{I}values: Array<AasTypes.Class>
): void {{
{I}writeList(parts, values, writeClass);
}}

/**
 * Write `that` as its own, self-describing XML element.
 *
 * @remarks
 *
 * Which element that is, is decided by the run-time type of `that`, so this one
 * writer serves every abstract class, every named union, and the item of a list
 * or of a tuple of any class at all. The reading, which has to decide what to
 * construct before it has read anything, needs a dispatcher per interface instead.
 */
function writeClass(parts: Array<string>, that: AasTypes.Class): void {{
{I}SERIALIZER.visitWithContext(that, parts);
}}

/**
 * Write the literal `value` of the enumeration `enumerationName` as the content
 * of an XML element.
 *
 * @remarks
 *
 * We deliberately go through the `toString` of the stringification module, which
 * gives out `null` for a literal it does not know, and not through its `mustToString`,
 * which throws an error of its own. An instance carrying a literal outside its
 * enumeration is exactly the kind of failure this module reports with a path.
 */
function writeEnumerationContent<T>(
{I}parts: Array<string>,
{I}value: T,
{I}enumerationName: string,
{I}toString: (value: T) => string | null
): void {{
{I}const text = toString(value);
{I}if (text === null) {{
{II}throw new SerializationError(
{III}`Invalid literal of ${{enumerationName}}: ${{value}}`
{II});
{I}}}

{I}parts.push(escapeXmlText(text));
}}"""
            ),
        ]
    )

    for primitive_type in intermediate.PrimitiveType:
        blocks.append(_generate_write_content_for_primitive_type(primitive_type))

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
 * @throws {{@link SerializationError}} if `that` can not be serialized, *e.g.*, if
 * a property expected to be an integer holds a fractional number
 */
export function toXmlString(that: AasTypes.Class): string {{
{I}const parts = new Array<string>();
{I}writeClass(parts, that);
{I}return parts.join("");
}}"""
            ),
            typescript_common.WARNING,
        ]
    )

    body = "\n\n".join(blocks)

    # NOTE (mristin):
    # The head is composed last, since the imports are read off the body.
    head = [
        Stripped(
            """\
/**
 * Provide de/serialization of AAS classes to/from XML.
 *
 * The implementation is incremental and follows a SAX-style parsing approach.
 *
 * @remarks
 *
 * The primitives which every reader and writer of XML shares -- the cursor, the
 * checks of the namespace and the consumption of the tags -- live in
 * the `xmlcommon` module, and so do the error classes and the path, which this
 * module re-exports so that they stay where a caller has always found them.
 */"""
        ),
        typescript_common.WARNING,
        _generate_imports(body=body),
        Stripped(
            """\
export {
  DeserializationError,
  ElementSegment,
  IndexSegment,
  KeySegment,
  Path,
  SerializationError
} from "./xmlcommon";
export type { Segment } from "./xmlcommon";"""
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    for block in head:
        writer.write(block)
        writer.write("\n\n")

    writer.write(body)
    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert __doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
