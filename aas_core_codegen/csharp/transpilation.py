"""Transpile Python to C# code."""
import abc
import ast
import io
import textwrap
from typing import (
    Final,
    Tuple,
    Optional,
    List,
    Mapping,
    Sequence,
    Union,
    Set,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Stripped,
    assert_never,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.csharp import (
    common as csharp_common,
    naming as csharp_naming,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.parse import tree as parse_tree


def _is_value_type(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
) -> bool:
    """
    Check whether ``type_annotation`` is represented as a C# value type.

    This mirrors :py:func:`aas_core_codegen.csharp.common.is_value_type` for
    the type annotations of the type inference.
    """
    primitive_type = intermediate_type_inference.try_primitive_type(type_annotation)
    if primitive_type is not None:
        return primitive_type in (
            intermediate_type_inference.PrimitiveType.BOOL,
            intermediate_type_inference.PrimitiveType.INT,
            intermediate_type_inference.PrimitiveType.FLOAT,
        )

    if isinstance(
        type_annotation, intermediate_type_inference.OurTypeAnnotation
    ) and isinstance(type_annotation.our_type, intermediate.Enumeration):
        return True

    return isinstance(type_annotation, intermediate_type_inference.TupleTypeAnnotation)


def generate_type(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
) -> Tuple[Optional[Stripped], Optional[str]]:
    """
    Generate the C# type for the given type annotation.

    We assume that our types are referred to with the ``Our.`` prefix.

    We handle only the type annotations which can be declared for the variables.
    Otherwise, we return an error message.
    """
    if isinstance(type_annotation, intermediate_type_inference.PrimitiveTypeAnnotation):
        if type_annotation.a_type in (
            intermediate_type_inference.PrimitiveType.LENGTH,
            intermediate_type_inference.PrimitiveType.NONE,
        ):
            return None, f"Unexpected primitive type: {type_annotation}"

        return (
            csharp_common.PRIMITIVE_TYPE_MAP[
                intermediate.PrimitiveType(type_annotation.a_type.value)
            ],
            None,
        )

    elif isinstance(type_annotation, intermediate_type_inference.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(f"Our.{csharp_naming.enum_name(our_type.name)}"), None
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return csharp_common.PRIMITIVE_TYPE_MAP[our_type.constrainee], None
        elif isinstance(our_type, intermediate.Class):
            return (
                Stripped(f"Our.{csharp_naming.interface_name(our_type.name)}"),
                None,
            )
        elif isinstance(our_type, intermediate.NamedUnion):
            return Stripped(f"Our.{csharp_naming.class_name(our_type.name)}"), None
        else:
            assert_never(our_type)

    elif isinstance(type_annotation, intermediate_type_inference.ListTypeAnnotation):
        item_type, error_message = generate_type(type_annotation.items)
        if error_message is not None:
            return None, error_message

        return Stripped(f"List<{item_type}>"), None

    elif isinstance(type_annotation, intermediate_type_inference.SetTypeAnnotation):
        item_type, error_message = generate_type(type_annotation.items)
        if error_message is not None:
            return None, error_message

        return Stripped(f"HashSet<{item_type}>"), None

    elif isinstance(type_annotation, intermediate_type_inference.TupleTypeAnnotation):
        item_types: List[Stripped] = []
        for item in type_annotation.items:
            item_type, error_message = generate_type(item)
            if error_message is not None:
                return None, error_message

            assert item_type is not None
            item_types.append(item_type)

        joined_item_types = ", ".join(item_types)

        if len(item_types) == 1:
            # NOTE (mristin):
            # A single-element value tuple has no literal syntax in C#, so we have
            # to spell out the generic type explicitly.
            return Stripped(f"System.ValueTuple<{joined_item_types}>"), None

        return Stripped(f"({joined_item_types})"), None

    elif isinstance(
        type_annotation, intermediate_type_inference.OptionalTypeAnnotation
    ):
        value_type, error_message = generate_type(type_annotation.value)
        if error_message is not None:
            return None, error_message

        return Stripped(f"{value_type}?"), None

    return None, f"Unexpected type annotation of a variable: {type_annotation}"


class Transpiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a node of our AST to C# code, or return an error."""

    _CSHARP_COMPARISON_MAP: Final[Mapping[parse_tree.Comparator, str]] = {
        parse_tree.Comparator.LT: "<",
        parse_tree.Comparator.LE: "<=",
        parse_tree.Comparator.GT: ">",
        parse_tree.Comparator.GE: ">=",
        parse_tree.Comparator.EQ: "==",
        parse_tree.Comparator.NE: "!=",
    }

    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        environment: intermediate_type_inference.Environment,
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
    ) -> None:
        """Initialize with the given values."""
        self.type_map = type_map
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )
        self._downcast_map = downcast_map

        # Keep track whenever we define a variable name, so that we can know how to
        # generate the reference in the C# code.
        self._variable_name_set: Set[Identifier] = set()

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform(
        self, node: parse_tree.Node
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        code, error = super().transform(node)
        if error is not None:
            return None, error

        assert code is not None

        downcast = self._downcast_map.get(node, None)
        if downcast is None:
            return code, None

        # NOTE (mristin):
        # The type inference narrowed the value down with an ``isinstance`` guard,
        # but the C# compiler does not know about it, so we have to down-cast
        # explicitly. We always parenthesize the cast so that the callers need not
        # care about the operator precedence.
        return Transpiler._downcast(code=code, downcast=downcast), None

    @staticmethod
    def _underlying_if_named_union(
        code: Stripped,
        type_annotation: intermediate_type_inference.TypeAnnotationUnion,
    ) -> Stripped:
        """
        Access the underlying instance of ``code`` if it is a named union.

        A named union is represented as a wrapper class in C#, so the run-time
        type checks and the down-casts need to operate on its underlying instance.
        """
        type_anno = intermediate_type_inference.beneath_optional(type_annotation)
        if isinstance(
            type_anno, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(type_anno.our_type, intermediate.NamedUnion):
            return Stripped(f"{code}.Underlying")

        return code

    @staticmethod
    def _downcast(
        code: Stripped, downcast: intermediate_type_inference.Downcast
    ) -> Stripped:
        """Down-cast the value given as ``code`` according to ``downcast``."""
        assert isinstance(
            downcast.target.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ), (
            f"Expected the target of a down-cast to be a class, "
            f"but got: {downcast.target}"
        )

        value = Transpiler._underlying_if_named_union(
            code=code, type_annotation=downcast.source
        )

        interface_name = csharp_naming.interface_name(downcast.target.our_type.name)

        # NOTE (mristin):
        # We assume that the types are referred to with the ``Our.`` prefix in
        # the generated code, as is the case with the verification module.
        return Stripped(f"((Our.{interface_name}){value})")

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_member(
        self, node: parse_tree.Member
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        instance, error = self.transform(node.instance)
        if error is not None:
            return None, error

        # Ignore optionals as they need to be checked before in the code
        instance_type = intermediate_type_inference.beneath_optional(
            self.type_map[node.instance]
        )
        member_type = intermediate_type_inference.beneath_optional(self.type_map[node])

        member_name: str

        if isinstance(
            instance_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type.our_type, intermediate.Enumeration):
            # The member denotes a literal of an enumeration.
            member_name = csharp_naming.enum_literal_name(node.name)

        elif isinstance(member_type, intermediate_type_inference.MethodTypeAnnotation):
            member_name = csharp_naming.method_name(node.name)

        elif isinstance(
            instance_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type.our_type, intermediate.Class):
            if node.name in instance_type.our_type.properties_by_name:
                member_name = csharp_naming.property_name(node.name)
            else:
                return None, Error(
                    node.original_node,
                    f"The property {node.name!r} has not been defined "
                    f"in the class {instance_type.our_type.name!r}",
                )

        elif isinstance(
            instance_type, intermediate_type_inference.EnumerationAsTypeTypeAnnotation
        ):
            if node.name in instance_type.enumeration.literals_by_name:
                member_name = csharp_naming.enum_literal_name(node.name)
            else:
                return None, Error(
                    node.original_node,
                    f"The literal {node.name!r} has not been defined "
                    f"in the enumeration {instance_type.enumeration.name!r}",
                )
        else:
            return None, Error(
                node.original_node,
                f"We do not know how to generate the member access. The inferred type "
                f"of the instance was {instance_type}, while the member type "
                f"was {member_type}. However, we do not know how to resolve "
                f"the member {node.name!r} in {instance_type}.",
            )

        return Stripped(f"{instance}.{member_name}"), None

    def _is_declared_nullable(self, node: parse_tree.Expression) -> bool:
        """
        Check whether the ``node`` has been declared as optional.

        The type inference strips ``Optional`` from the types of the nodes which have
        been narrowed down by a guard such as ``x is not None``. However, C# keeps
        the declared type, so that a narrowed integer or floating-point number is
        still a nullable value type (``long?`` or ``double?``) in C#. The lifted
        operators work on nullable value types, but we need to explicitly unwrap
        them with ``.Value`` before passing them to a method.
        """
        if isinstance(node, parse_tree.Member):
            instance_type = self.type_map.get(node.instance, None)
            if isinstance(
                instance_type, intermediate_type_inference.OurTypeAnnotation
            ) and isinstance(
                instance_type.our_type,
                (intermediate.ConcreteClass, intermediate.AbstractClass),
            ):
                prop = instance_type.our_type.properties_by_name.get(node.name, None)
                return prop is not None and isinstance(
                    prop.type_annotation, intermediate.OptionalTypeAnnotation
                )

            return False

        elif isinstance(node, parse_tree.Name):
            return isinstance(
                self._environment.find(node.identifier),
                intermediate_type_inference.OptionalTypeAnnotation,
            )

        return False

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_index(
        self, node: parse_tree.Index
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        collection_type = self.type_map[node.collection]

        if isinstance(
            intermediate_type_inference.beneath_optional(collection_type),
            intermediate_type_inference.TupleTypeAnnotation,
        ):
            # NOTE (mristin):
            # Tuples are heterogeneous and fixed-length, so, unlike lists, they can
            # not be indexed at runtime. Instead, the index must be a literal
            # integer known at the time of the code generation so that we can
            # generate an access to the corresponding ``ItemN`` property.
            #
            # This is enforced in
            # :py:meth:`aas_core_codegen.intermediate.type_inference.Inferrer.transform_index`.
            assert isinstance(node.index, parse_tree.Constant) and isinstance(
                node.index.value, int
            )

            tuple_type = intermediate_type_inference.beneath_optional(collection_type)
            assert isinstance(
                tuple_type, intermediate_type_inference.TupleTypeAnnotation
            )

            index_value = node.index.value
            if index_value < 0:
                index_value += len(tuple_type.items)

            collection, error = self.transform(node.collection)
            if error is not None:
                return None, error
            assert collection is not None

            tuple_no_parentheses_types = (
                parse_tree.Member,
                parse_tree.FunctionCall,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.Constant,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.Tuple,
            )
            if not isinstance(node.collection, tuple_no_parentheses_types):
                collection = Stripped(f"({collection})")

            # NOTE (mristin):
            # A tuple is a value type in C#, so an optional tuple is
            # a ``System.Nullable`` even if narrowed to non-null, and we need to
            # unwrap it before we access its items.
            if self._is_declared_nullable(node.collection):
                collection = Stripped(f"{collection}.Value")

            return Stripped(f"{collection}.Item{index_value + 1}"), None

        collection, error = self.transform(node.collection)
        if error is not None:
            return None, error

        index, error = self.transform(node.index)
        if error is not None:
            return None, error
        assert index is not None

        index_as_int: Optional[int] = None
        try:
            index_as_int = int(index)
        except ValueError:
            pass

        if index_as_int is not None and index_as_int < 0:
            index = Stripped(f"^{-index_as_int}")

        elif (
            index_as_int is None
            and intermediate_type_inference.try_primitive_type(
                self.type_map[node.index]
            )
            is intermediate_type_inference.PrimitiveType.INT
        ):
            # NOTE (mristin):
            # The integers of the meta-model are ``long``'s in C#, while the lists
            # and the JSON arrays are indexed by ``int``'s. We narrow the index
            # explicitly, and fail loudly instead of silently overflowing.
            if isinstance(
                node.index,
                (
                    parse_tree.Member,
                    parse_tree.FunctionCall,
                    parse_tree.MethodCall,
                    parse_tree.Name,
                    parse_tree.Index,
                ),
            ):
                index = Stripped(f"checked((int){index})")
            else:
                index = Stripped(f"checked((int)({index}))")

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.IsIn,
        )

        if not isinstance(node.collection, no_parentheses_types):
            collection = Stripped(f"({collection})")

        # NOTE (mristin):
        # The indexer of a ``Nodes.JsonObject`` and of a ``Nodes.JsonArray``
        # gives a nullable node. This is exactly our ``JSONValue``, which might
        # be a JSON null even if the meta-model guarded the index with
        # a membership or a length check, so there is nothing to forgive.
        return Stripped(f"{collection}[{index}]"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_slice(
        self, node: parse_tree.Slice
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        collection, error = self.transform(node.collection)
        if error is not None:
            errors.append(error)

        start: Optional[Stripped] = None
        if node.start is not None:
            start, error = self.transform(node.start)
            if error is not None:
                errors.append(error)

        end: Optional[Stripped] = None
        if node.end is not None:
            end, error = self.transform(node.end)
            if error is not None:
                errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the slice", errors
            )

        assert collection is not None

        # NOTE (mristin):
        # We do not use the native ``Substring`` as it counts the UTF-16 code units
        # instead of the characters, throws on the positions out of range, and does
        # not count the negative ones from the end, unlike Python. See
        # ``Common.StringHelpers.Slice`` in the generated common module.
        args: List[str] = [collection, start if start is not None else "0"]
        if end is not None:
            args.append(end)

        return (
            Stripped(
                f"{csharp_common.COMMON_CLASS}.StringHelpers.Slice({', '.join(args)})"
            ),
            None,
        )

    def _transform_and_unwrap_narrowed_nullable_value(
        self, node: parse_tree.Expression
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``node`` and unwrap it if it is a narrowed nullable value type.

        A value type such as ``long?`` stays nullable in C# even if the type
        inference narrowed it down to non-null, so we need to unwrap it with
        ``.Value`` before we assign it to a non-nullable or return it.
        """
        code, error = self.transform(node)
        if error is not None:
            return None, error

        assert code is not None

        if self._is_declared_nullable(node) and _is_value_type(self.type_map[node]):
            return Stripped(f"{code}.Value"), None

        return code, None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        value_reprs: List[Stripped] = []

        # NOTE (mristin):
        # A tuple of ``long`` does not accept a ``long?``, so we unwrap a narrowed
        # nullable value type.
        for value_node in node.values:
            value_repr, error = self._transform_and_unwrap_narrowed_nullable_value(
                value_node
            )
            if error is not None:
                errors.append(error)
                continue

            assert value_repr is not None
            value_reprs.append(value_repr)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the tuple", errors
            )

        return csharp_common.generate_tuple_literal(value_reprs), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_list_literal(
        self, node: parse_tree.ListLiteral
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        items: List[Stripped] = []

        # NOTE (mristin):
        # A list of ``long`` does not accept a ``long?``, so we unwrap a narrowed
        # nullable value type.
        for item_node in node.items:
            item, error = self._transform_and_unwrap_narrowed_nullable_value(item_node)
            if error is not None:
                errors.append(error)
                continue

            assert item is not None
            items.append(item)

        list_type, error_message = generate_type(self.type_map[node])
        if error_message is not None:
            errors.append(Error(node.original_node, error_message))

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the list literal", errors
            )

        if len(items) == 0:
            return Stripped(f"new {list_type}()"), None

        one_liner = f"new {list_type} {{ {', '.join(items)} }}"
        if "\n" not in one_liner and len(one_liner) <= 60:
            return Stripped(one_liner), None

        items_joined = ",\n".join(items)
        return (
            Stripped(
                f"""\
new {list_type}
{{
{I}{indent_but_first_line(items_joined, I)}
}}"""
            ),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_comparison(
        self, node: parse_tree.Comparison
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        comparator = Transpiler._CSHARP_COMPARISON_MAP[node.op]

        # NOTE (mristin):
        # C# orders neither the strings nor the booleans with the operators ``<``,
        # ``<=``, ``>`` and ``>=``. Moreover, ``string.CompareOrdinal`` would order
        # the strings by their UTF-16 code units, while Python orders them by their
        # characters (code points). Hence, we order the strings with our helpers,
        # and the booleans with ``CompareTo``, where ``false`` comes before ``true``
        # as in Python.
        primitive_type = intermediate_type_inference.try_primitive_type(
            self.type_map[node.left]
        )
        if node.op not in (
            parse_tree.Comparator.EQ,
            parse_tree.Comparator.NE,
        ) and primitive_type in (
            intermediate_type_inference.PrimitiveType.STR,
            intermediate_type_inference.PrimitiveType.BOOL,
        ):
            ordering_errors: List[Error] = []

            ordered_left, error = self._transform_and_unwrap_narrowed_nullable_value(
                node.left
            )
            if error is not None:
                ordering_errors.append(error)

            ordered_right, error = self._transform_and_unwrap_narrowed_nullable_value(
                node.right
            )
            if error is not None:
                ordering_errors.append(error)

            if len(ordering_errors) > 0:
                return None, Error(
                    node.original_node,
                    "Failed to transpile the comparison",
                    ordering_errors,
                )

            assert ordered_left is not None
            assert ordered_right is not None

            if primitive_type is intermediate_type_inference.PrimitiveType.STR:
                return (
                    Stripped(
                        f"{csharp_common.COMMON_CLASS}.StringHelpers.CompareByCodePoints("
                        f"{ordered_left}, {ordered_right}) {comparator} 0"
                    ),
                    None,
                )

            if not isinstance(
                node.left, (parse_tree.Member, parse_tree.Name, parse_tree.Constant)
            ):
                ordered_left = Stripped(f"({ordered_left})")

            return (
                Stripped(f"{ordered_left}.CompareTo({ordered_right}) {comparator} 0"),
                None,
            )

        errors = []

        left, error = self.transform(node.left)
        if error is not None:
            errors.append(error)

        right, error = self.transform(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the comparison", errors
            )

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
        )

        if isinstance(node.left, no_parentheses_types) and isinstance(
            node.right, no_parentheses_types
        ):
            return Stripped(f"{left} {comparator} {right}"), None

        return Stripped(f"({left}) {comparator} ({right})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_is_in(
        self, node: parse_tree.IsIn
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []

        # NOTE (mristin):
        # A set of value types, such as enumeration literals, does not hold
        # nullables, so we unwrap a narrowed member.
        member, error = self._transform_and_unwrap_narrowed_nullable_value(node.member)
        if error is not None:
            errors.append(error)

        container, error = self.transform(node.container)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node,
                "Failed to transpile the membership relation",
                errors,
            )

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
        )

        if not isinstance(node.container, no_parentheses_types):
            container = Stripped(f"({container})")

        container_type = self.type_map[node.container]

        # NOTE (mristin):
        # A JSON-able object is a ``Nodes.JsonObject``, a dictionary of nodes,
        # so the membership is a question about its keys.
        if isinstance(
            container_type, intermediate_type_inference.JsonObjectTypeAnnotation
        ):
            return Stripped(f"{container}.ContainsKey({member})"), None

        if isinstance(
            container_type,
            (
                intermediate_type_inference.JsonValueTypeAnnotation,
                intermediate_type_inference.JsonArrayTypeAnnotation,
            ),
        ):
            return None, Error(
                node.original_node,
                f"We do not know how to generate the membership check for "
                f"the container of type {container_type}. Only a JSON-able "
                f"object, whose keys the membership is about, is supported. "
                f"Please contact the developers if you need this feature.",
            )

        return Stripped(f"{container}.Contains({member})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_is_instance(
        self, node: parse_tree.IsInstance
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        value_type: intermediate_type_inference.TypeAnnotationUnion

        downcast = self._downcast_map.get(node.value, None)
        if downcast is not None:
            # NOTE (mristin):
            # The value has already been narrowed down by an earlier guard. We skip
            # the down-cast of the value here, since it would change nothing at
            # the run-time, and only make the check harder to read.
            value, error = super().transform(node.value)
            value_type = downcast.source
        else:
            value, error = self.transform(node.value)
            value_type = self.type_map[node.value]

        if error is not None:
            return None, error

        assert value is not None

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Index,
            parse_tree.Slice,
        )
        if not isinstance(node.value, no_parentheses_types):
            value = Stripped(f"({value})")

        value = Transpiler._underlying_if_named_union(
            code=value, type_annotation=value_type
        )

        # NOTE (mristin):
        # We assume that the types are referred to with the ``Our.`` prefix in
        # the generated code, as is the case with the verification module.
        checks = [
            f"{value} is Our.{csharp_naming.interface_name(cls.identifier)}"
            for cls in node.classes
        ]

        if len(checks) == 1:
            return Stripped(checks[0]), None

        checks_joined = " || ".join(checks)
        return Stripped(f"({checks_joined})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_implication(
        self, node: parse_tree.Implication
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []

        antecedent, error = self.transform(node.antecedent)
        if error is not None:
            errors.append(error)

        consequent, error = self.transform(node.consequent)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the implication", errors
            )

        assert antecedent is not None
        assert consequent is not None

        no_parentheses_types_in_this_context = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
        )

        if isinstance(node.antecedent, no_parentheses_types_in_this_context):
            not_antecedent = f"!{antecedent}"
        else:
            # NOTE (mristin):
            # This is a very rudimentary heuristic for breaking the lines, and can be
            # greatly improved by rendering into C# code. However, at this point, we
            # lack time for more sophisticated reformatting approaches.
            if "\n" in antecedent:
                not_antecedent = f"""\
!(
{I}{indent_but_first_line(antecedent, I)}
)"""
            else:
                not_antecedent = f"!({antecedent})"

        if not isinstance(node.consequent, no_parentheses_types_in_this_context):
            # NOTE (mristin):
            # This is a very rudimentary heuristic for breaking the lines, and can be
            # greatly improved by rendering into C# code. However, at this point, we
            # lack time for more sophisticated reformatting approaches.
            if "\n" in consequent:
                consequent = Stripped(
                    f"""\
(
{I}{indent_but_first_line(consequent, I)}
)"""
                )
            else:
                consequent = Stripped(f"({consequent})")

        return Stripped(f"{not_antecedent}\n|| {consequent}"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_method_call(
        self, node: parse_tree.MethodCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        instance, error = self.transform(node.member.instance)
        if error is not None:
            errors.append(error)

        args: List[Stripped] = []
        for arg_node in node.args:
            arg, error = self.transform(arg_node)
            if error is not None:
                errors.append(error)
                continue

            assert arg is not None

            args.append(arg)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the method call", errors
            )

        assert instance is not None

        member_type = self.type_map[node.member]

        parenthesized_instance = (
            instance
            if isinstance(
                node.member.instance,
                (parse_tree.Name, parse_tree.Member, parse_tree.Slice),
            )
            else Stripped(f"({instance})")
        )

        if isinstance(
            member_type, intermediate_type_inference.BuiltinMethodTypeAnnotation
        ):
            kind = member_type.method.kind

            if kind is intermediate_type_inference.BuiltinMethodKind.STR_FIND:
                # NOTE (mristin):
                # We do not use the native ``IndexOf`` as it counts the UTF-16
                # code units instead of the characters, throws on a start out of
                # range, and does not count a negative start from the end, unlike
                # Python. See ``Common.StringHelpers.Find`` in the generated common module.
                return (
                    Stripped(
                        f"{csharp_common.COMMON_CLASS}.StringHelpers.Find({parenthesized_instance}, {', '.join(args)})"
                    ),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_LSTRIP:
                # NOTE (mristin):
                # We do not use the native ``TrimStart`` as it strips the UTF-16 code
                # units instead of the characters, unlike Python. See
                # ``StringHelpers.LStrip`` in the generated common class.
                return (
                    Stripped(
                        f"{csharp_common.COMMON_CLASS}.StringHelpers.LStrip"
                        f"({instance}, {args[0]})"
                    ),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_RSTRIP:
                # NOTE (mristin):
                # We do not use the native ``TrimEnd`` as it strips the UTF-16 code
                # units instead of the characters, unlike Python. See
                # ``StringHelpers.RStrip`` in the generated common class.
                return (
                    Stripped(
                        f"{csharp_common.COMMON_CLASS}.StringHelpers.RStrip"
                        f"({instance}, {args[0]})"
                    ),
                    None,
                )

            elif (
                kind is intermediate_type_inference.BuiltinMethodKind.STR_STARTSWITH
                or kind is intermediate_type_inference.BuiltinMethodKind.STR_ENDSWITH
            ):
                # NOTE (mristin):
                # We pass ``Ordinal`` since the default overloads compare
                # the strings culture-sensitively, and, *e.g.*, ignore the zero-width
                # characters. The ordinal comparison of the UTF-16 code units gives
                # the same result as the Python comparison of the characters (code
                # points) unless the prefix or the suffix has a lone surrogate.
                native_method = (
                    "StartsWith"
                    if kind
                    is intermediate_type_inference.BuiltinMethodKind.STR_STARTSWITH
                    else "EndsWith"
                )

                receiver = (
                    instance
                    if isinstance(
                        node.member.instance,
                        (
                            parse_tree.Name,
                            parse_tree.Member,
                            parse_tree.MethodCall,
                            parse_tree.FunctionCall,
                        ),
                    )
                    else Stripped(f"({instance})")
                )

                return (
                    Stripped(
                        f"{receiver}.{native_method}"
                        f"({args[0]}, System.StringComparison.Ordinal)"
                    ),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.SET_ADD:
                # NOTE (mristin):
                # A set of value types does not hold nullables, so we unwrap
                # a narrowed item.
                item, error = self._transform_and_unwrap_narrowed_nullable_value(
                    node.args[0]
                )
                if error is not None:
                    return None, error

                assert item is not None
                return Stripped(f"{parenthesized_instance}.Add({item})"), None

            elif kind is intermediate_type_inference.BuiltinMethodKind.LIST_APPEND:
                # NOTE (mristin):
                # A list of value types does not hold nullables, so we unwrap
                # a narrowed item.
                item, error = self._transform_and_unwrap_narrowed_nullable_value(
                    node.args[0]
                )
                if error is not None:
                    return None, error

                assert item is not None
                return Stripped(f"{parenthesized_instance}.Add({item})"), None

            elif (
                kind is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
                or kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
            ):
                set_type, error_message = generate_type(self.type_map[node])
                if error_message is not None:
                    return None, Error(node.original_node, error_message)

                # NOTE (mristin):
                # We copy the result of LINQ into a new set, as Python gives
                # a new set as well.
                linq_method: str
                if (
                    kind
                    is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
                ):
                    linq_method = "Intersect"
                elif (
                    kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
                ):
                    linq_method = "Except"
                else:
                    assert_never(kind)

                return (
                    Stripped(
                        f"new {set_type}"
                        f"({parenthesized_instance}.{linq_method}({args[0]}))"
                    ),
                    None,
                )

            else:
                assert_never(kind)

        method_name = csharp_naming.method_name(node.member.name)

        joined_args = ", ".join(args)

        # Apply heuristic for breaking the lines
        if len(joined_args) > 50:
            writer = io.StringIO()
            writer.write(f"{parenthesized_instance}.{method_name}(\n")

            for i, arg in enumerate(args):
                writer.write(f"{I}{arg}")

                if i == len(args) - 1:
                    writer.write(")")
                else:
                    writer.write(",\n")

            return Stripped(writer.getvalue()), None
        else:
            return (
                Stripped(f"{parenthesized_instance}.{method_name}({joined_args})"),
                None,
            )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_function_call(
        self, node: parse_tree.FunctionCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        args: List[Stripped] = []
        for arg_node in node.args:
            arg, error = self.transform(arg_node)
            if error is not None:
                errors.append(error)
                continue

            assert arg is not None

            args.append(arg)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the function call", errors
            )

        # NOTE (mristin):
        # The validity of the arguments is checked in
        # :py:func:`aas_core_codegen.intermediate._translate.translate`, so we do not
        # have to test for argument arity here.

        func_type = self.type_map[node.name]

        if not isinstance(
            func_type, intermediate_type_inference.FunctionTypeAnnotationUnionAsTuple
        ):
            return None, Error(
                node.name.original_node,
                f"Expected the name to refer to a function, "
                f"but its inferred type was {func_type}",
            )

        if isinstance(
            func_type, intermediate_type_inference.VerificationTypeAnnotation
        ):
            method_name = csharp_naming.method_name(func_type.func.name)

            joined_args = ", ".join(args)

            # Apply heuristic for breaking the lines
            if len(joined_args) > 50:
                writer = io.StringIO()
                writer.write(f"Verification.{method_name}(\n")

                for i, arg in enumerate(args):
                    writer.write(f"{I}{arg}")

                    if i == len(args) - 1:
                        writer.write(")")
                    else:
                        writer.write(",\n")

                return Stripped(writer.getvalue()), None
            else:
                return Stripped(f"Verification.{method_name}({joined_args})"), None

        elif isinstance(
            func_type, intermediate_type_inference.BuiltinFunctionTypeAnnotation
        ):
            if (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.LEN
            ):
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                collection_node = node.args[0]
                if not isinstance(
                    collection_node,
                    (
                        parse_tree.Name,
                        parse_tree.Member,
                        parse_tree.MethodCall,
                        parse_tree.Slice,
                    ),
                ):
                    collection = f"({args[0]})"
                else:
                    collection = args[0]

                arg_type = self.type_map[node.args[0]]
                while isinstance(
                    arg_type, intermediate_type_inference.OptionalTypeAnnotation
                ):
                    arg_type = arg_type.value

                primitive_type = intermediate_type_inference.try_primitive_type(
                    arg_type
                )

                if primitive_type is intermediate_type_inference.PrimitiveType.STR:
                    # NOTE (mristin):
                    # We do not use the native ``Length`` as it counts the UTF-16
                    # code units instead of the characters, unlike Python. See
                    # ``Common.StringHelpers.Len`` in the generated common module.
                    return (
                        Stripped(
                            f"{csharp_common.COMMON_CLASS}.StringHelpers.Len({args[0]})"
                        ),
                        None,
                    )

                elif (
                    primitive_type
                    is intermediate_type_inference.PrimitiveType.BYTEARRAY
                ):
                    return Stripped(f"{collection}.Length"), None

                elif isinstance(
                    arg_type,
                    (
                        intermediate_type_inference.ListTypeAnnotation,
                        intermediate_type_inference.SetTypeAnnotation,
                    ),
                ):
                    return Stripped(f"{collection}.Count"), None

                elif isinstance(
                    arg_type, intermediate_type_inference.TupleTypeAnnotation
                ):
                    return (
                        Stripped(
                            f"{csharp_common.COMMON_CLASS}.TupleHelpers.Len({args[0]})"
                        ),
                        None,
                    )

                # NOTE (mristin):
                # A JSON-able array is a ``Nodes.JsonArray`` and a JSON-able
                # object a ``Nodes.JsonObject``, and both count their items
                # the same way. A JSON-able *value* has no length at all --
                # the type inference refuses it before we get here.
                elif isinstance(
                    arg_type,
                    (
                        intermediate_type_inference.JsonArrayTypeAnnotation,
                        intermediate_type_inference.JsonObjectTypeAnnotation,
                    ),
                ):
                    return Stripped(f"{collection}.Count"), None

                else:
                    return None, Error(
                        node.original_node,
                        f"We do not know how to compute the length on type {arg_type}",
                        errors,
                    )

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.ABS
            ):
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                arg = args[0]
                if self._is_declared_nullable(node.args[0]):
                    arg = Stripped(f"{arg}.Value")

                return Stripped(f"System.Math.Abs({arg})"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.INT
            ):
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                # NOTE (mristin):
                # We do not use the native ``long.Parse`` as it depends on
                # the culture, and accepts the numbers beyond the safe integers.
                # See ``ParseSafeInt`` in the generated common class.
                return (
                    Stripped(f"{csharp_common.COMMON_CLASS}.ParseSafeInt({args[0]})"),
                    None,
                )

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.LIST
            ):
                assert len(node.args) == 1, (
                    f"Expected exactly one argument, but got: {node.args}; "
                    f"this should have been caught before."
                )

                the_list, error = self.transform(node.args[0])
                if error is not None:
                    return None, Error(
                        node.original_node,
                        "Failed to transpile the argument of list",
                        [error],
                    )

                assert the_list is not None

                # NOTE (mristin):
                # The type inference allows ``list(...)`` only to copy a list,
                # which we transpile as ``ToList``.
                if not isinstance(
                    node.args[0],
                    (
                        parse_tree.Member,
                        parse_tree.FunctionCall,
                        parse_tree.MethodCall,
                        parse_tree.Name,
                        parse_tree.Index,
                    ),
                ):
                    the_list = Stripped(f"({the_list})")

                return Stripped(f"{the_list}.ToList()"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.SET
            ):
                set_type, error_message = generate_type(self.type_map[node])
                if error_message is not None:
                    return None, Error(node.original_node, error_message)

                return Stripped(f"new {set_type}()"), None

            else:
                assert_never(func_type.func.kind)
        else:
            assert_never(func_type)

        raise AssertionError("Should not have gotten here")

    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.value is None:
            return Stripped("null"), None
        elif isinstance(node.value, bool):
            return Stripped("true" if node.value else "false"), None
        elif isinstance(node.value, (int, float)):
            return Stripped(str(node.value)), None
        elif isinstance(node.value, str):
            return Stripped(csharp_common.string_literal(node.value)), None
        else:
            assert_never(node.value)

        raise AssertionError("Should not have gotten here")

    def transform_is_none(
        self, node: parse_tree.IsNone
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        value, error = self.transform(node.value)
        if error is not None:
            return None, error

        no_parentheses_types = (
            parse_tree.Name,
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
        )
        if isinstance(node.value, no_parentheses_types):
            return Stripped(f"{value} == null"), None
        else:
            return Stripped(f"({value}) == null"), None

    def transform_is_not_none(
        self, node: parse_tree.IsNotNone
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        value, error = self.transform(node.value)
        if error is not None:
            return None, error

        no_parentheses_types_in_this_context = (
            parse_tree.Name,
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
        )
        if isinstance(node.value, no_parentheses_types_in_this_context):
            return Stripped(f"{value} != null"), None
        else:
            return Stripped(f"({value}) != null"), None

    @abc.abstractmethod
    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        raise NotImplementedError

    def transform_not(
        self, node: parse_tree.Not
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        operand, error = self.transform(node.operand)
        if error is not None:
            return None, error

        no_parentheses_types_in_this_context = (
            parse_tree.Name,
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
        )
        if not isinstance(node.operand, no_parentheses_types_in_this_context):
            return Stripped(f"!({operand})"), None
        else:
            return Stripped(f"!{operand}"), None

    def transform_and(
        self, node: parse_tree.And
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        values: List[Stripped] = []

        for value_node in node.values:
            value, error = self.transform(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert value is not None

            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.Comparison,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.IsInstance,
                parse_tree.Index,
                parse_tree.Slice,
            )

            if not isinstance(value_node, no_parentheses_types_in_this_context):
                # NOTE (mristin):
                # This is a very rudimentary heuristic for breaking the lines, and can
                # be greatly improved by rendering into C# code. However, at this point,
                # we lack time for more sophisticated reformatting approaches.
                if "\n" in value:
                    value = Stripped(
                        f"""\
(
{I}{indent_but_first_line(value, I)}
)"""
                    )
                else:
                    value = Stripped(f"({value})")

            values.append(value)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the conjunction", errors
            )

        writer = io.StringIO()
        for i, value in enumerate(values):
            if i == 0:
                writer.write(value)
            else:
                writer.write(f"\n&& {value}")

        return Stripped(writer.getvalue()), None

    def transform_or(
        self, node: parse_tree.Or
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        values: List[Stripped] = []

        for value_node in node.values:
            value, error = self.transform(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert value is not None

            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.Comparison,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.IsInstance,
                parse_tree.Index,
                parse_tree.Slice,
            )

            if not isinstance(value_node, no_parentheses_types_in_this_context):
                # NOTE (mristin):
                # This is a very rudimentary heuristic for breaking the lines, and can
                # be greatly improved by rendering into C# code. However, at this point,
                # we lack time for more sophisticated reformatting approaches.
                if "\n" in value:
                    value = Stripped(
                        f"""\
(
{I}{indent_but_first_line(value, I)}
)"""
                    )
                else:
                    value = Stripped(f"({value})")

            values.append(value)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the conjunction", errors
            )

        writer = io.StringIO()
        for i, value in enumerate(values):
            if i == 0:
                writer.write(value)
            else:
                writer.write(f"\n|| {value}")

        return Stripped(writer.getvalue()), None

    def _transform_as_method_argument(
        self, node: parse_tree.Expression
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Transpile the ``node`` and unwrap it if it is a nullable value type."""
        code, error = self.transform(node)
        if error is not None:
            return None, error

        assert code is not None

        if self._is_declared_nullable(node):
            return Stripped(f"{code}.Value"), None

        return code, None

    def transform_mod(
        self, node: parse_tree.Mod
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        left, error = self._transform_as_method_argument(node.left)
        if error is not None:
            errors.append(error)

        right, error = self._transform_as_method_argument(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the modulo operation", errors
            )

        # NOTE (mristin):
        # We deliberately do not use the native C# operator ``%``. C# truncates
        # the division towards zero so that its remainder takes the sign of
        # the dividend (``-7 % 3 == -1``). The meta-model is written in Python where
        # the division is floored so that the remainder takes the sign of the divisor
        # (``-7 % 3 == 2``). The two only coincide for the operands of the same sign,
        # but the invariants must behave the same in all the SDKs for all the inputs.
        # Hence, we call the helper which computes the floored remainder, see
        # :py:data:`aas_core_codegen.csharp.lib._generate_verification.FLOOR_MOD`.
        #
        # However, a length is never negative. When the dividend is a length and
        # the divisor is either a length or a positive integer literal, both operands
        # are non-negative, so the native operator gives the same remainder as
        # the floored division. We use the native operator in that case, so that
        # the remainder is an ``int`` as all the other lengths, *e.g.*,
        # ``len(text) % 2``.
        length = intermediate_type_inference.PrimitiveType.LENGTH
        if intermediate_type_inference.try_primitive_type(
            self.type_map[node.left]
        ) is length and (
            intermediate_type_inference.try_primitive_type(self.type_map[node.right])
            is length
            or (
                isinstance(node.right, parse_tree.Constant)
                and isinstance(node.right.value, int)
                and not isinstance(node.right.value, bool)
                and node.right.value > 0
            )
        ):
            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.Constant,
                parse_tree.Name,
                parse_tree.Index,
            )

            if not isinstance(node.left, no_parentheses_types_in_this_context):
                left = Stripped(f"({left})")

            if not isinstance(node.right, no_parentheses_types_in_this_context):
                right = Stripped(f"({right})")

            return Stripped(f"{left} % {right}"), None

        code = Stripped(f"{csharp_common.COMMON_CLASS}.FloorMod({left}, {right})")

        # NOTE (mristin):
        # The helper always returns a ``long``. If the result is a length, *e.g.*,
        # ``len(text) % -2``, we narrow it to ``int`` so that it can be used as
        # a length, *e.g.*, as an index. The narrowing fails loudly instead of
        # silently overflowing.
        if (
            intermediate_type_inference.try_primitive_type(self.type_map[node])
            is length
        ):
            code = Stripped(f"checked((int){code})")

        return code, None

    def _transform_add_or_sub(
        self, node: Union[parse_tree.Add, parse_tree.Sub]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        left, error = self.transform(node.left)
        if error is not None:
            errors.append(error)

        right, error = self.transform(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            operation_name: str

            if isinstance(node, parse_tree.Add):
                operation_name = "the addition"
            elif isinstance(node, parse_tree.Sub):
                operation_name = "the subtraction"
            else:
                assert_never(node)

            return None, Error(
                node.original_node, f"Failed to transpile {operation_name}", errors
            )

        no_parentheses_types_in_this_context = (
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
            parse_tree.Constant,
            parse_tree.Name,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
        )

        if not isinstance(node.left, no_parentheses_types_in_this_context):
            left = Stripped(f"({left})")

        if not isinstance(node.right, no_parentheses_types_in_this_context):
            right = Stripped(f"({right})")

        if isinstance(node, parse_tree.Add):
            return Stripped(f"{left} + {right}"), None
        elif isinstance(node, parse_tree.Sub):
            return Stripped(f"{left} - {right}"), None
        else:
            assert_never(node)

    def transform_add(
        self, node: parse_tree.Add
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_add_or_sub(node)

    def transform_sub(
        self, node: parse_tree.Sub
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_add_or_sub(node)

    def transform_neg(
        self, node: parse_tree.Neg
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        operand, error = self.transform(node.operand)
        if error is not None:
            return None, Error(
                node.original_node,
                "Failed to transpile the arithmetic negation",
                [error],
            )

        # NOTE (mristin):
        # We have to put a negative constant in parentheses as well, since ``--1``
        # would be parsed as a decrement in C#.
        no_parentheses_types_in_this_context = (
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
            parse_tree.Name,
            parse_tree.Index,
        )

        if not isinstance(node.operand, no_parentheses_types_in_this_context):
            operand = Stripped(f"({operand})")

        return Stripped(f"-{operand}"), None

    def transform_joined_str(
        self, node: parse_tree.JoinedStr
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        parts: List[str] = []
        needs_interpolation = False
        for value in node.values:
            if isinstance(value, str):
                string_literal = csharp_common.string_literal(
                    value.replace("{", "{{").replace("}", "}}")
                )

                # We need to remove double-quotes since we are joining everything
                # ourselves later.

                assert string_literal.startswith('"') and string_literal.endswith('"')

                string_literal_wo_quotes = string_literal[1:-1]
                parts.append(string_literal_wo_quotes)

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self.transform(value.value)
                if error is not None:
                    return None, error

                assert code is not None

                assert (
                    "\n" not in code
                ), f"New-lines are not expected in formatted values, but got: {code}"

                needs_interpolation = True
                parts.append(f"{{{code}}}")
            else:
                assert_never(value)

        writer = io.StringIO()
        if needs_interpolation:
            writer.write('$"')
        else:
            writer.write('"')

        for part in parts:
            writer.write(part)

        writer.write('"')

        return Stripped(writer.getvalue()), None

    def _transform_any_or_all(
        self, node: Union[parse_tree.Any, parse_tree.All]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        iteration: Optional[Stripped] = None
        start: Optional[Stripped] = None
        end: Optional[Stripped] = None

        if isinstance(node.generator, parse_tree.ForEach):
            iteration, error = self.transform(node.generator.iteration)
            if error is not None:
                errors.append(error)
        elif isinstance(node.generator, parse_tree.ForRange):
            start, error = self.transform(node.generator.start)
            if error is not None:
                errors.append(error)

            end, error = self.transform(node.generator.end)
            if error is not None:
                errors.append(error)

        else:
            assert_never(node.generator)

        if len(errors) > 0:
            return None, Error(
                node.original_node,
                "Failed to transpile the generator expression",
                errors,
            )

        assert (iteration is not None) ^ (start is not None and end is not None)

        variable_name = node.generator.variable.identifier
        variable_type = self.type_map[node.generator.variable]

        try:
            self._environment.set(
                identifier=variable_name, type_annotation=variable_type
            )
            self._variable_name_set.add(variable_name)

            condition, error = self.transform(node.condition)
            if error is not None:
                errors.append(error)

            variable, error = self.transform(node.generator.variable)
            if error is not None:
                errors.append(error)

        finally:
            self._variable_name_set.remove(variable_name)
            self._environment.remove(variable_name)

        if len(errors) > 0:
            return None, Error(
                node.original_node,
                "Failed to transpile the generator expression",
                errors,
            )

        assert variable is not None
        assert condition is not None

        qualifier_function: str

        if isinstance(node, parse_tree.Any):
            qualifier_function = "Any"
        elif isinstance(node, parse_tree.All):
            qualifier_function = "All"
        else:
            assert_never(node)

        source: Stripped

        if isinstance(node.generator, parse_tree.ForEach):
            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.Index,
                parse_tree.Slice,
            )

            if not isinstance(
                node.generator.iteration, no_parentheses_types_in_this_context
            ):
                source = Stripped(f"({iteration})")
            else:
                assert iteration is not None
                source = iteration

        elif isinstance(node.generator, parse_tree.ForRange):
            assert start is not None
            assert end is not None

            is_integer_range = (
                intermediate_type_inference.try_primitive_type(
                    self.type_map[node.generator.variable]
                )
                is intermediate_type_inference.PrimitiveType.INT
            )

            # NOTE (mristin):
            # ``Enumerable.Range`` expects the count instead of the end, and throws
            # on a negative count, while the range in Python is simply empty if
            # the end precedes the start. Hence, we clamp the count at zero, unless
            # the range goes from zero to a length, which is never negative.
            if start == "0" and not is_integer_range:
                count = end
            else:
                zero = "0L" if is_integer_range else "0"
                count = Stripped(f"System.Math.Max({zero}, {end} - {start})")

            # NOTE (mristin):
            # ``Enumerable.Range`` works only on ``int``'s, while the integers
            # of the meta-model are ``long``'s. We narrow the start and the count
            # explicitly, and fail loudly instead of silently overflowing.
            if is_integer_range:
                if isinstance(node.generator.start, parse_tree.Name):
                    start = Stripped(f"checked((int){start})")
                elif not isinstance(node.generator.start, parse_tree.Constant):
                    start = Stripped(f"checked((int)({start}))")

                count = Stripped(f"checked((int){count})")

            source = Stripped(
                f"""\
Enumerable.Range(
{I}{indent_but_first_line(start, I)},
{I}{indent_but_first_line(count, I)}
)"""
            )

        else:
            assert_never(node.generator)

        return (
            Stripped(
                f"""\
{source}.{qualifier_function}(
{I}{variable} => {indent_but_first_line(condition, II)})"""
            ),
            None,
        )

    def transform_any(
        self, node: parse_tree.Any
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_any_or_all(node)

    def transform_all(
        self, node: parse_tree.All
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_any_or_all(node)

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        value, error = self._transform_and_unwrap_narrowed_nullable_value(node.value)
        if error is not None:
            errors.append(error)

        target: Optional[Stripped] = None
        if (
            isinstance(node.target, parse_tree.Name)
            and self._environment.find(identifier=node.target.identifier) is None
        ):
            # NOTE (mristin):
            # This is a variable definition as we did not specify the identifier
            # in the environment.

            type_anno = self.type_map[node.target]
            self._variable_name_set.add(node.target.identifier)
            self._environment.set(
                identifier=node.target.identifier, type_annotation=type_anno
            )

            target, error = self.transform_name(node=node.target)
            if error is not None:
                errors.append(error)
            elif (
                node.annotation is not None
                and isinstance(node.value, parse_tree.Name)
                and self.type_map[node.target] is self.type_map[node.value]
            ):
                # NOTE (mristin):
                # An immutable alias shares the type annotation of the aliased
                # variable, see
                # :py:meth:`intermediate_type_inference._Inferrer.transform_assignment`,
                # so we infer its type with ``var``. This way, the alias of a generic
                # sequence is also declared as ``IReadOnlyList<T>``, see
                # :py:func:`intermediate.generic_sequence_item_class`.
                target = Stripped(f"var {target}")
            elif node.annotation is not None:
                # NOTE (mristin):
                # We spell out the declared type, as it might differ from the type
                # of the value, *e.g.*, for ``null``.
                declared_type, error_message = generate_type(type_anno)
                if error_message is not None:
                    errors.append(Error(node.annotation.original_node, error_message))
                else:
                    target = Stripped(f"{declared_type} {target}")
            elif (
                isinstance(
                    type_anno, intermediate_type_inference.PrimitiveTypeAnnotation
                )
                and type_anno.a_type is intermediate_type_inference.PrimitiveType.INT
            ):
                # NOTE (mristin):
                # The integers of the meta-model are ``long``'s in C#, while
                # C# infers ``int`` for the integer literals with ``var``, so
                # that the subsequent assignments of ``long``'s would fail.
                target = Stripped(f"long {target}")
            else:
                target = Stripped(f"var {target}")
        else:
            # NOTE (mristin):
            # The properties are settable in C#, and the index access resolves
            # the negative literal indices, so we can assign to the members and
            # the items of the lists directly.
            target, error = self.transform(node=node.target)
            if error is not None:
                errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assignment", errors
            )

        assert target is not None
        assert value is not None

        target_type = self.type_map[node.target]
        value_type = self.type_map[node.value]
        if intermediate_type_inference.needs_wrapping_into_named_union(
            target_type=target_type, value_type=value_type
        ):
            # NOTE (mristin):
            # A named union is a wrapper class in C#, so we wrap the instance
            # as the most specific root of the union.
            union_type = intermediate_type_inference.beneath_optional(target_type)
            assert isinstance(union_type, intermediate_type_inference.OurTypeAnnotation)
            assert isinstance(union_type.our_type, intermediate.NamedUnion)
            assert isinstance(value_type, intermediate_type_inference.OurTypeAnnotation)
            assert isinstance(value_type.our_type, intermediate.Class)

            root = union_type.our_type.most_specific_root_of(value_type.our_type)

            union_name = csharp_naming.class_name(union_type.our_type.name)
            from_method_name = csharp_naming.method_name(
                Identifier(f"from_{root.name}")
            )
            value = Stripped(f"Our.{union_name}.{from_method_name}({value})")

        # NOTE (mristin):
        # This is a rudimentary heuristic for basic line breaks, but works well in
        # practice.
        if "\n" not in value and len(value) > 50:
            return (
                Stripped(
                    f"""\
{target} = (
{I}{indent_but_first_line(value, I)});"""
                ),
                None,
            )

        return Stripped(f"{target} = {value};"), None

    def transform_return(
        self, node: parse_tree.Return
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.value is None:
            return Stripped("return;"), None

        # NOTE (mristin):
        # The type inference records the return type of the function on the return.
        # A narrowed nullable value type needs to be unwrapped only if the function
        # returns a non-optional.
        value, error = (
            self.transform(node.value)
            if isinstance(
                self.type_map[node], intermediate_type_inference.OptionalTypeAnnotation
            )
            else self._transform_and_unwrap_narrowed_nullable_value(node.value)
        )
        if error is not None:
            return None, error

        assert value is not None

        # NOTE (mristin):
        # This is a rudimentary heuristic for basic line breaks, but works well in
        # practice.
        if "\n" not in value and len(value) > 50:
            return (
                Stripped(
                    f"""\
return (
{I}{indent_but_first_line(value, I)});"""
                ),
                None,
            )

        return Stripped(f"return {value};"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_branch(
        self, statements: Sequence[parse_tree.StatementUnion]
    ) -> Tuple[Optional[Tuple[List[Stripped], bool]], Optional[Error]]:
        """
        Transpile the ``statements`` of a block in a new scope.

        The block is a branch of a switch or of an if-statement, or the body of
        a for-loop. The variables defined in the ``statements`` are not visible
        after the block.

        Return the transpiled statements, and whether they define any variables.
        We leave the layout of the statements to the caller.
        """
        parent_environment = self._environment
        scope_environment = intermediate_type_inference.MutableEnvironment(
            parent=parent_environment
        )
        self._environment = scope_environment

        errors: List[Error] = []
        stmts: List[Stripped] = []
        try:
            for stmt in statements:
                code, error = self.transform(stmt)
                if error is not None:
                    errors.append(error)
                    continue

                assert code is not None
                stmts.append(code)
        finally:
            self._environment = parent_environment

        if len(errors) > 0:
            return None, Error(
                None, "Failed to transpile the statements of a block", errors
            )

        return (stmts, len(scope_environment.mapping) > 0), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_switch(
        self, node: parse_tree.Switch
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        subject, error = self.transform(node.subject)
        if error is not None:
            return None, error

        assert subject is not None

        errors: List[Error] = []

        # NOTE (mristin):
        # We collect the headers of the clauses together with their statements, and
        # treat the default as the last clause.
        clauses: List[Tuple[str, Sequence[parse_tree.StatementUnion]]] = []

        for case in node.cases:
            headers: List[str] = []
            for label in case.labels:
                label_code, error = self.transform(label)
                if error is not None:
                    errors.append(error)
                    continue

                assert label_code is not None
                headers.append(f"case {label_code}:")

            clauses.append(("\n".join(headers), case.body))

        if node.default is not None:
            clauses.append(("default:", node.default))

        writer = io.StringIO()
        writer.write(f"switch ({subject})\n{{")

        for header, statements in clauses:
            stmts_and_defines, error = self._transform_branch(statements)
            if error is not None:
                errors.append(error)
                continue

            assert stmts_and_defines is not None
            stmts, defines_variables = stmts_and_defines

            # NOTE (mristin):
            # C# does not allow the fall-through, so we end the clause with
            # a ``break`` if its execution can complete.
            if parse_tree.can_complete_normally(statements):
                stmts = stmts + [Stripped("break;")]

            writer.write("\n")
            writer.write(textwrap.indent(header, I))

            # NOTE (mristin):
            # We enclose the statements in a block only if they define variables
            # since all the clauses of a switch share the same scope otherwise.
            if defines_variables:
                writer.write(f"\n{II}{{")
                for stmt in stmts:
                    writer.write("\n")
                    writer.write(textwrap.indent(stmt, III))
                writer.write(f"\n{II}}}")
            else:
                for stmt in stmts:
                    writer.write("\n")
                    writer.write(textwrap.indent(stmt, II))

        writer.write("\n}")

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the switch", errors
            )

        return Stripped(writer.getvalue()), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_for(
        self, node: parse_tree.For
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        variable_name = node.generator.variable.identifier
        variable_type = self.type_map[node.generator.variable]
        variable = csharp_naming.variable_name(variable_name)

        header: Optional[str] = None
        if isinstance(node.generator, parse_tree.ForEach):
            iteration, error = self.transform(node.generator.iteration)
            if error is not None:
                errors.append(error)
            else:
                assert iteration is not None
                header = (
                    f"foreach (var {variable} in "
                    f"{indent_but_first_line(iteration, I)})"
                )

        elif isinstance(node.generator, parse_tree.ForRange):
            start, error = self.transform(node.generator.start)
            if error is not None:
                errors.append(error)

            end, error = self.transform(node.generator.end)
            if error is not None:
                errors.append(error)

            # NOTE (mristin):
            # The lengths of the collections are ``int``'s in C#, and so are
            # the indices of the lists, while the integers of the meta-model are
            # ``long``'s.
            assert isinstance(
                variable_type, intermediate_type_inference.PrimitiveTypeAnnotation
            )
            if variable_type.a_type is intermediate_type_inference.PrimitiveType.LENGTH:
                variable_type_code = "int"
            elif variable_type.a_type is intermediate_type_inference.PrimitiveType.INT:
                variable_type_code = "long"
            else:
                raise AssertionError(f"Unexpected {variable_type=}")

            if start is not None and end is not None:
                if "\n" not in start and "\n" not in end:
                    header = (
                        f"for ({variable_type_code} {variable} = {start}; "
                        f"{variable} < {end}; {variable}++)"
                    )
                else:
                    header = f"""\
for (
{I}{variable_type_code} {variable} = {indent_but_first_line(start, I)};
{I}{variable} < {indent_but_first_line(end, I)};
{I}{variable}++
)"""

        else:
            assert_never(node.generator)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the for-loop", errors
            )

        assert header is not None

        # NOTE (mristin):
        # The loop variable is scoped to the loop, so we define it in its own
        # environment enclosing the body.
        parent_environment = self._environment
        loop_environment = intermediate_type_inference.MutableEnvironment(
            parent=parent_environment
        )
        loop_environment.set(identifier=variable_name, type_annotation=variable_type)
        self._variable_name_set.add(variable_name)

        self._environment = loop_environment
        try:
            stmts_and_defines, error = self._transform_branch(node.body)
        finally:
            self._environment = parent_environment

        if error is not None:
            return None, Error(
                node.original_node, "Failed to transpile the for-loop", [error]
            )

        assert stmts_and_defines is not None
        stmts, _ = stmts_and_defines

        writer = io.StringIO()
        writer.write(f"{header}\n{{")
        for stmt in stmts:
            writer.write("\n")
            writer.write(textwrap.indent(stmt, I))
        writer.write("\n}")

        return Stripped(writer.getvalue()), None

    def transform_continue(
        self, node: parse_tree.Continue
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return Stripped("continue;"), None

    def transform_break(
        self, node: parse_tree.Break
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return Stripped("break;"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_assert(
        self, node: parse_tree.Assert
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        # NOTE (mristin):
        # We transpile the negation of the condition as a ``not`` so that
        # the operand is parenthesized the same way as elsewhere.
        negation, error = self.transform_not(
            parse_tree.Not(
                operand=node.condition, original_node=node.condition.original_node
            )
        )
        if error is not None:
            errors.append(error)

        message: Optional[Stripped] = None
        if node.message is None:
            message = csharp_common.string_literal(
                f"Assertion failed: {ast.unparse(node.condition.original_node)}"
            )
        else:
            message, error = self.transform(node.message)
            if error is not None:
                errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assertion", errors
            )

        assert negation is not None
        assert message is not None

        if "\n" in negation:
            header = f"""\
if (
{I}{indent_but_first_line(negation, I)}
)"""
        else:
            header = f"if ({negation})"

        return (
            Stripped(
                f"""\
{header}
{{
{I}throw new System.InvalidOperationException(
{II}{indent_but_first_line(message, II)}
{I});
}}"""
            ),
            None,
        )

    def transform_expression_statement(
        self, node: parse_tree.ExpressionStatement
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        expression, error = self.transform(node.expression)
        if error is not None:
            return None, error

        assert expression is not None
        return Stripped(f"{expression};"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_if(
        self, node: parse_tree.If
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        # NOTE (mristin):
        # We collect the headers of the branches together with their statements, and
        # treat the default as the last branch.
        branches: List[Tuple[str, Sequence[parse_tree.StatementUnion]]] = []

        for i, branch in enumerate(node.branches):
            condition, error = self.transform(branch.condition)
            if error is not None:
                errors.append(error)
                continue

            assert condition is not None

            keyword = "if" if i == 0 else "else if"
            if "\n" in condition:
                header = f"""\
{keyword} (
{I}{indent_but_first_line(condition, I)}
)"""
            else:
                header = f"{keyword} ({condition})"

            branches.append((header, branch.body))

        if node.default is not None:
            branches.append(("else", node.default))

        writer = io.StringIO()

        for i, (header, statements) in enumerate(branches):
            stmts_and_defines, error = self._transform_branch(statements)
            if error is not None:
                errors.append(error)
                continue

            assert stmts_and_defines is not None
            stmts, _ = stmts_and_defines

            if i > 0:
                writer.write("\n")

            writer.write(f"{header}\n{{")
            for stmt in stmts:
                writer.write("\n")
                writer.write(textwrap.indent(stmt, I))
            writer.write("\n}")

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the if-statement", errors
            )

        return Stripped(writer.getvalue()), None


# noinspection PyProtectedMember,PyProtectedMember
assert all(op in Transpiler._CSHARP_COMPARISON_MAP for op in parse_tree.Comparator)
