"""Provide a string representation of the regular expressions."""
from typing import Union, Optional

from aas_core_codegen import stringify
from aas_core_codegen.parse.retree import _types
from aas_core_codegen.parse.retree._types import (
    Char,
    Range,
    Concatenation,
    Symbol,
    Group,
    CharSet,
    Quantifier,
    Term,
    UnionExpr,
    Regex,
)
from aas_core_codegen.parse.tree import FormattedValue


def _stringify_char(that: Char) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("character", that.character),
            stringify.Property("explicitly_encoded", that.explicitly_encoded),
        ],
    )

    return result


def _stringify_range(that: Range) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("start", _stringify(that.start)),
            stringify.Property("end", _stringify(that.end)),
        ],
    )

    return result


def _stringify_concatenation(that: Concatenation) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("concatenants", list(map(_stringify, that.concatenants)))
        ],
    )

    return result


def _stringify_group(that: Group) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("union", _stringify(that.union)),
        ],
    )

    return result


def _stringify_char_set(that: CharSet) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("complementing", that.complementing),
            stringify.Property("ranges", list(map(_stringify, that.ranges))),
        ],
    )

    return result


def _stringify_quantifier(that: Quantifier) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("non_greedy", that.non_greedy),
            stringify.Property("minimum", that.minimum),
            stringify.Property("maximum", that.maximum),
        ],
    )

    return result


def _stringify_symbol(that: Symbol) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("kind", that.kind.value),
        ],
    )

    return result


def _stringify_term(that: Term) -> stringify.Entity:
    if isinstance(that.value, FormattedValue):
        stringified_value: Union[str, stringify.Entity, None] = "<formatted value>"
    else:
        stringified_value = _stringify(that.value)

    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("value", stringified_value),
            stringify.Property("quantifier", _stringify(that.quantifier)),
        ],
    )

    return result


def _stringify_union_expr(that: UnionExpr) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("uniates", list(map(_stringify, that.uniates))),
        ],
    )

    return result


def _stringify_regex(that: Regex) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("union", _stringify(that.union)),
        ],
    )

    return result


Dumpable = Union[
    Char,
    Range,
    Concatenation,
    Group,
    CharSet,
    Quantifier,
    Symbol,
    Term,
    UnionExpr,
    Regex,
]

stringify.assert_all_public_types_listed_as_dumpables(
    dumpable=Dumpable, types_module=_types
)

_DISPATCH = {
    Char: _stringify_char,
    Range: _stringify_range,
    Concatenation: _stringify_concatenation,
    Group: _stringify_group,
    CharSet: _stringify_char_set,
    Quantifier: _stringify_quantifier,
    Symbol: _stringify_symbol,
    Term: _stringify_term,
    UnionExpr: _stringify_union_expr,
    Regex: _stringify_regex,
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
