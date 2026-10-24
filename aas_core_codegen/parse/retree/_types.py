"""Provide data structures and types for representing regular expressions."""
import abc
import enum
from typing import List, Union, Optional, TypeVar, Generic

from icontract import require, DBC

from aas_core_codegen.parse.tree import FormattedValue

T = TypeVar("T")


class Node(DBC):
    """Represent a generic node in the abstract syntax tree of a regular expression."""

    @abc.abstractmethod
    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        raise NotImplementedError


class Regex(Node):
    """Represent the root of the AST of a regex."""

    #: List of concatenations joined by "|"
    union: "UnionExpr"

    def __init__(
        self,
        union: "UnionExpr",
    ) -> None:
        """Initialize with the given values."""
        self.union = union

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_regex(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_regex(self)


class UnionExpr(Node):
    """
    Represent a regex union of concatenations.

    For example, ``a|b``.
    """

    def __init__(self, uniates: List["Concatenation"]) -> None:
        """Initialize with the given values."""
        self.uniates = uniates

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_union_expr(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_union_expr(self)


class Concatenation(Node):
    """Represent a concatenation of one or more regex terms."""

    def __init__(self, concatenants: List["Term"]) -> None:
        """Initialize with the given values."""
        self.concatenants = concatenants

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_concatenation(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_concatenation(self)


class SymbolKind(enum.Enum):
    """Represent a symbol in the pattern such as start and end."""

    START = "^"
    END = "$"
    DOT = "."


class Symbol(Node):
    """Represent a special symbol."""

    def __init__(self, kind: SymbolKind) -> None:
        """Initialize with the given values."""
        self.kind = kind

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_symbol(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_symbol(self)


TermValueUnion = Union["Group", "Char", "CharSet", FormattedValue, "Symbol"]


class Term(Node):
    """Represent a term in a regex concatenation."""

    # fmt: off
    @require(
        lambda value, quantifier:
        not (
                isinstance(value, Symbol)
                and (
                        value.kind is SymbolKind.START
                        or value.kind is SymbolKind.END
                )
        )
        or quantifier is None,
        "No quantifier for ``^`` and ``$`` symbols"
    )
    # fmt: on
    def __init__(
        self, value: TermValueUnion, quantifier: Optional["Quantifier"]
    ) -> None:
        """Initialize with the given values."""
        self.value = value
        self.quantifier = quantifier

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_term(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_term(self)


class Group(Node):
    """Represent a regex group."""

    def __init__(self, union: UnionExpr) -> None:
        """Initialize with the given values."""
        self.union = union

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_group(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_group(self)


class Char(Node):
    """Represent a character as-is."""

    #: Decoded character
    character: str

    #: If set, the character should be represented encoded (as ``\xHH``, ``\\uXXXX`` or
    #: ``\UXXXXXXXX``, depending on the code of the :attr:`~character`)
    explicitly_encoded: bool

    @require(lambda character: len(character) == 1)
    def __init__(self, character: str, explicitly_encoded: bool = False) -> None:
        """Initialize with the given values."""
        self.character = character
        self.explicitly_encoded = explicitly_encoded

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_char(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_char(self)


class Quantifier(Node):
    """Represent a quantifier applied on a regex term."""

    # fmt: off
    @require(
        lambda minimum, maximum:
        not (maximum is not None)
        or (minimum <= maximum)
    )
    @require(lambda maximum: not (maximum is not None) or maximum >= 0)
    @require(lambda minimum: minimum >= 0)
    # fmt: on
    def __init__(
        self, non_greedy: bool, minimum: int, maximum: Optional[int] = None
    ) -> None:
        """Initialize with the given values."""
        self.non_greedy = non_greedy
        self.minimum = minimum
        self.maximum = maximum

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_quantifier(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_quantifier(self)


class CharSet(Node):
    """Represent a regex character set (also sometimes called *character class*)."""

    def __init__(self, complementing: bool, ranges: List["Range"]) -> None:
        """Initialize with the given values."""
        self.complementing = complementing
        self.ranges = ranges

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_char_set(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_char_set(self)


class Range(Node):
    """Represent a range in a character set."""

    def __init__(self, start: Char, end: Optional[Char]) -> None:
        """Initialize with the given values."""
        self.start = start
        self.end = end

    def accept(self, visitor: "Visitor") -> None:
        """Accept the visitor."""
        visitor.visit_range(self)

    def transform(self, transformer: "Transformer[T]") -> T:
        """Accept the transformer."""
        return transformer.transform_range(self)


class Visitor(DBC):
    """Visit a node and do something about it."""

    def visit(self, node: Node) -> None:
        """Dispatch to the appropriate visiting method."""
        node.accept(self)

    @abc.abstractmethod
    def visit_regex(self, node: Regex) -> None:
        """Visit the ``regex``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_union_expr(self, node: UnionExpr) -> None:
        """Visit the ``union_expr``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_concatenation(self, node: Concatenation) -> None:
        """Visit the ``concatenation``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_symbol(self, node: Symbol) -> None:
        """Visit the ``symbol``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_term(self, node: Term) -> None:
        """Visit the ``term``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_group(self, node: Group) -> None:
        """Visit the ``group``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_char(self, node: Char) -> None:
        """Visit the ``char``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_quantifier(self, node: Quantifier) -> None:
        """Visit the ``quantifier``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_char_set(self, node: CharSet) -> None:
        """Visit the ``char_set``."""
        raise NotImplementedError

    @abc.abstractmethod
    def visit_range(self, node: Range) -> None:
        """Visit the ``range``."""
        raise NotImplementedError


class Transformer(DBC, Generic[T]):
    """Transform the regular expression into something else."""

    def transform(self, node: Node) -> T:
        """Dispatch the ``node`` to the appropriate transforming method."""
        return node.transform(self)

    @abc.abstractmethod
    def transform_regex(self, node: Regex) -> T:
        """Transform the ``regex`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_union_expr(self, node: UnionExpr) -> T:
        """Transform the ``union_expr`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_concatenation(self, node: Concatenation) -> T:
        """Transform the ``concatenation`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_symbol(self, node: Symbol) -> T:
        """Transform the ``symbol`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_term(self, node: Term) -> T:
        """Transform the ``term`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_group(self, node: Group) -> T:
        """Transform the ``group`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_char(self, node: Char) -> T:
        """Transform the ``char`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_quantifier(self, node: Quantifier) -> T:
        """Transform the ``quantifier`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_char_set(self, node: CharSet) -> T:
        """Transform the ``char_set`` into something."""
        raise NotImplementedError

    @abc.abstractmethod
    def transform_range(self, node: Range) -> T:
        """Transform the ``range`` into something."""
        raise NotImplementedError
