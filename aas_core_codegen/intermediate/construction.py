"""Understand the constructors of the classes."""
import abc
import ast
import collections
import itertools
import pathlib
from typing import (
    List,
    Optional,
    MutableMapping,
    Mapping,
    Sequence,
    Union,
    Tuple,
    AbstractSet,
)

import asttokens
from icontract import ensure, require, DBC

from aas_core_codegen import parse, stringify
from aas_core_codegen.common import (
    Identifier,
    Error,
    assert_union_of_descendants_exhaustive,
)
from aas_core_codegen.parse import Method

_MODULE_NAME = pathlib.Path(__file__).parent.name


class CallSuperConstructor:
    """
    Represent a call to the constructor of a super class.

    The arguments of the original ``__init__`` are expected to be propagated as-are.
    """

    super_name: Identifier  #: Identifier of the super class

    def __init__(self, super_name: Identifier) -> None:
        """Initialize with the given values."""
        self.super_name = super_name


class Default(DBC):
    """Represent a default value set to a property if an argument is unspecified."""

    def __init__(self, node: ast.AST) -> None:
        """Initialize with the given values."""
        self.node = node

    @abc.abstractmethod
    def __repr__(self) -> str:
        # Signal that the class is purely abstract
        raise NotImplementedError()


class EmptyList(Default):
    """Represent an empty list set to a property if the argument is unspecified."""

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


class DefaultEnumLiteral(Default):
    """Represent an enum literal set to a property if the argument is unspecified."""

    @require(lambda enum, literal: literal in enum.literals)
    def __init__(
        self, enum: parse.Enumeration, literal: parse.EnumerationLiteral, node: ast.AST
    ) -> None:
        """Initialize with the given values."""
        Default.__init__(self, node=node)
        self.enum = enum
        self.literal = literal

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


class AssignArgument:
    """Represent an assignment of an argument to ``__init__`` to a property."""

    name: Identifier  #: Identifier of the property
    argument: Identifier  #: Identifier of the argument
    default: Optional["DefaultUnion"]  #: Default value if the argument is None

    def __init__(
        self, name: Identifier, argument: Identifier, default: Optional["DefaultUnion"]
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.argument = argument
        self.default = default


Statement = Union[CallSuperConstructor, AssignArgument]


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _call_as_call_to_super_init(
    call: ast.Call,
    parsed_class: parse.Class,
    parsed_symbol_table: parse.SymbolTable,
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[CallSuperConstructor], Optional[Error]]:
    """Understand a call as a call to the constructor of a super-class."""
    if not isinstance(call.func, ast.Attribute):
        return (
            None,
            Error(
                call,
                f"Unexpected call in the body "
                f"of ``__init__``: {atok.get_text(call.func)}; "
                f"only calls to super ``__init__``'s are expected",
            ),
        )

    if call.func.attr != "__init__":
        return (
            None,
            Error(
                call,
                f"Unexpected call in the body "
                f"of ``__init__``: {atok.get_text(call.func)}; "
                f"only calls to super ``__init__``'s are expected",
            ),
        )

    if not isinstance(call.func.value, ast.Name):
        return (
            None,
            Error(
                call.func.value,
                f"Expected a super class as a name "
                f"for a call to super ``__init__``, "
                f"but got: {atok.get_text(call.func.value)}",
            ),
        )

    identifier = Identifier(call.func.value.id)

    if identifier not in parsed_class.inheritances:
        return (
            None,
            Error(
                call.func.value,
                f"Expected a super class in the call "
                f"to a super ``__init__``, "
                f"but {parsed_class.name} does not inherit "
                f"from {identifier}",
            ),
        )

    parsed_super_class = parsed_symbol_table.must_find_class(name=identifier)

    if "__init__" not in parsed_super_class.methods_by_name:
        return (
            None,
            Error(
                call.func,
                f"The super class {parsed_super_class.name} "
                f"does not define a ``__init__``",
            ),
        )

    # region Check the arguments of the call to super ``__init__``

    double_star_keyword = next(
        (keyword for keyword in call.keywords if keyword.arg is None), None
    )

    if double_star_keyword is not None:
        return (
            None,
            Error(
                double_star_keyword,
                "Expected a call to a super ``__init__`` to provide only "
                "explicit keyword arguments, "
                "but got a double-star keyword argument",
            ),
        )

    underlying_errors = []  # type: List[Error]

    for arg_node in itertools.chain(
        call.args, (keyword.value for keyword in call.keywords)
    ):
        if not isinstance(arg_node, ast.Name):
            underlying_errors.append(
                Error(
                    arg_node,
                    f"Expected only names in the arguments to "
                    f"super ``__init__``, but got: {atok.get_text(arg_node)}",
                )
            )

    if len(underlying_errors) > 0:
        return (
            None,
            Error(
                call,
                "Failed to parse the arguments to the super ``__init__``",
                underlying_errors,
            ),
        )

    super_init = parsed_super_class.methods_by_name[Identifier("__init__")]
    resolved_kwargs = dict()  # type: MutableMapping[str, str]

    if len(call.args) > len(super_init.arguments):
        return (
            None,
            Error(
                call,
                f"The ``{parsed_super_class.name}.__init__`` "
                f"expected {len(super_init.arguments)} argument(s), "
                f"but the call provides "
                f"{len(call.args)} positional argument(s)",
            ),
        )

    for arg_node, argument in zip(call.args, super_init.arguments):
        assert isinstance(arg_node, ast.Name)
        resolved_kwargs[argument.name] = arg_node.id

    assert len(underlying_errors) == 0

    for keyword in call.keywords:
        if keyword.arg not in super_init.arguments_by_name:
            underlying_errors.append(
                Error(
                    keyword,
                    f"The ``{parsed_super_class.name}.__init__`` does not expect "
                    f"the argument {keyword.arg}",
                )
            )
        else:
            assert isinstance(keyword.value, ast.Name)
            assert isinstance(keyword.arg, str)
            resolved_kwargs[keyword.arg] = keyword.value.id

    if len(underlying_errors) > 0:
        return (
            None,
            Error(
                call,
                "Failed to parse the arguments to the super ``__init__``",
                underlying_errors,
            ),
        )

    init = parsed_class.methods_by_name[Identifier("__init__")]
    for key, val in resolved_kwargs.items():
        if val not in init.arguments_by_name:
            underlying_errors.append(
                Error(
                    call,
                    f"Expected all the arguments to "
                    f"``{parsed_super_class.name}.__init__`` "
                    f"to be propagation of the original ``__init__`` "
                    f"arguments, but the name {key} is not an argument "
                    f"of ``{parsed_class.name}.__init__``",
                )
            )

        elif key != val:
            underlying_errors.append(
                Error(
                    call,
                    f"Expected the arguments to super ``__init__`` "
                    f"to be passed with the same names, "
                    f"but the argument {key} is passed "
                    f"as the name {val}",
                )
            )

    missing_args = [
        argument.name
        for argument in super_init.arguments
        if argument.name not in resolved_kwargs
    ]

    if len(missing_args) > 0:
        missing_args_str = ", ".join(missing_args)
        underlying_errors.append(
            Error(
                call,
                f"The call to ``{parsed_super_class.name}.__init__`` "
                f"is missing one or more arguments: "
                f"{missing_args_str}",
            )
        )

    if len(underlying_errors) > 0:
        return (
            None,
            Error(
                call,
                "Failed to parse the arguments to the super ``__init__``",
                underlying_errors,
            ),
        )
    # endregion

    return CallSuperConstructor(super_name=parsed_super_class.name), None


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _understand_assignment(
    assign: ast.Assign,
    init: Method,
    parsed_class: parse.Class,
    parsed_symbol_table: parse.SymbolTable,
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[Statement], Optional[Error]]:
    if len(assign.targets) > 1:
        return (
            None,
            Error(
                assign,
                f"Expected only a single target for property assignment, "
                f"but got {len(assign.targets)} targets",
            ),
        )

    target = assign.targets[0]

    if not (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    ):
        return (
            None,
            Error(
                target,
                f"Expected a property as the target of an assignment, "
                f"but got: {atok.get_text(target)}",
            ),
        )

    if target.attr not in parsed_class.properties_by_name:
        return (
            None,
            Error(
                target.value,
                f"The property has not been previously "
                f"defined in the class {parsed_class.name!r}: {target.attr}",
            ),
        )

    if isinstance(assign.value, ast.Name):
        if assign.value.id not in init.arguments_by_name:
            return (
                None,
                Error(
                    assign.value,
                    f"Expected the property {target.attr} to be assigned "
                    f"to an argument, but it was assigned to a non-argument variable: "
                    f"{atok.get_text(assign.value)}",
                ),
            )

        if target.attr != assign.value.id:
            return (
                None,
                Error(
                    assign.value,
                    f"Expected the property {target.attr} to be assigned "
                    f"exactly the argument with the same name, "
                    f"but got: {atok.get_text(assign.value)}",
                ),
            )

        return (
            AssignArgument(
                name=Identifier(target.attr),
                argument=Identifier(target.attr),
                default=None,
            ),
            None,
        )
    elif isinstance(assign.value, ast.IfExp):
        default_node = None  # type: Optional[ast.AST]

        if_exp = assign.value
        # noinspection PyUnresolvedReferences
        if (
            isinstance(if_exp.test, ast.Compare)
            and isinstance(if_exp.test.left, ast.Name)
            and isinstance(if_exp.test.left.ctx, ast.Load)
            and if_exp.test.left.id in init.arguments_by_name
            and len(if_exp.test.ops) == 1
            and isinstance(if_exp.test.ops[0], ast.IsNot)
            and len(if_exp.test.comparators) == 1
            and isinstance(if_exp.test.comparators[0], ast.Constant)
            and if_exp.test.comparators[0].value is None
            and isinstance(if_exp.body, ast.Name)
            and if_exp.body.id == if_exp.test.left.id
            and if_exp.orelse is not None
        ):
            default_node = if_exp.orelse

        elif (
            isinstance(if_exp.test, ast.Compare)
            and isinstance(if_exp.test.left, ast.Name)
            and if_exp.test.left.id in init.arguments_by_name
            and len(if_exp.test.ops) == 1
            and isinstance(if_exp.test.ops[0], ast.Is)
            and len(if_exp.test.comparators) == 1
            and isinstance(if_exp.test.comparators[0], ast.Constant)
            and if_exp.test.comparators[0].value is None
            and isinstance(if_exp.orelse, ast.Name)
            and if_exp.orelse.id == if_exp.test.left.id
            and if_exp.body is not None
        ):
            default_node = if_exp.body
        else:
            # We did not match this case.
            pass

        if default_node is not None:
            default = None  # type: Optional[DefaultUnion]

            if isinstance(default_node, ast.List) and default_node.elts == []:
                default = EmptyList(node=default_node)

            elif isinstance(default_node, ast.Attribute) and isinstance(
                default_node.value, ast.Name
            ):
                our_type = parsed_symbol_table.find_our_type(
                    name=Identifier(default_node.value.id)
                )

                if isinstance(our_type, parse.Enumeration):
                    literal = our_type.literals_by_name.get(
                        Identifier(default_node.attr), None
                    )

                    if literal is not None:
                        default = DefaultEnumLiteral(
                            enum=our_type, literal=literal, node=default_node
                        )
            else:
                assert default is None

            if default is None:
                return None, Error(
                    if_exp.orelse,
                    f"The handling of this default value for "
                    f"the property {target.attr!r} has not been implemented: "
                    f"{ast.dump(default_node)}",
                )
            else:
                assert isinstance(if_exp.test, ast.Compare)
                assert isinstance(if_exp.test.left, ast.Name)

                return (
                    AssignArgument(
                        name=Identifier(target.attr),
                        argument=Identifier(if_exp.test.left.id),
                        default=default,
                    ),
                    None,
                )

    return None, Error(
        assign,
        f"The handling of the constructor statement "
        f"has not been implemented: {ast.dump(assign)}; "
        f"please notify the developers if you really need this feature",
    )


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _understand_body(
    parsed_class: parse.Class,
    parsed_symbol_table: parse.SymbolTable,
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[List[Statement]], Optional[Error]]:
    """Try to understand the body of the constructor for the given ``parsed_class``."""
    init = None  # type: Optional[parse.Method]
    for method in parsed_class.methods:
        if method.name == "__init__":
            init = method
            break

    if init is None:
        return [], None

    errors = []  # type: List[Error]
    result = []  # type: List[Statement]

    assert isinstance(init.node, ast.FunctionDef)

    for stmt in init.node.body:
        if isinstance(stmt, ast.Pass):
            continue
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call_super_init, error = _call_as_call_to_super_init(
                call=stmt.value,
                parsed_class=parsed_class,
                parsed_symbol_table=parsed_symbol_table,
                atok=atok,
            )

            if error is not None:
                errors.append(error)
            else:
                assert call_super_init is not None
                result.append(call_super_init)

        elif isinstance(stmt, ast.Assign):
            prop_assignment, error = _understand_assignment(
                assign=stmt,
                init=init,
                parsed_class=parsed_class,
                parsed_symbol_table=parsed_symbol_table,
                atok=atok,
            )

            if error is not None:
                errors.append(error)
            else:
                assert prop_assignment is not None
                result.append(prop_assignment)
        else:
            errors.append(
                Error(
                    stmt,
                    f"Unexpected statement in the body "
                    f"of ``__init__``: {atok.get_text(stmt)}; "
                    f"only calls to super ``__init__``'s and "
                    f"property assignments expected",
                )
            )

    if len(errors) > 0:
        return (
            None,
            Error(
                init.node,
                f"Failed to understand the constructor "
                f"of the class {parsed_class.name}",
                underlying=errors,
            ),
        )

    return result, None


class ConstructorTable:
    """Map understanding of constructors for the classes."""

    def __init__(self, mapping: Mapping[parse.Class, Sequence[Statement]]) -> None:
        self._mapping = mapping

    def has(self, parsed_class: parse.Class) -> bool:
        """Check if there is an entry in the table for the given ``parsed_class``."""
        return parsed_class in self._mapping

    def must_find(self, parsed_class: parse.Class) -> Sequence[Statement]:
        """
        Find the constructor corresponding to this ``parsed_class``.

        :raise: :py:attr:`KeyError` if the entry does not exist.
        """
        result = self._mapping.get(parsed_class, None)
        if result is None:
            raise KeyError(
                f"No entry found in the constructor table for the class: {parsed_class}"
            )

        return result

    def entries(self) -> AbstractSet[Tuple[parse.Class, Sequence[Statement]]]:
        """Retrieve all the entries in the table."""
        # noinspection PyTypeChecker
        return self._mapping.items()


# fmt: off
@ensure(
    lambda parsed_symbol_table, result:
    result[0] is None
    or all(
        result[0].has(our_type)
        for our_type in parsed_symbol_table.our_types
        if isinstance(our_type, parse.Class)
    ),
    "Constructor understood for each class"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def understand_all(
    parsed_symbol_table: parse.SymbolTable, atok: asttokens.ASTTokens
) -> Tuple[Optional[ConstructorTable], Optional[Error]]:
    """Understand the constructors of all the classes in the symbol table."""
    errors = []  # type: List[Error]
    mapping = (
        collections.OrderedDict()
    )  # type: MutableMapping[parse.Class, List[Statement]]

    for our_type in parsed_symbol_table.our_types:
        if not isinstance(our_type, parse.Class):
            continue

        statements, error = _understand_body(
            parsed_class=our_type, parsed_symbol_table=parsed_symbol_table, atok=atok
        )

        if error is not None:
            errors.append(error)
        else:
            assert statements is not None
            mapping[our_type] = statements

    if len(errors) > 0:
        return (
            None,
            Error(
                atok.tree, "Failed to understand the constructors", underlying=errors
            ),
        )

    return ConstructorTable(mapping=mapping), None


# NOTE (mristin):
# At this point we need to dump only a subset of this module, so we go for YAGNI
# principle and do not provide dump functions for everything.

Dumpable = Union[
    Default,
    EmptyList,
    DefaultEnumLiteral,
    AssignArgument,
    CallSuperConstructor,
]


def _stringify_empty_list(
    that: EmptyList,
) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.PropertyEllipsis("node", that.node),
        ],
    )

    return result


def _stringify_default_enum_literal(
    that: DefaultEnumLiteral,
) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.PropertyEllipsis("node", that.node),
            stringify.Property(
                "enum",
                f"Reference to {that.enum.__class__.__name__} {that.enum.name}",
            ),
            stringify.Property(
                "literal",
                f"Reference to {that.literal.__class__.__name__} "
                f"{that.literal.name}",
            ),
        ],
    )

    return result


def _stringify_assign_argument(
    that: AssignArgument,
) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("name", that.name),
            stringify.Property("argument", that.argument),
            stringify.Property("default", _stringify(that.default)),
        ],
    )

    return result


def _stringify_call_super_constructor(
    that: CallSuperConstructor,
) -> stringify.Entity:
    result = stringify.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify.Property("super_name", that.super_name),
        ],
    )

    return result


_DISPATCH = {
    EmptyList: _stringify_empty_list,
    DefaultEnumLiteral: _stringify_default_enum_literal,
    AssignArgument: _stringify_assign_argument,
    CallSuperConstructor: _stringify_call_super_constructor,
}

stringify.assert_dispatch_exhaustive(dispatch=_DISPATCH, dumpable=Dumpable)


def _stringify(that: Optional[Dumpable]) -> Optional[stringify.Entity]:
    """Dispatch to the correct ``_stringify_*`` method."""
    if that is None:
        return None

    stringify_func = _DISPATCH.get(that.__class__, None)
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


DefaultUnion = Union[EmptyList, DefaultEnumLiteral]
assert_union_of_descendants_exhaustive(union=DefaultUnion, base_class=Default)
