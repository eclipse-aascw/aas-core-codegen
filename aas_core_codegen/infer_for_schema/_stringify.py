"""Represent inferred constraints as strings."""
from typing import Union, Optional

from aas_core_codegen import stringify, intermediate
from aas_core_codegen.infer_for_schema._types import (
    LenConstraint,
    PatternConstraint,
    SetOfPrimitivesConstraint,
    SetOfEnumerationLiteralsConstraint,
    Constraints,
)


def _stringify_len_constraint(
    that: LenConstraint,
) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("min_value", that.min_value),
            stringify.Property("max_value", that.max_value),
        ],
    )

    return result


def _stringify_pattern_constraint(
    that: PatternConstraint,
) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("pattern", that.pattern),
        ],
    )

    return result


def _stringify_set_of_primitives_constraint(
    that: SetOfPrimitivesConstraint,
) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("a_type", that.a_type.name),
            stringify.Property(
                "literals", list(map(intermediate.stringify, that.literals))
            ),
        ],
    )

    return result


def _stringify_set_of_enumeration_literals_constraint(
    that: SetOfEnumerationLiteralsConstraint,
) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property(
                "enumeration",
                f"Reference to {that.enumeration.__class__.__name__} "
                f"{that.enumeration.name}",
            ),
            stringify.Property(
                "literals",
                [
                    f"Reference to {literal.__class__.__name__} {literal.name}"
                    for literal in that.literals
                ],
            ),
        ],
    )

    return result


def _stringify_constraints(that: Constraints) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property(
                "len_constraint",
                _stringify_len_constraint(that.len_constraint)
                if that.len_constraint is not None
                else None,
            ),
            stringify.Property(
                "patterns",
                [_stringify_pattern_constraint(pattern) for pattern in that.patterns]
                if that.patterns is not None
                else None,
            ),
            stringify.Property(
                "set_of_primitives",
                _stringify_set_of_primitives_constraint(that.set_of_primitives)
                if that.set_of_primitives is not None
                else None,
            ),
            stringify.Property(
                "set_of_enumeration_literals",
                _stringify_set_of_enumeration_literals_constraint(
                    that.set_of_enumeration_literals
                )
                if that.set_of_enumeration_literals is not None
                else None,
            ),
        ],
    )

    return result


Dumpable = Union[
    LenConstraint,
    PatternConstraint,
    SetOfPrimitivesConstraint,
    SetOfEnumerationLiteralsConstraint,
    Constraints,
]

_DISPATCH = {
    LenConstraint: _stringify_len_constraint,
    PatternConstraint: _stringify_pattern_constraint,
    SetOfPrimitivesConstraint: _stringify_set_of_primitives_constraint,
    # fmt: off
    SetOfEnumerationLiteralsConstraint: (
        _stringify_set_of_enumeration_literals_constraint
    ),
    # fmt: on
    Constraints: _stringify_constraints,
}

stringify.assert_dispatch_exhaustive(dispatch=_DISPATCH, dumpable=Dumpable)


def _stringify(that: Optional[Dumpable]) -> Optional[stringify.Entity]:
    """Dispatch to the correct ``_stringify_*`` method."""
    if that is None:
        return None

    stringify_func = _DISPATCH.get(that.__class__)
    if stringify_func is None:
        raise AssertionError(
            f"No stringify function could be found for the class {that.__class__}"
        )

    stringified = stringify_func(that)  # type: ignore
    assert isinstance(stringified, stringify.Entity)
    stringify.assert_compares_against_dict(stringified, that)

    return stringified


def dump(that: Optional[Dumpable]) -> str:
    """Produce a string representation of the ``dumpable`` for testing or debugging."""
    if that is None:
        return repr(None)

    stringified = _stringify(that)
    return stringify.dump(stringified)
