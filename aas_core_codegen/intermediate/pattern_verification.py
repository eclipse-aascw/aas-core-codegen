"""
Understand the verification functions.

The classes
:py:class:`aas_core_codegen.intermediate._types.ImplementationSpecificVerification`
and :py:class:`aas_core_codegen.intermediate._types.PatternVerification` had to be
defined in :py:mod:`aas_core_codegen.intermediate._types` to avoid circular imports.
"""
import collections
import re
from typing import Optional, Tuple, List, MutableMapping, Mapping

from icontract import require, ensure

from aas_core_codegen import parse
from aas_core_codegen.common import Error, Identifier, assert_never
from aas_core_codegen.parse import tree as parse_tree


def _check_support(
    node: parse_tree.Node, argument: Identifier
) -> Optional[List[Error]]:
    """
    Check that we understand the ``node`` in the pattern-matching function.

    The ``argument`` specifies the argument to the verification function, which should
    not be used.
    """
    # NOTE (mristin):
    # This run-time check is necessary as we already burned our fingers with it.
    assert isinstance(node, parse_tree.Node), f"{node=}"

    if isinstance(node, parse_tree.Constant):
        if isinstance(node.value, str):
            return None
        else:
            return [
                Error(
                    node.original_node,
                    f"We did not implement the support for non-string constants "
                    f"in pattern matching: {parse_tree.dump(node)}.\n"
                    f"\n"
                    f"Please notify the developers if you need this.",
                )
            ]

    elif isinstance(node, parse_tree.JoinedStr):
        errors = []  # type: List[Error]

        for value in node.values:
            # noinspection PyTypeChecker
            if isinstance(value, str):
                continue
            elif isinstance(value, parse_tree.FormattedValue):
                underlying_errors = _check_support(node=value.value, argument=argument)
                if underlying_errors is not None:
                    errors.extend(underlying_errors)
            else:
                assert_never(value)

        if len(errors) == 0:
            return None

        return errors

    elif isinstance(node, parse_tree.Name):
        if node.identifier == argument:
            return [
                Error(
                    node.original_node,
                    f"The verification arguments, {argument!r}, is not expected "
                    f"to be accessed neither for reading nor for writing.",
                )
            ]
        else:
            return None

    elif isinstance(node, parse_tree.Assignment):
        if not isinstance(node.target, parse_tree.Name):
            return [
                Error(
                    node.target.original_node,
                    f"We currently support only assignments to simple variables, "
                    f"but got: {parse_tree.dump(node.target)}.\n"
                    f"\n"
                    f"Please notify the developers if you need this.",
                )
            ]

        return _check_support(node=node.value, argument=argument)

    else:
        return [
            Error(
                node.original_node,
                f"We did not implement the support for this construct "
                f"in pattern matching: {parse_tree.dump(node)}.\n"
                f"\n"
                f"Please notify the developers if you need this.",
            )
        ]


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _evaluate(
    expr: parse_tree.Expression, state: Mapping[Identifier, str]
) -> Tuple[Optional[str], Optional[Error]]:
    """Evaluate the expression to a string constant."""
    if isinstance(expr, parse_tree.Constant):
        assert isinstance(expr.value, str)
        return expr.value, None

    elif isinstance(expr, parse_tree.Name):
        value = state.get(expr.identifier, None)
        if value is None:
            return (
                None,
                Error(
                    expr.original_node,
                    f"The value of variable {expr.identifier} has not been assigned "
                    f"before",
                ),
            )

        return value, None

    elif isinstance(expr, parse_tree.JoinedStr):
        parts = []  # type: List[str]
        for joined_str_value in expr.values:
            if isinstance(joined_str_value, str):
                parts.append(joined_str_value)

            elif isinstance(joined_str_value, parse_tree.FormattedValue):

                part, error = _evaluate(joined_str_value.value, state=state)
                if error is not None:
                    return None, error

                assert part is not None
                parts.append(part)
            else:
                assert_never(joined_str_value)

        return "".join(parts), None

    else:
        raise AssertionError(f"Unexpected expression: {parse_tree.dump(expr)}")


# fmt: off
@require(
    lambda parsed:
    parsed.verification,
    "Understand only verification functions"
)
@ensure(
    lambda result:
    not (result[2] is None)
    or (
        (result[0] is not None) ^ (result[1] is not None)
    ),
    "Valid match and cause if no error"
)
@ensure(
    lambda result:
    not (result[2] is not None)
    or (result[0] is None and result[1] is None),
    "No match and cause if error"
)
# fmt: on
def try_to_understand(
    parsed: parse.UnderstoodMethod,
) -> Tuple[Optional[str], Optional[Error], Optional[Error]]:
    """
    Try to understand the given verification function as a pattern matching function.

    :param parsed: Verification function as parsed in the parsing phase
    :return: tuple of (pattern, reason for not matching, error)

    We distinguish between two causes why the method could not be understood. The first
    cause, returned as the middle value in the tuple, indicates why the method could
    not be matched, but this non-matching is actually expected.

    The second error, the last value in the return tuple, is an unexpected error. For
    example, if everything looks like a pattern matching function, but there are flags
    in the call to ``match(...)``.
    """
    # Understand only functions that take a single string argument
    if not (
        len(parsed.arguments) == 1
        and isinstance(parsed.arguments[0].type_annotation, parse.AtomicTypeAnnotation)
        and parsed.arguments[0].type_annotation.identifier == "str"
    ):
        return None, Error(parsed.node, "Expected a single ``str`` argument"), None

    # We need to return something,
    if not (
        parsed.returns is not None
        and isinstance(parsed.returns, parse.AtomicTypeAnnotation)
        and parsed.returns.identifier == "bool"
    ):
        return None, Error(parsed.node, "Expected a ``bool`` return value"), None

    if len(parsed.body) == 0:
        return None, Error(parsed.node, "Unexpected empty body"), None

    if not isinstance(parsed.body[-1], parse_tree.Return):
        return (
            None,
            Error(parsed.body[-1].original_node, "Last statement not a a return"),
            None,
        )

    return_node = parsed.body[-1]
    assert isinstance(return_node, parse_tree.Return)
    # noinspection PyUnresolvedReferences
    if return_node.value is None:
        return (
            None,
            Error(parsed.body[-1].original_node, "Expected to return a value"),
            None,
        )

    # noinspection PyUnresolvedReferences
    if return_node.value is None:
        return (
            None,
            Error(parsed.body[-1].original_node, "Expected to return a value"),
            None,
        )

    if (
        isinstance(return_node.value, parse_tree.FunctionCall)
        and return_node.value.name.identifier == "match"
    ):
        return (
            None,
            None,
            Error(
                return_node.original_node,
                "The ``match`` function returns a re.Match object, "
                "but this function expected the return value to be a boolean. "
                "Did you maybe want to write ``return match(...) is not None``?",
            ),
        )

    if not isinstance(return_node.value, parse_tree.IsNotNone):
        return (
            None,
            Error(
                return_node.value.original_node,
                f"Expected to return a ``match(...) is not None``, "
                f"but got: {parse_tree.dump(return_node.value)}",
            ),
            None,
        )

    if not isinstance(return_node.value.value, parse_tree.FunctionCall):
        return (
            None,
            Error(
                return_node.value.value.original_node,
                f"Expected a function call ``match(...)``, "
                f"but got: {parse_tree.dump(return_node.value.value)}",
            ),
            None,
        )

    if return_node.value.value.name.identifier != "match":
        return (
            None,
            Error(
                return_node.value.value.name.original_node,
                f"Expected a call to the function ``match(...)``, "
                f"but got a call "
                f"to function: {return_node.value.value.name.identifier!r}",
            ),
            None,
        )

    # NOTE (mristin):
    # From here on we return errors. The verification function looks like a pattern
    # matching so if we can not match (no pun intended), we should signal the user that
    # something was unexpected.

    match_call = return_node.value.value
    assert isinstance(match_call, parse_tree.FunctionCall)
    assert match_call.name.identifier == "match"

    if len(match_call.args) < 2:
        return (
            None,
            None,
            Error(
                match_call.original_node,
                f"The ``match`` function expects two arguments "
                f"(pattern and the text to be matched), "
                f"but you provided {len(match_call.args)} argument(s)",
            ),
        )

    if len(match_call.args) > 2:
        return (
            None,
            None,
            Error(
                match_call.original_node,
                "We do not support calls to the ``match`` function with more than "
                "two arguments (pattern and the text to be matched) "
                "since we could not transpile to other languages and schemas "
                "(*e.g.*, flags such as multi-line matching)",
            ),
        )

    # noinspection PyUnresolvedReferences
    if not (
        isinstance(match_call.args[1], parse_tree.Name)
        and match_call.args[1].identifier == parsed.arguments[0].name
    ):
        return (
            None,
            None,
            Error(
                match_call.original_node,
                f"The second argument to ``match`` function, the text to be matched, "
                f"needs to correspond to the single argument of "
                f"the verification function, {parsed.arguments[0].name!r}. "
                f"Otherwise, we can not transpile the pattern to schemas.\n"
                f"\n"
                f"However, we got: {parse_tree.dump(match_call.args[1])}",
            ),
        )

    # noinspection PyUnresolvedReferences
    if (
        isinstance(match_call.args[0], parse_tree.Name)
        and match_call.args[0].identifier == parsed.arguments[0].name
    ):
        return (
            None,
            None,
            Error(
                match_call.original_node,
                f"The first argument, the pattern, to the ``match`` function "
                f"must not be the argument supplied to "
                f"the verification function, {parsed.arguments[0].name!r}.",
            ),
        )

    # region Check the support of the statements

    errors = []  # type: List[Error]
    for i, stmt in enumerate(parsed.body):
        # Skip the return statement
        if i == len(parsed.body) - 1:
            break

        underlying_errors = _check_support(node=stmt, argument=parsed.arguments[0].name)

        if underlying_errors is not None:
            errors.extend(underlying_errors)

    underlying_errors = _check_support(
        node=match_call.args[0], argument=parsed.arguments[0].name
    )

    if underlying_errors is not None:
        errors.extend(underlying_errors)

    if len(errors) > 0:
        return (
            None,
            None,
            Error(
                parsed.node,
                f"We could not understand "
                f"the pattern matching function {parsed.name!r}",
                errors,
            ),
        )

    # endregion

    # region Re-execute the function to infer the pattern

    state = collections.OrderedDict()  # type: MutableMapping[Identifier, str]

    pattern = None  # type: Optional[str]
    for i, stmt in enumerate(parsed.body):
        if i < len(parsed.body) - 1:
            assert isinstance(stmt, parse_tree.Assignment)
            assert isinstance(stmt.target, parse_tree.Name)

            value, error = _evaluate(expr=stmt.value, state=state)
            if error is not None:
                return None, None, error

            assert value is not None

            state[stmt.target.identifier] = value

        else:
            pattern, error = _evaluate(expr=match_call.args[0], state=state)
            if error is not None:
                return None, None, error

            assert pattern is not None

    # endregion

    assert pattern is not None

    try:
        re.compile(pattern)
    except re.error as exception:
        return (
            None,
            None,
            Error(
                match_call.args[0].original_node,
                f"Failed to compile the pattern with the Python's ``re`` module.\n"
                f"\n"
                f"The evaluated pattern was: {pattern!r}.\n"
                f"The error message was: {exception}",
            ),
        )

    return pattern, None, None
