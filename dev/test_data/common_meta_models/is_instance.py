from typing import List, Optional, Union

from icontract import DBC, invariant

from aas_core_meta.marker import abstract, serialization, verification


# region Verification functions


@verification
def has_leaf_in_tree(element: "Element") -> bool:
    """
    Check recursively whether there is a leaf in the tree of :paramref:`element`.

    This function tests the narrowing in a conjunction nested in a disjunction,
    and the self-recursion.
    """
    return isinstance(element, Leaf) or (
        isinstance(element, Container)
        and any(has_leaf_in_tree(child) for child in element.children)
    )


@verification
def leaves_in_tree_are_not_empty(element: "Element") -> bool:
    """
    Check recursively that all the leaves in the tree of :paramref:`element`
    have a non-empty text.

    This function tests the narrowing in a chain of implications, and
    the self-recursion.
    """
    return (not isinstance(element, Leaf) or len(element.text) > 0) and (
        not isinstance(element, Container)
        or all(leaves_in_tree_are_not_empty(child) for child in element.children)
    )


@verification
def is_short_leaf_or_no_leaf(element: "Element") -> bool:
    """
    Check that :paramref:`element` is either not a leaf or has a short text.

    This function tests the narrowing in a disjunction of more than two values,
    where the first value is a negated ``isinstance``.
    """
    return (
        not isinstance(element, Leaf)
        or len(element.text) == 0
        or len(element.text) < 16
    )


@verification
def is_container(element: "Element") -> bool:
    """
    Check that :paramref:`element` is a container.

    This function tests ``isinstance`` over a tuple of classes.
    """
    return isinstance(element, (Ordered_container, Unordered_container))


@verification
def is_sorted_ordered_container(element: "Element") -> bool:
    """
    Check that :paramref:`element` is an ordered container which is sorted.

    This function tests the narrowing over two levels of the class hierarchy.
    """
    return (
        isinstance(element, Container)
        and isinstance(element, Ordered_container)
        and element.is_sorted
    )


@verification
def container_has_children(container: "Container") -> bool:
    """Check that :paramref:`container` has at least one child."""
    return len(container.children) > 0


@verification
def is_global_attribute_of_kind_name(value: "Value") -> bool:
    """
    Check that :paramref:`value` refers to a global attribute of kind name.

    This function tests the narrowing of a named union to a class, and then
    the narrowing of a property of that class from another named union to a class.
    """
    return (
        isinstance(value, Attribute_operand)
        and isinstance(value.attribute, Global_attribute)
        and value.attribute.kind == "name"
    )


@verification
def is_string_value(value: "Value") -> bool:
    """
    Check that :paramref:`value` is a string value.

    This function tests ``isinstance`` over a tuple of classes on a named union.
    """
    return isinstance(value, (String_literal, Attribute_operand))


# endregion

# region Class hierarchy


@abstract
@serialization(with_model_type=True)
class Element(DBC):
    identifier: str

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier


class Leaf(Element, DBC):
    text: str

    def __init__(self, identifier: str, text: str) -> None:
        Element.__init__(self, identifier)
        self.text = text


@abstract
class Container(Element, DBC):
    children: List[Element]

    def __init__(self, identifier: str, children: List[Element]) -> None:
        Element.__init__(self, identifier)
        self.children = children


class Ordered_container(Container, DBC):
    is_sorted: bool

    def __init__(
        self, identifier: str, children: List[Element], is_sorted: bool
    ) -> None:
        Container.__init__(self, identifier, children)
        self.is_sorted = is_sorted


class Unordered_container(Container, DBC):
    def __init__(self, identifier: str, children: List[Element]) -> None:
        Container.__init__(self, identifier, children)


# endregion

# region Named unions


@serialization(with_model_type=True)
class Global_attribute(DBC):
    kind: str

    def __init__(self, kind: str) -> None:
        self.kind = kind


@serialization(with_model_type=True)
class Local_attribute(DBC):
    name: str

    def __init__(self, name: str) -> None:
        self.name = name


Attribute_item = Union[Global_attribute, Local_attribute]


@serialization(with_model_type=True)
class Attribute_operand(DBC):
    attribute: Attribute_item

    def __init__(self, attribute: Attribute_item) -> None:
        self.attribute = attribute


@serialization(with_model_type=True)
class String_literal(DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@serialization(with_model_type=True)
class Number_literal(DBC):
    number: float

    def __init__(self, number: float) -> None:
        self.number = number


String_value = Union[String_literal, Attribute_operand]

Value = Union[String_value, Number_literal]

# endregion


# fmt: off
@invariant(
    lambda self:
    not (
        self.optional_element is not None
        and isinstance(self.optional_element, Leaf)
    )
    or len(self.optional_element.text) > 0,
    "The optional element, if a leaf, must have a non-empty text."
)
@invariant(
    lambda self:
    not isinstance(self.root, Container)
    or container_has_children(self.root),
    "The root, if a container, must have children."
)
@invariant(
    lambda self:
    any(
        isinstance(value, String_literal) and value.text == "root"
        for value in self.values
    ),
    "There must be at least one string literal ``root`` among the values."
)
@invariant(
    lambda self:
    all(
        not isinstance(value, Number_literal) or value.number >= 0.0
        for value in self.values
    ),
    "The number literals among the values must be non-negative."
)
@invariant(
    lambda self:
    is_global_attribute_of_kind_name(self.value),
    "The value must be a global attribute of kind name."
)
@invariant(
    lambda self:
    has_leaf_in_tree(self.root),
    "There must be at least one leaf in the tree."
)
# fmt: on
class Something(DBC):
    root: Element
    optional_element: Optional[Element]
    value: Value
    values: List[Value]

    def __init__(
        self,
        root: Element,
        value: Value,
        values: List[Value],
        optional_element: Optional[Element] = None,
    ) -> None:
        self.root = root
        self.value = value
        self.values = values
        self.optional_element = optional_element


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
