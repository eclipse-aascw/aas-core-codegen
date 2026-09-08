"""Generate code of common functionality."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.golang import (
    common as golang_common,
)
from aas_core_codegen.golang.common import INDENT as I, INDENT2 as II, INDENT3 as III


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
def generate() -> str:
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
