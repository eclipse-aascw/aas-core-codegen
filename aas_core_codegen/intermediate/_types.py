"""Provide types of the intermediate representation."""
import abc
import enum
import pathlib
from typing import (
    Sequence,
    Optional,
    Union,
    TypeVar,
    List,
    Mapping,
    MutableMapping,
    Final,
    FrozenSet,
    Set,
    Iterator,
    OrderedDict,
    Type,
    get_args,
    Dict,
    Any,
)

import docutils.nodes
from icontract import require, invariant, ensure, DBC

from aas_core_codegen import parse
from aas_core_codegen.common import (
    Identifier,
    assert_never,
    assert_union_of_descendants_exhaustive,
    assert_union_without_excluded,
    NonEmptyString,
    Stripped,
    XMLTagName,
)
from aas_core_codegen.intermediate import construction
from aas_core_codegen.parse import tree as parse_tree

_MODULE_NAME = pathlib.Path(__file__).parent.name


class PrimitiveType(enum.Enum):
    """List primitive types."""

    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STR = "str"
    BYTEARRAY = "bytearray"


assert sorted(literal.value for literal in PrimitiveType) == sorted(
    parse.PRIMITIVE_TYPES
), "All primitive types specified in the intermediate layer"

STR_TO_PRIMITIVE_TYPE = {
    literal.value: literal for literal in PrimitiveType
}  # type: Mapping[str, PrimitiveType]

# fmt: off
PRIMITIVE_TYPE_TO_PYTHON_TYPE: Final[
    Mapping[
        PrimitiveType,
        Union[Type[bool], Type[int], Type[float], Type[str], Type[bytearray]
        ]
    ]
] = {
    PrimitiveType.BOOL: bool,
    PrimitiveType.INT: int,
    PrimitiveType.FLOAT: float,
    PrimitiveType.STR: str,
    PrimitiveType.BYTEARRAY: bytearray,
}
assert all(
    primitive_type in PRIMITIVE_TYPE_TO_PYTHON_TYPE
    for primitive_type in PrimitiveType
)
# fmt: on

# fmt: off
PYTHON_TYPE_TO_PRIMITIVE_TYPE: Mapping[
    Union[Type[bool], Type[int], Type[float], Type[str], Type[bytearray]],
    PrimitiveType
] = {
    bool: PrimitiveType.BOOL,
    int: PrimitiveType.INT,
    float: PrimitiveType.FLOAT,
    str: PrimitiveType.STR,
    bytearray: PrimitiveType.BYTEARRAY,
}
assert (
    sorted(key.__name__ for key in PYTHON_TYPE_TO_PRIMITIVE_TYPE) ==
    sorted(value.__name__ for value in PRIMITIVE_TYPE_TO_PYTHON_TYPE.values())
)
# fmt: on

PYTHON_CONSTANT_TYPE_TO_PRIMITIVE_TYPE: Mapping[
    Union[Type[bool], Type[int], Type[float], Type[str], Type[bytes]], PrimitiveType
] = {
    bool: PrimitiveType.BOOL,
    int: PrimitiveType.INT,
    float: PrimitiveType.FLOAT,
    str: PrimitiveType.STR,
    bytes: PrimitiveType.BYTEARRAY,
}


class TypeAnnotation(DBC):
    """Represent a general type annotation."""

    #: Relation to the parse stage
    parsed: Final[parse.TypeAnnotation]

    def __init__(self, parsed: parse.TypeAnnotation) -> None:
        """Initialize with the given values."""
        self.parsed = parsed

    @abc.abstractmethod
    def __str__(self) -> str:
        # Signal that this class is a purely abstract one
        raise NotImplementedError()


class PrimitiveTypeAnnotation(TypeAnnotation):
    """Represent a primitive type such as ``int``."""

    def __init__(self, a_type: PrimitiveType, parsed: parse.TypeAnnotation) -> None:
        """Initialize with the given values."""
        TypeAnnotation.__init__(self, parsed=parsed)
        self.a_type = a_type

    def __str__(self) -> str:
        return str(self.a_type.value)


class OurTypeAnnotation(TypeAnnotation):
    """
    Represent an atomic annotation defined by our type in the meta-model.

     For example, ``Asset``.
    """

    def __init__(self, our_type: "OurType", parsed: parse.TypeAnnotation) -> None:
        """Initialize with the given values."""
        TypeAnnotation.__init__(self, parsed=parsed)
        self.our_type = our_type

    def __str__(self) -> str:
        return self.our_type.name


class ListTypeAnnotation(TypeAnnotation):
    """Represent a type annotation involving a ``List[...]``."""

    def __init__(self, items: "TypeAnnotationUnion", parsed: parse.TypeAnnotation):
        TypeAnnotation.__init__(self, parsed=parsed)

        self.items = items

    def __str__(self) -> str:
        return f"List[{self.items}]"


class TupleTypeAnnotation(TypeAnnotation):
    """
    Represent a type annotation involving a ``Tuple[...]`` of fixed length.

    Unlike :class:`ListTypeAnnotation`, the items are heterogeneous and their
    number is fixed.
    """

    def __init__(
        self, items: Sequence["TypeAnnotationUnion"], parsed: parse.TypeAnnotation
    ):
        TypeAnnotation.__init__(self, parsed=parsed)

        self.items = items

    def __str__(self) -> str:
        items_joined = ", ".join(str(item) for item in self.items)
        return f"Tuple[{items_joined}]"


# NOTE (mristin, 2021-11-19):
# We do not support other generic types except for ``List`` and ``Tuple``. In the
# future we might add support for ``Set``, ``MutableMapping`` *etc.*


class OptionalTypeAnnotation(TypeAnnotation):
    """Represent a type annotation involving an ``Optional[...]``."""

    def __init__(self, value: "TypeAnnotationUnion", parsed: parse.TypeAnnotation):
        TypeAnnotation.__init__(self, parsed=parsed)

        self.value = value

    def __str__(self) -> str:
        return f"Optional[{self.value}]"


TypeAnnotationUnion = Union[
    PrimitiveTypeAnnotation,
    OurTypeAnnotation,
    ListTypeAnnotation,
    TupleTypeAnnotation,
    OptionalTypeAnnotation,
]

assert_union_of_descendants_exhaustive(
    union=TypeAnnotationUnion, base_class=TypeAnnotation
)

TypeAnnotationUnionAsTuple = (
    PrimitiveTypeAnnotation,
    OurTypeAnnotation,
    ListTypeAnnotation,
    TupleTypeAnnotation,
    OptionalTypeAnnotation,
)

assert TypeAnnotationUnionAsTuple == get_args(TypeAnnotationUnion)

TypeAnnotationExceptOptional = Union[
    PrimitiveTypeAnnotation,
    OurTypeAnnotation,
    ListTypeAnnotation,
    TupleTypeAnnotation,
]

assert_union_without_excluded(
    original_union=TypeAnnotationUnion,
    subset_union=TypeAnnotationExceptOptional,
    excluded=[OptionalTypeAnnotation],
)

TypeAnnotationExceptOptionalAsTuple = (
    PrimitiveTypeAnnotation,
    OurTypeAnnotation,
    ListTypeAnnotation,
    TupleTypeAnnotation,
)
assert TypeAnnotationExceptOptionalAsTuple == get_args(TypeAnnotationExceptOptional)

AtomicTypeAnnotation = Union[PrimitiveTypeAnnotation, OurTypeAnnotation]

AtomicTypeAnnotationAsTuple = (PrimitiveTypeAnnotation, OurTypeAnnotation)
assert AtomicTypeAnnotationAsTuple == get_args(AtomicTypeAnnotation)

assert_union_without_excluded(
    original_union=TypeAnnotationUnion,
    subset_union=AtomicTypeAnnotation,
    excluded=[ListTypeAnnotation, TupleTypeAnnotation, OptionalTypeAnnotation],
)


def type_annotations_equal(
    that: TypeAnnotationUnion, other: TypeAnnotationUnion
) -> bool:
    """
    Compare two type annotations for equality.

    Two type annotations are equal if they describe the same type.
    """
    if type(that) is not type(other):
        return False

    if isinstance(that, PrimitiveTypeAnnotation):
        assert isinstance(other, PrimitiveTypeAnnotation)
        return that.a_type == other.a_type

    elif isinstance(that, OurTypeAnnotation):
        assert isinstance(other, OurTypeAnnotation)
        return that.our_type == other.our_type

    elif isinstance(that, ListTypeAnnotation):
        assert isinstance(other, ListTypeAnnotation)
        return type_annotations_equal(that.items, other.items)

    elif isinstance(that, TupleTypeAnnotation):
        assert isinstance(other, TupleTypeAnnotation)
        return len(that.items) == len(other.items) and all(
            type_annotations_equal(that_item, other_item)
            for that_item, other_item in zip(that.items, other.items)
        )

    elif isinstance(that, OptionalTypeAnnotation):
        assert isinstance(other, OptionalTypeAnnotation)
        return type_annotations_equal(that.value, other.value)

    else:
        assert_never(that)

    raise AssertionError("Should not have gotten here")


def beneath_optional(
    type_annotation: TypeAnnotationUnion,
) -> TypeAnnotationExceptOptional:
    """Descend below ``Optional[...]`` to the underlying type."""
    type_anno = type_annotation
    while isinstance(type_anno, OptionalTypeAnnotation):
        type_anno = type_anno.value

    assert not isinstance(type_anno, OptionalTypeAnnotation)

    return type_anno


# region Descriptions

# NOTE (mristin, 2022-03-18):
# We take C# documentation comments as an orientation for the structure of the
# descriptions.


def find_first_field_list(
    element: docutils.nodes.Element,
) -> Optional[docutils.nodes.field_list]:
    """Find the first field list beneath the element or return None."""
    return next(element.findall(condition=docutils.nodes.field_list), None)


class SummaryRemarksDescription(DBC):
    """Represent a description with a summary and remarks."""

    #: Summary as the first line of the docstring
    summary: Final[docutils.nodes.paragraph]

    #: List of remarks following the summary in the docstring
    remarks: Final[Sequence[docutils.nodes.Element]]

    #: Original parsed description
    parsed: Final[parse.Description]

    # fmt: off
    @require(
        lambda summary:
        find_first_field_list(summary) is None,
        "Summary expected without field lists"
    )
    @require(
        lambda remarks:
        all(
            find_first_field_list(remark) is None
            for remark in remarks
        ),
        "Remarks expected without field lists"
    )
    # fmt: on
    def __init__(
        self,
        summary: docutils.nodes.paragraph,
        remarks: Sequence[docutils.nodes.Element],
        parsed: parse.Description,
    ) -> None:
        """Initialize with the given values."""
        self.summary = summary
        self.remarks = remarks
        self.parsed = parsed

    @abc.abstractmethod
    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        raise NotImplementedError()


# noinspection PyAbstractClass
class SummaryRemarksConstraintsDescription(SummaryRemarksDescription):
    """Represent a description with summary, remarks and constraints blocks."""

    #: Map constraint documentation elements by their identifiers
    constraints_by_identifier: Final[OrderedDict[str, docutils.nodes.field_body]]

    # fmt: off
    @require(
        lambda constraints_by_identifier:
        all(
            find_first_field_list(body) is None
            for body in constraints_by_identifier.values()
        ),
        "Constraint bodies expected without field lists"
    )
    # fmt: on
    def __init__(
        self,
        summary: docutils.nodes.paragraph,
        remarks: Sequence[docutils.nodes.Element],
        constraints_by_identifier: OrderedDict[str, docutils.nodes.field_body],
        parsed: parse.Description,
    ) -> None:
        """Initialize with the given values."""
        SummaryRemarksDescription.__init__(
            self, summary=summary, remarks=remarks, parsed=parsed
        )
        self.constraints_by_identifier = constraints_by_identifier


class DescriptionOfMetaModel(SummaryRemarksConstraintsDescription):
    """Represent a description of a meta-model."""

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


class DescriptionOfOurType(SummaryRemarksConstraintsDescription):
    """Represent a description of our type."""

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


class DescriptionOfProperty(SummaryRemarksConstraintsDescription):
    """Represent a documentation of a property."""

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


class DescriptionOfEnumerationLiteral(SummaryRemarksDescription):
    """Represent a documentation of an enumeration literal."""

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


class DescriptionOfSignature(SummaryRemarksDescription):
    """Represent a documentation of a method or a function signature."""

    #: Map argument documentation by the argument names
    arguments_by_name: Final[OrderedDict[Identifier, docutils.nodes.field_body]]

    #: Documentation of the return value, if written
    returns: Final[Optional[docutils.nodes.field_body]]

    # fmt: off
    @require(
        lambda arguments_by_name:
        all(
            find_first_field_list(body) is None
            for body in arguments_by_name.values()
        ),
        "Argument descriptions expected without field lists"
    )
    @require(
        lambda returns:
        not (returns is not None)
        or find_first_field_list(returns) is None,
        "Return value description expected without field lists"
    )
    # fmt: on
    def __init__(
        self,
        summary: docutils.nodes.paragraph,
        remarks: Sequence[docutils.nodes.Element],
        arguments_by_name: OrderedDict[Identifier, docutils.nodes.field_body],
        returns: Optional[docutils.nodes.field_body],
        parsed: parse.Description,
    ) -> None:
        """Initialize with the given values."""
        SummaryRemarksDescription.__init__(
            self, summary=summary, remarks=remarks, parsed=parsed
        )
        self.arguments_by_name = arguments_by_name
        self.returns = returns

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


class DescriptionOfConstant(SummaryRemarksDescription):
    """Represent a documentation of a constant in the meta-model."""

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


# endregion

# region Our types


class Property:
    """Represent a property of a class."""

    #: Name of the property
    name: Final[Identifier]

    #: Type annotation of the property
    type_annotation: Final[TypeAnnotationUnion]

    #: Description of the property, if any
    description: Final[Optional[DescriptionOfProperty]]

    #: The original class where this property is specified.
    #: We stack all the properties over the ancestors, so using ``specified_for``
    #: you can distinguish between inherited properties and genuine properties of
    #: a class.
    specified_for: Final["Class"]

    #: Name of the property in a JSON serialization.
    #:
    #: This is either the explicit name given by the ``json_name`` marker in
    #: the meta-model, or, if none was given, the name inferred from :py:attr:`name`
    #: by the usual naming convention (see :py:mod:`aas_core_codegen.naming`).
    json_name: Final[NonEmptyString]

    #: Name of the property in an XML serialization.
    #:
    #: This is either the explicit name given by the ``xml_name`` marker in
    #: the meta-model, or, if none was given, the name inferred from :py:attr:`name`
    #: by the usual naming convention (see :py:mod:`aas_core_codegen.naming`).
    xml_name: Final[XMLTagName]

    #: Relation to the property from the parse stage
    parsed: Final[parse.Property]

    def __init__(
        self,
        name: Identifier,
        type_annotation: TypeAnnotationUnion,
        description: Optional[DescriptionOfProperty],
        specified_for: "Class",
        json_name: NonEmptyString,
        xml_name: XMLTagName,
        parsed: parse.Property,
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.type_annotation = type_annotation
        self.description = description
        self.specified_for = specified_for
        self.json_name = json_name
        self.xml_name = xml_name
        self.parsed = parsed

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class DefaultPrimitive:
    """Represent a primitive value as a default for an argument."""

    #: The default value
    value: Final[Union[bool, int, float, str, None]]

    #: Relation to the parsed stage
    parsed: Final[parse.Default]

    def __init__(
        self, value: Union[bool, int, float, str, None], parsed: parse.Default
    ) -> None:
        """Initialize with the given values."""
        self.value = value
        self.parsed = parsed


class DefaultEnumerationLiteral:
    """Represent an enumeration literal as a default for an argument."""

    #: Related enumeration
    enumeration: Final["Enumeration"]

    #: Related enumeration literal
    literal: Final["EnumerationLiteral"]

    #: Relation to the parse stage
    parsed: Final[parse.Default]

    # fmt: off
    @require(
        lambda enumeration, literal:
        literal.name in enumeration.literals_by_name
        and enumeration.literals_by_name[literal.name] == literal
    )
    # fmt: on
    def __init__(
        self,
        enumeration: "Enumeration",
        literal: "EnumerationLiteral",
        parsed: parse.Default,
    ) -> None:
        """Initialize with the given values."""
        self.parsed = parsed
        self.enumeration = enumeration
        self.literal = literal


Default = Union[DefaultPrimitive, DefaultEnumerationLiteral]


class Argument:
    """Represent an argument of a method (both of an interface and of class)."""

    #: Name of the argument
    name: Final[Identifier]

    #: Type annotation of the argument
    type_annotation: Final[TypeAnnotationUnion]

    #: Default value of the argument, if any
    default: Final[Optional[Default]]

    #: Relation to the parse stage
    parsed: Final[parse.Argument]

    def __init__(
        self,
        name: Identifier,
        type_annotation: TypeAnnotationUnion,
        default: Optional[Default],
        parsed: parse.Argument,
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.type_annotation = type_annotation
        self.default = default
        self.parsed = parsed


class Serialization:
    """Specify the general settings for serialization of an interface or a class."""

    def __init__(self, with_model_type: bool) -> None:
        """
        Initialize with the given values.

        :param with_model_type:
            if set, the serialization needs to include a discriminator.
        """
        self.with_model_type = with_model_type


class Invariant:
    """Represent an invariant of a class."""

    #: Human-readable description of the invariant
    description: Final[str]

    #: Understood body of the invariant
    body: Final[parse_tree.Expression]

    #: The original our type where this invariant is specified.
    #: We stack all the invariants over the ancestors, so using ``specified_for``
    #: you can distinguish between inherited invariants and genuine invariants of
    #: a class or a constrained primitive.
    specified_for: Final[Union["ConstrainedPrimitive", "Class"]]

    #: Relation to the parse stage
    parsed: Final[parse.Invariant]

    def __init__(
        self,
        description: str,
        body: parse_tree.Expression,
        specified_for: Union["ConstrainedPrimitive", "Class"],
        parsed: parse.Invariant,
    ) -> None:
        self.description = description
        self.body = body
        self.specified_for = specified_for
        self.parsed = parsed


class Contract:
    """Represent a contract of a method."""

    #: Argument names of the contract
    args: Final[Sequence[Identifier]]

    #: Human-readable description of the contract, if any
    description: Final[Optional[str]]

    #: Understood body of the contract
    body: Final[parse_tree.Node]

    #: Relation to the parse stage
    parsed: Final[parse.Contract]

    def __init__(
        self,
        args: Sequence[Identifier],
        description: Optional[str],
        body: parse_tree.Node,
        parsed: parse.Contract,
    ) -> None:
        """Initialize with the given values."""
        self.args = args
        self.description = description
        self.body = body
        self.parsed = parsed


class Snapshot:
    """Represent a snapshot of an OLD value capture before the method execution."""

    #: Argument names of the snapshot
    args: Final[Sequence[Identifier]]

    #: Understood body of the snapshot
    body: Final[parse_tree.Node]

    #: Name of the snapshot variable
    name: Final[Identifier]

    #: Relation to parse stage
    parsed: Final[parse.Snapshot]

    def __init__(
        self,
        args: Sequence[Identifier],
        body: parse_tree.Node,
        name: Identifier,
        parsed: parse.Snapshot,
    ) -> None:
        """Initialize with the given values."""
        self.args = args
        self.body = body
        self.name = name
        self.parsed = parsed


class Contracts:
    """Represent the set of contracts for a method or a function."""

    # NOTE (mristin, 2022-04-07):
    # Common programming languages which work with contracts usually implement
    # pre-conditions in a disjunctive normal form, *i.e.* as a disjunction of
    # conjunctions, where at least one conjunction needs to hold. The individual
    # conjunctions correspond to the levels of the inheritance hierarchy.
    #
    # However, we have not touched methods at the moment nor their proper inheritance.
    # Therefore, we leave the pre-conditions in the intermediate representation as they
    # would appear in the code, without inheritance and hence without disjunctions.
    # In the future, once we want to tackle the methods as a feature, we need to change
    # the way how we model and resolve the pre-conditions through
    # the inheritance hierarchy.

    #: Pre-conditions that need to hold *before* the call
    preconditions: Final[Sequence[Contract]]

    #: Snapshots which are captured *before* the call
    snapshots: Final[Sequence[Snapshot]]

    #: Post-conditions that need to hold *after* the call
    postconditions: Final[Sequence[Contract]]

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


class SignatureLike(DBC):
    """
    Represent a signature-like "something".

    This can be either a signature of a method, a method or a function.
    """

    #: Name of the signature-like
    name: Final[Identifier]

    #: Arguments of the signature-like
    arguments: Final[Sequence[Argument]]

    #: Return type of the signature-like
    returns: Final[Optional[TypeAnnotationUnion]]

    #: Description of the signature-like, if any
    description: Final[Optional[DescriptionOfSignature]]

    #: List of contracts of the signature-like. The contracts are stacked from the
    #: ancestors.
    contracts: Final[Contracts]

    # NOTE (mristin, 2021-12-26):
    # The ``parsed`` must be optional since constructors can be synthesized without
    # being defined in the original meta-model.

    #: Relation to the parse stage
    parsed: Optional[parse.Method]

    #: Map arguments by their names
    arguments_by_name: Final[Mapping[Identifier, Argument]]

    # fmt: off
    @require(
        lambda arguments:
        all(
            arg.name != 'self'
            for arg in arguments
        ),
        "No explicit ``self`` argument in the arguments"
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
        len(self.arguments) == len(self.arguments_by_name)
        and all(
            (
                    found_argument := self.arguments_by_name.get(argument.name, None),
                    found_argument is not None and found_argument is argument
            )[1]
            for argument in self.arguments
        ),
        "Arguments and arguments-by-name consistent"
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotationUnion],
        description: Optional[DescriptionOfSignature],
        contracts: Contracts,
        parsed: Optional[parse.Method],
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.arguments = arguments
        self.returns = returns
        self.description = description
        self.contracts = contracts
        self.parsed = parsed

        self.arguments_by_name = {
            argument.name: argument for argument in self.arguments
        }

    @abc.abstractmethod
    def __repr__(self) -> str:
        # Signal that this is a pure abstract class
        raise NotImplementedError()


class Method(SignatureLike):
    """Represent a method of a class."""

    # NOTE (mristin, 2021-12-26):
    # The ``parsed`` must be optional in the parent class, ``SignatureLike``, since
    # constructors can be synthesized without being defined in the original meta-model.
    #
    # However, methods are never synthesized, so we always have a clear link to
    # the parse stage.

    parsed: parse.Method

    #: The original class where this method is specified.
    #: We stack all the methods over the ancestors, so using ``specified_for``
    #: you can distinguish between inherited methods and genuine methods of
    #: a class.
    specified_for: Final["Class"]

    #: If set, the method does not mutate the instance data.
    #:
    #: We do not check for non-mutating methods in any way as this is very complex,
    #: so we leave it out-of-scope for the moment (2023-07-06).
    non_mutating: Final[bool]

    # fmt: off
    @require(
        lambda name:
        name != "__init__",
        "Expected constructors to be handled in a special way and not as a method"
    )
    @require(
        lambda arguments, contracts:
        (
                arg_set := {arg.name for arg in arguments},
                all(
                    arg in arg_set  # pylint: disable=used-before-assignment
                    for precondition in contracts.preconditions
                    for arg in precondition.args
                    if arg != 'self'
                )
                and all(
                    arg in arg_set
                    for postcondition in contracts.postconditions
                    for arg in postcondition.args
                    if arg not in ('OLD', 'result', 'self')
                )
                and all(
                    arg in arg_set
                    for snapshot in contracts.snapshots
                    for arg in snapshot.args
                    if arg != 'self'
                )
        )[1],
        "All arguments of contracts defined in method arguments except ``self``"
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotationUnion],
        description: Optional[DescriptionOfSignature],
        specified_for: "Class",
        contracts: Contracts,
        non_mutating: bool,
        parsed: parse.Method,
    ) -> None:
        """Initialize with the given values."""
        SignatureLike.__init__(
            self,
            name=name,
            arguments=arguments,
            returns=returns,
            description=description,
            contracts=contracts,
            parsed=parsed,
        )

        self.non_mutating = non_mutating
        self.specified_for = specified_for

    @abc.abstractmethod
    def __repr__(self) -> str:
        # Signal that this is a pure abstract class.
        raise NotImplementedError()


# NOTE (mristin, 2021-12-19):
# At the moment, we support only implementation-specific methods. However, we anticipate
# that we will try to understand the methods in the very near future, so we already
# prepare the class hierarchy for it.


class ImplementationSpecificMethod(Method):
    """Represent an implementation-specific method of a class."""

    # NOTE (mristin, 2021-12-26):
    # The ``parsed`` must be optional in the parent class, ``SignatureLike``, since
    # constructors can be synthesized without being defined in the original meta-model.
    #
    # However, methods are never synthesized, so we always have a clear link to
    # the parse stage here.

    #: Relation to parse stage
    parsed: parse.Method

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class UnderstoodMethod(Method):
    """Represent a method of a class which we could understand."""

    #: Understood syntax tree of the method's body
    body: Final[Sequence[parse_tree.Node]]

    # NOTE (mristin, 2021-12-26):
    # The ``parsed`` must be optional in the parent class, ``SignatureLike``, since
    # constructors can be synthesized without being defined in the original meta-model.
    #
    # However, methods are never synthesized, so we always have a clear link to
    # the parse stage here.

    #: Relation to parse stage
    parsed: parse.Method

    def __init__(
        self,
        name: Identifier,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotationUnion],
        description: Optional[DescriptionOfSignature],
        specified_for: "Class",
        contracts: Contracts,
        non_mutating: bool,
        body: Sequence[parse_tree.Node],
        parsed: parse.Method,
    ) -> None:
        """Initialize with the given values."""
        Method.__init__(
            self,
            name=name,
            arguments=arguments,
            returns=returns,
            description=description,
            specified_for=specified_for,
            contracts=contracts,
            non_mutating=non_mutating,
            parsed=parsed,
        )

        self.body = body

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class Constructor(SignatureLike):
    """
    Represent an understood constructor of a class stacked.

    The constructor is expected to be stacked from the class and all the ancestors.
    """

    #: Interpreted statements of the constructor, including calls to super constructors
    statements: Final[Sequence[construction.Statement]]

    #: Interpreted statements of the constructor stacked over all the ancestors
    #:
    #: ``inlined_statements`` are semantically equivalent to ``statements``. Usually
    #: you want to use them instead of ``statements`` when you deal with languages
    #: which do not support multiple inheritance, so that calls to multiple super
    #: constructors are not possible.
    inlined_statements: Final[Sequence[construction.AssignArgument]]

    #: If set, the constructor is implementation-specific, and we need to provide
    #: a snippet for it.
    is_implementation_specific: Final[bool]

    def __init__(
        self,
        is_implementation_specific: bool,
        arguments: Sequence[Argument],
        contracts: Contracts,
        description: Optional[DescriptionOfSignature],
        statements: Sequence[construction.Statement],
        inlined_statements: Sequence[construction.AssignArgument],
        parsed: Optional[parse.Method],
    ) -> None:
        SignatureLike.__init__(
            self,
            name=Identifier("__init__"),
            arguments=arguments,
            returns=None,
            description=description,
            contracts=contracts,
            parsed=parsed,
        )

        self.is_implementation_specific = is_implementation_specific

        self.statements = statements
        self.inlined_statements = inlined_statements

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return f"<{_MODULE_NAME}.{self.__class__.__name__} at 0x{id(self):x}>"


class EnumerationLiteral:
    """Represent a single enumeration literal."""

    def __init__(
        self,
        name: Identifier,
        value: str,
        description: Optional[DescriptionOfEnumerationLiteral],
        parsed: parse.EnumerationLiteral,
    ) -> None:
        self.name = name
        self.value = value
        self.description = description
        self.parsed = parsed


# fmt: off
@invariant(
    lambda self:
    all(
        literal == self.literals_by_value[literal.value]
        for literal in self.literals
    ),
    "Literal map by value consistent on value"
)
@invariant(
    lambda self:
    sorted(map(id, self.literals_by_value.values())) == sorted(map(id, self.literals)),
    "Literal map by value complete"
)
@invariant(
    lambda self:
    all(
        literal == self.literals_by_name[literal.name]
        for literal in self.literals
    ),
    "Literal map by name consistent on name"
)
@invariant(
    lambda self:
    sorted(map(id, self.literals_by_name.values())) == sorted(map(id, self.literals)),
    "Literal map by name complete"
)
# fmt: on
class Enumeration:
    """Represent an enumeration."""

    #: Name of the enumeration
    name: Final[Identifier]

    #: Literals associated with the enumeration
    literals: Final[Sequence[EnumerationLiteral]]

    #: Description of the enumeration, if any
    description: Final[Optional[DescriptionOfOurType]]

    #: Map literals by their identifiers
    literals_by_name: Final[Mapping[str, EnumerationLiteral]]

    # NOTE (mristin, 2022-09-01):
    # This map is used by the downstream code, *e.g.*, aas-core3.0rc02-testgen.
    #: Map literals by their values
    literals_by_value: Final[Mapping[str, EnumerationLiteral]]

    #: Collect IDs (with :py:func:`id`) of the literal objects in a set
    literal_id_set: Final[FrozenSet[int]]

    #: Set of all the literal values
    literal_value_set: Final[FrozenSet[str]]

    def __init__(
        self,
        name: Identifier,
        literals: Sequence[EnumerationLiteral],
        description: Optional[DescriptionOfOurType],
        parsed: parse.Enumeration,
    ) -> None:
        self.name = name
        self.literals = literals
        self.description = description
        self.parsed = parsed

        self.literals_by_name: Mapping[str, EnumerationLiteral] = {
            literal.name: literal for literal in self.literals
        }

        self.literals_by_value: Mapping[str, EnumerationLiteral] = {
            literal.value: literal for literal in self.literals
        }

        self.literal_id_set = self.__class__._compute_literal_id_set(literals)
        self.literal_value_set = frozenset(literal.value for literal in literals)

    @staticmethod
    def _compute_literal_id_set(
        literals: Sequence[EnumerationLiteral],
    ) -> FrozenSet[int]:
        return frozenset(id(literal) for literal in literals)

    def __getstate__(self) -> Dict[str, Any]:
        state = self.__dict__.copy()

        state.pop("literal_id_set", None)

        return state

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)

        # NOTE (mristin):
        # We rebuild what we could not pickle.
        setattr(
            self, "literal_id_set", Enumeration._compute_literal_id_set(self.literals)
        )

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class ConstrainedPrimitive:
    """Represent a primitive type constrained by one or more invariants."""

    #: Name of the class
    name: Final[Identifier]

    # region Inheritances

    # NOTE (mristin, 2021-12-24):
    # We have to decorate inheritances with ``@property`` so that the client code is
    # forced to use ``_set_inheritances``.

    _inheritances: Sequence["ConstrainedPrimitive"]

    _inheritance_id_set: FrozenSet[int]

    # endregion

    # region Ancestors

    # NOTE (mristin, 2023-03-17):
    # We have to decorate ancestors  with ``@property`` so that the translation code
    # is forced to use ``_set_ancestors``.

    _ancestors: Sequence["ConstrainedPrimitive"]

    _ancestor_id_set: FrozenSet[int]

    # endregion

    # region Descendants

    # NOTE (mristin, 2021-12-24):
    # We have to decorate ``descendant_id_set`` with
    # ``@property`` so that the translation code is forced to use
    # ``_set_descendants``.

    _descendants: Sequence["ConstrainedPrimitive"]

    _descendant_id_set: FrozenSet[int]

    # endregion

    #: Which primitive type is constrained
    constrainee: PrimitiveType

    #: If set, this class is implementation-specific, and we need to provide a snippet
    #: for each implementation target
    is_implementation_specific: Final[bool]

    # region Invariants

    # NOTE (mristin, 2022-03-19):
    # We have to decorate invariants with ``@property`` so that the translation code
    # is forced to use ``_set_invariants``.

    _invariants: Sequence[Invariant]

    _invariant_id_set: FrozenSet[int]

    # endregion

    #: Description of the class
    description: Final[Optional[DescriptionOfOurType]]

    #: Relation to the class from the parse stage
    parsed: parse.Class

    @require(lambda self, ancestors: self not in ancestors)
    def _set_ancestors(self, ancestors: Sequence["ConstrainedPrimitive"]) -> None:
        """
        Set the ancestors in the constrained primitive.

        This method is expected to be called only during the translation phase.
        """
        self._ancestors = ancestors
        self._ancestor_id_set = self.__class__._compute_ancestor_id_set(ancestors)

    @require(lambda self, descendants: self not in descendants)
    def _set_descendants(self, descendants: Sequence["ConstrainedPrimitive"]) -> None:
        """
        Set the descendants in the constrained primitive.

        This method is expected to be called only during the translation phase.
        """
        self._descendants = descendants
        self._descendant_id_set = self.__class__._compute_descendant_id_set(descendants)

    def _set_invariants(self, invariants: Sequence[Invariant]) -> None:
        """
        Set the invariants in the class.

        This method is expected to be called only during the translation phase.
        """
        self._invariants = invariants
        self._invariant_id_set = self.__class__._compute_invariant_id_set(invariants)

    # fmt: off
    @require(
        lambda inheritances:
        len(inheritances) == len(set(inheritance.name for inheritance in inheritances)),
        "No duplicate inheritances"
    )
    # fmt: on
    def _set_inheritances(self, inheritances: Sequence["ConstrainedPrimitive"]) -> None:
        """
        Set the inheritances in the class.

        This method is expected to be called only during the translation phase.
        """
        self._inheritances = inheritances
        self._inheritance_id_set = self.__class__._compute_inheritance_id_set(
            self._inheritances
        )

    # fmt: off
    @require(
        lambda parsed: len(parsed.methods) == 0,
        "No methods expected in the constrained primitive type"
    )
    @require(
        lambda parsed: len(parsed.properties) == 0,
        "No properties expected in the constrained primitive type"
    )
    @require(
        lambda constrainee, inheritances:
        all(
            inheritance.constrainee == constrainee
            for inheritance in inheritances
        ),
        "Constrainee consistent with ancestors"
    )
    @require(
        lambda constrainee, descendants:
        all(
            descendant.constrainee == constrainee
            for descendant in descendants
        ),
        "Constrainee consistent with descendants"
    )
    @require(
        lambda ancestors, inheritances:
        (
            ancestor_id_set := set(id(ancestor) for ancestor in ancestors),
            all(
                id(inheritance) in ancestor_id_set  # pylint: disable=used-before-assignment
                for inheritance in inheritances
            )
        )[1],
        "Inheritances is a subset of ancestors"
    )
    @require(lambda self, inheritances: self not in inheritances)
    @require(lambda self, ancestors: self not in ancestors)
    @require(lambda self, descendants: self not in descendants)
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        inheritances: Sequence["ConstrainedPrimitive"],
        ancestors: Sequence["ConstrainedPrimitive"],
        descendants: Sequence["ConstrainedPrimitive"],
        constrainee: PrimitiveType,
        is_implementation_specific: bool,
        invariants: Sequence[Invariant],
        description: Optional[DescriptionOfOurType],
        parsed: parse.Class,
    ) -> None:
        self.name = name
        self._set_inheritances(inheritances)
        self._set_ancestors(ancestors)
        self._set_descendants(descendants)
        self.constrainee = constrainee
        self.is_implementation_specific = is_implementation_specific
        self._set_invariants(invariants)
        self.description = description
        self.parsed = parsed

    @staticmethod
    def _compute_ancestor_id_set(
        ancestors: Sequence["ConstrainedPrimitive"],
    ) -> FrozenSet[int]:
        return frozenset(id(ancestor) for ancestor in ancestors)

    @staticmethod
    def _compute_descendant_id_set(
        descendants: Sequence["ConstrainedPrimitive"],
    ) -> FrozenSet[int]:
        return frozenset(id(descendant) for descendant in descendants)

    @staticmethod
    def _compute_invariant_id_set(invariants: Sequence[Invariant]) -> FrozenSet[int]:
        return frozenset(id(inv) for inv in invariants)

    @staticmethod
    def _compute_inheritance_id_set(
        inheritances: Sequence["ConstrainedPrimitive"],
    ) -> FrozenSet[int]:
        return frozenset(id(inheritance) for inheritance in inheritances)

    @property
    def inheritances(self) -> Sequence["ConstrainedPrimitive"]:
        """Return direct parents that this class inherits from."""
        return self._inheritances

    @property
    def inheritance_id_set(self) -> FrozenSet[int]:
        """Collect IDs (with :py:func:`id`) of the inheritance objects in a set."""
        return self._inheritance_id_set

    @property
    def ancestors(self) -> Sequence["ConstrainedPrimitive"]:
        """
        Return the ancestor constrained primitives.

        These are the constrained primitives that this one directly or indirectly
        inherits from.
        """
        return self._ancestors

    @property
    def ancestor_id_set(self) -> FrozenSet[int]:
        """Collect IDs (with :py:func:`id`) of the ancestors in a set."""
        return self._ancestor_id_set

    def is_subclass_of(self, constrained_primitive: "ConstrainedPrimitive") -> bool:
        """
        Check whether this one is a subclass of ``constrained_primitive``.

        Every constrained primitive is a subclass of itself.
        """
        # NOTE (mristin, 2022-05-13):
        # This function is not used by the aas-core-codegen, but by downstream clients
        # such as aas-core3.0rc02-testgen.

        if id(constrained_primitive) == id(self):
            return True

        return id(constrained_primitive) in self._ancestor_id_set

    @property
    def descendants(self) -> Sequence["ConstrainedPrimitive"]:
        """
        Return the ancestor constrained primitives.

        These are the constrained primitives that directly or indirectly inherit from
        this one.
        """
        return self._descendants

    @property
    def descendant_id_set(self) -> FrozenSet[int]:
        """List the IDs (as in Python's ``id`` built-in) of the descendants."""
        return self._descendant_id_set

    @property
    def invariants(self) -> Sequence[Invariant]:
        """List invariants of the class."""
        return self._invariants

    @property
    def invariant_id_set(self) -> FrozenSet[int]:
        """Collect IDs (with :py:func:`id`) of the invariant objects in a set."""
        return self._invariant_id_set

    def __getstate__(self) -> Dict[str, Any]:
        state = self.__dict__.copy()

        state.pop("_inheritance_id_set", None)
        state.pop("_ancestor_id_set", None)
        state.pop("_descendant_id_set", None)
        state.pop("_invariant_id_set", None)

        return state

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)

        setattr(
            self,
            "_inheritance_id_set",
            self.__class__._compute_inheritance_id_set(self._inheritances),
        )
        setattr(
            self,
            "_ancestor_id_set",
            self.__class__._compute_ancestor_id_set(self._ancestors),
        )
        setattr(
            self,
            "_descendant_id_set",
            self.__class__._compute_descendant_id_set(self._descendants),
        )
        setattr(
            self,
            "_invariant_id_set",
            ConstrainedPrimitive._compute_invariant_id_set(self._invariants),
        )

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class Class(DBC):
    """Represent an abstract or a concrete class."""

    #: Name of the class
    name: Final[Identifier]

    # region Inheritances

    # NOTE (mristin, 2021-12-24):
    # We have to decorate inheritances with ``@property`` so that the translation code
    # is forced to use ``_set_inheritances``.

    _inheritances: Sequence["ClassUnion"]

    _inheritance_id_set: FrozenSet[int]

    # endregion

    # region Ancestors

    # NOTE (mristin, 2023-03-17):
    # We have to decorate ancestors  with ``@property`` so that the translation code
    # is forced to use ``_set_ancestors``.

    _ancestors: Sequence["ClassUnion"]

    _ancestor_id_set: FrozenSet[int]

    # endregion

    #: If set, this class is implementation-specific, and we need to provide a snippet
    #: for each implementation target
    is_implementation_specific: Final[bool]

    #: Interface of the class. If it is a concrete class with no descendants, there is
    #: no interface available.
    interface: Optional["Interface"]

    # region Descendants

    # NOTE (mristin, 2023-03-24):
    # We have to decorate ``descendant_id_set``, ``descendants``,
    # ``concrete_descendant_id_set`` and ``concrete_descendants`` with
    # ``@property`` so that the translation code is forced to use
    # ``_set_descendants``.

    _descendant_id_set: FrozenSet[int]

    _descendants: Sequence["ClassUnion"]

    _concrete_descendant_id_set: FrozenSet[int]

    _concrete_descendants: Sequence["ConcreteClass"]

    # endregion

    # region Properties

    # NOTE (mristin, 2022-03-19):
    # We have to decorate properties with ``@property`` so that the translation code
    # is forced to use ``_set_properties``.

    _properties: Sequence[Property]

    _properties_by_name: Mapping[Identifier, Property]

    _property_id_set: FrozenSet[int]

    # endregion

    # region Methods

    # NOTE (mristin, 2022-03-19):
    # We have to decorate methods with ``@property`` so that the translation code
    # is forced to use ``_set_methods``.

    _methods: Sequence["MethodUnion"]

    _methods_by_name: Mapping[Identifier, "MethodUnion"]

    _method_id_set: FrozenSet[int]

    # endregion

    #: Constructor specification of the class
    constructor: Final[Constructor]

    # region Invariants

    # NOTE (mristin, 2022-03-19):
    # We have to decorate invariants with ``@property`` so that the translation code
    # is forced to use ``_set_invariants``.

    _invariants: Sequence[Invariant]

    _invariant_id_set: FrozenSet[int]

    # endregion

    #: Particular serialization settings for this class
    serialization: Final[Serialization]

    #: Description of the class
    description: Final[Optional[DescriptionOfOurType]]

    #: Relation to the class from the parse stage
    parsed: Final[parse.Class]

    # fmt: off
    @require(
        lambda inheritances:
        len(inheritances) == len(set(inheritance.name for inheritance in inheritances)),
        "No duplicate inheritances"
    )
    # fmt: on
    def _set_inheritances(self, inheritances: Sequence["ClassUnion"]) -> None:
        """
        Set the inheritances in the class.

        This method is expected to be called only during the translation phase.
        """
        self._inheritances = inheritances
        self._inheritance_id_set = self.__class__._compute_inheritance_id_set(
            self._inheritances
        )

    @require(lambda self, ancestors: self not in ancestors)
    def _set_ancestors(self, ancestors: Sequence["ClassUnion"]) -> None:
        """
        Set the ancestors in the class.

        This method is expected to be called only during the translation phase.
        """
        self._ancestor_id_set = self.__class__._compute_ancestor_id_set(ancestors)
        self._ancestors = ancestors

    @require(lambda self, descendants: self not in descendants)
    def _set_descendants(self, descendants: Sequence["ClassUnion"]) -> None:
        """
        Set the descendants and the concrete descendants in the class.

        This method is expected to be called only during the translation phase.
        """
        self._descendant_id_set = self.__class__._compute_descendant_id_set(descendants)

        self._descendants = descendants

        self._concrete_descendants = [
            descendant
            for descendant in descendants
            if isinstance(descendant, ConcreteClass)
        ]

        self._concrete_descendant_id_set = (
            self.__class__._compute_concrete_descendant_id_set(
                self._concrete_descendants
            )
        )

    # fmt: off
    @require(
        lambda properties:
        len(properties) == len(set(prop.name for prop in properties)),
        "No duplicate properties"
    )
    # fmt: on
    def _set_properties(self, properties: Sequence[Property]) -> None:
        """
        Set the properties in the class.

        This method is expected to be called only during the translation phase.
        """
        self._properties = properties
        self._properties_by_name = {prop.name: prop for prop in properties}
        self._property_id_set = self.__class__._compute_property_id_set(properties)

    # fmt: off
    @require(
        lambda methods:
        len(methods) == len(set(method.name for method in methods)),
        "No duplicate methods"
    )
    # fmt: on
    def _set_methods(self, methods: Sequence["MethodUnion"]) -> None:
        """
        Set the methods in the class.

        This method is expected to be called only during the translation phase.
        """
        self._methods = methods
        self._methods_by_name = {method.name: method for method in methods}
        self._method_id_set = self.__class__._compute_method_id_set(methods)

    def _set_invariants(self, invariants: Sequence[Invariant]) -> None:
        """
        Set the invariants in the class.

        This method is expected to be called only during the translation phase.
        """
        self._invariants = invariants
        self._invariant_id_set = self.__class__._compute_invariant_id_set(invariants)

    # fmt: off
    @require(
        lambda ancestors, inheritances:
        (
            ancestor_id_set := set(id(ancestor) for ancestor in ancestors),
            all(
                id(inheritance) in ancestor_id_set  # pylint: disable=used-before-assignment
                for inheritance in inheritances
            )
        )[1],
        "Inheritances is a subset of ancestors"
    )
    @require(
        lambda ancestors, descendants:
        len(
            set(id(ancestor) for ancestor in ancestors).difference(
                id(descendant) for descendant in descendants
            )
        ) == 0,
        "No ancestor is also a descendant"
    )
    @require(lambda self, inheritances: self not in inheritances)
    @require(lambda self, ancestors: self not in ancestors)
    @require(lambda self, descendants: self not in descendants)
    @ensure(
        lambda self:
        all(
            isinstance(descendant, ConcreteClass)
            for descendant in self.concrete_descendants
        ),
        "All concrete descendants must match in type"
    )
    @ensure(
        lambda descendants, self:
        all(
            (
                    id(descendant) in self.concrete_descendant_id_set
                    and descendant in self.descendants
            )
            for descendant in descendants
        ),
        "Descendants are propagated to properties"
    )
    @ensure(
        lambda self:
        (
                len(
                    self.concrete_descendant_id_set.intersection(self.descendant_id_set)
                ) == len(self.concrete_descendant_id_set)
        ),
        "Concrete descendants are a subset of descendants"
    )
    @ensure(
        lambda self:
        (
            id(descendant) in self.concrete_descendant_id_set
            for descendant in self.descendants
            if isinstance(descendant, ConcreteClass)
        ),
        "All concrete descendants are in concrete descendant set"
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        inheritances: Sequence["ClassUnion"],
        ancestors: Sequence["ClassUnion"],
        interface: Optional["Interface"],
        descendants: Sequence["ClassUnion"],
        is_implementation_specific: bool,
        properties: Sequence[Property],
        methods: Sequence["MethodUnion"],
        constructor: Constructor,
        invariants: Sequence[Invariant],
        serialization: Serialization,
        description: Optional[DescriptionOfOurType],
        parsed: parse.Class,
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self._set_inheritances(inheritances)
        self._set_ancestors(ancestors)
        self.interface = interface
        self._set_descendants(descendants)
        self.is_implementation_specific = is_implementation_specific
        self._set_properties(properties)
        self._set_methods(methods)
        self.constructor = constructor
        self._set_invariants(invariants)
        self.serialization = serialization
        self.description = description
        self.parsed = parsed

    @staticmethod
    def _compute_inheritance_id_set(
        inheritances: Sequence["ClassUnion"],
    ) -> FrozenSet[int]:
        return frozenset(id(inheritance) for inheritance in inheritances)

    @staticmethod
    def _compute_ancestor_id_set(ancestors: Sequence["ClassUnion"]) -> FrozenSet[int]:
        return frozenset(id(ancestor) for ancestor in ancestors)

    @staticmethod
    def _compute_descendant_id_set(
        descendants: Sequence["ClassUnion"],
    ) -> FrozenSet[int]:
        return frozenset(id(descendant) for descendant in descendants)

    @staticmethod
    def _compute_concrete_descendant_id_set(
        concrete_descendants: Sequence["ConcreteClass"],
    ) -> FrozenSet[int]:
        return frozenset(id(descendant) for descendant in concrete_descendants)

    @staticmethod
    def _compute_property_id_set(properties: Sequence[Property]) -> FrozenSet[int]:
        return frozenset(id(prop) for prop in properties)

    @staticmethod
    def _compute_method_id_set(methods: Sequence["MethodUnion"]) -> FrozenSet[int]:
        return frozenset(id(method) for method in methods)

    @staticmethod
    def _compute_invariant_id_set(invariants: Sequence[Invariant]) -> FrozenSet[int]:
        return frozenset(id(inv) for inv in invariants)

    @property
    def inheritances(self) -> Sequence["ClassUnion"]:
        """Return direct parents that this class inherits from."""
        return self._inheritances

    @property
    def inheritance_id_set(self) -> FrozenSet[int]:
        """Collect IDs (with :py:func:`id`) of the inheritance objects in a set."""
        return self._inheritance_id_set

    @property
    def ancestors(self) -> Sequence["ClassUnion"]:
        """Return classes that this class directly or indirectly inherits from."""
        return self._ancestors

    @property
    def ancestor_id_set(self) -> FrozenSet[int]:
        """Collect IDs (with :py:func:`id`) of the ancestor classes in a set."""
        return self._ancestor_id_set

    def is_subclass_of(self, cls: "ClassUnion") -> bool:
        """
        Check whether this class is a subclass of ``cls``.

        Every class is a subclass of itself.
        """
        # NOTE (mristin, 2022-05-13):
        # This function is not used by the aas-core-codegen, but by downstream clients
        # such as aas-core3.0rc02-testgen.

        if id(cls) == id(self):
            return True

        return id(cls) in self._ancestor_id_set

    def is_structural_subtype_of(self, cls: "ClassUnion") -> bool:
        """
        Check whether this class is a structural subtype of ``cls``.

        In contrast to :py:meth:`is_subclass_of`, which follows the nominal
        inheritance hierarchy of the meta-model, structural subtyping only cares
        about the shape of the class: this class is a structural subtype of
        ``cls`` if, for every property of ``cls``, this class defines a property
        of the same name and the exact same type (see
        :py:func:`type_annotations_equal`). Structural subtyping is invariant:
        an optional property is not the same as a required one, in either
        direction.

        Properties are re-specified per class (see
        :py:attr:`Property.specified_for`) instead of being inherited as the same
        object, so, unlike, *e.g.*, :py:attr:`property_id_set`, we can not compare
        the properties by their IDs here — we have to compare them by name and
        type instead.

        Every class is a structural subtype of itself.
        """
        if id(cls) == id(self):
            return True

        for prop_name, cls_prop in cls.properties_by_name.items():
            self_prop = self.properties_by_name.get(prop_name, None)
            if self_prop is None:
                return False

            if not type_annotations_equal(
                self_prop.type_annotation, cls_prop.type_annotation
            ):
                return False

        return True

    @property
    def descendant_id_set(self) -> FrozenSet[int]:
        """List the IDs (as in Python's ``id`` built-in) of the descendants."""
        return self._descendant_id_set

    @property
    def descendants(self) -> Sequence["ClassUnion"]:
        """List all descendants of this class."""
        return self._descendants

    @property
    def concrete_descendant_id_set(self) -> FrozenSet[int]:
        """List the IDs (as in Python's ``id`` built-in) of the concrete descendants."""
        return self._concrete_descendant_id_set

    @property
    def concrete_descendants(self) -> Sequence["ConcreteClass"]:
        """List descendants of this class which are concrete classes."""
        return self._concrete_descendants

    @property
    def properties(self) -> Sequence[Property]:
        """Return list of properties of the class."""
        return self._properties

    @property
    def properties_by_name(self) -> Mapping[Identifier, Property]:
        """Map all properties by their names."""
        return self._properties_by_name

    @property
    def property_id_set(self) -> FrozenSet[int]:
        """Collect IDs (with :py:func:`id`) of the property objects in a set."""
        return self._property_id_set

    @property
    def methods(self) -> Sequence["MethodUnion"]:
        """
        List methods of the class.

        The methods are strictly non-static and non-class (in the Python sense of
        the terms).
        """
        return self._methods

    @property
    def methods_by_name(self) -> Mapping[Identifier, "MethodUnion"]:
        """Map all methods by their names."""
        return self._methods_by_name

    @property
    def method_id_set(self) -> FrozenSet[int]:
        """Collect IDs (with :py:func:`id`) of the method objects in a set."""
        return self._method_id_set

    @property
    def invariants(self) -> Sequence[Invariant]:
        """List invariants of the class."""
        return self._invariants

    @property
    def invariant_id_set(self) -> FrozenSet[int]:
        """Collect IDs (with :py:func:`id`) of the invariant objects in a set."""
        return self._invariant_id_set

    def __getstate__(self) -> Dict[str, Any]:
        state = self.__dict__.copy()

        state.pop("_inheritance_id_set", None)
        state.pop("_ancestor_id_set", None)
        state.pop("_descendant_id_set", None)
        state.pop("_concrete_descendant_id_set", None)
        state.pop("_property_id_set", None)
        state.pop("_method_id_set", None)
        state.pop("_invariant_id_set", None)

        return state

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)

        setattr(
            self,
            "_inheritance_id_set",
            Class._compute_inheritance_id_set(self._inheritances),
        )
        setattr(
            self, "_ancestor_id_set", Class._compute_ancestor_id_set(self._ancestors)
        )
        setattr(
            self,
            "_descendant_id_set",
            Class._compute_descendant_id_set(self._descendants),
        )
        setattr(
            self,
            "_concrete_descendant_id_set",
            Class._compute_concrete_descendant_id_set(self._concrete_descendants),
        )
        setattr(
            self, "_property_id_set", Class._compute_property_id_set(self._properties)
        )
        setattr(self, "_method_id_set", Class._compute_method_id_set(self._methods))
        setattr(
            self, "_invariant_id_set", Class._compute_invariant_id_set(self._invariants)
        )

    @abc.abstractmethod
    def __repr__(self) -> str:
        # Signal that this is a purely abstract class.
        raise NotImplementedError()


class ConcreteClass(Class):
    """Represent a class that can be instantiated."""

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class AbstractClass(Class):
    """Represent a class that is purely abstract and can not be instantiated."""

    #: Interface of the class. All abstract classes have an interface as opposed to
    #: concrete classes, which only have an interface if there are descendants.
    interface: "Interface"

    # We need to override the constructor because the ``interface`` is required.
    def __init__(
        self,
        name: Identifier,
        inheritances: Sequence["ClassUnion"],
        ancestors: Sequence["ClassUnion"],
        interface: "Interface",
        descendants: Sequence["ClassUnion"],
        is_implementation_specific: bool,
        properties: Sequence[Property],
        methods: Sequence["MethodUnion"],
        constructor: Constructor,
        invariants: Sequence[Invariant],
        serialization: Serialization,
        description: Optional[DescriptionOfOurType],
        parsed: parse.Class,
    ) -> None:
        """Initialize with the given values."""
        Class.__init__(
            self,
            name=name,
            inheritances=inheritances,
            ancestors=ancestors,
            interface=interface,
            descendants=descendants,
            is_implementation_specific=is_implementation_specific,
            properties=properties,
            methods=methods,
            constructor=constructor,
            invariants=invariants,
            serialization=serialization,
            description=description,
            parsed=parsed,
        )

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


# endregion


# region Constants


class Constant(DBC):
    """Represent a constant of the meta-model."""

    #: Name of the constant
    name: Final[Identifier]

    #: Description of the constant, if any given in the meta-model
    description: Final[Optional[DescriptionOfConstant]]

    def __init__(
        self,
        name: Identifier,
        description: Optional[DescriptionOfConstant],
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.description = description

    @abc.abstractmethod
    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        raise NotImplementedError()


class ConstantPrimitive(Constant):
    """Represent a constant primitive value in the meta-model."""

    #: Value of the constant
    value: Union[bool, int, float, str, bytes]

    #: Type of the constant
    a_type: Final[PrimitiveType]

    #: Relation to the parse stage
    parsed: Final[parse.ConstantPrimitive]

    # fmt: off
    # noinspection PyTypeHints
    @require(
        lambda value, a_type:
        isinstance(value, PRIMITIVE_TYPE_TO_PYTHON_TYPE[a_type])
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        value: Union[bool, int, float, str, bytes],
        a_type: PrimitiveType,
        description: Optional[DescriptionOfConstant],
        parsed: parse.ConstantPrimitive,
    ) -> None:
        """Initialize with the given values."""
        Constant.__init__(
            self,
            name=name,
            description=description,
        )

        self.value = value
        self.a_type = a_type
        self.parsed = parsed

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class PrimitiveSetLiteral:
    """Represent an item of a set of primitive literals."""

    #: Value of the literal
    value: Union[bool, int, float, str, bytearray]

    #: Type of the literal
    a_type: Final[PrimitiveType]

    #: Relation to the parse stage
    parsed: Final[parse.SetLiteral]

    # fmt: off
    # noinspection PyTypeHints
    @require(
        lambda value, a_type:
        isinstance(value, PRIMITIVE_TYPE_TO_PYTHON_TYPE[a_type])
    )
    # fmt: on
    def __init__(
        self,
        value: Union[bool, int, float, str, bytearray],
        a_type: PrimitiveType,
        parsed: parse.SetLiteral,
    ) -> None:
        """Initialize with the given values."""
        self.value = value
        self.a_type = a_type
        self.parsed = parsed

    def __repr__(self) -> str:
        """Represent as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} "
            f"{self.a_type.name} {self.value!r} at 0x{id(self):x}>"
        )


class ConstantSetOfPrimitives(Constant):
    """Represent a set of primitive literals."""

    #: Type of the literals
    a_type: Final[PrimitiveType]

    #: Members of this subset
    literals: Final[Sequence[PrimitiveSetLiteral]]

    #: All other subsets which are contained in this enumeration subset
    subsets: Final[Sequence["ConstantSetOfPrimitives"]]

    #: Relation to the parse stage
    parsed: Final[parse.ConstantSet]

    #: Set of all the literal values
    literal_value_set: Final[FrozenSet[Union[bool, int, float, str, bytearray]]]

    # fmt: off
    # noinspection PyTypeHints
    @require(
        lambda a_type, literals:
        all(
            literal.a_type is a_type
            for literal in literals
        ),
        "All literals share the same primitive type"
    )
    @ensure(
        lambda self:
        not (len(self.literal_value_set) > 1)
        or (
            python_type := PRIMITIVE_TYPE_TO_PYTHON_TYPE[self.a_type],
            all(
                isinstance(value, python_type)  # pylint: disable=used-before-assignment
                for value in self.literal_value_set
            )
        )[1],
        "Types in the literal value set match ``a_type``"
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        a_type: PrimitiveType,
        literals: Sequence[PrimitiveSetLiteral],
        subsets: Sequence["ConstantSetOfPrimitives"],
        description: Optional[DescriptionOfConstant],
        parsed: parse.ConstantSet,
    ) -> None:
        """Initialize with the given values."""
        Constant.__init__(
            self,
            name=name,
            description=description,
        )

        self.a_type = a_type
        self.literals = literals
        self.subsets = subsets
        self.parsed = parsed

        self.literal_value_set = frozenset(literal.value for literal in literals)

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class ConstantSetOfEnumerationLiterals(Constant):
    """Represent a set of enumeration literals."""

    #: Enumeration that this is a subset of
    enumeration: Final[Enumeration]

    #: Members of this subset
    literals: Final[Sequence[EnumerationLiteral]]

    #: All other subsets which are contained in this enumeration subset
    subsets: Final[Sequence["ConstantSetOfEnumerationLiterals"]]

    #: Relation to the parse stage
    parsed: Final[parse.ConstantSet]

    #: Set of all the IDs (as in Python objects) of the literals
    literal_id_set: Final[FrozenSet[int]]

    #: Set of all the literal values
    literal_value_set: Final[FrozenSet[str]]

    # fmt: off
    @require(
        lambda literals, enumeration:
        all(
            id(literal) in enumeration.literal_id_set
            for literal in literals
        ),
        "All literals are members of the same enumeration"
    )
    @ensure(
        lambda literals, self:
        all(
            id(literal) in self.literal_id_set
            for literal in self.literals
        ) and len(self.literals) == len(self.literal_id_set),
        "Literal set corresponds to literals"
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        enumeration: Enumeration,
        literals: Sequence[EnumerationLiteral],
        subsets: Sequence["ConstantSetOfEnumerationLiterals"],
        description: Optional[DescriptionOfConstant],
        parsed: parse.ConstantSet,
    ) -> None:
        """Initialize with the given values."""
        Constant.__init__(
            self,
            name=name,
            description=description,
        )

        self.enumeration = enumeration
        self.literals = literals
        self.subsets = subsets
        self.parsed = parsed

        self.literal_id_set = self.__class__._compute_literal_id_set(self.literals)
        self.literal_value_set = frozenset(literal.value for literal in self.literals)

    @staticmethod
    def _compute_literal_id_set(
        literals: Sequence[EnumerationLiteral],
    ) -> FrozenSet[int]:
        return frozenset(id(literal) for literal in literals)

    def __getstate__(self) -> Dict[str, Any]:
        state = self.__dict__.copy()

        state.pop("literal_id_set", None)

        return state

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)

        # We rebuild what we did not pickle.
        setattr(
            self,
            "literal_id_set",
            self.__class__._compute_literal_id_set(self.literals),
        )

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


# endregion

# region Verification functions


class Verification(SignatureLike):
    """Represent a verification function defined in the meta-model."""

    parsed: parse.Method

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
                    for arg in postcondition.args
                    if arg not in ('OLD', 'result')
                )
                and all(
                    arg in arg_set
                    for snapshot in contracts.snapshots
                    for arg in snapshot.args
                )
        )[1],
        "All arguments of contracts defined in function arguments"
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotationUnion],
        description: Optional[DescriptionOfSignature],
        contracts: Contracts,
        parsed: parse.Method,
    ) -> None:
        """Initialize with the given values."""
        SignatureLike.__init__(
            self,
            name=name,
            arguments=arguments,
            returns=returns,
            description=description,
            contracts=contracts,
            parsed=parsed,
        )

    @abc.abstractmethod
    def __repr__(self) -> str:
        # Signal that this is a pure abstract class.
        raise NotImplementedError()


class ImplementationSpecificVerification(Verification):
    """Represent an implementation-specific verification function."""

    def __init__(
        self,
        name: Identifier,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotationUnion],
        description: Optional[DescriptionOfSignature],
        contracts: Contracts,
        parsed: parse.Method,
    ) -> None:
        """Initialize with the given values."""
        Verification.__init__(
            self,
            name=name,
            arguments=arguments,
            returns=returns,
            description=description,
            contracts=contracts,
            parsed=parsed,
        )

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class PatternVerification(Verification):
    """
    Represent a function that checks a string against a regular expression.

    There is expected to be a single string argument (the text to be matched).
    The function is expected to return a boolean.
    """

    #: Method as we understood it in the parse stage
    parsed: parse.UnderstoodMethod

    #: Pattern, *i.e.* the regular expression, that the function checks against
    pattern: Final[str]

    #: Expression extracted from the function body to be checked at the end
    pattern_expr: Final[parse_tree.Expression]

    # fmt: off
    @require(
        lambda arguments:
        len(arguments) == 1
        and isinstance(arguments[0].type_annotation, PrimitiveTypeAnnotation)
        and arguments[0].type_annotation.a_type == PrimitiveType.STR,
        "There is a single string argument"
    )
    @require(
        lambda returns:
        (returns is not None)
        and isinstance(returns, PrimitiveTypeAnnotation)
        and returns.a_type == PrimitiveType.BOOL
    )
    # fmt: on
    def __init__(
        self,
        name: Identifier,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotationUnion],
        description: Optional[DescriptionOfSignature],
        contracts: Contracts,
        pattern: str,
        parsed: parse.UnderstoodMethod,
    ) -> None:
        """Initialize with the given values."""
        Verification.__init__(
            self,
            name=name,
            arguments=arguments,
            returns=returns,
            description=description,
            contracts=contracts,
            parsed=parsed,
        )

        self.pattern = pattern
        self.pattern_expr = PatternVerification._extract_pattern_expr(parsed.body)

    @staticmethod
    def _extract_pattern_expr(body: Sequence[parse_tree.Node]) -> parse_tree.Expression:
        """Extract the pattern expression from the body of the pattern verification."""
        assert len(body) >= 1

        assert isinstance(body[-1], parse_tree.Return)
        # noinspection PyUnresolvedReferences
        assert isinstance(body[-1].value, parse_tree.IsNotNone)
        # noinspection PyUnresolvedReferences
        assert isinstance(body[-1].value.value, parse_tree.FunctionCall)
        # noinspection PyUnresolvedReferences
        assert body[-1].value.value.name.identifier == "match"

        # noinspection PyUnresolvedReferences
        match_call = body[-1].value.value

        assert isinstance(
            match_call, parse_tree.FunctionCall
        ), f"{parse_tree.dump(match_call)}"
        assert match_call.name.identifier == "match"

        assert isinstance(match_call.args[0], parse_tree.Expression)
        return match_call.args[0]

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class TranspilableVerification(Verification):
    """
    Represent a function that needs to be transpiled into the native code.

    Unlike :class:`.PatternVerification`, we do not understand this verification
    function at the higher level, and can not use it further in the inference.
    Nevertheless, we can still transpile it into different target implementations.
    """

    #: Method as we understood it in the parse stage
    parsed: parse.UnderstoodMethod

    def __init__(
        self,
        name: Identifier,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotationUnion],
        description: Optional[DescriptionOfSignature],
        contracts: Contracts,
        parsed: parse.UnderstoodMethod,
    ) -> None:
        """Initialize with the given values."""
        Verification.__init__(
            self,
            name=name,
            arguments=arguments,
            returns=returns,
            description=description,
            contracts=contracts,
            parsed=parsed,
        )

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


# endregion


class Signature(SignatureLike):
    """Represent a signature of a method in an interface."""

    def __init__(
        self,
        name: Identifier,
        arguments: Sequence[Argument],
        returns: Optional[TypeAnnotationUnion],
        description: Optional[DescriptionOfSignature],
        contracts: Contracts,
        parsed: parse.Method,
    ) -> None:
        """
        Initialize with the given values.

        The ``parsed`` refers to the method of the abstract or concrete class that
        defines the interface. Mind that we do not introduce interfaces as a concept
        in the meta-model.
        """
        SignatureLike.__init__(
            self,
            name=name,
            arguments=arguments,
            returns=returns,
            description=description,
            contracts=contracts,
            parsed=parsed,
        )

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


class Interface:
    """
    Represent an interface of some abstract and/or concrete classes.

    Mind that the concept of interfaces is *not* used in the meta-model. We introduce
    it at the intermediate stage to facilitate generation of the code, especially for
    targets where multiple inheritance is not supported.
    """

    #: Class which this interface is based on
    base: Final["ClassUnion"]

    #: Name of the interface
    name: Final[Identifier]

    inheritances: Final[Sequence["Interface"]]

    #: List of concrete classes that implement this interface
    implementers: Sequence["ConcreteClass"]

    #: List of properties assumed by the interface
    properties: Final[Sequence[Property]]

    #: List of method signatures assumed by the interface
    signatures: Final[Sequence[Signature]]

    #: Description of the interface, taken from class
    description: Final[Optional[DescriptionOfOurType]]

    #: Relation to the class from the parse stage
    parsed: Final[parse.Class]

    #: Map all properties by their identifiers to the corresponding objects
    properties_by_name: Final[Mapping[Identifier, Property]]

    #: Collect IDs (with :py:func:`id`) of the property objects in a set
    property_id_set: Final[FrozenSet[int]]

    def __init__(
        self,
        base: "ClassUnion",
        inheritances: Sequence["Interface"],
    ) -> None:
        """Initialize with the given values."""
        self.base = base

        self.name = base.name
        self.inheritances = inheritances

        implementers = list(base.concrete_descendants)

        if isinstance(base, ConcreteClass):
            implementers.append(base)

        self.implementers = implementers

        self.properties = [
            prop for prop in base.properties if prop.specified_for is base
        ]

        self.signatures = [
            Signature(
                name=method.name,
                arguments=method.arguments,
                returns=method.returns,
                description=method.description,
                contracts=method.contracts,
                parsed=method.parsed,
            )
            for method in base.methods
            if method.specified_for is base
        ]

        self.description = base.description
        self.parsed = base.parsed

        self.properties_by_name: Mapping[Identifier, Property] = {
            prop.name: prop for prop in self.properties
        }

        self.property_id_set = self.__class__._compute_property_id_set(self.properties)

    @staticmethod
    def _compute_property_id_set(properties: Sequence[Property]) -> FrozenSet[int]:
        return frozenset(id(prop) for prop in properties)

    def __getstate__(self) -> Dict[str, Any]:
        state = self.__dict__.copy()

        state.pop("property_id_set", None)

        return state

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)

        setattr(
            self, "property_id_set", Interface._compute_property_id_set(self.properties)
        )

    def __repr__(self) -> str:
        """Represent the instance as a string for easier debugging."""
        return (
            f"<{_MODULE_NAME}.{self.__class__.__name__} {self.name} at 0x{id(self):x}>"
        )


T = TypeVar("T")


class MetaModel:
    """Collect information about the underlying meta-model."""

    #: Description of the meta-model extracted from the docstring
    description: Final[Optional[DescriptionOfMetaModel]]

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
        description: Optional[DescriptionOfMetaModel],
    ) -> None:
        self.version = version
        self.xml_namespace = xml_namespace
        self.description = description


ClassUnion = Union[AbstractClass, ConcreteClass]


class SymbolTable:
    """Represent all the symbols of the intermediate representation."""

    #: List of all our types that we need for the code generation
    our_types: Final[Sequence["OurType"]]

    #: List of all our types, topologically sorted by inheritance
    our_types_topologically_sorted: Final[Sequence["OurType"]]

    #: List all constants defined in the meta-model
    constants: Final[Sequence["ConstantUnion"]]

    #: Map constants by their name
    constants_by_name: Final[Mapping[Identifier, "ConstantUnion"]]

    #: List of all functions used in the verification
    verification_functions: Final[Sequence["VerificationUnion"]]

    #: Map verification functions by their name
    verification_functions_by_name: Final[Mapping[Identifier, "VerificationUnion"]]

    #: Additional information about the source meta-model
    meta_model: Final[MetaModel]

    _name_to_our_type: Final[Mapping[Identifier, "OurType"]]

    #: List all the enumerations in the symbol table
    enumerations: Final[Sequence["Enumeration"]]

    #: List all the constrained primitives in the symbol table
    constrained_primitives: Final[Sequence["ConstrainedPrimitive"]]

    #: List all the classes (abstract and concrete alike) in the symbol table
    classes: Final[Sequence["ClassUnion"]]

    #: List all the concrete classes in the symbol table
    concrete_classes: Final[Sequence["ConcreteClass"]]

    # fmt: off
    @require(
        lambda our_types: (
                names := [our_type.name for our_type in our_types],
                len(names) == len(set(names)),
        )[1],
        "Names of our types unique",
    )
    @require(
        lambda our_types, our_types_topologically_sorted:
        set(
            id(our_type)
            for our_type in our_types
            if not isinstance(our_type, Enumeration)
        )
        == set(id(our_type) for our_type in our_types_topologically_sorted),
        "Only maybe the order differs between our_types and "
        "our_types_topologically_sorted"
    )
    @require(
        lambda constants: (
                names := [constant.name for constant in constants],
                len(names) == len(set(names)),
        )[1],
        "Names of the constants unique",
    )
    @ensure(
        lambda self:
        all(
            self.must_find_enumeration(enumeration.name)
            for enumeration in self.enumerations
        )
    )
    @ensure(
        lambda self:
        all(
            self.must_find_constrained_primitive(constrained_primitive.name)
            for constrained_primitive in self.constrained_primitives
        )
    )
    @ensure(
        lambda self:
        all(
            self.must_find_concrete_class(cls.name)
            for cls in self.concrete_classes
        )
    )
    @ensure(
        lambda self:
        all(
            self.must_find_class(cls.name)
            for cls in self.classes
        )
    )
    @ensure(
        lambda self:
        all(
            self.verification_functions_by_name[func.name] is func
            for func in self.verification_functions
        )
        and len(self.verification_functions_by_name) == len(
            self.verification_functions),
        "The verification functions and their mapping by name are consistent"
    )
    @ensure(
        lambda self:
        all(
            self.constants_by_name[constant.name] is constant
            for constant in self.constants
        ) and len(self.constants_by_name) == len(self.constants),
        "The constants and their mapping by name are consistent"
    )
    @ensure(
        lambda self:
        all(
            (
                    found_our_type := self.find_our_type(our_type.name),
                    found_our_type is not None and found_our_type is our_type
            )[1]
            for our_type in self.our_types
        ),
        "Finding our types is consistent with ``our_types``"
    )
    # fmt: on
    def __init__(
        self,
        our_types: Sequence["OurType"],
        our_types_topologically_sorted: Sequence["OurTypeExceptEnumeration"],
        constants: Sequence["ConstantUnion"],
        verification_functions: Sequence["VerificationUnion"],
        meta_model: MetaModel,
    ) -> None:
        """Initialize with the given values and map by name."""
        self.our_types = our_types
        self.our_types_topologically_sorted = our_types_topologically_sorted
        self.constants = constants
        self.verification_functions = verification_functions
        self.meta_model = meta_model

        self.constants_by_name = {constant.name: constant for constant in constants}

        self.verification_functions_by_name = {
            func.name: func for func in self.verification_functions
        }

        self.enumerations = [
            our_type for our_type in our_types if isinstance(our_type, Enumeration)
        ]

        self.classes = [
            our_type
            for our_type in our_types
            if isinstance(our_type, (AbstractClass, ConcreteClass))
        ]

        self.concrete_classes = [
            our_type for our_type in our_types if isinstance(our_type, ConcreteClass)
        ]

        self.constrained_primitives = [
            our_type
            for our_type in our_types
            if isinstance(our_type, ConstrainedPrimitive)
        ]

        self._name_to_our_type = {our_type.name: our_type for our_type in our_types}

    def find_our_type(self, name: Identifier) -> Optional["OurType"]:
        """Find our type with the given ``name``."""
        return self._name_to_our_type.get(name, None)

    def must_find_our_type(self, name: Identifier) -> "OurType":
        """
        Find our type with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in our types.
        """
        result = self.find_our_type(name)
        if result is None:
            raise KeyError(name)

        return result

    def must_find_enumeration(self, name: Identifier) -> "Enumeration":
        """
        Find the enumeration with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in our types.
        :raise:
            :py:class:`TypeError` if the ``name`` is our type,
            but is not an enumeration.
        """
        result = self.find_our_type(name)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, Enumeration):
            raise TypeError(
                f"Found {name} in our types; "
                f"expected an instance of {Enumeration.__name__}, "
                f"but got {type(result)}: {result}"
            )

        return result

    def must_find_constrained_primitive(
        self, name: Identifier
    ) -> "ConstrainedPrimitive":
        """
        Find the constrained primitive with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in our types.
        :raise:
            :py:class:`TypeError` if the ``name`` is our type,
            but is not a constrained primitive.
        """
        result = self.find_our_type(name)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, ConstrainedPrimitive):
            raise TypeError(
                f"Found {name} in our types; "
                f"expected an instance of {ConstrainedPrimitive.__name__}, "
                f"but got {type(result)}: {result}"
            )

        return result

    def must_find_class(self, name: Identifier) -> "ClassUnion":
        """
        Find the class with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in our types.
        :raise: :py:class:`TypeError` if the ``name`` is our type, but is not a class.
        """
        result = self.find_our_type(name)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, (AbstractClass, ConcreteClass)):
            raise TypeError(
                f"Found {name} in our types; "
                f"expected an instance of {ClassUnion}, "
                f"but got {type(result)}: {result}"
            )

        return result

    def must_find_abstract_class(self, name: Identifier) -> "AbstractClass":
        """
        Find the abstract class with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in our types.
        :raise:
            :py:class:`TypeError` if the ``name`` is our type,
            but is not an abstract class.
        """
        result = self.find_our_type(name)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, AbstractClass):
            raise TypeError(
                f"Found {name} in our types; "
                f"expected an instance of {AbstractClass.__name__}, "
                f"but got {type(result)}: {result}"
            )

        return result

    def must_find_concrete_class(self, name: Identifier) -> "ConcreteClass":
        """
        Find the concrete class with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in our types.
        :raise:
            :py:class:`TypeError` if the ``name`` is our type,
            but is not a concrete class.
        """
        result = self.find_our_type(name)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, ConcreteClass):
            raise TypeError(
                f"Found {name} in our types; "
                f"expected an instance of {ConcreteClass.__name__}, "
                f"but got {type(result)}: {result}"
            )

        return result

    def must_find_class_or_constrained_primitive(
        self, name: Identifier
    ) -> Union["ClassUnion", ConstrainedPrimitive]:
        """
        Find the class with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in our types.
        :raise:
            :py:class:`TypeError` if the ``name`` is our type, but is neither a class
            nor a constrained primitive
        """
        result = self.find_our_type(name)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, (AbstractClass, ConcreteClass, ConstrainedPrimitive)):
            raise TypeError(
                f"Found {name} in our types; "
                f"expected an instance of either {AbstractClass.__name__}, "
                f"{ConcreteClass.__name__} or {ConstrainedPrimitive.__name__},"
                f"but got {type(result)}: {result}"
            )

        return result

    def must_find_constant(self, name: Identifier) -> "ConstantUnion":
        """
        Find the constant with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in our constants.
        """
        result = self.constants_by_name.get(name, None)
        if result is None:
            raise KeyError(name)

        return result

    def must_find_constant_primitive(self, name: Identifier) -> ConstantPrimitive:
        """
        Find the primitive constant with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in the constants.
        :raise:
            :py:class:`TypeError` if the ``name`` is in the constants, but it is not
            a constant primitive.
        """
        result = self.constants_by_name.get(name, None)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, ConstantPrimitive):
            raise TypeError(
                f"Found {name} in the constants; "
                f"expected an instance of {ConstantPrimitive.__name__},"
                f"but got {type(result)}: {result}"
            )

        return result

    def must_find_constant_set_of_primitives(
        self, name: Identifier
    ) -> ConstantSetOfPrimitives:
        """
        Find the constant set of primitives with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in the constants.
        :raise:
            :py:class:`TypeError` if the ``name`` is in the constants, but it is not
            a constant set of primitives.
        """
        result = self.constants_by_name.get(name, None)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, ConstantSetOfPrimitives):
            raise TypeError(
                f"Found {name} in the constants; "
                f"expected an instance of {ConstantSetOfPrimitives.__name__},"
                f"but got {type(result)}: {result}"
            )

        return result

    def must_find_constant_set_of_enumeration_literals(
        self, name: Identifier
    ) -> ConstantSetOfEnumerationLiterals:
        """
        Find the constant set of enumeration literals with the given ``name``.

        :raise: :py:class:`KeyError` if the ``name`` is not in the constants.
        :raise:
            :py:class:`TypeError` if the ``name`` is in the constants, but it is not
            a constant set of enumeration literals.
        """
        result = self.constants_by_name.get(name, None)
        if result is None:
            raise KeyError(name)

        if not isinstance(result, ConstantSetOfEnumerationLiterals):
            raise TypeError(
                f"Found {name} in the constants; "
                f"expected an instance of {ConstantSetOfEnumerationLiterals.__name__},"
                f"but got {type(result)}: {result}"
            )

        return result

    def is_enumeration_literal_of(
        self, literal: EnumerationLiteral, enumeration_or_constant_set_name: Identifier
    ) -> bool:
        """
        Check that the given ``literal`` is a member of the enumeration or constant set.

        We assume that the enumeration or the constant set of enumeration literals
        exists in the symbol table.

        :raises:
            :py:class:`KeyError` if the ``enumeration_or_constant_set_name`` is neither
            in our types nor in constants

        :raises:
             :py:class:`TypeError` if the ``enumeration_or_constant_set_name`` is
             neither an enumeration nor a constant set of enumeration literals, but
             exists in our types or in the constants.
        """
        our_type = self._name_to_our_type.get(enumeration_or_constant_set_name, None)
        if our_type is not None:
            if not isinstance(our_type, Enumeration):
                raise TypeError(
                    f"Expected an enumeration "
                    f"under the name {enumeration_or_constant_set_name!r}, "
                    f"but got {type(our_type)}: {our_type}"
                )

            return id(literal) in our_type.literal_id_set

        constant = self.constants_by_name.get(enumeration_or_constant_set_name, None)
        if constant is not None:
            if not isinstance(constant, ConstantSetOfEnumerationLiterals):
                raise TypeError(
                    f"Expected a constant set of enumeration literals "
                    f"under the name {enumeration_or_constant_set_name!r}, "
                    f"but got {type(constant)}: {constant}"
                )

            return id(literal) in constant.literal_id_set

        raise KeyError(enumeration_or_constant_set_name)


def try_primitive_type(type_annotation: TypeAnnotationUnion) -> Optional[PrimitiveType]:
    """
    Try to get the underlying primitive type of the type annotation.

    If it is neither a primitive type annotation nor a constrained primitive,
    return None.
    """
    if isinstance(type_annotation, PrimitiveTypeAnnotation):
        return type_annotation.a_type

    elif isinstance(type_annotation, OurTypeAnnotation) and isinstance(
        type_annotation.our_type, ConstrainedPrimitive
    ):
        return type_annotation.our_type.constrainee
    else:
        return None


def map_descendability(
    type_annotation: TypeAnnotationUnion,
) -> MutableMapping[TypeAnnotationUnion, bool]:
    """
    Map the type annotation recursively by the descendability.

    The descendability means that the type annotation references an interface
    or a class *or* that it is a subscripted type annotation which subscribes one or
    more classes of the meta-model.

    Constrained primitives are considered primitives and thus non-descendable.

    The mapping is a form of caching. Otherwise, the time complexity would be quadratic
    if we queried at each type annotation subscript.
    """
    mapping = dict()  # type: MutableMapping[TypeAnnotationUnion, bool]

    def recurse(a_type_annotation: TypeAnnotationUnion) -> bool:
        """Recursively iterate over subscripted type annotations."""
        if isinstance(a_type_annotation, PrimitiveTypeAnnotation):
            mapping[a_type_annotation] = False
            return False

        elif isinstance(a_type_annotation, OurTypeAnnotation):
            result: bool
            if isinstance(a_type_annotation.our_type, Enumeration):
                result = False
            elif isinstance(a_type_annotation.our_type, ConstrainedPrimitive):
                result = False
            elif isinstance(a_type_annotation.our_type, Class):
                result = True
            else:
                assert_never(a_type_annotation.our_type)

            mapping[a_type_annotation] = result
            return result

        elif isinstance(a_type_annotation, ListTypeAnnotation):
            result = recurse(a_type_annotation=a_type_annotation.items)
            mapping[a_type_annotation] = result
            return result

        elif isinstance(a_type_annotation, TupleTypeAnnotation):
            # NOTE (mristin, 2026-09-02):
            # We deliberately recurse into *all* the items, and not just until
            # the first descendable one, so that the ``mapping`` cache is populated
            # for every item.
            item_results = [
                recurse(a_type_annotation=item) for item in a_type_annotation.items
            ]
            result = any(item_results)
            mapping[a_type_annotation] = result
            return result

        elif isinstance(a_type_annotation, OptionalTypeAnnotation):
            result = recurse(a_type_annotation=a_type_annotation.value)
            mapping[a_type_annotation] = result
            return result

        else:
            assert_never(a_type_annotation)

        raise AssertionError("Should not have gotten here")

    _ = recurse(a_type_annotation=type_annotation)

    return mapping


def over_type_annotation_and_nested_type_annotations(
    type_annotation: TypeAnnotationUnion,
) -> Iterator[TypeAnnotationUnion]:
    """
    Iterate recursively over ``type_annotation`` and all its nested type
    annotations.

    This descends into the value of an :class:`OptionalTypeAnnotation`, the
    items of a :class:`ListTypeAnnotation` and the items of a
    :class:`TupleTypeAnnotation`, so it also yields type annotations nested
    arbitrarily deeply (*e.g.*, the ``Tuple[...]`` inside a
    ``List[Tuple[...]]``), not just ``type_annotation`` itself.
    """
    yield type_annotation

    if isinstance(type_annotation, OptionalTypeAnnotation):
        yield from over_type_annotation_and_nested_type_annotations(
            type_annotation.value
        )

    elif isinstance(type_annotation, ListTypeAnnotation):
        yield from over_type_annotation_and_nested_type_annotations(
            type_annotation.items
        )

    elif isinstance(type_annotation, TupleTypeAnnotation):
        for item in type_annotation.items:
            yield from over_type_annotation_and_nested_type_annotations(item)

    else:
        pass


@ensure(
    lambda result: sorted(set(result)) == result,
    "The arities are unique and sorted",
)
def tuple_arities(symbol_table: SymbolTable) -> List[int]:
    """
    List the distinct tuple arities used anywhere in the model, sorted.

    This works recursively: a tuple arity is picked up regardless of how
    deeply the corresponding :class:`TupleTypeAnnotation` is nested within
    a property's type annotation (*e.g.*, inside a ``List[...]`` or
    an ``Optional[...]``), not just when the property itself is directly
    annotated as a tuple.
    """
    arities = set()  # type: Set[int]
    for cls in symbol_table.classes:
        for prop in cls.properties:
            for type_anno in over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if isinstance(type_anno, TupleTypeAnnotation):
                    arities.add(len(type_anno.items))

    return sorted(arities)


def collect_ids_of_our_types_in_properties(symbol_table: SymbolTable) -> Set[int]:
    """
    Collect the IDs of our types occurring in type annotations of the properties.

    The IDs refer to IDs of the Python objects in this context.
    """
    result = set()  # type: Set[int]
    for cls in symbol_table.classes:
        for prop in cls.properties:
            stack = [prop.type_annotation]  # type: List[TypeAnnotationUnion]
            while len(stack) > 0:
                type_anno = stack.pop()

                if isinstance(type_anno, OptionalTypeAnnotation):
                    stack.append(type_anno.value)
                elif isinstance(type_anno, ListTypeAnnotation):
                    stack.append(type_anno.items)
                elif isinstance(type_anno, TupleTypeAnnotation):
                    stack.extend(type_anno.items)
                elif isinstance(type_anno, PrimitiveTypeAnnotation):
                    pass
                elif isinstance(type_anno, OurTypeAnnotation):
                    result.add(id(type_anno.our_type))
                else:
                    assert_never(type_anno)

    return result


DescriptionUnion = Union[
    DescriptionOfMetaModel,
    DescriptionOfOurType,
    DescriptionOfProperty,
    DescriptionOfEnumerationLiteral,
    DescriptionOfSignature,
    DescriptionOfConstant,
]
assert_union_of_descendants_exhaustive(
    union=DescriptionUnion, base_class=SummaryRemarksDescription
)
assert_union_of_descendants_exhaustive(union=ClassUnion, base_class=Class)

ClassUnionAsTuple = (AbstractClass, ConcreteClass)
assert ClassUnionAsTuple == get_args(ClassUnion)

MethodUnion = Union[UnderstoodMethod, ImplementationSpecificMethod]
assert_union_of_descendants_exhaustive(union=MethodUnion, base_class=Method)

OurType = Union[Enumeration, ConstrainedPrimitive, ClassUnion]

OurTypeExceptEnumeration = Union[ConstrainedPrimitive, ClassUnion]
assert_union_without_excluded(
    original_union=OurType,
    subset_union=OurTypeExceptEnumeration,
    excluded=[Enumeration],
)

ConstantSetUnion = Union[ConstantSetOfPrimitives, ConstantSetOfEnumerationLiterals]

ConstantUnion = Union[
    ConstantPrimitive, ConstantSetOfPrimitives, ConstantSetOfEnumerationLiterals
]
assert_union_of_descendants_exhaustive(union=ConstantUnion, base_class=Constant)

VerificationUnion = Union[
    ImplementationSpecificVerification,
    PatternVerification,
    TranspilableVerification,
]
assert_union_of_descendants_exhaustive(union=VerificationUnion, base_class=Verification)
