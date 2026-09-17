"""Infer the constraints on a property based on constant sets."""
import collections
from typing import Optional, Tuple, MutableMapping, List, Mapping, Union, Sequence

from icontract import ensure, require

from aas_core_codegen.common import Identifier, Error, assert_never
from aas_core_codegen.infer_for_schema._types import (
    SetOfPrimitivesConstraint,
    SetOfEnumerationLiteralsConstraint,
)
from aas_core_codegen.parse import tree as parse_tree
from aas_core_codegen import intermediate
from aas_core_codegen.infer_for_schema import match as infer_for_schema_match


class _PropNameInNamedContainer:
    """Hold the information for matches of the form ``self.something in X``."""

    def __init__(
        self, prop_name: Identifier, container_name: Identifier, node: parse_tree.IsIn
    ) -> None:
        """Initialize with the given values."""
        self.prop_name = prop_name
        self.container_name = container_name
        self.node = node


def _match_prop_in_named_container(
    node: parse_tree.Node,
) -> Optional[_PropNameInNamedContainer]:
    """Match the expression ``self.something in Something``."""
    if not isinstance(node, parse_tree.IsIn):
        return None

    prop_name = infer_for_schema_match.try_property(node.member)
    if prop_name is None:
        return None

    if not isinstance(node.container, parse_tree.Name):
        return None

    return _PropNameInNamedContainer(
        prop_name=prop_name, container_name=node.container.identifier, node=node
    )


class SetConstraintsByProperty:
    """Group the set constraints by the class properties."""

    def __init__(
        self,
        set_of_primitives_by_property: Mapping[
            intermediate.Property, SetOfPrimitivesConstraint
        ],
        set_of_enumeration_literals_by_property: Mapping[
            intermediate.Property, SetOfEnumerationLiteralsConstraint
        ],
    ) -> None:
        """Initialize with the given values."""
        self.set_of_primitives_by_property = set_of_primitives_by_property
        # fmt: off
        self.set_of_enumeration_literals_by_property = (
                set_of_enumeration_literals_by_property
        )
        # fmt: on


class _IntersectionOfPrimitiveSetLiterals:
    """Track an intersection of primitive set literals."""

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
        """Initialize with the given set."""
        self.a_type = a_type
        self._literals = literals

        self._count_by_literal_value = {
            literal.value: 0 for literal in literals
        }  # type: MutableMapping[Union[bool, int, float, str, bytearray], int]

        self._counter = 0

    # fmt: off
    @require(
        lambda self, literals:
        all(
            literal.a_type is self.a_type
            for literal in literals
        )
    )
    # fmt: on
    def observe(self, literals: Sequence[intermediate.PrimitiveSetLiteral]) -> None:
        """Limit the intersection by the literals in-place."""
        for literal in literals:
            if literal.value in self._count_by_literal_value:
                self._count_by_literal_value[literal.value] += 1

        self._counter += 1

    def compute_literals(self) -> List[intermediate.PrimitiveSetLiteral]:
        """Compute the literals contained in the intersection."""
        return [
            literal
            for literal in self._literals
            if self._count_by_literal_value[literal.value] == self._counter
        ]


@require(lambda constraints: len(constraints) >= 1)
def intersect_set_of_primitives_constraints(
    constraints: Sequence[SetOfPrimitivesConstraint],
) -> SetOfPrimitivesConstraint:
    """Compute the intersection over all the primitive set literals."""
    intersection = None  # type: Optional[_IntersectionOfPrimitiveSetLiterals]
    for constraint in constraints:
        if intersection is None:
            intersection = _IntersectionOfPrimitiveSetLiterals(
                a_type=constraint.a_type, literals=constraint.literals
            )
        else:
            intersection.observe(literals=constraint.literals)

    assert intersection is not None

    return SetOfPrimitivesConstraint(
        a_type=intersection.a_type, literals=intersection.compute_literals()
    )


class _IntersectionOfEnumerationLiterals:
    """Track an intersection of enumeration literals by their Python object ID."""

    def __init__(self, literals: Sequence[intermediate.EnumerationLiteral]) -> None:
        """Initialize with the given set."""
        self._literals = literals

        self._count_by_literal_id = {
            id(literal): 0 for literal in literals
        }  # type: MutableMapping[int, int]

        self._counter = 0

    def observe(self, literals: Sequence[intermediate.EnumerationLiteral]) -> None:
        """Limit the literals in the intersection."""
        for literal in literals:
            if id(literal) in self._count_by_literal_id:
                self._count_by_literal_id[id(literal)] += 1

        self._counter += 1

    def compute_literals(self) -> List[intermediate.EnumerationLiteral]:
        """Compute the literals contained in the intersection."""
        return [
            literal
            for literal in self._literals
            if self._count_by_literal_id[id(literal)] == self._counter
        ]


# fmt: off
@require(
    lambda constraints:
    all(
        constraint.enumeration is constraints[0].enumeration
        for constraint in constraints
    )
)
@require(
    lambda constraints:
    all(
        all(
            id(literal) in constraint.enumeration.literal_id_set
            for literal in constraint.literals
        )
        for constraint in constraints
    )
)
@require(
    lambda constraints:
    len(constraints) >= 1
)
# fmt: on
def intersect_set_of_enumeration_literals_constraints(
    constraints: Sequence[SetOfEnumerationLiteralsConstraint],
) -> SetOfEnumerationLiteralsConstraint:
    """Compute the intersection over all the set literals."""
    enumeration = None  # type: Optional[intermediate.Enumeration]
    intersection = None  # type: Optional[_IntersectionOfEnumerationLiterals]

    for constraint in constraints:
        if intersection is None:
            enumeration = constraint.enumeration

            intersection = _IntersectionOfEnumerationLiterals(
                literals=constraint.literals
            )
        else:
            intersection.observe(literals=constraint.literals)

    assert enumeration is not None
    assert intersection is not None

    return SetOfEnumerationLiteralsConstraint(
        enumeration=enumeration, literals=intersection.compute_literals()
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def infer_set_constraints_by_property_from_invariants(
        cls: intermediate.Class,
        symbol_table: intermediate.SymbolTable
) -> Tuple[
    Optional[SetConstraintsByProperty],
    Optional[List[Error]]
]:
    # fmt: on
    """
    Match all the named constant sets that a property needs to belong to.

    Even if a property is optional, the constraint will still be inferred.

    The constraints are not exhaustive. We only infer constraints based on invariants
    which involve constant sets. It might be that the actual invariants are tighter.
    """
    errors = []  # type: List[Error]

    # fmt: off
    sets_of_primitives_by_property: MutableMapping[
        intermediate.Property,
        List[SetOfPrimitivesConstraint]
    ] = collections.defaultdict(lambda: [])
    # fmt: on

    # fmt: off
    sets_of_enumeration_literals_by_property: MutableMapping[
        intermediate.Property, List[SetOfEnumerationLiteralsConstraint]
    ] = collections.defaultdict(lambda: [])
    # fmt: on

    # region Collect

    for invariant in cls.invariants:
        # NOTE (mristin):
        # We consider only the genuine invariants of the class, and ignore
        # the invariants of its ancestors.

        if invariant.specified_for is not cls:
            continue

        # Match ``not (self.something is not None) or self.something in X``
        conditional_on_prop = infer_for_schema_match.try_conditional_on_prop(
            invariant.body
        )
        if conditional_on_prop is not None:
            node = conditional_on_prop.consequent
        else:
            # Match ``self.something in X``
            node = invariant.body

        matches = []  # type: List[_PropNameInNamedContainer]

        if isinstance(node, parse_tree.And):
            for value_node in node.values:
                match = _match_prop_in_named_container(value_node)
                if match is not None:
                    matches.append(match)
        else:
            match = _match_prop_in_named_container(node)
            if match is not None:
                matches.append(match)

        for match in matches:
            prop = cls.properties_by_name.get(match.prop_name, None)
            if prop is None:
                errors.append(
                    Error(
                        match.node.member.original_node,
                        f"The property {match.prop_name!r} does not "
                        f"belong to the class {cls.name!r}"
                    )
                )
                continue

            constant = symbol_table.constants_by_name.get(match.container_name, None)
            if constant is None:
                continue

            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(constant, intermediate.ConstantPrimitive):
                continue
            elif isinstance(constant, intermediate.ConstantSetOfPrimitives):
                prop_primitive_type = intermediate.try_primitive_type(type_anno)

                if prop_primitive_type is not constant.a_type:
                    errors.append(
                        Error(
                            match.node.container.original_node,
                            f"The container is a constant set "
                            f"of {constant.a_type.value}'s while "
                            f"the property {prop.name!r} in class {cls.name!r} "
                            f"has type {prop.type_annotation}"
                        )
                    )
                    continue

                sets_of_primitives_by_property[prop].append(
                    SetOfPrimitivesConstraint(
                        a_type=constant.a_type,
                        literals=constant.literals
                    )
                )

            elif isinstance(constant, intermediate.ConstantSetOfEnumerationLiterals):
                if not (
                        isinstance(type_anno, intermediate.OurTypeAnnotation)
                        and isinstance(type_anno.our_type, intermediate.Enumeration)
                        and (type_anno.our_type is constant.enumeration)
                ):
                    errors.append(
                        Error(
                            match.node.container.original_node,
                            f"The container is a constant set "
                            f"of enumeration literals of {constant.enumeration.name} "
                            f"while the property {prop.name!r} in class {cls.name!r} "
                            f"has type {prop.type_annotation}"
                        )
                    )
                    continue

                sets_of_enumeration_literals_by_property[prop].append(
                    SetOfEnumerationLiteralsConstraint(
                        enumeration=constant.enumeration,
                        literals=constant.literals
                    )
                )

            else:
                assert_never(constant)

    if len(errors) > 0:
        return None, errors

    # endregion

    # region Reduce

    # fmt: off
    set_of_primitives_by_property: MutableMapping[
        intermediate.Property,
        SetOfPrimitivesConstraint
    ] = dict()
    # fmt: on

    # fmt: off
    set_of_enumeration_literals_by_property: MutableMapping[
        intermediate.Property, SetOfEnumerationLiteralsConstraint
    ] = dict()
    # fmt: on

    for prop, set_of_primitives_constraints in sets_of_primitives_by_property.items():
        set_of_primitives_by_property[prop] = intersect_set_of_primitives_constraints(
            constraints=set_of_primitives_constraints
        )

    for prop, set_of_enumeration_literals_constraints in (
            sets_of_enumeration_literals_by_property.items()
    ):
        set_of_enumeration_literals_by_property[prop] = (
            intersect_set_of_enumeration_literals_constraints(
                constraints=set_of_enumeration_literals_constraints
            )
        )

    # endregion

    return SetConstraintsByProperty(
        set_of_primitives_by_property=set_of_primitives_by_property,
        set_of_enumeration_literals_by_property=set_of_enumeration_literals_by_property
    ), None
