from enum import Enum
from typing import List

from icontract import DBC, invariant


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Item(DBC):
    texts: List[str]

    def __init__(self, texts: List[str]) -> None:
        self.texts = texts


@verification
def first_text_is_not_empty(texts: List[str]) -> bool:
    """Check the for-each with an unconditional early return."""
    for text in texts:
        return len(text) > 0

    return True


@verification
def no_number_is_zero(numbers: List[int]) -> bool:
    """Check the for-each with an early return in a switch."""
    for number in numbers:
        if number == 0:
            return False

    return True


@verification
def no_number_is_minus_one(numbers: List[int]) -> bool:
    """Check the for-range with a variable defined in the body of the loop."""
    for i in range(0, len(numbers)):
        number = numbers[i]
        if number == -1:
            return False

    return True


@verification
def no_number_after_the_first_is_one(numbers: List[int]) -> bool:
    """Check the for-range which does not start at zero."""
    for i in range(1, len(numbers)):
        if numbers[i] == 1:
            return False

    return True


@verification
def sum_is_small(numbers: List[int]) -> bool:
    """Check the for-each which assigns to a variable defined before the loop."""
    total = 0
    for number in numbers:
        total = total + number

    return total < 100


@verification
def no_item_has_an_empty_text(items: List[Item]) -> bool:
    """Check the nested for-each loops."""
    for item in items:
        texts = item.texts
        for text in texts:
            if text == "":
                return False

    return True


@verification
def is_neither_thirteen_nor_unlucky(texts: List[str]) -> bool:
    """Check the loop variable re-used in a sibling loop."""
    for x in texts:
        if x == "thirteen":
            return False

    for x in texts:
        if x == "unlucky":
            return False

    return True


@verification
def alpha_has_no_negative_numbers(kind: Kind, numbers: List[int]) -> bool:
    """Check the for-each in a switch branch."""
    if kind == Kind.Alpha:
        for number in numbers:
            if number == -2:
                return False

    return True


@invariant(
    lambda self: first_text_is_not_empty(self.texts),
    "The first text must not be empty",
)
@invariant(lambda self: no_number_is_zero(self.numbers), "No number is zero")
@invariant(lambda self: no_number_is_minus_one(self.numbers), "No number is minus one")
@invariant(
    lambda self: no_number_after_the_first_is_one(self.numbers),
    "No number after the first is one",
)
@invariant(lambda self: sum_is_small(self.numbers), "Sum of numbers is small")
@invariant(
    lambda self: no_item_has_an_empty_text(self.items),
    "No item has an empty text",
)
@invariant(
    lambda self: is_neither_thirteen_nor_unlucky(self.texts),
    "Neither thirteen nor unlucky",
)
@invariant(
    lambda self: alpha_has_no_negative_numbers(self.kind, self.numbers),
    "Alpha has no minus two",
)
class Something(DBC):
    kind: Kind
    numbers: List[int]
    texts: List[str]
    items: List[Item]

    def __init__(
        self,
        kind: Kind,
        numbers: List[int],
        texts: List[str],
        items: List[Item],
    ) -> None:
        self.kind = kind
        self.numbers = numbers
        self.texts = texts
        self.items = items


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
