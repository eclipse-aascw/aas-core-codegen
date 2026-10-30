"""Transpile Python to Java code."""
import abc
import ast
import io
import textwrap
from typing import (
    Final,
    Tuple,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Union,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    assert_never,
    Error,
    Identifier,
    indent_but_first_line,
    Stripped,
)
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.parse import tree as parse_tree


# NOTE (empwilli):
# We have to implement a very similar function for generating type annotations to
# aas_core_codegen.golang.common.generate_type since we can not simply pass
# intermediate_type_inference.TypeAnnotationUnion to
# aas_core_codegen.golang.common.generate_type.

PRIMITIVE_TYPE_MAP = {
    intermediate_type_inference.PrimitiveType.BOOL: Stripped("Boolean"),
    intermediate_type_inference.PrimitiveType.INT: Stripped("Long"),
    intermediate_type_inference.PrimitiveType.FLOAT: Stripped("Double"),
    intermediate_type_inference.PrimitiveType.STR: Stripped("String"),
    intermediate_type_inference.PrimitiveType.BYTEARRAY: Stripped("byte[]"),
}


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def generate_type(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the Java type for the given type annotation.

    If ``types_package`` is specified, it is prepended to all our types.

    (empwilli): We do not handle all the type annotations from
    :py:mod:`aas_core_codegen.intermediate.type_inference` as that would be
    YAGNI (*e.g.*, verification functions, built-in functions *etc.*).
    If we do not know how to generate the type in Java, we return an error message.
    """
    if isinstance(type_annotation, intermediate_type_inference.PrimitiveTypeAnnotation):
        return PRIMITIVE_TYPE_MAP[type_annotation.a_type], None

    elif isinstance(type_annotation, intermediate_type_inference.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(java_naming.enum_name(type_annotation.our_type.name)), None

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return java_common.PRIMITIVE_TYPE_MAP[our_type.constrainee], None

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # NOTE (empwilli):
            # We always refer to interfaces even in cases of concrete classes without
            # concrete descendants since we want to allow enhancing.

            return Stripped(java_naming.interface_name(our_type.name)), None

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is represented as a wrapper class in Java.
            return Stripped(java_naming.union_name(our_type.name)), None

    elif isinstance(type_annotation, intermediate_type_inference.ListTypeAnnotation):
        item_type, error = generate_type(type_annotation=type_annotation.items)
        if error is not None:
            return None, error

        return Stripped(f"List<{item_type}>"), None

    elif isinstance(type_annotation, intermediate_type_inference.SetTypeAnnotation):
        item_type, error = generate_type(type_annotation=type_annotation.items)
        if error is not None:
            return None, error

        return Stripped(f"Set<{item_type}>"), None

    elif isinstance(type_annotation, intermediate_type_inference.TupleTypeAnnotation):
        item_types: List[Stripped] = []
        for item in type_annotation.items:
            item_type, error = generate_type(type_annotation=item)
            if error is not None:
                return None, error

            assert item_type is not None
            item_types.append(item_type)

        assert len(item_types) <= java_common.MAX_TUPLE_ARITY, (
            f"We only pre-generate Tuple1 .. Tuple{java_common.MAX_TUPLE_ARITY} "
            f"in the common package, but got a tuple of arity {len(item_types)}. "
            f"Please contact the developers if you need larger tuples."
        )

        joined_item_types = ", ".join(item_types)
        tuple_type_name = f"Tuple{len(item_types)}"

        return Stripped(f"{tuple_type_name}<{joined_item_types}>"), None

    elif isinstance(
        type_annotation, intermediate_type_inference.OptionalTypeAnnotation
    ):
        value_type, error = generate_type(type_annotation=type_annotation.value)
        if error is not None:
            return None, error

        return Stripped(f"Optional<{value_type}>"), None

    else:
        return None, Error(
            None,
            f"(empwilli): We do not handle "
            f"the type annotation {type_annotation} from "
            "aas_core_codegen.intermediate.type_inference as that was, "
            "at this time point, YAGNI (*e.g.*, verification functions, "
            "built-in functions *etc.*). If you need this feature, please "
            "contact the developers.",
        )

    raise AssertionError("Should not have gotten here")


def _is_parenthesized_is_instance(node: parse_tree.Node) -> bool:
    """
    Check whether ``node`` is an ``isinstance`` transpiled with parentheses.

    We always parenthesize the disjunction of ``instanceof`` checks when
    an ``isinstance`` is checked against multiple classes.
    """
    return isinstance(node, parse_tree.IsInstance) and len(node.classes) > 1


#: Map the primitive types to the primitive Java types which unbox their values,
#: see :py:meth:`Transpiler.transform_comparison`
_UNBOXED_TYPE_BY_PRIMITIVE_TYPE: Final[
    Mapping[intermediate_type_inference.PrimitiveType, str]
] = {
    intermediate_type_inference.PrimitiveType.BOOL: "boolean",
    intermediate_type_inference.PrimitiveType.INT: "long",
    intermediate_type_inference.PrimitiveType.FLOAT: "double",
}

#: List the nodes which are transpiled to Java primitives, and never to boxed values,
#: see :py:meth:`Transpiler.transform_comparison`
_CERTAINLY_PRIMITIVE_NODE_TYPES: Final = (
    parse_tree.Constant,
    parse_tree.Add,
    parse_tree.Sub,
    parse_tree.Mod,
    parse_tree.Neg,
)


class Transpiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a node of our AST to Java code, or return an error."""

    _JAVA_COMPARISON_MAP: Final[Mapping[parse_tree.Comparator, str]] = {
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
        optional_map: Mapping[parse_tree.Node, bool],
        environment: intermediate_type_inference.Environment,
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
    ) -> None:
        """Initialize with the given values."""
        self.type_map = type_map
        self._optional_map = optional_map
        self._downcast_map = downcast_map
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )

        # Keep track of the optionals which we use as ``Optional``, *e.g.*, in
        # the is-none checks or as optional arguments, where we must not call
        # ``.get()``.
        self._beneath_none_check: Set[parse_tree.Node] = set()

        # Keep track of the values passed to the setters and to ``List.set``, which
        # expect ``null`` instead of an empty optional. Thus, we have to unpack
        # the value and fall back if it is not set.
        self._beneath_call: Set[parse_tree.Node] = set()

        # Keep track whenever we define a variable name, so that we can know how to
        # generate the reference in the Java code.
        self._variable_name_set: Set[Identifier] = set()

    def _unwrap_if_optional(
        self, node: parse_tree.Name, variable: Stripped
    ) -> Stripped:
        """
        Unwrap the ``variable`` referenced by ``node`` if it holds an ``Optional``.

        We unwrap an optional variable analogously to an optional property, see
        :py:meth:`transform_member`.
        """
        if not self._optional_map[node] or node in self._beneath_none_check:
            return variable

        if node in self._beneath_call:
            return Stripped(f"{variable}.orElse(null)")

        return Stripped(f"{variable}.get()")

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
        # The value has been narrowed down by an ``isinstance`` guard, so we need
        # to down-cast it. A named union is represented as a wrapper class in Java,
        # so we need to down-cast its underlying instance.
        if isinstance(downcast.source.our_type, intermediate.NamedUnion):
            code = Stripped(f"{code}.getUnderlying()")

        interface_name = java_naming.interface_name(downcast.target.our_type.name)

        return Stripped(f"(({interface_name}) {code})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_member(
        self, node: parse_tree.Member
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        instance, error = self.transform(node.instance)
        if error is not None:
            return None, error

        instance_type = intermediate_type_inference.beneath_optional(
            self.type_map[node.instance]
        )
        member_type = intermediate_type_inference.beneath_optional(self.type_map[node])

        # noinspection PyUnusedLocal
        member_name: str

        if isinstance(
            instance_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type.our_type, intermediate.Enumeration):
            # The member denotes a literal of an enumeration.
            member_name = java_naming.enum_literal_name(node.name)

        elif isinstance(member_type, intermediate_type_inference.MethodTypeAnnotation):
            member_name = java_naming.method_name(node.name)

        elif isinstance(
            instance_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type.our_type, intermediate.Class):
            if node.name in instance_type.our_type.properties_by_name:
                getter_name = java_naming.getter_name(node.name)

                if self._optional_map[node]:
                    if node in self._beneath_none_check:
                        member_name = f"{getter_name}()"
                    elif node in self._beneath_call:
                        member_name = f"{getter_name}().orElse(null)"
                    else:
                        member_name = f"{getter_name}().get()"
                else:
                    member_name = f"{getter_name}()"
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
                member_name = java_naming.enum_literal_name(node.name)
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

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_index(
        self, node: parse_tree.Index
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        collection_type = intermediate_type_inference.beneath_optional(
            self.type_map[node.collection]
        )

        if isinstance(collection_type, intermediate_type_inference.TupleTypeAnnotation):
            collection, error = self.transform(node.collection)
            if error is not None:
                return None, error

            assert isinstance(node.index, parse_tree.Constant) and isinstance(
                node.index.value, int
            ), (
                f"We expect only a literal integer constant as the index "
                f"of a tuple, since the arity of the tuple is fixed and "
                f"known at the code generation time, but got: {node.index}"
            )

            index_value = node.index.value
            if index_value < 0:
                index_value += len(collection_type.items)

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

            return Stripped(f"{collection}.item{index_value + 1}()"), None

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
            index = Stripped(f"{collection}.size() - {abs(index_as_int)}")

        elif (
            index_as_int is None
            and intermediate_type_inference.try_primitive_type(
                self.type_map[node.index]
            )
            is intermediate_type_inference.PrimitiveType.INT
        ):
            # NOTE (mristin):
            # We represent the integers as ``long``, while the lists are indexed
            # by ``int``'s in Java. We narrow the index explicitly, and fail loudly
            # instead of silently overflowing.
            index = Stripped(f"Math.toIntExact({index})")

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

        return Stripped(f"{collection}.get({index})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_as_long(
        self, node: parse_tree.Expression
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``node`` such that an integer literal or a length is a ``long``.

        We represent the integers as ``Long`` in Java, while we transpile the integer
        literals as ``int`` literals, and the lengths are ``int``'s. Java does not
        convert an ``int`` to ``Long`` implicitly, *e.g.*, when passing an integer
        literal or a length as an argument to a method expecting a ``Long``, so we
        need to suffix the literal with ``L``, and cast the length to ``long``.
        """
        if Transpiler._is_int_literal(node):
            assert isinstance(node, parse_tree.Constant)
            return Stripped(f"{node.value}L"), None

        code, error = self.transform(node)
        if error is not None:
            return None, error

        assert code is not None

        if (
            intermediate_type_inference.try_primitive_type(self.type_map[node])
            is intermediate_type_inference.PrimitiveType.LENGTH
        ):
            if isinstance(
                node,
                (
                    parse_tree.Member,
                    parse_tree.FunctionCall,
                    parse_tree.MethodCall,
                    parse_tree.Name,
                    parse_tree.Index,
                ),
            ):
                return Stripped(f"(long) {code}"), None

            return Stripped(f"(long) ({code})"), None

        return code, None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        item_exprs: List[Stripped] = []

        for value_node in node.values:
            # NOTE (mristin):
            # Java does not box an ``int`` to a ``Long`` item of a tuple.
            item_expr, error = self._transform_as_long(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert item_expr is not None
            item_exprs.append(item_expr)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the tuple literal", errors
            )

        return java_common.generate_tuple_literal(item_exprs=item_exprs), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_as_collection_member(
        self, node: parse_tree.Expression, collection_node: parse_tree.Expression
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``node`` to be looked up in or added to ``collection_node``.

        A set or a list of integers holds ``Long``'s, while the integer literals and
        the lengths are ``int``'s. Java boxes them to ``Integer``'s, which are never
        equal to any ``Long``, so ``contains`` would silently give ``false``.
        """
        collection_type = intermediate_type_inference.beneath_optional(
            self.type_map[collection_node]
        )
        if (
            isinstance(
                collection_type,
                (
                    intermediate_type_inference.SetTypeAnnotation,
                    intermediate_type_inference.ListTypeAnnotation,
                ),
            )
            and intermediate_type_inference.try_primitive_type(collection_type.items)
            is intermediate_type_inference.PrimitiveType.INT
        ):
            return self._transform_as_long(node)

        return self.transform(node)

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_list_literal(
        self, node: parse_tree.ListLiteral
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        items: List[Stripped] = []

        for item_node in node.items:
            item, error = self._transform_as_collection_member(
                node=item_node, collection_node=node
            )
            if error is not None:
                errors.append(error)
                continue

            assert item is not None
            items.append(item)

        list_type = self.type_map[node]
        assert isinstance(list_type, intermediate_type_inference.ListTypeAnnotation)

        # NOTE (mristin):
        # We spell out the items, since Java can not infer them when the new list
        # is wrapped, *e.g.*, in an ``Optional.of``.
        item_type, error = generate_type(list_type.items)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the list literal", errors
            )

        if len(items) == 0:
            return Stripped(f"new java.util.ArrayList<{item_type}>()"), None

        # NOTE (mristin):
        # The ``List.of`` gives an immutable list, so we copy it into
        # an ``ArrayList``, which can be appended to as the Python list.
        one_liner = (
            f"new java.util.ArrayList<{item_type}>("
            f"java.util.List.of({', '.join(items)}))"
        )
        if "\n" not in one_liner and len(one_liner) <= 80:
            return Stripped(one_liner), None

        items_joined = ",\n".join(items)
        return (
            Stripped(
                f"""\
new java.util.ArrayList<{item_type}>(
{I}java.util.List.of(
{II}{indent_but_first_line(items_joined, II)}
{I})
)"""
            ),
            None,
        )

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
        # We do not use the native ``substring`` as it counts the UTF-16 code units
        # instead of the characters, throws on the positions out of range, and does
        # not count the negative ones from the end, unlike Python. See
        # ``StringHelpers.slice`` in the generated common package.
        args: List[str] = [collection, start if start is not None else "0"]
        if end is not None:
            args.append(end)

        return Stripped(f"StringHelpers.slice({', '.join(args)})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_comparison(
        self, node: parse_tree.Comparison
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        comparator = Transpiler._JAVA_COMPARISON_MAP[node.op]

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

        # NOTE (mristin):
        # The operators ``==`` and ``!=`` compare the references of strings in Java,
        # so we need to compare their content explicitly.
        if node.op in (parse_tree.Comparator.EQ, parse_tree.Comparator.NE) and any(
            intermediate_type_inference.try_primitive_type(
                intermediate_type_inference.beneath_optional(self.type_map[operand])
            )
            is intermediate_type_inference.PrimitiveType.STR
            for operand in (node.left, node.right)
        ):
            equals = f"Objects.equals({left}, {right})"
            if node.op is parse_tree.Comparator.EQ:
                return Stripped(equals), None

            return Stripped(f"!{equals}"), None

        # NOTE (mristin):
        # Java orders neither the strings nor the booleans with the operators ``<``,
        # ``<=``, ``>`` and ``>=``. Moreover, ``String.compareTo`` would order
        # the strings by their UTF-16 code units, while Python orders them by their
        # characters (code points). Hence, we order the strings with our helpers,
        # and the booleans with ``Boolean.compare``, where ``false`` comes before
        # ``true`` as in Python.
        if node.op not in (parse_tree.Comparator.EQ, parse_tree.Comparator.NE):
            primitive_type = intermediate_type_inference.try_primitive_type(
                self.type_map[node.left]
            )

            if primitive_type is intermediate_type_inference.PrimitiveType.STR:
                return (
                    Stripped(
                        f"StringHelpers.compareByCodePoints({left}, {right}) "
                        f"{comparator} 0"
                    ),
                    None,
                )

            if primitive_type is intermediate_type_inference.PrimitiveType.BOOL:
                return (
                    Stripped(f"Boolean.compare({left}, {right}) {comparator} 0"),
                    None,
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

        if not (
            isinstance(node.left, no_parentheses_types)
            and isinstance(node.right, no_parentheses_types)
        ):
            left = Stripped(f"({left})")
            right = Stripped(f"({right})")

        # NOTE (mristin):
        # We represent the integers, the floats and the booleans as ``Long``'s,
        # ``Double``'s and ``Boolean``'s in the arguments, the properties and
        # the collections. The operators ``==`` and ``!=`` compare the references of
        # two such boxed values, which are equal only by chance, *e.g.*, for
        # the ``Long``'s between -128 and 127, which Java caches. Hence, we unbox
        # the left operand, unless an operand is certainly a primitive already, as
        # Java then unboxes the other operand itself.
        if node.op in (parse_tree.Comparator.EQ, parse_tree.Comparator.NE):
            left_primitive_type = intermediate_type_inference.try_primitive_type(
                self.type_map[node.left]
            )
            right_primitive_type = intermediate_type_inference.try_primitive_type(
                self.type_map[node.right]
            )

            unboxed_type = (
                _UNBOXED_TYPE_BY_PRIMITIVE_TYPE.get(left_primitive_type, None)
                if left_primitive_type is not None
                else None
            )

            if (
                unboxed_type is not None
                and right_primitive_type is not None
                and right_primitive_type
                is not intermediate_type_inference.PrimitiveType.LENGTH
                and not isinstance(node.left, _CERTAINLY_PRIMITIVE_NODE_TYPES)
                and not isinstance(node.right, _CERTAINLY_PRIMITIVE_NODE_TYPES)
            ):
                left = Stripped(f"({unboxed_type}) {left}")

        return Stripped(f"{left} {comparator} {right}"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_is_in(
        self, node: parse_tree.IsIn
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []

        member, error = self._transform_as_collection_member(
            node=node.member, collection_node=node.container
        )
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
        # A JSON-able object is an ``ObjectNode``, so the membership is
        # a question about its field names.
        if isinstance(
            container_type, intermediate_type_inference.JsonObjectTypeAnnotation
        ):
            return Stripped(f"{container}.has({member})"), None

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

        return Stripped(f"{container}.contains({member})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_is_instance(
        self, node: parse_tree.IsInstance
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        value, error = self.transform(node.value)
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

        # NOTE (mristin):
        # A named union is represented as a wrapper class in Java, so we need to
        # check the type of its underlying instance.
        value_type = self.type_map[node.value]
        if isinstance(
            value_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(value_type.our_type, intermediate.NamedUnion):
            value = Stripped(f"{value}.getUnderlying()")

        checks = [
            f"{value} instanceof {java_naming.interface_name(cls.identifier)}"
            for cls in node.classes
        ]

        if len(checks) == 1:
            return Stripped(checks[0]), None

        # NOTE (mristin):
        # We always parenthesize the disjunction so that the check can be used
        # as an operand of a conjunction or a disjunction without further ado.
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

        if isinstance(
            node.antecedent, no_parentheses_types_in_this_context
        ) or _is_parenthesized_is_instance(node.antecedent):
            not_antecedent = f"!{antecedent}"
        else:
            # NOTE (empwilli):
            # This is a very rudimentary heuristic for breaking the lines, and can be
            # greatly improved by rendering into Java code. However, at this point, we
            # lack time for more sophisticated reformatting approaches.
            if "\n" in antecedent:
                not_antecedent = f"""\
!(
{I}{indent_but_first_line(antecedent, I)}
)"""
            else:
                not_antecedent = f"!({antecedent})"

        # NOTE (mristin):
        # The operator ``instanceof`` binds stronger than ``||``, and a check
        # against multiple classes is always parenthesized.
        if not isinstance(
            node.consequent,
            (*no_parentheses_types_in_this_context, parse_tree.IsInstance),
        ):
            # NOTE (empwilli):
            # This is a very rudimentary heuristic for breaking the lines, and can be
            # greatly improved by rendering into Java code. However, at this point, we
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

    def _transform_as_optional(
        self, node: parse_tree.Expression
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``node`` as an ``Optional``.

        We keep the nullability explicit in the optional arguments and the optional
        local variables. An optional value is passed on as-is, even if it has been
        narrowed, while a non-optional value needs to be wrapped.
        """
        if isinstance(node, parse_tree.Constant) and node.value is None:
            return Stripped("Optional.empty()"), None

        if self._optional_map[node]:
            self._beneath_none_check.add(node)
            try:
                return self.transform(node)
            finally:
                self._beneath_none_check.remove(node)

        code, error = self._transform_as_long(node)
        if error is not None:
            return None, error

        assert code is not None

        return Stripped(f"Optional.of({code})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_method_call(
        self, node: parse_tree.MethodCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        instance, error = self.transform(node.member.instance)
        if error is not None:
            errors.append(error)

        member_type = self.type_map[node.member]

        # NOTE (mristin):
        # Our methods expect the integers as ``Long``'s, so we need to render
        # the integer literals and the lengths as ``long``'s. See
        # :py:meth:`_transform_as_long`.
        transform_arg = (
            self.transform
            if isinstance(
                member_type, intermediate_type_inference.BuiltinMethodTypeAnnotation
            )
            else self._transform_as_long
        )

        args: List[Stripped] = []
        for arg_node in node.args:
            arg, error = transform_arg(arg_node)

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

        if isinstance(
            member_type, intermediate_type_inference.BuiltinMethodTypeAnnotation
        ):
            kind = member_type.method.kind

            if kind is intermediate_type_inference.BuiltinMethodKind.STR_FIND:
                # NOTE (mristin):
                # We do not use the native ``indexOf`` as it counts the UTF-16
                # code units instead of the characters, and does not count
                # a negative start from the end, unlike Python. See
                # ``StringHelpers.find`` in the generated common package.
                return (
                    Stripped(f"StringHelpers.find({instance}, {', '.join(args)})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_LSTRIP:
                # NOTE (mristin):
                # Java has no native ``lstrip`` with a set of characters. See
                # ``StringHelpers.lstrip`` in the generated common package.
                return (
                    Stripped(f"StringHelpers.lstrip({instance}, {args[0]})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_RSTRIP:
                # NOTE (mristin):
                # Java has no native ``rstrip`` with a set of characters. See
                # ``StringHelpers.rstrip`` in the generated common package.
                return (
                    Stripped(f"StringHelpers.rstrip({instance}, {args[0]})"),
                    None,
                )

            elif (
                kind is intermediate_type_inference.BuiltinMethodKind.STR_STARTSWITH
                or kind is intermediate_type_inference.BuiltinMethodKind.STR_ENDSWITH
            ):
                if not isinstance(
                    node.member.instance,
                    (
                        parse_tree.Name,
                        parse_tree.Member,
                        parse_tree.Slice,
                        parse_tree.MethodCall,
                    ),
                ):
                    instance = Stripped(f"({instance})")

                # NOTE (mristin):
                # The native ``startsWith`` and ``endsWith`` compare the UTF-16 code
                # units, which gives the same result as comparing the characters
                # (code points) in Python unless the prefix or the suffix has
                # a lone surrogate at its boundary.
                java_method = (
                    "startsWith"
                    if kind
                    is intermediate_type_inference.BuiltinMethodKind.STR_STARTSWITH
                    else "endsWith"
                )
                return Stripped(f"{instance}.{java_method}({args[0]})"), None

            elif kind is intermediate_type_inference.BuiltinMethodKind.SET_ADD:
                item, error = self._transform_as_collection_member(
                    node=node.args[0], collection_node=node.member.instance
                )
                if error is not None:
                    return None, error

                assert item is not None
                return Stripped(f"{instance}.add({item})"), None

            elif kind is intermediate_type_inference.BuiltinMethodKind.LIST_APPEND:
                item, error = self._transform_as_collection_member(
                    node=node.args[0], collection_node=node.member.instance
                )
                if error is not None:
                    return None, error

                assert item is not None
                return Stripped(f"{instance}.add({item})"), None

            elif (
                kind is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
                or kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
            ):
                # NOTE (mristin):
                # See ``SetHelpers`` in the generated common package.
                helper_name: str
                if (
                    kind
                    is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
                ):
                    helper_name = "intersection"
                elif (
                    kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
                ):
                    helper_name = "difference"
                else:
                    assert_never(kind)

                return (
                    Stripped(f"SetHelpers.{helper_name}({instance}, {args[0]})"),
                    None,
                )

            else:
                assert_never(kind)

        if not isinstance(node.member.instance, (parse_tree.Name, parse_tree.Member)):
            instance = Stripped(f"({instance})")

        method_name = java_naming.method_name(node.member.name)

        joined_args = ", ".join(args)

        # Apply heuristic for breaking the lines
        if len(joined_args) > 50:
            writer = io.StringIO()
            writer.write(f"{instance}.{method_name}(\n")

            for i, arg in enumerate(args):
                writer.write(f"{I}{arg}")

                if i == len(args) - 1:
                    writer.write(")")
                else:
                    writer.write(",\n")

            return Stripped(writer.getvalue()), None
        else:
            return Stripped(f"{instance}.{method_name}({joined_args})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_function_call(
        self, node: parse_tree.FunctionCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        # NOTE (empwilli):
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

        args: List[Stripped] = []
        for i, arg_node in enumerate(node.args):
            if isinstance(
                func_type, intermediate_type_inference.VerificationTypeAnnotation
            ):
                if isinstance(
                    func_type.func.arguments[i].type_annotation,
                    intermediate.OptionalTypeAnnotation,
                ):
                    arg, error = self._transform_as_optional(arg_node)
                else:
                    # NOTE (mristin):
                    # We need to render the integer literals and the lengths as
                    # ``long``'s as Java does not convert an ``int`` to ``Long``
                    # implicitly.
                    self._beneath_call.add(arg_node)
                    arg, error = self._transform_as_long(arg_node)
                    self._beneath_call.remove(arg_node)
            else:
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

        if isinstance(
            func_type, intermediate_type_inference.VerificationTypeAnnotation
        ):
            method_name = java_naming.method_name(func_type.func.name)

            joined_args = ", ".join(args)

            # Apply heuristic for breaking the lines
            if len(joined_args) > 50:
                writer = io.StringIO()
                writer.write(f"{method_name}(\n")

                for i, arg in enumerate(args):
                    writer.write(f"{I}{arg}")

                    if i == len(args) - 1:
                        writer.write(")")
                    else:
                        writer.write(",\n")

                return Stripped(writer.getvalue()), None
            else:
                return Stripped(f"{method_name}({joined_args})"), None

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
                    # We do not use the native ``length()`` as it counts the UTF-16
                    # code units instead of the characters, unlike Python. See
                    # ``StringHelpers.len`` in the generated common package.
                    return Stripped(f"StringHelpers.len({args[0]})"), None

                elif (
                    primitive_type
                    is intermediate_type_inference.PrimitiveType.BYTEARRAY
                ):
                    return Stripped(f"{collection}.length"), None

                elif isinstance(
                    arg_type,
                    (
                        intermediate_type_inference.ListTypeAnnotation,
                        intermediate_type_inference.SetTypeAnnotation,
                        intermediate_type_inference.TupleTypeAnnotation,
                    ),
                ):
                    return Stripped(f"{collection}.size()"), None

                # NOTE (mristin):
                # A JSON-able array is an ``ArrayNode`` and a JSON-able object
                # an ``ObjectNode``, and both count their items the same way.
                # A JSON-able *value* has no length at all -- the type
                # inference refuses it before we get here.
                elif isinstance(
                    arg_type,
                    (
                        intermediate_type_inference.JsonArrayTypeAnnotation,
                        intermediate_type_inference.JsonObjectTypeAnnotation,
                    ),
                ):
                    return Stripped(f"{collection}.size()"), None

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

                # NOTE (mristin):
                # The type inference allows only integers (``Long``) and
                # floating-point numbers (``Double``) as the argument. Java unboxes
                # them automatically, and resolves ``Math.abs(long)`` and
                # ``Math.abs(double)``, respectively. A narrowed optional property
                # has been already unwrapped with ``.get()`` in
                # :py:meth:`transform_member`.
                # NOTE (mristin):
                # We render an integer literal as a ``long`` literal so that
                # the result is a ``long`` as all the other integers.
                arg = args[0]
                if Transpiler._is_int_literal(node.args[0]):
                    arg, error = self._transform_as_long(node.args[0])
                    assert error is None and arg is not None

                return Stripped(f"Math.abs({arg})"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.INT
            ):
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                # NOTE (mristin):
                # We do not use the native ``Long.parseLong`` as it accepts
                # the digits of any script, and the range of all the 64-bit
                # integers, while the other SDKs accept only the ASCII digits and
                # the safe integers. See ``StringHelpers.parseSafeInt`` in
                # the generated common package.
                return Stripped(f"StringHelpers.parseSafeInt({args[0]})"), None

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
                # which we transpile as a new ``ArrayList``.
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

                return Stripped(f"new java.util.ArrayList<>({the_list})"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.SET
            ):
                set_type = self.type_map[node]
                assert isinstance(
                    set_type, intermediate_type_inference.SetTypeAnnotation
                )

                # NOTE (mristin):
                # We spell out the items, since Java can not infer them when
                # the new set is wrapped, *e.g.*, in an ``Optional.of``.
                item_type, error = generate_type(set_type.items)
                if error is not None:
                    return None, error

                return Stripped(f"new HashSet<{item_type}>()"), None

            else:
                assert_never(func_type.func.kind)
        else:
            assert_never(func_type)

        raise AssertionError("Should not have gotten here")

    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.value is None:
            return Stripped("Optional.empty()"), None
        elif isinstance(node.value, bool):
            return Stripped("true" if node.value else "false"), None
        elif isinstance(node.value, int):
            # NOTE (mristin):
            # An integer literal is an ``int`` in Java, so a literal beyond its range
            # does not compile unless suffixed with ``L``.
            if not -(2**31) <= node.value <= 2**31 - 1:
                return Stripped(f"{node.value}L"), None

            return Stripped(str(node.value)), None
        elif isinstance(node.value, float):
            return Stripped(str(node.value)), None
        elif isinstance(node.value, str):
            return Stripped(java_common.string_literal(node.value)), None
        else:
            assert_never(node.value)

        raise AssertionError("Should not have gotten here")

    def transform_is_none(
        self, node: parse_tree.IsNone
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        self._beneath_none_check.add(node.value)

        value, error = self.transform(node.value)

        self._beneath_none_check.remove(node.value)

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

        # NOTE (mristin):
        # A non-optional JSON-able value is never a Java ``null``, but might be
        # a JSON null, which Jackson represents as a null node.
        if isinstance(
            self.type_map[node.value],
            intermediate_type_inference.JsonValueTypeAnnotation,
        ):
            if isinstance(node.value, no_parentheses_types):
                return Stripped(f"{value}.isNull()"), None
            else:
                return Stripped(f"({value}).isNull()"), None

        if isinstance(node.value, no_parentheses_types):
            if self._optional_map[node.value]:
                return Stripped(f"!{value}.isPresent()"), None
            else:
                return Stripped(f"{value} == null"), None
        else:
            if self._optional_map[node.value]:
                return Stripped(f"!({value}).isPresent()"), None
            else:
                return Stripped(f"({value}) == null"), None

    def transform_is_not_none(
        self, node: parse_tree.IsNotNone
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        self._beneath_none_check.add(node.value)

        value, error = self.transform(node.value)

        self._beneath_none_check.remove(node.value)

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

        # NOTE (mristin):
        # See the note in :py:meth:`transform_is_none` on the JSON null.
        if isinstance(
            self.type_map[node.value],
            intermediate_type_inference.JsonValueTypeAnnotation,
        ):
            if isinstance(node.value, no_parentheses_types_in_this_context):
                return Stripped(f"!{value}.isNull()"), None
            else:
                return Stripped(f"!({value}).isNull()"), None

        if isinstance(node.value, no_parentheses_types_in_this_context):
            if self._optional_map[node.value]:
                return Stripped(f"{value}.isPresent()"), None
            else:
                return Stripped(f"{value} != null"), None
        else:
            if self._optional_map[node.value]:
                return Stripped(f"({value}).isPresent()"), None
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
        if not isinstance(
            node.operand, no_parentheses_types_in_this_context
        ) and not _is_parenthesized_is_instance(node.operand):
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

            # NOTE (mristin):
            # The operator ``instanceof`` binds stronger than ``&&`` and ``||``,
            # and a check against multiple classes is always parenthesized.
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
                # NOTE (empwilli):
                # This is a very rudimentary heuristic for breaking the lines, and can
                # be greatly improved by rendering into Java code. However, at this point,
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

            # NOTE (mristin):
            # The operator ``instanceof`` binds stronger than ``&&`` and ``||``,
            # and a check against multiple classes is always parenthesized.
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
                # NOTE (empwilli):
                # This is a very rudimentary heuristic for breaking the lines, and can
                # be greatly improved by rendering into Java code. However, at this point,
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
            operation_name: Optional[str] = None
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

        raise AssertionError("Unexpected execution path")

    def transform_add(
        self, node: parse_tree.Add
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_add_or_sub(node)

    def transform_sub(
        self, node: parse_tree.Sub
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_add_or_sub(node)

    @staticmethod
    def _is_int_literal(node: parse_tree.Node) -> bool:
        """Check whether the ``node`` is an integer literal, rendered as ``int``."""
        return (
            isinstance(node, parse_tree.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
        )

    def transform_mod(
        self, node: parse_tree.Mod
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        result_type = intermediate_type_inference.try_primitive_type(
            self.type_map[node]
        )

        # NOTE (mristin):
        # The integers are ``Long`` in Java, while the lengths and the integer
        # literals are ``int``. The overloads of ``Math.floorMod`` return ``int`` if
        # the divisor is an ``int``, and ``long`` otherwise. Hence, if the result
        # is an integer, we render the integer literals as ``long`` literals so that
        # the result is a ``long`` as well, and can be passed, *e.g.*, to a method
        # expecting a ``Long``.
        transform_operand = (
            self._transform_as_long
            if result_type is intermediate_type_inference.PrimitiveType.INT
            else self.transform
        )

        left, error = transform_operand(node.left)
        if error is not None:
            errors.append(error)

        right, error = transform_operand(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the modulo operation", errors
            )

        # NOTE (mristin):
        # We deliberately do not use the native Java operator ``%``. Java truncates
        # the division towards zero so that its remainder takes the sign of
        # the dividend (``-7 % 3 == -1``). The meta-model is written in Python where
        # the division is floored so that the remainder takes the sign of the divisor
        # (``-7 % 3 == 2``). The two only coincide for the operands of the same sign,
        # but the invariants must behave the same in all the SDKs for all the inputs.
        #
        # Hence, we use ``Math.floorMod`` from the JDK which computes the floored
        # remainder exactly as Python does. We do not need our own helper as
        # in some other targets. Java unboxes the integers (``Long``) automatically
        # to resolve the overloads of ``Math.floorMod``.
        # NOTE (mristin):
        # If the result is a length, the divisor is a length or an integer literal,
        # see :py:func:`aas_core_codegen.intermediate.type_inference._combines_to_length`,
        # so ``Math.floorMod(int, int)`` is resolved and the result is an ``int``.
        return Stripped(f"Math.floorMod({left}, {right})"), None

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
        # would be parsed as a decrement in Java.
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
        for value in node.values:
            if isinstance(value, str):
                string_literal = java_common.string_literal(
                    value.replace("{", "{{").replace("}", "}}")
                )

                assert string_literal.startswith('"') and string_literal.endswith('"')

                parts.append(string_literal)

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self.transform(value.value)
                if error is not None:
                    return None, error

                assert code is not None

                assert (
                    "\n" not in code
                ), f"New-lines are not expected in formatted values, but got: {code}"

                no_parentheses = (
                    parse_tree.Member,
                    parse_tree.FunctionCall,
                    parse_tree.MethodCall,
                    parse_tree.Name,
                    parse_tree.Constant,
                    parse_tree.Index,
                    parse_tree.Slice,
                    parse_tree.IsIn,
                )

                if isinstance(code, no_parentheses):
                    parts.append(f"{code}")
                else:
                    parts.append(f"({code})")
            else:
                assert_never(value)

        return Stripped(" + ".join(parts)), None

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

        qualifier_function: Optional[str] = None
        if isinstance(node, parse_tree.Any):
            qualifier_function = "anyMatch"
        elif isinstance(node, parse_tree.All):
            qualifier_function = "allMatch"
        else:
            assert_never(node)

        source: Optional[Stripped] = None
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
                source = Stripped(f"({iteration}.stream())")
            else:
                source = Stripped(f"{iteration}.stream()")
        elif isinstance(node.generator, parse_tree.ForRange):
            assert start is not None
            assert end is not None

            # NOTE (mristin):
            # We represent the lengths as ``int``, and the other integers as ``long``,
            # so we range over the integers with ``LongStream``.
            stream = (
                "java.util.stream.LongStream"
                if intermediate_type_inference.try_primitive_type(
                    self.type_map[node.generator.variable]
                )
                is intermediate_type_inference.PrimitiveType.INT
                else "IntStream"
            )

            source = Stripped(
                f"""\
{stream}.range(
{I}{indent_but_first_line(start, I)},
{I}{indent_but_first_line(end, I)}
)"""
            )

        else:
            assert_never(node.generator)

        return (
            Stripped(
                f"""\
{source}.{qualifier_function}(
{I}{variable} -> {indent_but_first_line(condition, II)})"""
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

    @staticmethod
    def _wrap_into_named_union_if_necessary(
        value: Stripped,
        target_type: intermediate_type_inference.TypeAnnotationUnion,
        value_type: intermediate_type_inference.TypeAnnotationUnion,
    ) -> Stripped:
        """
        Wrap the instance of a class, given as ``value``, into the named union.

        A named union is a wrapper class in Java, so we wrap the instance as
        the most specific root of the union.
        """
        if not intermediate_type_inference.needs_wrapping_into_named_union(
            target_type=target_type, value_type=value_type
        ):
            return value

        union_type = intermediate_type_inference.beneath_optional(target_type)
        assert isinstance(union_type, intermediate_type_inference.OurTypeAnnotation)
        assert isinstance(union_type.our_type, intermediate.NamedUnion)
        assert isinstance(value_type, intermediate_type_inference.OurTypeAnnotation)
        assert isinstance(value_type.our_type, intermediate.Class)

        root = union_type.our_type.most_specific_root_of(value_type.our_type)

        union_name = java_naming.union_name(union_type.our_type.name)
        root_class_name = java_naming.class_name(root.name)

        return Stripped(f"{union_name}.from{root_class_name}({value})")

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        if isinstance(node.target, (parse_tree.Member, parse_tree.Index)):
            # NOTE (mristin):
            # The type inference allows only the properties of a class and the items
            # of a list as such targets. We assign to them with a setter and
            # with ``List.set``, respectively. The value is an argument to these
            # methods, so we pass in ``null`` for an empty optional, and render
            # an integer literal as ``long``.
            value: Optional[Stripped]
            if isinstance(node.value, parse_tree.Constant) and node.value.value is None:
                value = Stripped("null")
            else:
                self._beneath_call.add(node.value)
                value, error = self._transform_as_long(node.value)
                self._beneath_call.remove(node.value)
                if error is not None:
                    errors.append(error)

            receiver_node = (
                node.target.instance
                if isinstance(node.target, parse_tree.Member)
                else node.target.collection
            )

            receiver, error = self.transform(receiver_node)
            if error is not None:
                errors.append(error)

            index_node: Optional[parse_tree.Expression] = None
            index: Optional[Stripped] = None
            if isinstance(node.target, parse_tree.Index):
                index_node = node.target.index
                index, error = self.transform(index_node)
                if error is not None:
                    errors.append(error)

            if len(errors) > 0:
                return None, Error(
                    node.original_node, "Failed to transpile the assignment", errors
                )

            assert value is not None
            assert receiver is not None

            value = self._wrap_into_named_union_if_necessary(
                value=value,
                target_type=self.type_map[node.target],
                value_type=self.type_map[node.value],
            )

            if not isinstance(
                receiver_node,
                (
                    parse_tree.Member,
                    parse_tree.FunctionCall,
                    parse_tree.MethodCall,
                    parse_tree.Name,
                    parse_tree.Index,
                ),
            ):
                receiver = Stripped(f"({receiver})")

            arguments: List[Stripped] = [value]
            if isinstance(node.target, parse_tree.Member):
                method_name = java_naming.setter_name(node.target.name)
            else:
                assert index_node is not None
                assert index is not None

                index_as_int: Optional[int] = None
                try:
                    index_as_int = int(index)
                except ValueError:
                    pass

                if index_as_int is not None and index_as_int < 0:
                    index = Stripped(f"{receiver}.size() - {-index_as_int}")

                elif (
                    index_as_int is None
                    and intermediate_type_inference.try_primitive_type(
                        self.type_map[index_node]
                    )
                    is intermediate_type_inference.PrimitiveType.INT
                ):
                    # NOTE (mristin):
                    # See the corresponding note in :py:meth:`transform_index`.
                    index = Stripped(f"Math.toIntExact({index})")

                method_name = Identifier("set")
                arguments.insert(0, index)

            # NOTE (mristin):
            # This is a rudimentary heuristic for basic line breaks, but works well in
            # practice.
            joined_arguments = ", ".join(arguments)
            if "\n" not in joined_arguments and len(joined_arguments) <= 50:
                return Stripped(f"{receiver}.{method_name}({joined_arguments});"), None

            arguments_block = ",\n".join(arguments)
            return (
                Stripped(
                    f"""\
{receiver}.{method_name}(
{I}{indent_but_first_line(arguments_block, I)});"""
                ),
                None,
            )

        # NOTE (mristin):
        # A variable of an optional type holds an ``Optional``, as we keep
        # the nullability explicit.
        #
        # The type inference records the type of the variable on the target.
        target_type = self.type_map[node.target]
        value_type = self.type_map[node.value]

        if intermediate_type_inference.needs_wrapping_into_named_union(
            target_type=target_type, value_type=value_type
        ):
            # NOTE (mristin):
            # We wrap the instance into the named union first, and only then into
            # an ``Optional``, if the variable is optional.
            value, error = self.transform(node.value)
            if error is None:
                assert value is not None
                value = self._wrap_into_named_union_if_necessary(
                    value=value, target_type=target_type, value_type=value_type
                )

                if isinstance(
                    target_type, intermediate_type_inference.OptionalTypeAnnotation
                ):
                    value = Stripped(f"Optional.of({value})")

        elif isinstance(
            target_type, intermediate_type_inference.OptionalTypeAnnotation
        ):
            value, error = self._transform_as_optional(node.value)
        else:
            value, error = self.transform(node.value)
        if error is not None:
            errors.append(error)

        target: Optional[Stripped] = None
        if isinstance(node.target, parse_tree.Name):
            # NOTE (mristin):
            # We must not unwrap the optional variable which we assign to.
            self._beneath_none_check.add(node.target)

            type_anno = self._environment.find(identifier=node.target.identifier)
            if type_anno is None:
                # NOTE (empwilli):
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
                    # so we infer its type with ``var``. This way, the alias of
                    # a generic sequence is also declared with the wildcard
                    # ``List<? extends T>``, see
                    # :py:func:`intermediate.generic_sequence_item_class`.
                    target = Stripped(f"var {target}")
                elif node.annotation is not None and (
                    intermediate_type_inference.try_primitive_type(type_anno)
                    is not intermediate_type_inference.PrimitiveType.INT
                ):
                    # NOTE (mristin):
                    # We spell out the declared type, as it might differ from
                    # the type of the value, *e.g.*, for ``Optional.empty()``.
                    declared_type, java_error = generate_type(type_anno)
                    if java_error is not None:
                        errors.append(java_error)
                    else:
                        target = Stripped(f"{declared_type} {target}")
                elif (
                    intermediate_type_inference.try_primitive_type(type_anno)
                    is intermediate_type_inference.PrimitiveType.INT
                ):
                    # NOTE (mristin):
                    # We represent the integers as ``long``, while ``var`` would
                    # infer ``int`` from an integer literal, and the variable could
                    # not be re-assigned a ``long`` later.
                    target = Stripped(f"long {target}")
                else:
                    # NOTE (mristin):
                    # We infer the type of the local variable with ``var``, which
                    # is available since Java 10.
                    target = Stripped(f"var {target}")

                # NOTE (mristin):
                # A variable declared as ``Final[...]`` is never re-assigned.
                if (
                    target is not None
                    and node.annotation is not None
                    and intermediate_type_inference.is_final_annotation(node.annotation)
                ):
                    target = Stripped(f"final {target}")
            else:
                target, error = self.transform(node=node.target)
                if error is not None:
                    errors.append(error)

            self._beneath_none_check.remove(node.target)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assignment", errors
            )

        assert target is not None
        assert value is not None

        # NOTE (empwilli):
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
        # An integer literal or a length can only be returned from a function
        # returning an integer, which we represent as ``Long``. Java does not convert
        # an ``int`` to ``Long`` implicitly, so we render them as ``long``'s.
        #
        # The type inference records the return type of the function on the return.
        # A function returning an optional returns an ``Optional``.
        value, error = (
            self._transform_as_optional(node.value)
            if isinstance(
                self.type_map[node], intermediate_type_inference.OptionalTypeAnnotation
            )
            else self._transform_as_long(node.value)
        )
        if error is not None:
            return None, error

        assert value is not None

        # NOTE (empwilli):
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
        Transpile the ``statements`` of a switch branch in a new scope.

        The variables defined in the ``statements`` are not visible after
        the branch.

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
                None, "Failed to transpile the statements of a switch branch", errors
            )

        return (stmts, len(scope_environment.mapping) > 0), None

    @staticmethod
    def _block(stmts: Sequence[Stripped]) -> Stripped:
        """Enclose the ``stmts`` in a block."""
        if len(stmts) == 0:
            return Stripped("{}")

        writer = io.StringIO()
        writer.write("{")
        for stmt in stmts:
            writer.write("\n")
            writer.write(textwrap.indent(stmt, I))
        writer.write("\n}")

        return Stripped(writer.getvalue())

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_if_chain(
        self, branches: Sequence[Tuple[str, Sequence[parse_tree.StatementUnion]]]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``branches`` as a chain of ``if``, ``else if`` and ``else``.

        Each branch is given as its header, *e.g.*, ``else if (x > 0)``, together
        with its statements.
        """
        errors: List[Error] = []
        writer = io.StringIO()

        for i, (header, statements) in enumerate(branches):
            stmts_and_defines, error = self._transform_branch(statements)
            if error is not None:
                errors.append(error)
                continue

            assert stmts_and_defines is not None
            stmts, _ = stmts_and_defines

            if i > 0:
                writer.write(" ")
            writer.write(f"{header} {Transpiler._block(stmts)}")

        if len(errors) > 0:
            return None, Error(None, "Failed to transpile the branches", errors)

        return Stripped(writer.getvalue()), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_switch_as_if_chain(
        self, node: parse_tree.Switch, subject: Stripped
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``node`` as a chain of ``if``, ``else if`` and ``else``.

        We need this for the subjects which Java can not switch on, namely ``long``.
        """
        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Index,
            parse_tree.Slice,
        )
        if not isinstance(node.subject, no_parentheses_types):
            subject = Stripped(f"({subject})")

        errors: List[Error] = []

        # NOTE (mristin):
        # We collect the headers of the branches together with their statements,
        # and treat the default as the last branch.
        branches: List[Tuple[str, Sequence[parse_tree.StatementUnion]]] = []

        for i, case in enumerate(node.cases):
            comparisons: List[str] = []
            for label in case.labels:
                label_code, error = self.transform(label)
                if error is not None:
                    errors.append(error)
                    continue

                assert label_code is not None
                comparisons.append(f"{subject} == {label_code}")

            condition = " || ".join(comparisons)
            keyword = "if" if i == 0 else "else if"
            branches.append((f"{keyword} ({condition})", case.body))

        if node.default is not None:
            branches.append(("else", node.default))

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the switch", errors
            )

        code, error = self._transform_if_chain(branches)
        if error is not None:
            return None, Error(
                node.original_node, "Failed to transpile the switch", [error]
            )

        return code, None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_switch(
        self, node: parse_tree.Switch
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        subject, error = self.transform(node.subject)
        if error is not None:
            return None, error

        assert subject is not None

        subject_type = self.type_map[node.subject]

        # NOTE (mristin):
        # Java can not switch on ``long``, which we use for integers.
        if (
            intermediate_type_inference.try_primitive_type(subject_type)
            is intermediate_type_inference.PrimitiveType.INT
        ):
            return self._transform_switch_as_if_chain(node=node, subject=subject)

        errors: List[Error] = []

        # NOTE (mristin):
        # We collect the headers of the clauses together with their statements, and
        # treat the default as the last clause.
        clauses: List[Tuple[str, Sequence[parse_tree.StatementUnion]]] = []

        for case in node.cases:
            labels: List[str] = []
            for label in case.labels:
                if isinstance(label, parse_tree.Member):
                    # NOTE (mristin):
                    # Java 17 expects the enumeration literals in the case labels
                    # without the qualification.
                    labels.append(java_naming.enum_literal_name(label.name))
                else:
                    label_code, error = self.transform(label)
                    if error is not None:
                        errors.append(error)
                        continue

                    assert label_code is not None
                    labels.append(label_code)

            clauses.append((f"case {', '.join(labels)} ->", case.body))

        if node.default is not None:
            clauses.append(("default ->", node.default))

        writer = io.StringIO()
        writer.write(f"switch ({subject}) {{")

        for header, statements in clauses:
            stmts_and_defines, error = self._transform_branch(statements)
            if error is not None:
                errors.append(error)
                continue

            assert stmts_and_defines is not None
            stmts, _ = stmts_and_defines

            # NOTE (mristin):
            # We always enclose the statements in a block. The arrow form of
            # the case does not fall through, so we need no ``break``.
            writer.write("\n")
            writer.write(textwrap.indent(f"{header} {Transpiler._block(stmts)}", I))

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
        variable = java_naming.variable_name(variable_name)

        header: Optional[str] = None
        if isinstance(node.generator, parse_tree.ForEach):
            iteration, error = self.transform(node.generator.iteration)
            if error is not None:
                errors.append(error)
            else:
                assert iteration is not None
                header = f"for (var {variable} : {indent_but_first_line(iteration, I)})"

        elif isinstance(node.generator, parse_tree.ForRange):
            start, error = self.transform(node.generator.start)
            if error is not None:
                errors.append(error)

            end, error = self.transform(node.generator.end)
            if error is not None:
                errors.append(error)

            if start is not None and end is not None:
                # NOTE (mristin):
                # We represent the lengths as ``int``, since the collections are
                # indexed by ``int``'s in Java, while we represent the other integers
                # as ``long``.
                primitive_type = intermediate_type_inference.try_primitive_type(
                    variable_type
                )
                if primitive_type is intermediate_type_inference.PrimitiveType.LENGTH:
                    variable_java_type = "int"
                elif primitive_type is intermediate_type_inference.PrimitiveType.INT:
                    variable_java_type = "long"
                else:
                    raise AssertionError(
                        f"Unexpected type of the loop variable over a range: "
                        f"{variable_type}"
                    )

                if "\n" not in start and "\n" not in end:
                    header = (
                        f"for ({variable_java_type} {variable} = {start}; "
                        f"{variable} < {end}; {variable}++)"
                    )
                else:
                    header = f"""\
for (
{I}{variable_java_type} {variable} = {indent_but_first_line(start, I)};
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

        return Stripped(f"{header} {Transpiler._block(stmts)}"), None

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
            message = java_common.string_literal(
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
{header} {{
{I}throw new IllegalStateException(
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
        # We collect the headers of the branches together with their statements,
        # and treat the default as the last branch.
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

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the if-statement", errors
            )

        code, error = self._transform_if_chain(branches)
        if error is not None:
            return None, Error(
                node.original_node, "Failed to transpile the if-statement", [error]
            )

        return code, None


# noinspection PyProtectedMember,PyProtectedMember
assert all(op in Transpiler._JAVA_COMPARISON_MAP for op in parse_tree.Comparator)
