"""Infer the constraints on the length of a property value."""
from typing import MutableMapping, Optional, Tuple, List, Union, Sequence

from icontract import require, ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    assert_never,
    Error,
    Identifier,
    assert_union_of_descendants_exhaustive,
)
from aas_core_codegen.infer_for_schema import match as infer_for_schema_match
from aas_core_codegen.infer_for_schema._types import LenConstraint
from aas_core_codegen.parse import tree as parse_tree


class _Constraint:
    """
    Represent a constraint on the ``len`` of something.

    That something can be, *e.g.*, a property or ``self``.
    """

    def __init__(self, node: parse_tree.Node) -> None:
        self.node = node


class _MinLength(_Constraint):
    """Represent the constraint that the ``len`` is ≥ ``value``."""

    def __init__(self, node: parse_tree.Node, value: int) -> None:
        """Initialize with the given values."""
        _Constraint.__init__(self, node=node)
        self.value = value


class _MaxLength(_Constraint):
    """Represent the constraint that the ``len`` is ≤ ``value``."""

    def __init__(self, node: parse_tree.Node, value: int) -> None:
        """Initialize with the given values."""
        _Constraint.__init__(self, node=node)
        self.value = value


class _ExactLength(_Constraint):
    """Represent the constraint that the ``len`` is == ``value``."""

    def __init__(self, node: parse_tree.Node, value: int) -> None:
        """Initialize with the given values."""
        _Constraint.__init__(self, node=node)
        self.value = value


class _LenOnMemberOrName:
    """Represent a match on a call to ``len(.)`` on a member or a name."""

    def __init__(
        self, member_or_name: Union[parse_tree.Member, parse_tree.Name]
    ) -> None:
        """Initialize with the given values."""
        self.member_or_name = member_or_name


def _match_len_on_member_or_name(node: parse_tree.Node) -> Optional[_LenOnMemberOrName]:
    """
    Match expressions like ``len(self.something)``.

    Return the name of the property, or None, if not matched.
    """
    mtch = infer_for_schema_match.try_single_arg_function_on_member_or_name(node)

    if mtch is None:
        return None

    if mtch.function_name == "len":
        return _LenOnMemberOrName(member_or_name=mtch.member_or_name)

    return None


def _match_int_constant(node: parse_tree.Node) -> Optional[int]:
    """Match an integer constant."""
    if isinstance(node, parse_tree.Constant) and isinstance(node.value, int):
        return node.value

    return None


class _LenConstraintOnMemberOrName:
    """
    Represent a match on an expression like ``len(.) < 42``.

    Unlike :py:class:`LenConstraint`, which represents an *inferred* constrained over
    multiple constraints, this class represents a constraint as it is derived directly
    from the parse tree.
    """

    def __init__(
        self,
        member_or_name: Union[parse_tree.Member, parse_tree.Name],
        constraint: "_ConstraintUnion",
    ) -> None:
        """Initialize with the given values."""
        self.member_or_name = member_or_name
        self.constraint = constraint


def _match_len_constraint_on_member_or_name(
    node: parse_tree.Node,
) -> Optional[_LenConstraintOnMemberOrName]:
    """
    Match the constraint on ``len`` of a member or a variable.

    For example, something like ``len(self.something) < 42`` or ``len(self) == 42``.

    Return the match, or None if not matched.
    """
    if not isinstance(node, parse_tree.Comparison):
        return None

    constraint = None  # type: Optional[_ConstraintUnion]

    # region Match a comparison like ``len(self.something) < 42``

    len_on_member_or_name = _match_len_on_member_or_name(node.left)
    constant = _match_int_constant(node.right)

    if len_on_member_or_name is not None and constant is not None:
        if node.op is parse_tree.Comparator.LT:
            # len(self.something) < 42
            constraint = _MaxLength(node=node, value=constant - 1)
        elif node.op is parse_tree.Comparator.LE:
            # len(self.something) <= 42
            constraint = _MaxLength(node=node, value=constant)
        elif node.op is parse_tree.Comparator.EQ:
            # len(self.something) == 42
            constraint = _ExactLength(node=node, value=constant)
        elif node.op is parse_tree.Comparator.GT:
            # len(self.something) > 42
            constraint = _MinLength(node=node, value=constant + 1)
        elif node.op is parse_tree.Comparator.GE:
            # len(self.something) >= 42
            constraint = _MinLength(node=node, value=constant)
        elif node.op is parse_tree.Comparator.NE:
            # We intentionally ignore the invariants such as ``len(n) != 42``
            # as there is no meaningful way to represent it simply in a schema.
            pass
        else:
            assert_never(node.op)

        if constraint is not None:
            return _LenConstraintOnMemberOrName(
                member_or_name=len_on_member_or_name.member_or_name,
                constraint=constraint,
            )

    # endregion

    # region Match a comparison like ``42 < self.something``

    constant = _match_int_constant(node.left)
    len_on_member_or_name = _match_len_on_member_or_name(node.right)

    if constant is not None and len_on_member_or_name is not None:
        if node.op is parse_tree.Comparator.LT:
            # 42 < len(self.something)
            constraint = _MinLength(node=node, value=constant + 1)
        elif node.op is parse_tree.Comparator.LE:
            # 42 <= len(self.something)
            constraint = _MinLength(node=node, value=constant)
        elif node.op is parse_tree.Comparator.EQ:
            # 42 == len(self.something)
            constraint = _ExactLength(node=node, value=constant)
        elif node.op is parse_tree.Comparator.GT:
            # 42 > len(self.something)
            constraint = _MaxLength(node=node, value=constant - 1)
        elif node.op is parse_tree.Comparator.GE:
            # 42 >= len(self.something)
            constraint = _MaxLength(node=node, value=constant)
        elif node.op is parse_tree.Comparator.NE:
            # We intentionally ignore the invariants such as ``len(n) != 42``
            # as there is no meaningful way to represent it simply in a schema.
            pass
        else:
            assert_never(node.op)

        if constraint is not None:
            return _LenConstraintOnMemberOrName(
                member_or_name=len_on_member_or_name.member_or_name,
                constraint=constraint,
            )

    # endregion

    return None


def min_with_none(*args: Optional[int]) -> Optional[int]:
    """
    Compute a minimum among the arguments where None are ignored.

    >>> min_with_none(2, None, 1)
    1

    >>> min_with_none(None, None)
    """
    # NOTE (mristin):
    # There is no one-liner in Python for this.
    # See: https://stackoverflow.com/questions/2295461/list-minimum-in-python-with-none
    minimum = None  # type: Optional[int]
    for arg in args:
        if minimum is None:
            minimum = arg
        else:
            if arg is not None:
                minimum = min(arg, minimum)

    return minimum


def max_with_none(*args: Optional[int]) -> Optional[int]:
    """
    Compute a maximum among the arguments where None are ignored.

    >>> max_with_none(2, None, 1)
    2

    >>> max_with_none(None, None)
    """
    # NOTE (mristin):
    # There is no one-liner in Python for this.
    # See: https://stackoverflow.com/questions/2295461/list-minimum-in-python-with-none
    maximum = None  # type: Optional[int]
    for arg in args:
        if maximum is None:
            maximum = arg
        else:
            if arg is not None:
                maximum = max(arg, maximum)

    return maximum


class _LenConstraintOnProperty:
    """Represent a len constraint such as ``len(self.something) < 42``."""

    def __init__(self, prop_name: Identifier, constraint: "_ConstraintUnion") -> None:
        """Initialize with the given values."""
        self.prop_name = prop_name
        self.constraint = constraint


def _match_len_constraint_on_property(
    node: parse_tree.Expression,
) -> Optional[_LenConstraintOnProperty]:
    """Match a len constraint on a property such as ``len(self.something) < 42``."""
    len_constraint_on_member_or_name = _match_len_constraint_on_member_or_name(node)
    if len_constraint_on_member_or_name:
        prop_name = infer_for_schema_match.try_property(
            len_constraint_on_member_or_name.member_or_name
        )

        if prop_name is not None:
            return _LenConstraintOnProperty(
                prop_name=prop_name,
                constraint=len_constraint_on_member_or_name.constraint,
            )

    return None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _reduce_constraints(
    constraints: Sequence["_ConstraintUnion"],
) -> Tuple[Optional[LenConstraint], Optional[List[str]]]:
    """
    Reduce a list of constraints to a range that encompasses all the constraints.

    Return the reduced constraint, or a list of errors.
    """
    min_len = None  # type: Optional[int]
    max_len = None  # type: Optional[int]
    exact_len = None  # type: Optional[int]

    errors = []  # type: List[str]

    for constraint in constraints:
        if isinstance(constraint, _MinLength):
            min_len = max_with_none(constraint.value, min_len)

        elif isinstance(constraint, _MaxLength):
            max_len = min_with_none(constraint.value, max_len)

        elif isinstance(constraint, _ExactLength):
            if exact_len is not None:
                errors.append(
                    f"The exact length, {exact_len}, contradicts "
                    f"another exactly expected length {constraint.value}.",
                )
            exact_len = constraint.value

        else:
            assert_never(constraint)

    if exact_len is not None:
        if min_len is not None and min_len > exact_len:
            errors.append(
                f"the minimum length, {min_len}, "
                f"contradicts the exactly expected length {exact_len}.",
            )

        if max_len is not None and exact_len > max_len:
            errors.append(
                f"the maximum length, {max_len}, "
                f"contradicts the exactly expected length {exact_len}.",
            )

    if min_len is not None and max_len is not None and min_len > max_len:
        errors.append(
            f"the minimum length, {min_len}, "
            f"contradicts the maximum length {max_len}.",
        )

    if len(errors) > 0:
        return None, errors

    if exact_len is not None:
        min_len = exact_len
        max_len = exact_len

    return LenConstraint(min_value=min_len, max_value=max_len), None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def len_constraints_from_invariants(
    cls: intermediate.Class,
) -> Tuple[
    Optional[MutableMapping[intermediate.Property, LenConstraint]],
    Optional[List[Error]],
]:
    """
    Infer the constraints on ``len`` for every property of the class ``cls``.

    Even if a property is optional, the constraint will still be inferred. Please be
    careful that this does not scramble your cardinality constraints (which start from
    zero for optional properties).

    The constraints are not exhaustive. We only infer constraints based on invariants
    which involve constants. It might be that the actual invariants are tighter.
    """
    constraint_map = dict()  # type: MutableMapping[Identifier, List[_ConstraintUnion]]

    # region Infer the constraints in the loose form from all the invariants

    # NOTE (mristin):
    # We iterate only once through the invariants instead of inferring the constraints
    # for each property individually to be able to keep linear time complexity.

    errors = []  # type: List[Error]

    for invariant in cls.invariants:
        # NOTE (mristin):
        # We consider only the genuine invariants of the class, and ignore
        # the invariants of its ancestors.

        if invariant.specified_for is not cls:
            continue

        # noinspection PyUnusedLocal
        len_constraint_on_prop = None  # type: Optional[_LenConstraintOnProperty]

        # Match ``self.something is None or len(self.something) < X``
        conditional_on_prop = infer_for_schema_match.try_conditional_on_prop(
            invariant.body
        )
        if conditional_on_prop is not None:
            len_constraint_on_prop = _match_len_constraint_on_property(
                conditional_on_prop.consequent
            )

        else:
            # Match ``len(self.something) < X``
            len_constraint_on_prop = _match_len_constraint_on_property(invariant.body)

        if len_constraint_on_prop is not None:
            if len_constraint_on_prop.prop_name not in cls.properties_by_name:
                errors.append(
                    Error(
                        invariant.body.original_node,
                        f"The property {len_constraint_on_prop.prop_name} does not "
                        f"appear in the properties of the class {cls.name}",
                    )
                )
                continue

            constraints = constraint_map.get(len_constraint_on_prop.prop_name, None)
            if constraints is None:
                constraints = []
                constraint_map[len_constraint_on_prop.prop_name] = constraints

            constraints.append(len_constraint_on_prop.constraint)

    # endregion

    if len(errors) > 0:
        return None, errors

    # region Compress the loose constraints

    result = dict()  # type: MutableMapping[intermediate.Property, LenConstraint]

    for prop_name, constraints in constraint_map.items():
        reduced_constraint, reduction_errors = _reduce_constraints(
            constraints=constraints
        )

        if reduction_errors is not None:
            for reduction_error in reduction_errors:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The property {prop_name} has conflicting invariants "
                        f"on the length: {reduction_error}",
                    )
                )
            continue

        assert reduced_constraint is not None

        prop = cls.properties_by_name.get(prop_name, None)
        assert prop is not None, (
            f"Expected the property {prop_name!r} in the properties "
            f"of the class {cls}"
        )

        result[prop] = reduced_constraint

    # endregion

    if len(errors) > 0:
        return None, errors

    return result, None


LENGTHABLE_PRIMITIVES = frozenset(
    [intermediate.PrimitiveType.STR, intermediate.PrimitiveType.BYTEARRAY]
)


# fmt: off
@require(
    lambda constrained_primitive:
    constrained_primitive.constrainee in LENGTHABLE_PRIMITIVES,
    "The length inferred only for meaningful primitives"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def infer_len_constraint_of_self(
    constrained_primitive: intermediate.ConstrainedPrimitive,
) -> Tuple[Optional[LenConstraint], Optional[List[Error]]]:
    """
    Infer the constraint on ``len(self)``.

    The constraints are not exhaustive. We only infer constraints based on invariants
    which involve constants. It might be that the actual invariants are tighter.
    """
    # region Infer the constraints in the loose form from all the invariants

    errors = []  # type: List[Error]

    constraints = []  # type: List[_ConstraintUnion]

    for invariant in constrained_primitive.invariants:
        # NOTE (mristin):
        # We consider only the genuine invariants of the constrained primitive, and
        # ignore the invariants of its ancestors.
        if invariant.specified_for is not constrained_primitive:
            continue

        # Match something like ``len(self) < 42``
        len_constraint_on_member_or_name = _match_len_constraint_on_member_or_name(
            invariant.body
        )

        if len_constraint_on_member_or_name:
            # Abbreviate for readability
            member_or_name = len_constraint_on_member_or_name.member_or_name

            if isinstance(member_or_name, parse_tree.Name) and (
                member_or_name.identifier == "self"
            ):
                constraints.append(len_constraint_on_member_or_name.constraint)

        # Otherwise, ignore the invariant as we do not understand it.

    # endregion

    if len(errors) > 0:
        return None, errors

    # region Compress the loose constraints

    reduced_constraint, reduction_errors = _reduce_constraints(constraints=constraints)

    if reduction_errors is not None:
        for reduction_error in reduction_errors:
            errors.append(
                Error(
                    constrained_primitive.parsed.node,
                    f"There are conflicting invariants on the length: "
                    f"{reduction_error}",
                )
            )
        return None, errors

    assert reduced_constraint is not None

    # endregion

    return reduced_constraint, None


_ConstraintUnion = Union[_MinLength, _MaxLength, _ExactLength]
assert_union_of_descendants_exhaustive(union=_ConstraintUnion, base_class=_Constraint)
