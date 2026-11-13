"""
Render Python AST nodes for error messages.

We do not use :py:func:`ast.dump` in error messages, since its output changes between
Python versions (*e.g.*, Python 3.13 omits ``ctx=Load()``, ``None`` values and
empty lists). Our error messages are recorded in the golden test data, so they need
to be stable.

We render only the top level of a node as source code, and describe its children
briefly, so that the messages stay short and readable.
"""

import ast
from typing import Final, Mapping, Optional, Type

_SYMBOL_BY_OPERATOR_TYPE: Final[Mapping[Type[ast.AST], str]] = {
    ast.Add: "+",
    ast.And: "and",
    ast.BitAnd: "&",
    ast.BitOr: "|",
    ast.BitXor: "^",
    ast.Div: "/",
    ast.Eq: "==",
    ast.FloorDiv: "//",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.In: "in",
    ast.Invert: "~",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.LShift: "<<",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.MatMult: "@",
    ast.Mod: "%",
    ast.Mult: "*",
    ast.Not: "not",
    ast.NotEq: "!=",
    ast.NotIn: "not in",
    ast.Or: "or",
    ast.Pow: "**",
    ast.RShift: ">>",
    ast.Sub: "-",
    ast.UAdd: "+",
    ast.USub: "-",
}

_DESCRIPTION_BY_NODE_TYPE: Final[Mapping[Type[ast.AST], str]] = {
    ast.AnnAssign: "annotated assignment",
    ast.Assign: "assignment",
    ast.Call: "call",
    ast.Dict: "dict",
    ast.DictComp: "dict comprehension",
    ast.For: "for-loop",
    ast.FormattedValue: "formatted value",
    ast.GeneratorExp: "generator expression",
    ast.If: "if-statement",
    ast.IfExp: "conditional expression",
    ast.JoinedStr: "f-string",
    ast.Lambda: "lambda",
    ast.List: "list",
    ast.ListComp: "list comprehension",
    ast.Return: "return statement",
    ast.Set: "set",
    ast.SetComp: "set comprehension",
    ast.Starred: "starred expression",
    ast.Subscript: "subscript",
    ast.Tuple: "tuple",
    ast.While: "while-loop",
    ast.comprehension: "comprehension clause",
    ast.keyword: "keyword argument",
}


def _describe(node: ast.AST) -> str:
    """
    Describe the ``node`` in a couple of words, falling back to its type name.

    >>> _describe(ast.parse("a | b", mode="eval").body)
    '|-operator'

    >>> _describe(ast.parse("a is not None", mode="eval").body)
    'is not-comparison'

    >>> _describe(ast.parse("-a", mode="eval").body)
    'unary --operator'

    >>> _describe(ast.parse("await a", mode="eval").body)
    'Await'
    """
    if isinstance(node, (ast.BinOp, ast.BoolOp)):
        return f"{_SYMBOL_BY_OPERATOR_TYPE[type(node.op)]}-operator"

    if isinstance(node, ast.UnaryOp):
        return f"unary {_SYMBOL_BY_OPERATOR_TYPE[type(node.op)]}-operator"

    if isinstance(node, ast.Compare):
        return f"{_SYMBOL_BY_OPERATOR_TYPE[type(node.ops[0])]}-comparison"

    return _DESCRIPTION_BY_NODE_TYPE.get(type(node), type(node).__name__)


def _dotted_name(node: ast.AST) -> Optional[str]:
    """
    Render the ``node`` if it is a name or a chain of attributes on a name.

    >>> _dotted_name(ast.parse("self.x.y", mode="eval").body)
    'self.x.y'

    >>> _dotted_name(ast.parse("f().x", mode="eval").body) is None
    True
    """
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        value = _dotted_name(node.value)
        return None if value is None else f"{value}.{node.attr}"

    return None


def _dump_child(node: ast.AST) -> str:
    """
    Render names, attribute chains and constants verbatim, and describe the rest.

    >>> _dump_child(ast.parse("self.f(g(x))", mode="eval").body)
    '<call to self.f>'

    >>> _dump_child(ast.parse("self.xs[0]", mode="eval").body)
    '<subscript of self.xs>'

    >>> _dump_child(ast.parse("f().x", mode="eval").body)
    '<attribute x>'
    """
    dotted_name = _dotted_name(node)
    if dotted_name is not None:
        return dotted_name

    if isinstance(node, ast.Constant):
        return repr(node.value)

    if isinstance(node, ast.Starred):
        value = _dotted_name(node.value)
        if value is not None:
            return f"*{value}"

    elif isinstance(node, ast.Call):
        func = _dotted_name(node.func)
        if func is not None:
            return f"<call to {func}>"

    elif isinstance(node, ast.Subscript):
        value = _dotted_name(node.value)
        if value is not None:
            return f"<subscript of {value}>"

    elif isinstance(node, ast.Attribute):
        return f"<attribute {node.attr}>"

    return f"<{_describe(node)}>"


def dump(node: ast.AST) -> str:
    """
    Render the Python AST ``node`` for error messages, stable across Python versions.

    We render only the top level of ``node`` as source code. The children are
    rendered verbatim only if they are names, attribute chains or constants, and
    described otherwise.

    >>> dump(ast.parse("self.Child", mode="eval").body)
    'self.Child'

    >>> dump(ast.parse("f(g(x), y.h(), *z, w=1)", mode="eval").body)
    'f(<call to g>, <call to y.h>, *z, w=1)'

    >>> dump(ast.parse("a | b | None", mode="eval").body)
    '<|-operator> | None'

    >>> dump(ast.parse("x: Dict[str, int] = {}").body[0])
    'x: <subscript of Dict> = <dict>'

    >>> dump(ast.parse("lambda: 1", mode="eval").body)
    '<lambda>'
    """
    child = _dump_child

    if isinstance(node, ast.Expr):
        return dump(node.value)

    if isinstance(node, ast.Attribute):
        return f"{child(node.value)}.{node.attr}"

    if isinstance(node, ast.Call):
        args = [child(arg) for arg in node.args]
        args.extend(
            (
                f"**{child(keyword.value)}"
                if keyword.arg is None
                else f"{keyword.arg}={child(keyword.value)}"
            )
            for keyword in node.keywords
        )
        return f"{child(node.func)}({', '.join(args)})"

    if isinstance(node, ast.Starred):
        return f"*{child(node.value)}"

    if isinstance(node, ast.BinOp):
        symbol = _SYMBOL_BY_OPERATOR_TYPE[type(node.op)]
        return f"{child(node.left)} {symbol} {child(node.right)}"

    if isinstance(node, ast.UnaryOp):
        symbol = _SYMBOL_BY_OPERATOR_TYPE[type(node.op)]
        separator = " " if isinstance(node.op, ast.Not) else ""
        return f"{symbol}{separator}{child(node.operand)}"

    if isinstance(node, ast.BoolOp):
        symbol = _SYMBOL_BY_OPERATOR_TYPE[type(node.op)]
        return f" {symbol} ".join(child(value) for value in node.values)

    if isinstance(node, ast.Compare):
        parts = [child(node.left)]
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            parts.append(_SYMBOL_BY_OPERATOR_TYPE[type(op)])
            parts.append(child(comparator))
        return " ".join(parts)

    if isinstance(node, ast.IfExp):
        return f"{child(node.body)} if {child(node.test)} else {child(node.orelse)}"

    if isinstance(node, ast.Subscript):
        if isinstance(node.slice, ast.Tuple):
            return (
                f"{child(node.value)}"
                f"[{', '.join(child(elt) for elt in node.slice.elts)}]"
            )
        return f"{child(node.value)}[{child(node.slice)}]"

    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        elts = ", ".join(child(elt) for elt in node.elts)
        if isinstance(node, ast.Tuple):
            return f"({elts},)" if len(node.elts) == 1 else f"({elts})"
        if isinstance(node, ast.List):
            return f"[{elts}]"
        return f"{{{elts}}}"

    if isinstance(node, ast.Dict):
        items = ", ".join(
            f"**{child(value)}" if key is None else f"{child(key)}: {child(value)}"
            for key, value in zip(node.keys, node.values, strict=True)
        )
        return f"{{{items}}}"

    if isinstance(node, ast.Assign):
        return " = ".join(child(part) for part in [*node.targets, node.value])

    if isinstance(node, ast.AnnAssign):
        text = f"{child(node.target)}: {child(node.annotation)}"
        return text if node.value is None else f"{text} = {child(node.value)}"

    if isinstance(node, ast.Return):
        return "return" if node.value is None else f"return {child(node.value)}"

    return child(node)
