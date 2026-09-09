"""
Infer the types of the tree nodes.

Note that these types roughly follow the type annotations in
:py:mod:`aas_core_codegen.intermediate._types`, but are not identical. For example,
the ``LENGTH`` primitive exists only in type inference. Another example, we do not
track ``parsed`` as the types are inferred in the intermediate stage, but can not
be traced back to the parse stage.
"""

import abc
import contextlib
import enum
from typing import (
    Mapping,
    MutableMapping,
    Optional,
    List,
    Final,
    Sequence,
    Union,
    get_args,
    Tuple,
)

from icontract import DBC, ensure, require

from aas_core_codegen.common import (
    Identifier,
    Error,
    assert_never,
    assert_union_of_descendants_exhaustive,
    assert_union_without_excluded,
)
from aas_core_codegen.intermediate import _types
from aas_core_codegen.parse import tree as parse_tree


class PrimitiveType(enum.Enum):
    """List primitive types."""

    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STR = "str"
    BYTEARRAY = "bytearray"

    #: Denote the language-agnostic type returned from ``len(.)``.
    #: Depending on the language, this is not the same as ``INT``.
    LENGTH = "length"

    #: Denote that the node is a statement and that there is no type
    NONE = "None"


class TypeAnnotation(DBC):
    """Represent an inferred type annotation."""

    @abc.abstractmethod
    def __str__(self) -> str:
        # Signal that this is a purely abstract class
        raise NotImplementedError()


class AtomicTypeAnnotation(TypeAnnotation):
    """
    Represent an atomic type annotation.

    Atomic, in this context, means a non-generic type annotation.

    For example, ``int``.
    """

    @abc.abstractmethod
    def __str__(self) -> str:
        # Signal that this is a purely abstract class
        raise NotImplementedError()


class PrimitiveTypeAnnotation(AtomicTypeAnnotation):
    """Represent a primitive type such as ``int``."""

    def __init__(self, a_type: PrimitiveType) -> None:
        """Initialize with the given values."""
        self.a_type = a_type

    def __str__(self) -> str:
        return str(self.a_type.value)


# NOTE (mristin):
# The types in _types module provide a different set of primitive types,
# so we have to map here.
_PRIMITIVE_TYPES_TO_OUR_PRIMITIVE_TYPES: Final[
    Mapping[_types.PrimitiveType, PrimitiveType]
] = {
    _types.PrimitiveType.BOOL: PrimitiveType.BOOL,
    _types.PrimitiveType.INT: PrimitiveType.INT,
    _types.PrimitiveType.FLOAT: PrimitiveType.FLOAT,
    _types.PrimitiveType.STR: PrimitiveType.STR,
    _types.PrimitiveType.BYTEARRAY: PrimitiveType.BYTEARRAY,
}
assert all(
    literal in _PRIMITIVE_TYPES_TO_OUR_PRIMITIVE_TYPES
    for literal in _types.PrimitiveType
)


class OurTypeAnnotation(AtomicTypeAnnotation):
    """
    Represent an atomic annotation defined by our type in the meta-model.

     For example, ``Asset``.
    """

    def __init__(self, our_type: _types.OurType) -> None:
        """Initialize with the given values."""
        self.our_type = our_type

    def __str__(self) -> str:
        return self.our_type.name


def try_primitive_type(
    type_annotation: "TypeAnnotationUnion",
) -> Optional[PrimitiveType]:
    """
    Try to get the underlying primitive type of the type annotation.

    If it is neither a primitive type annotation nor a constrained primitive,
    return None.
    """
    if isinstance(type_annotation, PrimitiveTypeAnnotation):
        return type_annotation.a_type

    elif isinstance(type_annotation, OurTypeAnnotation) and isinstance(
        type_annotation.our_type, _types.ConstrainedPrimitive
    ):
        return _PRIMITIVE_TYPES_TO_OUR_PRIMITIVE_TYPES[
            type_annotation.our_type.constrainee
        ]
    else:
        return None


class FunctionTypeAnnotation(AtomicTypeAnnotation):
    """Represent a function as a type."""

    @abc.abstractmethod
    def __str__(self) -> str:
        # Signal that this is a purely abstract class
        raise NotImplementedError()


class VerificationTypeAnnotation(FunctionTypeAnnotation):
    """Represent a type of verification function."""

    def __init__(self, func: _types.Verification):
        """Initialize with the given values."""
        self.func = func

    def __str__(self) -> str:
        return self.func.name


class BuiltinFunction:
    """Represent a built-in function."""

    def __init__(self, name: Identifier, returns: Optional["TypeAnnotationUnion"]):
        """Initialize with the given values."""
        self.name = name
        self.returns = returns


class BuiltinFunctionTypeAnnotation(FunctionTypeAnnotation):
    """Represent a type of built-in function."""

    def __init__(self, func: BuiltinFunction):
        """Initialize with the given values."""
        self.func = func

    def __str__(self) -> str:
        return self.func.name


class MethodTypeAnnotation(AtomicTypeAnnotation):
    """Represent a type of class method."""

    def __init__(self, method: _types.Method):
        """Initialize with the given values."""
        self.method = method

    def __str__(self) -> str:
        return self.method.name


class SubscriptedTypeAnnotation(TypeAnnotation):
    """Represent a subscripted (i.e. generic) type annotation.

    The subscripted type annotations are, for example, ``List[...]`` (or
    ``Mapping[..., ...]``, *etc.*).
    """

    @abc.abstractmethod
    def __str__(self) -> str:
        # Signal that this is a purely abstract class
        raise NotImplementedError()


class ListTypeAnnotation(SubscriptedTypeAnnotation):
    """Represent a type annotation involving a ``List[...]``."""

    def __init__(self, items: "TypeAnnotationUnion"):
        self.items = items

    def __str__(self) -> str:
        return f"List[{self.items}]"


class SetTypeAnnotation(SubscriptedTypeAnnotation):
    """Represent a type annotation involving a ``Set[...]``."""

    def __init__(self, items: "TypeAnnotationUnion"):
        self.items = items

    def __str__(self) -> str:
        return f"Set[{self.items}]"


class TupleTypeAnnotation(SubscriptedTypeAnnotation):
    """
    Represent a type annotation involving a ``Tuple[...]`` of fixed length.

    Unlike :class:`ListTypeAnnotation`, the items are heterogeneous and their
    number is fixed.
    """

    def __init__(self, items: Sequence["TypeAnnotationUnion"]):
        self.items = items

    def __str__(self) -> str:
        items_joined = ", ".join(str(item) for item in self.items)
        return f"Tuple[{items_joined}]"


class OptionalTypeAnnotation(SubscriptedTypeAnnotation):
    """Represent a type annotation involving an ``Optional[...]``."""

    def __init__(self, value: "TypeAnnotationUnion"):
        self.value = value

    def __str__(self) -> str:
        return f"Optional[{self.value}]"


class EnumerationAsTypeTypeAnnotation(TypeAnnotation):
    """
    Represent an enum class as a type.

    Note that this is not the enum as a type of that enum class, but
    rather the type-as-a-type. We write``Type[T]`` in Python to describe this.
    """

    # NOTE (mristin, 2022-02-04):
    # The name of this class is admittedly clumsy. Please feel free to change if you
    # come up with a better idea.

    def __init__(self, enumeration: _types.Enumeration) -> None:
        """Initialize with the given values."""
        self.enumeration = enumeration

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{self.enumeration}]"


def beneath_optional(
    type_annotation: "TypeAnnotationUnion",
) -> "TypeAnnotationExceptOptional":
    """Recurse over optionals until we reach a non-optional."""
    while isinstance(type_annotation, OptionalTypeAnnotation):
        type_annotation = type_annotation.value

    return type_annotation


def _type_annotations_equal(
    that: "TypeAnnotationUnion", other: "TypeAnnotationUnion"
) -> bool:
    """Check whether the ``that`` and ``other`` type annotations are identical."""
    if isinstance(that, PrimitiveTypeAnnotation):
        if not isinstance(other, PrimitiveTypeAnnotation):
            return False
        else:
            return that.a_type == other.a_type

    elif isinstance(that, OurTypeAnnotation):
        if not isinstance(other, OurTypeAnnotation):
            return False
        else:
            return that.our_type is other.our_type

    elif isinstance(that, VerificationTypeAnnotation):
        if not isinstance(other, VerificationTypeAnnotation):
            return False
        else:
            return that.func is other.func

    elif isinstance(that, BuiltinFunctionTypeAnnotation):
        if not isinstance(other, BuiltinFunctionTypeAnnotation):
            return False
        else:
            return that.func is other.func

    elif isinstance(that, MethodTypeAnnotation):
        if not isinstance(other, MethodTypeAnnotation):
            return False
        else:
            return that.method is other.method

    elif isinstance(that, ListTypeAnnotation):
        if not isinstance(other, ListTypeAnnotation):
            return False
        else:
            return _type_annotations_equal(that.items, other.items)

    elif isinstance(that, SetTypeAnnotation):
        if not isinstance(other, SetTypeAnnotation):
            return False
        else:
            return _type_annotations_equal(that.items, other.items)

    elif isinstance(that, TupleTypeAnnotation):
        if not isinstance(other, TupleTypeAnnotation):
            return False
        else:
            return len(that.items) == len(other.items) and all(
                _type_annotations_equal(that_item, other_item)
                for that_item, other_item in zip(that.items, other.items)
            )

    elif isinstance(that, OptionalTypeAnnotation):
        if not isinstance(other, OptionalTypeAnnotation):
            return False
        else:
            return _type_annotations_equal(that.value, other.value)

    elif isinstance(that, EnumerationAsTypeTypeAnnotation):
        if not isinstance(other, EnumerationAsTypeTypeAnnotation):
            return False
        else:
            return that.enumeration is other.enumeration

    else:
        assert_never(that)

    raise AssertionError("Should not have gotten here")


PRIMITIVE_TYPE_MAP = {
    _types.PrimitiveType.BOOL: PrimitiveType.BOOL,
    _types.PrimitiveType.INT: PrimitiveType.INT,
    _types.PrimitiveType.FLOAT: PrimitiveType.FLOAT,
    _types.PrimitiveType.STR: PrimitiveType.STR,
    _types.PrimitiveType.BYTEARRAY: PrimitiveType.BYTEARRAY,
}


def _assignable(
    target_type: "TypeAnnotationUnion", value_type: "TypeAnnotationUnion"
) -> bool:
    """Check whether the value can be assigned to the target."""
    if isinstance(target_type, PrimitiveTypeAnnotation):
        if isinstance(value_type, PrimitiveTypeAnnotation):
            return target_type.a_type == value_type.a_type

        # NOTE (mristin, 2021-12-25):
        # We have to be careful about the constrained primitives,
        # since we can always assign a constrained primitive to a primitive, if they
        # primitive types match.
        elif isinstance(value_type, OurTypeAnnotation) and isinstance(
            value_type.our_type, _types.ConstrainedPrimitive
        ):
            return (
                target_type.a_type
                == PRIMITIVE_TYPE_MAP[value_type.our_type.constrainee]
            )

        else:
            return False

    elif isinstance(target_type, OurTypeAnnotation):
        if isinstance(target_type.our_type, _types.Enumeration):
            # NOTE (mristin, 2021-12-25):
            # The enumerations are invariant.
            return (
                isinstance(value_type, OurTypeAnnotation)
                and isinstance(value_type.our_type, _types.Enumeration)
                and target_type.our_type is value_type.our_type
            )

        elif isinstance(target_type.our_type, _types.ConstrainedPrimitive):
            # NOTE (mristin, 2021-12-25):
            # If it is a constrained primitive with no constraints, allow the assignment
            # if the target and the value match on the primitive type.
            if len(target_type.our_type.invariants) == 0 and isinstance(
                value_type, PrimitiveTypeAnnotation
            ):
                return (
                    PRIMITIVE_TYPE_MAP[target_type.our_type.constrainee]
                    == value_type.a_type
                )
            else:
                # NOTE (mristin, 2021-12-25):
                # We assume the assignments of constrained primitives to be co-variant.
                if (
                    isinstance(value_type, OurTypeAnnotation)
                    and isinstance(value_type.our_type, _types.ConstrainedPrimitive)
                    and target_type.our_type.constrainee
                    == value_type.our_type.constrainee
                ):
                    return (
                        target_type.our_type is value_type.our_type
                        or id(value_type.our_type)
                        in target_type.our_type.descendant_id_set
                    )

            return False

        elif isinstance(target_type.our_type, _types.Class):
            if not (
                isinstance(value_type, OurTypeAnnotation)
                and isinstance(value_type.our_type, _types.Class)
            ):
                return False

            # NOTE (mristin, 2021-12-25):
            # We assume the assignment to be co-variant. Either the target type and
            # the value type are equal *or* the value type is a descendant of the
            # target type.

            return target_type.our_type is value_type.our_type or (
                id(value_type.our_type) in target_type.our_type.descendant_id_set
            )

    elif isinstance(target_type, VerificationTypeAnnotation):
        if not isinstance(value_type, VerificationTypeAnnotation):
            return False
        else:
            return target_type.func is value_type.func

    elif isinstance(target_type, BuiltinFunctionTypeAnnotation):
        if not isinstance(value_type, BuiltinFunctionTypeAnnotation):
            return False
        else:
            return target_type.func is value_type.func

    elif isinstance(target_type, MethodTypeAnnotation):
        if not isinstance(value_type, MethodTypeAnnotation):
            return False
        else:
            return target_type.method is value_type.method

    elif isinstance(target_type, ListTypeAnnotation):
        if not isinstance(value_type, ListTypeAnnotation):
            return False
        else:
            # NOTE (mristin, 2021-12-25):
            # We assume the lists to be invariant. This is necessary for code generation
            # in implementation targets such as C++ and Golang.
            return _type_annotations_equal(target_type.items, value_type.items)

    elif isinstance(target_type, SetTypeAnnotation):
        if not isinstance(value_type, SetTypeAnnotation):
            return False
        else:
            # NOTE (mristin, 2021-12-25):
            # We assume the sets to be invariant. This is necessary for code generation
            # in implementation targets such as C++ and Golang.
            return _type_annotations_equal(target_type.items, value_type.items)

    elif isinstance(target_type, TupleTypeAnnotation):
        if not isinstance(value_type, TupleTypeAnnotation):
            return False
        else:
            # NOTE (mristin, 2026-09-02):
            # We assume the tuples to be invariant, analogous to the lists and sets
            # above.
            return len(target_type.items) == len(value_type.items) and all(
                _type_annotations_equal(target_item, value_item)
                for target_item, value_item in zip(target_type.items, value_type.items)
            )

    elif isinstance(target_type, OptionalTypeAnnotation):
        # NOTE (mristin, 2021-12-25):
        # We can always assign a non-optional to an optional.
        if not isinstance(value_type, OptionalTypeAnnotation):
            return _assignable(target_type=target_type.value, value_type=value_type)
        else:
            # NOTE (mristin, 2021-12-25):
            # We assume the optionals to be co-variant.
            return _assignable(
                target_type=target_type.value, value_type=value_type.value
            )

    elif isinstance(target_type, EnumerationAsTypeTypeAnnotation):
        raise NotImplementedError(
            "(mristin, 2022-02-04): Assigning enumeration-as-type to another "
            "enumeration-as-type is a very niche program logic. As we do not have "
            "a concrete example of such an assignment, we currently ignore this case "
            "in determining whether the assignment makes sense. When you have "
            "a concrete example, please revisit this part of the code."
        )

    else:
        assert_never(target_type)

    return False


for _types_primitive_type in _types.PrimitiveType:
    assert (
        _types_primitive_type in PRIMITIVE_TYPE_MAP
    ), f"All primitive types from _types covered, but: {_types_primitive_type=}"


def convert_type_annotation(
    type_annotation: _types.TypeAnnotationUnion,
) -> "TypeAnnotationUnion":
    """
    Convert from the :py:mod:`aas_core_codegen.intermediate._types`.

    We can not use the same type annotations as type inference uses a wider set of
    type annotations such as ``LENGTH`` in primitives or enumeration-as-type.
    """
    if isinstance(type_annotation, _types.PrimitiveTypeAnnotation):
        return PrimitiveTypeAnnotation(
            a_type=PRIMITIVE_TYPE_MAP[type_annotation.a_type]
        )

    elif isinstance(type_annotation, _types.OurTypeAnnotation):
        return OurTypeAnnotation(our_type=type_annotation.our_type)

    elif isinstance(type_annotation, _types.ListTypeAnnotation):
        return ListTypeAnnotation(items=convert_type_annotation(type_annotation.items))

    elif isinstance(type_annotation, _types.TupleTypeAnnotation):
        return TupleTypeAnnotation(
            items=[convert_type_annotation(item) for item in type_annotation.items]
        )

    elif isinstance(type_annotation, _types.OptionalTypeAnnotation):
        return OptionalTypeAnnotation(
            value=convert_type_annotation(type_annotation.value)
        )

    else:
        assert_never(type_annotation)

    raise AssertionError("Should not have gotten here")


class Environment(DBC):
    """
    Map names to type annotations for a given scope.

    We first search in the given scope and then iterate over the ancestor scopes.
    See, for example: https://craftinginterpreters.com/resolving-and-binding.html.

    The most outer, global, scope is parentless.
    """

    def __init__(self, parent: Optional["Environment"]) -> None:
        """Initialize with the given values."""
        self.parent = parent

    @property
    @abc.abstractmethod
    def mapping(self) -> Mapping[Identifier, "TypeAnnotationUnion"]:
        """Retrieve the underlying mapping."""
        raise NotImplementedError()

    def find(self, identifier: Identifier) -> Optional["TypeAnnotationUnion"]:
        """
        Search for the type annotation of the given ``identifier``.

        We search all the way to the most outer scope.
        """
        type_anno = self.mapping.get(identifier, None)
        if type_anno is not None:
            return type_anno

        if self.parent is not None:
            return self.parent.find(identifier)

        return None


class ImmutableEnvironment(Environment):
    """
    Map immutably names to type annotations for a given scope.
    """

    def __init__(
        self,
        mapping: Mapping[Identifier, "TypeAnnotationUnion"],
        parent: Optional["Environment"] = None,
    ) -> None:
        self._mapping = mapping

        Environment.__init__(self, parent)

    @property
    def mapping(self) -> Mapping[Identifier, "TypeAnnotationUnion"]:
        """Retrieve the underlying mapping."""
        return self._mapping


class MutableEnvironment(Environment):
    """
    Map names to type annotations for a given scope and allow mutations.
    """

    def __init__(self, parent: Optional["Environment"] = None) -> None:
        self._mapping = (
            dict()
        )  # type: MutableMapping[Identifier, "TypeAnnotationUnion"]

        Environment.__init__(self, parent)

    @property
    def mapping(self) -> Mapping[Identifier, "TypeAnnotationUnion"]:
        """Retrieve the underlying mapping."""
        return self._mapping

    def set(
        self, identifier: Identifier, type_annotation: "TypeAnnotationUnion"
    ) -> None:
        """Set the ``type_annotation`` for the given ``identifier``."""
        self._mapping[identifier] = type_annotation

    def remove(self, identifier: Identifier) -> None:
        """
        Remove the entry in the environment for the ``identifier``.

        For example, you need to do this if you have temporary scopes such as generator
        expressions where a long linked list of environments would be neither
        performant nor readable during the debugging.
        """
        del self._mapping[identifier]


class _Canonicalizer(parse_tree.RestrictedTransformer[str]):
    """Represent the nodes as canonical strings so that they can be used in look-ups."""

    #: Track of the canonical representations
    representation_map: Final[MutableMapping[parse_tree.Node, str]]

    def __init__(self) -> None:
        """Initialize with the given values."""
        self.representation_map = dict()

    @ensure(lambda self, node: node in self.representation_map)
    def transform(self, node: parse_tree.Node) -> str:
        return super().transform(node)

    @staticmethod
    def _needs_no_brackets(node: parse_tree.Node) -> bool:
        """
        Check if the representation needs brackets for unambiguity.

        While we could always put brackets, they harm readability in later debugging, so
        we try to make the representation as readable as possible.
        """
        return isinstance(
            node,
            (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.FunctionCall,
                parse_tree.Constant,
                parse_tree.JoinedStr,
                parse_tree.Any,
                parse_tree.All,
                parse_tree.Tuple,
            ),
        )

    def transform_member(self, node: parse_tree.Member) -> str:
        instance_repr = self.transform(node.instance)

        if _Canonicalizer._needs_no_brackets(node.instance):
            result = f"{instance_repr}.{node.name}"
        else:
            result = f"({instance_repr}).{node.name}"

        self.representation_map[node] = result
        return result

    def transform_index(self, node: parse_tree.Index) -> str:
        collection_repr = self.transform(node.collection)
        index_repr = self.transform(node.index)

        if _Canonicalizer._needs_no_brackets(node.collection):
            result = f"{collection_repr}[{index_repr}]"
        else:
            result = f"({collection_repr})[{index_repr}]"

        self.representation_map[node] = result
        return result

    def transform_comparison(self, node: parse_tree.Comparison) -> str:
        left = self.transform(node.left)
        if not _Canonicalizer._needs_no_brackets(node.left):
            left = f"({left})"

        right = self.transform(node.right)
        if not _Canonicalizer._needs_no_brackets(node.right):
            right = f"({right})"

        result = f"{left} {node.op.value} {right}"
        self.representation_map[node] = result
        return result

    def transform_is_in(self, node: parse_tree.IsIn) -> str:
        member = self.transform(node.member)
        if not _Canonicalizer._needs_no_brackets(node.member):
            member = f"({member})"

        container = self.transform(node.container)
        if not _Canonicalizer._needs_no_brackets(node.container):
            container = f"({container})"

        result = f"{member} in {container}"
        self.representation_map[node] = result
        return result

    def transform_implication(self, node: parse_tree.Implication) -> str:
        antecedent = self.transform(node.antecedent)
        if not _Canonicalizer._needs_no_brackets(node.antecedent):
            antecedent = f"({antecedent})"

        consequent = self.transform(node.consequent)
        if not _Canonicalizer._needs_no_brackets(node.consequent):
            consequent = f"({consequent})"

        result = f"{antecedent} ⇒ {consequent}"
        self.representation_map[node] = result
        return result

    def transform_method_call(self, node: parse_tree.MethodCall) -> str:
        member = self.transform(node.member)

        args = [self.transform(arg) for arg in node.args]

        args_joined = ", ".join(args)
        result = f"{member}({args_joined})"
        self.representation_map[node] = result
        return result

    def transform_function_call(self, node: parse_tree.FunctionCall) -> str:
        name = self.transform(node.name)

        args = [self.transform(arg) for arg in node.args]

        args_joined = ", ".join(args)
        result = f"{name}({args_joined})"
        self.representation_map[node] = result
        return result

    def transform_constant(self, node: parse_tree.Constant) -> str:
        result = repr(node.value)
        self.representation_map[node] = result
        return result

    def transform_tuple(self, node: parse_tree.Tuple) -> str:
        values = [self.transform(value) for value in node.values]

        values_joined = ", ".join(values)
        if len(values) == 1:
            result = f"({values_joined},)"
        else:
            result = f"({values_joined})"

        self.representation_map[node] = result
        return result

    def transform_is_none(self, node: parse_tree.IsNone) -> str:
        value = self.transform(node.value)
        if not _Canonicalizer._needs_no_brackets(node.value):
            value = f"({value})"

        result = f"{value} is None"
        self.representation_map[node] = result
        return result

    def transform_is_not_none(self, node: parse_tree.IsNotNone) -> str:
        value = self.transform(node.value)
        if not _Canonicalizer._needs_no_brackets(node.value):
            value = f"({value})"

        result = f"{value} is not None"
        self.representation_map[node] = result
        return result

    def transform_name(self, node: parse_tree.Name) -> str:
        result = node.identifier
        self.representation_map[node] = result
        return result

    def transform_not(self, node: parse_tree.Not) -> str:
        operand_repr = self.transform(node.operand)

        if not _Canonicalizer._needs_no_brackets(node):
            operand_repr = f"({operand_repr})"

        result = f"not {operand_repr}"
        self.representation_map[node] = result
        return result

    def transform_and(self, node: parse_tree.And) -> str:
        values = []  # type: List[str]

        for value_node in node.values:
            value = self.transform(value_node)
            if not _Canonicalizer._needs_no_brackets(value_node):
                value = f"({value})"

            values.append(value)

        result = " and ".join(values)
        self.representation_map[node] = result
        return result

    def transform_or(self, node: parse_tree.Or) -> str:
        values = []  # type: List[str]
        for value_node in node.values:
            value = self.transform(value_node)
            if not _Canonicalizer._needs_no_brackets(value_node):
                value = f"({value})"

            values.append(value)

        result = " or ".join(values)
        self.representation_map[node] = result
        return result

    def _transform_add_or_sub(self, node: Union[parse_tree.Add, parse_tree.Sub]) -> str:
        left_repr = self.transform(node.left)
        if not _Canonicalizer._needs_no_brackets(node.left):
            left_repr = f"({left_repr})"

        right_repr = self.transform(node.right)
        if not _Canonicalizer._needs_no_brackets(node.right):
            right_repr = f"({right_repr})"

        result: str
        if isinstance(node, parse_tree.Add):
            result = f"{left_repr} + {right_repr}"
        elif isinstance(node, parse_tree.Sub):
            result = f"{left_repr} - {right_repr}"
        else:
            assert_never(node)

        self.representation_map[node] = result
        return result

    def transform_add(self, node: parse_tree.Add) -> str:
        return self._transform_add_or_sub(node)

    def transform_sub(self, node: parse_tree.Sub) -> str:
        return self._transform_add_or_sub(node)

    def transform_formatted_value(self, node: parse_tree.FormattedValue) -> str:
        result = self.transform(node.value)
        self.representation_map[node] = result
        return result

    def transform_joined_str(self, node: parse_tree.JoinedStr) -> str:
        parts = []  # type: List[str]
        for value in node.values:
            if isinstance(value, str):
                parts.append(repr(value))
            elif isinstance(value, parse_tree.FormattedValue):
                transformed_value = self.transform(value)
                parts.append(f"{{{transformed_value}}}")
            else:
                assert_never(value)

        result = "".join(parts)
        self.representation_map[node] = result
        return result

    def transform_for_each(self, node: parse_tree.ForEach) -> str:
        variable = self.transform(node.variable)
        iteration = self.transform(node.iteration)
        if not _Canonicalizer._needs_no_brackets(node.iteration):
            iteration = f"({iteration})"

        result = f"for {variable} in {iteration}"
        self.representation_map[node] = result
        return result

    def transform_for_range(self, node: parse_tree.ForRange) -> str:
        variable = self.transform(node.variable)
        start = self.transform(node.start)
        end = self.transform(node.end)

        result = f"for {variable} in range({start}, {end})"
        self.representation_map[node] = result
        return result

    def _transform_any_or_all(self, node: Union[parse_tree.Any, parse_tree.All]) -> str:
        generator = self.transform(node.generator)

        condition = self.transform(node.condition)
        if not _Canonicalizer._needs_no_brackets(node.condition):
            condition = f"({condition})"

        result: str

        if isinstance(node, parse_tree.Any):
            result = f"any({condition} {generator})"
        elif isinstance(node, parse_tree.All):
            result = f"all({condition} {generator})"
        else:
            assert_never(node)

        self.representation_map[node] = result
        return result

    def transform_any(self, node: parse_tree.Any) -> str:
        return self._transform_any_or_all(node)

    def transform_all(self, node: parse_tree.All) -> str:
        return self._transform_any_or_all(node)

    def transform_assignment(self, node: parse_tree.Assignment) -> str:
        target = self.transform(node.target)
        if not _Canonicalizer._needs_no_brackets(node.target):
            target = f"({target})"

        # NOTE (mristin, 2022-06-17):
        # Nested assignments are not possible in Python, but who knows where our
        # intermediate representation will take us. Therefore, we handle this edge case
        # even though it seems nonsensical at the moment.
        value = self.transform(node.value)
        if isinstance(node.value, parse_tree.Assignment):
            value = f"({value})"

        result = f"{target} = {value}"

        self.representation_map[node] = result
        return result

    def transform_return(self, node: parse_tree.Return) -> str:
        if node.value is not None:
            value = self.transform(node.value)

            # NOTE (mristin, 2022-06-17):
            # Nested returns are not possible in Python, but who knows where our
            # intermediate representation will take us. Therefore, we handle
            # this edge case even though it seems nonsensical at the moment.
            if isinstance(node.value, parse_tree.Return):
                value = f"({value})"

            result = f"return {value}"
        else:
            result = "return"

        self.representation_map[node] = result
        return result


class _CountingMap:
    """Provide a map to track multiple counters."""

    def __init__(self) -> None:
        self._counts = dict()  # type: MutableMapping[str, int]

    def increment(self, key: str) -> None:
        """Increment the counter for the ``key``."""
        count = self._counts.get(key, None)
        if count is None:
            self._counts[key] = 1
        else:
            self._counts[key] = count + 1

    @ensure(lambda self, key, result: not result or self.count(key) > 0)
    @ensure(lambda self, key, result: result or self.count(key) == 0)
    def at_least_once(self, key: str) -> bool:
        """Return ``True`` if the ``key`` is tracked and the count is at least 1."""
        count = self.count(key)
        return count >= 1

    @ensure(lambda result: result >= 0)
    def count(self, key: str) -> int:
        """Return the number of stacked ``key``'s."""
        result = self._counts.get(key, None)
        return 0 if result is None else result

    # fmt: off
    @require(
        lambda self, key:
        self.at_least_once(key),
        "Can not decrement past 1"
    )
    # fmt: on
    def decrement(self, key: str) -> None:
        """Decrement the counter for the ``key``."""
        count = self._counts.get(key, None)

        if count is None or count == 0:
            raise AssertionError(f"Unexpected count == 0 for key {key!r}")
        elif count < 0:
            raise AssertionError(f"Unexpected count < 0 for key {key!r}")
        elif count == 1:
            del self._counts[key]
        else:
            self._counts[key] = count - 1


TypeAnnotationUnion = Union[
    PrimitiveTypeAnnotation,
    OurTypeAnnotation,
    VerificationTypeAnnotation,
    BuiltinFunctionTypeAnnotation,
    MethodTypeAnnotation,
    ListTypeAnnotation,
    SetTypeAnnotation,
    TupleTypeAnnotation,
    OptionalTypeAnnotation,
    EnumerationAsTypeTypeAnnotation,
]


class _Inferrer(parse_tree.RestrictedTransformer[Optional["TypeAnnotationUnion"]]):
    """
    Infer the types of the given parse tree.

    Since we also handle non-nullness, you need to pre-compute the canonical
    representation of the nodes that you want to infer the types for. To that end,
    use :class:`~CanonicalRepresenter`.
    """

    #: Track of the inferred types
    type_map: Final[MutableMapping[parse_tree.Node, "TypeAnnotationUnion"]]

    #: Errors encountered during the inference
    errors: Final[List[Error]]

    def __init__(
        self,
        environment: "Environment",
        representation_map: Mapping[parse_tree.Node, str],
    ) -> None:
        """Initialize with the given values."""
        # We need to create our own child environment so that we can introduce new
        # entries without affecting the variables from the outer scopes.
        self._environment = MutableEnvironment(parent=environment)

        self._representation_map = representation_map

        # NOTE (mristin, 2022-06-17):
        # We need to keep track of the expressions that can be assumed to be non-null.
        # This member is stateful! It will constantly change, depending on the position
        # of the iteration through the tree.
        #
        # We use canonical representation from ``representation_map`` to associate
        # non-null assumptions with the expressions.
        self._non_null = _CountingMap()

        self.type_map = dict()
        self.errors = []

    def _strip_optional_if_non_null(
        self, node: parse_tree.Node, type_annotation: "TypeAnnotationUnion"
    ) -> "TypeAnnotationUnion":
        """
        Remove ``Optional`` from the ``type_annotation`` if the ``node`` is non-null.

        The ``type_annotation`` refers to the type inferred for the ``node``.

        We keep track of the non-nullness over the iteration in :attr:`._non_null`.
        Using the canonical representation of the ``node``, we can check whether
        the type of the ``node`` is non-null.
        """
        if not isinstance(type_annotation, OptionalTypeAnnotation):
            return type_annotation

        canonical_repr = self._representation_map[node]
        if self._non_null.at_least_once(canonical_repr):
            return type_annotation.value

        return type_annotation

    @ensure(lambda self, result: not (result is None) or len(self.errors) > 0)
    def transform(self, node: parse_tree.Node) -> Optional["TypeAnnotationUnion"]:
        # NOTE (mristin, 2022-06-17):
        # We can not write the following as the pre-condition as it would break
        # behavioral subtyping since the parent class expects no pre-conditions.
        #
        # However, in this case, we check that the supplied dependency,
        # ``representation_map``, is correct.
        assert node in self._representation_map, (
            f"The node {parse_tree.dump(node)} at 0x{id(node):x} could not be found "
            f"in the supplied representation_map."
        )

        return super().transform(node)

    def transform_member(
        self, node: parse_tree.Member
    ) -> Optional["TypeAnnotationUnion"]:
        instance_type = self.transform(node.instance)

        if instance_type is None:
            return None

        if isinstance(instance_type, OurTypeAnnotation):
            if not isinstance(instance_type.our_type, _types.Class):
                self.errors.append(
                    Error(
                        node.instance.original_node,
                        f"Expected an instance type as our type to be a class, "
                        f"but got: {instance_type.our_type}",
                    )
                )
                return None

            cls = instance_type.our_type
            assert isinstance(cls, _types.Class)

            prop = cls.properties_by_name.get(node.name, None)
            if prop is not None:
                result = convert_type_annotation(prop.type_annotation)

                result = self._strip_optional_if_non_null(
                    node=node, type_annotation=result
                )
                self.type_map[node] = result
                return result

            method = cls.methods_by_name.get(node.name, None)
            if method is not None:
                result = MethodTypeAnnotation(method=method)

                result = self._strip_optional_if_non_null(
                    node=node, type_annotation=result
                )
                self.type_map[node] = result
                return result

            self.errors.append(
                Error(
                    node.original_node,
                    f"The member {node.name!r} could not be found "
                    f"in the class {cls.name!r}",
                )
            )

        elif isinstance(instance_type, EnumerationAsTypeTypeAnnotation):
            enumeration = instance_type.enumeration
            literal = enumeration.literals_by_name.get(node.name, None)
            if literal is not None:
                result = OurTypeAnnotation(our_type=enumeration)

                result = self._strip_optional_if_non_null(
                    node=node, type_annotation=result
                )
                self.type_map[node] = result
                return result

            self.errors.append(
                Error(
                    node.original_node,
                    f"The literal {node.name!r} could not be found "
                    f"in the enumeration {enumeration.name!r}",
                )
            )
        else:
            if isinstance(instance_type, OptionalTypeAnnotation):
                self.errors.append(
                    Error(
                        node.instance.original_node,
                        f"Expected an instance type to be a non-None, either "
                        f"an enumeration-as-type or our type, "
                        f"but inferred an Optional: {instance_type}",
                    )
                )
            else:
                self.errors.append(
                    Error(
                        node.instance.original_node,
                        f"Expected an instance type to be either "
                        f"an enumeration-as-type or our type, "
                        f"but inferred: {instance_type}",
                    )
                )
            return None

        return None

    def transform_index(
        self, node: parse_tree.Index
    ) -> Optional["TypeAnnotationUnion"]:
        collection_type = self.transform(node.collection)
        if collection_type is None:
            return None

        index_type = self.transform(node.index)
        if index_type is None:
            return None

        success = True

        if isinstance(collection_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.collection.original_node,
                    f"Expected the collection to be a non-None, "
                    f"but got: {collection_type}",
                )
            )
            success = False

        if isinstance(index_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.index.original_node,
                    f"Expected the index to be a non-None, " f"but got: {index_type}",
                )
            )
            success = False

        if not success:
            return None

        if isinstance(collection_type, TupleTypeAnnotation):
            # NOTE (mristin, 2026-09-02):
            # Tuples are heterogeneous, so, unlike lists, we can only infer the type
            # of the individual item if the index is given as a literal integer.
            if not (
                isinstance(node.index, parse_tree.Constant)
                and isinstance(node.index.value, int)
                and not isinstance(node.index.value, bool)
            ):
                self.errors.append(
                    Error(
                        node.index.original_node,
                        f"Expected a literal integer as the index into a tuple "
                        f"so that the type of the individual tuple item can be "
                        f"statically inferred, but got: {parse_tree.dump(node.index)}",
                    )
                )
                return None

            items = collection_type.items
            index_value = node.index.value
            if not (
                -len(items) <= index_value < len(items)
            ):  # pylint: disable=superfluous-parens
                self.errors.append(
                    Error(
                        node.index.original_node,
                        f"The index {index_value} is out of range "
                        f"for a tuple of {len(items)} item(s): {collection_type}",
                    )
                )
                return None

            result = items[index_value]
            self.type_map[node] = result
            return result

        if not isinstance(collection_type, ListTypeAnnotation):
            self.errors.append(
                Error(
                    node.collection.original_node,
                    f"Expected an index access on a list or a tuple, "
                    f"but got: {collection_type}",
                )
            )
            return None

        if not (
            isinstance(index_type, PrimitiveTypeAnnotation)
            and index_type.a_type in (PrimitiveType.INT, PrimitiveType.LENGTH)
        ):
            self.errors.append(
                Error(
                    node.collection.original_node,
                    f"Expected the index to be an integer, but got: {index_type}",
                )
            )
            return None

        result = collection_type.items
        self.type_map[node] = result
        return result

    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Optional["TypeAnnotationUnion"]:
        items = []  # type: List[TypeAnnotationUnion]
        failed = False
        for value in node.values:
            value_type = self.transform(value)
            if value_type is None:
                failed = True
            else:
                items.append(value_type)

        if failed:
            return None

        result = TupleTypeAnnotation(items=items)
        self.type_map[node] = result
        return result

    def transform_comparison(
        self, node: parse_tree.Comparison
    ) -> Optional["TypeAnnotationUnion"]:
        # Just recurse to fill ``type_map`` on ``left`` and ``right`` even though we
        # know the type in advance

        left_type = self.transform(node.left)
        if left_type is None:
            return None

        right_type = self.transform(node.right)
        if right_type is None:
            return None

        success = True

        if isinstance(left_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.left.original_node,
                    f"Expected the left operand to be a non-None, "
                    f"but got: {left_type}",
                )
            )
            success = False

        if isinstance(right_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.right.original_node,
                    f"Expected the right operand to be a non-None, "
                    f"but got: {right_type}",
                )
            )
            success = False

        if not success:
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_is_in(self, node: parse_tree.IsIn) -> Optional["TypeAnnotationUnion"]:
        # Just recurse to fill ``type_map`` on ``member`` and ``container`` even though
        # we know the type of the expression in advance.

        member_type = self.transform(node.member)
        container_type = self.transform(node.container)

        if member_type is None or container_type is None:
            return None

        # NOTE (mristin, 2023-06-09):
        # Check that both the member and the container are non-nullables. We already
        # had bugs related to this, see:
        # https://github.com/aas-core-works/aas-core-meta/pull/272
        success = True

        if isinstance(member_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.member.original_node,
                    f"Expected the member to be a non-None, but got: {member_type}",
                )
            )
            success = False

        if isinstance(container_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.container.original_node,
                    f"Expected the container to be a non-None, "
                    f"but got: {container_type}",
                )
            )
            success = False

        if not success:
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_implication(
        self, node: parse_tree.Implication
    ) -> Optional["TypeAnnotationUnion"]:
        # NOTE (mristin, 2022-06-17):
        # Just recurse to fill ``type_map`` on ``antecedent`` even though we know the
        # type in advance

        antecedent_type = self.transform(node.antecedent)
        if antecedent_type is None:
            return None

        success = True

        if isinstance(antecedent_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.antecedent.original_node,
                    f"Expected the antecedent to be a non-None, "
                    f"but got: {antecedent_type}",
                )
            )
            success = False

        # region Recurse into consequent while considering any non-nullness

        # NOTE (mristin, 2022-06-17):
        # We are very lax here and ignore the fact that calls to methods and functions
        # can actually alter the value assumed to be non-null, and actually violate
        # its non-nullness by setting it to null.
        #
        # This lack of conservatism works for now. If the bugs related to nullness
        # start to surface, we should re-think our approach here.

        with contextlib.ExitStack() as exit_stack:
            if isinstance(node.antecedent, parse_tree.IsNotNone):
                canonical_repr = self._representation_map[node.antecedent.value]
                self._non_null.increment(canonical_repr)

                exit_stack.callback(
                    lambda a_canonical_repr=canonical_repr: self._non_null.decrement(  # type: ignore
                        a_canonical_repr
                    )
                )

            elif isinstance(node.antecedent, parse_tree.And):
                for value in node.antecedent.values:
                    if isinstance(value, parse_tree.IsNotNone):
                        canonical_repr = self._representation_map[value.value]
                        self._non_null.increment(canonical_repr)

                        # fmt: off
                        exit_stack.callback(
                            lambda a_canonical_repr=canonical_repr:  # type: ignore
                            self._non_null.decrement(a_canonical_repr)
                        )
                        # fmt: on
            else:
                # NOTE (mristin, 2022-06-17):
                # We do not know how to infer any non-nullness in this case.
                pass

            success = (self.transform(node.consequent) is not None) and success

            if not success:
                return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_method_call(
        self, node: parse_tree.MethodCall
    ) -> Optional["TypeAnnotationUnion"]:
        # Simply recurse to track the type, but we don't care about the arguments
        failed = False
        for arg in node.args:
            arg_type = self.transform(arg)
            if arg_type is None:
                failed = True

        member_type = self.transform(node.member)

        if member_type is None:
            failed = True

        elif isinstance(member_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.member.original_node,
                    f"Expected the member to be a non-None, " f"but got: {member_type}",
                )
            )
            failed = True
        else:
            pass

        if failed:
            return None

        if not isinstance(member_type, MethodTypeAnnotation):
            self.errors.append(
                Error(
                    node.original_node,
                    f"Expected the member in a method call to be a method, "
                    f"but got: {member_type}",
                )
            )
            return None

        result: TypeAnnotationUnion

        if member_type.method.returns is None:
            result = PrimitiveTypeAnnotation(a_type=PrimitiveType.NONE)
        else:
            result = convert_type_annotation(member_type.method.returns)

        result = self._strip_optional_if_non_null(node=node, type_annotation=result)
        self.type_map[node] = result
        return result

    def transform_function_call(
        self, node: parse_tree.FunctionCall
    ) -> Optional["TypeAnnotationUnion"]:
        result = None  # type: Optional[TypeAnnotationUnion]
        failed = False

        func_type = self.transform(node.name)
        if func_type is None:
            failed = True
        else:
            # NOTE (mristin, 2021-12-26):
            # The verification functions use
            # :py:mod:`aas_core_codegen.intermediate._types` while the built-in
            # functions are a construct of
            # :py:mod:`aas_core_codegen.intermediate.type_inference`.

            if isinstance(func_type, VerificationTypeAnnotation):
                if func_type.func.returns is not None:
                    result = convert_type_annotation(func_type.func.returns)
                else:
                    result = PrimitiveTypeAnnotation(PrimitiveType.NONE)

            elif isinstance(func_type, BuiltinFunctionTypeAnnotation):
                if func_type.func.returns is not None:
                    result = func_type.func.returns
                else:
                    result = PrimitiveTypeAnnotation(PrimitiveType.NONE)

            elif isinstance(
                func_type,
                (
                    PrimitiveTypeAnnotation,
                    OurTypeAnnotation,
                    MethodTypeAnnotation,
                    ListTypeAnnotation,
                    SetTypeAnnotation,
                    TupleTypeAnnotation,
                    OptionalTypeAnnotation,
                    EnumerationAsTypeTypeAnnotation,
                ),
            ):
                self.errors.append(
                    Error(
                        node.name.original_node,
                        f"Expected the variable {node.name.identifier!r} to be "
                        f"a function, but got {func_type}",
                    )
                )

            else:
                assert_never(func_type)

        # NOTE (mristin, 2021-12-26):
        # Recurse to track the type of arguments. Even if we failed before, we want to
        # catch the errors in the arguments for better developer experience.
        #
        # Mind that we are sloppy here. Theoretically, we could check that arguments in
        # the call are assignable to the arguments in the function definition and catch
        # errors in the meta-model at this point. However, we prioritize other features
        # and leave this check unimplemented for now.

        for arg in node.args:
            arg_type = self.transform(arg)
            if arg_type is None:
                failed = True

        if failed:
            return None

        assert result is not None

        result = self._strip_optional_if_non_null(node=node, type_annotation=result)
        self.type_map[node] = result
        return result

    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Optional["TypeAnnotationUnion"]:
        result: TypeAnnotationUnion

        if isinstance(node.value, bool):
            result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        elif isinstance(node.value, int):
            result = PrimitiveTypeAnnotation(PrimitiveType.INT)
        elif isinstance(node.value, float):
            result = PrimitiveTypeAnnotation(PrimitiveType.FLOAT)
        elif isinstance(node.value, str):
            result = PrimitiveTypeAnnotation(PrimitiveType.STR)
        else:
            assert_never(node.value)

        self.type_map[node] = result
        return result

    def transform_is_none(
        self, node: parse_tree.IsNone
    ) -> Optional["TypeAnnotationUnion"]:
        value_type = self.transform(node.value)

        # NOTE (mristin):
        # Something went wrong if we could not infer the type of the ``value``.
        if value_type is None:
            return None

        if not isinstance(value_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.value.original_node,
                    f"Expected the value to be of an optional type for "
                    f"a nullness check (``is None``), "
                    f"but got {value_type}",
                )
            )
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_is_not_none(
        self, node: parse_tree.IsNotNone
    ) -> Optional["TypeAnnotationUnion"]:
        value_type = self.transform(node.value)

        # NOTE (mristin):
        # Something went wrong if we could not infer the type of the ``value``.
        if value_type is None:
            return None

        if not isinstance(value_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.value.original_node,
                    f"Expected the value to be of an optional type "
                    f"for a non-nullness check (``is not None``), "
                    f"but got {value_type}",
                )
            )
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_not(self, node: parse_tree.Not) -> Optional["TypeAnnotationUnion"]:
        # Just recurse to fill ``type_map`` on ``operand`` even though we know the type
        # in advance

        operand_type = self.transform(node.operand)

        if operand_type is None:
            return None

        if isinstance(operand_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.operand.original_node,
                    f"Expected the operand to be a non-None, "
                    f"but got: {operand_type}",
                )
            )
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_name(self, node: parse_tree.Name) -> Optional["TypeAnnotationUnion"]:
        type_in_env = self._environment.find(node.identifier)
        if type_in_env is None:
            self.errors.append(
                Error(
                    node.original_node,
                    f"We do not know how to infer the type of "
                    f"the variable with the identifier {node.identifier!r} from the "
                    f"given environment. Mind that we do not consider the module "
                    f"scope nor handle all built-in functions due to simplicity! If "
                    f"you believe this needs to work, please notify the developers.",
                )
            )
            return None

        result = type_in_env

        result = self._strip_optional_if_non_null(node=node, type_annotation=result)
        self.type_map[node] = result
        return result

    def transform_and(self, node: parse_tree.And) -> Optional["TypeAnnotationUnion"]:
        # NOTE (mristin, 2022-06-17):
        # We need to iterate and recurse into ``values`` to fill the ``type_map``.
        # In the process, we have to consider the non-nullness and how it applies
        # to the remainder of the conjunction.

        # NOTE (mristin, 2022-06-17):
        # We are very lax here and ignore the fact that calls to methods and functions
        # can actually alter the value assumed to be non-null, and actually violate
        # its non-nullness by setting it to null.
        #
        # This lack of conservatism works for now. If the bugs related to nullness
        # start to surface, we should re-think our approach here.

        success = True

        with contextlib.ExitStack() as exit_stack:
            for value_node in node.values:
                value_type = self.transform(value_node)
                if value_type is None:
                    return None

                if isinstance(value_type, OptionalTypeAnnotation):
                    self.errors.append(
                        Error(
                            value_node.original_node,
                            f"Expected the value to be a non-None, "
                            f"but got: {value_type}",
                        )
                    )
                    success = False

                if isinstance(value_node, parse_tree.IsNotNone):
                    canonical_repr = self._representation_map[value_node.value]
                    self._non_null.increment(canonical_repr)

                    # fmt: off
                    exit_stack.callback(
                        lambda a_canonical_repr=canonical_repr:  # type: ignore
                        self._non_null.decrement(a_canonical_repr)
                    )
                    # fmt: on

        if not success:
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_or(self, node: parse_tree.Or) -> Optional["TypeAnnotationUnion"]:
        # Just recurse to fill ``type_map`` on ``values`` even though we know the type
        # in advance

        success = True

        with contextlib.ExitStack() as exit_stack:
            for value_node in node.values:
                value_type = self.transform(value_node)
                if value_type is None:
                    return None

                if isinstance(value_type, OptionalTypeAnnotation):
                    self.errors.append(
                        Error(
                            value_node.original_node,
                            f"Expected the value to be a non-None, "
                            f"but got: {value_type}",
                        )
                    )
                    success = False

                if isinstance(value_node, parse_tree.IsNone):
                    canonical_repr = self._representation_map[value_node.value]
                    self._non_null.increment(canonical_repr)

                    # fmt: off
                    exit_stack.callback(
                        lambda a_canonical_repr=canonical_repr:  # type: ignore
                            self._non_null.decrement(
                            a_canonical_repr
                        )
                    )
                    # fmt: on

        if not success:
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    @staticmethod
    def _binary_operation_name_with_capital_the(
        node: Union[parse_tree.Add, parse_tree.Sub]
    ) -> str:
        if isinstance(node, parse_tree.Add):
            return "The addition"

        elif isinstance(node, parse_tree.Sub):
            return "The subtraction"

        else:
            assert_never(node)

    def _transform_add_or_sub(
        self, node: Union[parse_tree.Add, parse_tree.Sub]
    ) -> Optional["TypeAnnotationUnion"]:
        left_type = self.transform(node.left)
        if left_type is None:
            return None

        right_type = self.transform(node.right)
        if right_type is None:
            return None

        success = True

        if isinstance(left_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.left.original_node,
                    f"Expected the left operand to be a non-None, "
                    f"but got: {left_type}",
                )
            )
            success = False

        if isinstance(right_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.right.original_node,
                    f"Expected the right operand to be a non-None, "
                    f"but got: {right_type}",
                )
            )
            success = False

        if not success:
            return None

        if not (
            isinstance(left_type, PrimitiveTypeAnnotation)
            and left_type.a_type
            in (
                PrimitiveType.INT,
                PrimitiveType.FLOAT,
                PrimitiveType.LENGTH,
            )
        ):
            self.errors.append(
                Error(
                    node.left.original_node,
                    f"{_Inferrer._binary_operation_name_with_capital_the(node)} is "
                    f"only defined on integer and floating-point numbers, "
                    f"but got as a left operand: {left_type}",
                )
            )
            success = False

        if not (
            isinstance(right_type, PrimitiveTypeAnnotation)
            and right_type.a_type
            in (
                PrimitiveType.INT,
                PrimitiveType.FLOAT,
                PrimitiveType.LENGTH,
            )
        ):
            self.errors.append(
                Error(
                    node.right.original_node,
                    f"{_Inferrer._binary_operation_name_with_capital_the(node)} is "
                    f"only defined on integer and floating-point numbers, "
                    f"but got as a right operand: {right_type}",
                )
            )
            success = False

        if not success:
            return None

        assert isinstance(left_type, PrimitiveTypeAnnotation)
        assert isinstance(right_type, PrimitiveTypeAnnotation)

        # fmt: off
        if (
            (
                left_type.a_type is PrimitiveType.FLOAT
                and right_type.a_type is not PrimitiveType.FLOAT
            ) or (
                right_type.a_type is PrimitiveType.FLOAT
                and left_type.a_type is not PrimitiveType.FLOAT
            )
        ):
            # fmt: on
            self.errors.append(
                Error(
                    node.original_node,
                    f"You can not mix floating-point and integer numbers, "
                    f"but the left operand was: {left_type}; "
                    f"and the right operand was: {right_type}"
                )
            )
            success = False

        if not success:
            return None

        # fmt: off
        result_type: PrimitiveType
        if (
            (
                left_type.a_type is PrimitiveType.LENGTH
                and right_type.a_type in (PrimitiveType.INT, PrimitiveType.LENGTH)
            ) or (
                right_type.a_type is PrimitiveType.LENGTH
                and left_type.a_type in (PrimitiveType.INT, PrimitiveType.LENGTH)
            )
        ):
            result_type = PrimitiveType.LENGTH

        elif (
                left_type.a_type is PrimitiveType.INT
                and right_type.a_type is PrimitiveType.INT
        ):
            result_type = PrimitiveType.INT

        elif (
                left_type.a_type is PrimitiveType.FLOAT
                and right_type.a_type is PrimitiveType.FLOAT
        ):
            result_type = PrimitiveType.FLOAT
        else:
            raise AssertionError(
                f"Unhandled execution path: {left_type=}, {right_type=}"
            )
        # fmt: on

        result = PrimitiveTypeAnnotation(a_type=result_type)
        self.type_map[node] = result
        return result

    def transform_add(self, node: parse_tree.Add) -> Optional["TypeAnnotationUnion"]:
        return self._transform_add_or_sub(node)

    def transform_sub(self, node: parse_tree.Sub) -> Optional["TypeAnnotationUnion"]:
        return self._transform_add_or_sub(node)

    def transform_formatted_value(
        self, node: parse_tree.FormattedValue
    ) -> Optional["TypeAnnotationUnion"]:
        value_type = self.transform(node.value)
        if value_type is None:
            return None

        if isinstance(value_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.value.original_node,
                    f"Expected the value to be a non-None, " f"but got: {value_type}",
                )
            )
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.STR)
        self.type_map[node] = result
        return result

    def transform_joined_str(
        self, node: parse_tree.JoinedStr
    ) -> Optional["TypeAnnotationUnion"]:
        # Just recurse to fill ``type_map`` on ``values`` even though we know the type
        # in advance
        success = True
        for value in node.values:
            if isinstance(value, str):
                continue
            elif isinstance(value, parse_tree.FormattedValue):
                formatted_value_type = self.transform(value)
                if formatted_value_type is None:
                    success = False
            else:
                assert_never(value)

        if not success:
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.STR)
        self.type_map[node] = result
        return result

    def transform_for_each(
        self, node: parse_tree.ForEach
    ) -> Optional["TypeAnnotationUnion"]:
        variable_type_in_env = self._environment.find(node.variable.identifier)
        if variable_type_in_env is not None:
            self.errors.append(
                Error(
                    node.variable.original_node,
                    f"The variable {node.variable.identifier} "
                    f"has been already defined before",
                )
            )
            return None

        iter_type = self.transform(node.iteration)
        if iter_type is None:
            return None

        if isinstance(iter_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.iteration.original_node,
                    f"Expected the collection which we iterate over to be a non-None, "
                    f"but got: {iter_type}",
                )
            )
            return None

        if not isinstance(iter_type, ListTypeAnnotation):
            self.errors.append(
                Error(
                    node.iteration.original_node,
                    f"Expected an iteration over a list, but got: {iter_type}",
                )
            )
            return None

        loop_variable_type = iter_type.items

        self.type_map[node.variable] = loop_variable_type

        result = PrimitiveTypeAnnotation(PrimitiveType.NONE)
        self.type_map[node] = result
        return result

    def transform_for_range(
        self, node: parse_tree.ForRange
    ) -> Optional["TypeAnnotationUnion"]:
        variable_type_in_env = self._environment.find(node.variable.identifier)
        if variable_type_in_env is not None:
            self.errors.append(
                Error(
                    node.variable.original_node,
                    f"The variable {node.variable.identifier} "
                    f"has been already defined before",
                )
            )
            return None

        start_type = self.transform(node.start)
        if start_type is None:
            return None

        end_type = self.transform(node.end)
        if end_type is None:
            return None

        success = True

        if isinstance(start_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.start.original_node,
                    f"Expected the start to be a non-None, " f"but got: {start_type}",
                )
            )
            success = False

        if isinstance(end_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.end.original_node,
                    f"Expected the end to be a non-None, " f"but got: {end_type}",
                )
            )
            success = False

        if not success:
            return None

        if not (
            isinstance(start_type, PrimitiveTypeAnnotation)
            and start_type.a_type in (PrimitiveType.INT, PrimitiveType.LENGTH)
        ):
            self.errors.append(
                Error(
                    node.start.original_node,
                    f"Expected the start of a range to be an integer, "
                    f"but got: {start_type}",
                )
            )
            return None

        if not (
            isinstance(end_type, PrimitiveTypeAnnotation)
            and end_type.a_type in (PrimitiveType.INT, PrimitiveType.LENGTH)
        ):
            self.errors.append(
                Error(
                    node.end.original_node,
                    f"Expected the end of a range to be an integer, "
                    f"but got: {end_type}",
                )
            )
            return None

        # region Pick the larger integer type for the type of the loop variable
        assert isinstance(
            start_type, PrimitiveTypeAnnotation
        ) and start_type.a_type in (PrimitiveType.INT, PrimitiveType.LENGTH)
        assert isinstance(end_type, PrimitiveTypeAnnotation) and end_type.a_type in (
            PrimitiveType.INT,
            PrimitiveType.LENGTH,
        )

        loop_variable_type: PrimitiveTypeAnnotation
        if (
            start_type.a_type is PrimitiveType.LENGTH
            or end_type.a_type is PrimitiveType.LENGTH
        ):
            loop_variable_type = PrimitiveTypeAnnotation(a_type=PrimitiveType.LENGTH)
        else:
            assert (
                start_type.a_type is PrimitiveType.INT
                and end_type.a_type is PrimitiveType.INT
            )
            loop_variable_type = PrimitiveTypeAnnotation(a_type=PrimitiveType.INT)

        # endregion

        self.type_map[node.variable] = loop_variable_type

        result = PrimitiveTypeAnnotation(PrimitiveType.NONE)
        self.type_map[node] = result
        return result

    def _transform_any_or_all(
        self, node: Union[parse_tree.Any, parse_tree.All]
    ) -> Optional["TypeAnnotationUnion"]:
        a_type = self.transform(node.generator)
        if a_type is None:
            return None

        loop_variable_type = self.type_map[node.generator.variable]
        try:
            self._environment.set(
                identifier=node.generator.variable.identifier,
                type_annotation=loop_variable_type,
            )

            a_type = self.transform(node.condition)
            if a_type is None:
                return None

            if (
                not isinstance(a_type, PrimitiveTypeAnnotation)
                or a_type.a_type is not PrimitiveType.BOOL
            ):
                self.errors.append(
                    Error(
                        node.condition.original_node,
                        f"Expected the condition to be a boolean, "
                        f"but got: {a_type}",
                    )
                )
                return None

        finally:
            self._environment.remove(identifier=node.generator.variable.identifier)

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_any(self, node: parse_tree.Any) -> Optional["TypeAnnotationUnion"]:
        return self._transform_any_or_all(node)

    def transform_all(self, node: parse_tree.All) -> Optional["TypeAnnotationUnion"]:
        return self._transform_any_or_all(node)

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Optional["TypeAnnotationUnion"]:
        is_new_variable = False

        target_type: Optional[TypeAnnotationUnion]

        if isinstance(node.target, parse_tree.Name):
            target_type = self._environment.find(node.target.identifier)
            if target_type is None:
                is_new_variable = True
        else:
            target_type = self.transform(node.target)

        value_type = self.transform(node.value)

        if (not is_new_variable and target_type is None) or (value_type is None):
            return None

        if target_type is not None and not _assignable(
            target_type=target_type, value_type=value_type
        ):
            self.errors.append(
                Error(
                    node.original_node,
                    f"We inferred the target type of the assignment to "
                    f"be {target_type}, while the value type is inferred to "
                    f"be {value_type}. We do not know how to model this assignment.",
                )
            )
            return None

        if is_new_variable:
            assert isinstance(node.target, parse_tree.Name)

            self._environment.set(
                identifier=node.target.identifier, type_annotation=value_type
            )

        result = PrimitiveTypeAnnotation(PrimitiveType.NONE)
        self.type_map[node] = result
        return result

    def transform_return(
        self, node: parse_tree.Return
    ) -> Optional["TypeAnnotationUnion"]:
        # Just recurse to fill ``type_map`` on ``value`` even though we know the type
        # in advance
        if node.value is not None:
            success = self.transform(node.value) is not None
            if not success:
                return None

        # Treat ``return`` as a statement
        result = PrimitiveTypeAnnotation(PrimitiveType.NONE)
        self.type_map[node] = result
        return result


def populate_base_environment(symbol_table: _types.SymbolTable) -> Environment:
    """Create a basic mapping name 🠒 type annotation from the global scope.

    The global scope, in this context, refers to the level of symbol table.
    """
    # Build up the environment;
    # see https://craftinginterpreters.com/resolving-and-binding.html
    mapping: MutableMapping[Identifier, "TypeAnnotationUnion"] = {
        Identifier("len"): BuiltinFunctionTypeAnnotation(
            func=BuiltinFunction(
                name=Identifier("len"),
                returns=PrimitiveTypeAnnotation(PrimitiveType.LENGTH),
            )
        )
    }

    for constant in symbol_table.constants:
        if isinstance(constant, _types.ConstantPrimitive):
            mapping[constant.name] = PrimitiveTypeAnnotation(
                a_type=PRIMITIVE_TYPE_MAP[constant.a_type]
            )
        elif isinstance(constant, _types.ConstantSetOfPrimitives):
            mapping[constant.name] = SetTypeAnnotation(
                items=PrimitiveTypeAnnotation(PRIMITIVE_TYPE_MAP[constant.a_type])
            )
        elif isinstance(constant, _types.ConstantSetOfEnumerationLiterals):
            mapping[constant.name] = SetTypeAnnotation(
                items=OurTypeAnnotation(our_type=constant.enumeration)
            )
        else:
            assert_never(constant)

    for verification in symbol_table.verification_functions:
        assert verification.name not in mapping
        mapping[verification.name] = VerificationTypeAnnotation(func=verification)

    for our_type in symbol_table.our_types:
        if isinstance(our_type, _types.Enumeration):
            assert our_type.name not in mapping
            mapping[our_type.name] = EnumerationAsTypeTypeAnnotation(
                enumeration=our_type
            )

    return ImmutableEnvironment(mapping=mapping, parent=None)


class InferenceOfFunction:
    """Represent the result of type inference on a function body and arguments."""

    #: Environment inferred after processing a body of statements including
    #: the function arguments
    environment_with_args: Final[Environment]

    #: Map of body nodes to types
    type_map: Final[Mapping[parse_tree.Node, "TypeAnnotationUnion"]]

    def __init__(
        self,
        environment_with_args: Environment,
        type_map: Mapping[parse_tree.Node, "TypeAnnotationUnion"],
    ) -> None:
        """Initialize with the given values."""
        self.environment_with_args = environment_with_args
        self.type_map = type_map


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def infer_for_verification(
    verification: _types.TranspilableVerification, base_environment: Environment
) -> Tuple[Optional[InferenceOfFunction], Optional[Error]]:
    """Infer the types for the given function and map the body nodes to the types."""
    canonicalizer = _Canonicalizer()
    for node in verification.parsed.body:
        _ = canonicalizer.transform(node)

    environment = MutableEnvironment(parent=base_environment)

    for arg in verification.arguments:
        environment.set(
            identifier=arg.name,
            type_annotation=convert_type_annotation(arg.type_annotation),
        )

    type_inferrer = _Inferrer(
        environment=environment,
        representation_map=canonicalizer.representation_map,
    )

    for node in verification.parsed.body:
        _ = type_inferrer.transform(node)

    if len(type_inferrer.errors):
        return None, Error(
            verification.parsed.node,
            f"Failed to infer the types "
            f"in the verification function {verification.name!r}",
            type_inferrer.errors,
        )

    return (
        InferenceOfFunction(
            environment_with_args=environment, type_map=type_inferrer.type_map
        ),
        None,
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def infer_for_invariant(
    invariant: _types.Invariant, environment: Environment
) -> Tuple[Optional[Mapping[parse_tree.Node, "TypeAnnotationUnion"]], Optional[Error]]:
    """Infer the types of the nodes corresponding to the body of an invariant."""
    canonicalizer = _Canonicalizer()
    _ = canonicalizer.transform(invariant.body)

    type_inferrer = _Inferrer(
        environment=environment,
        representation_map=canonicalizer.representation_map,
    )

    _ = type_inferrer.transform(invariant.body)

    if len(type_inferrer.errors):
        return None, Error(
            invariant.parsed.node,
            "Failed to infer the types in the invariant",
            type_inferrer.errors,
        )

    return type_inferrer.type_map, None


assert_union_of_descendants_exhaustive(
    union=TypeAnnotationUnion, base_class=TypeAnnotation
)

TypeAnnotationExceptOptional = Union[
    PrimitiveTypeAnnotation,
    OurTypeAnnotation,
    VerificationTypeAnnotation,
    BuiltinFunctionTypeAnnotation,
    MethodTypeAnnotation,
    ListTypeAnnotation,
    SetTypeAnnotation,
    TupleTypeAnnotation,
    EnumerationAsTypeTypeAnnotation,
]
assert_union_without_excluded(
    original_union=TypeAnnotationUnion,
    subset_union=TypeAnnotationExceptOptional,
    excluded=[OptionalTypeAnnotation],
)

FunctionTypeAnnotationUnion = Union[
    VerificationTypeAnnotation, BuiltinFunctionTypeAnnotation
]
assert_union_of_descendants_exhaustive(
    union=FunctionTypeAnnotationUnion, base_class=FunctionTypeAnnotation
)

# NOTE (mristin, 2021-12-27):
# Mypy is not smart enough to work with ``get_args``, so we have to manually write it
# out.
FunctionTypeAnnotationUnionAsTuple = (
    VerificationTypeAnnotation,
    BuiltinFunctionTypeAnnotation,
)
assert FunctionTypeAnnotationUnionAsTuple == get_args(FunctionTypeAnnotationUnion)
