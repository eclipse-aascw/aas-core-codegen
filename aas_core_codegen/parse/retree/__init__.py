# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""
Parse and operate on regular expressions defined over a possibly-formatted string.

Due to time constraints, we do not handle the whole of Python regular expression,
but just a subset. This subset was exactly enough to handle all the expressions of the
current meta-models. With newer meta-models, the subset is expected to grow.
"""

from aas_core_codegen.parse.retree import (
    _parse,
    _types,
    _stringify,
    _render,
    _visitor,
    _fix,
)

parse = _parse.parse
Error = _parse.Error
Cursor = _parse.Cursor
render_pointer = _parse.render_pointer

Node = _types.Node
Char = _types.Char
Range = _types.Range
Concatenation = _types.Concatenation
SymbolKind = _types.SymbolKind
Symbol = _types.Symbol
Group = _types.Group
CharSet = _types.CharSet
Quantifier = _types.Quantifier
Term = _types.Term
UnionExpr = _types.UnionExpr
Regex = _types.Regex
TermValueUnion = _types.TermValueUnion
Visitor = _types.Visitor
Transformer = _types.Transformer

PassThroughVisitor = _visitor.PassThroughVisitor

dump = _stringify.dump

Renderer = _render.Renderer
render = _render.render

fix_for_utf16_regex_in_place = _fix.fix_for_utf16_regex_in_place
