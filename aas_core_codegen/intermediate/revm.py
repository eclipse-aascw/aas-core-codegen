"""
Transpile the regular expressions to instructions of a Virtual Machine.

The implementation in the standard library has exponential time complexity, so it was
a major blocker for most of the practical inputs. For example, see this bug report:
https://gcc.gnu.org/bugzilla/show_bug.cgi?id=93502

The virtual machine is based on Ken Thompson's approach published in:
Thompson, K., "Regular expression search algorithm", ACM 11(6) (June 1968)

We followed a very clear and concise blog post which described it in detail:
https://swtch.com/~rsc/regexp/regexp2.html

The ideas for additional instructions were taken from:
https://www.codeproject.com/Articles/5256833/Regex-as-a-Tiny-Threaded-Virtual-Machine
"""
import itertools
import dataclasses
import io
from typing import (
    Final,
    cast,
    List,
    Optional,
    Union,
    Tuple,
    TextIO,
    MutableMapping,
    Sequence,
)

from icontract import require

from aas_core_codegen.common import assert_never
from aas_core_codegen.parse import retree as parse_retree, tree as parse_tree


class Character(str):
    """Represent a single character."""

    __slots__ = ()

    @require(lambda text: len(text) == 1)
    def __new__(cls, text: str) -> "Character":
        return cast(Character, text)


@dataclasses.dataclass
class InstructionChar:
    """Match a single character."""

    character: Character


class Range:
    """Define a character range."""

    first: Final[Character]
    last: Final[Character]

    # fmt: off
    @require(
        lambda first, last: ord(first) <= ord(last),
        "Range boundaries must be sorted."
    )
    # fmt: on
    def __init__(self, first: Character, last: Character) -> None:
        """Initialize with the given values."""
        self.first = first
        self.last = last

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.first!r}, {self.last!r})"


def check_ranges_sorted_and_non_overlapping(ranges: Sequence[Range]) -> Optional[str]:
    """
    Check that the ranges' boundaries are sorted and non-overlapping.

    If there are no errors, return ``None``. Otherwise, return a message explaining
    what precisely was not satisfied.
    """
    for this_range, next_range in itertools.pairwise(ranges):
        if ord(this_range.first) >= ord(next_range.last):
            return (
                f"The range {this_range} and its next range {next_range} "
                f"are not in sorted order."
            )

        if ord(this_range.last) >= ord(next_range.first):
            return f"The range {this_range} and its next range {next_range} overlap."

    return None


class InstructionSet:
    """Match a set of characters."""

    ranges: Final[Sequence[Range]]

    @require(lambda ranges: check_ranges_sorted_and_non_overlapping(ranges) is None)
    def __init__(self, ranges: Sequence[Range]) -> None:
        """Initialize with the given values."""
        self.ranges = ranges

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.ranges!r})"


class InstructionNotSet:
    """Match an out-of-set character."""

    ranges: Final[Sequence[Range]]

    @require(lambda ranges: check_ranges_sorted_and_non_overlapping(ranges) is None)
    def __init__(self, ranges: Sequence[Range]) -> None:
        """Initialize with the given values."""
        self.ranges = ranges

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.ranges!r})"


@dataclasses.dataclass
class InstructionAny:
    """Match any character."""


@dataclasses.dataclass
class InstructionMatch:
    """Stop the thread and signal that we found a match."""


@dataclasses.dataclass
class InstructionJump:
    """Jump to the indicated position in the program."""

    target: int


@dataclasses.dataclass
class InstructionSplit:
    """Split the program in two threads, both jumping to different locations."""

    first_target: int
    second_target: int


@dataclasses.dataclass
class InstructionEnd:
    """Match the end-of-input."""


@dataclasses.dataclass
class _InstructionNoop:
    """
    Represent a no-operation instruction which does nothing.

    This is used only as a place-holder during the translation.
    """


Instruction = Union[
    InstructionChar,
    InstructionSet,
    InstructionNotSet,
    InstructionAny,
    InstructionMatch,
    InstructionJump,
    InstructionSplit,
    InstructionEnd,
]


# NOTE (mristin):
# The classes ``_Leaf`` and ``_Node`` correspond to the translation phase, while
# the classes ``Leaf`` and ``Node`` are used to represent the final result.


@dataclasses.dataclass
class _Leaf:
    """Represent a leaf node in the nested instruction tree during compilation."""

    instruction: Union[Instruction, _InstructionNoop]
    label: Optional[int] = None


@dataclasses.dataclass
class _Node:
    """Represent nested instructions during compilation."""

    re_node: parse_retree.Node
    children: List["_NodeOrLeaf"]


_NodeOrLeaf = Union[_Node, _Leaf]


@dataclasses.dataclass
class Leaf:
    """Represent a leaf node in the nested instruction tree."""

    instruction: Instruction
    label: Optional[int] = None


@dataclasses.dataclass
class Node:
    """Represent nested instructions related to a part of the regular expression."""

    re_node: parse_retree.Node
    children: List["NodeOrLeaf"]


NodeOrLeaf = Union[Node, Leaf]


class _CheckForFormattedValue(parse_retree.PassThroughVisitor):
    """Check that no ``FormattedValue`` is contained in a pattern."""

    def __init__(self) -> None:
        self.has_formatted_value = False

    def visit_term(self, node: parse_retree.Term) -> None:
        if isinstance(node.value, parse_tree.FormattedValue):
            self.has_formatted_value = True

        super().visit_term(node)


class _CheckForNonGreedyQuantifiers(parse_retree.PassThroughVisitor):
    """Check for presence of non-greedy quantifiers in a pattern."""

    def __init__(self) -> None:
        self.has_non_greedy_quantifiers = False

    def visit_quantifier(self, node: parse_retree.Quantifier) -> None:
        if node.non_greedy:
            self.has_non_greedy_quantifiers = True

        super().visit_quantifier(node)


class _RegexRenderer(parse_retree.Renderer):
    """
    Render regex patterns for readable comments.

    In contrast to :py:class:`parse_retree.Renderer`, we also render
    the :py:class:`parse_retree.Char` as we need to cover the granularity of a single
    character in this module.
    """

    def transform_char(
        self, node: parse_retree.Char
    ) -> List[Union[str, parse_tree.FormattedValue]]:
        return self.char_to_str_and_escape_or_encode_if_necessary(
            node=node, escaping=parse_retree.Renderer._ESCAPING_IN_CHARACTER_LITERALS
        )


_REGEX_RENDERER = _RegexRenderer()


def _render_re_node(re_node: parse_retree.Node) -> str:
    """Render the pattern as a string for comments."""
    parts = _REGEX_RENDERER.transform(re_node)
    assert all(
        isinstance(part, str) for part in parts
    ), f"Expected all rendered parts to be strings, but got: {parts}"

    return "".join(parts)  # type: ignore


class _Translator(parse_retree.Transformer[_Node]):
    """Translate the regular expression to nested instructions."""

    def __init__(self) -> None:
        self._next_label = 0

    def _obtain_label(self) -> int:
        """
        Return the current next label, and increment it for the next call.

        Do not fiddle with :py:attr:`_next_label` yourself; use this function.
        """
        result = self._next_label
        self._next_label += 1
        return result

    def transform_union_expr(self, node: parse_retree.UnionExpr) -> _Node:
        if len(node.uniates) == 0:
            return _Node(re_node=node, children=[_Leaf(instruction=_InstructionNoop())])
        elif len(node.uniates) == 1:
            return self.transform(node.uniates[0])
        else:
            pass

        children: List[_NodeOrLeaf] = []

        final_label = self._obtain_label()

        for i, uniate in enumerate(node.uniates):
            if i < len(node.uniates) - 1:
                l0 = self._obtain_label()
                l1 = self._obtain_label()

                children.append(
                    _Leaf(InstructionSplit(first_target=l0, second_target=l1))
                )

                children.append(_Leaf(_InstructionNoop(), label=l0))

                children.append(self.transform(uniate))

                children.append(_Leaf(InstructionJump(target=final_label)))

                children.append(_Leaf(_InstructionNoop(), label=l1))
            else:
                children.append(self.transform(uniate))

                children.append(_Leaf(_InstructionNoop(), label=final_label))

        return _Node(re_node=node, children=children)

    def transform_concatenation(self, node: parse_retree.Concatenation) -> _Node:
        if len(node.concatenants) == 0:
            return _Node(re_node=node, children=[_Leaf(instruction=_InstructionNoop())])

        elif len(node.concatenants) == 1:
            return self.transform(node=node.concatenants[0])

        else:
            return _Node(
                re_node=node,
                children=[
                    self.transform(concatenant) for concatenant in node.concatenants
                ],
            )

    def transform_symbol(self, node: parse_retree.Symbol) -> _Node:
        if node.kind is parse_retree.SymbolKind.START:
            raise AssertionError(
                "We expect that the caller skipped the start anchor "
                "as we always expect the patterns to be anchored at start, and there "
                "is no matching to be done against the start anchor. We decided "
                "against introduction of a no-op instruction since that only eats up "
                "resources, which we can avoid with a bit of smartness in "
                "the transpilation phase."
            )

        elif node.kind is parse_retree.SymbolKind.END:
            return _Node(re_node=node, children=[_Leaf(instruction=InstructionEnd())])

        elif node.kind is parse_retree.SymbolKind.DOT:
            return _Node(
                re_node=node,
                children=[_Leaf(instruction=InstructionAny())],
            )

        else:
            assert_never(node.kind)

    def transform_term(self, node: parse_retree.Term) -> _Node:
        assert not isinstance(node.value, parse_tree.FormattedValue), (
            "Unexpected formatted value in the regular expression to be "
            "transformed into a program for Regex Virtual Machine. "
            "This should have been checked before. "
            f"The formatted value is: {parse_tree.dump(node.value)}"
        )

        if node.quantifier is not None:
            if node.quantifier.non_greedy:
                raise AssertionError(
                    "(mristin) Only non-greedy quantifiers are currently "
                    "translated to a program for a RegEx virtual machine. We did not "
                    "cover non-greedy quantifiers for simplicity, as we currently have "
                    "no meta-model where they are required. The presence of non-greedy "
                    "quantifiers should have been caught before, as we explicitly "
                    "check for them when transpiling a meta-model. Please report "
                    "this exception to the developers as a bug."
                )

            if node.quantifier.minimum == 1 and node.quantifier.maximum == 1:
                return self.transform(node.value)

            children: List[_NodeOrLeaf] = []

            if node.quantifier.maximum is not None:
                for _ in range(node.quantifier.minimum):
                    children.append(self.transform(node.value))

                optional_count = node.quantifier.maximum - node.quantifier.minimum
                if optional_count > 0:
                    final_label = self._obtain_label()

                    for _ in range(optional_count):
                        l1 = self._obtain_label()
                        children.append(
                            _Leaf(
                                InstructionSplit(
                                    first_target=l1, second_target=final_label
                                )
                            )
                        )
                        children.append(_Leaf(_InstructionNoop(), label=l1))
                        children.append(self.transform(node.value))

                    children.append(_Leaf(_InstructionNoop(), label=final_label))
            else:
                if node.quantifier.minimum == 0:
                    l1 = self._obtain_label()
                    l2 = self._obtain_label()
                    final_label = self._obtain_label()

                    children.append(
                        _Leaf(
                            InstructionSplit(
                                first_target=l2, second_target=final_label
                            ),
                            label=l1,
                        )
                    )

                    children.append(_Leaf(_InstructionNoop(), label=l2))
                    children.append(self.transform(node.value))
                    children.append(_Leaf(InstructionJump(target=l1)))

                    children.append(_Leaf(_InstructionNoop(), label=final_label))

                else:
                    # NOTE (mristin):
                    # The last mandatory repetition will be used for the unbounded loop.
                    for _ in range(node.quantifier.minimum - 1):
                        children.append(self.transform(node.value))

                    l1 = self._obtain_label()
                    final_label = self._obtain_label()

                    children.append(_Leaf(_InstructionNoop(), label=l1))
                    children.append(self.transform(node.value))
                    children.append(
                        _Leaf(
                            InstructionSplit(first_target=l1, second_target=final_label)
                        )
                    )
                    children.append(_Leaf(_InstructionNoop(), label=final_label))

            return _Node(re_node=node, children=children)

        else:
            return self.transform(node.value)

    def transform_group(self, node: parse_retree.Group) -> _Node:
        return self.transform(node.union)

    def transform_char(self, node: parse_retree.Char) -> _Node:
        return _Node(
            re_node=node,
            children=[
                _Leaf(instruction=InstructionChar(character=Character(node.character)))
            ],
        )

    def transform_quantifier(self, node: parse_retree.Quantifier) -> _Node:
        raise AssertionError(
            f"Expected the quantifier to be already handled "
            f"in {_Translator.transform_term.__name__}. We should have never gotten "
            f"here."
        )

    def transform_char_set(self, node: parse_retree.CharSet) -> _Node:
        ranges = [
            Range(
                first=Character(re_range.start.character),
                last=(
                    Character(re_range.end.character)
                    if re_range.end is not None
                    else Character(re_range.start.character)
                ),
            )
            for re_range in node.ranges
        ]

        ranges.sort(key=lambda rng: rng.first)

        if node.complementing:
            return _Node(
                re_node=node,
                children=[_Leaf(instruction=InstructionNotSet(ranges=ranges))],
            )
        else:
            return _Node(
                re_node=node,
                children=[_Leaf(instruction=InstructionSet(ranges=ranges))],
            )

    def transform_range(self, node: parse_retree.Range) -> _Node:
        raise AssertionError(
            "Expected to handle a regex range within the character set"
        )

    def transform_regex(self, node: parse_retree.Regex) -> _Node:
        non_anchored_exception_message = (
            "(mristin): We expect all the patterns which need "
            "to be transpiled to instructions of the RegEx virtual machine "
            "to be anchored at the start (``^``) and at the end (``$``). Please "
            "consider re-writing your pattern with putting a prefix ``^.*`` if you "
            "want to match an arbitrary prefix, and a suffix ``.*$`` if you want to "
            "match an arbitrary suffix. "
            "If you really need this feature, please contact the developers. "
            f"The regular expression was: {_render_re_node(node)}"
        )

        if len(node.union.uniates) == 0 or len(node.union.uniates[0].concatenants) == 0:
            raise NotImplementedError(non_anchored_exception_message)

        first_term = node.union.uniates[0].concatenants[0]
        last_term = node.union.uniates[0].concatenants[-1]

        first_symbol_is_start = isinstance(first_term.value, parse_retree.Symbol) and (
            first_term.value.kind is parse_retree.SymbolKind.START
        )
        last_symbol_is_end = isinstance(last_term.value, parse_retree.Symbol) and (
            last_term.value.kind is parse_retree.SymbolKind.END
        )

        if (
            len(node.union.uniates) != 1
            or not first_symbol_is_start
            or not last_symbol_is_end
        ):
            parts = [non_anchored_exception_message]
            if len(node.union.uniates) > 1:
                parts.append(
                    "Expected no alternation in the root group of "
                    "the pattern (only concatenation), but the pattern starts "
                    "with an alternation. You can not properly anchor "
                    "with an alternation."
                )

            if not first_symbol_is_start:
                parts.append(
                    f"Expected the first term of the pattern to be a start anchor, "
                    f"but it is not. Got: {_render_re_node(first_term)}"
                )

            if not last_symbol_is_end:
                parts.append(
                    f"Expected the last term of the pattern to be an end anchor, "
                    f"but it is not. Got: {_render_re_node(last_term)}"
                )

            raise NotImplementedError("\n\n".join(parts))

        check_for_formatted_value = _CheckForFormattedValue()
        check_for_formatted_value.visit(node)
        if check_for_formatted_value.has_formatted_value:
            raise AssertionError(
                f"The regex you want to transpile to the instructions of "
                f"a RegEx virtual machine contains a formatted value. "
                f"The formatted values can only be transpiled into code, "
                f"but can not be transpiled into instructions. "
                f"Please check your code logic. "
                f"The pattern was: {parse_retree.dump(node)}"
            )

        check_for_non_greedy_quantifiers = _CheckForNonGreedyQuantifiers()
        check_for_non_greedy_quantifiers.visit(node)
        if check_for_non_greedy_quantifiers.has_non_greedy_quantifiers:
            raise NotImplementedError(
                "(mristin): We did not implement the transpilation of "
                "non-greedy quantifiers to instructions of a RegEx virtual machine "
                "as this is more complex than the transpilation of the greedy ones. "
                "If you need this feature, please contact the developers."
            )

        assert len(node.union.uniates) == 1, (
            "Only concatenation expected at the root level since we must anchor "
            "at the start and at the end."
        )

        # region Optimize for arbitrary suffix

        # NOTE (mristin):
        # We optimize here for the pattern ``.*$`` as we can put an instruction ``Match``
        # just before the arbitrary suffix, and need not the match ``Any`` followed by
        # the ``End``.
        penultimate_term = (
            node.union.uniates[0].concatenants[-2]
            if len(node.union.uniates[0].concatenants) >= 2
            else None
        )

        assert (
            node.union.uniates[0].concatenants[0] is first_term
            and isinstance(first_term.value, parse_retree.Symbol)
            and first_term.value.kind is parse_retree.SymbolKind.START
        ), "Expected the first term to be an anchor at ``^``"

        assert (
            last_term is node.union.uniates[0].concatenants[-1]
            and isinstance(last_term.value, parse_retree.Symbol)
            and (last_term.value.kind is parse_retree.SymbolKind.END)
        ), "Expected the last term to be an anchor at ``$``"

        if (
            penultimate_term is not None
            and isinstance(penultimate_term.value, parse_retree.Symbol)
            and penultimate_term.value.kind is parse_retree.SymbolKind.DOT
            and penultimate_term.quantifier is not None
            and penultimate_term.quantifier.minimum == 0
            and penultimate_term.quantifier.maximum is None
        ):
            # NOTE (mristin):
            # We skip the start anchor as it is not transpiled to an instruction.
            concatenants = node.union.uniates[0].concatenants[1:-2]
        else:
            # NOTE (mristin):
            # We skip the start anchor as it is not transpiled to an instruction.
            concatenants = node.union.uniates[0].concatenants[1:]

        # endregion

        children: List[_NodeOrLeaf] = []
        for concatenant in concatenants:
            child = self.transform(concatenant)
            children.append(child)

        children.append(_Leaf(instruction=InstructionMatch()))

        return _Node(
            re_node=node,
            children=children,
        )


def _recursively_convert_node_for_public(raw_node_or_leaf: _NodeOrLeaf) -> NodeOrLeaf:
    """
    Convert the post-processed "raw" node into a node for the public use.

    .. note::

        All post-processing needs to be performed *before* calling this function.
        This function only copy-converts the nodes into structures to be further
        used by the downstream clients. No post-processing is performed here.
    """
    if isinstance(raw_node_or_leaf, _Leaf):
        assert not isinstance(
            raw_node_or_leaf.instruction, _InstructionNoop
        ), "No no-op instructions expected in public"

        return Leaf(
            instruction=raw_node_or_leaf.instruction, label=raw_node_or_leaf.label
        )

    elif isinstance(raw_node_or_leaf, _Node):
        children: List[NodeOrLeaf] = []
        for raw_child in raw_node_or_leaf.children:
            children.append(_recursively_convert_node_for_public(raw_child))

        return Node(re_node=raw_node_or_leaf.re_node, children=children)

    else:
        assert_never(raw_node_or_leaf)


def _linearize(node: _Node) -> List[_Leaf]:
    """Make recursively a linear list over all the leaves."""
    lst: List[_Leaf] = []
    for child in node.children:
        if isinstance(child, _Leaf):
            lst.append(child)
        elif isinstance(child, _Node):
            lst.extend(_linearize(child))
        else:
            assert_never(child)

    return lst


def _relabel_in_place(root: _Node) -> None:
    """
    Re-assign labels according to the indices in a linearized sequence of instructions.

    We expect that the no-op instructions will be removed, so they are not assigned
    an index.
    """
    linearized_leaves = _linearize(root)

    # NOTE (mristin):
    # We index all the leaves except for no-op instructions which are going to be
    # eventually removed. The indices thus correspond to the instructions *after*
    # the no-op instructions are removed.

    next_index = 0

    # NOTE (mristin):
    # We map on the ``id(leaf)`` as the leaves are not hashable.
    leaf_to_index: MutableMapping[int, int] = dict()

    for leaf in linearized_leaves:
        if isinstance(leaf.instruction, _InstructionNoop):
            continue

        leaf_to_index[id(leaf)] = next_index
        next_index += 1

    # NOTE (mristin):
    # This variable captures the mapping:
    # arbitrary labelling 🠒 labeling according to indices.
    #
    # Only the leaves indicated by new labels will finally have a label at the end.
    old_to_new_label: MutableMapping[int, int] = dict()

    # NOTE (mristin):
    # We iterate in reverse over the leaves so that a single non-no-op instruction
    # can accumulate multiple labels for itself.

    leaf_after_noop: Optional[_Leaf] = None
    for leaf in reversed(linearized_leaves):
        if isinstance(leaf.instruction, _InstructionNoop):
            if leaf.label is not None:
                assert leaf_after_noop is not None, (
                    "Expected at least one leaf *after* the no-op instruction. "
                    "Since the very last instruction must be a ``match`` instruction, "
                    "this must hold, so something obviously went wrong."
                )

                old_to_new_label[leaf.label] = leaf_to_index[id(leaf_after_noop)]
        else:
            if leaf.label is not None:
                old_to_new_label[leaf.label] = leaf_to_index[id(leaf)]

            leaf_after_noop = leaf

    new_label_set = set(old_to_new_label.values())

    for leaf in linearized_leaves:
        if isinstance(leaf.instruction, _InstructionNoop):
            leaf.label = None
            continue

        leaf_index = leaf_to_index[id(leaf)]

        if leaf_index in new_label_set:
            leaf.label = leaf_index
        else:
            leaf.label = None

        if isinstance(leaf.instruction, InstructionJump):
            leaf.instruction.target = old_to_new_label[leaf.instruction.target]

        elif isinstance(leaf.instruction, InstructionSplit):
            leaf.instruction.first_target = old_to_new_label[
                leaf.instruction.first_target
            ]

            leaf.instruction.second_target = old_to_new_label[
                leaf.instruction.second_target
            ]
        else:
            # NOTE (mristin):
            # Other instruction need not be adapted to the new labels.
            pass


def _remove_noop_in_place(node: _Node) -> None:
    """
    Remove recursively all no-op instructions in place.

    The no-op instructions are expected to have no labels attached to them.
    """
    new_children: List[_NodeOrLeaf] = []
    for child in node.children:
        if isinstance(child, _Leaf):
            if isinstance(child.instruction, _InstructionNoop):
                assert child.label is None, (
                    f"Expected all no-op leaves to have their labels removed "
                    f"before calling {_remove_noop_in_place.__name__}"
                )
                continue

        elif isinstance(child, _Node):
            _remove_noop_in_place(child)

        else:
            assert_never(child)

        new_children.append(child)

    node.children = new_children


def translate(regex: parse_retree.Regex) -> Node:
    """Translate the regular expression into a program."""
    # NOTE (mristin):
    # We call the nodes "raw" here which still need to be post-processed.
    # The post-processing includes removal of no-ops, re-wiring of the labels *etc.*

    translator = _Translator()
    raw_root = translator.transform(regex)

    _relabel_in_place(raw_root)
    _remove_noop_in_place(raw_root)

    root = _recursively_convert_node_for_public(raw_node_or_leaf=raw_root)
    assert isinstance(root, Node), (
        f"Only node and no leaf expected at the root of the regular expression, "
        f"but got as root: {root}"
    )

    return root


def _determine_min_and_max_label(node_or_leaf: NodeOrLeaf) -> Optional[Tuple[int, int]]:
    """
    Iterate recursively over the nodes, and determine the extreme labels in the program.

    If no node contains a label, return ``None``.
    """
    if isinstance(node_or_leaf, Leaf):
        if node_or_leaf.label is not None:
            return node_or_leaf.label, node_or_leaf.label
        else:
            return None

    elif isinstance(node_or_leaf, Node):
        minimum: Optional[int] = None
        maximum: Optional[int] = None

        for child in node_or_leaf.children:
            maybe_child_min_max = _determine_min_and_max_label(node_or_leaf=child)
            if maybe_child_min_max is not None:
                child_min, child_max = maybe_child_min_max

                if minimum is not None:
                    minimum = min(minimum, child_min)
                else:
                    minimum = child_min

                if maximum is not None:
                    maximum = max(maximum, child_max)
                else:
                    maximum = child_max

        assert (minimum is not None and maximum is not None) or (
            minimum is None and maximum is None
        ), (
            f"Both minimum and maximum must be set or neither, "
            f"but got: {minimum=}, {maximum=}"
        )

        if minimum is not None:
            assert maximum is not None
            return minimum, maximum
        else:
            assert maximum is None
            return None
    else:
        assert_never(node_or_leaf)


@require(lambda indention: indention >= 0)
@require(lambda label_columns: label_columns >= 0)
def _write_recursively(
    node_or_leaf: NodeOrLeaf, indention: int, label_columns: int, writer: TextIO
) -> None:
    """Write recursively the node or leaf as a human-readable text to the ``writer``."""
    whitespace = "  " * indention

    if isinstance(node_or_leaf, Leaf):
        if label_columns == 0:
            label_prefix = ""
        else:
            if node_or_leaf.label is None:
                label_prefix = " " * (label_columns + 2)
            else:
                # noinspection PyStringFormat
                label_prefix = f"{{:0{label_columns}d}}: ".format(node_or_leaf.label)

        instruction_str: str

        if isinstance(node_or_leaf.instruction, InstructionChar):
            instruction_str = f"char {node_or_leaf.instruction.character!r}"

        elif isinstance(node_or_leaf.instruction, (InstructionSet, InstructionNotSet)):
            ranges_str = "".join(
                f"{rng.first}" if rng.first == rng.last else f"{rng.first}-{rng.last}"
                for rng in node_or_leaf.instruction.ranges
            )

            if isinstance(node_or_leaf.instruction, InstructionSet):
                instruction_str = f"set {ranges_str!r}"
            elif isinstance(node_or_leaf.instruction, InstructionNotSet):
                instruction_str = f"not-set {ranges_str!r}"
            else:
                assert_never(node_or_leaf.instruction)

        elif isinstance(node_or_leaf.instruction, InstructionAny):
            instruction_str = "any"

        elif isinstance(node_or_leaf.instruction, InstructionMatch):
            instruction_str = "match"

        elif isinstance(node_or_leaf.instruction, InstructionJump):
            instruction_str = f"jump {node_or_leaf.instruction.target}"

        elif isinstance(node_or_leaf.instruction, InstructionSplit):
            instruction_str = (
                f"split {node_or_leaf.instruction.first_target}, "
                f"{node_or_leaf.instruction.second_target}"
            )

        elif isinstance(node_or_leaf.instruction, InstructionEnd):
            instruction_str = "end"

        else:
            assert_never(node_or_leaf.instruction)

        writer.write(f"{label_prefix}{whitespace}{instruction_str}")

    elif isinstance(node_or_leaf, Node):
        if label_columns == 0:
            label_prefix = ""
        else:
            label_prefix = " " * (label_columns + 2)

        re_node_str = _render_re_node(node_or_leaf.re_node)
        if len(node_or_leaf.children) == 0:
            more_whitespace = "  " * (indention + 1)
            writer.write(
                f"{label_prefix}{whitespace}# {re_node_str}\n"
                f"{label_prefix}{whitespace}{{\n"
                f"{label_prefix}{more_whitespace}# Nothing\n"
                f"{label_prefix}{whitespace}}}"
            )
        elif len(node_or_leaf.children) == 1 and isinstance(
            node_or_leaf.children[0], Leaf
        ):
            if not isinstance(
                node_or_leaf.children[0].instruction,
                (InstructionSet, InstructionNotSet, InstructionAny, InstructionChar),
            ):
                writer.write(f"{label_prefix}{whitespace}# {re_node_str}\n")

            _write_recursively(
                node_or_leaf=node_or_leaf.children[0],
                indention=indention,
                label_columns=label_columns,
                writer=writer,
            )
        else:
            writer.write(
                f"{label_prefix}{whitespace}# {re_node_str}\n"
                f"{label_prefix}{whitespace}{{\n"
            )
            for child in node_or_leaf.children:
                _write_recursively(
                    node_or_leaf=child,
                    indention=indention + 1,
                    label_columns=label_columns,
                    writer=writer,
                )

                writer.write("\n")

            writer.write(f"{label_prefix}{whitespace}}}")

    else:
        assert_never(node_or_leaf)


def dump(program: NodeOrLeaf) -> str:
    """Write out the program as a readable nested list of instructions."""
    maybe_min_max_label = _determine_min_and_max_label(node_or_leaf=program)

    if maybe_min_max_label is None:
        label_columns = 0
    else:
        min_label, max_label = maybe_min_max_label
        label_columns = max(len(str(min_label)), len(str(max_label)))

    writer = io.StringIO()
    _write_recursively(
        node_or_leaf=program, indention=0, label_columns=label_columns, writer=writer
    )

    return writer.getvalue()
