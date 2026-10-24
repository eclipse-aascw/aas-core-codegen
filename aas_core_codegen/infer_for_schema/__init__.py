"""Infer constraints representable in common schemas such as JSON Schema or XSD."""

from aas_core_codegen.infer_for_schema import (
    _inline,
    _stringify,
    _types,
)

LenConstraint = _types.LenConstraint
PatternConstraint = _types.PatternConstraint
SetOfPrimitivesConstraint = _types.SetOfPrimitivesConstraint
SetOfEnumerationLiteralsConstraint = _types.SetOfEnumerationLiteralsConstraint

Constraints = _types.Constraints
ConstraintsByValue = _types.ConstraintsByValue

infer_constraints_by_class = _inline.infer_constraints_by_class

tightening_steps_from_other_to_that_constraints = (
    _inline.tightening_steps_from_other_to_that_constraints
)

dump = _stringify.dump
