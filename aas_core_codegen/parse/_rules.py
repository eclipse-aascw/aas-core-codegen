"""
Define the parse rules for transforming Python AST to our custom AST.

This module provides translation from a very general Python AST to our more specific,
domain-related syntax.

For comparison, :py:mod:`aas_core_codegen.intermediate` is responsible for
semantic analysis, simplifications and resolution to environments and actual symbols.
"""

import abc
import ast
import os
import pathlib
import sys
from typing import Tuple, Optional, List, Mapping, Type, Sequence, Union, cast

from icontract import ensure

from aas_core_codegen.common import Identifier, Error, assert_never
from aas_core_codegen.parse import tree

# noinspection PyTypeChecker
_AST_COMPARATOR_TO_OURS = {
    ast.Lt: tree.Comparator.LT,
    ast.LtE: tree.Comparator.LE,
    ast.Gt: tree.Comparator.GT,
    ast.GtE: tree.Comparator.GE,
    ast.Eq: tree.Comparator.EQ,
    ast.NotEq: tree.Comparator.NE,
}  # type: Mapping[Type[ast.cmpop], tree.Comparator]

_AST_COMPARATORS = tuple(_AST_COMPARATOR_TO_OURS.keys())


class _Parse(abc.ABC):
    """Define a parse rule from a Python AST node to our custom AST."""

    @abc.abstractmethod
    def matches(self, node: ast.AST) -> bool:
        """Return True if the node can be matched by the rule."""
        raise NotImplementedError()

    @abc.abstractmethod
    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        """Transform the Python node to our custom node."""
        raise NotImplementedError()


class _ParseComparison(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], _AST_COMPARATORS)
            and len(node.comparators) == 1
        )

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Compare)

        left, error = ast_node_to_our_node(cast(ast.AST, node.left))
        if error is not None:
            return None, error

        assert isinstance(left, tree.Expression), f"{left=}"

        op = _AST_COMPARATOR_TO_OURS[type(node.ops[0])]

        right, error = ast_node_to_our_node(node.comparators[0])
        if error is not None:
            return None, error

        assert isinstance(right, tree.Expression), f"{right=}"

        return tree.Comparison(left=left, op=op, right=right, original_node=node), None


class _ParseIsIn(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.In)
            and len(node.comparators) == 1
        )

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Compare)

        member, error = ast_node_to_our_node(cast(ast.AST, node.left))
        if error is not None:
            return None, error

        assert isinstance(member, tree.Expression), f"{member=}"

        container, error = ast_node_to_our_node(node.comparators[0])
        if error is not None:
            return None, error

        assert isinstance(container, tree.Expression), f"{container=}"

        return tree.IsIn(member=member, container=container, original_node=node), None


class _ParseAnyOrAll(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("any", "all")
        )

    # noinspection PyUnresolvedReferences,PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("any", "all")
        )

        if len(node.keywords) > 0:
            return None, Error(
                node,
                f"Expected no keyword arguments in ``{node.func.id}``, "
                f"but got {len(node.keywords)}",
            )

        if len(node.args) != 1:
            return None, Error(
                node,
                f"Expected exactly one argument in ``{node.func.id}``, "
                f"but got {len(node.args)}",
            )

        if not isinstance(node.args[0], ast.GeneratorExp):
            return None, Error(
                node,
                f"Expected a generator expression in ``{node.func.id}``, "
                f"but got: {ast.dump(node)}",
            )

        generator_exp = node.args[0]

        # noinspection PyUnresolvedReferences
        our_condition, error = ast_node_to_our_node(generator_exp.elt)
        if error is not None:
            return None, error

        assert isinstance(our_condition, tree.Expression), f"{our_condition=}"

        if len(generator_exp.generators) != 1:
            return None, Error(
                node,
                f"Expected exactly one generator in ``{node.func.id}``, "
                f"but got {len(generator_exp.generators)}",
            )

        generator = generator_exp.generators[0]
        if not isinstance(generator, ast.comprehension):
            return None, Error(
                generator, f"Expected a comprehension, but got: {ast.dump(generator)}"
            )

        if not isinstance(generator.target, ast.Name):
            return None, Error(
                generator,
                f"Expected the target of the generator to be a name, "
                f"but got: {ast.dump(generator.target)}",
            )

        our_variable, error = ast_node_to_our_node(generator.target)
        if error is not None:
            return None, error
        assert isinstance(our_variable, tree.Name), f"{our_variable=}"

        # region Parse the generator

        our_generator: tree.ForUnion

        if (
            isinstance(generator.iter, ast.Call)
            and isinstance(generator.iter.func, ast.Name)
            and generator.iter.func.id == "range"
        ):
            if len(generator.iter.args) != 2:
                return None, Error(
                    generator.iter,
                    f"Expected exactly to arguments to a call of ``range``, "
                    f"but got: {len(generator.iter.args)}",
                )

            if len(generator.iter.keywords) != 0:
                return None, Error(
                    generator.iter,
                    f"Expected no keyword arguments to a call of ``range``, "
                    f"but got: {len(generator.iter.keywords)}",
                )

            start, error = ast_node_to_our_node(generator.iter.args[0])
            if error is not None:
                return None, error

            end, error = ast_node_to_our_node(generator.iter.args[1])
            if error is not None:
                return None, error

            assert isinstance(start, tree.Expression), f"{start=}"
            assert isinstance(end, tree.Expression), f"{end=}"

            our_generator = tree.ForRange(
                variable=our_variable, start=start, end=end, original_node=generator
            )

        else:
            our_iteration, error = ast_node_to_our_node(generator.iter)
            if error is not None:
                return None, error

            assert isinstance(our_iteration, tree.Expression), f"{our_iteration=}"

            our_generator = tree.ForEach(
                variable=our_variable, iteration=our_iteration, original_node=generator
            )

        # endregion

        # noinspection PyUnusedLocal
        factory_to_use: Union[Type[tree.Any], Type[tree.All]]
        if node.func.id == "any":
            factory_to_use = tree.Any
        elif node.func.id == "all":
            factory_to_use = tree.All
        else:
            raise AssertionError(f"Unexpected {node.func.id=}")

        return (
            factory_to_use(
                generator=our_generator,
                condition=our_condition,
                original_node=node,
            ),
            None,
        )


class _ParseCall(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Call)

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Call)

        args = []  # type: List[tree.Expression]
        for arg_node in node.args:
            arg, error = ast_node_to_our_node(arg_node)
            if error is not None:
                return None, error

            if not isinstance(arg, tree.Expression):
                return None, Error(
                    arg_node,
                    f"Expected the argument to a call to be an expression, "
                    f"but got: {arg}",
                )

            args.append(arg)

        if len(node.keywords) > 0:
            return None, Error(
                node,
                "Keyword arguments are not supported since "
                "many implementation languages do not support them",
            )

        if isinstance(node.func, ast.Name):
            name, error = ast_node_to_our_node(node.func)
            if error is not None:
                return None, error

            assert name is not None
            assert isinstance(name, tree.Name)

            return (
                tree.FunctionCall(name=name, args=args, original_node=node),
                None,
            )
        else:
            member, error = ast_node_to_our_node(node.func)
            if error is not None:
                return None, error

            assert isinstance(
                member, tree.Member
            ), f"Expected a member for {ast.dump(node.func)=}, but got: {member=}"

            return tree.MethodCall(member=member, args=args, original_node=node), None


class _ParseConstant(_Parse):
    def matches(self, node: ast.AST) -> bool:
        # fmt: off
        return (
                isinstance(node, ast.Constant)
                and isinstance(node.value, (bool, int, float, str))
        ) or (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float))
        )
        # fmt: on

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        # fmt: off
        assert (
                isinstance(node, ast.Constant)
                and isinstance(node.value, (bool, int, float, str))
        ) or (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float))
        )
        # fmt: on

        if isinstance(node, ast.Constant):
            assert isinstance(node.value, (bool, int, float, str))
            return tree.Constant(value=node.value, original_node=node), None

        elif isinstance(node, ast.UnaryOp):
            assert (
                isinstance(node.op, ast.USub)
                and isinstance(node.operand, ast.Constant)
                and isinstance(node.operand.value, (int, float))
            )

            return tree.Constant(value=-node.operand.value, original_node=node), None

        else:
            raise AssertionError(
                "Unexpected execution path with node: {ast.dump(node)}"
            )


class _ParseTuple(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Tuple)

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Tuple)

        values = []  # type: List[tree.Expression]
        for elt_node in node.elts:
            value, error = ast_node_to_our_node(elt_node)
            if error is not None:
                return None, error

            assert value is not None

            if not isinstance(value, tree.Expression):
                return None, Error(
                    elt_node,
                    f"Expected an expression as an element of a tuple literal, "
                    f"but got: {value}",
                )

            values.append(value)

        return tree.Tuple(values=values, original_node=node), None


class _ParseImplication(_Parse):
    # noinspection PyUnresolvedReferences
    def matches(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.BoolOp)
            and isinstance(node.op, ast.Or)
            and len(node.values) == 2
            and isinstance(node.values[0], ast.UnaryOp)
            and isinstance(node.values[0].op, ast.Not)
        )

    # noinspection PyUnresolvedReferences,PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert (
            isinstance(node, ast.BoolOp)
            and isinstance(node.op, ast.Or)
            and len(node.values) == 2
            and isinstance(node.values[0], ast.UnaryOp)
            and isinstance(node.values[0].op, ast.Not)
        )

        antecedent, error = ast_node_to_our_node(node.values[0].operand)
        if error is not None:
            return None, error

        assert isinstance(antecedent, tree.Expression), f"{antecedent=}"

        consequent, error = ast_node_to_our_node(node.values[1])
        if error is not None:
            return None, error

        assert isinstance(consequent, tree.Expression), f"{consequent=}"

        return (
            tree.Implication(
                antecedent=antecedent, consequent=consequent, original_node=node
            ),
            None,
        )


class _ParseMember(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Attribute)

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Attribute)

        instance, error = ast_node_to_our_node(node.value)
        if error is not None:
            return None, error

        assert isinstance(instance, tree.Expression), f"{instance=}"

        return (
            tree.Member(
                instance=instance, name=Identifier(node.attr), original_node=node
            ),
            None,
        )


class _ParseIndex(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Subscript)

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Subscript)

        collection, error = ast_node_to_our_node(node.value)
        if error is not None:
            return None, error

        # NOTE (mristin, 2022-07-11):
        # There were breaking changes between Python 3.8 and 3.9 in ``ast`` module.
        # Relevant to this particular piece of parsing logic is the deprecation of
        # ``ast.Index``.
        #
        # Hence, we need to switch on Python version and get the underlying slice value
        # explicitly.
        #
        # See deprecation notes just at the end of:
        # https://docs.python.org/3/library/ast.html#ast.AST

        if sys.version_info < (3, 9):
            if not isinstance(node.slice, ast.Index):
                return None, Error(
                    node.slice,
                    f"We expect only indices in index access, "
                    f"but got: {ast.dump(node.slice)}",
                )

            index, error = ast_node_to_our_node(node.slice.value)
            if error is not None:
                return None, error
        else:
            index, error = ast_node_to_our_node(node.slice)
            if error is not None:
                return None, error

        assert isinstance(collection, tree.Expression), f"{collection=}"
        assert isinstance(index, tree.Expression), f"{index=}"

        return tree.Index(collection=collection, index=index, original_node=node), None


class _ParseName(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Name)

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Name)

        return tree.Name(identifier=Identifier(node.id), original_node=node), None


class _ParseIsNoneOrIsNotNone(_Parse):
    # noinspection PyUnresolvedReferences
    def matches(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], (ast.Is, ast.IsNot))
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Constant)
            and node.comparators[0].value is None
        )

    # noinspection PyUnresolvedReferences,PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], (ast.Is, ast.IsNot))
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Constant)
            and node.comparators[0].value is None
        )

        value, error = ast_node_to_our_node(node.left)
        if error is not None:
            return None, error

        assert value is not None
        assert isinstance(value, tree.Expression), f"{value=}"

        if isinstance(node.ops[0], ast.Is):
            return tree.IsNone(value=value, original_node=node), None
        elif isinstance(node.ops[0], ast.IsNot):
            return tree.IsNotNone(value=value, original_node=node), None
        else:
            raise AssertionError(f"Unexpected: {node.ops[0]=}")


class _ParseNot(_Parse):
    # noinspection PyUnresolvedReferences
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)

    # noinspection PyUnresolvedReferences,PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)

        operand, error = ast_node_to_our_node(node.operand)
        if error is not None:
            return None, error

        assert operand is not None
        assert isinstance(operand, tree.Expression), f"{operand=}"

        return tree.Not(operand=operand, original_node=node), None


class _ParseAndOrOr(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or))

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or))

        values = []  # type: List[tree.Expression]
        for value_node in node.values:
            value, error = ast_node_to_our_node(value_node)
            if error is not None:
                return None, error

            assert value is not None
            assert isinstance(value, tree.Expression), f"{value=}"

            values.append(value)

        if isinstance(node.op, ast.And):
            return tree.And(values=values, original_node=node), None
        elif isinstance(node.op, ast.Or):
            return tree.Or(values=values, original_node=node), None
        else:
            raise AssertionError(f"Unexpected: {node.op=}")


class _ParseAddOrSub(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub))

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub))

        left, error = ast_node_to_our_node(node.left)
        if error is not None:
            return None, error

        assert isinstance(left, tree.Expression), f"{left=}"

        right, error = ast_node_to_our_node(node.right)
        if error is not None:
            return None, error

        assert isinstance(right, tree.Expression), f"{right=}"

        if isinstance(node.op, ast.Add):
            return tree.Add(left=left, right=right, original_node=node), None
        elif isinstance(node.op, ast.Sub):
            return tree.Sub(left=left, right=right, original_node=node), None
        else:
            raise AssertionError(f"Unexpected: {node.op=}")


class _ParseExpression(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Expr)

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Expr)

        value, error = ast_node_to_our_node(node.value)
        if error is not None:
            return None, error

        assert value is not None

        return value, None


class _ParseJoinedStr(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.JoinedStr)

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.JoinedStr)

        values = []  # type: List[Union[str, tree.FormattedValue]]

        assert isinstance(node, ast.JoinedStr)
        for value_node in node.values:
            if isinstance(value_node, ast.Constant):
                if not isinstance(value_node.value, str):
                    return None, Error(
                        value_node,
                        "Unexpected non-string constant in the joined string",
                    )

                values.append(value_node.value)

            elif isinstance(value_node, ast.FormattedValue):
                if value_node.conversion != -1:
                    return None, Error(
                        value_node,
                        f"We do not support any conversions at the moment. "
                        f"Expected -1, but got conversion: {value_node.conversion}",
                    )

                if value_node.format_spec is not None:
                    return None, Error(
                        value_node,
                        f"We do not support any format spec at the moment. "
                        f"Expected None, but got format spec: {value_node.format_spec}",
                    )

                # noinspection PyTypeChecker
                value, error = ast_node_to_our_node(node=value_node.value)
                if error is not None:
                    return None, error

                assert value is not None

                assert isinstance(value, tree.Expression)
                values.append(
                    tree.FormattedValue(value=value, original_node=value_node)
                )

            elif isinstance(value_node, ast.expr):
                return None, Error(
                    value_node,
                    f"We do not know how to parse the Python ast.expr "
                    f"as part of the JoinedStr.values: {ast.dump(value_node)}; "
                    f"please notify the developers.",
                )
            else:
                assert_never(value_node)

        return tree.JoinedStr(values=values, original_node=node), None


class _ParseAssignment(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Assign) and len(node.targets) == 1

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Assign) and len(node.targets) == 1

        target, error = ast_node_to_our_node(node.targets[0])
        if error is not None:
            return None, error

        assert target is not None
        assert isinstance(target, tree.Expression), f"{target=}"

        value, error = ast_node_to_our_node(node.value)
        if error is not None:
            return None, error

        assert value is not None
        assert isinstance(value, tree.Expression), f"{value=}"

        return (
            tree.Assignment(target=target, value=value, original_node=node),
            None,
        )


class _ParseReturn(_Parse):
    def matches(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Return)

    # noinspection PyTypeChecker
    def transform(self, node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
        assert isinstance(node, ast.Return)

        if node.value is None:
            return tree.Return(value=None, original_node=node), None

        value, error = ast_node_to_our_node(node.value)
        if error is not None:
            return None, error

        assert value is not None
        assert isinstance(value, tree.Expression), f"{value=}"

        return tree.Return(value=value, original_node=node), None


_CHAIN_OF_RULES = [
    _ParseComparison(),
    _ParseIsIn(),
    _ParseAnyOrAll(),
    _ParseCall(),
    _ParseConstant(),
    _ParseTuple(),
    _ParseImplication(),
    _ParseMember(),
    _ParseIndex(),
    _ParseName(),
    _ParseIsNoneOrIsNotNone(),
    _ParseNot(),
    _ParseAndOrOr(),
    _ParseAddOrSub(),
    _ParseExpression(),
    _ParseJoinedStr(),
    _ParseAssignment(),
    _ParseReturn(),
]  # type: Sequence[_Parse]


def _assert_chains_follow_file_structure() -> None:
    """
    Make sure that the chains of command follow the structure of the module.

    This check is necessary so that the rules can be directly followed in the source
    code. Otherwise, it is very hard to follow the chain if it differs from the order
    in which the classes are defined.
    """
    this_file = pathlib.Path(os.path.realpath(__file__))

    # If we are in an environment where we can not load the file, skip this assertion.
    # This is the case, for example, in a pyinstaller package.
    if not this_file.exists():
        return

    root = ast.parse(
        source=this_file.read_text(encoding="utf-8"), filename=str(this_file)
    )
    assert isinstance(root, ast.Module)

    expected_parse_names = [
        stmt.name
        for stmt in root.body
        if (
            isinstance(stmt, ast.ClassDef)
            and stmt.name.startswith("_Parse")
            and stmt.name != "_Parse"
        )
    ]  # type: List[str]

    parse_names_in_chain = [parse.__class__.__name__ for parse in _CHAIN_OF_RULES]

    assert (
        expected_parse_names == parse_names_in_chain
    ), f"{expected_parse_names=} != {parse_names_in_chain=}"


_assert_chains_follow_file_structure()


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def ast_node_to_our_node(node: ast.AST) -> Tuple[Optional[tree.Node], Optional[Error]]:
    """
    Parse the Python AST node into our custom AST.

    For example, this function is used to parse contract conditions into
    our representation which is later easier for processing.
    """
    for parse_rule in _CHAIN_OF_RULES:
        # NOTE(mristin, 2021-10-08):
        # Please leave the variables as they are to facilitate the eventual debugging
        # even though a more succinct code structure lures you.

        matches = parse_rule.matches(node)
        if matches:
            result, error = parse_rule.transform(node)

            if error is not None:
                return None, error

            return result, None

    return None, Error(
        node,
        f"The code matched no pattern for transpilation "
        f"at the parse stage: {ast.dump(node)}",
    )
