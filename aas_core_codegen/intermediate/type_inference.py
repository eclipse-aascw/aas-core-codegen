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
    Set,
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


class Downcast:
    """
    Represent a value whose type has been narrowed down by an ``isinstance`` guard.

    The implementation targets need to down-cast such values. The class or
    the named union of the value before the narrowing determines how the value
    is represented, and hence how it needs to be down-cast.
    """

    #: Type of the value before the narrowing, a class or a named union
    source: Final[OurTypeAnnotation]

    #: Class which the value has been narrowed down to
    target: Final[OurTypeAnnotation]

    def __init__(self, source: OurTypeAnnotation, target: OurTypeAnnotation) -> None:
        """Initialize with the given values."""
        self.source = source
        self.target = target

    def __str__(self) -> str:
        return f"{self.source} as {self.target}"


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


class JsonValueTypeAnnotation(AtomicTypeAnnotation):
    """
    Represent the type of an arbitrary, open JSON-able value.

    Since neither its shape nor any further operation on it can be determined
    statically, we treat it analogous to ``Unknown`` -- no member access,
    indexing or other operation is allowed on a value of this type.
    """

    def __str__(self) -> str:
        return "JSONValue"


class JsonArrayTypeAnnotation(AtomicTypeAnnotation):
    """Represent the type of an open, JSON-able array."""

    def __str__(self) -> str:
        return "JSONArray"


class JsonObjectTypeAnnotation(AtomicTypeAnnotation):
    """
    Represent the type of an open, JSON-object-shaped value.

    The value is always a :class:`JsonValueTypeAnnotation` and can not be
    customized, so we only track the ``key`` here.
    """

    def __init__(self, key: "TypeAnnotationUnion") -> None:
        """Initialize with the given values."""
        self.key = key

    def __str__(self) -> str:
        return f"JSONObject[{self.key}]"


class EnumerationAsTypeTypeAnnotation(TypeAnnotation):
    """
    Represent an enum class as a type.

    Note that this is not the enum as a type of that enum class, but
    rather the type-as-a-type. We write``Type[T]`` in Python to describe this.
    """

    # NOTE (mristin):
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

    elif isinstance(that, JsonValueTypeAnnotation):
        return isinstance(other, JsonValueTypeAnnotation)

    elif isinstance(that, JsonArrayTypeAnnotation):
        return isinstance(other, JsonArrayTypeAnnotation)

    elif isinstance(that, JsonObjectTypeAnnotation):
        if not isinstance(other, JsonObjectTypeAnnotation):
            return False
        else:
            return _type_annotations_equal(that.key, other.key)

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

        # NOTE (mristin):
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
            # NOTE (mristin):
            # The enumerations are invariant.
            return (
                isinstance(value_type, OurTypeAnnotation)
                and isinstance(value_type.our_type, _types.Enumeration)
                and target_type.our_type is value_type.our_type
            )

        elif isinstance(target_type.our_type, _types.ConstrainedPrimitive):
            # NOTE (mristin):
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
                # NOTE (mristin):
                # We assume the assignments of constrained primitives to be co-variant.
                if (
                    isinstance(value_type, OurTypeAnnotation)
                    and isinstance(value_type.our_type, _types.ConstrainedPrimitive)
                    and target_type.our_type.constrainee
                    == value_type.our_type.constrainee
                ):
                    return (
                        target_type.our_type is value_type.our_type
                        or _types.runtime_id(value_type.our_type)
                        in target_type.our_type.descendant_id_set
                    )

            return False

        elif isinstance(target_type.our_type, _types.Class):
            if not (
                isinstance(value_type, OurTypeAnnotation)
                and isinstance(value_type.our_type, _types.Class)
            ):
                return False

            # NOTE (mristin):
            # We assume the assignment to be co-variant. Either the target type and
            # the value type are equal *or* the value type is a descendant of the
            # target type.

            return target_type.our_type is value_type.our_type or (
                _types.runtime_id(value_type.our_type)
                in target_type.our_type.descendant_id_set
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
            # NOTE (mristin):
            # We assume the lists to be invariant. This is necessary for code generation
            # in implementation targets such as C++ and Golang.
            return _type_annotations_equal(target_type.items, value_type.items)

    elif isinstance(target_type, SetTypeAnnotation):
        if not isinstance(value_type, SetTypeAnnotation):
            return False
        else:
            # NOTE (mristin):
            # We assume the sets to be invariant. This is necessary for code generation
            # in implementation targets such as C++ and Golang.
            return _type_annotations_equal(target_type.items, value_type.items)

    elif isinstance(target_type, TupleTypeAnnotation):
        if not isinstance(value_type, TupleTypeAnnotation):
            return False
        else:
            # NOTE (mristin):
            # We assume the tuples to be invariant, analogous to the lists and sets
            # above.
            return len(target_type.items) == len(value_type.items) and all(
                _type_annotations_equal(target_item, value_item)
                for target_item, value_item in zip(target_type.items, value_type.items)
            )

    elif isinstance(target_type, OptionalTypeAnnotation):
        # NOTE (mristin):
        # We can always assign a non-optional to an optional.
        if not isinstance(value_type, OptionalTypeAnnotation):
            return _assignable(target_type=target_type.value, value_type=value_type)
        else:
            # NOTE (mristin):
            # We assume the optionals to be co-variant.
            return _assignable(
                target_type=target_type.value, value_type=value_type.value
            )

    elif isinstance(target_type, JsonValueTypeAnnotation):
        # NOTE (mristin):
        # ``JSONValue`` denotes an arbitrary, open JSON-able value, so any
        # JSON-able value -- a JSON-able primitive or a JSON-able collection --
        # can be assigned to it.
        #
        # We deliberately exclude ``PrimitiveType.INT`` here. JSON itself has
        # no separate integer type, only a single "number" type, which we
        # model as ``PrimitiveType.FLOAT``. Accepting an ``int`` here would be
        # ambiguous -- it is unclear whether it should be rendered as, say,
        # ``1`` or ``1.0`` -- so we require the value to already be a
        # ``float`` (or another JSON-able type) before it can flow into
        # a ``JSONValue``.
        return isinstance(
            value_type,
            (
                JsonValueTypeAnnotation,
                JsonArrayTypeAnnotation,
                JsonObjectTypeAnnotation,
            ),
        ) or (
            isinstance(value_type, PrimitiveTypeAnnotation)
            and value_type.a_type
            in (
                PrimitiveType.BOOL,
                PrimitiveType.FLOAT,
                PrimitiveType.STR,
            )
        )

    elif isinstance(target_type, JsonArrayTypeAnnotation):
        return isinstance(value_type, JsonArrayTypeAnnotation)

    elif isinstance(target_type, JsonObjectTypeAnnotation):
        if not isinstance(value_type, JsonObjectTypeAnnotation):
            return False
        else:
            return _type_annotations_equal(target_type.key, value_type.key)

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

    elif isinstance(type_annotation, _types.JsonValueTypeAnnotation):
        return JsonValueTypeAnnotation()

    elif isinstance(type_annotation, _types.JsonArrayTypeAnnotation):
        return JsonArrayTypeAnnotation()

    elif isinstance(type_annotation, _types.JsonObjectTypeAnnotation):
        return JsonObjectTypeAnnotation(
            key=convert_type_annotation(type_annotation.key)
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

    def find_our_type(self, identifier: Identifier) -> Optional[_types.OurType]:
        """
        Search for our type with the given ``identifier``.

        Unlike :py:meth:`find`, this method resolves the names which refer to our
        types, and not to values. For example, we need to resolve the classes
        in ``isinstance(something, Some_class)``.

        We search all the way to the most outer scope.
        """
        if self.parent is not None:
            return self.parent.find_our_type(identifier)

        return None


class ImmutableEnvironment(Environment):
    """
    Map immutably names to type annotations for a given scope.

    Optionally, the environment also resolves the names of our types. This is
    usually the case only for the most outer, global scope.
    """

    def __init__(
        self,
        mapping: Mapping[Identifier, "TypeAnnotationUnion"],
        parent: Optional["Environment"] = None,
        our_types_by_name: Optional[Mapping[Identifier, _types.OurType]] = None,
    ) -> None:
        self._mapping = mapping
        self._our_types_by_name = our_types_by_name

        Environment.__init__(self, parent)

    @property
    def mapping(self) -> Mapping[Identifier, "TypeAnnotationUnion"]:
        """Retrieve the underlying mapping."""
        return self._mapping

    def find_our_type(self, identifier: Identifier) -> Optional[_types.OurType]:
        if self._our_types_by_name is not None:
            our_type = self._our_types_by_name.get(identifier, None)
            if our_type is not None:
                return our_type

        return Environment.find_our_type(self, identifier)


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

    @staticmethod
    def index_representation(
        collection: parse_tree.Node, collection_repr: str, index_repr: str
    ) -> str:
        """
        Render the canonical representation of ``collection[index]``.

        This is a static method so that the callers which know the parts of an index,
        but have no index node at hand, can render exactly the same representation.
        """
        if _Canonicalizer._needs_no_brackets(collection):
            return f"{collection_repr}[{index_repr}]"

        return f"({collection_repr})[{index_repr}]"

    def transform_index(self, node: parse_tree.Index) -> str:
        collection_repr = self.transform(node.collection)
        index_repr = self.transform(node.index)

        result = _Canonicalizer.index_representation(
            collection=node.collection,
            collection_repr=collection_repr,
            index_repr=index_repr,
        )

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

    def transform_is_instance(self, node: parse_tree.IsInstance) -> str:
        value = self.transform(node.value)

        classes = [self.transform(cls) for cls in node.classes]

        if len(classes) == 1:
            result = f"isinstance({value}, {classes[0]})"
        else:
            classes_joined = ", ".join(classes)
            result = f"isinstance({value}, ({classes_joined}))"

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

        # NOTE (mristin):
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

            # NOTE (mristin):
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

    def transform_switch(self, node: parse_tree.Switch) -> str:
        parts = [f"switch {self.transform(node.subject)}:"]  # type: List[str]

        for case in node.cases:
            labels = ", ".join(self.transform(label) for label in case.labels)
            stmts = "; ".join(self.transform(stmt) for stmt in case.body)
            parts.append(f"case {labels}: {{{stmts}}}")

        if node.default is not None:
            stmts = "; ".join(self.transform(stmt) for stmt in node.default)
            parts.append(f"default: {{{stmts}}}")

        result = " ".join(parts)

        self.representation_map[node] = result
        return result


#: Map a comparator to the comparator which says the same about the flipped operands
_FLIPPED_COMPARATOR = {
    parse_tree.Comparator.LT: parse_tree.Comparator.GT,
    parse_tree.Comparator.LE: parse_tree.Comparator.GE,
    parse_tree.Comparator.GT: parse_tree.Comparator.LT,
    parse_tree.Comparator.GE: parse_tree.Comparator.LE,
    parse_tree.Comparator.EQ: parse_tree.Comparator.EQ,
    parse_tree.Comparator.NE: parse_tree.Comparator.NE,
}  # type: Mapping[parse_tree.Comparator, parse_tree.Comparator]


def _is_int_literal(node: parse_tree.Node) -> bool:
    """Check whether the ``node`` is a literal integer."""
    return (
        isinstance(node, parse_tree.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    )


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
    JsonValueTypeAnnotation,
    JsonArrayTypeAnnotation,
    JsonObjectTypeAnnotation,
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

    #: Track of the nodes whose type has been narrowed down to a class by
    #: an ``isinstance`` guard. The implementation targets need to down-cast
    #: the value of these nodes to the given class.
    downcast_map: Final[MutableMapping[parse_tree.Node, Downcast]]

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

        # NOTE (mristin):
        # We need to keep track of the expressions that can be assumed to be non-null.
        # This member is stateful! It will constantly change, depending on the position
        # of the iteration through the tree.
        #
        # We use canonical representation from ``representation_map`` to associate
        # non-null assumptions with the expressions.
        self._non_null = _CountingMap()

        # NOTE (mristin):
        # We analogously keep track of how long the JSON-able arrays are known to be,
        # as asserted by the guards such as ``len(self.values) > 0``. The lengths are
        # stacked, so that we can pop them as the iteration leaves the guarded scope.
        self._min_lengths = dict()  # type: MutableMapping[str, List[int]]

        # NOTE (mristin):
        # We analogously keep track of the classes to which the values have been
        # narrowed down by the ``isinstance`` guards. The narrowings are stacked, so
        # that we can pop them as the iteration leaves the guarded scope. The last
        # narrowing is always the most specific one, as we allow ``isinstance`` only
        # on strict descendants of the value's type.
        self._narrowings = dict()  # type: MutableMapping[str, List[OurTypeAnnotation]]

        # NOTE (mristin):
        # We keep track of the names of the variables defined in the nested scopes,
        # *i.e.*, the switch branches, which have been already closed. The variables
        # themselves are not visible anymore, as their environments have been
        # discarded. We keep only their names to refuse the re-declarations of
        # the same names in the enclosing scope. See
        # :py:meth:`_transform_in_new_scope` for more details.
        #
        # Each entry of the stack belongs to a scope, and the top of the stack
        # belongs to the current scope.
        self._names_of_variables_in_closed_scopes = [
            set()
        ]  # type: List[Set[Identifier]]

        self.type_map = dict()
        self.downcast_map = dict()
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

    def _index_within_asserted_length(self, node: parse_tree.Index) -> bool:
        """
        Check whether a guard asserted the position of the ``node`` to be there.

        We keep track of the asserted lengths over the iteration
        in :attr:`._min_lengths`, see :py:meth:`._assume_guard`.
        """
        if not _is_int_literal(node.index):
            return False

        assert isinstance(node.index, parse_tree.Constant)
        assert isinstance(node.index.value, int)

        lengths = self._min_lengths.get(self._representation_map[node.collection], None)
        if lengths is None or len(lengths) == 0:
            return False

        min_length = max(lengths)

        # NOTE (mristin):
        # A negative index is resolved from the back of the array, so both ends
        # of the range are bounded by the asserted length.
        return -min_length <= node.index.value < min_length

    def _is_length_call(self, node: parse_tree.Node) -> bool:
        """Check whether the ``node`` is a call to the built-in ``len``."""
        if not (isinstance(node, parse_tree.FunctionCall) and len(node.args) == 1):
            return False

        func_type = self.type_map.get(node.name, None)

        return (
            isinstance(func_type, BuiltinFunctionTypeAnnotation)
            and func_type.func.name == "len"
        )

    def _asserted_min_length(self, node: parse_tree.Node) -> Optional[Tuple[str, int]]:
        """
        Determine which JSON-able array the ``node`` asserts to be how long.

        We understand the length checks such as ``len(self.values) > 0`` and
        ``1 <= len(self.values)``, and return the canonical representation of
        the array together with the asserted length.
        """
        if not isinstance(node, parse_tree.Comparison):
            return None

        length_call = None  # type: Optional[parse_tree.FunctionCall]
        literal = None  # type: Optional[int]
        op = node.op

        if self._is_length_call(node.left) and _is_int_literal(node.right):
            assert isinstance(node.left, parse_tree.FunctionCall)
            assert isinstance(node.right, parse_tree.Constant)
            assert isinstance(node.right.value, int)

            length_call, literal = node.left, node.right.value
        elif _is_int_literal(node.left) and self._is_length_call(node.right):
            assert isinstance(node.left, parse_tree.Constant)
            assert isinstance(node.left.value, int)
            assert isinstance(node.right, parse_tree.FunctionCall)

            length_call, literal = node.right, node.left.value

            # NOTE (mristin):
            # ``1 < len(self.values)`` says the same as ``len(self.values) > 1``.
            op = _FLIPPED_COMPARATOR[op]
        else:
            return None

        assert length_call is not None
        assert literal is not None

        if op is parse_tree.Comparator.GT:
            min_length = literal + 1
        elif op is parse_tree.Comparator.GE:
            min_length = literal
        else:
            return None

        if min_length <= 0:
            return None

        collection = length_call.args[0]
        if not isinstance(
            beneath_optional(self.type_map[collection]), JsonArrayTypeAnnotation
        ):
            return None

        return self._representation_map[collection], min_length

    def _assume_narrowing(
        self, node: parse_tree.IsInstance, exit_stack: contextlib.ExitStack
    ) -> None:
        """
        Assume that the value of the ``node`` is an instance of its class.

        The assumption is undone as the ``exit_stack`` unwinds.

        Mind that the ``node`` must have been already transformed and its types
        successfully inferred, as we need to resolve the class.
        """
        if len(node.classes) != 1:
            return

        cls = self._environment.find_our_type(node.classes[0].identifier)
        assert isinstance(cls, _types.ClassUnionAsTuple), (
            f"Expected the class of a successfully inferred isinstance "
            f"to be resolved, but got: {cls}"
        )

        canonical_repr = self._representation_map[node.value]

        narrowings = self._narrowings.setdefault(canonical_repr, [])
        narrowings.append(OurTypeAnnotation(our_type=cls))

        # fmt: off
        exit_stack.callback(
            lambda a_narrowings=narrowings: a_narrowings.pop()  # type: ignore
        )
        # fmt: on

    def _assume_guard(
        self, node: parse_tree.Node, exit_stack: contextlib.ExitStack
    ) -> None:
        """
        Assume that the ``node`` holds, and note down what it tells us about the rest.

        The assumption is undone as the ``exit_stack`` unwinds, so that it holds only
        for the expressions which the guard actually guards.

        Mind that the ``node`` must have been already transformed, as we need its type
        and its canonical representation.
        """
        if isinstance(node, parse_tree.IsNotNone):
            canonical_repr = self._representation_map[node.value]
            self._non_null.increment(canonical_repr)

            # fmt: off
            exit_stack.callback(
                lambda a_canonical_repr=canonical_repr:  # type: ignore
                self._non_null.decrement(a_canonical_repr)
            )
            # fmt: on
            return

        # NOTE (mristin):
        # ``key in obj`` tells us that ``obj[key]`` is there. A JSON-able object is
        # the only container whose membership is a question about the index.
        if isinstance(node, parse_tree.IsIn) and isinstance(
            beneath_optional(self.type_map[node.container]), JsonObjectTypeAnnotation
        ):
            canonical_repr = _Canonicalizer.index_representation(
                collection=node.container,
                collection_repr=self._representation_map[node.container],
                index_repr=self._representation_map[node.member],
            )
            self._non_null.increment(canonical_repr)

            # fmt: off
            exit_stack.callback(
                lambda a_canonical_repr=canonical_repr:  # type: ignore
                self._non_null.decrement(a_canonical_repr)
            )
            # fmt: on
            return

        # NOTE (mristin):
        # ``isinstance(x, C)`` tells us that ``x`` is an instance of ``C``. We can not
        # narrow on multiple classes, ``isinstance(x, (A, B))``, as the value could be
        # an instance of either of them.
        if isinstance(node, parse_tree.IsInstance):
            self._assume_narrowing(node, exit_stack)
            return

        # NOTE (mristin):
        # ``len(arr) > 0`` tells us that ``arr[0]`` and ``arr[-1]`` are there, and
        # so on for the longer arrays.
        asserted = self._asserted_min_length(node)
        if asserted is not None:
            collection_repr, min_length = asserted

            lengths = self._min_lengths.setdefault(collection_repr, [])
            lengths.append(min_length)

            # fmt: off
            exit_stack.callback(
                lambda a_lengths=lengths: a_lengths.pop()  # type: ignore
            )
            # fmt: on

    @ensure(lambda self, result: not (result is None) or len(self.errors) > 0)
    def transform(self, node: parse_tree.Node) -> Optional["TypeAnnotationUnion"]:
        # NOTE (mristin):
        # We can not write the following as the pre-condition as it would break
        # behavioral subtyping since the parent class expects no pre-conditions.
        #
        # However, in this case, we check that the supplied dependency,
        # ``representation_map``, is correct.
        assert node in self._representation_map, (
            f"The node {parse_tree.dump(node)} at 0x{id(node):x} could not be found "
            f"in the supplied representation_map."
        )

        result = super().transform(node)

        # NOTE (mristin):
        # We narrow the type of the value if an ``isinstance`` guard applies to it.
        # Analogous to non-nullness, we are lax here, and ignore the fact that
        # calls to methods and functions can alter the value in-between.
        if isinstance(result, OurTypeAnnotation):
            narrowings = self._narrowings.get(self._representation_map[node], None)
            if narrowings is not None and len(narrowings) > 0:
                self.downcast_map[node] = Downcast(source=result, target=narrowings[-1])

                result = narrowings[-1]
                self.type_map[node] = result

        return result

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
            # NOTE (mristin):
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

        if isinstance(collection_type, JsonArrayTypeAnnotation):
            if not (
                isinstance(index_type, PrimitiveTypeAnnotation)
                and index_type.a_type in (PrimitiveType.INT, PrimitiveType.LENGTH)
            ):
                self.errors.append(
                    Error(
                        node.index.original_node,
                        f"Expected the index into a JSONArray to be an integer, "
                        f"but got: {index_type}",
                    )
                )
                return None

            # NOTE (mristin):
            # The position might lie outside the array, so the item is optional
            # unless a guard, such as ``len(self.values) > 0``, asserted the array
            # to be long enough.
            if self._index_within_asserted_length(node):
                result = JsonValueTypeAnnotation()
            else:
                result = OptionalTypeAnnotation(JsonValueTypeAnnotation())

            self.type_map[node] = result
            return result

        if isinstance(collection_type, JsonObjectTypeAnnotation):
            if try_primitive_type(index_type) != PrimitiveType.STR:
                self.errors.append(
                    Error(
                        node.index.original_node,
                        f"Expected the index into a JSONObject to be a string "
                        f"(or a class constraining ``str``), but got: {index_type}",
                    )
                )
                return None

            # NOTE (mristin):
            # The key might be missing in the object, so the value is optional
            # unless a guard, such as ``"type" in self.mapping``, asserted the key
            # to be there.
            result = OptionalTypeAnnotation(JsonValueTypeAnnotation())
            result = self._strip_optional_if_non_null(node=node, type_annotation=result)
            self.type_map[node] = result
            return result

        if isinstance(collection_type, JsonValueTypeAnnotation):
            self.errors.append(
                Error(
                    node.collection.original_node,
                    "JSONValue represents an arbitrary, open JSON-able value "
                    "whose shape can not be determined statically, so we treat "
                    "it analogous to Unknown -- indexing into it is not "
                    "supported",
                )
            )
            return None

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

        # NOTE (mristin):
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

    def transform_is_instance(
        self, node: parse_tree.IsInstance
    ) -> Optional["TypeAnnotationUnion"]:
        value_type = self.transform(node.value)

        if value_type is None:
            return None

        # NOTE (mristin):
        # We refuse the optional values since ``isinstance`` on ``None`` would
        # panic or be undefined behavior in some implementation targets. Please
        # check for non-nullness first, and only then check the class.
        if isinstance(value_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.value.original_node,
                    f"Expected the value to be a non-None for ``isinstance``, "
                    f"but got: {value_type}. Please check for ``is not None`` first.",
                )
            )
            return None

        if not (
            isinstance(value_type, OurTypeAnnotation)
            and isinstance(
                value_type.our_type,
                (_types.AbstractClass, _types.ConcreteClass, _types.NamedUnion),
            )
        ):
            self.errors.append(
                Error(
                    node.value.original_node,
                    f"Expected the value to be an instance of a class or "
                    f"of a named union for ``isinstance``, but got: {value_type}",
                )
            )
            return None

        value_our_type = value_type.our_type

        success = True

        for cls_name in node.classes:
            cls = self._environment.find_our_type(cls_name.identifier)

            if cls is None:
                self.errors.append(
                    Error(
                        cls_name.original_node,
                        f"The class {cls_name.identifier!r} given to ``isinstance`` "
                        f"could not be found",
                    )
                )
                success = False
                continue

            if not isinstance(cls, _types.ClassUnionAsTuple):
                self.errors.append(
                    Error(
                        cls_name.original_node,
                        f"Expected only classes in ``isinstance``, "
                        f"but got {cls_name.identifier!r}: {cls}",
                    )
                )
                success = False
                continue

            if isinstance(value_our_type, _types.NamedUnion):
                if not any(cls.is_subclass_of(root) for root in value_our_type.roots):
                    roots_joined = ", ".join(root.name for root in value_our_type.roots)

                    self.errors.append(
                        Error(
                            cls_name.original_node,
                            f"Expected the class {cls.name!r} "
                            f"to be a root of the named union "
                            f"{value_our_type.name!r} of the value "
                            f"in ``isinstance``, or a descendant of a root, "
                            f"but it is not. The roots are: {roots_joined}",
                        )
                    )
                    success = False

            elif isinstance(value_our_type, _types.ClassUnionAsTuple):
                if _types.runtime_id(cls) not in value_our_type.descendant_id_set:
                    is_ancestor_or_same = (
                        cls is value_our_type
                        or _types.runtime_id(value_our_type) in cls.descendant_id_set
                    )

                    if is_ancestor_or_same:
                        reason = "so the check always holds"
                    else:
                        reason = "so the check never holds"

                    self.errors.append(
                        Error(
                            cls_name.original_node,
                            f"Expected the class {cls.name!r} to be a strict "
                            f"descendant of the class {value_our_type.name!r} "
                            f"of the value in ``isinstance``, but it is not, "
                            f"{reason}",
                        )
                    )
                    success = False

            else:
                assert_never(value_our_type)

        if not success:
            return None

        result = PrimitiveTypeAnnotation(PrimitiveType.BOOL)
        self.type_map[node] = result
        return result

    def transform_implication(
        self, node: parse_tree.Implication
    ) -> Optional["TypeAnnotationUnion"]:
        # NOTE (mristin):
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

        # NOTE (mristin):
        # We are very lax here and ignore the fact that calls to methods and functions
        # can actually alter the value assumed to be non-null, and actually violate
        # its non-nullness by setting it to null.
        #
        # This lack of conservatism works for now. If the bugs related to nullness
        # start to surface, we should re-think our approach here.

        with contextlib.ExitStack() as exit_stack:
            if isinstance(node.antecedent, parse_tree.And):
                for value in node.antecedent.values:
                    self._assume_guard(value, exit_stack)
            else:
                self._assume_guard(node.antecedent, exit_stack)

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
            # NOTE (mristin):
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
                    JsonValueTypeAnnotation,
                    JsonArrayTypeAnnotation,
                    JsonObjectTypeAnnotation,
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

        # NOTE (mristin):
        # Recurse to track the type of arguments. Even if we failed before, we want to
        # catch the errors in the arguments for better developer experience.
        #
        # Mind that we are sloppy here. Theoretically, we could check that arguments in
        # the call are assignable to the arguments in the function definition and catch
        # errors in the meta-model at this point. However, we prioritize other features
        # and leave this check unimplemented for now.

        arg_types = []  # type: List[Optional[TypeAnnotationUnion]]
        for arg in node.args:
            arg_type = self.transform(arg)
            if arg_type is None:
                failed = True

            arg_types.append(arg_type)

        if failed:
            return None

        # NOTE (mristin):
        # The length of a JSON-able value is not a question we can answer: its
        # shape is known only at run time, and a boolean and a number have no
        # length at all. This mirrors :py:meth:`_Inferrer.transform_index`,
        # which refuses to index into a JSON-able value for the very same
        # reason. A JSON-able array and a JSON-able object, in contrast, are
        # known to be a sequence and a mapping, respectively.
        if (
            isinstance(func_type, BuiltinFunctionTypeAnnotation)
            and func_type.func.name == "len"
            and len(arg_types) == 1
        ):
            arg_type = arg_types[0]
            assert arg_type is not None

            if isinstance(beneath_optional(arg_type), JsonValueTypeAnnotation):
                self.errors.append(
                    Error(
                        node.args[0].original_node,
                        "JSONValue represents an arbitrary, open JSON-able value "
                        "whose shape can not be determined statically, so we treat "
                        "it analogous to Unknown -- computing its length is not "
                        "supported. Only a JSONArray and a JSONObject have "
                        "a length which we can compute.",
                    )
                )
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

    def _nullness_check_over_json_index_is_refused(
        self, value: parse_tree.Node, check: str
    ) -> bool:
        """
        Record an error if the ``check`` is applied to an index into a JSON-able value.

        The ``value`` must have been already transformed, as we need the type of
        its collection.
        """
        if not isinstance(value, parse_tree.Index):
            return False

        if not isinstance(
            beneath_optional(self.type_map[value.collection]),
            (JsonArrayTypeAnnotation, JsonObjectTypeAnnotation),
        ):
            return False

        self.errors.append(
            Error(
                value.original_node,
                f"A JSON-able value is never null, so {check} over an index into "
                f"a JSON-able object or array really asks whether the key or "
                f"the position is there. Please ask that directly, as "
                f"``<key> in <object>`` and as ``len(<array>) > <position>``, "
                f"which strips the optionality of the index in the guarded "
                f"expression.",
            )
        )
        return True

    def transform_is_none(
        self, node: parse_tree.IsNone
    ) -> Optional["TypeAnnotationUnion"]:
        value_type = self.transform(node.value)

        # NOTE (mristin):
        # Something went wrong if we could not infer the type of the ``value``.
        if value_type is None:
            return None

        if self._nullness_check_over_json_index_is_refused(node.value, "``is None``"):
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

        if self._nullness_check_over_json_index_is_refused(
            node.value, "``is not None``"
        ):
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
        # NOTE (mristin):
        # We need to iterate and recurse into ``values`` to fill the ``type_map``.
        # In the process, we have to consider the non-nullness and how it applies
        # to the remainder of the conjunction.

        # NOTE (mristin):
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

                self._assume_guard(value_node, exit_stack)

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

                # NOTE (mristin):
                # Analogous to ``x is None or ...``, the remainder of
                # the disjunction in ``not isinstance(x, C) or ...`` is evaluated only
                # if ``x`` is an instance of ``C``.
                if (
                    success
                    and isinstance(value_node, parse_tree.Not)
                    and isinstance(value_node.operand, parse_tree.IsInstance)
                ):
                    self._assume_narrowing(value_node.operand, exit_stack)

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

        if is_new_variable:
            assert isinstance(node.target, parse_tree.Name)
            if node.target.identifier in self._names_of_variables_in_closed_scopes[-1]:
                self.errors.append(
                    Error(
                        node.original_node,
                        f"The variable {node.target.identifier!r} has been already "
                        f"defined in a branch of a switch before. In Python, both "
                        f"definitions denote the same variable, while they denote "
                        f"two different variables in the target languages with "
                        f"block scopes, and some target languages, such as C#, "
                        f"refuse such re-declarations altogether. Please use "
                        f"a different name.",
                    )
                )

                # NOTE (mristin):
                # We still define the variable so that the subsequent statements
                # do not report it as unknown, which would only confuse the user.
                self._environment.set(
                    identifier=node.target.identifier, type_annotation=value_type
                )
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

    def _transform_in_new_scope(
        self, statements: Sequence[parse_tree.StatementUnion]
    ) -> bool:
        """
        Transform the ``statements`` in a new scope, and return ``True`` on success.

        A scope is the region of the code where a variable is visible. Python has
        only function-level scopes, so a variable assigned in a branch of an ``if``
        stays visible after the ``if``. The target languages with C-like syntax
        (C++, C#, Java, TypeScript and Go) scope the variables to the enclosing block,
        and we generate a separate block for each branch of a switch. Hence, we
        model the branches as block scopes here as well:

        * The statements see the variables of the enclosing scopes, and can assign
          to them.
        * A variable newly defined in the statements is visible only in them, and
          not after the branch. For example, the following is not allowed:

          .. code-block:: python

              if kind == Kind.Something:
                  x = 1
              else:
                  x = 2

              return x > 0

        The meta-model is written in Python, but must behave the same in all
        the targets. Therefore, we refuse all the collisions of variable names where
        Python's function-level scope and the block scopes would diverge:

        * Reading a variable after the branch which defined it is refused, as
          the variable is unknown outside the branch. This also refuses reading
          a variable which has been defined only in a sibling branch.
        * Defining a variable in an enclosing scope after a branch which defined
          a variable of the same name is refused. In Python, both definitions
          would denote the same variable, while they denote two different
          variables with block scopes. Moreover, some target languages, such as
          C#, refuse such re-declarations altogether. To that end, we remember
          the names (but not the variables themselves!) of the closed scopes in
          :attr:`_names_of_variables_in_closed_scopes`.
        * Assigning in a branch to a variable defined before the switch is
          an assignment to that very variable, both in Python and in the block
          scopes, so it is allowed.
        * Sibling branches can define the variables of the same name. In Python,
          they denote the same variable, but since neither of them is visible
          outside its branch, no branch can observe the value set by another
          branch, and the behavior is the same as with block scopes.
        """
        parent_environment = self._environment
        scope_environment = MutableEnvironment(parent=parent_environment)
        self._environment = scope_environment
        self._names_of_variables_in_closed_scopes.append(set())

        success = True
        try:
            for stmt in statements:
                if self.transform(stmt) is None:
                    success = False
        finally:
            # NOTE (mristin):
            # We discard the environment of the scope so that its variables are not
            # visible anymore. However, we pass on the names of its variables, and
            # the names of the variables of its own closed nested scopes, to
            # the enclosing scope so that it can refuse their re-declarations.
            names_of_variables_in_nested_scopes = (
                self._names_of_variables_in_closed_scopes.pop()
            )
            self._names_of_variables_in_closed_scopes[-1].update(
                names_of_variables_in_nested_scopes
            )
            self._names_of_variables_in_closed_scopes[-1].update(
                scope_environment.mapping.keys()
            )

            self._environment = parent_environment

        return success

    def transform_switch(
        self, node: parse_tree.Switch
    ) -> Optional["TypeAnnotationUnion"]:
        subject_type = self.transform(node.subject)
        if subject_type is None:
            return None

        if isinstance(subject_type, OptionalTypeAnnotation):
            self.errors.append(
                Error(
                    node.subject.original_node,
                    f"Expected the subject of the switch to be a non-None, "
                    f"but got: {subject_type}",
                )
            )
            return None

        enumeration = None  # type: Optional[_types.Enumeration]
        primitive_type = None  # type: Optional[PrimitiveType]

        if isinstance(subject_type, OurTypeAnnotation) and isinstance(
            subject_type.our_type, _types.Enumeration
        ):
            enumeration = subject_type.our_type
        else:
            primitive_type = try_primitive_type(subject_type)
            if primitive_type not in (PrimitiveType.STR, PrimitiveType.INT):
                self.errors.append(
                    Error(
                        node.subject.original_node,
                        f"Expected the subject of the switch to be an enumeration, "
                        f"a string or an integer, but got: {subject_type}",
                    )
                )
                return None

        success = True

        for case in node.cases:
            for label in case.labels:
                label_type = self.transform(label)
                if label_type is None:
                    success = False
                    continue

                if enumeration is not None:
                    if not (
                        isinstance(label, parse_tree.Member)
                        and isinstance(
                            self.type_map.get(label.instance, None),
                            EnumerationAsTypeTypeAnnotation,
                        )
                        and isinstance(label_type, OurTypeAnnotation)
                        and label_type.our_type is enumeration
                    ):
                        self.errors.append(
                            Error(
                                label.original_node,
                                f"Expected the label to be a literal of "
                                f"the enumeration {enumeration.name!r}, the type of "
                                f"the subject of the switch, but got: {label_type}",
                            )
                        )
                        success = False

                else:
                    assert primitive_type is not None
                    if not (
                        isinstance(label, parse_tree.Constant)
                        and isinstance(label_type, PrimitiveTypeAnnotation)
                        and label_type.a_type is primitive_type
                    ):
                        self.errors.append(
                            Error(
                                label.original_node,
                                f"Expected the label to be "
                                f"a {primitive_type.value} literal, the type of "
                                f"the subject of the switch, but got: {label_type}",
                            )
                        )
                        success = False

            if not self._transform_in_new_scope(case.body):
                success = False

        if node.default is not None:
            if not self._transform_in_new_scope(node.default):
                success = False

        if not success:
            return None

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

    return ImmutableEnvironment(
        mapping=mapping,
        parent=None,
        our_types_by_name={
            our_type.name: our_type for our_type in symbol_table.our_types
        },
    )


class InferenceOfFunction:
    """Represent the result of type inference on a function body and arguments."""

    #: Environment inferred after processing a body of statements including
    #: the function arguments
    environment_with_args: Final[Environment]

    #: Map of body nodes to types
    type_map: Final[Mapping[parse_tree.Node, "TypeAnnotationUnion"]]

    #: Map of body nodes narrowed by ``isinstance`` to their down-casts
    downcast_map: Final[Mapping[parse_tree.Node, Downcast]]

    def __init__(
        self,
        environment_with_args: Environment,
        type_map: Mapping[parse_tree.Node, "TypeAnnotationUnion"],
        downcast_map: Mapping[parse_tree.Node, Downcast],
    ) -> None:
        """Initialize with the given values."""
        self.environment_with_args = environment_with_args
        self.type_map = type_map
        self.downcast_map = downcast_map


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
            environment_with_args=environment,
            type_map=type_inferrer.type_map,
            downcast_map=type_inferrer.downcast_map,
        ),
        None,
    )


class InferenceOfInvariant:
    """Represent the result of type inference on the body of an invariant."""

    #: Map of body nodes to types
    type_map: Final[Mapping[parse_tree.Node, "TypeAnnotationUnion"]]

    #: Map of body nodes narrowed by ``isinstance`` to their down-casts
    downcast_map: Final[Mapping[parse_tree.Node, Downcast]]

    def __init__(
        self,
        type_map: Mapping[parse_tree.Node, "TypeAnnotationUnion"],
        downcast_map: Mapping[parse_tree.Node, Downcast],
    ) -> None:
        """Initialize with the given values."""
        self.type_map = type_map
        self.downcast_map = downcast_map


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def infer_for_invariant(
    invariant: _types.Invariant, environment: Environment
) -> Tuple[Optional[InferenceOfInvariant], Optional[Error]]:
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

    return (
        InferenceOfInvariant(
            type_map=type_inferrer.type_map,
            downcast_map=type_inferrer.downcast_map,
        ),
        None,
    )


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
    JsonValueTypeAnnotation,
    JsonArrayTypeAnnotation,
    JsonObjectTypeAnnotation,
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

# NOTE (mristin):
# Mypy is not smart enough to work with ``get_args``, so we have to manually write it
# out.
FunctionTypeAnnotationUnionAsTuple = (
    VerificationTypeAnnotation,
    BuiltinFunctionTypeAnnotation,
)
assert FunctionTypeAnnotationUnionAsTuple == get_args(FunctionTypeAnnotationUnion)
