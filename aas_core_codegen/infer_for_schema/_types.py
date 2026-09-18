"""Provide data structures for the constraint inferences."""
import sys
from typing import Mapping, Sequence, Optional, Final, MutableMapping

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

from icontract import require  # pylint: disable=wrong-import-position

from aas_core_codegen import intermediate  # pylint: disable=wrong-import-position


class LenConstraint:
    """
    Represent the inferred constraint on the ``len`` of something.

    Both bounds are inclusive: ``min_value ≤ len ≤ max_value``.
    """

    min_value: Final[Optional[int]]
    max_value: Final[Optional[int]]

    # fmt: off
    @require(
        lambda min_value, max_value:
        not (min_value is not None and max_value is not None)
        or 0 < min_value <= max_value
    )
    # fmt: on
    def __init__(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        """Initialize with the given values."""
        self.min_value = min_value
        self.max_value = max_value

    def equals(self, other: Optional["LenConstraint"]) -> bool:
        """Return true if the other constraint equals semantically ours."""
        if other is None:
            return False

        return self.min_value == other.min_value and self.max_value == other.max_value

    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"min_value={self.min_value!r}, max_value={self.max_value!r})"
        )


class PatternConstraint:
    """Constrain a string to comply to a regular expression."""

    pattern: Final[str]

    def __init__(self, pattern: str) -> None:
        """Initialize with the given values."""
        self.pattern = pattern

    def equals(self, other: Optional["PatternConstraint"]) -> bool:
        """Return true if the other constraint equals semantically ours."""
        if other is None:
            return False

        return self.pattern == other.pattern

    def __repr__(self) -> str:
        """Represent the constraint with the pattern."""
        return (
            f"<{self.__class__.__name__} at 0x{id(self):x} "
            f"with pattern={self.pattern!r}>"
        )


class SetOfPrimitivesConstraint:
    """Constrain a primitive value to be a member of a pre-defined set of values."""

    a_type: Final[intermediate.PrimitiveType]
    literals: Final[Sequence[intermediate.PrimitiveSetLiteral]]

    # fmt: off
    @require(
        lambda a_type, literals:
        all(
            literal.a_type is a_type
            for literal in literals
        )
    )
    # fmt: on
    def __init__(
        self,
        a_type: intermediate.PrimitiveType,
        literals: Sequence[intermediate.PrimitiveSetLiteral],
    ) -> None:
        """Initialize with the given values."""
        self.a_type = a_type
        self.literals = literals

    def equals(self, other: Optional["SetOfPrimitivesConstraint"]) -> bool:
        """Return true if the other constraint equals semantically ours."""
        if other is None:
            return False

        return (
            self.a_type == other.a_type
            and len(self.literals) == len(other.literals)
            and all(
                intermediate.runtime_id(that_literal)
                == intermediate.runtime_id(other_literal)
                for that_literal, other_literal in zip(self.literals, other.literals)
            )
        )

    def __repr__(self) -> str:
        """Represent the constraint with the pattern."""
        return f"<{self.__class__.__name__} at 0x{id(self):x}>"


class SetOfEnumerationLiteralsConstraint:
    """Constrain a value to be a member of a pre-defined set of values."""

    enumeration: Final[intermediate.Enumeration]
    literals: Final[Sequence[intermediate.EnumerationLiteral]]

    # fmt: off
    @require(
        lambda enumeration, literals:
        all(
            intermediate.runtime_id(literal) in enumeration.literal_id_set
            for literal in literals
        )
    )
    # fmt: on
    def __init__(
        self,
        enumeration: intermediate.Enumeration,
        literals: Sequence[intermediate.EnumerationLiteral],
    ) -> None:
        """Initialize with the given values."""
        self.enumeration = enumeration
        self.literals = literals

    @require(
        lambda self, other: not (other is not None)
        or (other.enumeration is self.enumeration),
        "Both self and other must refer to the same enumeration for "
        "an equality comparison to make sense.",
    )
    def equals(self, other: Optional["SetOfEnumerationLiteralsConstraint"]) -> bool:
        """Return true if the other constraint equals semantically ours."""
        if other is None:
            return False

        return len(self.literals) == len(other.literals) and all(
            intermediate.runtime_id(that_literal)
            == intermediate.runtime_id(other_literal)
            for that_literal, other_literal in zip(self.literals, other.literals)
        )

    def __repr__(self) -> str:
        """Represent the constraint with the pattern."""
        return f"<{self.__class__.__name__} at 0x{id(self):x}>"


class Constraints:
    """
    Represent all the inferred constraints for a value.

    The constraints coming from the constrained primitives are in-lined and hence also
    included in this representation.
    """

    len_constraint: Final[Optional[LenConstraint]]
    patterns: Final[Optional[Sequence[PatternConstraint]]]
    set_of_primitives: Final[Optional[SetOfPrimitivesConstraint]]
    set_of_enumeration_literals: Final[Optional[SetOfEnumerationLiteralsConstraint]]

    @require(lambda patterns: not (patterns is not None) or len(patterns) > 0)
    def __init__(
        self,
        len_constraint: Optional[LenConstraint] = None,
        patterns: Optional[Sequence[PatternConstraint]] = None,
        set_of_primitives: Optional[SetOfPrimitivesConstraint] = None,
        set_of_enumeration_literals: Optional[
            SetOfEnumerationLiteralsConstraint
        ] = None,
    ) -> None:
        """Initialize with the given values."""
        self.len_constraint = len_constraint
        self.patterns = patterns
        self.set_of_primitives = set_of_primitives
        # fmt: off
        self.set_of_enumeration_literals = (
            set_of_enumeration_literals
        )
        # fmt: on

    def is_empty(self) -> bool:
        """Return True if no constraints are set."""
        return (
            self.len_constraint is None
            and self.patterns is None
            and self.set_of_primitives is None
            and self.set_of_enumeration_literals is None
        )


#: Represent the constraints inferred for the given value in a class.
ConstraintsByValue: TypeAlias = Mapping[intermediate.TypeAnnotationUnion, Constraints]

MutableConstraintsByValue: TypeAlias = MutableMapping[
    intermediate.TypeAnnotationUnion, Constraints
]
