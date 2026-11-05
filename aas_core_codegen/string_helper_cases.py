# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""
Specify the operations on strings by example.

The transpiled code follows the Python implementation of ``len``, the slicing,
``str.find``, the comparison of strings, ``str.lstrip``, ``str.rstrip``,
``str.startswith`` and ``str.endswith``, since Python is the language of
the meta-model specifications. Hence, the lengths and the positions count
the characters (code points), and not the UTF-16 code units or the UTF-8 bytes of
the target, a negative position counts from the end of the string, the positions
out of range are clamped to the string, and ``str.find`` gives -1 for a start
beyond the end of the string. The strings are ordered by their characters (code
points), and not by their UTF-16 code units. Likewise, ``str.lstrip`` and
``str.rstrip`` strip the characters, and never a half of a surrogate pair.

The targets generate unit tests from these cases so that the users can inspect
the behavior of the generated code. We compute the expected results with Python
itself, so that the Python implementation serves as the reference.
"""

from typing import Final, Optional, Sequence


class LenCase:
    """Represent a case of ``len(text)``."""

    #: Short description of what the case demonstrates
    description: Final[str]

    #: Text to be measured
    text: Final[str]

    #: Expected length, as given by Python
    expected: Final[int]

    def __init__(self, description: str, text: str) -> None:
        """Initialize with the given values, and compute the expected length."""
        self.description = description
        self.text = text
        self.expected = len(text)

    def python_expression(self) -> str:
        """Render the case in Python notation, *e.g.*, for the names of the tests."""
        return f"len({self.text!r})"


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


class CompareCase:
    """Represent a case of comparing the strings ``left`` and ``right``."""

    #: Short description of what the case demonstrates
    description: Final[str]

    #: Left operand of the comparison
    left: Final[str]

    #: Right operand of the comparison
    right: Final[str]

    #: Expected result, as given by Python: -1 if less, 0 if equal and 1 if greater
    expected: Final[int]

    def __init__(self, description: str, left: str, right: str) -> None:
        """Initialize with the given values, and compute the expected result."""
        self.description = description
        self.left = left
        self.right = right
        self.expected = (left > right) - (left < right)

    def python_expression(self) -> str:
        """Render the case in Python notation, *e.g.*, for the names of the tests."""
        return f"compare({self.left!r}, {self.right!r})"


class LStripCase:
    """Represent a case of ``text.lstrip(chars)``."""

    #: Short description of what the case demonstrates
    description: Final[str]

    #: Text to be stripped
    text: Final[str]

    #: Characters to be stripped from the start of the text
    chars: Final[str]

    #: Expected stripped text, as given by Python
    expected: Final[str]

    def __init__(self, description: str, text: str, chars: str) -> None:
        """Initialize with the given values, and compute the expected text."""
        self.description = description
        self.text = text
        self.chars = chars
        self.expected = text.lstrip(chars)

    def python_expression(self) -> str:
        """Render the case in Python notation, *e.g.*, for the names of the tests."""
        return f"{self.text!r}.lstrip({self.chars!r})"


class RStripCase:
    """Represent a case of ``text.rstrip(chars)``."""

    #: Short description of what the case demonstrates
    description: Final[str]

    #: Text to be stripped
    text: Final[str]

    #: Characters to be stripped from the end of the text
    chars: Final[str]

    #: Expected stripped text, as given by Python
    expected: Final[str]

    def __init__(self, description: str, text: str, chars: str) -> None:
        """Initialize with the given values, and compute the expected text."""
        self.description = description
        self.text = text
        self.chars = chars
        self.expected = text.rstrip(chars)

    def python_expression(self) -> str:
        """Render the case in Python notation, *e.g.*, for the names of the tests."""
        return f"{self.text!r}.rstrip({self.chars!r})"


class StartsWithCase:
    """Represent a case of ``text.startswith(prefix)``."""

    #: Short description of what the case demonstrates
    description: Final[str]

    #: Text to be checked
    text: Final[str]

    #: Prefix to be checked for
    prefix: Final[str]

    #: Expected result, as given by Python
    expected: Final[bool]

    def __init__(self, description: str, text: str, prefix: str) -> None:
        """Initialize with the given values, and compute the expected result."""
        self.description = description
        self.text = text
        self.prefix = prefix
        self.expected = text.startswith(prefix)

    def python_expression(self) -> str:
        """Render the case in Python notation, *e.g.*, for the names of the tests."""
        return f"{self.text!r}.startswith({self.prefix!r})"


class EndsWithCase:
    """Represent a case of ``text.endswith(suffix)``."""

    #: Short description of what the case demonstrates
    description: Final[str]

    #: Text to be checked
    text: Final[str]

    #: Suffix to be checked for
    suffix: Final[str]

    #: Expected result, as given by Python
    expected: Final[bool]

    def __init__(self, description: str, text: str, suffix: str) -> None:
        """Initialize with the given values, and compute the expected result."""
        self.description = description
        self.text = text
        self.suffix = suffix
        self.expected = text.endswith(suffix)

    def python_expression(self) -> str:
        """Render the case in Python notation, *e.g.*, for the names of the tests."""
        return f"{self.text!r}.endswith({self.suffix!r})"


# NOTE (mristin):
# We include the characters beyond ASCII since the targets represent the strings
# differently. The character "é" takes one UTF-16 code unit, but two UTF-8 bytes,
# while the character "😀" lies beyond the Basic Multilingual Plane, and takes two
# UTF-16 code units (a surrogate pair) and four UTF-8 bytes.

LEN_CASES: Sequence[LenCase] = (
    LenCase("empty text", ""),
    LenCase("ASCII text", "abc"),
    LenCase("character of two UTF-8 bytes", "é-"),
    LenCase("character beyond the Basic Multilingual Plane", "😀-"),
    LenCase("mixed characters", "aé😀b😀"),
)

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
    SliceCase("after a character of two UTF-8 bytes", "é-x", 1, None),
    SliceCase("character of two UTF-8 bytes", "aéb", 1, 2),
    SliceCase("character beyond the Basic Multilingual Plane", "a😀b", 1, 2),
    SliceCase("after a character beyond the Basic Multilingual Plane", "😀-x", 1, None),
    SliceCase("negative start on characters beyond ASCII", "aé😀b😀", -3, -1),
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
    FindCase("after a character of two UTF-8 bytes", "é-", "-", None),
    FindCase("after a character beyond the Basic Multilingual Plane", "😀-", "-", None),
    FindCase("character beyond the Basic Multilingual Plane", "a😀b", "😀", None),
    FindCase("start after a character beyond ASCII", "😀a😀a", "a", 2),
    FindCase("negative start on characters beyond ASCII", "😀a😀a", "😀", -2),
    FindCase("start beyond the end of characters beyond ASCII", "é😀", "", 3),
)

# NOTE (mristin):
# The UTF-16 code units of the characters beyond the Basic Multilingual Plane
# (the surrogates, from U+D800 to U+DFFF) are smaller than the characters from
# U+E000 to U+FFFF. Hence, the order by the UTF-16 code units differs from
# the order by the characters for these cases.

COMPARE_CASES: Sequence[CompareCase] = (
    CompareCase("empty texts", "", ""),
    CompareCase("equal texts", "abc", "abc"),
    CompareCase("empty text before non-empty", "", "a"),
    CompareCase("prefix before the longer text", "ab", "abc"),
    CompareCase("first difference decides", "abd", "abc"),
    CompareCase("upper case before lower case", "B", "a"),
    CompareCase("character of two UTF-8 bytes after ASCII", "é", "z"),
    CompareCase("equal characters beyond ASCII", "aé😀", "aé😀"),
    CompareCase(
        "character beyond the Basic Multilingual Plane after U+FFFD", "😀", "\ufffd"
    ),
    CompareCase(
        "U+E000 before a character beyond the Basic Multilingual Plane",
        "a\ue000",
        "a😀",
    ),
    CompareCase(
        "characters beyond the Basic Multilingual Plane differing in low surrogates",
        "😀",
        "😁",
    ),
    CompareCase(
        "characters beyond the Basic Multilingual Plane differing in high surrogates",
        "😀",
        "\U0001d11e",
    ),
)

# NOTE (mristin):
# The emojis lie beyond the Basic Multilingual Plane, so they are encoded as two
# UTF-16 code units. The emojis "😀" (U+1F600) and "😁" (U+1F601) share the high
# surrogate (U+D83D), while "😀" and "𐈀" (U+10200) share the low surrogate
# (U+DE00). An implementation which strips the UTF-16 code units instead of
# the characters would strip a half of "😁" when told to strip "😀", or strip "😀"
# when told to strip "𐈀" and "😁".

LSTRIP_CASES: Final[Sequence[LStripCase]] = (
    LStripCase("leading zeros", "000123", "0"),
    LStripCase("any of the characters", "+-+12", "+-"),
    LStripCase("only the leading characters", "0102", "0"),
    LStripCase("empty text", "", "0"),
    LStripCase("all the characters", "000", "0"),
    LStripCase("empty characters", "abc", ""),
    LStripCase("characters not in the text", "abc", "xyz"),
    LStripCase("characters in any order", "abc", "cba"),
    LStripCase("character of two UTF-8 bytes", "éé-x", "-é"),
    LStripCase("character beyond the Basic Multilingual Plane", "😀😀a😀", "😀"),
    LStripCase("character sharing the high surrogate", "😁x", "😀"),
    LStripCase("characters sharing the surrogates", "😀x", "𐈀😁"),
    LStripCase("ASCII before a character beyond ASCII", "a😀", "a"),
)

RSTRIP_CASES: Final[Sequence[RStripCase]] = (
    RStripCase("trailing zeros", "123000", "0"),
    RStripCase("any of the characters", "12+-+", "+-"),
    RStripCase("only the trailing characters", "2010", "0"),
    RStripCase("empty text", "", "0"),
    RStripCase("all the characters", "000", "0"),
    RStripCase("empty characters", "abc", ""),
    RStripCase("characters not in the text", "abc", "xyz"),
    RStripCase("characters in any order", "abc", "cba"),
    RStripCase("character of two UTF-8 bytes", "x-éé", "-é"),
    RStripCase("character beyond the Basic Multilingual Plane", "😀a😀😀", "😀"),
    RStripCase("character sharing the high surrogate", "x😁", "😀"),
    RStripCase("characters sharing the surrogates", "x😀", "𐈀😁"),
    RStripCase("ASCII after a character beyond ASCII", "😀a", "a"),
)

# NOTE (mristin):
# The targets compare the prefixes and the suffixes ordinally, *i.e.*, by their
# UTF-16 code units or UTF-8 bytes, which gives the same result as comparing
# the characters for the strings without lone surrogates. We include
# the characters sharing a surrogate so that the users can see that a half of
# a character never matches.

STARTSWITH_CASES: Final[Sequence[StartsWithCase]] = (
    StartsWithCase("prefix", "abc", "ab"),
    StartsWithCase("not a prefix", "abc", "bc"),
    StartsWithCase("empty prefix", "abc", ""),
    StartsWithCase("whole text", "abc", "abc"),
    StartsWithCase("prefix longer than text", "ab", "abc"),
    StartsWithCase("empty prefix of empty text", "", ""),
    StartsWithCase("non-empty prefix of empty text", "", "a"),
    StartsWithCase("character of two UTF-8 bytes", "éa", "é"),
    StartsWithCase("character beyond the Basic Multilingual Plane", "😀a", "😀"),
    StartsWithCase("character sharing the high surrogate", "😁x", "😀"),
)

ENDSWITH_CASES: Final[Sequence[EndsWithCase]] = (
    EndsWithCase("suffix", "abc", "bc"),
    EndsWithCase("not a suffix", "abc", "ab"),
    EndsWithCase("empty suffix", "abc", ""),
    EndsWithCase("whole text", "abc", "abc"),
    EndsWithCase("suffix longer than text", "bc", "abc"),
    EndsWithCase("empty suffix of empty text", "", ""),
    EndsWithCase("non-empty suffix of empty text", "", "a"),
    EndsWithCase("character of two UTF-8 bytes", "aé", "é"),
    EndsWithCase("character beyond the Basic Multilingual Plane", "a😀", "😀"),
    EndsWithCase("character sharing the high surrogate", "x😁", "😀"),
)
