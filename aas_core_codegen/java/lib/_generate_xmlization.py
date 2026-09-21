"""Generate the code for XML de/serialization."""

import io
import textwrap

from typing import Final, List, Mapping, MutableMapping, Optional, Set, Tuple

from icontract import ensure, require

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    assert_never,
    Error,
    Identifier,
    indent_but_first_line,
    Stripped,
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
    INDENT5 as IIIII,
)

# region Generate

# region Names of the generated readers

#: Name the function converting the text content, and the type as it is called
#: in the error messages, for each primitive
_CONTENT_CONVERTER_BY_PRIMITIVE: Final[
    Mapping[intermediate.PrimitiveType, Tuple[str, str]]
] = {
    intermediate.PrimitiveType.BOOL: ("readContentAsBool", "Boolean"),
    intermediate.PrimitiveType.INT: ("readContentAsLong", "Long"),
    intermediate.PrimitiveType.FLOAT: ("readContentAsDouble", "Double"),
    intermediate.PrimitiveType.STR: ("readContentAsString", "String"),
    intermediate.PrimitiveType.BYTEARRAY: (
        "readContentAsBase64",
        "base64-encoded bytes",
    ),
}
assert all(
    primitive_type in _CONTENT_CONVERTER_BY_PRIMITIVE
    for primitive_type in intermediate.PrimitiveType
)

#: Give the value of a primitive read from a self-closing element. A primitive
#: which is absent from this mapping can not be read from one at all.
_EMPTY_VALUE_BY_PRIMITIVE: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.STR: '""',
    intermediate.PrimitiveType.BYTEARRAY: "new byte[0]",
}


def _is_instance_type(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether ``type_anno`` de-serializes from a self-describing element.

    An instance element carries its own type in its local name, whereas
    everything else is read from an element whose name its container supplies.
    """
    return isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    )


def _is_dispatched(our_type: intermediate.OurType) -> bool:
    """
    Check whether an element of ``our_type`` is dispatched on its own name.

    A concrete class without any descendant has a single admissible element
    name, so a property of that type wraps its properties directly. Everything
    else needs the discriminator element nested within the property element.
    """
    if isinstance(our_type, intermediate.NamedUnion):
        return True

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class or a named union, but got: {our_type}"

    return (
        isinstance(our_type, intermediate.AbstractClass)
        or len(our_type.concrete_descendants) > 0
    )


def _from_element_name(our_type: intermediate.OurType) -> Identifier:
    """
    Name the function reading a whole element of ``our_type``.

    Mind that this is *not* the moniker of the type: a concrete class without
    any descendant is referred to by its interface, but reads through
    a function named after the class itself.
    """
    if isinstance(our_type, intermediate.NamedUnion):
        return Identifier(f"read{java_naming.union_name(our_type.name)}FromElement")

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class or a named union, but got: {our_type}"

    if _is_dispatched(our_type):
        return Identifier(f"read{java_naming.interface_name(our_type.name)}FromElement")

    return Identifier(f"read{java_naming.class_name(our_type.name)}FromElement")


def _from_sequence_name(cls: intermediate.ClassUnion) -> Identifier:
    """Name the function reading the properties of ``cls`` from their sequence."""
    return Identifier(f"read{java_naming.class_name(cls.name)}FromSequence")


@require(lambda type_anno: not _is_instance_type(type_anno))
def _content_reader_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """Name the function reading the content of an element as ``type_anno``."""
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation)
    ):
        return Identifier(f"read{java_common.type_moniker(type_anno)}")

    return Identifier(f"readTextAs_{java_common.leaf_moniker(type_anno)}")


@require(lambda v_name: v_name.startswith("v"))
@require(lambda type_anno: not _is_instance_type(type_anno))
def _at_v_reader_name(
    type_anno: intermediate.TypeAnnotationUnion, v_name: str
) -> Identifier:
    """Name the function reading ``type_anno`` from an element called ``v_name``."""
    return Identifier(f"readAtV{v_name[1:]}_{java_common.type_moniker(type_anno)}")


def _element_reader_name(
    type_anno: intermediate.TypeAnnotationUnion, v_name: str
) -> Identifier:
    """
    Name the function reading a single element holding ``type_anno``.

    This is what a list item and a tuple item are read with. An instance reads
    its own, self-describing element, whereas everything else is wrapped in
    an element which the container names -- ``v`` in a list, ``v1``, ``v2``,
    ... by position in a tuple.
    """
    if _is_instance_type(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)
        return _from_element_name(type_anno.our_type)

    return _at_v_reader_name(type_anno, v_name)


# endregion

# region Names of the generated writers


#: Name of the class through which the writing is dispatched. A method
#: reference to one of its static writers has to be qualified by it, exactly
#: as the readers are qualified by ``_DeserializeImplementation``.
_VISITOR_NAME: Final[Identifier] = Identifier("_VisitorWithWriter")


# NOTE (mristin):
# The three functions which follow answer, for a value which is neither
# a list nor a tuple, what writes it and how it is spelled. They dispatch on
# the type annotation and need no notion of their own.
#
# Once a value is at hand, nothing about the writing follows from its declared
# type any more: a scalar is rendered through ``toString``, a byte array
# through base64, an enumeration literal through the text it carries, and
# an instance through the element its run-time type names. Several types
# therefore give the same answer, and that is the whole of what makes a writer
# shared.
#
# The reading can not be shared this way. It has to decide what to construct
# before it has read anything, and only the declared type says what that
# is -- hence one reader per type there, against one writer per answer here.


@ensure(lambda result: "_" not in result)
def _written_leaf_moniker(type_anno: intermediate.AtomicTypeAnnotation) -> str:
    """
    Name what ``type_anno`` is written *as*, for a shared writer to be named after.

    This is the writing counterpart of
    :py:func:`aas_core_codegen.java.common.leaf_moniker`, which names a leaf by
    its very type. Here all four scalars collapse onto ``stringified``, every
    enumeration onto ``IEnum``, every class onto ``IClass`` and every named
    union onto ``IUnion``, so that the writers of a list of any scalar, of any
    enumeration, of any class or of any union are one apiece.

    ``IClass``, ``IEnum`` and ``IUnion`` are the fixed names of our own
    interfaces and are never generated from the meta-model, and ``stringified``
    and ``bytes`` are lower-case (see
    :py:attr:`aas_core_codegen.java.common.PRIMITIVE_TYPE_TO_MONIKER`), so none
    of them can be confused with the moniker of one of our types. None contains
    an underscore, as the moniker grammar requires (see
    :py:func:`aas_core_codegen.java.common.list_moniker`).
    """
    primitive_type = intermediate.try_primitive_type(type_anno)

    if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return "bytes"

    if primitive_type is not None:
        return "stringified"

    # NOTE (mristin):
    # A JSON-able value is written by its own writer, and the three shapes do
    # *not* collapse onto one: an array writes a ``<data>`` and an object
    # a run of ``<member>``, which are different documents.
    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return "jsonValue"

    if isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return "jsonArray"

    if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        return "jsonObject"

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Expected a primitive, a constrained primitive or one of our types, but got: {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return "IEnum"

    if isinstance(our_type, intermediate.NamedUnion):
        return "IUnion"

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Expected a class, but got: {our_type}"

    return "IClass"


def _written_value_type(type_anno: intermediate.AtomicTypeAnnotation) -> Stripped:
    """
    Render the type of a value of ``type_anno`` as its writer takes it.

    Everything widens to what it is written through: a scalar to ``Object``,
    whose ``toString`` renders it, and an instance to the interface over which
    the writing dispatches, so that one writer serves them all.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)

    if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Stripped("byte[]")

    if primitive_type is not None:
        return Stripped("Object")

    # NOTE (mristin):
    # A JSON-able value widens to nothing: its writer takes the very Jackson
    # node which the property holds, and the three shapes have three writers
    # of their own, unlike the classes, which share one.
    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return java_common.generate_type(type_anno)

    moniker = _written_leaf_moniker(type_anno)

    # NOTE (mristin):
    # ``IUnion`` is generic in the union's own type, which is exactly what we
    # are widening away here, so the wildcard stands for it.
    return Stripped("IUnion<?>" if moniker == "IUnion" else moniker)


def _item_type_annotations(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> List[intermediate.AtomicTypeAnnotation]:
    """
    Give the items of the list or of the tuple ``type_anno``, in order.

    An item is atomic, which
    :py:func:`aas_core_codegen.intermediate._translate._verify_only_simple_type_patterns`
    guarantees for a tuple and which the code generators assume for a list. We
    narrow it here, once, so that everything downstream can simply say so in
    its signature.
    """
    items = (
        [type_anno.items]
        if isinstance(type_anno, intermediate.ListTypeAnnotation)
        else list(type_anno.items)
    )

    result = []  # type: List[intermediate.AtomicTypeAnnotation]
    for item in items:
        assert isinstance(item, intermediate.AtomicTypeAnnotationAsTuple), (
            f"We only support lists and tuples of atomic values (primitives, "
            f"constrained primitives, enumeration literals), of classes or of "
            f"named unions when de/serializing to XML, but got the nested "
            f"type {item}. Please contact the developers if you need this "
            f"feature."
        )
        result.append(item)

    return result


def _as_sequence_name(cls: intermediate.ConcreteClass) -> Identifier:
    """Name the function writing the properties of ``cls`` as their sequence."""
    return Identifier(f"write{java_naming.class_name(cls.name)}AsSequence")


@require(lambda type_anno: not _is_instance_type(type_anno))
def _content_writer_name(type_anno: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Name the function writing ``type_anno`` as the content of an element.

    Only a list and a tuple have something of their own to write, and hence
    get a function each; every leaf is written by the shared writer of what it
    is written as. Either way the name follows that and not the type, so one
    function serves every type which is written the same way -- see
    :py:func:`_written_leaf_moniker`.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        moniker = _written_leaf_moniker(_item_type_annotations(type_anno)[0])
        return Identifier(f"write{java_common.list_moniker(moniker)}")

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        monikers = [
            _written_leaf_moniker(item_type_anno)
            for item_type_anno in _item_type_annotations(type_anno)
        ]
        return Identifier(f"write{java_common.tuple_moniker(monikers)}")

    assert isinstance(
        type_anno, intermediate.AtomicTypeAnnotationAsTuple
    ), f"Expected an atomic type annotation, but got: {type_anno}"

    primitive_type = intermediate.try_primitive_type(type_anno)

    if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Identifier("writeByteArrayContent")

    # NOTE (mristin):
    # A double can not go through ``toString``: that renders an infinity as
    # ``Infinity``, which is not a valid ``xs:double``.
    if primitive_type is intermediate.PrimitiveType.FLOAT:
        return Identifier("writeDoubleContent")

    if primitive_type is not None:
        return Identifier("writeStringifiedContent")

    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return Identifier("writeJsonValueContent")

    if isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return Identifier("writeJsonArrayContent")

    if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        return Identifier("writeJsonObjectContent")

    assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    ), f"Expected an enumeration, but got: {type_anno}"

    return Identifier("writeEnum")


@require(lambda v_name: v_name.startswith("v"))
@require(lambda type_anno: not _is_instance_type(type_anno))
def _at_v_writer_name(
    type_anno: intermediate.AtomicTypeAnnotation, v_name: str
) -> Identifier:
    """Name the function writing ``type_anno`` as an element called ``v_name``."""
    return Identifier(f"writeAtV{v_name[1:]}_{_written_leaf_moniker(type_anno)}")


def _element_writer_name(
    type_anno: intermediate.AtomicTypeAnnotation, v_name: str
) -> Identifier:
    """
    Name the function writing a single element holding ``type_anno``.

    This is what a list item and a tuple item are written with. An instance
    writes its own, self-describing element, whereas everything else is
    wrapped in an element which the container names -- ``v`` in a list,
    ``v1``, ``v2``, ... by position in a tuple.

    Unlike :py:func:`_element_reader_name`, an instance needs no writer per
    class: the element follows from the run-time type of the value, which
    a single virtual call answers for every class at once.
    """
    if _is_instance_type(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)

        if isinstance(type_anno.our_type, intermediate.NamedUnion):
            return Identifier("writeUnion")

        return Identifier("writeClass")

    return _at_v_writer_name(type_anno, v_name)


def _content_writer_reference(type_anno: intermediate.TypeAnnotationUnion) -> Stripped:
    """
    Reference the writer of ``type_anno`` as the content of a property element.

    A concrete class without any descendant has a single admissible element
    name, so the property element holds its properties directly. Everything
    else which is an instance writes its own discriminator element nested
    within the property element, and hence goes through a dispatching writer.
    """
    name: Identifier

    if _is_instance_type(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.NamedUnion):
            name = Identifier("writeUnion")
        elif _is_dispatched(our_type):
            name = Identifier("writeClass")
        else:
            assert isinstance(our_type, intermediate.ConcreteClass), (
                f"Expected a concrete class without any descendant, "
                f"but got: {our_type}"
            )
            name = _as_sequence_name(our_type)
    else:
        name = _content_writer_name(type_anno)

        # NOTE (mristin):
        # These two write nothing but a text, and the XML-RPC writers need
        # them as well, so they live in ``XmlCommon``.
        if name in (
            Identifier("writeStringifiedContent"),
            Identifier("writeDoubleContent"),
        ):
            return Stripped(f"XmlCommon::{name}")

    return Stripped(f"{_VISITOR_NAME}::{name}")


# endregion


# region Gating


class _Needed:
    """Track which shared helpers, readers and writers the meta-model reaches."""

    def __init__(self) -> None:
        """Initialize with nothing needed."""
        self.primitive_types = set()  # type: Set[intermediate.PrimitiveType]
        self.enumerations = False
        self.lists = False
        self.nested_elements = False

        #: Content readers to emit, keyed and de-duplicated by the moniker
        self.content_readers = (
            dict()
        )  # type: MutableMapping[str, intermediate.TypeAnnotationUnion]

        #: Positional item readers to emit, keyed by their function name
        self.at_v_readers = (
            dict()
        )  # type: MutableMapping[str, Tuple[intermediate.TypeAnnotationUnion, str]]

        # NOTE (mristin):
        # The writers are collected separately from the readers, although both
        # are reached by the very same walk. A writer is named after what it
        # writes and not after the type (see
        # :py:func:`_written_leaf_moniker`), so several types collapse onto one
        # writer where each of them still needs a reader of its own. The
        # annotation kept here is therefore only the first representative
        # registered for that name -- everything the writer is generated from
        # is derived from the moniker it is named after.

        #: Content writers to emit, keyed by their function name
        self.content_writers = (
            dict()
        )  # type: MutableMapping[str, intermediate.ContainerTypeAnnotation]

        #: Positional item writers to emit, keyed by their function name
        self.at_v_writers = (
            dict()
        )  # type: MutableMapping[str, Tuple[intermediate.AtomicTypeAnnotation, str]]

        #: Shared content writers which something calls, be it for
        #: a property, for a list item or for a tuple item
        self.called_content_writers = set()  # type: Set[Identifier]


def _collect_needed(symbol_table: intermediate.SymbolTable) -> _Needed:
    """
    Determine which shared helpers, readers and writers have to be generated.

    The pass recurses into the items of a list and of a tuple: an item is
    de/serialized by the same functions, only one nesting level deeper, and
    the function it needs may occur nowhere else in the model. Without
    the recursion, a model whose only ``str`` sits in a ``List[List[str]]``
    would emit a reader composed of helpers which were never generated.

    One walk answers for both directions, since the reading and the writing
    reach a value over the very same path. What they need at the end of that
    path differs, though: a reader per type against a writer per answer (see
    :py:func:`_written_leaf_moniker`), so the two are collected side by side.

    A step is taken at most once per type, which is what the reader
    de-duplication keys on. That is never too coarse for the writers: every
    writer key is derived from the type reached, so a type seen twice yields
    the very same keys, and two types which share a writer are each still
    walked, as their reader keys differ.

    Only the properties of the concrete classes matter, as they are the only
    thing de/serialized as a sequence of XML elements.
    """
    needed = _Needed()

    def register_item(
        type_anno: intermediate.AtomicTypeAnnotation, v_name: str
    ) -> None:
        """Register the de/serialization of a single element of ``type_anno``."""
        if _is_instance_type(type_anno):
            # NOTE (mristin):
            # An instance de/serializes its own, self-describing element, so
            # it needs neither a positional nor a content function.
            return

        register_content(type_anno)

        reader_name = _at_v_reader_name(type_anno, v_name)
        if reader_name not in needed.at_v_readers:
            needed.at_v_readers[reader_name] = (type_anno, v_name)

        writer_name = _at_v_writer_name(type_anno, v_name)
        if writer_name not in needed.at_v_writers:
            needed.at_v_writers[writer_name] = (type_anno, v_name)

    @require(lambda type_anno: not _is_instance_type(type_anno))
    def register_content(type_anno: intermediate.TypeAnnotationUnion) -> None:
        """Register the de/serialization of the content of an element."""
        moniker = java_common.type_moniker(type_anno)
        if moniker in needed.content_readers:
            return

        if isinstance(
            type_anno,
            (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
        ):
            writer_name = _content_writer_name(type_anno)
            if writer_name not in needed.content_writers:
                needed.content_writers[writer_name] = type_anno

            item_type_annos = _item_type_annotations(type_anno)

            if isinstance(type_anno, intermediate.ListTypeAnnotation):
                needed.lists = True
                register_item(item_type_annos[0], "v")
            else:
                for i, item_type_anno in enumerate(item_type_annos):
                    register_item(item_type_anno, f"v{i + 1}")
        else:
            assert isinstance(
                type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), f"Expected an atomic type annotation, but got: {type_anno}"

            needed.called_content_writers.add(_content_writer_name(type_anno))

            primitive_type = intermediate.try_primitive_type(type_anno)
            if primitive_type is not None:
                needed.primitive_types.add(primitive_type)
            elif isinstance(
                type_anno,
                (
                    intermediate.JsonValueTypeAnnotation,
                    intermediate.JsonArrayTypeAnnotation,
                    intermediate.JsonObjectTypeAnnotation,
                ),
            ):
                # NOTE (mristin):
                # The XML-RPC de/serialization is emitted whenever the model
                # uses a JSON-able type at all, so there is nothing to register
                # per shape here. A ``<boolean>``, a ``<name>`` and a
                # ``<string>`` are all written through
                # ``writeStringifiedContent``, though, which is otherwise
                # emitted only for a scalar.
                needed.primitive_types.add(intermediate.PrimitiveType.STR)
                needed.called_content_writers.add(Identifier("writeStringifiedContent"))
            else:
                assert isinstance(type_anno, intermediate.OurTypeAnnotation) and (
                    isinstance(type_anno.our_type, intermediate.Enumeration)
                ), f"Expected an enumeration, but got: {type_anno}"

                needed.enumerations = True

                # NOTE (mristin):
                # ``readEnum`` is built on the text path. ``writeEnum`` is
                # not -- a literal carries its own text -- so the writing
                # needs no ``writeStringifiedContent`` on the account of
                # an enumeration.
                needed.primitive_types.add(intermediate.PrimitiveType.STR)

        needed.content_readers[moniker] = type_anno

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if _is_instance_type(type_anno):
                assert isinstance(type_anno, intermediate.OurTypeAnnotation)
                if _is_dispatched(type_anno.our_type):
                    needed.nested_elements = True
                continue

            register_content(type_anno)

    return needed


@ensure(lambda result: result[0] or not result[1])
def _collect_dispatching_writers(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[bool, bool]:
    """
    Determine which of the two dispatching writers the meta-model reaches.

    Give whether ``writeClass`` and whether ``writeUnion`` have to be
    generated, in that order. The union writer delegates to the class writer,
    so the former can not be needed without the latter.

    The walk has to recurse into the items of a list and of a tuple the same
    way :py:func:`_collect_needed` does, but the position matters here: an
    item is always written as its own, self-describing element, whereas
    a property of a concrete class without any descendant writes its
    properties directly into the property element and needs no dispatch.
    """
    classes = False
    unions = False

    def register(type_anno: intermediate.TypeAnnotationUnion, as_item: bool) -> None:
        """Register what writing ``type_anno`` in its position dispatches to."""
        nonlocal classes
        nonlocal unions

        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            register(type_anno.items, True)
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            for item_type_anno in type_anno.items:
                register(item_type_anno, True)
        elif _is_instance_type(type_anno):
            assert isinstance(type_anno, intermediate.OurTypeAnnotation)

            if isinstance(type_anno.our_type, intermediate.NamedUnion):
                unions = True
                classes = True
            elif as_item or _is_dispatched(type_anno.our_type):
                classes = True
        else:
            # NOTE (mristin):
            # A primitive and an enumeration literal are written as text, so
            # there is nothing to dispatch on.
            pass

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            register(intermediate.beneath_optional(prop.type_annotation), False)

    return classes, unions


# endregion

# region Shared helpers


def _generate_skip_start_document() -> Stripped:
    """Generate the function to skip start document."""
    return Stripped(
        f"""\
private static void skipStartDocument(XMLEventReader reader){{
{I}if (XmlCommon.currentEvent(reader).isStartDocument()){{
{II}reader.next();
{I}}}
}}"""
    )


_CONTENT_CONVERTER_BODY_BY_PRIMITIVE: Final[
    Mapping[intermediate.PrimitiveType, Stripped]
] = {
    intermediate.PrimitiveType.STR: Stripped(
        f"""\
private static String readContentAsString(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}return content.toString();
}}"""
    ),
    intermediate.PrimitiveType.BOOL: Stripped(
        f"""\
private static Boolean readContentAsBool(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}
{I}final String text = XmlCommon.collapseWhitespace(content.toString());

{I}// NOTE (mristin):
{I}// ``xs:boolean`` spells the two values in four ways, not two, so ``1`` and
{I}// ``0`` have to be read as well. Boolean.valueOf is of no use here: it
{I}// answers ``false`` to anything which is not ``true``, so it would take
{I}// ``0`` and ``banana`` alike, and silently.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#boolean
{I}if (text.equals("true") || text.equals("1")) {{
{II}return Boolean.TRUE;
{I}}}

{I}if (text.equals("false") || text.equals("0")) {{
{II}return Boolean.FALSE;
{I}}}

{I}throw new IllegalStateException(
{II}"Expected a value as xs:boolean, but got: " + text);
}}"""
    ),
    intermediate.PrimitiveType.INT: Stripped(
        f"""\
private static Long readContentAsLong(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}return Long.valueOf(XmlCommon.collapseWhitespace(content.toString()));
}}"""
    ),
    intermediate.PrimitiveType.FLOAT: Stripped(
        f"""\
/**
 * Match the lexical space of {{@code xs:double}}.
 *
 * <p>See: https://www.w3.org/TR/xmlschema-2/#double
 */
private static final Pattern XS_DOUBLE_PATTERN = Pattern.compile(
{I}"^((\\\\+|-)?([0-9]+(\\\\.[0-9]*)?|\\\\.[0-9]+)([Ee](\\\\+|-)?[0-9]+)?"
{II}+ "|-?INF|NaN)$");

private static Double readContentAsDouble(XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();

{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}final String text = XmlCommon.collapseWhitespace(content.toString());

{I}// NOTE (mristin):
{I}// The two infinities have to be spelled out: Double.valueOf refuses
{I}// ``INF`` and ``-INF``, which is exactly what ``xs:double`` calls them.
{I}// NOTE (mristin):
{I}// ``+INF`` is read although it is written as ``INF``: XSD 1.1 admits it,
{I}// its production being ``(\\+|-)?INF``, and being liberal in what we
{I}// accept costs nothing here.
{I}if (text.equals("INF") || text.equals("+INF")) {{
{II}return Double.POSITIVE_INFINITY;
{I}}}

{I}if (text.equals("-INF")) {{
{II}return Double.NEGATIVE_INFINITY;
{I}}}

{I}// NOTE (mristin):
{I}// Double.valueOf is in the other direction far too permissive: it accepts
{I}// ``Infinity``, a trailing type suffix as in ``1.0d``, a hexadecimal
{I}// significand as in ``0x1p3``, and surrounding whitespace, none of which
{I}// is a valid ``xs:double``. The pattern is therefore checked first.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#double
{I}if (!XS_DOUBLE_PATTERN.matcher(text).matches()) {{
{II}throw new NumberFormatException(
{III}"Expected a value as xs:double, but got: " + text);
{I}}}

{I}return Double.valueOf(text);
}}"""
    ),
    intermediate.PrimitiveType.BYTEARRAY: Stripped(
        f"""\
/**
 * Read the whole content of an element into memory.
 */
private static byte[] readContentAsBase64(
{I}XMLEventReader reader) throws XMLStreamException {{
{I}final StringBuilder content = new StringBuilder();
{I}while (reader.peek().isCharacters() || reader.peek().getEventType() == XMLStreamConstants.COMMENT) {{
{II}if (reader.peek().isCharacters()) {{
{III}content.append(reader.peek().asCharacters().getData());
{II}}}
{II}reader.nextEvent();
{I}}}

{I}// NOTE (mristin):
{I}// ``xs:base64Binary`` allows whitespace *between* the characters, not only
{I}// around them -- its grammar admits a space after every one -- while
{I}// Base64.getDecoder() refuses all of it. So every whitespace character is
{I}// dropped, and not merely collapsed.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#base64Binary
{I}String encodedData = removeWhitespace(content.toString());

{I}if (!matchesXsBase64Binary(encodedData)) {{
{II}throw new XMLStreamException(
{III}"Expected a text as base64-encoded bytes, but got: " + encodedData);
{I}}}
{I}final byte[] decodedData;
{I}Base64.Decoder decoder = Base64.getDecoder();

{I}try {{
{II}decodedData = decoder.decode(encodedData);
{I}}} catch (IllegalArgumentException exception) {{
{II}throw new XMLStreamException(
{III}"Failed to read base64 encoded data: " +
{III}exception.getMessage());
{I}}}

{I}return decodedData;
}}"""
    ),
}
assert all(
    primitive_type in _CONTENT_CONVERTER_BODY_BY_PRIMITIVE
    for primitive_type in intermediate.PrimitiveType
)


_COLLAPSE_WHITESPACE = Stripped(
    f"""\
/**
 * Normalize {{@code text}} the way {{@code whiteSpace="collapse"}} prescribes.
 *
 * <p>Every atomic XSD type except a string, and every type derived from one
 * by restriction, fixes {{@code whiteSpace}} to {{@code collapse}}, and
 * a schema author can not change it. A tab, a line feed and a carriage
 * return each become a space, a run of spaces becomes one space, and
 * the leading and trailing spaces go. Only the result of that is a lexical
 * representation to be matched.
 *
 * <p>Mind that this strips only the whitespace <i>around</i> the value:
 * a space within it survives as a single space, so {{@code 2  3}} becomes
 * {{@code 2 3}}, which is still no number.
 *
 * <p>See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace
 */
private static String collapseWhitespace(String text) {{
{I}return XmlCommon.WHITESPACE_RUN.matcher(text).replaceAll(" ").trim();
}}"""
)

_MATCHES_XS_BASE64_BINARY = Stripped(
    f"""\
/**
 * Tell whether {{@code text}} is a lexical form of {{@code xs:base64Binary}}.
 *
 * <p>The whitespace is expected to be gone already. What is left has to match
 * {{@code (B64 B64 B64 B64)* ((B64 B64 B64 B64) | (B64 B64 B16 '=')
 * | (B64 B04 '=='))?}} -- a length which is a multiple of four,
 * the alphabet and nothing else, an equals sign only at the very end, and,
 * easily missed, a constrained character <i>before</i> the padding, as
 * the bits which the padding drops have to be zero.
 *
 * <p>The decoders do not agree on any of this. Base64.getDecoder() reads
 * {{@code SGk}} although it is three characters long, where the Go and
 * the Python SDKs refuse it. Hence this check, so that every target refuses
 * the same texts.
 *
 * <p>See: https://www.w3.org/TR/xmlschema-2/#base64Binary
 */
private static boolean matchesXsBase64Binary(String text) {{
{I}if (text.length() % 4 != 0) {{
{II}return false;
{I}}}

{I}if (text.isEmpty()) {{
{II}return true;
{I}}}

{I}int pads = 0;
{I}if (text.charAt(text.length() - 1) == '=') {{
{II}pads = 1;
{II}if (text.charAt(text.length() - 2) == '=') {{
{III}pads = 2;
{II}}}
{I}}}

{I}for (int i = 0; i < text.length() - pads; i++) {{
{II}final char character = text.charAt(i);
{II}final boolean inAlphabet =
{III}(character >= 'A' && character <= 'Z')
{IIII}|| (character >= 'a' && character <= 'z')
{IIII}|| (character >= '0' && character <= '9')
{IIII}|| character == '+'
{IIII}|| character == '/';
{II}if (!inAlphabet) {{
{III}return false;
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// Only these sixteen characters leave the two dropped bits at zero, and
{I}// only these four leave the four dropped bits at zero.
{I}if (pads == 1) {{
{II}return "AEIMQUYcgkosw048".indexOf(text.charAt(text.length() - 2)) >= 0;
{I}}}

{I}if (pads == 2) {{
{II}return "AQgw".indexOf(text.charAt(text.length() - 3)) >= 0;
{I}}}

{I}return true;
}}"""
)

_REMOVE_WHITESPACE = Stripped(
    f"""\
/**
 * Drop every whitespace character of {{@code text}}.
 *
 * <p>This is what {{@code xs:base64Binary}} needs: it allows whitespace
 * between the characters and not only around them, so collapsing is not
 * enough -- the decoder accepts none of it.
 */
private static String removeWhitespace(String text) {{
{I}return XmlCommon.WHITESPACE_RUN.matcher(text).replaceAll("");
}}"""
)

_WHITESPACE_RUN = Stripped(
    """\
/**
 * Match a run of the four characters which XML calls whitespace.
 */
private static final Pattern WHITESPACE_RUN = Pattern.compile("[ \\t\\n\\r]+");"""
)


def _generate_content_converters(
    primitive_types: Set[intermediate.PrimitiveType],
) -> List[Stripped]:
    """Generate the functions converting the text content of an element."""
    # NOTE (mristin):
    # ``readContentAsString`` and the collapsing live in ``XmlCommon``, as
    # the XML-RPC module needs them whatever this meta-model uses.
    result = [
        _CONTENT_CONVERTER_BODY_BY_PRIMITIVE[primitive_type]
        for primitive_type in intermediate.PrimitiveType
        if primitive_type in primitive_types
        and primitive_type is not intermediate.PrimitiveType.STR
    ]

    # NOTE (mristin):
    # Only a byte array asks for a helper of its own here. The collapsing
    # lives in ``XmlCommon``, which generates it for every model, as
    # the XML-RPC module collapses the text of a ``<boolean>`` and of
    # a ``<double>`` whatever this meta-model happens to use.
    needs_removal = intermediate.PrimitiveType.BYTEARRAY in primitive_types

    if needs_removal:
        result.insert(0, _REMOVE_WHITESPACE)
        result.insert(1, _MATCHES_XS_BASE64_BINARY)

    return result


def _generate_reader_interfaces() -> Stripped:
    """Generate the shape of a converter of an element's text."""
    return Stripped(
        f"""\
/**
 * Convert the text content of an element which has already been opened.
 */
@FunctionalInterface
private interface ContentConverter<T> {{
{I}T convert(XMLEventReader reader) throws XMLStreamException;
}}"""
    )


def _generate_read_text(
    primitive_types: Set[intermediate.PrimitiveType],
) -> List[Stripped]:
    """Generate the readers of the text content of an element."""
    result = [
        Stripped(
            f"""\
/**
 * Read the text content of an element and convert it with
 * {{@code convert}}.
 *
 * <p>A self-closing element is an error, since there is no text to convert.
 */
private static <T> Reporting.Result<T> readText(
{I}XMLEventReader reader,
{I}boolean isEmpty,
{I}ContentConverter<T> convert,
{I}String typeName) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML content representing " + typeName +
{III}", but encountered a self-closing element"));
{I}}}

{I}if (XmlCommon.currentEvent(reader).isEndDocument()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"Expected an XML content representing " + typeName +
{III}", but reached the end-of-file"));
{I}}}

{I}try {{
{II}return Reporting.Result.success(convert.convert(reader));
{I}}} catch (Exception exception) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"The XML content could not be de-serialized as " + typeName + ": " +
{III}exception.getMessage()));
{I}}}
}}"""
        )
    ]  # type: List[Stripped]

    if (
        intermediate.PrimitiveType.STR in primitive_types
        or intermediate.PrimitiveType.BYTEARRAY in primitive_types
    ):
        result.append(
            Stripped(
                f"""\
/**
 * Read the text content of an element and convert it with
 * {{@code convert}}, giving {{@code whenEmpty}} for a self-closing element.
 */
private static <T> Reporting.Result<T> readText(
{I}XMLEventReader reader,
{I}boolean isEmpty,
{I}ContentConverter<T> convert,
{I}String typeName,
{I}T whenEmpty) {{
{I}if (isEmpty) {{
{II}return Reporting.Result.success(whenEmpty);
{I}}}

{I}return readText(reader, isEmpty, convert, typeName);
}}"""
            )
        )

    return result


def _generate_read_enum() -> Stripped:
    """Generate the reader of an enumeration literal."""
    return Stripped(
        f"""\
/**
 * Read the text content of an element and parse it as a literal of
 * the enumeration called {{@code enumName}}.
 */
private static <T> Reporting.Result<T> readEnum(
{I}XMLEventReader reader,
{I}boolean isEmpty,
{I}Function<String, Optional<T>> parseLiteral,
{I}String enumName) {{
{I}final Reporting.Result<String> tryText = readText(
{II}reader, isEmpty, XmlCommon::readContentAsString, enumName);
{I}if (tryText.isError()) {{
{II}return Reporting.Result.failure(tryText.getError());
{I}}}

{I}final Optional<T> literal = parseLiteral.apply(tryText.getResult());
{I}if (!literal.isPresent()) {{
{II}return Reporting.Result.failure(new Reporting.Error(
{III}"The text could not be parsed as a literal of " + enumName + ": " +
{III}tryText.getResult()));
{I}}}

{I}return Reporting.Result.success(literal.get());
}}"""
    )


def _generate_read_list() -> Stripped:
    """Generate the reader of the items of a list."""
    return Stripped(
        f"""\
/**
 * Read the items of a list, each with {{@code readItem}}.
 *
 * <p>Every start element is considered to mark the start of an item. Reading
 * stops as soon as a non-start element is encountered.
 */
private static <T> Reporting.Result<List<T>> readList(
{I}XMLEventReader reader, boolean isEmpty, XmlCommon.ElementReader<T> readItem) {{
{I}final List<T> result = new ArrayList<>();
{I}if (isEmpty) {{
{II}return Reporting.Result.success(result);
{I}}}

{I}XmlCommon.skipWhitespaceAndComments(reader);
{I}int index = 0;
{I}if (!XmlCommon.currentEvent(reader).isStartElement()) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected a start element opening an item of the list, " +
{III}"but got an XML " + XmlCommon.getEventTypeAsString(XmlCommon.currentEvent(reader)));
{II}error.prependSegment(new Reporting.IndexSegment(index));
{II}return Reporting.Result.failure(error);
{I}}}

{I}while (XmlCommon.currentEvent(reader).isStartElement()) {{
{II}final Reporting.Result<? extends T> itemResult = readItem.read(reader);
{II}if (itemResult.isError()) {{
{III}itemResult.getError()
{IIII}.prependSegment(
{IIIII}new Reporting.IndexSegment(index));
{III}return Reporting.Result.failure(itemResult.getError());
{II}}}

{II}result.add(itemResult.getResult());
{II}index++;
{II}XmlCommon.skipWhitespaceAndComments(reader);
{I}}}

{I}return Reporting.Result.success(result);
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_read_tuple_helper(arity: int) -> Stripped:
    """Generate the reader of the items of a tuple of ``arity`` items."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    tuple_type = f"Tuple{arity}<{', '.join(type_params)}>"

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Read a tuple of {arity} item(s), each with the corresponding
 * {{@code readItemI}}.
 */
private static <{", ".join(type_params)}> Reporting.Result<{tuple_type}> readTuple{arity}(
{I}XMLEventReader reader,
{I}boolean isEmpty,
"""
    )

    for i in range(arity):
        writer.write(f"{I}XmlCommon.ElementReader<T{i + 1}> readItem{i + 1}")
        writer.write(",\n" if i < arity - 1 else ") {\n")

    writer.write(
        f"""\
{I}if (isEmpty) {{
{II}final Reporting.Error error = new Reporting.Error(
{III}"Expected exactly {arity} item(s), but got a self-closing element");
{II}return Reporting.Result.failure(error);
{I}}}

"""
    )

    for i in range(arity):
        writer.write(
            f"""\
{I}final Reporting.Result<? extends T{i + 1}> item{i + 1}Result =
{II}readItem{i + 1}.read(reader);
{I}if (item{i + 1}Result.isError()) {{
{II}item{i + 1}Result.getError()
{III}.prependSegment(new Reporting.IndexSegment({i}));
{II}return Reporting.Result.failure(item{i + 1}Result.getError());
{I}}}

"""
        )

    tuple_literal = java_common.generate_tuple_literal(
        item_exprs=[Stripped(f"item{i + 1}Result.getResult()") for i in range(arity)]
    )

    writer.write(
        f"""\
{I}return Reporting.Result.success(
{II}{indent_but_first_line(tuple_literal, II)});
}}"""
    )

    return Stripped(writer.getvalue())


def _generate_at_end_of_sequence() -> Stripped:
    """Generate the predicate telling whether the sequence of properties ended."""
    return Stripped(
        f"""\
/**
 * Check whether the sequence of the properties has ended.
 *
 * <p>Only the end tag of the enclosing element concludes a sequence. Reaching
 * the end-of-file does not -- that is an error, which
 * {{@link #peekElementName}} reports when the caller goes on to read the next
 * property.
 */
private static boolean atEndOfSequence(XMLEventReader reader) {{
{I}XmlCommon.skipWhitespaceAndComments(reader);
{I}return XmlCommon.currentEvent(reader).isEndElement();
}}"""
    )


def _generate_unexpected_property() -> Stripped:
    """Generate the error for a property which the class does not have."""
    return Stripped(
        f"""\
/**
 * Report an element which is not a property of the class {{@code className}}.
 */
private static <T> Reporting.Result<T> unexpectedProperty(
{I}String className, String elementName) {{
{I}return Reporting.Result.failure(new Reporting.Error(
{II}"We expected properties of the class " + className + ", " +
{II}"but got an unexpected element " +
{II}"with the name " + elementName));
}}"""
    )


def _generate_duplicate_property_error() -> Stripped:
    """Generate the error for a property which the sequence gave more than once."""
    return Stripped(
        f"""\
/**
 * Report a property which the sequence of the properties gave more than once.
 */
private static Reporting.Error duplicatePropertyError(String elementName) {{
{I}return new Reporting.Error(
{II}"Property " + elementName + " occurred more than once");
}}"""
    )


def _generate_missing_required_property() -> Stripped:
    """Generate the error for a required property which the sequence omitted."""
    return Stripped(
        f"""\
/**
 * Report a required property of the class {{@code className}} which the
 * sequence of the properties did not give.
 */
private static <T> Reporting.Result<T> missingRequiredProperty(
{I}String propertyName, String className) {{
{I}return Reporting.Result.failure(new Reporting.Error(
{II}"The required property " + propertyName + " has not been given " +
{II}"in the XML representation of an instance of class " + className));
}}"""
    )


# endregion

# region Readers of a single type


def _concrete_from_element_name(cls: intermediate.ConcreteClass) -> Identifier:
    """
    Name the function reading a whole element of the concrete class ``cls``.

    Unlike :py:func:`_from_element_name`, this never dispatches: it is what
    a dispatcher dispatches *to*, so a concrete class which itself has
    descendants must resolve to its own reader here and not back to
    the dispatcher.
    """
    return Identifier(f"read{java_naming.class_name(cls.name)}FromElement")


@require(lambda type_anno: not _is_instance_type(type_anno))
def _generate_content_reader(type_anno: intermediate.TypeAnnotationUnion) -> Stripped:
    """Generate the function reading the content of an element as ``type_anno``."""
    name = _content_reader_name(type_anno)
    value_type = java_common.generate_type(type_anno)

    # NOTE (mristin):
    # A JSON-able value is read over the XML-RPC subset, and those readers
    # already wear the name which ``_content_reader_name`` gives -- see
    # :py:func:`_generate_xml_rpc_readers` -- so there is nothing to generate
    # per type here.
    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return Stripped("")

    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_reader = _element_reader_name(type_anno.items, "v")
        body = Stripped(
            f"""\
return readList(
{I}reader, isEmpty, _DeserializeImplementation::{item_reader});"""
        )
    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_readers = ",\n".join(
            f"_DeserializeImplementation::"
            f"{_element_reader_name(item_type_anno, f'v{i + 1}')}"
            for i, item_type_anno in enumerate(type_anno.items)
        )
        body = Stripped(
            f"""\
return readTuple{len(type_anno.items)}(
{I}reader,
{I}isEmpty,
{I}{indent_but_first_line(item_readers, I)});"""
        )
    else:
        primitive_type = intermediate.try_primitive_type(type_anno)
        if primitive_type is not None:
            converter, display_name = _CONTENT_CONVERTER_BY_PRIMITIVE[primitive_type]
            display_name_literal = java_common.string_literal(display_name)
            empty_value = _EMPTY_VALUE_BY_PRIMITIVE.get(primitive_type, None)

            # NOTE (mristin):
            # The converter of a string lives in ``XmlCommon``, as the XML-RPC
            # module needs it whatever this meta-model uses.
            converter_holder = (
                "XmlCommon"
                if converter == "readContentAsString"
                else "_DeserializeImplementation"
            )

            arguments = [
                Stripped("reader"),
                Stripped("isEmpty"),
                Stripped(f"{converter_holder}::{converter}"),
                Stripped(display_name_literal),
            ]
            if empty_value is not None:
                arguments.append(Stripped(empty_value))

            joined_arguments = ",\n".join(arguments)
            body = Stripped(
                f"""\
return readText(
{I}{indent_but_first_line(joined_arguments, I)});"""
            )
        else:
            assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
                type_anno.our_type, intermediate.Enumeration
            ), f"Expected an enumeration, but got: {type_anno}"

            enum_name = java_naming.enum_name(type_anno.our_type.name)
            from_str_name = java_naming.private_property_name(
                Identifier(f"{type_anno.our_type.name}_from_string")
            )
            enum_name_literal = java_common.string_literal(enum_name)

            body = Stripped(
                f"""\
return readEnum(
{I}reader,
{I}isEmpty,
{I}Stringification::{from_str_name},
{I}{enum_name_literal});"""
            )

    return Stripped(
        f"""\
private static Reporting.Result<{value_type}> {name}(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


@require(lambda type_anno: not _is_instance_type(type_anno))
def _generate_at_v_reader(
    type_anno: intermediate.TypeAnnotationUnion, v_name: str
) -> Stripped:
    """Generate the function reading ``type_anno`` from a ``v``-element."""
    name = _at_v_reader_name(type_anno, v_name)
    value_type = java_common.generate_type(type_anno)
    v_name_literal = java_common.string_literal(v_name)
    content_reader = _content_reader_name(type_anno)

    return Stripped(
        f"""\
private static Reporting.Result<? extends {value_type}> {name}(
{I}XMLEventReader reader) {{
{I}return XmlCommon.readNamedElement(
{II}reader,
{II}{v_name_literal},
{II}_DeserializeImplementation::{content_reader});
}}"""
    )


# endregion

# region De-serialization of a class


@require(lambda prop, cls: intermediate.runtime_id(prop) in cls.property_id_set)
def _generate_deserialize_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Stripped:
    """Generate the snippet to deserialize the property ``prop`` from the content."""
    target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    result_type: str
    read_expr: Stripped

    if _is_instance_type(type_anno):
        assert isinstance(type_anno, intermediate.OurTypeAnnotation)
        our_type = type_anno.our_type

        if _is_dispatched(our_type):
            result_type = f"? extends {java_common.generate_type(type_anno)}"
            read_expr = Stripped(
                f"""\
XmlCommon.readNestedElement(
{I}reader,
{I}isEmptyProperty,
{I}_DeserializeImplementation::{_from_element_name(our_type)})"""
            )
        else:
            assert isinstance(our_type, intermediate.ConcreteClass), (
                f"Expected a concrete class without any descendant, "
                f"but got: {our_type}"
            )
            result_type = java_naming.class_name(our_type.name)
            read_expr = Stripped(
                f"{_from_sequence_name(our_type)}(reader, isEmptyProperty)"
            )
    else:
        result_type = java_common.generate_type(type_anno)
        read_expr = Stripped(
            f"{_content_reader_name(type_anno)}(reader, isEmptyProperty)"
        )

    # NOTE (mristin):
    # A variable which is not null can only have been set by an earlier turn of
    # the property loop, so it tells us that the property comes a second time.
    # The check precedes the read, so the duplicate is refused without its
    # content ever being looked at.
    return Stripped(
        f"""\
if ({target_var} != null) {{
{I}valueError = duplicatePropertyError(elementName);
{I}break;
}}

final Reporting.Result<{result_type}> value =
{I}{indent_but_first_line(read_expr, I)};
if (value.isError()) {{
{I}valueError = value.getError();
}} else {{
{I}{target_var} = value.getResult();
}}"""
    )


def _generate_deserialize_impl_cls_from_sequence(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the function to de-serialize the ``cls`` from an XML sequence."""
    name = java_naming.class_name(identifier=cls.name)
    function_name = _from_sequence_name(cls)

    description = Stripped(
        f"""\
/**
 * Deserialize an instance of class {name} from a sequence of XML elements.
 *
 * <p>If {{@code isEmptySequence}} is set, we should try to deserialize
 * the instance from an empty sequence. That is, the parent element
 * was a self-closing element.
 */"""
    )

    # NOTE (empwilli):
    # Hard-wire for the case when no sequence is read
    if len(cls.constructor.arguments) == 0:
        return (
            Stripped(
                f"""\
{description}
private static Reporting.Result<{name}> {function_name}(
{I}XMLEventReader reader,
{I}boolean isEmptySequence) {{
{I}return Reporting.Result.success(new {name}());
}}"""
            ),
            None,
        )

    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    init_target_var_stmts = []  # type: List[Stripped]
    for prop in cls.properties:
        target_type = java_common.generate_type(
            intermediate.beneath_optional(prop.type_annotation)
        )
        target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

        init_target_var_stmts.append(Stripped(f"{target_type} {target_var} = null;"))
    blocks.append(Stripped("\n".join(init_target_var_stmts)))

    case_blocks = []  # type: List[Stripped]
    for prop in cls.properties:
        case_body = _generate_deserialize_property(prop=prop, cls=cls)

        xml_prop_name_literal = java_common.string_literal(prop.xml_name)
        case_blocks.append(
            Stripped(
                f"""\
case {xml_prop_name_literal}: {{
{I}{indent_but_first_line(case_body, I)}
{I}break;
}}"""
            )
        )

    class_name_literal = java_common.string_literal(name)

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}return unexpectedProperty({class_name_literal}, elementName);"""
        )
    )

    switch_body = "\n".join(case_blocks)

    # NOTE (mristin):
    # Every property is read in this very loop, so we mark the error with
    # the property's own element name here, once, instead of at every single
    # case above. For a matched case, ``elementName`` *is* that name.
    blocks.append(
        Stripped(
            f"""\
if (!isEmptySequence) {{
{I}while (!atEndOfSequence(reader)) {{
{II}final Reporting.Result<String> tryElementName = XmlCommon.peekElementName(reader);
{II}if (tryElementName.isError()) {{
{III}return Reporting.Result.failure(tryElementName.getError());
{II}}}

{II}final String elementName = tryElementName.getResult();
{II}final boolean isEmptyProperty = XmlCommon.isEmptyElement(reader);

{II}Reporting.Error valueError = null;

{II}switch (elementName) {{
{III}{indent_but_first_line(switch_body, III)}
{II}}}

{II}if (valueError != null) {{
{III}valueError.prependSegment(
{IIII}new Reporting.NameSegment(
{IIIII}elementName));
{III}return Reporting.Result.failure(valueError);
{II}}}

{II}final Reporting.Result<XMLEvent> endResult = XmlCommon.consumeEndElement(reader, elementName);
{II}if (endResult.isError()) {{
{III}return Reporting.Result.failure(endResult.getError());
{II}}}
{I}}}
}}"""
        )
    )

    # region Check that the mandatory properties have been set

    for prop in cls.properties:
        prop_java = java_naming.property_name(prop.name)
        target_var = java_naming.variable_name(Identifier(f"the_{prop.name}"))

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            prop_java_literal = java_common.string_literal(prop_java)

            blocks.append(
                Stripped(
                    f"""\
if ({target_var} == null) {{
{I}return missingRequiredProperty({prop_java_literal}, {class_name_literal});
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
    init_writer.write(f"return Reporting.Result.success(new {name}(\n")

    for i, arg in enumerate(cls.constructor.arguments):
        prop = cls.properties_by_name[arg.name]

        # NOTE (empwilli):
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
                    f"to the constructor in the XML de-serialization.",
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

    # endregion

    blocks.append(Stripped(init_writer.getvalue()))

    writer = io.StringIO()
    writer.write(
        f"""\
{description}
private static Reporting.Result<{name}> {function_name}(
{I}XMLEventReader reader,
{I}boolean isEmptySequence) {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_deserialize_impl_concrete_cls_from_element(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the function to de-serialize a concrete ``cls`` from an XML element."""
    name = java_naming.class_name(cls.name)
    xml_name_literal = java_common.string_literal(naming.xml_class_name(cls.name))

    return Stripped(
        f"""\
/**
 * Deserialize an instance of class {name} from an XML element.
 */
private static Reporting.Result<? extends {name}> {_concrete_from_element_name(cls)}(
{I}XMLEventReader reader) {{
{I}return XmlCommon.readNamedElement(
{II}reader,
{II}{xml_name_literal},
{II}_DeserializeImplementation::{_from_sequence_name(cls)});
}}"""
    )


def _generate_dispatch_from_element(
    function_name: Identifier,
    value_type: str,
    description: Stripped,
    case_blocks: List[Stripped],
) -> Stripped:
    """Generate a dispatcher on the element's own name."""
    case_blocks = list(case_blocks)
    case_blocks.append(
        Stripped(
            f"""\
default:
{I}return Reporting.Result.failure(new Reporting.Error(
{II}"Unexpected element with the name " + tryElementName.getResult()));"""
        )
    )

    joined_case_blocks = "\n".join(case_blocks)

    return Stripped(
        f"""\
{description}
private static Reporting.Result<? extends {value_type}> {function_name}(
{I}XMLEventReader reader) {{
{I}// NOTE (mristin):
{I}// We only peek the name, so that the whole element can be handed on to
{I}// the reader which we select below.
{I}final Reporting.Result<String> tryElementName = XmlCommon.peekElementName(reader);
{I}if (tryElementName.isError()) {{
{II}return Reporting.Result.failure(tryElementName.getError());
{I}}}

{I}switch (tryElementName.getResult()) {{
{II}{indent_but_first_line(joined_case_blocks, II)}
{I}}}
}}"""
    )


def _generate_deserialize_impl_interface_from_element(
    interface: intermediate.Interface,
) -> Stripped:
    """Generate the function to de-serialize an ``interface`` from an XML element."""
    name = java_naming.interface_name(interface.name)

    case_blocks = []  # type: List[Stripped]
    for implementer in interface.implementers:
        implementer_xml_name_literal = java_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        case_blocks.append(
            Stripped(
                f"""\
case {implementer_xml_name_literal}:
{I}return {_concrete_from_element_name(implementer)}(reader);"""
            )
        )

    return _generate_dispatch_from_element(
        function_name=Identifier(f"read{name}FromElement"),
        value_type=name,
        description=Stripped(
            f"""\
/**
 * Deserialize an instance of {name} from an XML element.
 */"""
        ),
        case_blocks=case_blocks,
    )


def _generate_deserialize_impl_named_union_from_element(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the function to de-serialize the named union ``named_union`` from
    an XML element.

    Dispatch uniformly on the element's own tag over every flattened
    implementer -- XML elements are always self-tagging with the concrete
    class's own name, regardless of whether that implementer is dispatched
    by ``modelType`` on the JSON side.
    """
    name = java_naming.union_name(named_union.name)

    case_blocks = []  # type: List[Stripped]
    for implementer in named_union.implementers:
        implementer_xml_name_literal = java_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        implementer_name = java_naming.class_name(implementer.name)

        case_blocks.append(
            Stripped(
                f"""\
case {implementer_xml_name_literal}: {{
{I}final Reporting.Result<? extends {implementer_name}> result =
{II}{_concrete_from_element_name(implementer)}(reader);
{I}if (result.isError()) {{
{II}return Reporting.Result.failure(result.getError());
{I}}}
{I}return Reporting.Result.success({name}.from{implementer_name}(result.getResult()));
}}"""
            )
        )

    return _generate_dispatch_from_element(
        function_name=Identifier(f"read{name}FromElement"),
        value_type=name,
        description=Stripped(
            f"""\
/**
 * Deserialize an instance of {name} from an XML element.
 */"""
        ),
        case_blocks=case_blocks,
    )


# endregion


def _generate_json_value_readers(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the readers which hand a JSON-able value over to ``XmlRpc``.

    A content reader of this module is a static method taking nothing but
    the reader and the emptiness of the element, which is what lets it be
    passed as a method reference without allocating. These three give
    the readers of ``XmlRpc`` the name which this module's registry of
    the readers expects.
    """
    if not intermediate.uses_json_types(symbol_table):
        return []

    return [
        Stripped(
            f"""\
/**
 * Read the content of an element holding a JSON-able value.
 */
private static Reporting.Result<JsonNode> readTextAs_jsonValue(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}return XmlRpc.readValueContent(reader, isEmpty);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of an element holding a JSON-able array.
 */
private static Reporting.Result<ArrayNode> readTextAs_jsonArray(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}return XmlRpc.readArrayContent(reader, isEmpty);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Read the content of an element holding a JSON-able object.
 */
private static Reporting.Result<ObjectNode> readTextAs_jsonObject(
{I}XMLEventReader reader, boolean isEmpty) {{
{I}return XmlRpc.readObjectContent(reader, isEmpty);
}}"""
        ),
    ]


def _generate_json_value_writers(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the writers which hand a JSON-able value over to ``XmlRpc``.

    These mirror :py:func:`_generate_json_value_readers`.
    """
    if not intermediate.uses_json_types(symbol_table):
        return []

    return [
        Stripped(
            f"""\
/**
 * Write {{@code that}} as the content of an element holding a JSON-able
 * value.
 */
private static void writeJsonValueContent(
{I}JsonNode that, XMLStreamWriter writer) {{
{I}XmlRpc.writeValueContent(that, writer);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write {{@code that}} as the content of an element holding a JSON-able
 * array.
 */
private static void writeJsonArrayContent(
{I}ArrayNode that, XMLStreamWriter writer) {{
{I}XmlRpc.writeArrayContent(that, writer);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Write {{@code that}} as the content of an element holding a JSON-able
 * object.
 */
private static void writeJsonObjectContent(
{I}ObjectNode that, XMLStreamWriter writer) {{
{I}XmlRpc.writeObjectContent(that, writer);
}}"""
        ),
    ]


def _generate_deserialize_impl(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the implementation for deserialization functions."""
    needed = _collect_needed(symbol_table)

    blocks = [
        _generate_skip_start_document(),
        _generate_reader_interfaces(),
    ]  # type: List[Stripped]

    blocks.extend(_generate_content_converters(needed.primitive_types))

    if len(needed.primitive_types) > 0:
        blocks.extend(_generate_read_text(needed.primitive_types))

    if needed.enumerations:
        blocks.append(_generate_read_enum())

    if needed.lists:
        blocks.append(_generate_read_list())

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_read_tuple_helper(arity=arity))

    if any(len(cls.constructor.arguments) > 0 for cls in symbol_table.concrete_classes):
        blocks.append(_generate_at_end_of_sequence())
        blocks.append(_generate_unexpected_property())
        blocks.append(_generate_duplicate_property_error())

    if any(
        not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.append(_generate_missing_required_property())

    blocks.extend(_generate_json_value_readers(symbol_table=symbol_table))

    for type_anno in needed.content_readers.values():
        content_reader = _generate_content_reader(type_anno)
        if content_reader != "":
            blocks.append(content_reader)

    for type_anno, v_name in needed.at_v_readers.values():
        blocks.append(_generate_at_v_reader(type_anno, v_name))

    errors = []  # type: List[Error]

    # NOTE (empwilli):
    # Enumerations are going to be directly deserialized using
    # ``Stringification``.

    # NOTE (empwilli):
    # Constrained primitives are only verified, but do not represent a Java type.

    for cls in symbol_table.classes:
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
            blocks.append(_generate_deserialize_impl_concrete_cls_from_element(cls=cls))

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_deserialize_impl_named_union_from_element(named_union=named_union)
        )

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()

    writer.write(
        """\
/**
 * Implement the deserialization of meta-model classes from XML.
 *
 * <p>The implementation propagates an {@link Reporting.Error} instead of
 * relying on exceptions. Under the assumption that incorrect data is much less
 * frequent than correct data, this makes the deserialization more
 * efficient.
 *
 * <p>However, we do not want to force the client to deal with
 * the {@link Reporting.Error} class as this is not intuitive.
 * Therefore we distinguish the implementation, realized in
 * {@link _DeserializeImplementation}, and the facade given in
 * {@link Deserialize} class.
 */
private static class _DeserializeImplementation
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_deserialize_from(name: Identifier) -> Stripped:
    """Generate the facade method for deserialization of the class or interface."""
    xml_prop_name_literal = java_common.string_literal(naming.xml_property(name))
    writer = io.StringIO()

    writer.write(
        f"""\
/**
 * Deserialize an instance of {name} from {{@code reader}}.
 *
 * @param reader Initialized XML reader with reader.peek() set to the element
 */
"""
    )
    writer.write(
        f"""\
public static {name} deserialize{name}(
{I}XMLEventReader reader) {{

{I}_DeserializeImplementation.skipStartDocument(reader);
{I}XmlCommon.skipWhitespaceAndComments(reader);

{I}Reporting.Result<? extends {name}> result =
{II}_DeserializeImplementation.read{name}FromElement(
{III}reader);

{I}return result.onError(error -> {{
{II}error.prependSegment(new Reporting.NameSegment({xml_prop_name_literal}));
{II}throw new XmlCommon.DeserializeException(
{III}Reporting.generateRelativeXPath(error.getPathSegments()),
{III}error.getCause());
{I}}});
}}"""
    )

    return Stripped(writer.getvalue())


def _generate_deserialize(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the public class ``Deserialize``."""
    blocks = []  # type: List[Stripped]

    # NOTE (empwilli):
    # We use stringification for de-serialization of enumerations.

    # NOTE (empwilli):
    # Constrained primitives are not handled as separate classes, but as
    # primitives, and only verified in the verification.

    for cls in symbol_table.classes:
        if cls.interface is not None:
            blocks.append(
                _generate_deserialize_from(
                    name=java_naming.interface_name(cls.interface.name)
                )
            )

        if isinstance(cls, intermediate.ConcreteClass):
            blocks.append(
                _generate_deserialize_from(name=java_naming.class_name(cls.name))
            )

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_deserialize_from(name=java_naming.union_name(named_union.name))
        )

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Deserialize instances of meta-model classes from XML.
 */
"""
    )

    first_cls = symbol_table.classes[0] if len(symbol_table.classes) > 0 else None

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
/** <pre>
 * Here is an example how to parse an instance of class {cls_name}:
 * {{@code
 * XMLEventReader reader = xmlFactory.createXMLEventReader(...some arguments...);
 * {cls_name} {an_instance_variable} = Deserialize.deserialize{cls_name}(
 * {I}reader);
 * }}
 * </pre>
 *
 * <pre>
 * If the elements live in a namespace, you have to supply it. For example:
 * {{@code
 * XMLEventReader reader = xmlFactory.createXMLEventReader(...some arguments...);
 * {cls_name} {an_instance_variable} = Deserialize.deserialize{cls_name}(
 * {I}reader,
 * {I}"http://www.example.com/5/12");
 * }}
 * </pre>
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


# region Shared writers


def _generate_visitors(with_nested: bool) -> Stripped:
    """Generate the namespace flag and the immutable visitors pinning it."""
    nested = (
        ""
        if not with_nested
        else f"""

/**
 * Write an element nested in another one, which never re-declares the XML
 * namespace.
 */
private static final {_VISITOR_NAME} NESTED =
{I}new {_VISITOR_NAME}(false);"""
    )

    return Stripped(
        f"""\
/**
 * Declare the XML namespace on the element which this visitor writes.
 *
 * <p>Only the outermost element carries the declaration. The obvious
 * alternative -- a flag cleared once the first element has been written --
 * would be mutable state, and state forces every method of this class to be
 * an instance method, which in turn makes every method reference to it
 * capture {{@code this}} and allocate. Pinning the flag in the constructor
 * instead costs one visitor per case, allocated once for the whole program,
 * and lets everything else here be {{@code static}}.
 */
private final boolean withNamespace;

private {_VISITOR_NAME}(boolean withNamespace) {{
{I}this.withNamespace = withNamespace;
}}

/**
 * Write the outermost element, which declares the XML namespace.
 */
private static final {_VISITOR_NAME} ROOT =
{I}new {_VISITOR_NAME}(true);{nested}"""
    )


def _generate_write_property() -> Stripped:
    """Generate the framer writing a property, naming it on the error path."""
    return Stripped(
        f"""\
/**
 * Write {{@code that}} as the XML element of a property called
 * {{@code name}}.
 *
 * <p>This is {{@link #writeElement}} plus the one thing a property knows
 * which nothing below it does: its own name. Prepending it here, once,
 * saves a {{@code try}} around every one of the property writes.
 *
 * <p>The path names the getter, and not the XML element: a serialization
 * error is reported on an <em>instance</em>, which the caller holds, and
 * not on a document which has not been written yet.
 */
private static <T> void writeProperty(
{I}String name,
{I}String getterName,
{I}T that,
{I}XMLStreamWriter writer,
{I}XmlCommon.ContentWriter<? super T> writeContent) {{
{I}try {{
{II}XmlCommon.writeElement(name, that, writer, writeContent);
{I}}} catch (XmlCommon.SerializeFailure failure) {{
{II}failure.getError().prependSegment(
{III}new Reporting.NameSegment(getterName));
{II}throw failure;
{I}}}
}}"""
    )


def _generate_write_optional_property() -> Stripped:
    """Generate the framer writing a property which may not have been given."""
    return Stripped(
        f"""\
/**
 * Write {{@code that}} as the XML element of a property called
 * {{@code name}} if it has been given, and write nothing at all otherwise.
 *
 * <p>The {{@link Optional}} is taken apart here, once, instead of at every
 * optional property: asking it and then unwrapping it at the call site
 * would call the getter twice, and every call allocates an
 * {{@link Optional}} of its own.
 */
private static <T> void writeOptionalProperty(
{I}String name,
{I}String getterName,
{I}Optional<T> that,
{I}XMLStreamWriter writer,
{I}XmlCommon.ContentWriter<? super T> writeContent) {{
{I}final T value = that.orElse(null);
{I}if (value != null) {{
{II}writeProperty(name, getterName, value, writer, writeContent);
{I}}}
}}"""
    )


def _generate_write_class() -> Stripped:
    """Generate the writer picking the element from the value itself."""
    return Stripped(
        f"""\
/**
 * Write {{@code that}} as its own, self-describing XML element.
 *
 * <p>Which element that is, is decided by the run-time type of
 * {{@code that}}, so this one writer serves every abstract class, every
 * concrete class with descendants, and the item of a list or of a tuple of
 * any class at all. The reading, which has to decide what to construct
 * before it has read anything, needs a dispatcher per interface instead.
 *
 * <p>An element written from here is nested in another one by
 * construction, so it goes through the visitor which does not re-declare
 * the XML namespace.
 */
private static void writeClass(
{I}IClass that,
{I}XMLStreamWriter writer) {{
{I}NESTED.visit(that, writer);
}}"""
    )


def _generate_write_union() -> Stripped:
    """Generate the writer of a named union shared by all the named unions."""
    return Stripped(
        f"""\
/**
 * Write the underlying instance of {{@code that}} as its own XML element.
 *
 * <p>A named union is not itself an {{@link IClass}}, so it can not be
 * written by {{@link #writeClass}} directly. Dispatching over the common
 * {{@code IUnion<?>}} instead of the union's own type means a single writer
 * for *all* the named unions, not one per union.
 *
 * <p>Should a named union ever be allowed to flatten a primitive or an
 * enumeration alternative, only this body has to change -- every call site
 * stays the same.
 */
private static void writeUnion(
{I}IUnion<?> that,
{I}XMLStreamWriter writer) {{
{I}writeClass(that.getUnderlying(), writer);
}}"""
    )


def _generate_write_enum() -> Stripped:
    """Generate the writer rendering any enumeration literal as content."""
    return Stripped(
        f"""\
/**
 * Write the text of {{@code that}} as XML content.
 *
 * <p>This is the {{@link ContentWriter}} of every enumeration-typed value, be
 * it a property, a list item or a tuple item. There is one writer, and not
 * one per enumeration, since a literal carries its own text -- see
 * {{@link IEnum#literalText()}} -- so nothing here is specific to
 * an enumeration.
 */
private static void writeEnum(
{I}IEnum that,
{I}XMLStreamWriter writer) throws XMLStreamException {{
{I}writer.writeCharacters(that.literalText());
}}"""
    )


def _generate_write_byte_array_content() -> Stripped:
    """Generate the writer rendering a byte array as base64-encoded content."""
    return Stripped(
        f"""\
/**
 * Write {{@code that}} as base64-encoded XML content.
 *
 * <p>This is the {{@link ContentWriter}} of every {{@code byte[]}}-typed
 * value, be it a property, a list item or a tuple item.
 */
private static void writeByteArrayContent(
{I}byte[] that,
{I}XMLStreamWriter writer) throws XMLStreamException {{
{I}writer.writeCharacters(
{II}Base64.getEncoder().encodeToString(that));
}}"""
    )


# endregion

# region Writers of a single type


def _container_type(type_anno: intermediate.ContainerTypeAnnotation) -> Stripped:
    """
    Render the type of the list or of the tuple ``type_anno`` as its writer takes it.

    The items are spelled by what they are written as, so that the writer
    accepts every list, and every tuple, of that shape.
    """
    # NOTE (mristin):
    # Java generics are invariant, so a ``List<IExtension>`` is *not*
    # a ``List<IClass>`` and a ``Tuple2<IExtension, IKey>`` is *not*
    # a ``Tuple2<IClass, IClass>``. Wherever the value type widens, the bound
    # has to be spelled out for the container to accept the list or the tuple
    # which a property actually holds. A byte array widens to nothing, so it
    # needs none, and a scalar widens all the way up, which the unbounded
    # wildcard already says.
    argument_types = []  # type: List[Stripped]
    for item_type_anno in _item_type_annotations(type_anno):
        primitive_type = intermediate.try_primitive_type(item_type_anno)

        if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
            argument_types.append(Stripped("byte[]"))
        elif primitive_type is not None:
            argument_types.append(Stripped("?"))
        else:
            argument_types.append(
                Stripped(f"? extends {_written_value_type(item_type_anno)}")
            )

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return Stripped(f"List<{argument_types[0]}>")

    return java_common.tuple_type(argument_types)


@require(lambda type_anno: not _is_instance_type(type_anno))
def _generate_content_writer(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """
    Generate the function writing ``type_anno`` as the content of an element.

    Everything here is derived from what the items are written as and never
    from their types, so that the one function really does serve every list,
    and every tuple, whose items are written the same way -- ``type_anno`` is
    only the first representative which reached this writer.

    The parameter is therefore wider than the list or the tuple a property
    holds, which means ``javac`` no longer rejects a value handed to the wrong
    writer: a ``List<byte[]>`` passed to ``writeListOf_stringified`` compiles,
    and would render ``[B@1a2b3c`` instead of base64. What keeps that from
    happening is that a single :py:func:`_written_leaf_moniker` decides both
    the name of the writer and its body, and that a byte array is an answer of
    its own -- the same discipline
    :py:func:`aas_core_codegen.java.common.leaf_moniker` already relies on.
    """
    name = _content_writer_name(type_anno)
    value_type = _container_type(type_anno)
    item_type_annos = _item_type_annotations(type_anno)

    body: Stripped

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_type = _written_value_type(item_type_annos[0])
        item_writer = _element_writer_name(item_type_annos[0], "v")

        # NOTE (mristin):
        # The ``try`` sits outside the loop, and the index is advanced only
        # once an item has been written, so that the item which failed is
        # the one named on the error path. A ``try`` per item would cost
        # nothing at run-time either, but it would be a good deal noisier.
        body = Stripped(
            f"""\
int index = 0;
try {{
{I}for ({item_type} item : that) {{
{II}{item_writer}(item, writer);
{II}index++;
{I}}}
}} catch (XmlCommon.SerializeFailure failure) {{
{I}failure.getError().prependSegment(
{II}new Reporting.IndexSegment(index));
{I}throw failure;
}}"""
        )
    else:
        assert isinstance(
            type_anno, intermediate.TupleTypeAnnotation
        ), f"Expected a tuple, but got: {type_anno}"

        item_writes = []  # type: List[str]
        for i, item_type_anno in enumerate(item_type_annos):
            if i > 0:
                item_writes.append(f"{I}index = {i};")

            item_writes.append(
                f"{I}{_element_writer_name(item_type_anno, f'v{i + 1}')}"
                f"(that.item{i + 1}(), writer);"
            )

        joined_item_writes = "\n".join(item_writes)

        body = Stripped(
            f"""\
int index = 0;
try {{
{joined_item_writes}
}} catch (XmlCommon.SerializeFailure failure) {{
{I}failure.getError().prependSegment(
{II}new Reporting.IndexSegment(index));
{I}throw failure;
}}"""
        )

    return Stripped(
        f"""\
private static void {name}(
{I}{indent_but_first_line(value_type, I)} that,
{I}XMLStreamWriter writer) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


@require(lambda type_anno: not _is_instance_type(type_anno))
def _generate_at_v_writer(
    type_anno: intermediate.AtomicTypeAnnotation, v_name: str
) -> Stripped:
    """
    Generate the function writing ``type_anno`` as a ``v``-element.

    Only what the value is written as decides the content, so this is one
    function per answer and position, and ``type_anno`` is merely the first
    representative which reached it.
    """
    name = _at_v_writer_name(type_anno, v_name)
    value_type = _written_value_type(type_anno)
    v_name_literal = java_common.string_literal(v_name)
    content_writer = _content_writer_reference(type_anno)

    return Stripped(
        f"""\
private static void {name}(
{I}{value_type} that,
{I}XMLStreamWriter writer) {{
{I}XmlCommon.writeElement(
{II}{v_name_literal},
{II}that,
{II}writer,
{II}{content_writer});
}}"""
    )


# endregion

# region Serialization of a class


def _generate_serialize_property(prop: intermediate.Property) -> Stripped:
    """Generate the snippet writing the property ``prop`` as an XML element."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    # NOTE (mristin):
    # Every property kind is written by the very same call -- only the
    # content writer differs, and the type of the property alone picks it.
    function_name = (
        "writeOptionalProperty"
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        else "writeProperty"
    )

    xml_prop_name_literal = java_common.string_literal(prop.xml_name)
    getter_name = java_naming.getter_name(prop.name)
    content_writer = _content_writer_reference(type_anno)

    # NOTE (mristin):
    # The path names the getter, and not the XML element: a serialization
    # error is reported on an *instance*, which the caller holds, and not on
    # a document which has not been written yet.
    getter_literal = java_common.string_literal(f"{getter_name}()")

    return Stripped(
        f"""\
{function_name}(
{I}{xml_prop_name_literal},
{I}{getter_literal},
{I}that.{getter_name}(),
{I}writer,
{I}{content_writer});"""
    )


def _generate_class_as_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the function writing ``cls`` as a sequence of property elements."""
    blocks = [_generate_serialize_property(prop=prop) for prop in cls.properties]

    if len(blocks) == 0:
        blocks.append(Stripped("// Intentionally empty."))

    interface_name = java_naming.interface_name(cls.name)
    name = _as_sequence_name(cls)

    writer = io.StringIO()
    writer.write(
        f"""\
private static void {name}(
{I}{interface_name} that,
{I}XMLStreamWriter writer) {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_visit_for_class(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method writing the ``cls`` as its own XML element."""
    interface_name = java_naming.interface_name(cls.name)
    visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))
    xml_cls_name_literal = java_common.string_literal(naming.xml_class_name(cls.name))

    return Stripped(
        f"""\
@Override
public void {visit_name}(
{I}{interface_name} that,
{I}XMLStreamWriter writer) {{
{I}XmlCommon.writeElement(
{II}{xml_cls_name_literal},
{II}that,
{II}writer,
{II}withNamespace,
{II}{_VISITOR_NAME}::{_as_sequence_name(cls)});
}}"""
    )


# endregion


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_visitor(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate a visitor which serializes instances of the meta-model to XML."""
    errors = []  # type: List[Error]

    # NOTE (mristin):
    # One gating pass answers for both directions, since the reading and
    # the writing reach a value over the same path. It keeps a collection per
    # direction, though, because a writer is named after what it writes and
    # a reader after the type it reads, so the writers are strictly
    # fewer -- see :py:func:`_written_leaf_moniker`.
    needed = _collect_needed(symbol_table)

    write_classes, write_unions = _collect_dispatching_writers(symbol_table)

    blocks = [
        _generate_visitors(with_nested=write_classes),
    ]  # type: List[Stripped]

    if any(len(cls.properties) > 0 for cls in symbol_table.concrete_classes):
        blocks.append(_generate_write_property())

    if any(
        isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.append(_generate_write_optional_property())

    if write_classes:
        blocks.append(_generate_write_class())

    if write_unions:
        blocks.append(_generate_write_union())

    # NOTE (mristin):
    # The gating follows the call graph literally: the very function which
    # names a call decides whether that call can occur at all, so a shared
    # writer can not be gated on one condition and called under another.
    if Identifier("writeByteArrayContent") in needed.called_content_writers:
        blocks.append(_generate_write_byte_array_content())

    if Identifier("writeEnum") in needed.called_content_writers:
        blocks.append(_generate_write_enum())

    blocks.extend(_generate_json_value_writers(symbol_table=symbol_table))

    for container_type_anno in needed.content_writers.values():
        blocks.append(_generate_content_writer(container_type_anno))

    for item_type_anno, v_name in needed.at_v_writers.values():
        blocks.append(_generate_at_v_writer(item_type_anno, v_name))

    # The abstract classes are directly dispatched by the transformer,
    # so we do not need to handle them separately.

    for cls in symbol_table.concrete_classes:
        blocks.append(_generate_class_as_sequence(cls=cls))
        # NOTE (mristin):
        # Writing the element around the sequence is the same for every
        # class, implementation-specific or not, so it is never snippeted.
        blocks.append(_generate_visit_for_class(cls=cls))

    if len(errors) > 0:
        return None, errors

    writer = io.StringIO()
    writer.write(
        f"""\
/**
 * Serialize recursively the instances as XML elements.
 */
static class {_VISITOR_NAME}
{I}extends AbstractVisitorWithContext<XMLStreamWriter> {{

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
        Stripped(
            f"""\
/**
 * Serialize an instance of the meta-model to XML.
 *
 * <p>{{@code writer}} is flushed exactly once, here at the end. Nothing is
 * flushed in-between, which is what lets {{@link XMLStreamWriter}} buffer,
 * and the single flush at the end is what lets a failure of the underlying
 * stream be reported as a {{@link XmlCommon.SerializeException}} from this method --
 * were it left to the caller, the failure would surface at their own flush,
 * after the serialization has long returned.
 *
 * <p>The path of a {{@link XmlCommon.SerializeException}} is rendered as
 * a Java access path, and not as the relative XPath the de-serialization
 * reports: the caller invoked this on an <em>instance</em>, and not on
 * a document, which has not been written yet. It names the getters and
 * the indices leading to the culprit, so that
 * {{@code getSubmodelElements().get(0).getValue()}} can be pasted as it
 * stands. The outermost element is deliberately not named, as this method
 * takes any {{@link IClass}} and the name would say nothing the caller does
 * not already know.
 */
public static void to(
{I}IClass that,
{I}XMLStreamWriter writer) throws XmlCommon.SerializeException {{
{I}try {{
{II}{_VISITOR_NAME}.ROOT.visit(
{III}that, writer);
{II}writer.flush();
{I}}} catch (XMLStreamException exception) {{
{II}throw new XmlCommon.SerializeException("", exception.getMessage());
{I}}} catch (XmlCommon.SerializeFailure failure) {{
{II}final Reporting.Error error = failure.getError();
{II}throw new XmlCommon.SerializeException(
{III}Reporting.generateJavaPath(error.getPathSegments()),
{III}error.getCause());
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Serialize instances of meta-model classes to XML.
 */
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
/**
 * <pre>
 * Here is an example how to serialize an instance of {cls_name}:
 * {{@code
 * IClass {an_instance_variable} = new {cls_name}(
 *     ... some constructor arguments ...
 * );
 * XMLStreamWriter writer = xmlWriterFactory.createXMLStreamWriter(...some arguments...);
 * Serialize.to(
 * {I}{an_instance_variable},
 * {I}writer);
 * }}
 * </pre>
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


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate the code for XML de/serialization.
    """
    errors = []  # type: List[Error]

    imports = [
        Stripped("import javax.xml.stream.events.XMLEvent;"),
        Stripped("import javax.xml.stream.XMLEventReader;"),
        Stripped("import javax.xml.stream.XMLStreamConstants;"),
        Stripped("import javax.xml.stream.XMLStreamException;"),
        Stripped("import javax.xml.stream.XMLStreamWriter;"),
        Stripped("import java.util.ArrayList;"),
        Stripped("import java.util.Base64;"),
        Stripped("import java.util.function.Function;"),
        Stripped("import java.util.List;"),
        Stripped("import java.util.Optional;"),
        Stripped("import java.util.regex.Pattern;"),
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.reporting.Reporting;"),
        Stripped(f"import {package}.stringification.Stringification;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.impl.*;"),
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.*;"),
        Stripped(f"import {package}.xmlcommon.XmlCommon;"),
    ]  # type: List[Stripped]

    # NOTE (mristin):
    # A JSON-able value is a Jackson node, and only the models which use one
    # pay for the import and for the XML-RPC de/serialization which goes
    # with it.
    if intermediate.uses_json_types(symbol_table):
        imports.extend(
            [
                *(
                    Stripped(f"import {json_import};")
                    for json_import in java_common.JSON_IMPORTS
                ),
                Stripped("import com.fasterxml.jackson.databind.node.JsonNodeFactory;"),
                Stripped("import java.util.Iterator;"),
                Stripped(f"import {package}.xmlrpc.XmlRpc;"),
            ]
        )

    # region Deserialization helpers

    # endregion

    # region Deserialization Implementation

    deserialize_impl_block, deserialize_impl_errors = _generate_deserialize_impl(
        symbol_table=symbol_table
    )
    if deserialize_impl_errors is not None:
        errors.extend(deserialize_impl_errors)

    assert deserialize_impl_block is not None

    # endregion

    # region Deserialization

    deserialize_block = _generate_deserialize(symbol_table=symbol_table)

    # endregion

    # region Visitor

    visitor_block, visitor_errors = _generate_visitor(symbol_table=symbol_table)
    if visitor_errors is not None:
        errors.extend(visitor_errors)

    assert visitor_block is not None

    # endregion

    # region Serialization

    serialization_block = _generate_serialize(symbol_table=symbol_table)

    # endregion

    xmlization_blocks = [
        Stripped(
            f"""\
/**
 * Provide de/serialization of meta-model classes to/from XML.
 */
public class Xmlization {{
{I}/**
{I} * The XML namespace of the meta-model
{I} */
{I}public static final String AAS_NAME_SPACE =
{II}XmlCommon.NAMESPACE;


{I}{indent_but_first_line(deserialize_impl_block, I)}

{I}{indent_but_first_line(deserialize_block, I)}

{I}{indent_but_first_line(visitor_block, I)}

{I}{indent_but_first_line(serialization_block, I)}
}}"""
        ),
    ]  # type: List[Stripped]

    if len(errors) > 0:
        return None, errors

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.xmlization;"),
        Stripped("\n".join(imports)),
        Stripped("\n\n".join(xmlization_blocks)),
        java_common.WARNING,
    ]  # type: List[Stripped]

    code = "\n\n".join(blocks)

    return [java_common.JavaFile("Xmlization.java", f"{code}\n")], None


# endregion


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
