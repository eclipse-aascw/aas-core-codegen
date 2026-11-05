# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""
Provide matching functions for different algorithms for inference of the constraints.

The constraints are inferred based on the invariants, so the properties in this context
refer to member access in form of ``self.some_property``.

.. note::

    This module is not only used by aas-core-codegen, but also by downstream clients
    or continuous integrations of other packages, *e.g.*, aas-core-meta.
"""
from typing import Optional, Union

from aas_core_codegen.common import Identifier

from aas_core_codegen.parse import tree as parse_tree


def try_property(node: parse_tree.Node) -> Optional[Identifier]:
    """
    Match access to a property.

    For example, matching ``self.something`` will be a ``"something"``.
    """
    if (
        isinstance(node, parse_tree.Member)
        and isinstance(node.instance, parse_tree.Name)
        and node.instance.identifier == "self"
    ):
        return node.name

    return None


class SingleArgFunctionOnMemberOrName:
    """
    Match a call of a function with a single argument on a member or a variable.

    Mind that we only match arguments, but ignore keyword arguments. This is due to
    simplicity of the implementation and this behavior might change in the future.
    """

    def __init__(
        self,
        function_name: Identifier,
        member_or_name: Union[parse_tree.Member, parse_tree.Name],
    ) -> None:
        """Initialize with the given values."""
        self.function_name = function_name
        self.member_or_name = member_or_name


def try_single_arg_function_on_member_or_name(
    node: parse_tree.Node,
) -> Optional[SingleArgFunctionOnMemberOrName]:
    """
    Match a call of a function with a single argument on a member or a variable.

    For example, something like ``len(self.some_property)`` or ``is_MIME_type(self)``.

    Mind that we only match arguments, but ignore keyword arguments. This is due to
    simplicity of the implementation and this behavior might change in the future.
    """
    if not isinstance(node, parse_tree.FunctionCall):
        return None

    if len(node.args) != 1:
        return None

    if not isinstance(node.args[0], (parse_tree.Name, parse_tree.Member)):
        return None

    # noinspection PyTypeChecker
    return SingleArgFunctionOnMemberOrName(
        function_name=node.name.identifier, member_or_name=node.args[0]
    )


class ConditionalOnProp:
    """Represent an invariant conditioned on an optional property."""

    def __init__(
        self, prop_name: Identifier, consequent: parse_tree.Expression
    ) -> None:
        """Initialize with the given values."""
        self.prop_name = prop_name
        self.consequent = consequent


def try_conditional_on_prop(node: parse_tree.Node) -> Optional[ConditionalOnProp]:
    """
    Match an invariant conditioned on an optional property.

    For example, ``not (self.some_prop is not None) or ...`` or
    ``self.some_prop is None or ...``.
    """
    if isinstance(node, parse_tree.Implication):
        if not isinstance(node.antecedent, parse_tree.IsNotNone):
            return None

        prop_name = try_property(node.antecedent.value)
        if prop_name is None:
            return None

        return ConditionalOnProp(prop_name=prop_name, consequent=node.consequent)

    elif isinstance(node, parse_tree.Or):
        if len(node.values) != 2:
            return None

        if not isinstance(node.values[0], parse_tree.IsNone):
            return None

        # noinspection PyUnresolvedReferences
        prop_name = try_property(node.values[0].value)
        if prop_name is None:
            return None

        return ConditionalOnProp(prop_name=prop_name, consequent=node.values[1])

    else:
        return None
