"""
Check the interplay between the integers and the lengths.

The integers of the meta-model are 64-bit, while some targets represent the lengths
and the indices with narrower native types, *e.g.*, ``int`` in C#, Java and Go.
"""
from typing import List, Optional, Sequence

from icontract import DBC, invariant


@verification
def count_texts(texts: Sequence[str]) -> int:
    """Check returning a length as an integer."""
    return len(texts)


@verification
def last_position(texts: Sequence[str]) -> int:
    """Check returning an arithmetic over a length as an integer."""
    return len(texts) - 1


@verification
def no_number_is_seven(numbers: Sequence[int], count: int) -> bool:
    """Check reading at the indices which are integers rather than lengths."""
    for i in range(0, count):
        number = numbers[i]
        if number == 7:
            return False

        mirrored = numbers[len(numbers) - 1 - i]
        if mirrored == 7:
            return False

        rotated = numbers[(i + 1) % len(numbers)]
        if rotated == 7:
            return False

    return True


@verification
def no_seven_from(numbers: Sequence[int], start: int) -> bool:
    """
    Check the ranges over the integers with a length as a bound.

    The ``start`` is checked against the bounds before it is used as an index,
    so that the invariant holds up even against integers as large as
    ``2 ** 53``. A negative ``start`` is refused, while a ``start`` beyond
    the numbers leaves nothing to check.
    """
    if start < 0:
        return False

    if start >= len(numbers):
        return True

    for i in range(start, len(numbers)):
        number = numbers[i]
        if number == 7:
            return False

    return all(numbers[i] != 7 for i in range(start, len(numbers)))


@verification
def fill_texts_from_both_ends(texts: List[str], count: int, text: str) -> bool:
    """Check writing at the indices which are integers rather than lengths."""
    for i in range(0, count):
        texts[i] = text
        texts[len(texts) - 1 - i] = text

    return True


@verification
def count_after_reassignment(texts: Sequence[str]) -> int:
    """Check re-assigning a length to an integer and to a length variable."""
    count = 0
    count = len(texts)

    last = len(texts)
    last = len(texts) - 1

    return count + last


@verification
def set_counts(something: Mutable["Something"], texts: Sequence[str]) -> bool:
    """Check assigning a length to integer properties and to an integer item."""
    something.count = len(texts)
    something.maybe_count = len(texts)
    something.numbers[0] = len(texts)
    return True


@invariant(
    lambda self: no_number_is_seven(self.numbers, len(self.numbers)),
    "No number is seven",
)
@invariant(
    lambda self: count_texts(self.texts) == len(self.texts),
    "Texts are counted",
)
@invariant(lambda self: last_position(self.texts) < 3, "At most three texts")
@invariant(
    lambda self: len(self.texts) - self.count >= 0,
    "Count is at most texts",
)
@invariant(
    lambda self: no_seven_from(self.numbers, self.count),
    "No seven from count on",
)
@invariant(
    lambda self: count_after_reassignment(self.texts) < 6,
    "Count after re-assignment is small",
)
@invariant(
    lambda self: not (len(self.texts) > 0) or self.is_valid_index(len(self.texts) - 1),
    "Last position is a valid index",
)
@invariant(
    lambda self: not (len(self.texts) > 0) or self.text_at(len(self.texts) - 1) != "",
    "Last text is not empty",
)
class Something(DBC):
    numbers: List[int]
    texts: List[str]
    count: int
    maybe_count: Optional[int]

    @non_mutating
    def is_valid_index(self, index: int) -> bool:
        """Check a method taking an integer argument, called with a length."""
        return 0 <= index and index < len(self.texts)

    @non_mutating
    def text_at(self, index: int) -> str:
        """Check reading in a method at an index which is an integer argument."""
        return self.texts[index]

    def __init__(
        self,
        numbers: List[int],
        texts: List[str],
        count: int,
        maybe_count: Optional[int] = None,
    ) -> None:
        self.numbers = numbers
        self.texts = texts
        self.count = count
        self.maybe_count = maybe_count


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
