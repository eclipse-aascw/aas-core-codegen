"""Provide the types into which we parse the original meta-model."""
import abc
import ast
import os
import pathlib
from typing import Sequence, Optional, Union, Final, Mapping, cast

import docutils.nodes
from icontract import require, DBC, ensure, invariant

from aas_core_codegen.common import (
    Identifier,
    assert_union_of_descendants_exhaustive,
    NonEmptyString,
    Stripped,
    XMLTagName,
)
from aas_core_codegen.parse import tree

_MODULE_NAME = pathlib.Path(os.path.realpath(__file__)).parent.name

#: Built-in primitive types
PRIMITIVE_TYPES = {"bool", "int", "float", "str", "bytearray"}

#: Built-in generic types
GENERIC_TYPES = {Identifier("List"), Identifier("Optional"), Identifier("Tuple")}


class AtomicTypeAnnotation:
    """
    Represent an atomic type annotation, such as ``Asset`` or ``int``.

    Atomic, in this context, means a non-generic type such as ``List``.
    """

    def __init__(self, identifier: Identifier, node: ast.AST) -> None:
        """Initialize with the given values."""
        self.identifier = identifier
        self.node = node

    def __repr__(self) -> str:
        """Represent the instance as a string for debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} "
            f"{self.identifier} at 0x{id(self):x}>"
        )

    def __str__(self) -> str:
        return self.identifier


class SelfTypeAnnotation:
    """Provide a placeholder for the special argument ``self`` in a method"""

    def __str__(self) -> str:
        return "SELF"


class SubscriptedTypeAnnotation:
    """Represent a subscripted type annotation such as ``Optional[...]``."""

    def __init__(
        self,
        identifier: Identifier,
        subscripts: Sequence["TypeAnnotation"],
        node: ast.AST,
    ) -> None:
        """Initialize with the given values."""
        self.identifier = identifier
        self.subscripts = subscripts
        self.node = node

    def __repr__(self) -> str:
        """Represent the instance as a string for debugging."""
        subscripts_str = ", ".join(repr(subscript) for subscript in self.subscripts)
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} "
            f"{self.identifier} at 0x{id(self):x} "
            f"subscripts={subscripts_str}>"
        )

    def __str__(self) -> str:
        """Represent by reconstructing the type annotation heuristically."""
        return "".join(
            [self.identifier, "["]
            + [", ".join([str(subscript) for subscript in self.subscripts])]
            + ["]"]
        )


TypeAnnotation = Union[
    AtomicTypeAnnotation, SubscriptedTypeAnnotation, SelfTypeAnnotation
]


class Description:
    """Represent a docstring describing something in the meta-model."""

    @require(lambda node: isinstance(node.value, str))
    def __init__(self, document: docutils.nodes.document, node: ast.Constant) -> None:
        """Initialize with the given values."""
        self.document = document
        self.node = node


# region Constants


class SetLiteral:
    """Represent a literal as an item of a constant set."""

    #: Original node of the meta-model's Python AST
    node: Final[Union[ast.Attribute, ast.Constant]]

    def __init__(self, node: Union[ast.Attribute, ast.Constant]) -> None:
        """Initialize with the given values."""
        self.node = node


class Constant(DBC):
    """Represent a constant in the meta-model."""

    #: Name of the constant
    name: Final[Identifier]

    #: Description of the constant, if any given in the meta-model
    description: Final[Optional[Description]]

    #: Original node of the meta-model's Python AST
    node: Final[ast.AnnAssign]

    def __init__(
        self,
        name: Identifier,
        description: Optional[Description],
        node: ast.AnnAssign,
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.description = description
        self.node = node

    @abc.abstractmethod
    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        raise NotImplementedError()


class ConstantPrimitive(Constant):
    """Represent a constant value in the meta-model of primitive type."""

    value: Final[Union[bool, int, float, str, bytes]]

    def __init__(
        self,
        name: Identifier,
        value: Union[bool, int, float, str, bytes],
        description: Optional[Description],
        node: ast.AnnAssign,
    ) -> None:
        """Initialize with the given values."""
        Constant.__init__(
            self,
            name=name,
            description=description,
            node=node,
        )

        self.value = value

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class ConstantSet(Constant):
    """Represent a constant set in the meta-model."""

    # NOTE (mristin, 2022-07-01):
    # At this moment, we only support enumeration subsets and sets of strings. That is
    # why we enforce only the atomic type annotations for the
    # :attr:`~items_type_annotation`. Subscripted type annotations are also possible,
    # but would involve more implementation effort.

    #: Type annotation corresponding to the set items
    items_type_annotation: Final[AtomicTypeAnnotation]

    #: Literals contained in the set
    set_literals: Final[Sequence[SetLiteral]]

    #: All the constant subsets of this set
    subsets: Final[Sequence[Identifier]]

    def __init__(
        self,
        name: Identifier,
        items_type_annotation: AtomicTypeAnnotation,
        set_literals: Sequence[SetLiteral],
        subsets: Sequence[Identifier],
        description: Optional[Description],
        node: ast.AnnAssign,
    ) -> None:
        """Initialize with the given values."""
        Constant.__init__(
            self,
            name=name,
            description=description,
            node=node,
        )

        self.items_type_annotation = items_type_annotation
        self.set_literals = set_literals
        self.subsets = subsets

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


# endregion


class Property:
    """
    Represent a property of a class.

    If a property is optional (non-required), the :py:attr:`type_annotation` needs to
    be set with the appropriate ``Optional`` type.
    """

    def __init__(
        self,
        name: Identifier,
        type_annotation: TypeAnnotation,
        description: Optional[Description],
        node: ast.AnnAssign,
        json_name: Optional[NonEmptyString] = None,
        xml_name: Optional[XMLTagName] = None,
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.type_annotation = type_annotation
        self.description = description
        self.node = node
        self.json_name = json_name
        self.xml_name = xml_name


class Default:
    """Represent a default value for an argument."""

    def __init__(self, node: ast.AST) -> None:
        """Initialize with the given values."""
        self.node = node


class Argument:
    """Represent an argument of a method."""

    def __init__(
        self,
        name: Identifier,
        type_annotation: TypeAnnotation,
        default: Optional[Default],
        node: ast.arg,
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.type_annotation = type_annotation
        self.default = default
        self.node = node


class Invariant:
    """Represent an invariant of a class."""

    def __init__(self, description: str, body: tree.Expression, node: ast.AST) -> None:
        self.description = description
        self.body = body
        self.node = node


class Contract:
    """Represent a contract of a method."""

    def __init__(
        self,
        args: Sequence[Identifier],
        description: Optional[str],
        body: tree.Expression,
        node: ast.AST,
    ) -> None:
        self.args = args
        self.description = description
        self.body = body
        self.node = node


class Snapshot:
    """Represent a snapshot of an OLD value capture before the method execution."""

    def __init__(
        self,
        args: Sequence[Identifier],
        name: Identifier,
        body: tree.Expression,
        node: ast.AST,
    ) -> None:
        """Initialize with the given values."""
        self.args = args
        self.name = name
        self.body = body
        self.node = node


class Contracts:
    """Represent the set of contracts for a method."""

    def __init__(
        self,
        preconditions: Sequence[Contract],
        snapshots: Sequence[Snapshot],
        postconditions: Sequence[Contract],
    ) -> None:
        """Initialize with the given values."""
        self.preconditions = preconditions
        self.snapshots = snapshots
        self.postconditions = postconditions


# fmt: off
@ensure(
    lambda expr, result:
    not result
    or (
            isinstance(expr, ast.Expr)
            and isinstance(expr.value, ast.Constant)
            and isinstance(expr.value.value, str)
    )
)
# fmt: on
def is_string_expr(expr: ast.AST) -> bool:
    """Check that the expression is a string literal."""
    return (
        isinstance(expr, ast.Expr)
        and isinstance(expr.value, ast.Constant)
        and isinstance(expr.value.value, str)
    )


class Method(DBC):
    """
    Represent a function or a class method.

    Though we have to distinguish in Python between a function and a method, we term
    both of them "methods" in our model.
    """

    #: Name of the method
    name: Final[Identifier]

    #: Set if the method is marked to be used for verification
    verification: Final[bool]

    #: Specification of method's arguments
    arguments: Final[Sequence[Argument]]

    #: Specification of the method's return value, or None if it is a procedure
    returns: Final[Optional[TypeAnnotation]]

    #: Parsed docstring of the method, if any
    description: Final[Optional[Description]]

    #: Parsed contracts of the method
    contracts: Final[Contracts]

    #: If set, the method is expected to be an instance method which does not
    #: mutate the instance data.
    non_mutating: Final[bool]

    #: Node representing the method in the meta-model's Python AST
    node: Final[ast.AST]

    #: Map arguments by their names
    arguments_by_name: Final[Mapping[str, Argument]]

    # fmt: off
    @require(
        lambda arguments, contracts:
        (
                arg_set := {arg.name for arg in arguments},
                all(
                    arg in arg_set  # pylint: disable=used-before-assignment
                    for precondition in contracts.preconditions
                    for arg in precondition.args
                )
                and all(
                    arg in arg_set
                    for postcondition in contracts.postconditions
                    for arg in postcondition.args if arg not in ('OLD', 'result')
                )
                and all(
                    arg in arg_set
                    for snapshot in contracts.snapshots
                    for arg in snapshot.args
                )
        )[1],
        "All arguments of contracts defined in method arguments"
    )
    @require(
        lambda arguments: (
                arg_names := [arg.name for arg in arguments],
                len(arg_names) == len(set(arg_names))
        )[1],
        "Unique arguments"
    )
    @ensure(
        lambda self:
        len(self.arguments_by_name) == len(self.arguments)
        and all(
            self.arguments_by_name[argument.name] is argument
            for argument in self.arguments
        ),
        "Arguments and arguments by name are consistent"
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        verification: bool,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotation],
        description: Optional[Description],
        contracts: Contracts,
        non_mutating: bool,
        node: ast.AST,
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.verification = verification
        self.arguments = arguments
        self.returns = returns
        self.description = description
        self.contracts = contracts
        self.non_mutating = non_mutating
        self.node = node

        self.arguments_by_name = {
            argument.name: argument for argument in self.arguments
        }  # type: Mapping[Identifier, Argument]

    @abc.abstractmethod
    def __repr__(self) -> str:
        # Make abstract to signal that this is a pure abstract class
        raise NotImplementedError()


class ImplementationSpecificMethod(Method):
    """
    Represent an implementation-specific function or a class method.

    Implementation-specific means that we have to provide a snippet for each
    target implementation.
    """

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class UnderstoodMethod(Method):
    """
    Represent a function or a class method that we could understand.

    We use :py:mod:`aas_core_codegen.parse._rules` to understand it.
    """

    #: Body as an AST that we could understand with
    #: :py:mod:`aas_core_codegen.parse._rules`
    body: Final[Sequence[tree.Node]]

    def __init__(
        self,
        name: Identifier,
        verification: bool,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotation],
        description: Optional[Description],
        contracts: Contracts,
        non_mutating: bool,
        body: Sequence[tree.Node],
        node: ast.AST,
    ) -> None:
        """Initialize with the given values."""
        Method.__init__(
            self,
            name=name,
            verification=verification,
            arguments=arguments,
            returns=returns,
            description=description,
            contracts=contracts,
            non_mutating=non_mutating,
            node=node,
        )

        self.body = body

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class ConstructorToBeUnderstood(Method):
    """
    Represent a constructor of a class.

    We will use :py:mod:`aas_core_codegen.intermediate.construction` to later
    understand it.
    """

    #: Body of the constructor as Python AST. We will understand it in the intermediate
    #: phase using :py:mod:`aas_core_codegen.intermediate.construction`.
    body: Final[Sequence[ast.AST]]

    # fmt: off
    @require(
        lambda body:
        not (len(body) > 0)
        or not is_string_expr(expr=body[0]),
        "Docstring is excluded from the body"
    )
    # fmt: on
    def __init__(
        self,
        arguments: Sequence[Argument],
        description: Optional[Description],
        contracts: Contracts,
        body: Sequence[ast.AST],
        node: ast.AST,
    ) -> None:
        """Initialize with the given values."""
        Method.__init__(
            self,
            name=Identifier("__init__"),
            verification=False,
            arguments=arguments,
            returns=None,
            description=description,
            contracts=contracts,
            non_mutating=False,
            node=node,
        )

        self.body = body

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class Serialization:
    """Define general settings for the de/serialization of a specific class."""

    def __init__(self, with_model_type: Optional[bool]) -> None:
        """
        Initialize with the given values.

        :param with_model_type: The parsed ``with_model_type`` argument
        """
        self.with_model_type = with_model_type


class Class(DBC):
    """Represent a class of the meta-model."""

    #: Name of the class
    name: Final[Identifier]

    #: If set, the class is implementation-specific, and we need to provide a snippet
    #: for it
    is_implementation_specific: Final[bool]

    #: List of all the ancestor classes
    inheritances: Final[Sequence[Identifier]]

    #: Properties of the class
    properties: Final[Sequence[Property]]

    #: Methods of the class
    methods: Final[Sequence["MethodUnion"]]

    #: Invariants of the class
    invariants: Final[Sequence[Invariant]]

    #: Serialization settings of the class
    serialization: Final[Optional[Serialization]]

    #: Description of the class, if any given in the meta-model
    description: Final[Optional[Description]]

    #: Original node of the meta-model's Python AST
    node: Final[ast.ClassDef]

    #: Map each property by its name
    properties_by_name: Final[Mapping[Identifier, Property]]

    #: Map each method by its name
    methods_by_name: Final[Mapping[Identifier, Method]]

    # fmt: off
    @require(
        lambda properties:
        (
                prop_names := [prop.name for prop in properties],
                len(prop_names) == len(set(prop_names))
        )[1],
        "Unique property names"
    )
    @require(
        lambda methods:
        (
                method_names := [method.name for method in methods],
                len(method_names) == len(set(method_names))
        )[1],
        "Unique methods names"
    )
    @require(
        lambda methods:
        all(
            len(method.arguments) >= 1
            and method.arguments[0].name == 'self'
            and isinstance(method.arguments[0].type_annotation, SelfTypeAnnotation)
            for method in methods
        ),
        "``self`` specified in all methods"
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        is_implementation_specific: bool,
        inheritances: Sequence[Identifier],
        properties: Sequence[Property],
        methods: Sequence["MethodUnion"],
        invariants: Sequence[Invariant],
        serialization: Optional[Serialization],
        description: Optional[Description],
        node: ast.ClassDef,
    ) -> None:
        self.name = name
        self.is_implementation_specific = is_implementation_specific
        self.inheritances = inheritances
        self.properties = properties
        self.methods = methods
        self.invariants = invariants
        self.serialization = serialization
        self.description = description
        self.node = node

        self.properties_by_name = {
            prop.name: prop for prop in properties
        }  # type: Mapping[Identifier, Property]

        self.methods_by_name = {
            method.name: method for method in methods
        }  # type: Mapping[Identifier, Method]

    @abc.abstractmethod
    def __repr__(self) -> str:
        raise NotImplementedError()


class AbstractClass(Class):
    """
    Represent an abstract class of the meta-model.

    For example, ``Referable``.
    """

    def __repr__(self) -> str:
        """Represent the class with a name for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} "
            f"{self.name} at 0x{id(self):x}>"
        )


class ConcreteClass(Class):
    """
    Represent a concrete class of the meta-model.

    For example, ``Asset``.
    """

    def __repr__(self) -> str:
        """Represent the class with a name for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class EnumerationLiteral:
    """Represent a single enumeration literal."""

    def __init__(
        self,
        name: Identifier,
        value: str,
        description: Optional[Description],
        node: ast.Assign,
    ) -> None:
        self.name = name
        self.value = value
        self.description = description
        self.node = node


# fmt: off
@invariant(
    lambda self:
    all(
        literal == self.literals_by_name[literal.name]
        for literal in self.literals
    ) and len(self.literals) == len(self.literals_by_name),
    "Literal map consistent on name"
)
# fmt: on
class Enumeration:
    """Represent an enumeration."""

    #: Name of the enumeration
    name: Final[Identifier]

    #: List of the enumeration literals
    literals: Final[Sequence[EnumerationLiteral]]

    #: Description of the enumeration, if any
    description: Final[Optional[Description]]

    #: Node of the enumeration in the meta-model's Python AST
    node: Final[ast.ClassDef]

    #: Map literals by their names
    literals_by_name: Final[Mapping[Identifier, EnumerationLiteral]]

    def __init__(
        self,
        name: Identifier,
        literals: Sequence[EnumerationLiteral],
        description: Optional[Description],
        node: ast.ClassDef,
    ) -> None:
        self.name = name
        self.literals = literals
        self.description = description
        self.node = node

        self.literals_by_name = {
            literal.name: literal for literal in self.literals
        }  # type: Mapping[Identifier, EnumerationLiteral]


OurType = Union[AbstractClass, ConcreteClass, Enumeration]


class MetaModel:
    """Collect information about the underlying meta-model."""

    #: Description of the meta-model extracted from the docstring
    description: Final[Optional[Description]]

    #: Specify the version of the meta-model
    version: Final[str]

    #: Specify the XML namespace that is used both for de/serialization and for schema
    #: definitions
    xml_namespace: Final[Stripped]

    @require(lambda xml_namespace: not xml_namespace.endswith("/"))
    @require(lambda xml_namespace: '"' not in xml_namespace)
    @require(lambda xml_namespace: "'" not in xml_namespace)
    def __init__(
        self,
        version: str,
        xml_namespace: Stripped,
        description: Optional[Description],
    ) -> None:
        self.version = version
        self.xml_namespace = xml_namespace
        self.description = description


class UnverifiedSymbolTable(DBC):
    """
    Represent the original classes in the meta-model.

    This symbol table is unverified and may contain inconsistencies.
    """

    #: List of parsed our types
    our_types: Final[Sequence[OurType]]

    #: List of constants in the meta-model
    constants: Final[Sequence["ConstantUnion"]]

    #: List of implementation-specific verification functions
    verification_functions: Final[Sequence["FunctionUnion"]]

    #: Additional information about the source meta-model
    meta_model: Final[MetaModel]

    _name_to_our_type: Final[Mapping[Identifier, OurType]]

    _name_to_constant: Final[Mapping[Identifier, "ConstantUnion"]]

    # fmt: off
    @require(
        lambda our_types: (
                names := [our_type.name for our_type in our_types],
                len(names) == len(set(names)),
        )[1],
        "Names of our types unique",
    )
    @require(
        lambda constants: (
            names := [constant.name for constant in constants],
            len(names) == len(set(names)),
        )[1],
        "Names of the constants unique"
    )
    @require(
        lambda verification_functions: (
            names := [func.name for func in verification_functions],
            len(names) == len(set(names)),
        )[1],
        "Names of the verification functions unique"
    )
    @require(
        lambda verification_functions:
        all(
            'self' not in func.arguments_by_name
            for func in verification_functions
            if isinstance(func, UnderstoodMethod)
        ),
        "No ``self`` in the verification functions expected as outside of a class"
    )
    # fmt: on
    def __init__(
        self,
        our_types: Sequence[OurType],
        constants: Sequence["ConstantUnion"],
        verification_functions: Sequence["FunctionUnion"],
        meta_model: MetaModel,
    ) -> None:
        """Initialize with the given values and map by name."""
        self.our_types = our_types
        self.constants = constants
        self.verification_functions = verification_functions
        self.meta_model = meta_model

        self._name_to_our_type = {our_type.name: our_type for our_type in our_types}
        self._name_to_constant = {constant.name: constant for constant in constants}

    def find_our_type(self, name: Identifier) -> Optional[OurType]:
        """Find our type with the given name."""
        return self._name_to_our_type.get(name, None)

    def must_find_our_type(self, name: Identifier) -> OurType:
        """
        Find our type with the given name.

        :raise: :py:class:`KeyError` if it does not exist.
        """
        our_type = self._name_to_our_type.get(name, None)
        if our_type is None:
            raise KeyError(name)

        return our_type

    # noinspection GrazieInspection
    def must_find_class(self, name: Identifier) -> Class:
        """
        Find the class with the given name.

        :param name: identifier of the class
        :return: the class
        :raise: :py:class:`KeyError` if the name is not in the symbol table.
        :raise: :py:class:`TypeError` if our type is not a class.
        """
        our_type = self.must_find_our_type(name)

        if not isinstance(our_type, Class):
            raise TypeError(
                f"Our type {name!r} is expected to be a class, "
                f"but it is not: {our_type}"
            )

        return our_type

    def find_constant(self, name: Identifier) -> Optional[Constant]:
        """Find the constant with the given name."""
        return self._name_to_constant.get(name, None)

    def must_find_constant(self, name: Identifier) -> Constant:
        """
        Find the constant with the given name.

        :raise: :py:class:`KeyError` if it does not exist.
        """
        constant = self._name_to_constant.get(name, None)
        if constant is None:
            raise KeyError(name)

        return constant


# noinspection PyInitNewSignature
class SymbolTable(UnverifiedSymbolTable):
    """
    Represent a symbol table that has been locally verified.

    Locality in this context means that there are no dangling or obviously invalid
    inheritances, but higher-order relationships such as inheritance cycles has not
    been verified yet.
    """

    # fmt: off
    @require(
        lambda symbol_table:
        all(
            func.verification
            for func in symbol_table.verification_functions
        ),
        "All verification functions should have ``verification`` set; "
        "this should have been caught as an Error before"
    )
    @require(
        lambda symbol_table:
        all(
            not method.verification
            for our_type in symbol_table.our_types
            if isinstance(our_type, Class)
            for method in our_type.methods
        ),
        "All class methods should not have ``verification`` set; "
        "this should have been caught as an Error before"
    )
    # fmt: on
    def __new__(cls, symbol_table: UnverifiedSymbolTable) -> "SymbolTable":
        return cast(SymbolTable, symbol_table)


# NOTE (mristin, 2022-07-01):
# At this moment, we only handle one type of constants, namely constant sets. However,
# we do anticipate more types of constants in the future, so we already prepare
# the program structure for that case.
ConstantUnion = Union[ConstantPrimitive, ConstantSet]
assert_union_of_descendants_exhaustive(union=ConstantUnion, base_class=Constant)

ClassUnion = Union[AbstractClass, ConcreteClass]
assert_union_of_descendants_exhaustive(union=ClassUnion, base_class=Class)

FunctionUnion = Union[UnderstoodMethod, ImplementationSpecificMethod]

MethodUnion = Union[
    UnderstoodMethod, ImplementationSpecificMethod, ConstructorToBeUnderstood
]
assert_union_of_descendants_exhaustive(union=MethodUnion, base_class=Method)
