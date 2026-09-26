"""
Specify the slicing and ``str.find`` of the transpiled code by example.

The transpiled code follows the Python implementation of the slicing and of
``str.find``, since Python is the language of the meta-model specifications.
Hence, a negative position counts from the end of the string, the positions out
of range are clamped to the string, and ``str.find`` gives -1 for a start
beyond the end of the string.

The targets generate unit tests from these cases so that the users can inspect
the behavior of the generated code. We compute the expected results with Python
itself, so that the Python implementation serves as the reference.
"""

from typing import Final, Optional, Sequence


class SliceCase:
    """Represent a case of slicing ``text[start:end]``."""

    #: Short description of what the case demonstrates
    description: Final[str]

    #: Text to be sliced
    text: Final[str]

    #: Start of the slice, or ``None`` if omitted
    start: Final[Optional[int]]

    #: End of the slice, or ``None`` if omitted
    end: Final[Optional[int]]

    #: Expected slice, as given by Python
    expected: Final[str]

    def __init__(
        self,
        description: str,
        text: str,
        start: Optional[int],
        end: Optional[int],
    ) -> None:
        """Initialize with the given values, and compute the expected slice."""
        self.description = description
        self.text = text
        self.start = start
        self.end = end
        self.expected = text[start:end]

    def python_expression(self) -> str:
        """Render the case in Python notation, *e.g.*, for the names of the tests."""
        start = "" if self.start is None else str(self.start)
        end = "" if self.end is None else str(self.end)
        return f"{self.text!r}[{start}:{end}]"


class FindCase:
    """Represent a case of ``text.find(sub)`` or ``text.find(sub, start)``."""

    #: Short description of what the case demonstrates
    description: Final[str]

    #: Text to be searched in
    text: Final[str]

    #: Text to be searched for
    sub: Final[str]

    #: Start of the search, or ``None`` if omitted
    start: Final[Optional[int]]

    #: Expected position, as given by Python
    expected: Final[int]

    def __init__(
        self, description: str, text: str, sub: str, start: Optional[int]
    ) -> None:
        """Initialize with the given values, and compute the expected position."""
        self.description = description
        self.text = text
        self.sub = sub
        self.start = start
        self.expected = text.find(sub) if start is None else text.find(sub, start)

    def python_expression(self) -> str:
        """Render the case in Python notation, *e.g.*, for the names of the tests."""
        if self.start is None:
            return f"{self.text!r}.find({self.sub!r})"

        return f"{self.text!r}.find({self.sub!r}, {self.start})"


SLICE_CASES: Sequence[SliceCase] = (
    SliceCase("start and end", "abcde", 1, 3),
    SliceCase("no start", "abcde", None, 2),
    SliceCase("no end", "abcde", 3, None),
    SliceCase("neither start nor end", "abcde", None, None),
    SliceCase("negative start counts from the end", "abcde", -2, None),
    SliceCase("negative end counts from the end", "abcde", None, -2),
    SliceCase("negative start and end", "abcde", -4, -1),
    SliceCase("negative start before the beginning is clamped", "abcde", -10, 2),
    SliceCase("end beyond the end is clamped", "abcde", 2, 10),
    SliceCase("start beyond the end gives empty", "abcde", 10, None),
    SliceCase("start after end gives empty", "abcde", 3, 1),
    SliceCase("negative start after negative end gives empty", "abcde", -1, -3),
    SliceCase("start equal to end gives empty", "abcde", 5, 5),
    SliceCase("empty text", "", 0, 0),
    SliceCase("negative start on empty text", "", -1, None),
    SliceCase("end beyond the end of empty text", "", None, 5),
)

FIND_CASES: Sequence[FindCase] = (
    FindCase("found", "abcabc", "b", None),
    FindCase("not found", "abcabc", "x", None),
    FindCase("empty sub", "abcabc", "", None),
    FindCase("sub longer than text", "ab", "abc", None),
    FindCase("found after start", "abcabc", "b", 2),
    FindCase("found only before start", "abcabc", "b", 5),
    FindCase("negative start counts from the end", "abcabc", "c", -1),
    FindCase("negative start finds the later occurrence", "abcabc", "a", -3),
    FindCase("negative start before the beginning is clamped", "abcabc", "a", -10),
    FindCase("empty sub at the end", "abcabc", "", 6),
    FindCase("empty sub beyond the end gives -1", "abcabc", "", 7),
    FindCase("start beyond the end gives -1", "abcabc", "c", 10),
    FindCase("empty sub in empty text", "", "", None),
    FindCase("empty sub beyond the end of empty text gives -1", "", "", 1),
    FindCase("not found in empty text", "", "x", None),
)
