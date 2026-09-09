"""Generate XML Schema Definition (XSD) corresponding to the meta-model."""

import re

# noinspection PyUnresolvedReferences
import xml.dom.minidom
import xml.etree.ElementTree as ET
from typing import TextIO, MutableMapping, Optional, Tuple, List, Any, Mapping, Final

import greenery
from icontract import ensure, require

import aas_core_codegen.xsd
from aas_core_codegen import (
    naming,
    specific_implementations,
    intermediate,
    run,
    infer_for_schema,
)
from aas_core_codegen.common import Error, assert_never, Identifier
from aas_core_codegen.parse import retree as parse_retree
from aas_core_codegen.xsd import naming as xsd_naming

assert aas_core_codegen.xsd.__doc__ == __doc__


def _define_for_enumeration(enumeration: intermediate.Enumeration) -> List[ET.Element]:
    """
    Generate the definitions for an ``enumeration``.
    The root element is to be *extended* with the resulting list.
    """
    restriction = ET.Element("xs:restriction", {"base": "xs:string"})
    for literal in enumeration.literals:
        restriction.append(ET.Element("xs:enumeration", {"value": literal.value}))

    element = ET.Element(
        "xs:simpleType", {"name": xsd_naming.type_name(enumeration.name)}
    )
    element.append(restriction)

    return [element]


_PRIMITIVE_MAP = {
    intermediate.PrimitiveType.BOOL: "xs:boolean",
    intermediate.PrimitiveType.INT: "xs:long",
    intermediate.PrimitiveType.FLOAT: "xs:double",
    intermediate.PrimitiveType.STR: "xs:string",
    intermediate.PrimitiveType.BYTEARRAY: "xs:base64Binary",
}
assert all(literal in _PRIMITIVE_MAP for literal in intermediate.PrimitiveType)

# noinspection RegExpSimplifiable
_ESCAPE_BACKSLASH_X_RE = re.compile(r"\\x([a-fA-f0-9]{2})")


def _undo_escaping_backslash_x_in_pattern(pattern: str) -> str:
    """
    Undo the escaping of `\\x??` in the ``pattern``.

    This is necessary since XML Schema Validators do not know how to handle such escape
    sequences in the patterns and need the verbatim characters.
    """
    parts = []  # type: List[str]
    cursor = None  # type: Optional[int]
    for mtch in re.finditer(_ESCAPE_BACKSLASH_X_RE, pattern):
        if cursor is None:
            parts.append(pattern[: mtch.start()])
        else:
            parts.append(pattern[cursor : mtch.start()])

        ascii_code = int(mtch.group(1), base=16)
        character = chr(ascii_code)
        parts.append(character)
        cursor = mtch.end()

    if cursor is None:
        parts.append(pattern)
    else:
        if cursor < len(pattern):
            parts.append(pattern[cursor:])

    return "".join(parts)


# noinspection RegExpSimplifiable
_ESCAPE_BACKSLASH_X_U_U_RE = re.compile(
    r"(\\x([a-fA-f0-9]{2})|\\u([a-fA-f0-9]{4})|\\U([a-fA-f0-9]{8}))"
)


def _undo_escaping_backslash_x_u_and_U_in_pattern(pattern: str) -> str:
    """
    Undo the escaping of ``\\x??``, ``\\u????`` and ``\\U????????`` in the ``pattern``.

    This is necessary since Greenery does not know how to handle such escape
    sequences in the patterns and need the verbatim characters.
    """
    parts = []  # type: List[str]
    cursor = None  # type: Optional[int]
    for mtch in re.finditer(_ESCAPE_BACKSLASH_X_U_U_RE, pattern):
        if cursor is None:
            parts.append(pattern[: mtch.start()])
        else:
            parts.append(pattern[cursor : mtch.start()])

        substring = mtch.group(0)
        assert len(substring) > 2
        assert substring[0] == "\\"

        hex_code = substring[2:]
        code_point = int(hex_code, base=16)
        character = chr(code_point)
        parts.append(character)
        cursor = mtch.end()

    if cursor is None:
        parts.append(pattern)
    else:
        if cursor < len(pattern):
            parts.append(pattern[cursor:])

    return "".join(parts)


class _AnchorRemover(parse_retree.PassThroughVisitor):
    """
    Remove anchors from a regex in-place.

    We need to remove the anchors (``^``, ``$``) since patterns in the XSD are always
    anchored.

    This is necessary since otherwise the schema validation fails.
    See: https://stackoverflow.com/questions/4367914/regular-expression-in-xml-schema-definition-fails
    """

    def visit_concatenation(self, node: parse_retree.Concatenation) -> None:
        """Visit the ``concatenation``."""
        new_concatenants = []  # type: List[parse_retree.Term]
        for concatenant in node.concatenants:
            if not (
                isinstance(concatenant.value, parse_retree.Symbol)
                and concatenant.value.kind
                in (parse_retree.SymbolKind.START, parse_retree.SymbolKind.END)
            ):
                new_concatenants.append(concatenant)

        node.concatenants = new_concatenants
        for concatenant in new_concatenants:
            self.visit(concatenant)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _translate_pattern(pattern: str) -> Tuple[Optional[str], Optional[str]]:
    """Translate the pattern to obtain the equivalent in XSD."""
    pattern = _undo_escaping_backslash_x_in_pattern(pattern)

    parsed, error = parse_retree.parse(values=[pattern])
    if error is not None:
        regex_line, pointer_line = parse_retree.render_pointer(error.cursor)
        return None, f"{error.message}\n{regex_line}\n{pointer_line}"
    assert parsed is not None

    remover = _AnchorRemover()
    remover.visit(parsed)

    values = parse_retree.render(regex=parsed)
    parts = []  # type: List[str]
    for value in values:
        assert isinstance(value, str), (
            "Only strings expected when rendering a pattern "
            "supplied originally as a string"
        )
        parts.append(value)

    return "".join(parts), None


class _SimpleTypeRestriction:
    """Model the restrictions applied on a simple type."""

    pattern: Final[Optional[str]]

    min_length: Final[Optional[int]]
    max_length: Final[Optional[int]]

    @require(
        lambda pattern, min_length, max_length: (pattern is not None)
        or (min_length is not None)
        or (max_length is not None),
        "At least one constraint defined",
    )
    def __init__(
        self,
        pattern: Optional[str] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> None:
        self.pattern = pattern
        self.min_length = min_length
        self.max_length = max_length


class _SimpleType:
    """
    Model a simple type in XSD.

    This is meant to be represented either with ``<xs:simpleType>``, if there are
    restrictions, or as an attribute ``type="..."`` in the containing element, when
    there are no restrictions.
    """

    tajp: Final[str]
    restriction: Final[Optional[_SimpleTypeRestriction]]

    def __init__(
        self, tajp: str, restriction: Optional[_SimpleTypeRestriction]
    ) -> None:
        self.tajp = tajp
        self.restriction = restriction


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _translate_to_simple_type(
    primitive_type: intermediate.PrimitiveType,
    constraints: Optional[infer_for_schema.Constraints],
) -> Tuple[Optional[_SimpleType], Optional[str]]:
    restriction: Optional[_SimpleTypeRestriction] = None

    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None

    if constraints is not None:
        if constraints.len_constraint is not None:
            min_length = constraints.len_constraint.min_value
            max_length = constraints.len_constraint.max_value

        if constraints.patterns is not None:
            # NOTE (mristin):
            # We skip the general XML character pattern. It makes greenery
            # unbearably slow since it instantiates *each* character in
            # the character range. Since XML engines can not deal with the special
            # characters any ways, there is no need to include this constraint in
            # the XSD pattern restrictions.
            patterns_relevant_for_xsd = [
                pattern_constraint
                for pattern_constraint in constraints.patterns
                if pattern_constraint.pattern
                != (
                    "^[\\x09\\x0A\\x0D\\x20-\\uD7FF\\uE000-\\uFFFD"
                    "\\U00010000-\\U0010FFFF]*$"
                )
            ]

            if len(patterns_relevant_for_xsd) > 0:
                translated_pattern: Optional[str]

                if len(patterns_relevant_for_xsd) == 1:
                    translated_pattern, error = _translate_pattern(
                        patterns_relevant_for_xsd[0].pattern
                    )
                    if error is not None:
                        return None, error
                else:
                    # NOTE (mristin, 2023-02-27):
                    # The module ``greenery`` is not annotated with types at the moment.
                    merger = None  # type: Optional[Any]
                    for pattern_constraint in patterns_relevant_for_xsd:
                        # NOTE (mristin, 2023-02-27):
                        # Greenery expects the characters to be in Unicode and not escaped.
                        translated_for_greenery = (
                            _undo_escaping_backslash_x_u_and_U_in_pattern(
                                pattern_constraint.pattern
                            )
                        )

                        try:
                            parsed = greenery.parse(translated_for_greenery)
                        except Exception as exception:
                            if translated_for_greenery == pattern_constraint.pattern:
                                return None, (
                                    f"The greenery failed to parse "
                                    f"the pattern {translated_for_greenery!r}: "
                                    f"{exception}"
                                )
                            else:
                                return None, (
                                    f"The greenery failed to parse "
                                    f"the pattern {translated_for_greenery!r} "
                                    f"(which was originally "
                                    f"{pattern_constraint.pattern!r}): {exception}"
                                )

                        if merger is None:
                            merger = parsed
                        else:
                            merger = merger & parsed

                    assert merger is not None

                    translated_pattern, error = _translate_pattern(str(merger))
                    if error is not None:
                        return None, error

                assert translated_pattern is not None
                pattern = translated_pattern

    if (min_length is not None) or (max_length is not None) or (pattern is not None):
        restriction = _SimpleTypeRestriction(
            min_length=min_length, max_length=max_length, pattern=pattern
        )

    return (
        _SimpleType(tajp=_PRIMITIVE_MAP[primitive_type], restriction=restriction),
        None,
    )


class _TypeElementOrTypeIdentifier:
    """
    Represent a rendering of a type annotation.

    A type annotation can either be represented as a ``type`` attribute of an element,
    or as a proper ``xs:simpleType`` or ``xs:complexType`` element.

    For example:

    .. code-block:: xml

        <xs:element name="something" type="xs:string" />

    or:

    .. code-block:: xml

        <xs:element name="someLanguage">
            <xs:simpleType>
                <xs:restriction base="xs:string">
                    <xs:minLength value="1" />
                </xs:restriction>
            </xs:simpleType>
        </xs:element>
    """

    tajp: Final[Optional[str]]

    element: Final[Optional[ET.Element]]

    @require(lambda tajp, element: (tajp is not None) ^ (element is not None))
    def __init__(
        self, tajp: Optional[str] = None, element: Optional[ET.Element] = None
    ) -> None:
        self.tajp = tajp
        self.element = element


def _value_to_type_element_or_type_identifier(
    type_annotation: intermediate.TypeAnnotationExceptOptional,
    constraints_by_value: infer_for_schema.ConstraintsByValue,
) -> Tuple[Optional[_TypeElementOrTypeIdentifier], Optional[str]]:
    """
    Translate the given type annotation to XSD.

    Return the either type element or type identifier, or an error, if any.
    """
    if isinstance(type_annotation, intermediate.OurTypeAnnotation):
        if type_annotation.our_type.name == "Value_data_type":
            # NOTE (mristin):
            # Please see the note regarding the value data type above for the
            # explanation why we hard-wire the ``Value_data_type`` here.
            return _TypeElementOrTypeIdentifier(tajp="valueDataType"), None

    primitive_type = intermediate.try_primitive_type(type_annotation)

    if primitive_type is not None:
        simple_type, simple_type_error = _translate_to_simple_type(
            primitive_type=primitive_type,
            constraints=constraints_by_value.get(type_annotation, None),
        )
        if simple_type_error is not None:
            return None, (
                f"Failed to translate the type annotation {type_annotation} "
                f"to xs:simpleType: {simple_type_error}"
            )

        assert simple_type is not None

        if simple_type.restriction is None:
            return _TypeElementOrTypeIdentifier(tajp=simple_type.tajp), None
        else:
            xs_simple_type = ET.Element("xs:simpleType")

            xs_restriction = ET.SubElement(
                xs_simple_type, "xs:restriction", {"base": simple_type.tajp}
            )

            # NOTE (mristin):
            # We define the pattern first for the legacy reasons -- already published
            # XSD schemas defined the pattern first, so we want to keep the diffs
            # minimal even though it intuitively makes more sense to start with
            # length.

            if simple_type.restriction.pattern is not None:
                ET.SubElement(
                    xs_restriction,
                    "xs:pattern",
                    {"value": simple_type.restriction.pattern},
                )

            if simple_type.restriction is not None:
                if simple_type.restriction.min_length is not None:
                    ET.SubElement(
                        xs_restriction,
                        "xs:minLength",
                        {"value": str(simple_type.restriction.min_length)},
                    )

                if simple_type.restriction.max_length is not None:
                    ET.SubElement(
                        xs_restriction,
                        "xs:maxLength",
                        {"value": str(simple_type.restriction.max_length)},
                    )

            return _TypeElementOrTypeIdentifier(element=xs_simple_type), None
    else:
        if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("This execution path must have been handled before.")

        elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
            our_type = type_annotation.our_type

            if isinstance(our_type, intermediate.Enumeration):
                return (
                    _TypeElementOrTypeIdentifier(
                        tajp=xsd_naming.type_name(our_type.name)
                    ),
                    None,
                )

            elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError(
                    "This execution path must have been handled before."
                )

            elif isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                # NOTE (mristin):
                # We generate choices only if there are at least one concrete descendant.
                # Otherwise, the choice is not generated. Hence, we need to reference
                # a choice only if there is actually one.
                #
                # This is especially necessary for abstract classes with no descendants
                # which we still want to include in the schema. We simply generate an empty
                # element in the schema for such abstract classes without descendants.

                if len(our_type.concrete_descendants) > 0:
                    xs_complex_type = ET.Element("xs:complexType")
                    xs_sequence = ET.SubElement(xs_complex_type, "xs:sequence")

                    ET.SubElement(
                        xs_sequence,
                        "xs:group",
                        {"ref": xsd_naming.choice_group_name(our_type.name)},
                    )

                    return (
                        _TypeElementOrTypeIdentifier(
                            element=xs_complex_type,
                        ),
                        None,
                    )

                else:
                    return (
                        _TypeElementOrTypeIdentifier(
                            tajp=xsd_naming.type_name(our_type.name)
                        ),
                        None,
                    )
            else:
                # noinspection PyTypeChecker
                assert_never(our_type)

        elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
            assert not isinstance(
                type_annotation.items, intermediate.OptionalTypeAnnotation
            ), (
                "(mristin, 2026-05-08): Only lists of non-optionals are supported "
                "at the moment. If you see this, please contact the developers."
            )

            xs_complex_type = ET.Element("xs:complexType")
            xs_sequence = ET.SubElement(xs_complex_type, "xs:sequence")

            item_element: ET.Element

            if isinstance(
                type_annotation.items, intermediate.OurTypeAnnotation
            ) and isinstance(
                type_annotation.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                # NOTE (mristin):
                # All the other cases introduce ``<v>`` element to capture the items,
                # but lists of classes use the name of the class, so we have to handle
                # it here differently.

                # NOTE (mristin):
                # We generate choices only if there are at least one concrete descendant.
                # Otherwise, the choice is not generated. Hence, we need to reference
                # a choice only if there is actually one.
                #
                # This is especially necessary for abstract classes with no descendants
                # which we still want to include in the schema. We simply generate an empty
                # element in the schema for such abstract classes without descendants.

                if len(type_annotation.items.our_type.concrete_descendants) > 0:
                    item_element = ET.Element(
                        "xs:group",
                        {
                            "ref": xsd_naming.choice_group_name(
                                type_annotation.items.our_type.name
                            )
                        },
                    )
                else:
                    item_element = ET.Element(
                        "xs:element",
                        {
                            "name": naming.xml_class_name(
                                type_annotation.items.our_type.name
                            ),
                            "type": xsd_naming.type_name(
                                type_annotation.items.our_type.name
                            ),
                        },
                    )
            else:
                (
                    items_type_element_or_identifier,
                    translation_error,
                ) = _value_to_type_element_or_type_identifier(
                    type_annotation=type_annotation.items,
                    constraints_by_value=constraints_by_value,
                )

                if translation_error is not None:
                    return None, (
                        f"Failed to translate the type annotation {type_annotation} to "
                        f"a type element or a type identifier: {translation_error}"
                    )

                assert items_type_element_or_identifier is not None

                item_element = ET.Element("xs:element", {"name": "v"})

                if items_type_element_or_identifier.tajp is not None:
                    item_element.attrib["type"] = items_type_element_or_identifier.tajp

                else:
                    assert items_type_element_or_identifier.element is not None

                    item_element.append(items_type_element_or_identifier.element)

            xs_sequence.append(item_element)

            min_occurs = "0"
            max_occurs = "unbounded"

            constraints = constraints_by_value.get(type_annotation, None)
            if constraints is not None and constraints.len_constraint is not None:
                if constraints.len_constraint.min_value is not None:
                    min_occurs = str(constraints.len_constraint.min_value)

                if constraints.len_constraint.max_value is not None:
                    max_occurs = str(constraints.len_constraint.max_value)

            item_element.attrib["minOccurs"] = min_occurs
            item_element.attrib["maxOccurs"] = max_occurs

            return _TypeElementOrTypeIdentifier(element=xs_complex_type), None

        elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
            # NOTE (mristin):
            # Tuples of classes are tagged by the class name, exactly as we do for
            # the lists above, so there is no conflict there: different classes give
            # different tags, and if the very same class appears twice (directly, or
            # indirectly through a choice group of an abstract class), the tag and
            # the type simply repeat identically, which is unproblematic -- XSD's
            # Element Declarations Consistent constraint (section 3.8.6) only
            # forbids the *same* tag from ever mapping to *different* types, and
            # ``xs:sequence`` fixes the order of the particles regardless, so there
            # is no ambiguity to resolve.
            #
            # However, we can *not* tag every primitive/constrained-primitive/
            # enumeration-literal item with a plain ``<v>``, as we do for the (always
            # homogeneous) lists above. A tuple can be heterogeneous, *e.g.*,
            # ``Tuple[str, int]``, and reusing ``<v>`` for both would violate the
            # very same Element Declarations Consistent constraint -- two element
            # particles in the same content model may not share a name but have
            # different types, *regardless of their order in the sequence*. We
            # verified this with a minimal schema
            # (``<xs:sequence><xs:element name="v" type="xs:string"/>
            # <xs:element name="v" type="xs:long"/></xs:sequence>``), which the
            # ``xmlschema`` library rejects outright.
            #
            # We therefore always disambiguate these value items with a 1-based
            # index over their position in the tuple (``v1``, ``v2``, ...), even
            # when a single index would not strictly need it, for the sake of
            # simplicity and predictability.

            xs_complex_type = ET.Element("xs:complexType")
            xs_sequence = ET.SubElement(xs_complex_type, "xs:sequence")

            for i, item_type_annotation in enumerate(type_annotation.items):
                assert isinstance(
                    item_type_annotation, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    "(mristin): Only tuples of atomic types (primitives, "
                    "constrained primitives, classes and enumerations) are "
                    "supported at the moment; this should have been caught before "
                    "by intermediate._translate._verify_only_simple_type_patterns. "
                    "If you see this, please contact the developers."
                )

                if isinstance(
                    item_type_annotation, intermediate.OurTypeAnnotation
                ) and isinstance(
                    item_type_annotation.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    if len(item_type_annotation.our_type.concrete_descendants) > 0:
                        item_element = ET.Element(
                            "xs:group",
                            {
                                "ref": xsd_naming.choice_group_name(
                                    item_type_annotation.our_type.name
                                )
                            },
                        )
                    else:
                        item_element = ET.Element(
                            "xs:element",
                            {
                                "name": naming.xml_class_name(
                                    item_type_annotation.our_type.name
                                ),
                                "type": xsd_naming.type_name(
                                    item_type_annotation.our_type.name
                                ),
                            },
                        )
                else:
                    (
                        item_type_element_or_identifier,
                        translation_error,
                    ) = _value_to_type_element_or_type_identifier(
                        type_annotation=item_type_annotation,
                        constraints_by_value=constraints_by_value,
                    )

                    if translation_error is not None:
                        return None, (
                            f"Failed to translate the type annotation "
                            f"{type_annotation} to "
                            f"a type element or a type identifier: "
                            f"{translation_error}"
                        )

                    assert item_type_element_or_identifier is not None

                    item_element = ET.Element("xs:element", {"name": f"v{i + 1}"})

                    if item_type_element_or_identifier.tajp is not None:
                        item_element.attrib[
                            "type"
                        ] = item_type_element_or_identifier.tajp
                    else:
                        assert item_type_element_or_identifier.element is not None
                        item_element.append(item_type_element_or_identifier.element)

                xs_sequence.append(item_element)

            return _TypeElementOrTypeIdentifier(element=xs_complex_type), None

        else:
            # noinspection PyTypeChecker
            assert_never(type_annotation)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _define_properties(
    cls: intermediate.ClassUnion,
    constraints_by_class: Mapping[
        intermediate.ClassUnion, infer_for_schema.ConstraintsByValue
    ],
) -> Tuple[Optional[List[ET.Element]], Optional[List[Error]]]:
    """Define the properties of the ``cls`` as a sequence of tags."""
    sequence = []  # type: List[ET.Element]
    errors = []  # type: List[Error]

    constraints_by_value = constraints_by_class[cls]

    for prop in cls.properties:
        # NOTE (mristin):
        # While we allow our classes to tighten the constraints from the parents, XSD
        # does not allow us to *easily* tighten the constraints in a group.
        #
        # Instead of making it really complicated, we simply ignore the tightening
        # of the constraints in the children classes.
        #
        # If we ever want to implement this feature, we have to define three intermediate
        # structures:
        # 1) Abstract parent class,
        # 2) Restricted class, only tightening the elements with
        #    ``<xs:restriction base="...">``, and
        # 3) Extended class which includes properties specified only for the class with
        #    ``<xs:extension base="...">``.

        if prop.specified_for is not cls:
            continue

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        xs_element = ET.Element("xs:element", {"name": prop.xml_name})

        # fmt: off
        (
            type_element_or_identifier,
            type_error
        ) = _value_to_type_element_or_type_identifier(
            type_annotation=type_anno,
            constraints_by_value=constraints_by_value
        )
        # fmt: on

        if type_error is not None:
            errors.append(
                Error(
                    prop.parsed.node,
                    f"Failed to translate the type annotation, "
                    f"{type_anno}, of the property {prop.name} "
                    f"to XSD: {type_error}",
                )
            )
            continue

        assert type_element_or_identifier is not None

        if type_element_or_identifier.tajp is not None:
            xs_element.attrib["type"] = type_element_or_identifier.tajp
        else:
            assert type_element_or_identifier.element is not None

            xs_element.append(type_element_or_identifier.element)

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            xs_element.attrib["minOccurs"] = "0"
            xs_element.attrib["maxOccurs"] = "1"

        sequence.append(xs_element)

    if len(errors) > 0:
        return None, errors

    return sequence, None


def _generate_xs_group_for_class(
    cls: intermediate.ClassUnion,
    constraints_by_class: Mapping[
        intermediate.ClassUnion, infer_for_schema.ConstraintsByValue
    ],
) -> Tuple[Optional[ET.Element], Optional[Error]]:
    """Generate the ``xs:group`` representation of the class properties."""
    properties, properties_errors = _define_properties(
        cls=cls, constraints_by_class=constraints_by_class
    )

    if properties_errors is not None:
        return None, Error(
            cls.parsed.node,
            f"Failed to generate xs:group for the class {cls.name!r}",
            properties_errors,
        )

    assert properties is not None

    xs_sequence = ET.Element("xs:sequence")
    for inheritance in cls.inheritances:
        inheritance_xs_group = ET.Element(
            "xs:group", {"ref": xsd_naming.group_name(inheritance.name)}
        )
        xs_sequence.append(inheritance_xs_group)

    xs_sequence.extend(properties)

    xs_group = ET.Element("xs:group", {"name": xsd_naming.group_name(cls.name)})
    xs_group.append(xs_sequence)

    return xs_group, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _define_for_class(
    cls: intermediate.ClassUnion,
    constraints_by_class: Mapping[
        intermediate.ClassUnion, infer_for_schema.ConstraintsByValue
    ],
) -> Tuple[Optional[List[ET.Element]], Optional[Error]]:
    """
    Generate the definitions for the class ``cls``.

    The root element is to be *extended* with the resulting list.
    """
    # NOTE (mristin, 2022-03-30):
    # We define each set of properties in a group. Then we reference these groups
    # among the complex types.
    # See: https://stackoverflow.com/questions/1198755/xml-schemas-with-multiple-inheritance

    xs_group, xs_group_error = _generate_xs_group_for_class(
        cls=cls, constraints_by_class=constraints_by_class
    )
    if xs_group_error is not None:
        return None, xs_group_error

    assert xs_group is not None

    xs_group_ref = ET.Element("xs:group", {"ref": xsd_naming.group_name(cls.name)})

    xs_sequence = ET.Element("xs:sequence")
    xs_sequence.append(xs_group_ref)

    complex_type = ET.Element(
        "xs:complexType", {"name": xsd_naming.type_name(cls.name)}
    )
    complex_type.append(xs_sequence)

    return [xs_group, complex_type], None


@require(lambda cls: len(cls.concrete_descendants) > 0)
def _generate_choice_group(cls: intermediate.ClassUnion) -> ET.Element:
    """Generate a group that defines a choice of concrete descendants."""
    xs_choice = ET.Element("xs:choice")

    if isinstance(cls, intermediate.ConcreteClass):
        xs_choice.append(
            ET.Element(
                "xs:element",
                {
                    "name": naming.xml_class_name(cls.name),
                    "type": xsd_naming.type_name(cls.name),
                },
            )
        )

    for descendant in cls.concrete_descendants:
        xs_choice.append(
            ET.Element(
                "xs:element",
                {
                    "name": naming.xml_class_name(descendant.name),
                    "type": xsd_naming.type_name(descendant.name),
                },
            )
        )

    xs_group = ET.Element("xs:group", {"name": xsd_naming.choice_group_name(cls.name)})
    xs_group.append(xs_choice)
    return xs_group


_WHITESPACE_RE = re.compile(r"\s+")


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _retrieve_implementation_specific_elements(
    cls: intermediate.ClassUnion,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[ET.Element]], Optional[List[Error]]]:
    """Parse the elements from the implementation-specific snippet."""
    implementation_key = specific_implementations.ImplementationKey(f"{cls.name}.xml")

    text = spec_impls.get(implementation_key, None)
    if text is None:
        return None, [
            Error(
                cls.parsed.node,
                f"The implementation is missing "
                f"for the implementation-specific class: {implementation_key}",
            )
        ]

    implementation_root: ET.Element

    try:
        implementation_root = ET.fromstring(text)
    except Exception as err:
        return None, [
            Error(
                cls.parsed.node,
                f"Failed to parse the XML out of "
                f"the specific implementation {implementation_key}: {err}",
            )
        ]

    errors = []  # type: List[Error]
    for descendant in implementation_root.iter():
        if descendant.text is not None and not _WHITESPACE_RE.fullmatch(
            descendant.text
        ):
            errors.append(
                Error(
                    cls.parsed.node,
                    f"Unexpected text "
                    f"in the specific implementation {implementation_key} "
                    f"in an element with tag {descendant.tag!r}: {descendant.text!r}",
                )
            )
            continue

        if descendant.tail is not None and not _WHITESPACE_RE.fullmatch(
            descendant.tail
        ):
            errors.append(
                Error(
                    cls.parsed.node,
                    f"Unexpected tail text "
                    f"in the specific implementation {implementation_key} "
                    f"in an element with tag {descendant.tag!r}: {descendant.tail!r}",
                )
            )
            continue

    if len(errors) > 0:
        return None, errors

    # Ignore the implementation root since it defines a partial schema
    elements = []  # type: List[ET.Element]
    for child in implementation_root:
        elements.append(child)

    return elements, None


def _sort_by_tags_and_names_in_place(root: ET.Element) -> None:
    """
    Sort the children elements by tag and name attribute in place.

    This makes diffing and searching in the schema a bit easier.
    """
    groups = []  # type: List[ET.Element]
    simple_types = []  # type: List[ET.Element]
    complex_types = []  # type: List[ET.Element]
    miscellaneous = []  # type: List[ET.Element]
    elements = []  # type: List[ET.Element]

    for child in root:
        if child.tag == "xs:group":
            groups.append(child)
        elif child.tag == "xs:simpleType":
            simple_types.append(child)
        elif child.tag == "xs:complexType":
            complex_types.append(child)
        elif child.tag == "xs:element":
            elements.append(child)
        else:
            miscellaneous.append(child)

    for element_list in [groups, simple_types, complex_types, miscellaneous, elements]:
        element_list.sort(key=lambda elt: elt.attrib.get("name", ""))

    children = groups + simple_types + complex_types + elements + miscellaneous

    assert len(children) == len(root)
    root[:] = children


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate the XML Schema Definition (XSD) based on the ``symbol_table."""
    root_element_key = specific_implementations.ImplementationKey("root_element.xml")

    root_element_as_text = spec_impls.get(root_element_key, None)
    if root_element_as_text is None:
        return None, [
            Error(
                None,
                f"The implementation snippet for the root element "
                f"is missing: {root_element_key}",
            )
        ]

    root: ET.Element
    try:
        root = ET.fromstring(root_element_as_text)
    except ET.ParseError as err:
        return None, [
            Error(
                None, f"Failed to parse the root element from {root_element_key}: {err}"
            )
        ]

    # NOTE (mristin):
    # We need to use minidom to extract the ``xmlns`` property as ElementTree removes
    # it.
    # noinspection PyUnresolvedReferences
    minidom_doc = xml.dom.minidom.parseString(root_element_as_text)

    assert minidom_doc.documentElement is not None, (
        "We expect the root element, which is stringified from ET, to be parsed "
        "successfully."
    )

    if not minidom_doc.documentElement.hasAttribute("xmlns"):
        return None, [
            Error(
                None,
                f"The implementation snippet for the root element "
                f"is missing the 'xmlns' attribute: {root_element_key}",
            )
        ]

    xmlns = minidom_doc.documentElement.getAttribute("xmlns")

    if xmlns != symbol_table.meta_model.xml_namespace:
        return None, [
            Error(
                None,
                f"The 'xmlns' attribute of the implementation snippet "
                f"{root_element_key} for the root element "
                f"and the '__xml_namespace__' of the meta-model "
                f"do not coincide: "
                f"{xmlns!r} != {symbol_table.meta_model.xml_namespace!r}",
            )
        ]

    if not minidom_doc.documentElement.hasAttribute("targetNamespace"):
        return None, [
            Error(
                None,
                f"The implementation snippet for the root element "
                f"is missing the 'targetNamespace' attribute: {root_element_key}",
            )
        ]

    target_namespace = minidom_doc.documentElement.getAttribute("targetNamespace")
    if target_namespace != symbol_table.meta_model.xml_namespace:
        return None, [
            Error(
                None,
                f"The 'targetNamespace' attribute of the implementation snippet "
                f"{root_element_key} for the root element "
                f"and the '__xml_namespace__' of the meta-model "
                f"do not coincide: "
                f"{target_namespace!r} != {symbol_table.meta_model.xml_namespace!r}",
            )
        ]

    assert root is not None

    errors = []  # type: List[Error]

    # NOTE (mristin, 2022-04-09):
    # We remove any whitespace tail and text in all the tags, and make sure there is no
    # unexpected text anywhere.
    for element in root.iter():
        if element.text is not None:
            if _WHITESPACE_RE.fullmatch(element.text):
                element.text = None
            else:
                errors.append(
                    Error(
                        None,
                        f"Unexpected text in an element with tag {element.tag!r} "
                        f"from the snippet {root_element_key!r}: {element.text!r}",
                    )
                )

        if element.tail is not None:
            if _WHITESPACE_RE.fullmatch(element.tail):
                element.tail = None
            else:
                errors.append(
                    Error(
                        None,
                        f"Unexpected tail in an element with tag {element.tag!r} "
                        f"from the snippet {root_element_key!r}: {element.tail!r}",
                    )
                )

    if len(errors) > 0:
        return None, errors

    constraints_by_class, some_errors = infer_for_schema.infer_constraints_by_class(
        symbol_table=symbol_table
    )

    if some_errors is not None:
        errors.extend(some_errors)

    # NOTE (mristin):
    # We provide an internal data type ``valueDataType`` corresponding to any XSD
    # atomic type specified through ``DataTypeDefXsd``. We need this type because
    # ``Value_data_type`` is hard-wired to it.
    #
    # We could have made ``Value_data_type`` implementation-specific and defined its
    # representation manually as a snippet, including ``valueDataType``. However,
    # we decided against that. Doing so would create a major hurdle for other code
    # and test-data generators, which can currently treat ``Value_data_type`` simply
    # as a string. Therefore, we accept a somewhat hackier XSD generator rather than
    # complicating the other generators.
    #
    # If the semantics of ``Value_data_type`` ever change, or if the type is
    # renamed, be careful to preserve backward compatibility here. You will
    # probably want to distinguish between different meta-model versions and act
    # accordingly. At that point, it might also make sense to move this schema
    # generator into a separate repository and pin it to a particular range of
    # meta-model versions.

    value_data_type_cls = symbol_table.find_our_type(Identifier("Value_data_type"))

    if value_data_type_cls is None:
        # NOTE (mristin):
        # The meta-model does not need the value data type so we do not have to do
        # anything about it.
        pass

    elif not isinstance(value_data_type_cls, intermediate.ConstrainedPrimitive):
        errors.append(
            Error(
                None,
                f"XSD generator expected ``Value_data_type`` to be "
                f"a constrained primitive,  but got: {type(value_data_type_cls)}",
            )
        )
    elif value_data_type_cls.constrainee != intermediate.PrimitiveType.STR:
        errors.append(
            Error(
                None,
                f"XSD generator expected ``Value_data_type`` to be a constrained "
                f"primitive of strings, "
                f"but got: {value_data_type_cls.constrainee}",
            )
        )
    else:
        # Our type ``Value_data_type`` is as expected.
        pass

    if len(errors) > 0:
        return None, errors

    assert constraints_by_class is not None

    ids_of_our_types_in_properties = (
        intermediate.collect_ids_of_our_types_in_properties(symbol_table=symbol_table)
    )

    # region Specify ``valueDataType``

    if value_data_type_cls is not None:
        # NOTE (mristin):
        # Please see the note regarding the value data type above for the
        # explanation why we hard-wire the ``Value_data_type`` here.

        value_data_type_element = ET.Element(
            "xs:simpleType", attrib={"name": "valueDataType"}
        )

        value_data_type_element.append(
            ET.Element(
                "xs:restriction",
                attrib={"base": "xs:string"},
            )
        )

        root.append(value_data_type_element)

    # endregion

    for our_type in symbol_table.our_types:
        if our_type.name == "Value_data_type":
            # NOTE (mristin):
            # Please see the note regarding the value data type above for the
            # explanation why we hard-wire the ``Value_data_type`` here.
            continue

        elements: Optional[List[ET.Element]]

        if (
            isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            )
            and our_type.is_implementation_specific
        ):
            elements, impl_spec_errors = _retrieve_implementation_specific_elements(
                cls=our_type, spec_impls=spec_impls
            )
            if impl_spec_errors is not None:
                errors.extend(impl_spec_errors)
                continue

            assert elements is not None
        else:
            if isinstance(our_type, intermediate.Enumeration):
                if id(our_type) not in ids_of_our_types_in_properties:
                    continue

                elements = _define_for_enumeration(enumeration=our_type)

            elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                # NOTE (mristin, 2022-03-30):
                # We in-line the constraints from the constrained primitives directly
                # in the properties. We do not want to introduce separate definitions
                # for them as that would make it more difficult for downstream code
                # generators to generate meaningful code.

                continue

            elif isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                elements, definition_error = _define_for_class(
                    cls=our_type, constraints_by_class=constraints_by_class
                )

                if definition_error is not None:
                    errors.append(definition_error)
                    continue

                assert elements is not None

                if len(our_type.concrete_descendants) > 0:
                    choice_group = _generate_choice_group(cls=our_type)
                    elements.append(choice_group)
            else:
                # noinspection PyTypeChecker
                assert_never(our_type)

        assert elements is not None
        root.extend(elements)

    if len(errors) > 0:
        return None, errors

    # Tag name 🠒 (name 🠒 element)
    observed_definitions = dict(
        dict()
    )  # type: MutableMapping[str, MutableMapping[str, ET.Element]]

    for element in root:
        name = element.attrib.get("name", None)
        if name is None:
            continue

        observed_for_tag = observed_definitions.get(element.tag, None)
        if observed_for_tag is None:
            observed_for_tag = dict()
            observed_definitions[element.tag] = observed_for_tag

        observed_element = observed_for_tag.get(name, None)
        if observed_element is not None:
            ours = ET.tostring(element, encoding="unicode", method="xml")
            theirs = ET.tostring(observed_element, encoding="unicode", method="xml")

            errors.append(
                Error(
                    None,
                    f"There are conflicting definitions in the schema "
                    f"with the name {name!r}:\n"
                    f"\n"
                    f"{ours}\n"
                    f"\n"
                    f"and\n"
                    f"\n"
                    f"{theirs}",
                )
            )
        else:
            observed_for_tag[name] = element

    if len(errors) > 0:
        return None, errors

    _sort_by_tags_and_names_in_place(root)

    # NOTE (mristin, 2022-03-30):
    # For some unknown reason, ElementTree erases the xmlns property of the root
    # element. Therefore, we need to add it here manually.
    root.attrib["xmlns"] = xmlns

    text = ET.tostring(root, encoding="unicode", method="xml")

    # NOTE (mristin, 2021-11-23):
    # This approach is slow, but effective. As long as the meta-model is not too big,
    # this should work.
    # noinspection PyUnresolvedReferences
    pretty_text = xml.dom.minidom.parseString(text).toprettyxml(indent="  ")

    return pretty_text, None


def execute(context: run.Context, stdout: TextIO, stderr: TextIO) -> int:
    """Generate the code."""
    code, errors = _generate(
        symbol_table=context.symbol_table, spec_impls=context.spec_impls
    )

    if errors is not None:
        run.write_error_report(
            message=f"Failed to generate the XML Schema Definition "
            f"based on {context.model_path}",
            errors=[context.lineno_columner.error_message(error) for error in errors],
            stderr=stderr,
        )
        return 1

    assert code is not None

    pth = context.output_dir / "schema.xsd"
    try:
        pth.write_text(code, encoding="utf-8")
    except Exception as exception:
        run.write_error_report(
            message=f"Failed to write the XML Schema Definition to {pth}",
            errors=[str(exception)],
            stderr=stderr,
        )
        return 1

    stdout.write(f"Code generated to: {context.output_dir}\n")
    return 0
