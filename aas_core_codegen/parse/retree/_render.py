"""Render the parsed (and possibly modified) regular expression back into values."""
import io
from typing import List, Union, Optional, Mapping

import more_itertools
from icontract import require, ensure

from aas_core_codegen.common import assert_never
from aas_core_codegen.parse.retree._types import (
    Transformer,
    Range,
    Regex,
    UnionExpr,
    Concatenation,
    Term,
    Symbol,
    Group,
    Char,
    Quantifier,
    CharSet,
    SymbolKind,
)
from aas_core_codegen.parse.tree import FormattedValue


class Renderer(Transformer[List[Union[str, FormattedValue]]]):
    """Render the regular expression back into a joined string."""

    _ESCAPING_IN_CHARACTER_LITERALS = {
        "\t": "\\t",
        "\n": "\\n",
        "\r": "\\r",
        "\f": "\\f",
        "\v": "\\v",
        ".": "\\.",
        "^": "\\^",
        "$": "\\$",
        "{": "\\{",
        "}": "\\}",
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "?": "\\?",
        "*": "\\*",
        "+": "\\+",
        "\\": "\\\\",
    }

    _ESCAPING_IN_RANGE = {
        "\t": "\\t",
        "\n": "\\n",
        "\r": "\\r",
        "\f": "\\f",
        "\v": "\\v",
        "[": "\\[",
        "]": "\\]",
        "\\": "\\\\",
        "-": "\\-",
    }

    @require(
        lambda escaping: all(len(key) == 1 for key in escaping),
        "The ``escaping`` works only on characters, not on arbitrary text",
    )
    # fmt: on
    def char_to_str_and_escape_or_encode_if_necessary(
        self, node: Char, escaping: Mapping[str, str]
    ) -> List[Union[str, FormattedValue]]:
        """Convert the ``node`` to a string, and escape and/or encode appropriately."""
        if not node.explicitly_encoded:
            escaped = escaping.get(node.character, None)
            if escaped is not None:
                result: List[Union[str, FormattedValue]] = [escaped]
            else:
                result = [node.character]

            return result
        else:
            code = ord(node.character)
            if code < 255:
                return [f"\\x{code:02x}"]
            else:
                return [node.character.encode("unicode_escape").decode("ascii")]

    def transform_regex(self, node: Regex) -> List[Union[str, FormattedValue]]:
        """Transform the ``regex``."""
        return self.transform(node.union)

    def transform_union_expr(self, node: UnionExpr) -> List[Union[str, FormattedValue]]:
        """Transform the ``union_expr``."""
        output = []  # type: List[Union[str, FormattedValue]]

        for i, concatenation in enumerate(node.uniates):
            if i > 0:
                output.append("|")

            output.extend(self.transform(concatenation))

        return output

    def transform_concatenation(
        self, node: Concatenation
    ) -> List[Union[str, FormattedValue]]:
        """Transform the ``concatenation``."""
        output = []  # type: List[Union[str, FormattedValue]]
        for concatenant in node.concatenants:
            output.extend(self.transform(concatenant))

        return output

    def transform_symbol(self, node: Symbol) -> List[Union[str, FormattedValue]]:
        """Transform the ``symbol``."""
        if node.kind is SymbolKind.START:
            return ["^"]
        elif node.kind is SymbolKind.END:
            return ["$"]
        elif node.kind is SymbolKind.DOT:
            return ["."]
        else:
            assert_never(node.kind)

    def transform_term(self, node: Term) -> List[Union[str, FormattedValue]]:
        """Transform the ``term``."""
        output = []  # type: List[Union[str, FormattedValue]]

        if isinstance(node.value, FormattedValue):
            output.append(node.value)
        elif isinstance(node.value, Char):
            output.extend(
                self.char_to_str_and_escape_or_encode_if_necessary(
                    node=node.value, escaping=Renderer._ESCAPING_IN_CHARACTER_LITERALS
                )
            )
        else:
            # noinspection PyTypeChecker
            output.extend(self.transform(node.value))

        if node.quantifier is not None:
            output.extend(self.transform(node.quantifier))

        return output

    def transform_group(self, node: Group) -> List[Union[str, FormattedValue]]:
        """Transform the ``group``."""
        output = ["("]  # type: List[Union[str, FormattedValue]]
        output.extend(self.transform(node.union))
        output.append(")")
        return output

    def transform_char(self, node: Char) -> List[Union[str, FormattedValue]]:
        """Transform the ``char``."""
        raise AssertionError(
            f"The responsibility of this method should have been covered either "
            f"by {Renderer.transform_term.__name__} "
            f"or {Renderer.transform_char_set.__name__}"
        )

    def transform_quantifier(
        self, node: Quantifier
    ) -> List[Union[str, FormattedValue]]:
        """Transform the ``quantifier``."""
        quantifier: str

        if node.maximum is not None:
            if node.minimum == node.maximum:
                quantifier = f"{{{node.minimum}}}"
            else:
                if node.minimum == 0:
                    if node.maximum == 1:
                        quantifier = "?"
                    else:
                        quantifier = f"{{0,{node.maximum}}}"
                else:
                    quantifier = f"{{{node.minimum},{node.maximum}}}"
        else:
            if node.minimum == 0:
                quantifier = "*"
            elif node.minimum == 1:
                quantifier = "+"
            else:
                quantifier = f"{{{node.minimum},}}"

        if node.non_greedy:
            quantifier += "?"

        return [quantifier]

    def transform_char_set(self, node: CharSet) -> List[Union[str, FormattedValue]]:
        """Transform the ``char_set``."""
        output = ["["]  # type: List[Union[str, FormattedValue]]

        already_output_something = False
        if node.complementing:
            already_output_something = True
            output.append("^")

        for i, a_range in enumerate(node.ranges):
            # NOTE (mristin):
            # The first and the last dash need no escaping.
            if (
                i in (0, len(node.ranges) - 1)
                and a_range.end is None
                and a_range.start.character == "-"
                and not a_range.start.explicitly_encoded
            ):
                output.append("-")

            # NOTE (mristin):
            # The caret needs to be escaped only if it is the very first character
            # in the character set.
            elif (
                i == 0
                and a_range.start.character == "^"
                and not a_range.start.explicitly_encoded
                and not already_output_something
            ):
                output.append("\\^")
            else:
                output.extend(
                    self.char_to_str_and_escape_or_encode_if_necessary(
                        node=a_range.start, escaping=Renderer._ESCAPING_IN_RANGE
                    )
                )

                if a_range.end is not None:
                    output.append("-")

                    output.extend(
                        self.char_to_str_and_escape_or_encode_if_necessary(
                            node=a_range.end, escaping=Renderer._ESCAPING_IN_RANGE
                        )
                    )

        output.append("]")

        return output

    def transform_range(self, node: Range) -> List[Union[str, FormattedValue]]:
        """Transform the ``range``."""
        raise AssertionError(
            f"The responsibility of this function should have been taken care of "
            f"by {Renderer.transform_char_set.__name__}"
        )


_RENDERER = Renderer()


# fmt: off
@ensure(
    lambda result:
    not (len(result) > 0)
    or (
        not any(
            isinstance(that, str) and isinstance(other, str)
            for that, other in more_itertools.windowed(result, 2)
        )
    )
)
# fmt: on
def render(
    regex: Regex, renderer: Optional[Renderer] = None
) -> List[Union[str, FormattedValue]]:
    """
    Render the regular expression ``regex`` to a joined string.

    If no ``renderer`` is supplied, the default renderer is used.
    """
    if renderer is None:
        renderer = _RENDERER

    values = renderer.transform(regex)

    # NOTE (mristin):
    # Compress the consecutive strings into a single string to have a shorter
    # representation

    output = []  # type: List[Union[str, FormattedValue]]
    buffer = io.StringIO()
    for value in values:
        if isinstance(value, str):
            buffer.write(value)
        elif isinstance(value, FormattedValue):
            buffered = buffer.getvalue()
            if len(buffered) > 0:
                output.append(buffered)
                buffer = io.StringIO()

            output.append(value)
        else:
            assert_never(value)

    buffered = buffer.getvalue()
    if len(buffered) > 0:
        output.append(buffered)

    return output
