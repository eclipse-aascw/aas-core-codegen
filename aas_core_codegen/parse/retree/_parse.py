"""Parse a regular expression defined over a possibly-formatted string."""
import collections.abc
import io
import math
import re
from typing import Tuple, Optional, List, Sequence, Union, MutableMapping

from icontract import invariant, require, ensure, snapshot

from aas_core_codegen.common import pairwise
from aas_core_codegen.parse.retree._types import (
    Char,
    Range,
    Concatenation,
    Symbol,
    Group,
    CharSet,
    Quantifier,
    Term,
    UnionExpr,
    Regex,
    TermValueUnion,
    SymbolKind,
)
from aas_core_codegen.parse.tree import FormattedValue


# fmt: off
@invariant(
    lambda self:
    (
        not self.done()
        ^ (
            self.major_cursor == len(self.values)
            or (
                self.major_cursor == len(self.values) - 1
                and isinstance(self.pointed_value(), str)
                and self.minor_cursor == len(self.pointed_value())
            )
        )
    ),
    "We are done iff we reached the end of values with the major cursor or "
    "the end of the last pointed value as string"
)
@invariant(
    lambda self:
    not isinstance(self.pointed_value(), str)
    or (0 <= self.minor_cursor <= len(self.pointed_value())),
    "Minor cursor is within the expected range if the pointed value is a string"
)
@invariant(
    lambda self:
    not (not isinstance(self.pointed_value(), str))
    or (self.minor_cursor is None),
    "Minor cursor is invalidated if the pointed value is not a string"
)
@invariant(
    lambda self:
    (
            not (self.major_cursor == len(self.values))
            or self.pointed_value() is None
    ),
    "No pointed value if we reached the end of the values"
)
@invariant(
    lambda self:
    (
            not (0 <= self.major_cursor < len(self.values))
            or self.pointed_value() is not None
    ),
    "A value must be pointed at if we did not reach the end of the values"
)
@invariant(
    lambda self:
    0 <= self.major_cursor <= len(self.values),
    "Major cursor is within the expected range"
)
# fmt: on
class Cursor:
    """Manage the iteration over the input stream."""

    # fmt: off
    @require(
        lambda values:
        not (len(values) > 1)
        or not any(
            (
                    isinstance(first, str)
                    and isinstance(second, str)
            )
            for first, second in zip(values, values[1:])
        ),
        "No consecutive strings expected in the parsed sequence of an AST expression "
        "representing a string interpolation"
    )
    # NOTE (mristin):
    # We add a runtime test here since it already happened that we supplied ``values``
    # as a string during development, causing an unnecessary long debugging session.
    @require(
        lambda values:
        isinstance(values, collections.abc.Sequence),
        "values must be a sequence"
    )
    # fmt: on
    def __init__(self, values: Sequence[Union[str, FormattedValue]]) -> None:
        """Initialize with the given values."""
        self.values = values

        # Major cursor points within the values
        self._major_cursor = 0

        # Minor cursor points within a value
        self._minor_cursor: Optional[int] = None
        if isinstance(self.pointed_value(), str):
            self._minor_cursor = 0

    def copy(self) -> "Cursor":
        """Make a deep copy of the cursor."""
        return Cursor(values=self.values)

    @property
    def major_cursor(self) -> int:
        """Return the current cursor in the :attr:`~values`."""
        return self._major_cursor

    @property
    def minor_cursor(self) -> Optional[int]:
        """
        Return the current cursor in the :attr:`~pointed_value`.

        If the :attr:`~pointed_value` is not a string, return ``None``.
        """
        if not isinstance(self.pointed_value(), str):
            return None

        return self._minor_cursor

    def pointed_value(self) -> Optional[Union[str, FormattedValue]]:
        """Return the value pointed by the :attr:`~major_cursor`."""
        if self._major_cursor >= len(self.values):
            return None

        return self.values[self._major_cursor]

    def _move_major_cursor(self) -> None:
        """
        Move the major cursor to the next value.

        The minor cursor is also updated accordingly, depending on the pointed value.
        """
        if not self.done():
            self._major_cursor += 1

            self._minor_cursor = 0 if isinstance(self.pointed_value(), str) else None

    @require(lambda jump_length: jump_length >= 0)
    @require(
        lambda self: not (not self.done())
        or (self._minor_cursor is not None and isinstance(self.pointed_value(), str)),
        "If we are not done, we should only move within a string value",
    )
    def _move_minor_cursor(self, jump_length: int) -> None:
        """
        Move the minor cursor within a string value for ``jump_length`` positions.

        If we reached the end of value, move to the next value.
        """
        if self.done():
            return

        assert self._minor_cursor is not None

        pointed_value = self.pointed_value()
        assert pointed_value is not None
        assert isinstance(pointed_value, str)

        if self._minor_cursor + jump_length >= len(pointed_value):
            self._move_major_cursor()
        else:
            self._minor_cursor += jump_length

    def done(self) -> bool:
        """Signal that we reached the end of the :attr:`~values`."""
        if self._major_cursor >= len(self.values):
            return True

        pointed_value = self.pointed_value()
        if isinstance(pointed_value, str):
            assert self._minor_cursor is not None
            return self._minor_cursor >= len(pointed_value)
        else:
            assert self._minor_cursor is None
            return False

    def try_formatted_value(self) -> Optional[FormattedValue]:
        """
        Try to read the formatted value at the current cursor and return it.

        Otherwise, if no formatted value is present, return ``None``.
        """
        value = self.pointed_value()
        if isinstance(value, FormattedValue):
            self._move_major_cursor()
            return value

        return None

    def try_positive_integer_without_sign(self) -> Optional[int]:
        """
        Try to read an integer and move the cursor accordingly.

        An integer can be prefixed by a zero (*e.g.*, ``000123``). No sign is expected
        as a prefix.

        Otherwise, if there is no integer at the cursor, return ``None`` and do not
        move the cursor.
        """
        pointed_value = self.pointed_value()
        if isinstance(pointed_value, FormattedValue):
            return None

        if self.minor_cursor is None:
            return None

        assert isinstance(pointed_value, str)
        accumulator = []  # type: List[str]
        for i in range(self.minor_cursor, len(pointed_value)):
            if pointed_value[i].isdigit():
                accumulator.append(pointed_value[i])
            else:
                break

        if len(accumulator) > 0:
            self._move_minor_cursor(jump_length=len(accumulator))
            return int("".join(accumulator))

        return None

    @snapshot(lambda self, literal: self.peek_literal(literal), "peeked")
    @ensure(
        lambda result, OLD: (result and OLD.peeked) or (not result and not OLD.peeked),
        "If we matched the literal, we should have been able to successfully peek it "
        "before moving the cursor, and vice-versa.",
    )
    def try_literal(self, literal: str) -> bool:
        """
        Try to match the ``literal``, return ``True`` and move the cursor accordingly.

        If the ``literal`` could not be matched, return ``False`` and do not move the
        cursor.
        """
        result = self.peek_literal(literal=literal)

        if result:
            self._move_minor_cursor(jump_length=len(literal))

        return result

    def peek_literal(self, literal: str) -> bool:
        """
        Try to match the ``literal``.

        Do not move the cursor.
        """
        pointed_value = self.pointed_value()
        if not isinstance(pointed_value, str):
            return False

        assert self.minor_cursor is not None
        if len(pointed_value) < self.minor_cursor + len(literal):
            return False

        result = (
            pointed_value[self.minor_cursor : (self.minor_cursor + len(literal))]
            == literal
        )

        return result

    def peek_substring(self, length: int) -> Optional[str]:
        """
        Try to read a substring of ``length`` characters.

        If the remainder of the stream contains less than ``length`` characters,
        return ``None``, or the pointed value is not a string, return ``None``.

        Do not move the cursor.
        """
        pointed_value = self.pointed_value()
        if not isinstance(pointed_value, str):
            return None

        assert self.minor_cursor is not None
        if len(pointed_value) < self.minor_cursor + length:
            return None

        return pointed_value[self.minor_cursor : (self.minor_cursor + length)]

    def try_substring(self, length: int) -> Optional[str]:
        """
        Try to read a substring of ``length`` characters and move the cursor.

        If the remainder of the stream contains less than ``length`` characters,
        or the pointed value is not a string, return ``None`` and
        do not move the cursor.
        """
        result = self.peek_substring(length=length)
        if result is None:
            return None

        self._move_minor_cursor(jump_length=length)

        return result

    def try_spaces_or_tabs(self) -> bool:
        """
        Try to read spaces (``" "``) and tabs (``"\t"``) from the stream.

        If the spaces are found, move the cursor and return ``True``.

        If no spaces are found at the cursor, return ``False`` and do not move
        the cursor.
        """
        found_tab_or_space = False
        while True:
            if self.try_literal(" "):
                found_tab_or_space = True
            elif self.try_literal("\t"):
                found_tab_or_space = True
            else:
                break

        return found_tab_or_space

    # fmt: off
    @require(
        lambda other, self:
        id(other.values) == id(self.values),
        "This and the other cursor must point to the same values"
    )
    # fmt: on
    def has_same_position(self, other: "Cursor") -> bool:
        """Check whether the ``other`` cursor points to the same position."""
        return (self.done() and other.done()) or (
            self.major_cursor == other.major_cursor
            and self.minor_cursor == other.minor_cursor
        )

    # fmt: off
    @require(
        lambda other, self:
        id(other.values) == id(self.values),
        "This and the other cursor must point to the same values"
    )
    @ensure(
        lambda other, self, result:
        not (self.has_same_position(other))
        or (not result)
    )
    # fmt: on
    def is_before(self, other: "Cursor") -> bool:
        """Check whether this cursor is pointing before the ``other`` cursor."""
        if self.done() and other.done():
            return False
        elif self.done() and not other.done():
            return False
        elif not self.done() and other.done():
            return True
        else:
            assert self.major_cursor is not None
            assert other.major_cursor is not None

            if self.major_cursor < other.major_cursor:
                return True
            elif self.major_cursor > other.major_cursor:
                return False
            else:
                if self.minor_cursor is None and other.minor_cursor is None:
                    # NOTE (mristin):
                    # Both major cursors point to the formatted value, so they
                    # point to the same position.
                    assert isinstance(self.pointed_value(), FormattedValue)
                    assert isinstance(other.pointed_value(), FormattedValue)
                    return False
                else:
                    # NOTE (mristin):
                    # If one minor cursor is not None, it means the major cursors
                    # point to a string.
                    assert isinstance(self.pointed_value(), str)
                    assert isinstance(other.pointed_value(), str)

                    assert self.minor_cursor is not None
                    assert other.minor_cursor is not None
                    return self.minor_cursor < other.minor_cursor


class Error:
    """Represent an error occurring during the parsing of a regular expression."""

    def __init__(self, message: str, cursor: Cursor) -> None:
        """Initialize with the given values."""
        self.message = message
        self.cursor = cursor


_UNEXPECTED_CHARACTERS_IN_REGEX_RE = re.compile("[\\n\\f\\v\\r]")
_WHITESPACE_RE = re.compile("\\s")


@require(lambda cursor: len(cursor.values) > 0)
@ensure(lambda result: len(result[0]) > 0 and len(result[1]) > 0)
@ensure(lambda result: result[1].endswith("^"))
def render_pointer(cursor: Cursor) -> Tuple[str, str]:
    """Render the regular expression and the pointer corresponding to the cursor."""
    regex_writer = io.StringIO()
    pointer_writer = io.StringIO()

    @require(lambda text: not _UNEXPECTED_CHARACTERS_IN_REGEX_RE.search(text))
    def write_text(text: str, draw_pointer: bool) -> None:
        """
        Output the ``text``.

        We write the ``text`` to the ``regex_writer``. Depending on ``draw_pointer``,
        we either write the corresponding whitespace to ``pointer_writer``
        (if ``False``) or draw a pointer (``^``).
        """
        if not draw_pointer:
            for character in text:
                regex_writer.write(character)

                if _WHITESPACE_RE.fullmatch(character):
                    pointer_writer.write(character)
                else:
                    pointer_writer.write(" ")
        else:
            regex_writer.write(text)
            pointer_writer.write("^")

    a_cursor = Cursor(values=cursor.values)
    while True:
        if a_cursor.done():
            assert a_cursor.has_same_position(cursor)
            pointer_writer.write("^")
            break

        has_same_position = a_cursor.has_same_position(cursor)

        formatted_value = a_cursor.try_formatted_value()
        if formatted_value:
            # NOTE (mristin):
            # The asttokens can not get the text of the formatted values,
            # see: https://github.com/gristlabs/asttokens/issues/6.
            write_text(text="<formatted value>", draw_pointer=has_same_position)
        else:
            substring = a_cursor.try_substring(length=1)
            assert substring is not None, (
                f"We explicitly checked for a_cursor "
                f"not done and not a formatted value, but got no substring: "
                f"{a_cursor.pointed_value()=}, {a_cursor.major_cursor=}, "
                f"{a_cursor.minor_cursor=}"
            )
            write_text(text=substring, draw_pointer=has_same_position)

        if has_same_position:
            break

    # NOTE (mristin):
    # Write the remainder of the regular expression
    while not a_cursor.done():
        formatted_value = a_cursor.try_formatted_value()
        if formatted_value:
            # NOTE (mristin):
            # The asttokens can not get the text of the formatted values,
            # see: https://github.com/gristlabs/asttokens/issues/6.
            regex_writer.write("<formatted value>")
        else:
            substring = a_cursor.try_substring(length=1)
            assert substring is not None, (
                f"We explicitly checked for a_cursor "
                f"not done and not a formatted value, but got no substring: "
                f"{a_cursor.pointed_value()=}, {a_cursor.major_cursor=}, "
                f"{a_cursor.minor_cursor=}"
            )
            regex_writer.write(substring)

    return regex_writer.getvalue(), pointer_writer.getvalue()


# fmt: off
# noinspection RegExpSimplifiable
@require(
    lambda cursor: not cursor.peek_literal("-"),
    "The dash (``-``) handled before, outside of this function"
)
@require(
    lambda cursor: not cursor.done(),
    "End of input handled before, outside of this function"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _parse_range_char(cursor: Cursor) -> Tuple[Optional[Char], Optional[Error]]:
    """Try to parse a character in the range of a character set."""
    if cursor.try_literal("\\x"):
        substring = cursor.try_substring(length=2)
        if substring is None:
            return None, Error("Expected two hexadecimal digits after \\x", cursor)

        # noinspection RegExpSimplifiable
        if not re.fullmatch(r"[a-fA-F0-9]{2}", substring):
            return None, Error(
                f"Expected two hexadecimal digits after \\x, but got {substring!r}",
                cursor,
            )

        result = Char(character=chr(int(substring, 16)), explicitly_encoded=True)

    elif cursor.try_literal("\\u"):
        substring = cursor.try_substring(length=4)
        if substring is None:
            return None, Error("Expected four hexadecimal digits after \\u", cursor)

        if not re.fullmatch(r"[a-fA-F0-9]{4}", substring):
            return None, Error(
                f"Expected four hexadecimal digits after \\u, "
                f"but got {substring!r}",
                cursor,
            )

        result = Char(character=chr(int(substring, 16)), explicitly_encoded=True)

    elif cursor.try_literal("\\U"):
        substring = cursor.try_substring(length=8)
        if substring is None:
            return None, Error("Expected eight hexadecimal digits after \\U", cursor)

        if not re.fullmatch(r"[a-fA-F0-9]{8}", substring):
            return None, Error(
                f"Expected eight hexadecimal digits after \\U, "
                f"but got {substring!r}",
                cursor,
            )

        code = int(substring, 16)
        if code < 0x00010000 or code > 0x0010FFFF:
            # noinspection SpellCheckingInspection
            return None, Error(
                f"Expected the character code in the range \\U00010000-\\U0010FFFF, "
                f"but got \\U{code:08x}; "
                f"the code can not be represented with high/low surrogates in UTF-16",
                cursor,
            )

        result = Char(character=chr(code), explicitly_encoded=True)
    elif cursor.try_literal("\\t"):
        result = Char(character="\t")

    elif cursor.try_literal("\\n"):
        result = Char(character="\n")

    elif cursor.try_literal("\\r"):
        result = Char(character="\r")

    elif cursor.try_literal("\\f"):
        result = Char(character="\f")

    elif cursor.try_literal("\\v"):
        result = Char(character="\v")

    elif cursor.try_literal("\\\\"):
        result = Char(character="\\")

    elif cursor.try_literal("\\["):
        result = Char(character="[")

    elif cursor.try_literal("\\]"):
        result = Char(character="]")

    elif cursor.try_literal("\\^"):
        result = Char(character="^")

    elif cursor.try_literal("\\-"):
        result = Char(character="-")

    elif cursor.try_literal("\\s") or cursor.try_literal("\\S"):
        return None, Error(
            "We do not handle whitespace escaping at the moment (2022-06-09), "
            "as the notion of a whitespace depends on the regex engine",
            cursor,
        )

    elif cursor.try_literal("\\d") or cursor.try_literal("\\D"):
        return None, Error(
            "We do not handle digit escaping at the moment (2022-06-09), "
            "as the notion of a digit depends on the regex engine",
            cursor,
        )

    elif cursor.try_literal("\\"):
        return None, Error("Unexpected escaping", cursor)

    else:
        character = cursor.try_substring(length=1)
        assert character is not None, (
            "Expected to read at least one character since we explicitly checked "
            "that the cursor is not done before"
        )
        result = Char(character=character)

    assert result is not None
    return result, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _parse_ranges_and_closing(
    cursor: Cursor,
) -> Tuple[Optional[List[Range]], Optional[Error]]:
    # noinspection GrazieInspection
    """Parse one or more ranges in a character set and the closing ``]``."""
    ranges = []  # type: List[Range]

    # Prefix dash is allowed and should be considered as a character.
    if cursor.try_literal("-"):
        ranges.append(Range(start=Char("-"), end=None))

    cursor_by_range = dict()  # type: MutableMapping[Range, Cursor]

    while True:
        if cursor.done():
            return None, Error(
                "Expected a closing bracket for the character set (``]``), "
                "but reached the end of input.",
                cursor,
            )

        cursor_at_start = cursor.copy()

        # NOTE (mristin):
        # A suffix dash is also allowed and should be considered a single character.
        if cursor.try_literal("-]"):
            the_range = Range(start=Char("-"), end=None)
            cursor_by_range[the_range] = cursor_at_start
            ranges.append(the_range)
            break
        elif cursor.try_literal("]"):
            break
        else:
            start, error = _parse_range_char(cursor)
            if error is not None:
                return None, error
            assert start is not None

            end = None  # type: Optional[Char]
            if not cursor.peek_literal("-]"):
                if cursor.try_literal("-"):
                    if cursor.try_literal("-"):
                        return None, Error(
                            "Unexpected double ``-`` in the character set", cursor
                        )

                    end, error = _parse_range_char(cursor)
                    if error is not None:
                        return None, error
                    assert end is not None

            if end is not None and ord(start.character) > ord(end.character):
                return None, Error(
                    "Invalid character range, start is smaller than end", cursor
                )

            the_range = Range(start=start, end=end)
            cursor_by_range[the_range] = cursor_at_start
            ranges.append(the_range)

    for this_range, next_range in pairwise(
        sorted(ranges, key=lambda rng: ord(rng.start.character))
    ):
        this_end = this_range.end if this_range.end is not None else this_range.start

        next_start = next_range.start

        if ord(this_end.character) >= ord(next_start.character):
            this_range_str = (
                f"{this_range.start.character!r}"
                if this_range.end is None
                else f"{this_range.start.character!r}-{this_range.end.character!r}"
            )

            next_range_str = (
                f"{next_range.start.character!r}"
                if next_range.end is None
                else f"{next_range.start.character!r}-{next_range.end.character!r}"
            )

            return None, Error(
                f"The range {this_range_str} and the range {next_range_str} overlap",
                cursor_by_range[this_range],
            )

    return ranges, None


# noinspection RegExpSimplifiable
def _parse_char_literal(cursor: Cursor) -> Tuple[Optional[Char], Optional[Error]]:
    """
    Parse a character literal in a concatenation.

    It might be that no character could be parsed, but that the stream is still valid.
    For example, if there is a quantifier (such as ``*``, ``+`` or ``?``) following
    a literal. In those cases, return ``None`` and no error.
    """
    if cursor.done():
        return None, None

    result: Char

    if cursor.try_literal("\\x"):
        substring = cursor.try_substring(length=2)
        if substring is None:
            return None, Error("Expected two hexadecimal digits after \\x", cursor)

        if not re.fullmatch(r"[a-fA-F0-9]{2}", substring):
            return None, Error(
                f"Expected two hexadecimal digits after \\x, but got {substring!r}",
                cursor,
            )

        result = Char(character=chr(int(substring, 16)), explicitly_encoded=True)

    elif cursor.try_literal("\\u"):
        substring = cursor.try_substring(length=4)
        if substring is None:
            return None, Error("Expected four hexadecimal digits after \\u", cursor)

        if not re.fullmatch(r"[a-fA-F0-9]{4}", substring):
            return None, Error(
                f"Expected four hexadecimal digits after \\u, "
                f"but got {substring!r}",
                cursor,
            )

        result = Char(character=chr(int(substring, 16)), explicitly_encoded=True)

    elif cursor.try_literal("\\U"):
        substring = cursor.try_substring(length=8)
        if substring is None:
            return None, Error("Expected eight hexadecimal digits after \\U", cursor)

        if not re.fullmatch(r"[a-fA-F0-9]{8}", substring):
            return None, Error(
                f"Expected eight hexadecimal digits after \\U, "
                f"but got {substring!r}",
                cursor,
            )

        code = int(substring, 16)
        if code < 0x00010000 or code > 0x0010FFFF:
            # noinspection SpellCheckingInspection
            return None, Error(
                f"Expected the character code in the range \\U00010000-\\U0010FFFF, "
                f"but got \\U{code:08x}; "
                f"the code can not be represented with high/low surrogates in UTF-16",
                cursor,
            )

        result = Char(character=chr(code), explicitly_encoded=True)
    elif cursor.try_literal("\\t"):
        result = Char(character="\t")

    elif cursor.try_literal("\\n"):
        result = Char(character="\n")

    elif cursor.try_literal("\\r"):
        result = Char(character="\r")

    elif cursor.try_literal("\\f"):
        result = Char(character="\f")

    elif cursor.try_literal("\\v"):
        result = Char(character="\v")

    elif cursor.try_literal("\\."):
        result = Char(character=".")

    elif cursor.try_literal("\\#"):
        result = Char(character="#")

    elif cursor.try_literal("\\^"):
        result = Char(character="^")

    elif cursor.try_literal("\\$"):
        result = Char(character="$")

    elif cursor.try_literal("\\("):
        result = Char(character="(")

    elif cursor.try_literal("\\)"):
        result = Char(character=")")

    elif cursor.try_literal("\\["):
        result = Char(character="[")

    elif cursor.try_literal("\\]"):
        result = Char(character="]")

    elif cursor.try_literal("\\\\"):
        result = Char(character="\\")

    elif cursor.try_literal("\\*"):
        result = Char(character="*")

    elif cursor.try_literal("\\+"):
        result = Char(character="+")

    elif cursor.try_literal("\\?"):
        result = Char(character="?")

    elif cursor.try_literal("\\s") or cursor.try_literal("\\S"):
        return None, Error(
            "We do not handle whitespace escaping at the moment (2022-06-09), "
            "as the notion of a whitespace depends on the regex engine",
            cursor,
        )

    elif cursor.try_literal("\\w") or cursor.try_literal("\\W"):
        return None, Error(
            "We do not handle word escaping at the moment (2022-06-09), "
            "as the notion of a word depends on the regex engine",
            cursor,
        )

    elif cursor.try_literal("\\d") or cursor.try_literal("\\D"):
        return None, Error(
            "We do not handle digit escaping at the moment (2022-06-09), "
            "as the notion of a digit depends on the regex engine",
            cursor,
        )

    elif cursor.try_literal("\\"):
        return None, Error("Unexpected escaping", cursor)

    elif cursor.try_literal("^"):
        raise AssertionError(
            "Expected to handle the start symbol before, outside of this function"
        )

    elif cursor.try_literal("$"):
        raise AssertionError(
            "Expected to handle the end symbol before, outside of this function"
        )

    elif cursor.try_literal("*"):
        raise AssertionError(
            "Expected to handle the ``*`` quantifier before, outside of this function"
        )

    elif cursor.try_literal("+"):
        raise AssertionError(
            "Expected to handle the ``+`` quantifier before, outside of this function"
        )

    elif cursor.try_literal("?"):
        raise AssertionError(
            "Expected to handle the ``?`` quantifier before, outside of this function"
        )

    elif cursor.try_literal("{"):
        raise AssertionError(
            "Expected to handle the opening ``{`` of a quantifier before, "
            "outside of this function"
        )

    elif cursor.peek_literal(")") or cursor.peek_literal("|"):
        # NOTE (mristin):
        # We encountered a closing bracket or a delimiter in a union,
        # so no concatenation is possible anymore, and we need to match an "empty"
        # character literal.
        return None, None

    else:
        character = cursor.try_substring(length=1)
        assert character is not None, (
            "Expected to read at least one character since we explicitly checked "
            "that the cursor is not done before"
        )
        result = Char(character=character)

    return result, None


_SUPPLEMENTARY_PLANE_START = 0x00010000


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _parse_concatenation(
    cursor: Cursor,
) -> Tuple[Optional[Concatenation], Optional[Error]]:
    """Try to parse a concatenation of regex terms."""
    if cursor.done():
        return None, Error(
            "Expected at least one term, but reached the end of input.", cursor
        )

    concatenants = []  # type: List[Term]

    while True:
        old_cursor_position = (
            cursor.major_cursor,
            cursor.minor_cursor if cursor.minor_cursor is not None else math.inf,
        )

        if cursor.done():
            break

        if cursor.peek_literal("|"):
            break

        value: Optional[TermValueUnion]

        # noinspection GrazieInspection
        if cursor.try_literal("^"):
            value = Symbol(kind=SymbolKind.START)

        elif cursor.try_literal("$"):
            value = Symbol(kind=SymbolKind.END)

        elif cursor.try_literal("."):
            value = Symbol(kind=SymbolKind.DOT)

        elif cursor.try_literal("("):
            if cursor.try_literal("?"):
                return None, Error(
                    "At this moment (2022-06-09), we did not have time to implement "
                    "the support for the directives in the groups (``?``). "
                    "Please inform the developers if you need this feature.",
                    cursor,
                )

            union, error = _parse_union(cursor)
            if error is not None:
                return None, error
            assert union is not None

            found_closing_bracket = cursor.try_literal(")")
            if not found_closing_bracket:
                return None, Error(
                    "Expected a closing bracket for the group, but found none.", cursor
                )

            value = Group(union=union)
        elif cursor.try_literal("[^"):
            ranges, error = _parse_ranges_and_closing(cursor)
            if error is not None:
                return None, error
            assert ranges is not None

            for a_range in ranges:
                if ord(a_range.start.character) > _SUPPLEMENTARY_PLANE_START or (
                    a_range.end is not None
                    and ord(a_range.end.character) > _SUPPLEMENTARY_PLANE_START
                ):
                    range_str = (
                        f"\\U{a_range.start:08x}"
                        if a_range.end is None
                        else f"\\U{a_range.start:08x}-\\U{a_range.end:08x}"
                    )
                    return None, Error(
                        f"Complementing character sets with a range {range_str} "
                        f"involving UTF-32 characters can not be supported, "
                        f"since we can not represent them in implementations relying "
                        f"on UTF-16-only regex engines (such as C# as of 2022-06-11)",
                        cursor,
                    )

            value = CharSet(complementing=True, ranges=ranges)

        elif cursor.try_literal("["):
            ranges, error = _parse_ranges_and_closing(cursor)
            if error is not None:
                return None, error
            assert ranges is not None

            value = CharSet(complementing=False, ranges=ranges)

        elif isinstance(cursor.pointed_value(), FormattedValue):
            formatted_value = cursor.try_formatted_value()
            assert formatted_value is not None

            value = formatted_value

        elif cursor.try_literal("*"):
            return None, Error("Unexpected ``*`` quantifier without a term", cursor)

        elif cursor.try_literal("+"):
            return None, Error("Unexpected ``+`` quantifier without a term", cursor)

        elif cursor.try_literal("?"):
            return None, Error("Unexpected ``?`` quantifier without a term", cursor)

        else:
            value, error = _parse_char_literal(cursor)
            if error is not None:
                return None, error

            # NOTE (mristin):
            # The ``value`` can be None here. For example, if we peeked a closing
            # ``)`` or a delimiting ``|``.

        if value is not None:
            quantifier = None  # type: Optional[Quantifier]
            if cursor.try_literal("*?"):
                quantifier = Quantifier(non_greedy=True, minimum=0, maximum=None)
            elif cursor.try_literal("+?"):
                quantifier = Quantifier(non_greedy=True, minimum=1, maximum=None)
            elif cursor.try_literal("??"):
                quantifier = Quantifier(non_greedy=True, minimum=0, maximum=1)
            elif cursor.try_literal("*"):
                quantifier = Quantifier(non_greedy=False, minimum=0, maximum=None)
            elif cursor.try_literal("+"):
                quantifier = Quantifier(non_greedy=False, minimum=1, maximum=None)
            elif cursor.try_literal("?"):
                quantifier = Quantifier(non_greedy=False, minimum=0, maximum=1)
            elif cursor.try_literal("{"):
                cursor.try_spaces_or_tabs()
                minimum = cursor.try_positive_integer_without_sign()
                cursor.try_spaces_or_tabs()
                found_comma = cursor.try_literal(",")
                cursor.try_spaces_or_tabs()
                maximum = cursor.try_positive_integer_without_sign()
                cursor.try_spaces_or_tabs()

                if minimum is None and maximum is None:
                    return None, Error(
                        "Encountered an opening ``{`` for a quantifier, "
                        "but both minimum and the maximum could not be parsed",
                        cursor,
                    )

                if not found_comma:
                    maximum = minimum

                minimum_zero_if_none = minimum if minimum is not None else 0

                if cursor.try_literal("}?"):
                    quantifier = Quantifier(
                        non_greedy=True, minimum=minimum_zero_if_none, maximum=maximum
                    )
                elif cursor.try_literal("}"):
                    quantifier = Quantifier(
                        non_greedy=False, minimum=minimum_zero_if_none, maximum=maximum
                    )
                else:
                    return None, Error(
                        "Expected closing ``}`` for the quantifier", cursor
                    )
            else:
                pass

            if isinstance(value, Symbol) and (
                value.kind is SymbolKind.START or value.kind is SymbolKind.END
            ):
                assert quantifier is None, (
                    f"Unexpected the symbol {value.kind.value} with a quantifier. "
                    f"This should have been detected before."
                )

            concatenants.append(Term(value=value, quantifier=quantifier))
        else:
            break

        cursor_position = (
            cursor.major_cursor,
            cursor.minor_cursor if cursor.minor_cursor is not None else math.inf,
        )
        assert (
            old_cursor_position < cursor_position
        ), f"Loop invariant: {old_cursor_position=}, {cursor_position=}"

    # NOTE (mristin):
    # Empty terms are possible! For example, parsing ``(())`` needs to allow for an
    # empty union expression in the inner group.

    return Concatenation(concatenants=concatenants), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _parse_union(cursor: Cursor) -> Tuple[Optional[UnionExpr], Optional[Error]]:
    """Try to parse a union of concatenations."""
    if cursor.done():
        return UnionExpr(uniates=[]), None

    concatenation, error = _parse_concatenation(cursor)
    if error is not None:
        return None, error
    assert concatenation is not None

    uniates = [concatenation]

    while cursor.try_literal(literal="|"):
        if cursor.done():
            # NOTE (mristin):
            # An empty term at the end of input is allowed.
            # For example, consider ``"|"``.
            uniates.append(Concatenation(concatenants=[]))
            break

        concatenation, error = _parse_concatenation(cursor)
        if error is not None:
            return None, error
        assert concatenation is not None

        uniates.append(concatenation)

    return UnionExpr(uniates=uniates), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _parse_regex(cursor: Cursor) -> Tuple[Optional[Regex], Optional[Error]]:
    """Try to parse the regular expression and move the cursor."""
    union, error = _parse_union(cursor)
    if error is not None:
        return None, error

    if not cursor.done():
        return None, Error(
            message=(
                "Expected to reach the end of input, "
                "but there is still some unconsumed input left"
            ),
            cursor=cursor,
        )

    assert union is not None
    return Regex(union=union), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def parse(
    values: Sequence[Union[str, FormattedValue]]
) -> Tuple[Optional[Regex], Optional[Error]]:
    """Try to parse the ``values`` into an AST representing the regular expression."""
    cursor = Cursor(values=values)
    parsed, error = _parse_regex(cursor)
    return parsed, error
