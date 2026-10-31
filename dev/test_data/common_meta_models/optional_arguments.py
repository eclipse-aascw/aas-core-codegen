from enum import Enum
from typing import List, Optional, Sequence

from icontract import DBC, invariant


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"
    Gamma = "gamma"


class Item(DBC):
    name: str
    note: Optional[str]

    def __init__(self, name: str, note: Optional[str] = None) -> None:
        self.name = name
        self.note = note


@verification
def text_is_short(text: Optional[str]) -> bool:
    """Check the optional string argument."""
    return text is None or len(text) <= 10


@verification
def text_is_not_banned(text: Optional[str]) -> bool:
    """Check the optional string argument compared for equality."""
    return text is None or text != "banned"


@verification
def forwards_text(text: Optional[str]) -> bool:
    """Check the optional argument passed on to another verification function."""
    return text_is_not_banned(text)


@verification
def text_is_given(text: Optional[str]) -> bool:
    """Check the negated nullness check of the optional argument."""
    return not (text is None)


@verification
def number_is_small(number: Optional[int]) -> bool:
    """Check the optional integer argument."""
    return number is None or number < 10


@verification
def item_has_name(item: Optional[Item]) -> bool:
    """Check the optional instance argument."""
    return item is None or len(item.name) > 0


@verification
def texts_are_few(texts: Optional[Sequence[str]]) -> bool:
    """Check the optional list argument."""
    return texts is None or len(texts) <= 2


@verification
def kind_is_not_gamma(kind: Optional[Kind]) -> bool:
    """Check the optional enumeration argument."""
    return kind is None or kind != Kind.Gamma


@verification
def note_is_short(item: Item) -> bool:
    """Check the local variable holding an optional property."""
    note = item.note
    return note is None or len(note) <= 5


@invariant(lambda self: text_is_short(self.optional_text), "Text must be short")
@invariant(lambda self: forwards_text(self.optional_text), "Text must not be banned")
@invariant(lambda self: number_is_small(self.optional_number), "Number must be small")
@invariant(
    lambda self: item_has_name(self.optional_item), "Optional item must have a name"
)
@invariant(lambda self: texts_are_few(self.optional_texts), "Texts must be few")
@invariant(lambda self: kind_is_not_gamma(self.optional_kind), "Kind must not be gamma")
@invariant(lambda self: note_is_short(self.item), "Note of the item must be short")
class Something(DBC):
    item: Item
    optional_text: Optional[str]
    optional_number: Optional[int]
    optional_item: Optional[Item]
    optional_texts: Optional[List[str]]
    optional_kind: Optional[Kind]

    def __init__(
        self,
        item: Item,
        optional_text: Optional[str] = None,
        optional_number: Optional[int] = None,
        optional_item: Optional[Item] = None,
        optional_texts: Optional[List[str]] = None,
        optional_kind: Optional[Kind] = None,
    ) -> None:
        self.item = item
        self.optional_text = optional_text
        self.optional_number = optional_number
        self.optional_item = optional_item
        self.optional_texts = optional_texts
        self.optional_kind = optional_kind


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
