"""Provide a visitor implementation so that we do not have to duplicate the code."""
from aas_core_codegen.parse.retree._types import (
    Visitor,
    Regex,
    UnionExpr,
    Concatenation,
    Term,
    Group,
    Char,
    Quantifier,
    CharSet,
    Range,
    Symbol,
)
from aas_core_codegen.parse.tree import FormattedValue


class PassThroughVisitor(Visitor):
    """Visit all the nodes recursively without any action."""

    def visit_regex(self, node: Regex) -> None:
        """Visit the ``regex``."""
        self.visit(node.union)

    def visit_union_expr(self, node: UnionExpr) -> None:
        """Visit the ``union_expr``."""
        for concatenation in node.uniates:
            self.visit(concatenation)

    def visit_concatenation(self, node: Concatenation) -> None:
        """Visit the ``concatenation``."""
        for concatenant in node.concatenants:
            self.visit(concatenant)

    def visit_symbol(self, node: Symbol) -> None:
        """Visit the ``symbol``."""
        # NOTE (mristin):
        # The recursion stops here.

    def visit_term(self, node: Term) -> None:
        """Visit the ``term``."""
        if not isinstance(node.value, FormattedValue):
            self.visit(node.value)

        if node.quantifier is not None:
            self.visit(node.quantifier)

    def visit_group(self, node: Group) -> None:
        """Visit the ``group``."""
        self.visit(node.union)

    def visit_char(self, node: Char) -> None:
        """Visit the ``char``."""
        # NOTE (mristin):
        # The recursion stops here.

    def visit_quantifier(self, node: Quantifier) -> None:
        """Visit the ``quantifier``."""
        # NOTE (mristin):
        # The recursion stops here.

    def visit_char_set(self, node: CharSet) -> None:
        """Visit the ``char_set``."""
        for a_range in node.ranges:
            self.visit(a_range)

    def visit_range(self, node: Range) -> None:
        """Visit the ``range``."""
        # NOTE (mristin):
        # The recursion stops here.
