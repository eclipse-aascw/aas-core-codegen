"""Generate code for XML de/serialization."""

import io
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
    INDENT5 as IIIII,
)


# region De-serialization


_CONTENT_PARSER_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: Identifier("parseBooleanContent"),
    intermediate.PrimitiveType.INT: Identifier("parseIntegerContent"),
    intermediate.PrimitiveType.FLOAT: Identifier("parseFloatContent"),
    intermediate.PrimitiveType.STR: Identifier("parseStringContent"),
    intermediate.PrimitiveType.BYTEARRAY: Identifier("parseBase64EncodedBytesContent"),
}

#: Moniker of a primitive type, for the name of a composed parser, see
#: :py:func:`_atomic_moniker`
_MONIKER_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: Identifier("Bool"),
    intermediate.PrimitiveType.INT: Identifier("Int"),
    intermediate.PrimitiveType.FLOAT: Identifier("Float"),
    intermediate.PrimitiveType.STR: Identifier("Str"),
    intermediate.PrimitiveType.BYTEARRAY: Identifier("Bytes"),
}


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
    function_name = _CONTENT_PARSER_BY_PRIMITIVE_TYPE[primitive_type]

    if primitive_type is intermediate.PrimitiveType.BOOL:
        return Stripped(
            f"""\
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<boolean, DeserializationError> {{
{I}const text = parseTextContent(cursor);

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
{I}const text = parseTextContent(cursor);

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
function {function_name}(
{I}cursor: XmlCursor
): AasCommon.Either<number, DeserializationError> {{
{I}const text = parseTextContent(cursor);

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
{I}const decodedOrError = AasCommon.base64Decode(parseTextContent(cursor));
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


#: Maximum length of a line of the generated code, in columns
#:
#: This is deliberately well above the ``printWidth`` of 88 which the Prettier
#: configuration sets. The consuming project runs Prettier over the generated code,
#: so neither spelling is the "wrong" one, and this is only about keeping what we
#: record readable: breaking a call of three short arguments over five lines costs far
#: more, at the hundreds of property sites, than the long line saves.
_MAX_LINE_LENGTH = 100


def _join_call_arguments(
    callee: str, arguments: Sequence[str], columns: int
) -> Stripped:
    """
    Render the call to the ``callee`` with the ``arguments``.

    The ``callee`` is the whole expression in front of the parenthesis, so it carries
    the explicit type arguments of a generic function as well. The ``columns`` are
    the columns already taken on the line before the call -- the indention plus
    whatever precedes it, such as ``return ``. The arguments go on the same line as
    the ``callee`` if the call fits in :py:attr:`_MAX_LINE_LENGTH` columns, and one
    argument per line otherwise.
    """
    joined = ", ".join(arguments)

    if columns + len(callee) + len("(") + len(joined) + len(");") <= _MAX_LINE_LENGTH:
        return Stripped(f"{callee}({joined})")

    arguments_joined = ",\n".join(f"{I}{argument}" for argument in arguments)
    return Stripped(
        f"""\
{callee}(
{arguments_joined}
)"""
    )


def _content_parser_name_for_enumeration(
    enumeration: intermediate.Enumeration,
) -> Identifier:
    """Give out the name of the parser of an ``enumeration`` literal."""
    return typescript_naming.function_name(
        Identifier(f"parse_{enumeration.name}_content")
    )


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


def _type_name_of_our_type(our_type: intermediate.OurType) -> Identifier:
    """Give out the TypeScript type which the parser of ``our_type`` gives out."""
    if isinstance(our_type, intermediate.Enumeration):
        return typescript_naming.enum_name(our_type.name)

    elif isinstance(our_type, intermediate.AbstractClass):
        return typescript_naming.interface_name(our_type.name)

    elif isinstance(our_type, intermediate.ConcreteClass):
        return typescript_naming.class_name(our_type.name)

    elif isinstance(our_type, intermediate.NamedUnion):
        return typescript_naming.union_name(our_type.name)

    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        raise AssertionError("Expected to handle this case before")

    else:
        assert_never(our_type)

    raise AssertionError("Should not have gotten here")


def _atomic_moniker(type_annotation: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Determine the moniker of the atomic ``type_annotation``.

    The monikers are the parts out of which we build the names of the composed
    parsers. A moniker never contains an underscore -- a TypeScript type name is
    camel-cased -- so a name whose parts are separated by an underscore can always
    be split back into its parts. The arity is spelled out in a tuple's name for
    the same reason. The names are thus unique by construction, and we need no check
    for collisions.
    """
    primitive_type = intermediate.try_primitive_type(type_annotation)
    if primitive_type is not None:
        return _MONIKER_BY_PRIMITIVE_TYPE[primitive_type]

    assert isinstance(
        type_annotation, intermediate.OurTypeAnnotation
    ), f"Expected an atomic type annotation, but got: {type_annotation}"

    return _type_name_of_our_type(type_annotation.our_type)


def _is_dispatched(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether a value of ``type_anno`` is parsed by dispatching on the local name
    of its XML element.

    This is the case for an abstract class, for a concrete class with concrete
    descendants, and for a named union -- none of them prescribes the element tag,
    so the tag is what tells us which parser to use.
    """
    if not isinstance(type_anno, intermediate.OurTypeAnnotation):
        return False

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.NamedUnion):
        return True

    if isinstance(our_type, intermediate.AbstractClass):
        return True

    if isinstance(our_type, intermediate.ConcreteClass):
        return len(our_type.concrete_descendants) > 0

    return False


def _dispatch_parse_function_name(
    type_anno: intermediate.OurTypeAnnotation,
) -> Identifier:
    """Give out the dispatching parser of ``type_anno``, see :py:func:`_is_dispatched`."""
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
    ``dispatchParse{X}Element`` reads whole.

    This is a pure function of its argument. The code of the parsers which have to be
    composed is generated by :py:class:`_ParserRegistry`.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return _CONTENT_PARSER_BY_PRIMITIVE_TYPE[primitive_type]

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("Expected to handle this case before")

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return _content_parser_name_for_enumeration(our_type)

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            if _is_dispatched(type_anno):
                return _dispatch_parse_function_name(type_anno)

            assert isinstance(our_type, intermediate.ConcreteClass), (
                f"Unexpected abstract class with no concrete "
                f"descendants: {our_type.name!r}"
            )

            return _parse_sequence_function_name_for_concrete_class(cls=our_type)

        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        moniker = _atomic_moniker(intermediate.beneath_optional(type_anno.items))
        return Identifier(f"parseListOf{moniker}Content")

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        monikers = [_atomic_moniker(item) for item in type_anno.items]
        return Identifier(
            f"parseTuple{len(type_anno.items)}Of" + "_".join(monikers) + "Content"
        )

    else:
        assert_never(type_anno)

    raise AssertionError("Should not have gotten here")


def _element_parser_name(
    type_anno: intermediate.AtomicTypeAnnotation, tag_suffix: str
) -> Identifier:
    """
    Give out the parser of a whole XML element, the tags included, holding a value of
    the ``type_anno``.

    This is what an item of a list or of a tuple is parsed with. A dispatched value
    picks the tag from its own model type, so it needs no name and no generated
    parser; everything else sits in an element tagged ``v``, ``v1``, ``v2``, *etc.*,
    prescribed by the position, which the ``tag_suffix`` gives.
    """
    if _is_dispatched(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)
        return _dispatch_parse_function_name(type_anno)

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.ConcreteClass
    ):
        cls_name = typescript_naming.class_name(type_anno.our_type.name)
        return Identifier(f"parse{cls_name}Element")

    moniker = _atomic_moniker(type_anno)
    return Identifier(f"parse{moniker}V{tag_suffix}Element")


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
        if _is_dispatched(type_anno):
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

        call = _join_call_arguments(
            "parseNamedElement",
            ["cursor", tag_literal, _content_parser_name(type_anno)],
            columns=len(I) + len("return "),
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
        call = _join_call_arguments(
            f"parseList<{item_type}>",
            ["cursor", _element_parser_name(items_type_anno, tag_suffix="")],
            columns=len(I) + len("return "),
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

        call = _join_call_arguments(
            f"parseTuple{arity}<{item_types_joined}>",
            ["cursor"] + parse_items,
            columns=len(I) + len("return "),
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
    del cls  # only used for the pre-condition

    xml_name_literal = typescript_common.string_literal(prop.xml_name)

    # NOTE (mristin):
    # A case sits two levels below the ``switch``, which the class's parser indents by
    # three, so the body of a case lands on the fourth level.
    call = _join_call_arguments(
        "parseElementContent",
        ["cursor", "propertyLocalName", _content_parser_name(prop.type_annotation)],
        columns=len(IIII) + len("const parsed = "),
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
    """
    call = _join_call_arguments(
        "dispatchParseElement",
        ["cursor", typescript_common.string_literal(expected_name), map_name],
        columns=len(I) + len("return "),
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

        # NOTE (mristin):
        # A class or a named union is never serialized as an atomic text
        # value -- it always writes its own element, tagged either with the
        # property's name (statically known concrete type) or with its own
        # runtime class name (polymorphic dispatch), see
        # :py:func:`_generate_serialize_block_for_property`.
        assert not isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
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
            type_anno.our_type, intermediate.NamedUnion
        ):
            # NOTE (mristin):
            # A named union always writes its own element, self-tagged with
            # the runtime class's own name, exactly as we do for a
            # polymorphic class property.
            body = Stripped(
                f"""\
parts.push(openTag({xml_name_literal}));
{indent_but_first_line(
    _generate_serialize_class_element(access_expr=access_expr),
    I,
)}
parts.push(closeTag({xml_name_literal}));"""
            )
        elif isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
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
        if isinstance(type_anno.items, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.items.our_type, intermediate.NamedUnion
        ):
            # NOTE (mristin):
            # A named union always writes its own element, self-tagged with
            # the runtime class's own name, exactly as we do for a list of
            # a polymorphic class.
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

        elif isinstance(
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

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_write_stmts = []  # type: List[Stripped]
        for i, item_type_anno in enumerate(type_anno.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, "
                "constrained primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so no "
                "nested optionals, lists or tuples are expected here."
            )

            item_access = Stripped(f"{access_expr}[{i}]")

            if isinstance(
                item_type_anno, intermediate.OurTypeAnnotation
            ) and isinstance(item_type_anno.our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # A named union always writes its own element, self-tagged
                # with the runtime class's own name, exactly as we do for a
                # tuple item of a polymorphic class. We keep this as a
                # branch of its own, separate from the class case below,
                # since a future named union of primitives would need to
                # diverge here.
                item_write_stmts.append(
                    _generate_serialize_class_element(access_expr=item_access)
                )
            elif isinstance(
                item_type_anno, intermediate.OurTypeAnnotation
            ) and isinstance(
                item_type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                item_write_stmts.append(
                    _generate_serialize_class_element(access_expr=item_access)
                )
            else:
                serialize_function = _serialize_function_for_atomic_type(item_type_anno)
                v_name_literal = typescript_common.string_literal(f"v{i + 1}")
                item_write_stmts.append(
                    _generate_serialize_atomic_element(
                        element_name_literal=v_name_literal,
                        serialize_function=serialize_function,
                        access_expr=item_access,
                    )
                )

        item_write_stmts_joined = "\n".join(item_write_stmts)

        body = Stripped(
            f"""\
parts.push(openTag({xml_name_literal}));
{item_write_stmts_joined}
parts.push(closeTag({xml_name_literal}));"""
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

/**
 * Parse a value from `cursor`.
 *
 * Every parser in this module wears this one shape, which is what lets them
 * compose: a parser can be given to another parser without a closure, since
 * everything it needs comes from the `cursor` and from its own definition.
 * The name says what a parser consumes -- a `parse*Content` stops right before
 * the closing tag of the element which the caller has opened, while
 * a `parse*Element` and a `dispatchParse*Element` read an element of their own,
 * its tags included.
 *
 * @typeParam T - type of the parsed value
 */
type ContentParser<T> = (
{I}cursor: XmlCursor
) => AasCommon.Either<T, DeserializationError>;

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
 * Parse the content of the XML element which the caller has opened, and consume
 * the corresponding closing element named `localName`.
 *
 * This is the one thing which every value of an XML element has in common,
 * whatever it holds: the property loop of a class calls it directly, since
 * it has already read the opening tag and switched on its local name, and
 * `parseNamedElement` calls it after reading an opening tag of its own.
 *
 * A property loop assigns *both* halves of the result -- the value as well as
 * the error -- without looking at either first. The loop returns as soon as
 * the error is set, so the `null` value which comes with an error is never
 * read, and the property's variable needs no guard.
 *
 * @param cursor - to read from
 * @param localName - local name of the element which the caller has opened
 * @param parseContent - parses the content of the element
 * @returns parsed value, or an error
 * @typeParam T - type of the parsed value
 */
function parseElementContent<T>(
{I}cursor: XmlCursor,
{I}localName: string,
{I}parseContent: ContentParser<T>
): AasCommon.Either<T, DeserializationError> {{
{I}const parsedOrError = parseContent(cursor);
{I}if (parsedOrError.error !== null) {{
{II}return parsedOrError;
{I}}}

{I}const closeError = consumeCloseTag(cursor, localName);
{I}if (closeError !== null) {{
{II}return new AasCommon.Either<T, DeserializationError>(null, closeError);
{I}}}

{I}return parsedOrError;
}}

/**
 * Read the next XML element from `cursor`, expecting it to be named
 * `expectedLocalName`, parse its content with `parseContent` and consume
 * the matching closing element.
 *
 * This is what an item of a list or of a tuple is parsed with -- a scalar item
 * in an element tagged `"v"`, `"v1"`, `"v2"`, *etc.*, and an item whose concrete
 * class is statically known in an element named after that class. Rejecting
 * an unexpected element on its local name alone spares us parsing its full
 * (possibly deeply nested) content only to discover the mismatch afterwards.
 *
 * @param cursor - to read from
 * @param expectedLocalName - the expected local name of the element
 * @param parseContent - parses the content of the element
 * @returns parsed value, or an error
 * @typeParam T - type of the parsed value
 */
function parseNamedElement<T>(
{I}cursor: XmlCursor,
{I}expectedLocalName: string,
{I}parseContent: ContentParser<T>
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

{I}return parseElementContent(cursor, expectedLocalName, parseContent);
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
{I}parseItem: ContentParser<T>
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
        blocks.append(_generate_serialize_text_as_enumeration(enumeration))

    for arity in intermediate.tuple_arities(symbol_table=symbol_table):
        blocks.append(_generate_parse_tuple_function(arity))

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

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_parse_concrete_class(cls=concrete_cls))

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
            )
        )
        blocks.append(_generate_from_xml_string_for_interface(interface=interface))

    # NOTE (mristin):
    # We keep the named unions' own dispatch functions in a loop of their
    # own, separate from the loop above, since a named union is never
    # a member of ``symbol_table.classes``.
    for named_union in symbol_table.named_unions:
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
