"""Fix regular expressions for different engines."""
from typing import Tuple, List

from icontract import require, ensure

from aas_core_codegen.parse.retree import (
    _visitor as retree_visitor,
    _types as retree_types,
)


class _FixForUTF16Regex(retree_visitor.PassThroughVisitor):
    """
    Modify the pattern in-place so that UTF-32 can be dealt by UTF-16-only regex engine.

    Specifically, we need to split UTF-32 characters in the two surrogates since
    UTF-16-only regex engines only work with UTF-16.

    The characters in the range ``\\uD800`` to ``\\uDFFF`` are reserved, so they can
    be used as high surrogates. However, it is still valid to use them as standalone
    characters. Hence, if you use them in your pattern, and the pattern also involves
    UTF-32 characters, the transformed pattern might be more permissive than
    the original one.

    For the problem, see:

    * https://stackoverflow.com/questions/364009/c-sharp-regular-expressions-with-uxxxxxxxx-characters-in-the-pattern
    * https://stackoverflow.com/questions/47605037/unicode-character-range-not-being-consumed-by-regex

    For the UTF-16 specs, ranges and computation of low/high surrogates, see:

    * https://en.wikipedia.org/wiki/UTF-16#Description
    * http://www.russellcottrell.com/greek/utilities/surrogatepaircalculator.htm
    """

    _SUPPLEMENTARY_PLANE_START = 0x00010000
    _SUPPLEMENTARY_PLANE_END = 0x0010FFFF

    # fmt: off
    @staticmethod
    @require(
        lambda code:
        _FixForUTF16Regex._SUPPLEMENTARY_PLANE_START
        <= code <=
        _FixForUTF16Regex._SUPPLEMENTARY_PLANE_END

    )
    @ensure(
        lambda result:
        0xD800 <= result[0] <= 0xDBFF
        and 0xDC00 <= result[1] <= 0xDFFF,
        "High and low surrogates in the expected range"
    )
    # fmt: on
    def _convert_to_surrogates(code: int) -> Tuple[int, int]:
        """Convert a UTF-32 character into its surrogates."""
        high_surrogate = (code - 0x10000) // 0x400 + 0xD800
        low_surrogate = (code - 0x10000) % 0x400 + 0xDC00

        return high_surrogate, low_surrogate

    @staticmethod
    @require(lambda term: isinstance(term.value, retree_types.Char))
    def _character_literal_to_surrogates_if_necessary(
        term: retree_types.Term,
    ) -> List[retree_types.Term]:
        """Expand the character literal to two surrogate characters if necessary."""
        # NOTE (mristin):
        # This assertion is needed for mypy.
        assert isinstance(term.value, retree_types.Char)

        if ord(term.value.character) < _FixForUTF16Regex._SUPPLEMENTARY_PLANE_START:
            return [term]

        high_surrogate, low_surrogate = _FixForUTF16Regex._convert_to_surrogates(
            code=ord(term.value.character)
        )

        # NOTE (mristin):
        # We explicitly encode the character since otherwise this split can not be
        # traced back meaningfully.
        high_surrogate_char = retree_types.Char(
            character=chr(high_surrogate), explicitly_encoded=True
        )
        low_surrogate_char = retree_types.Char(
            character=chr(low_surrogate), explicitly_encoded=True
        )

        output = []  # type: List[retree_types.Term]

        if term.quantifier is not None:
            # NOTE (mristin):
            # We need to put the surrogates in a group so that the quantifier
            # applies to both.
            value = retree_types.Group(
                union=retree_types.UnionExpr(
                    uniates=[
                        retree_types.Concatenation(
                            concatenants=[
                                retree_types.Term(
                                    value=high_surrogate_char, quantifier=None
                                ),
                                retree_types.Term(
                                    value=low_surrogate_char, quantifier=None
                                ),
                            ]
                        )
                    ]
                )
            )

            output.append(retree_types.Term(value=value, quantifier=term.quantifier))
        else:
            # NOTE (mristin):
            # When there is no quantifier, we can simply inject the surrogates
            # as character literals.
            output.append(retree_types.Term(value=high_surrogate_char, quantifier=None))
            output.append(retree_types.Term(value=low_surrogate_char, quantifier=None))

        return output

    @staticmethod
    def _produce_char_char(
        first_code: int, second_code: int
    ) -> retree_types.Concatenation:
        """
        Produce a concatenation as ``{u(code)}{u(code)}``.

        This method helped us to make
        :method:`~_expand_char_set_to_surrogates_if_necessary` somewhat manageable since
        we struggled with the complexity of its code.
        """
        return retree_types.Concatenation(
            concatenants=[
                retree_types.Term(
                    value=retree_types.Char(
                        character=chr(first_code), explicitly_encoded=True
                    ),
                    quantifier=None,
                ),
                retree_types.Term(
                    value=retree_types.Char(
                        character=chr(second_code), explicitly_encoded=True
                    ),
                    quantifier=None,
                ),
            ]
        )

    @staticmethod
    def _produce_char_char_set(
        code: int, range_start: int, range_end: int
    ) -> retree_types.Concatenation:
        """
        Produce a concatenation as ``{u(code)}[{u(range_start)-u(range_end)}]``.

        This method helped us to make
        :method:`~_expand_char_set_to_surrogates_if_necessary` somewhat manageable since
        we struggled with the complexity of its code.
        """
        return retree_types.Concatenation(
            concatenants=[
                retree_types.Term(
                    value=retree_types.Char(
                        character=chr(code), explicitly_encoded=True
                    ),
                    quantifier=None,
                ),
                retree_types.Term(
                    value=retree_types.CharSet(
                        complementing=False,
                        ranges=[
                            retree_types.Range(
                                start=retree_types.Char(
                                    character=chr(range_start), explicitly_encoded=True
                                ),
                                end=retree_types.Char(
                                    character=chr(range_end), explicitly_encoded=True
                                ),
                            )
                        ],
                    ),
                    quantifier=None,
                ),
            ]
        )

    @staticmethod
    def _produce_char_set_char_set(
        first_range_start: int,
        first_range_end: int,
        second_range_start: int,
        second_range_end: int,
    ) -> retree_types.Concatenation:
        """
        Produce a concatenation of the character sets.

        This method helped us to make
        :method:`~_expand_char_set_to_surrogates_if_necessary` somewhat manageable since
        we struggled with the complexity of its code.
        """
        return retree_types.Concatenation(
            concatenants=[
                retree_types.Term(
                    value=retree_types.CharSet(
                        complementing=False,
                        ranges=[
                            retree_types.Range(
                                start=retree_types.Char(
                                    character=chr(first_range_start),
                                    explicitly_encoded=True,
                                ),
                                end=retree_types.Char(
                                    character=chr(first_range_end),
                                    explicitly_encoded=True,
                                ),
                            )
                        ],
                    ),
                    quantifier=None,
                ),
                retree_types.Term(
                    value=retree_types.CharSet(
                        complementing=False,
                        ranges=[
                            retree_types.Range(
                                start=retree_types.Char(
                                    character=chr(second_range_start),
                                    explicitly_encoded=True,
                                ),
                                end=retree_types.Char(
                                    character=chr(second_range_end),
                                    explicitly_encoded=True,
                                ),
                            )
                        ],
                    ),
                    quantifier=None,
                ),
            ]
        )

    @staticmethod
    @require(lambda term: isinstance(term.value, retree_types.CharSet))
    def _expand_char_set_to_surrogates_if_necessary(
        term: retree_types.Term,
    ) -> List[retree_types.Term]:
        """Extend the set with surrogates or expand it to a union, if necessary."""
        ranges_wo_utf32 = []  # type: List[retree_types.Range]
        ranges_w_utf32 = []  # type: List[retree_types.Range]

        # Needed for mypy
        assert isinstance(term.value, retree_types.CharSet)

        for a_range in term.value.ranges:
            if (
                ord(a_range.start.character)
                < _FixForUTF16Regex._SUPPLEMENTARY_PLANE_START
            ) and (
                a_range.end is None
                or (
                    ord(a_range.end.character)
                    < _FixForUTF16Regex._SUPPLEMENTARY_PLANE_START
                )
            ):
                ranges_wo_utf32.append(a_range)
            else:
                ranges_w_utf32.append(a_range)

        if len(ranges_w_utf32) == 0:
            return [term]

        assert not term.value.complementing, (
            "Complementing character sets with one or more ranges "
            "involving UTF-32 characters can not be supported, "
            "since we can not represent them relying "
            "on an UTF-16-only regex engine.\n"
            "\n"
            "This should have been detected before and returned as an error.",
        )

        # NOTE (mristin):
        # Expand the character set into a union of:
        # 1) A character set without any UTF-32 characters
        # 2) One or more character sets representing the ranges involving
        #    UTF-32 characters.

        # noinspection PyListCreation
        uniates = []  # type: List[retree_types.Concatenation]

        if len(ranges_wo_utf32) > 0:
            uniates.append(
                retree_types.Concatenation(
                    concatenants=[
                        retree_types.Term(
                            value=retree_types.CharSet(
                                complementing=False, ranges=ranges_wo_utf32
                            ),
                            quantifier=None,
                        )
                    ]
                )
            )

        for a_range in ranges_w_utf32:
            high_start, low_start = _FixForUTF16Regex._convert_to_surrogates(
                code=ord(a_range.start.character)
            )

            if (a_range.end is None) or (
                a_range.start.character == a_range.end.character
            ):
                uniates.append(
                    _FixForUTF16Regex._produce_char_char(
                        first_code=high_start, second_code=low_start
                    )
                )
            else:
                assert ord(a_range.start.character) < ord(a_range.end.character), (
                    "Start of a range must be smaller than its end.\n"
                    "\n"
                    "This is expected to be detected at the parse stage."
                )

                high_end, low_end = _FixForUTF16Regex._convert_to_surrogates(
                    code=ord(a_range.end.character)
                )

                # noinspection SpellCheckingInspection
                if high_start == high_end:
                    # {high start}[{low start}-{low end}]
                    uniates.append(
                        _FixForUTF16Regex._produce_char_char_set(
                            code=high_start, range_start=low_start, range_end=low_end
                        )
                    )
                else:
                    # {high start}[{low start}-\uDFFF]
                    uniates.append(
                        _FixForUTF16Regex._produce_char_char_set(
                            code=high_start, range_start=low_start, range_end=0xDFFF
                        )
                    )

                    if high_end - high_start > 1:
                        # noinspection SpellCheckingInspection
                        if high_start + 1 == high_end - 1:
                            # {high start + 1}[\uDC00-\uDFFF]
                            uniates.append(
                                _FixForUTF16Regex._produce_char_char_set(
                                    code=high_start + 1,
                                    range_start=0xDC00,
                                    range_end=0xDFFF,
                                )
                            )
                        else:
                            # [{high start + 1}-{high end - 1}][\uDC00-\uDFFF]
                            uniates.append(
                                _FixForUTF16Regex._produce_char_set_char_set(
                                    first_range_start=high_start + 1,
                                    first_range_end=high_end - 1,
                                    second_range_start=0xDC00,
                                    second_range_end=0xDFFF,
                                )
                            )

                    uniates.append(
                        _FixForUTF16Regex._produce_char_char_set(
                            code=high_end, range_start=0xDC00, range_end=low_end
                        )
                    )

        return [
            retree_types.Term(
                value=retree_types.Group(union=retree_types.UnionExpr(uniates=uniates)),
                quantifier=term.quantifier,
            )
        ]

    def visit_concatenation(self, node: retree_types.Concatenation) -> None:
        """Convert character literals to UTF-16, where appropriate."""
        new_concatenants = []  # type: List[retree_types.Term]

        for concatenant in node.concatenants:
            if isinstance(concatenant.value, retree_types.Char):
                new_concatenants.extend(
                    _FixForUTF16Regex._character_literal_to_surrogates_if_necessary(
                        term=concatenant
                    )
                )
            elif isinstance(concatenant.value, retree_types.CharSet):
                new_concatenants.extend(
                    _FixForUTF16Regex._expand_char_set_to_surrogates_if_necessary(
                        term=concatenant
                    )
                )
            else:
                new_concatenants.append(concatenant)

        node.concatenants = new_concatenants
        for concatenant in new_concatenants:
            self.visit(concatenant)


_FIX_FOR_UTF16_REGEX = _FixForUTF16Regex()


def fix_for_utf16_regex_in_place(regex: retree_types.Regex) -> None:
    """
    Modify the pattern in-place so that UTF-32 can be dealt by UTF-16-only regex engine.

    Specifically, we need to split UTF-32 characters in the two surrogates since
    UTF-16-only regex engines only work with UTF-16.

    The characters in the range ``\\uD800`` to ``\\uDFFF`` are reserved, so they can
    be used as high surrogates. However, it is still valid to use them as standalone
    characters. Hence, if you use them in your pattern, and the pattern also involves
    UTF-32 characters, the transformed pattern might be more permissive than
    the original one.

    For the problem, see:

    * https://stackoverflow.com/questions/364009/c-sharp-regular-expressions-with-uxxxxxxxx-characters-in-the-pattern
    * https://stackoverflow.com/questions/47605037/unicode-character-range-not-being-consumed-by-regex

    For the UTF-16 specs, ranges and computation of low/high surrogates, see:

    * https://en.wikipedia.org/wiki/UTF-16#Description
    * http://www.russellcottrell.com/greek/utilities/surrogatepaircalculator.htm
    """
    _FIX_FOR_UTF16_REGEX.visit(regex)


assert fix_for_utf16_regex_in_place.__doc__ == _FIX_FOR_UTF16_REGEX.__doc__
