"""Merge constrained primitives as property constraints."""
import collections
import itertools
from typing import (
    Tuple,
    Optional,
    List,
    Mapping,
    MutableMapping,
    Sequence,
    Set,
    Union,
    Iterator,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Error, assert_never
from aas_core_codegen.infer_for_schema import (
    _len as infer_for_schema_len,
    _pattern as infer_for_schema_pattern,
    _set as infer_for_schema_set,
)
from aas_core_codegen.infer_for_schema._types import (
    Constraints,
    LenConstraint,
    PatternConstraint,
    SetOfPrimitivesConstraint,
    SetOfEnumerationLiteralsConstraint,
    ConstraintsByValue,
    MutableConstraintsByValue,
)


def _min_or_none(that: Optional[int], other: Optional[int]) -> Optional[int]:
    """Compute the minimum or return None if both values are None."""
    if that is not None and other is not None:
        return min(that, other)

    elif that is None and other is not None:
        return other

    elif that is not None and other is None:
        return that

    elif that is None and other is None:
        return None

    else:
        raise AssertionError("Unhandled execution path")


def _max_or_none(that: Optional[int], other: Optional[int]) -> Optional[int]:
    """Compute the maximum or return None if both values are None."""
    if that is not None and other is not None:
        return max(that, other)

    elif that is None and other is not None:
        return other

    elif that is not None and other is None:
        return that

    elif that is None and other is None:
        return None

    else:
        raise AssertionError("Unhandled execution path")


def _merge_len_constraints(
    that: Optional[LenConstraint], other: Optional[LenConstraint]
) -> Optional[LenConstraint]:
    if that is not None and other is not None:
        return LenConstraint(
            min_value=_max_or_none(that.min_value, other.min_value),
            max_value=_min_or_none(that.max_value, other.max_value),
        )

    elif that is not None and other is None:
        return that

    elif that is None and other is not None:
        return other

    elif that is None and other is None:
        return None

    else:
        raise AssertionError("Unhandled execution path")


def _merge_pattern_constraints(
    that: Optional[Sequence[PatternConstraint]],
    other: Optional[Sequence[PatternConstraint]],
) -> Optional[Sequence[PatternConstraint]]:
    if that is not None and other is not None:
        observed_pattern_set: Set[str] = set()

        result: List[PatternConstraint] = []

        for pattern_constraint in itertools.chain(that, other):
            if pattern_constraint.pattern not in observed_pattern_set:
                result.append(pattern_constraint)
                observed_pattern_set.add(pattern_constraint.pattern)

        return result

    elif that is not None and other is None:
        return that

    elif that is None and other is not None:
        return other

    elif that is None and other is None:
        return None

    else:
        raise AssertionError("Unhandled execution path")


def _merge_set_of_primitives_constraints(
    that: Optional[SetOfPrimitivesConstraint],
    other: Optional[SetOfPrimitivesConstraint],
) -> Optional[SetOfPrimitivesConstraint]:
    if that is not None and other is not None:
        if that.a_type != other.a_type:
            raise ValueError(
                "Constraints on sets of primitives of different primitive types "
                f"can not be merged together; that primitive type is {that.a_type}, "
                f"other primitive type is {other.a_type}."
            )

        value_histo: MutableMapping[
            Union[bool, int, float, str, bytearray], int
        ] = collections.OrderedDict()

        literal_by_value: MutableMapping[
            Union[bool, int, float, str, bytearray], intermediate.PrimitiveSetLiteral
        ] = {}

        for literal in itertools.chain(that.literals, other.literals):
            if literal.value not in value_histo:
                value_histo[literal.value] = 1
            else:
                value_histo[literal.value] += 1

            literal_by_value[literal.value] = literal

        return SetOfPrimitivesConstraint(
            # NOTE (mristin):
            # We simply pick one of the types as we assert before that that.a_type
            # and other.a_type must be the same.
            a_type=that.a_type,
            # NOTE (mristin):
            # We need to compute the intersection, so we only pick the literals which we
            # observed twice, once in each list of literals.
            literals=[
                literal_by_value[value]
                for value, count in value_histo.items()
                if count == 2
            ],
        )

    elif that is not None and other is None:
        return that

    elif that is None and other is not None:
        return other

    elif that is None and other is None:
        return None

    else:
        raise AssertionError("Unhandled execution path")


def _merge_set_of_enumeration_literals_constraints(
    that: Optional[SetOfEnumerationLiteralsConstraint],
    other: Optional[SetOfEnumerationLiteralsConstraint],
) -> Optional[SetOfEnumerationLiteralsConstraint]:
    if that is not None and other is not None:
        if that.enumeration is not other.enumeration:
            raise ValueError(
                "Constraints on sets of enumeration literals of different enumerations "
                f"can not be merged together; that enumeration is {that.enumeration}, "
                f"other enumeration is {other.enumeration}."
            )

        literal_by_id: MutableMapping[int, intermediate.EnumerationLiteral] = dict()

        literal_id_histo: MutableMapping[int, int] = collections.OrderedDict()

        for literal in itertools.chain(that.literals, other.literals):
            literal_id = id(literal)

            if literal_id not in literal_id_histo:
                literal_id_histo[literal_id] = 1
            else:
                literal_id_histo[literal_id] += 1

            literal_by_id[literal_id] = literal

        return SetOfEnumerationLiteralsConstraint(
            # NOTE (mristin):
            # We simply pick one of the enumerations as we assert before that
            # enumeration and other enumeration are one and the same.
            enumeration=that.enumeration,
            # NOTE (mristin):
            # We need to compute the intersection, so we only pick the literals which we
            # observed twice, once in each list of literals.
            literals=[
                literal_by_id[literal_id]
                for literal_id, count in literal_id_histo.items()
                if count == 2
            ],
        )

    elif that is not None and other is None:
        return that

    elif that is None and other is not None:
        return other

    elif that is None and other is None:
        return None

    else:
        raise AssertionError("Unhandled execution path")


def _merge_constraints(
    that: Optional[Constraints], other: Optional[Constraints]
) -> Optional[Constraints]:
    """Combine the constraints on tighter bounds."""
    if that is not None and other is not None:
        return Constraints(
            len_constraint=_merge_len_constraints(
                that.len_constraint, other.len_constraint
            ),
            patterns=_merge_pattern_constraints(that.patterns, other.patterns),
            set_of_primitives=_merge_set_of_primitives_constraints(
                that.set_of_primitives, other.set_of_primitives
            ),
            set_of_enumeration_literals=_merge_set_of_enumeration_literals_constraints(
                that.set_of_enumeration_literals, other.set_of_enumeration_literals
            ),
        )

    elif that is not None and other is None:
        return that

    elif that is None and other is not None:
        return other

    elif that is None and other is None:
        return None

    else:
        raise AssertionError("Unhandled execution path")


def _infer_constraints_of_constrained_primitive_without_inheritance(
    constrained_primitive: intermediate.ConstrainedPrimitive,
    pattern_verifications_by_name: infer_for_schema_pattern.PatternVerificationsByName,
) -> Tuple[Optional[Constraints], Optional[List[Error]]]:
    """
    Infer the constraints from the invariants on self of the constrained primitive.

    We do not go up (or down) the inheritance tree -- the constraints from the parents
    are not inherited at this step.

    If there are no constraints inferred from the constrained primitive, we return None.
    """
    errors = []  # type: List[Error]

    len_constraint: Optional[LenConstraint] = None

    if constrained_primitive.constrainee in infer_for_schema_len.LENGTHABLE_PRIMITIVES:
        (
            len_constraint,
            len_constraint_errors,
        ) = infer_for_schema_len.infer_len_constraint_of_self(
            constrained_primitive=constrained_primitive
        )

        if len_constraint_errors is not None:
            errors.extend(len_constraint_errors)
        else:
            assert len_constraint is not None

            # NOTE (mristin):
            # We do not want to keep dummy constraints.
            if len_constraint.min_value is None and len_constraint.max_value is None:
                len_constraint = None

    pattern_constraints: Optional[Sequence[PatternConstraint]] = None

    if constrained_primitive.constrainee is intermediate.PrimitiveType.STR:
        pattern_constraints = infer_for_schema_pattern.infer_patterns_on_self(
            constrained_primitive=constrained_primitive,
            pattern_verifications_by_name=pattern_verifications_by_name,
        )

        if len(pattern_constraints) == 0:
            # NOTE (mristin):
            # We do not want to keep dummy constraints.
            pattern_constraints = None

    if len(errors) > 0:
        return None, errors

    if len_constraint is None and pattern_constraints is None:
        return None, None

    return (
        Constraints(
            len_constraint=len_constraint,
            patterns=pattern_constraints,
            # NOTE (mristin):
            # We do not match the set of primitives on the constrained primitives at the
            # moment, but this could be easily implemented.
            set_of_primitives=None,
            set_of_enumeration_literals=None,
        ),
        None,
    )


@ensure(lambda result: not (result[1] is not None) or len(result[1]) > 0)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _infer_constraints_by_constrained_primitive(
    symbol_table: intermediate.SymbolTable,
    pattern_verifications_by_name: infer_for_schema_pattern.PatternVerificationsByName,
) -> Tuple[
    Optional[MutableMapping[intermediate.ConstrainedPrimitive, Constraints]],
    Optional[List[Error]],
]:
    """
    Infer the constraints from the constrained primitives considering the inheritance.

    If there are no constraints for the given constrained primitive, it is not present
    in the mapping.
    """
    errors: List[Error] = []

    mapping: MutableMapping[intermediate.ConstrainedPrimitive, Constraints] = dict()

    # NOTE (mristin):
    # We perform the first pass where we disregard inheritance and return if there are
    # any errors. We can then be certain that there will be no errors when we stack
    # the constraints considering the inheritance tree.

    for constrained_primitive in symbol_table.constrained_primitives:
        (
            constraints,
            errors_constrained_primitive,
        ) = _infer_constraints_of_constrained_primitive_without_inheritance(
            constrained_primitive=constrained_primitive,
            pattern_verifications_by_name=pattern_verifications_by_name,
        )

        if errors_constrained_primitive is not None:
            errors.append(
                Error(
                    constrained_primitive.parsed.node,
                    f"Failed to infer the schema constraints "
                    f"from constrained primitive {constrained_primitive.name!r}",
                    errors_constrained_primitive,
                )
            )

        if constraints is not None:
            mapping[constrained_primitive] = constraints

    if len(errors) > 0:
        return None, errors

    for our_type in symbol_table.our_types_topologically_sorted:
        if not isinstance(our_type, intermediate.ConstrainedPrimitive):
            continue

        # NOTE (mristin):
        # We rename for clarity when the reader reads the previous code.
        constrained_primitive = our_type

        constraints = mapping.get(constrained_primitive, None)

        # NOTE (mristin):
        # The topological order ensures that we have processed the parents already.
        for parent in constrained_primitive.inheritances:
            # NOTE (mristin):
            # The constrained primitive inherits all the constraints from the parent,
            # and then it might tighten them some more.
            constraints = _merge_constraints(mapping.get(parent, None), constraints)

        if constraints is not None:
            mapping[constrained_primitive] = constraints

    return mapping, None


def _over_non_optional_type_annotations(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> Iterator[intermediate.TypeAnnotationExceptOptional]:
    """
    Iterate recursively over the type annotation and all its nested type annotations.

    The optional type annotations are recursed into, but will not be yielded.
    """
    if not isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        yield type_annotation

    if isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        yield from _over_non_optional_type_annotations(type_annotation.value)

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        yield from _over_non_optional_type_annotations(type_annotation.items)

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        for item in type_annotation.items:
            yield from _over_non_optional_type_annotations(item)

    elif isinstance(
        type_annotation,
        (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
    ):
        pass

    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


@ensure(
    lambda result: not (result[0] is not None)
    or (all(not constraints.is_empty() for constraints in result[0].values()))
)
@ensure(lambda result: not (result[1] is not None) or len(result[1]) >= 1)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _infer_constraints_of_class_values_without_inheritance(
    cls: intermediate.ClassUnion,
    constraints_by_constrained_primitive: Mapping[
        intermediate.ConstrainedPrimitive, Constraints
    ],
    pattern_verifications_by_name: infer_for_schema_pattern.PatternVerificationsByName,
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[MutableConstraintsByValue], Optional[List[Error]],]:
    """
    Infer the constraints on all the possible values of the class.

    The class hierarchy is not taken into account; we consider only the invariants
    defined for this class.
    """
    errors: List[Error] = []

    mapping: MutableConstraintsByValue = dict()

    # region Constraints on length
    (
        len_constraints_from_invariants,
        some_errors,
    ) = infer_for_schema_len.len_constraints_from_invariants(cls=cls)

    if some_errors is not None:
        errors.extend(some_errors)
    else:
        assert len_constraints_from_invariants is not None

        for prop, len_constraint in len_constraints_from_invariants.items():
            if len_constraint.min_value is None and len_constraint.max_value is None:
                continue

            type_anno = intermediate.beneath_optional(prop.type_annotation)

            merged_constraints = _merge_constraints(
                mapping.get(type_anno, None), Constraints(len_constraint=len_constraint)
            )

            if merged_constraints is not None:
                mapping[type_anno] = merged_constraints

    # endregion

    # region Pattern constraints

    patterns_from_invariants_by_property = (
        infer_for_schema_pattern.patterns_from_invariants(
            cls=cls,
            pattern_verifications_by_name=pattern_verifications_by_name,
        )
    )

    for prop, pattern_constraints in patterns_from_invariants_by_property.items():
        if len(pattern_constraints) == 0:
            continue

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        merged_constraints = _merge_constraints(
            mapping.get(type_anno, None), Constraints(patterns=pattern_constraints)
        )

        if merged_constraints is not None:
            mapping[type_anno] = merged_constraints

    # endregion

    # region Constraints from constant sets

    # fmt: off
    set_constraints, some_errors = (
        infer_for_schema_set.infer_set_constraints_by_property_from_invariants(
            cls=cls,
            symbol_table=symbol_table
        )
    )
    # fmt: on

    if some_errors is not None:
        errors.extend(some_errors)
    else:
        assert set_constraints is not None

        for (
            prop,
            set_of_primitives_constraint,
        ) in set_constraints.set_of_primitives_by_property.items():
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            merged_constraints = _merge_constraints(
                mapping.get(type_anno, None),
                Constraints(set_of_primitives=set_of_primitives_constraint),
            )

            if merged_constraints is not None:
                mapping[type_anno] = merged_constraints

        for (
            prop,
            set_of_enumeration_literals_constraint,
        ) in set_constraints.set_of_enumeration_literals_by_property.items():
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            merged_constraints = _merge_constraints(
                mapping.get(type_anno, None),
                Constraints(
                    set_of_enumeration_literals=set_of_enumeration_literals_constraint
                ),
            )

            if merged_constraints is not None:
                mapping[type_anno] = merged_constraints

    # endregion

    if len(errors) > 0:
        return None, errors

    # region Patterns from constrained primitives

    for prop in cls.properties:
        for type_anno in _over_non_optional_type_annotations(prop.type_annotation):
            if not isinstance(type_anno, intermediate.OurTypeAnnotation):
                continue

            if not isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                continue

            constraints = _merge_constraints(
                mapping.get(type_anno, None),
                constraints_by_constrained_primitive.get(type_anno.our_type, None),
            )

            if constraints is not None and not constraints.is_empty():
                mapping[type_anno] = constraints

    # endregion

    assert len(errors) == 0
    return mapping, None


@ensure(lambda result: not (result[1] is not None) or len(result[1]) > 0)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def infer_constraints_by_class(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[
    Optional[Mapping[intermediate.ClassUnion, ConstraintsByValue]],
    Optional[List[Error]],
]:
    """Infer the constraints from the invariants and constrained primitives."""
    errors = []  # type: List[Error]

    pattern_verifications_by_name = (
        infer_for_schema_pattern.map_pattern_verifications_by_name(
            verifications=symbol_table.verification_functions
        )
    )

    (
        constraints_by_constrained_primitive,
        some_errors,
    ) = _infer_constraints_by_constrained_primitive(
        symbol_table=symbol_table,
        pattern_verifications_by_name=pattern_verifications_by_name,
    )

    if some_errors is not None:
        errors.extend(some_errors)

    if len(errors) > 0:
        return None, errors

    assert constraints_by_constrained_primitive is not None

    mapping: MutableMapping[intermediate.ClassUnion, MutableConstraintsByValue] = dict()

    for cls in symbol_table.classes:
        (
            constraints_by_value,
            some_errors,
        ) = _infer_constraints_of_class_values_without_inheritance(
            cls=cls,
            constraints_by_constrained_primitive=constraints_by_constrained_primitive,
            pattern_verifications_by_name=pattern_verifications_by_name,
            symbol_table=symbol_table,
        )

        if some_errors is not None:
            errors.extend(some_errors)
            continue

        assert constraints_by_value is not None

        mapping[cls] = constraints_by_value

    if len(errors) > 0:
        return None, errors

    # NOTE (mristin):
    # We stack now the constraints considering the class hierarchy. The topological
    # order guarantees that the parents have been processed before the children.
    for our_type in symbol_table.our_types_topologically_sorted:
        if not isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            continue

        # NOTE (mristin):
        # We introduce the alias for better readability with the previous section.
        cls = our_type

        that_constraints_by_value = mapping[cls]

        for parent in cls.inheritances:
            parent_constraints_by_value = mapping[parent]

            # NOTE (mristin):
            # The class inherits all the constraints from the parent, and then it might
            # tighten them some more.
            for type_anno, parent_constraints in parent_constraints_by_value.items():
                merged_constraints = _merge_constraints(
                    parent_constraints,
                    that_constraints_by_value.get(type_anno, None),
                )

                if merged_constraints is not None:
                    that_constraints_by_value[type_anno] = merged_constraints

    return mapping, None


def tightening_steps_from_other_to_that_constraints(
    that: Constraints, other: Optional[Constraints]
) -> Optional[Constraints]:
    """
    Identify constraints to be updated to go from ``other`` to ``that``.

    This function is used to spot tightening of the constraints in the children
    classes which override the parents' constraints.

    We assume that the in-lining and merging of the constraints has been already
    performed before. Any constraints in the ``other`` which differs from ``that``
    constraint is assumed to be "overridden" (*i.e.*, tightened) by ``that`` constraint.

    You can think of the resulting constraint list as all the constraints that a child
    class (corresponding to ``that``) imposes in addition to constraints that are already
    imposed by the parent class (corresponding to ``other``).
    """
    if other is None:
        return that

    len_constraint: Optional[LenConstraint] = None

    if other.len_constraint is not None:
        assert that.len_constraint is not None, (
            "The ``other``, corresponding to a parent class, defines a length constraint, "
            "but the child class, corresponding to ``that``, relaxes the constraint and "
            "defines no length constraints. This breaks the behavioral subtyping. "
            "Have the constraints been properly merged and inlined?\n"
            f"{other.len_constraint=}"
        )

        len_constraint = (
            that.len_constraint
            if not that.len_constraint.equals(other.len_constraint)
            else None
        )
    else:
        len_constraint = that.len_constraint

    patterns: Optional[Sequence[PatternConstraint]] = None

    if other.patterns is not None:
        assert that.patterns is not None, (
            "The ``other``, corresponding to a parent class, defines patterns, "
            "but the child class, corresponding to ``that``, relaxes the constraint and "
            "defines no patterns. This breaks the behavioral subtyping. "
            "Have the constraints been properly merged and inlined?\n"
            f"{other.patterns=}, {that.patterns=}"
        )

        other_pattern_set = set(
            pattern_constraint.pattern for pattern_constraint in other.patterns
        )

        that_pattern_set = set(
            pattern_constraint.pattern for pattern_constraint in that.patterns
        )

        assert other_pattern_set.intersection(that_pattern_set) == other_pattern_set, (
            "The ``other``, corresponding to a parent class, defines more patterns "
            "than the child class, corresponding to ``that`` -- this amounts to relaxing "
            "constraints. This breaks the behavioral subtyping. "
            "Have the constraints been properly merged and inlined?\n"
            f"{other.patterns=}, {that.patterns=}"
        )

        # NOTE (mristin):
        # We select only patterns which are not already defined in ``other``, as
        # the ``other`` corresponds to the parent class.
        patterns = [
            pattern_constraint
            for pattern_constraint in that.patterns
            if pattern_constraint.pattern not in other_pattern_set
        ]

        if len(patterns) == 0:
            patterns = None
    else:
        patterns = that.patterns

    set_of_primitives: Optional[SetOfPrimitivesConstraint] = None

    if other.set_of_primitives is not None:
        assert that.set_of_primitives is not None, (
            "The ``other``, corresponding to a parent class, defines set of primitives, "
            "but the child class, corresponding to ``that``, relaxes the constraint and "
            "defines no set of primitives. This breaks the behavioral subtyping. "
            "Have the constraints been properly merged and inlined?\n"
            f"{other.set_of_primitives=}"
        )

        other_set_of_primitives = set(
            literal.value for literal in other.set_of_primitives.literals
        )

        that_set_of_primitives = set(
            literal.value for literal in that.set_of_primitives.literals
        )

        assert (
            that_set_of_primitives.intersection(other_set_of_primitives)
            == that_set_of_primitives
        ), (
            "The ``that``, corresponding to a child class, can only tighten the set of "
            "allowed primitives from ``other``, which corresponds to the parent class. "
            "However, ``that`` defines more literals -- this breaks the behavioral "
            "subtyping. Have the constraints been properly merged and inlined?\n"
            f"{other.set_of_primitives=}, {that.set_of_primitives=}"
        )

        if not that.set_of_primitives.equals(other.set_of_primitives):
            set_of_primitives = that.set_of_primitives

    else:
        set_of_primitives = that.set_of_primitives

    set_of_enumeration_literals: Optional[SetOfEnumerationLiteralsConstraint] = None

    if other.set_of_enumeration_literals is not None:
        assert that.set_of_enumeration_literals is not None, (
            "The ``other``, corresponding to a parent class, defines set of "
            "enumeration literals, but the child class, corresponding to ``that``, "
            "relaxes the constraint and defines no set of enumeration literals. This "
            "breaks the behavioral subtyping. Have the constraints been properly merged "
            "and inlined?\n"
            f"{other.set_of_enumeration_literals=}"
        )

        other_set_of_enumeration_literals = set(
            literal.value for literal in other.set_of_enumeration_literals.literals
        )

        that_set_of_enumeration_literals = set(
            literal.value for literal in that.set_of_enumeration_literals.literals
        )

        assert (
            that_set_of_enumeration_literals.intersection(
                other_set_of_enumeration_literals
            )
            == that_set_of_enumeration_literals
        ), (
            "The ``that``, corresponding to a child class, can only tighten the set of "
            "allowed enumeration literals from ``other``, which corresponds to "
            "the parent class. However, ``that`` defines more literals -- this breaks "
            "the behavioral subtyping. Have the constraints been properly merged and "
            "inlined?\n"
            f"{other.set_of_enumeration_literals=}, {that.set_of_enumeration_literals=}"
        )

        if not that.set_of_enumeration_literals.equals(
            other.set_of_enumeration_literals
        ):
            set_of_enumeration_literals = that.set_of_enumeration_literals
    else:
        set_of_enumeration_literals = that.set_of_enumeration_literals

    tightening = Constraints(
        len_constraint=len_constraint,
        patterns=patterns,
        set_of_primitives=set_of_primitives,
        set_of_enumeration_literals=set_of_enumeration_literals,
    )

    return tightening
