"""Generate code of common functionality."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.golang import (
    common as golang_common,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


def _generate_tuple_struct(arity: int) -> Stripped:
    """Generate the generic struct representing a tuple of the given ``arity``."""
    type_params = ", ".join(f"T{i + 1} any" for i in range(arity))
    fields = "\n".join(f"Item{i + 1} T{i + 1}" for i in range(arity))

    name = f"Tuple{arity}"

    return Stripped(
        f"""\
// Represent a fixed-size heterogeneous tuple of {arity} item(s).
type {name}[{type_params}] struct {{
{I}{indent_but_first_line(fields, I)}
}}"""
    )


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code of common functionality."""
    blocks = [
        Stripped(
            """\
// Package common provides common functions shared among the other packages.
package common"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"strings"
)"""
        ),
        Stripped(
            f"""\
func Concat(
{I}parts ...string,
) string {{
{I}b := new(strings.Builder)
{I}for _, part := range parts {{
{II}b.WriteString(part)
{I}}}
{I}return b.String()
}}"""
        ),
        Stripped(
            f"""\
// Check if the map contains the given key.
func MapContains[K comparable, V any](m map[K]V, k K) bool {{
{I}_, ok := m[k]
{I}return ok
}}"""
        ),
        Stripped(
            f"""\
// Check if any of the elements satisfy the condition.
func Some[V any](condition func(V) bool, l []V) bool {{
{I}ok := false
{I}for _, v := range l {{
{II}ok = ok || condition(v)
{I}}}
{I}return ok
}}"""
        ),
        Stripped(
            f"""\
// Check if all the elements satisfy the condition.
func All[V any](condition func(V) bool, l []V) bool {{
{I}for _, v := range l {{
{II}if !condition(v) {{
{III}return false
{II}}}
{I}}}
{I}return true
}}"""
        ),
        Stripped(
            f"""\
// Check if some of the elements in the given range satisfy the condition.
func SomeRange(condition func(int) bool, start int, end int) bool {{
{I}for i := start; i < end; i++ {{
{II}if condition(i) {{
{III}return true
{II}}}
{I}}}
{I}return false
}}"""
        ),
        Stripped(
            f"""\
// Check if all the elements in the given range satisfy the condition.
func AllRange(condition func(int) bool, start int, end int) bool {{
{I}for i := start; i < end; i++ {{
{II}if !condition(i) {{
{III}return false
{II}}}
{I}}}
{I}return true
}}"""
        ),
        Stripped(
            f"""\
// Create a new instance of the `value` and return the pointer to it.
func NewBool(value bool) *bool {{
{I}return &value
}}"""
        ),
        Stripped(
            f"""\
// Create a new instance of the `value` and return the pointer to it.
func NewInt(value int) *int {{
{I}return &value
}}"""
        ),
        Stripped(
            f"""\
// Create a new instance of the `value` and return the pointer to it.
func NewInt64(value int64) *int64 {{
{I}return &value
}}"""
        ),
        Stripped(
            f"""\
// Create a new instance of the `value` and return the pointer to it.
func NewFloat64(value float64) *float64 {{
{I}return &value
}}"""
        ),
        Stripped(
            f"""\
// Create a new instance of the `value` and return the pointer to it.
func NewString(value string) *string {{
{I}return &value
}}"""
        ),
    ]  # type: List[Stripped]

    blocks.extend(
        _generate_tuple_struct(arity=arity)
        for arity in range(1, golang_common.MAX_TUPLE_ARITY + 1)
    )

    # NOTE (mristin):
    # The native slicing panics on the positions out of range, does not count
    # the negative ones from the end, and ``strings.Index`` has no start. We need
    # helpers which follow the Python implementation of slicing and
    # ``str.find``. The helpers are generated only for a meta-model which slices
    # strings or calls ``find`` on them.
    if intermediate.uses_string_slicing_or_find(symbol_table):
        blocks.extend(
            [
                Stripped(
                    f"""\
// Resolve `position` in a string of `length` as Python does in slicing.
//
// A negative position counts from the end, and the positions out of range are
// clamped to the string.
func resolvePosition(position int64, length int) int {{
{I}if position < 0 {{
{II}position += int64(length)
{II}if position < 0 {{
{III}return 0
{II}}}
{II}return int(position)
{I}}}

{I}if position > int64(length) {{
{II}return length
{I}}}
{I}return int(position)
}}"""
                ),
                Stripped(
                    f"""\
// Slice `text` from `start` up to `end`, exclusive.
//
// We follow the Python implementation of slicing, since Python is
// the language of the meta-model specifications. Hence, a negative position
// counts from the end, the positions out of range are clamped to the string,
// and the slice is empty if `start` is not before `end`.
func SliceStr(text string, start int64, end int64) string {{
{I}theStart := resolvePosition(start, len(text))
{I}theEnd := resolvePosition(end, len(text))

{I}if theStart >= theEnd {{
{II}return ""
{I}}}

{I}return text[theStart:theEnd]
}}"""
                ),
                Stripped(
                    f"""\
// Slice `text` from `start` up to its end.
//
// See [SliceStr] for the semantics.
func SliceStrFrom(text string, start int64) string {{
{I}return text[resolvePosition(start, len(text)):]
}}"""
                ),
                Stripped(
                    f"""\
// Find the first `sub` in `text` from `start` on.
//
// Return the position of `sub` in `text`, or -1 if `sub` could not be found.
//
// We follow the Python implementation of `str.find`, since Python is
// the language of the meta-model specifications. Hence, a negative `start`
// counts from the end, and a `start` beyond the end of `text` gives -1.
func FindStr(text string, sub string, start int64) int64 {{
{I}if start < 0 {{
{II}start += int64(len(text))
{II}if start < 0 {{
{III}start = 0
{II}}}
{I}}}

{I}if start > int64(len(text)) {{
{II}return -1
{I}}}

{I}index := strings.Index(text[start:], sub)
{I}if index == -1 {{
{II}return -1
{I}}}

{I}return start + int64(index)
}}"""
                ),
            ]
        )

    blocks.append(golang_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
