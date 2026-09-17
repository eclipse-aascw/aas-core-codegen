"""Translate control flows to linear flows with goto-statements and co-routines."""
import abc
import typing
from typing import (
    Optional,
    Union,
    Sequence,
    List,
    Tuple,
    Set,
    Dict,
    cast,
    overload,
)

from icontract import require, ensure

from aas_core_codegen import common
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    pairwise,
    iterate_except_first,
)
from aas_core_codegen.yielding import flow as yielding_flow


class Statement(abc.ABC):
    """Represent an abstract statement in a co-routine."""

    @require(lambda label: not (label is not None) or label >= 0)
    def __init__(self, label: Optional[int] = None) -> None:
        """Initialize with the given values."""
        self.label = label


class Command(Statement):
    """Represent a command which contains no jumps."""

    def __init__(self, code: Stripped, label: Optional[int] = None) -> None:
        """Initialize with the given values."""
        Statement.__init__(self, label=label)

        self.code = code


class If(Statement):
    """Represent a conditional jump, where we jump based on the condition."""

    def __init__(
        self,
        condition: Stripped,
        on_true: Optional[int] = None,
        on_false: Optional[int] = None,
        label: Optional[int] = None,
    ) -> None:
        """Initialize with the given values."""
        Statement.__init__(self, label=label)

        self.condition = condition
        self.on_true = on_true
        self.on_false = on_false


class Jump(Statement):
    """Represent an unconditional jump in the execution."""

    def __init__(self, target: int, label: Optional[int] = None) -> None:
        """Initialize with the given values."""
        Statement.__init__(self, label=label)

        self.target = target


class Yield(Statement):
    """Represent a yield statement, where the next co-routine should take over."""

    def __init__(self, label: Optional[int] = None) -> None:
        """Initialize with the given values."""
        Statement.__init__(self, label=label)


class Noop(Statement):
    """Represent a no-operation statement, which does nothing."""

    def __init__(
        self, label: Optional[int] = None, comment: Optional[Stripped] = None
    ) -> None:
        """Initialize with the given values."""
        Statement.__init__(self, label=label)
        self.comment = comment


StatementUnion = Union[Command, If, Jump, Yield, Noop]
common.assert_union_of_descendants_exhaustive(
    union=StatementUnion, base_class=Statement
)


def _dump_command_without_label(command: Command) -> str:
    return command.code


def _dump_if_without_label(if_statement: If) -> str:
    indent = "  "
    blocks = []  # type: List[str]
    if "\n" in if_statement.condition:
        blocks.append(
            f"""\
if
{indent}{indent_but_first_line(if_statement.condition, indent)}"""
        )
    else:
        blocks.append(f"if {if_statement.condition}")

    if if_statement.on_true is not None:
        blocks.append(f"is true, jump to {if_statement.on_true}")

    if if_statement.on_false is not None:
        blocks.append(f"is false, jump to {if_statement.on_false}")

    return "\n".join(blocks)


def _dump_jump_without_label(jump: Jump) -> str:
    return f"jump {jump.target}"


def _dump_yield_without_label(yield_statement: Yield) -> str:
    return "yield"


def _dump_noop_without_label(noop_statement: Noop) -> str:
    if noop_statement.comment is not None:
        return f"noop - {noop_statement.comment}"

    return "noop"


_DUMP_WITHOUT_LABEL_DISPATCH = {
    Command: _dump_command_without_label,
    If: _dump_if_without_label,
    Jump: _dump_jump_without_label,
    Yield: _dump_yield_without_label,
    Noop: _dump_noop_without_label,
}
assert all(
    cls in _DUMP_WITHOUT_LABEL_DISPATCH for cls in typing.get_args(StatementUnion)
), "All statements covered in _DUMP_WITHOUT_LABEL_DISPATCH"


def _dump_without_label(statement: StatementUnion) -> str:
    _dump_without_label_func = _DUMP_WITHOUT_LABEL_DISPATCH[statement.__class__]
    result = _dump_without_label_func(statement)  # type: ignore
    assert isinstance(result, str)  # necessary for mypy
    return result


def dump(statements: Sequence[StatementUnion]) -> str:
    """Render the statements to a textual sequence of labeled code."""
    if len(statements) == 0:
        return ""

    max_label = None
    for statement in statements:
        if statement.label is not None:
            if max_label is None:
                max_label = statement.label
            else:
                max_label = statement.label

    if max_label is None:
        label_characters = 0
    else:
        label_characters = len(str(max_label))

    label_format = f"{{:{label_characters}d}}: "
    empty_label = " " * label_characters + ": "
    indent = " " * (label_characters + 2)

    blocks = []  # type: List[str]
    for statement in statements:
        if statement.label is not None:
            label_str = label_format.format(statement.label)
        else:
            label_str = empty_label

        code = _dump_without_label(statement)

        blocks.append(
            f"""\
{label_str}{indent_but_first_line(code, indent)}"""
        )

    return "\n".join(blocks)


def _linearize_command(
    command: yielding_flow.Command, label: int
) -> Tuple[List[StatementUnion], int]:
    """
    Linearize the command with the given label.

    Return the linearization and the next available label.
    """
    return [Command(code=command.code, label=label)], label + 1


def _linearize_if_true(
    if_true_node: yielding_flow.IfTrue, label: int
) -> Tuple[List[StatementUnion], int]:
    """
    Linearize recursively the if-node in the control flow with the given label.

    Return the linearization and the next available label.
    """
    # NOTE (mristin):
    # We will fix this if-statement at the end, once we know the labels for ``on_true``
    # and ``on_false``.
    if_statement = If(condition=if_true_node.condition, label=label)

    result = [if_statement]  # type: List[StatementUnion]
    label += 1

    if if_true_node.or_else is not None:
        body, label = _linearize_sequence(if_true_node.body, label)
        result.extend(body)

        # NOTE (mristin):
        # This jump will be fixed after we know the exact target.
        jump_to_done_after_body = Jump(target=-1, label=label)
        result.append(jump_to_done_after_body)
        label += 1

        on_false = label
        or_else, label = _linearize_sequence(if_true_node.or_else, label)
        result.extend(or_else)

        done_label = label
        result.append(Noop(label=label))
        label += 1

        jump_to_done_after_body.target = done_label

        if_statement.on_false = on_false

    else:
        body, label = _linearize_sequence(if_true_node.body, label)
        if len(body) == 0:
            result.append(Noop(label=label))
        result.extend(body)

        done_label = label
        result.append(Noop(label=label))
        label += 1

        if_statement.on_false = done_label

    return result, label


def _linearize_if_false(
    if_false_node: yielding_flow.IfFalse, label: int
) -> Tuple[List[StatementUnion], int]:
    """
    Linearize recursively the if-node in the control flow with the given label.

    Return the linearization and the next available label.
    """
    # NOTE (mristin):
    # We will fix this if-statement at the end, once we know the labels for ``on_true``
    # and ``on_false``.
    if_statement = If(condition=if_false_node.condition, label=label)

    result = [if_statement]  # type: List[StatementUnion]
    label += 1

    if if_false_node.or_else is not None:
        body, label = _linearize_sequence(if_false_node.body, label)
        result.extend(body)

        # NOTE (mristin):
        # This jump will be fixed after we know the exact target.
        jump_to_done_after_body = Jump(target=-1, label=label)
        result.append(jump_to_done_after_body)
        label += 1

        on_true = label
        or_else, label = _linearize_sequence(if_false_node.or_else, label)
        result.extend(or_else)

        done_label = label
        result.append(Noop(label=label))
        label += 1

        jump_to_done_after_body.target = done_label

        if_statement.on_true = on_true

    else:
        body, label = _linearize_sequence(if_false_node.body, label)
        if len(body) == 0:
            result.append(Noop(label=label))
        result.extend(body)

        done_label = label
        result.append(Noop(label=label))
        label += 1

        if_statement.on_true = done_label

    return result, label


def _linearize_for(
    for_node: yielding_flow.For, label: int
) -> Tuple[List[StatementUnion], int]:
    """
    Linearize recursively the for-node in the control flow with the given label.

    Return the linearization and the next available label.
    """
    result = []  # type: List[StatementUnion]

    if for_node.init is not None:
        result.append(Command(for_node.init, label=label))
        label += 1

    # NOTE (mristin):
    # We will fix this if-statement at the end, once we know the label for ``on_true``.
    if_statement = If(condition=for_node.condition, label=label)

    result.append(if_statement)
    label += 1

    body, label = _linearize_sequence(for_node.body, label=label)
    result.extend(body)

    result.append(Command(for_node.iteration, label=label))
    label += 1

    assert if_statement.label is not None, (
        "The label of the condition If-statement must have been set; otherwise "
        "we do not know where to jump at the end of a loop iteration."
    )
    result.append(Jump(target=if_statement.label, label=label))
    label += 1

    done_label = label
    result.append(Noop(label=done_label))
    label += 1

    if_statement.on_false = done_label

    return result, label


def _linearize_while(
    while_node: yielding_flow.While, label: int
) -> Tuple[List[StatementUnion], int]:
    """
    Linearize the while-node in the control flow with the given label.

    Return the linearization and the next available label.
    """
    result = []  # type: List[StatementUnion]

    # NOTE (mristin):
    # We will fix this if-statement at the end, once we know the label for ``on_true``.
    if_statement = If(condition=while_node.condition, label=label)
    label += 1
    result.append(if_statement)

    body, label = _linearize_sequence(while_node.body, label=label)
    result.extend(body)

    assert if_statement.label is not None, (
        "The label of the condition If-statement must have been set; otherwise "
        "we do not know where to jump at the end of a loop iteration."
    )

    result.append(Jump(target=if_statement.label, label=label))
    label += 1

    done_label = label
    result.append(Noop(label=done_label))
    label += 1

    if_statement.on_false = done_label

    return result, label


def _linearize_yield(
    yield_node: yielding_flow.Yield, label: int
) -> Tuple[List[StatementUnion], int]:
    """
    Linearize the yield node in the control flow with the given label.

    Return the linearization and the next available label.
    """
    return [Yield(label=label)], label + 1


_LINEARIZE_DISPATCH = {
    yielding_flow.Command: _linearize_command,
    yielding_flow.IfTrue: _linearize_if_true,
    yielding_flow.IfFalse: _linearize_if_false,
    yielding_flow.For: _linearize_for,
    yielding_flow.While: _linearize_while,
    yielding_flow.Yield: _linearize_yield,
}
assert all(
    cls in _LINEARIZE_DISPATCH for cls in typing.get_args(yielding_flow.Node)
), "All classes covered in _LINEARIZE_DISPATCH"


def _linearize_node(
    node: yielding_flow.Node, label: int
) -> Tuple[List[StatementUnion], int]:
    """
    Linearize the yield node in the control flow with the given label.

    Return the linearization and the next available label.
    """
    linearize_func = _LINEARIZE_DISPATCH[node.__class__]
    result = linearize_func(node, label)  # type: ignore

    assert isinstance(result, tuple)
    assert isinstance(result[0], list)
    assert isinstance(result[1], int)

    return linearize_func(node, label)  # type: ignore


@ensure(
    lambda sequence, label, result: not (len(sequence) == 0)
    or (len(result[0]) == 0 and label == result[1]),
    "Empty sequence implies no statements and no change in labels",
)
def _linearize_sequence(
    sequence: Sequence[yielding_flow.Node], label: int
) -> Tuple[List[StatementUnion], int]:
    """
    Linearize recursively the control flow sequence, starting with the given label.
    :param sequence:
    :return:
    """
    result = []  # type: List[StatementUnion]
    for node in sequence:
        statements, label = _linearize_node(node, label)
        result.extend(statements)

    return result, label


def _linearize_control_flow(flow: Sequence[yielding_flow.Node]) -> List[StatementUnion]:
    """Compile the control flow into a linearized sequence of statements."""
    statements, _ = _linearize_sequence(flow, label=0)
    return statements


def _collect_targets(statements: Sequence[StatementUnion]) -> Set[int]:
    """Collect all the targets over all the sequences."""
    result = set()  # type: Set[int]
    for statement in statements:
        if isinstance(statement, Jump):
            result.add(statement.target)

        elif isinstance(statement, If):
            if statement.on_true is not None:
                result.add(statement.on_true)

            if statement.on_false is not None:
                result.add(statement.on_false)
        else:
            pass

    return result


def _remove_redundant_labels_in_place(statements: Sequence[StatementUnion]) -> None:
    """Remove labels from statements which are never a target."""
    target_set = _collect_targets(statements)
    for statement in statements:
        if statement.label not in target_set:
            statement.label = None


def _remove_noops_in_place(statements: List[StatementUnion]) -> List[StatementUnion]:
    """
    Remove no-ops and re-wire the targets in-place.

    The input statements list is invalidated, and should not be used after the call
    to this function.
    """
    # NOTE (mristin):
    # We can safely remove all no-ops which do not have a label, since they are
    # not targeted at all.
    statements = [
        statement
        for statement in statements
        if not isinstance(statement, Noop) or statement.label is not None
    ]

    # NOTE (mristin):
    # We will iterate through the statements now, map all the targets to the new
    # labels, and mark the no-ops for removal by unsetting their labels.

    old_to_new_target = dict()  # type: Dict[int, int]
    noop_block = []  # type: List[Noop]

    for statement in statements:
        if isinstance(statement, Noop):
            noop_block.append(statement)
        else:
            if len(noop_block) == 0:
                continue

            # NOTE (mristin):
            # If the statement does not have a label, we arbitrarily assign the label
            # of the first no-op in the block.
            if statement.label is None:
                assert noop_block[0].label is not None, (
                    "The label of the first no-op statement is always expected "
                    "as it starts a block."
                )

                statement.label = noop_block[0].label

            for noop in noop_block:
                assert noop.label is not None, (
                    "We have removed non-labeled no-ops before, "
                    "so all remaining no-ops must have a label."
                )

                assert (
                    statement.label is not None
                ), "The statement must have been set before so that we can map it."

                old_to_new_target[noop.label] = statement.label
                noop.label = None

            noop_block = []

    if len(noop_block) > 1:
        # NOTE (mristin):
        # This is a trailing no-op block. We simply reduce it to one no-op.
        iter_noop_block = iter(noop_block)
        next(iter_noop_block)

        for noop in iter_noop_block:
            assert noop.label is not None, (
                "We have removed non-labeled no-ops before, "
                "so all remaining no-ops must have a label."
            )

            assert noop_block[0].label is not None, (
                "Since all no-op statements must have a label, "
                "the first no-op in the block must have a label as well."
            )

            old_to_new_target[noop.label] = noop_block[0].label
            noop.label = None

    # NOTE (mristin):
    # We marked all no-ops for removal by unsetting their label.
    statements = [
        statement
        for statement in statements
        if not isinstance(statement, Noop) or statement.label is not None
    ]

    # NOTE (mristin):
    # Now we have to re-wire the targets.
    for statement in statements:
        if isinstance(statement, If):
            if statement.on_true is not None and statement.on_true in old_to_new_target:
                statement.on_true = old_to_new_target[statement.on_true]

            if (
                statement.on_false is not None
                and statement.on_false in old_to_new_target
            ):
                statement.on_false = old_to_new_target[statement.on_false]

        elif isinstance(statement, Jump):
            if statement.target in old_to_new_target:
                statement.target = old_to_new_target[statement.target]

        else:
            pass

    return statements


def _compress_in_place(statements: List[StatementUnion]) -> List[StatementUnion]:
    """
    Remove redundant statements and labels.

    The input statements list is invalidated, and should not be used after the call
    to this function.
    """
    _remove_redundant_labels_in_place(statements)
    statements = _remove_noops_in_place(statements)
    return statements


def _fix_labels_in_place(statements: List[StatementUnion]) -> None:
    """
    Go through statements and re-wire the labels so that they are consecutive.

    Moreover, we make sure that there is a label after each yield and at the first
    statement, so that we can split statements in blocks by labels.
    """
    if len(statements) == 0:
        return

    label = (
        max(
            statement.label if statement.label is not None else 0
            for statement in statements
        )
        + 1
    )

    # NOTE (mristin):
    # We simply set the first label to some arbitrary number and fix it later.
    if statements[0].label is None:
        statements[0].label = label
        label += 1

    # NOTE (mristin):
    # We add a label after each yield so that we can split the statements in block,
    # where each block starts with a statement label.
    for previous, current in pairwise(statements):
        if isinstance(previous, Yield) and current.label is None:
            current.label = label
            label += 1

    # NOTE (mristin):
    # Now reset all labels so that they are consecutive.

    label = 0

    old_to_new_label = dict()  # type: Dict[int, int]
    for statement in statements:
        if statement.label is not None:
            old_to_new_label[statement.label] = label
            label += 1

    for statement in statements:
        if statement.label is not None:
            statement.label = old_to_new_label[statement.label]

        if isinstance(statement, If):
            if statement.on_true is not None and statement.on_true in old_to_new_label:
                statement.on_true = old_to_new_label[statement.on_true]

            if (
                statement.on_false is not None
                and statement.on_false in old_to_new_label
            ):
                statement.on_false = old_to_new_label[statement.on_false]

        elif isinstance(statement, Jump):
            if statement.target in old_to_new_label:
                statement.target = old_to_new_label[statement.target]

        else:
            pass


class Subroutine(Sequence[StatementUnion]):
    """Capture a subroutine which can execute between the yields."""

    # fmt: off
    @require(
        lambda statements:
        statements[0].label is not None
        and all(
            statement.label is None
            for statement in iterate_except_first(statements)
        ),
        "Only the first statement should have the label defined, "
        "and the remainder of the statements should not."
    )
    @require(
        lambda statements: len(statements) > 0,
        "Empty subroutines are ill-defined"
    )
    # fmt: on
    def __new__(cls, statements: Sequence[StatementUnion]) -> "Subroutine":
        return cast(Subroutine, statements)

    @overload
    def __getitem__(self, index: int) -> StatementUnion:
        raise NotImplementedError("Only for type annotations")

    @overload
    def __getitem__(self, index: slice) -> "Subroutine":
        raise NotImplementedError("Only for type annotations")

    def __getitem__(
        self, index: Union[int, slice]
    ) -> Union[StatementUnion, "Subroutine"]:
        raise NotImplementedError("Only for type annotations")

    def __len__(self) -> int:
        raise NotImplementedError("Only for type annotations")


def _split_in_subroutines(statements: Sequence[StatementUnion]) -> List[Subroutine]:
    """Split the statements in blocks on each label."""
    result = []  # type: List[Subroutine]

    block = []  # type: List[StatementUnion]
    for statement in statements:
        if statement.label is not None:
            if len(block) > 0:
                result.append(Subroutine(block))

            block = [statement]

        else:
            block.append(statement)

    if len(block) > 0:
        result.append(Subroutine(block))

    return result


# fmt: off
@ensure(
    lambda result:
    all(
        subroutine[0].label + 1 == next_subroutine[0].label
        for subroutine, next_subroutine in pairwise(result)
    ),
    "Subroutine labels are consecutively increasing"
)
# fmt: on
def linearize_to_subroutines(flow: Sequence[yielding_flow.Node]) -> List[Subroutine]:
    """Linearize the control flow and split it in subroutines on each yield."""
    if len(flow) == 0:
        return []

    statements = _linearize_control_flow(flow)
    statements = _compress_in_place(statements)
    _fix_labels_in_place(statements)
    subroutines = _split_in_subroutines(statements)

    return subroutines
