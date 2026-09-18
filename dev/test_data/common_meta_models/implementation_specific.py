from enum import Enum
from typing import List, Optional

from icontract import DBC, invariant


# region Verification functions


@verification
@implementation_specific
def has_balanced_brackets(text: str) -> bool:
    """Check that the square brackets in :paramref:`text` are balanced."""
    # NOTE (mristin):
    # This implementation will not be transpiled, but is given here as reference.
    depth = 0
    for character in text:
        if character == "[":
            depth = depth + 1
        elif character == "]":
            depth = depth - 1
            if depth < 0:
                return False

    return depth == 0


@verification
@implementation_specific
def texts_are_unique(texts: List[str]) -> bool:
    """Check that the :paramref:`texts` do not repeat."""
    # NOTE (mristin):
    # This implementation will not be transpiled, but is given here as reference.
    text_set = set()
    for text in texts:
        if text in text_set:
            return False

        text_set.add(text)

    return True


@verification
@implementation_specific
def items_have_unique_labels(items: List["Item"]) -> bool:
    """Check that :attr:`Item.label`'s of the :paramref:`items` do not repeat."""
    # NOTE (mristin):
    # This implementation will not be transpiled, but is given here as reference.
    label_set = set()
    for item in items:
        if item.label in label_set:
            return False

        label_set.add(item.label)

    return True


# endregion


class Color(Enum):
    Red = "Red"
    Green = "Green"


# NOTE (mristin):
# The invariant is defined on the abstract class so that it propagates to all
# the descendants, and the implementation-specific verification function is thus
# called on more than one class.
@invariant(
    lambda self: has_balanced_brackets(self.label),
    "The square brackets in the label must be balanced.",
)
@abstract
@serialization(with_model_type=True)
class Item(DBC):
    label: str

    # NOTE (mristin):
    # This method is specified on an abstract class, so the snippet is expected
    # under the key of the class which *specified* it, and re-used in all
    # the concrete descendants.
    @implementation_specific
    @non_mutating
    def describe(self) -> str:
        """Render a human-readable description of the item."""
        # NOTE (mristin):
        # This implementation will not be transpiled, but is given here as reference.
        return self.label

    def __init__(self, label: str) -> None:
        self.label = label


class Box(Item):
    color: Optional["Color"]

    # NOTE (mristin):
    # This method follows the ``X_or_default`` convention, so the generated unit
    # tests are expected to call it without any arguments.
    @implementation_specific
    @non_mutating
    def color_or_default(self) -> "Color":
        """Return the :attr:`color` if set, or the default otherwise."""
        # NOTE (mristin):
        # This implementation will not be transpiled, but is given here as reference.
        return self.color if self.color is not None else Color.Red

    # NOTE (mristin):
    # This method is non-mutating, takes an optional argument and returns
    # an enumeration literal.
    @implementation_specific
    @non_mutating
    def resolve_color(self, fallback: Optional["Color"]) -> "Color":
        """Return the :attr:`color`, or the :paramref:`fallback` if not set."""
        # NOTE (mristin):
        # This implementation will not be transpiled, but is given here as reference.
        if self.color is not None:
            return self.color

        return fallback if fallback is not None else Color.Red

    # NOTE (mristin):
    # This method mutates the instance and returns nothing.
    @implementation_specific
    def relabel(self, new_label: str) -> None:
        """Set the :attr:`label` to :paramref:`new_label`."""
        # NOTE (mristin):
        # This implementation will not be transpiled, but is given here as reference.
        self.label = new_label

    def __init__(self, label: str, color: Optional["Color"] = None) -> None:
        Item.__init__(self, label)
        self.color = color


class Bag(Item):
    tags: List[str]

    def __init__(self, label: str, tags: List[str]) -> None:
        Item.__init__(self, label)
        self.tags = tags


@invariant(lambda self: texts_are_unique(self.names), "The names must not repeat.")
@invariant(
    lambda self: items_have_unique_labels(self.items), "The labels must not repeat."
)
class Container(DBC):
    names: List[str]
    items: List["Item"]

    def __init__(self, names: List[str], items: List["Item"]) -> None:
        self.names = names
        self.items = items


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
