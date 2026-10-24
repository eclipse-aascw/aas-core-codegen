"""Transpile Python to Go code."""
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
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    pointering as golang_pointering,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.parse import tree as parse_tree

# NOTE (mristin):
# We have to implement a very similar function for generating type annotations to
# aas_core_codegen.golang.common.generate_type since we can not simply pass
# intermediate_type_inference.TypeAnnotationUnion to
# aas_core_codegen.golang.common.generate_type.

PRIMITIVE_TYPE_MAP = {
    intermediate_type_inference.PrimitiveType.BOOL: Stripped("bool"),
    intermediate_type_inference.PrimitiveType.INT: Stripped("int64"),
    intermediate_type_inference.PrimitiveType.FLOAT: Stripped("float64"),
    intermediate_type_inference.PrimitiveType.STR: Stripped("string"),
    intermediate_type_inference.PrimitiveType.BYTEARRAY: Stripped("[]byte"),
    intermediate_type_inference.PrimitiveType.NONE: Stripped("struct{}"),
    intermediate_type_inference.PrimitiveType.LENGTH: Stripped("int"),
}

#: Name of the helper function in the common package which computes
#: the remainder of the floored division as in Python.
#:
#: See :py:meth:`Transpiler.transform_mod` and
#: :py:data:`aas_core_codegen.golang.lib._generate_common.FLOOR_MOD` on why
#: we do not use the native Go operator ``%``.
FLOOR_MOD_FUNCTION_NAME = Identifier("FloorMod")

#: Name of the helper function in the common package which computes
#: the absolute value of a 64-bit signed integer.
#:
#: Go does not provide an absolute value for integers in its standard library;
#: ``math.Abs`` works only on ``float64``.
ABS_INT64_FUNCTION_NAME = Identifier("AbsInt64")

#: Name of the helper function in the common package which parses a string
#: as a safe integer.
#:
#: See :py:data:`aas_core_codegen.golang.lib._generate_common.PARSE_SAFE_INT`
#: on why we do not use ``strconv.ParseInt`` directly.
PARSE_SAFE_INT_FUNCTION_NAME = Identifier("ParseSafeInt")


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def generate_type(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
    types_package: Optional[Identifier] = None,
) -> Tuple[Optional[Stripped], Optional[str]]:
    """
    Generate the Go type for the given type annotation.

    If ``types_package`` is specified, it is prepended to all our types.

    (mristin): We do not handle all the type annotations from
    :py:mod:`aas_core_codegen.intermediate.type_inference` as that would be
    YAGNI (*e.g.*, verification functions, built-in functions *etc.*).
    If we do not know how to generate the type in Go, we return an error message.
    """
    if isinstance(type_annotation, intermediate_type_inference.PrimitiveTypeAnnotation):
        return PRIMITIVE_TYPE_MAP[type_annotation.a_type], None

    elif isinstance(type_annotation, intermediate_type_inference.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            enum_name = golang_naming.enum_name(type_annotation.our_type.name)
            if types_package is None:
                return enum_name, None

            return Stripped(f"{types_package}.{enum_name}"), None

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return golang_common.PRIMITIVE_TYPE_MAP[our_type.constrainee], None

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # NOTE (mristin):
            # We always refer to interfaces even in cases of concrete classes without
            # concrete descendants since we want to allow enhancing.
            interface_name = golang_naming.interface_name(our_type.name)

            if types_package is None:
                return interface_name, None

            return Stripped(f"{types_package}.{interface_name}"), None

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is represented as a pointer to a plain Go struct,
            # see :py:func:`aas_core_codegen.golang.common.generate_type`.
            union_name = golang_naming.union_name(our_type.name)

            if types_package is None:
                return Stripped(f"*{union_name}"), None

            return Stripped(f"*{types_package}.{union_name}"), None

    elif isinstance(type_annotation, intermediate_type_inference.ListTypeAnnotation):
        item_type, error_msg = generate_type(
            type_annotation=type_annotation.items, types_package=types_package
        )

        if error_msg is not None:
            return None, error_msg

        assert item_type is not None

        return Stripped(f"[]{item_type}"), None

    elif isinstance(type_annotation, intermediate_type_inference.SetTypeAnnotation):
        item_type, error_msg = generate_type(
            type_annotation=type_annotation.items, types_package=types_package
        )

        if error_msg is not None:
            return None, error_msg

        assert item_type is not None

        return Stripped(f"map[{item_type}]struct{{}}"), None

    elif isinstance(
        type_annotation, intermediate_type_inference.OptionalTypeAnnotation
    ):
        value_type, error_msg = generate_type(
            type_annotation=type_annotation.value, types_package=types_package
        )

        if error_msg is not None:
            return None, error_msg

        assert value_type is not None

        if golang_pointering.is_pointer_type(type_annotation):
            return Stripped(f"*{value_type}"), None

        return value_type, None

    elif isinstance(type_annotation, intermediate_type_inference.TupleTypeAnnotation):
        item_types: List[Stripped] = []
        for item in type_annotation.items:
            item_type, error_msg = generate_type(
                type_annotation=item, types_package=types_package
            )

            if error_msg is not None:
                return None, error_msg

            assert item_type is not None
            item_types.append(item_type)

        if len(item_types) > golang_common.MAX_TUPLE_ARITY:
            return None, (
                f"We only pre-generate Tuple1 .. Tuple{golang_common.MAX_TUPLE_ARITY} "
                f"in {golang_common.COMMON_PACKAGE}, but got a tuple of "
                f"arity {len(item_types)}. Please contact the developers if you "
                f"need larger tuples."
            )

        joined_item_types = ", ".join(item_types)
        tuple_type_name = f"Tuple{len(item_types)}"

        return (
            Stripped(
                f"{golang_common.COMMON_PACKAGE}.{tuple_type_name}[{joined_item_types}]"
            ),
            None,
        )

    else:
        return None, (
            f"(mristin): We do not handle "
            f"the type annotation {type_annotation} from "
            "aas_core_codegen.intermediate.type_inference as that was, "
            "at this time point, YAGNI (*e.g.*, verification functions, "
            "built-in functions *etc.*). If you need this feature, please "
            "contact the developers."
        )

    raise AssertionError("Should not have gotten here")


class Transpiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a node of our AST to Go code, or return an error."""

    _GOLANG_COMPARISON_MAP: Final[Mapping[parse_tree.Comparator, str]] = {
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
        is_pointer_map: Mapping[parse_tree.Node, bool],
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        environment: intermediate_type_inference.Environment,
        types_package: Optional[Identifier] = None,
    ) -> None:
        """
        Initialize with the given values.

        If ``types_package`` is specified, it is prepended to all our types.
        """
        self.type_map = type_map
        self._is_pointer_map = is_pointer_map
        self._downcast_map = downcast_map
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )
        self._types_package = types_package

        # Keep track whenever we define a variable name, so that we can know how to
        # generate the reference in the Go code.
        self._variable_name_set: Set[Identifier] = set()

    def _type_parameter_of(
        self, type_annotation: intermediate_type_inference.TypeAnnotationUnion
    ) -> Optional[Identifier]:
        """
        Determine the type parameter which stands for the ``type_annotation``.

        Only the verification functions have type parameters, namely for the items
        of the generic sequences, see
        :py:func:`intermediate.generic_sequence_item_class`. The transpiler of
        the verification functions overrides this method.

        :param type_annotation: inferred type of a value
        :return:
            the type parameter, if the value is an item of a generic sequence,
            and None otherwise
        """
        return None

    def _our_type_name(self, name: Identifier) -> Stripped:
        """Prepend the types package, if specified, to the ``name`` of our type."""
        if self._types_package is None:
            return Stripped(name)

        return Stripped(f"{self._types_package}.{name}")

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
        # The value has been narrowed down by an ``isinstance`` guard, so we need to
        # cast it to the interface of the target class. The type assertion is safe
        # as the guard checked the model type before.
        #
        # Classes are represented as interfaces and named unions as pointers to
        # structs, so the narrowed value is never a pointer which we would need to
        # de-reference.
        if self._is_pointer_map.get(node, False):
            return None, Error(
                node.original_node,
                f"Unexpected narrowed value represented as a pointer "
                f"in Go: {parse_tree.dump(node)}; this is an assertion violation!",
            )

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Index,
            parse_tree.Slice,
        )
        if not isinstance(node, no_parentheses_types):
            code = Stripped(f"({code})")

        interface_name = self._our_type_name(
            golang_naming.interface_name(downcast.target.our_type.name)
        )

        source_type = downcast.source.our_type
        if isinstance(source_type, intermediate.Class):
            # NOTE (mristin):
            # Go forbids type assertions on the values of a type parameter, so we
            # convert the item of a generic sequence to an interface first.
            if self._type_parameter_of(downcast.source) is not None:
                return Stripped(f"any({code}).({interface_name})"), None

            return Stripped(f"{code}.({interface_name})"), None

        elif isinstance(source_type, intermediate.NamedUnion):
            return Stripped(f"{code}.Underlying().({interface_name})"), None

        else:
            return None, Error(
                node.original_node,
                f"Expected the source of a narrowing to be a class or "
                f"a named union, but got {downcast.source} "
                f"for {parse_tree.dump(node)}; this is an assertion violation!",
            )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_and_dereference_if_necessary(
        self, node: parse_tree.Node
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Dereference the given node if it is annotated as an optional.

        If the value denoted by ``node`` is not an optional, or does not need
        dereferencing, it is returned transpiled as-is.
        """
        if not isinstance(node, (parse_tree.Name, parse_tree.Member, parse_tree.Index)):
            return self.transform(node)

        code, error = self.transform(node)
        if error is not None:
            return None, error

        needs_dereferencing = self._is_pointer_map.get(node, None)
        if needs_dereferencing is None:
            error = Error(
                node.original_node,
                f"A node in our AST has not been mapped for "
                f"is-pointer: {parse_tree.dump(node)}; this is an assertion violation!",
            )
            return None, error

        if not needs_dereferencing:
            return code, None

        return Stripped(f"*{code}"), None

    def _as_int64_position(self, node: parse_tree.Node, code: Stripped) -> Stripped:
        """
        Convert the transpiled position ``node`` to an ``int64`` if it is a length.

        The string helpers take the positions as ``int64``'s, our integers,
        while the lengths are ``int``'s. The same holds for the integer parameters
        of our functions and methods.
        """
        type_anno = self.type_map[node]
        if (
            isinstance(type_anno, intermediate_type_inference.PrimitiveTypeAnnotation)
            and type_anno.a_type is intermediate_type_inference.PrimitiveType.LENGTH
        ):
            return Stripped(f"int64({code})")

        return code

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_as_pointer(
        self, node: parse_tree.Expression
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``node`` as a pointer to its value.

        We pass on a pointer, *e.g.*, of an optional property, as-is. A non-pointer
        value needs to be wrapped in ``NewAndPointTo``. Go does not allow to take
        the address of a literal or of an expression, and taking the address of
        a variable would alias it, so that a later assignment to the variable would
        also change the pointed value.
        """
        code, error = self.transform(node)
        if error is not None:
            return None, error

        assert code is not None

        # NOTE (mristin):
        # A value of an optional type which is not narrowed down, *e.g.*, the result
        # of a method returning an optional, is already a pointer, if the optional
        # is represented as a pointer at all.
        if (
            (
                isinstance(node, (parse_tree.Name, parse_tree.Member, parse_tree.Index))
                and self._is_pointer_map[node]
            )
            or (isinstance(node, parse_tree.Constant) and node.value is None)
            or golang_pointering.is_pointer_type(self.type_map[node])
        ):
            return code, None

        # NOTE (mristin):
        # A length can only be pointed to as an integer, an ``int64``, while
        # the lengths are ``int``'s.
        code = self._as_int64_position(node, code)

        if (
            isinstance(node, parse_tree.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
        ):
            # NOTE (mristin):
            # The integer literals are untyped in Go, and ``NewAndPointTo`` would
            # infer an ``int`` for them, while we represent the integers as
            # ``int64``.
            code = Stripped(f"int64({code})")

        return Stripped(f"{golang_common.COMMON_PACKAGE}.NewAndPointTo({code})"), None

    @abc.abstractmethod
    def _transform_enumeration_literal(
        self, enumeration_name: Identifier, literal_name: Identifier
    ) -> Stripped:
        """
        Generate code to represent an enumeration literal.

        In Go, enumeration literals are mere constants. Hence, we can not
        "de-reference" the enumeration literals from an enumeration, but
        generate the constant name here.
        """
        raise NotImplementedError

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_member(
        self, node: parse_tree.Member
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        instance, error = self.transform(node.instance)
        if error is not None:
            return None, error

        # NOTE (mristin):
        # Ignore optional instance as they need to be checked before in the code
        instance_type = intermediate_type_inference.beneath_optional(
            self.type_map[node.instance]
        )

        # NOTE (mristin):
        # We explicitly do *not* dereference member access. Make sure you use
        # :py:meth:`_transform_and_dereference_if_necessary` where appropriate. Notably,
        # the operators ``is None`` and ``is not None`` have to compare against
        # references instead of values. That is why we can not simply de-reference
        # all the member access.

        member_type = self.type_map[node]

        member_accessor: str

        if isinstance(
            instance_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type.our_type, intermediate.Enumeration):
            # NOTE (mristin):
            # This member denotes an enumeration literal of an enumeration.
            # In Go, enumeration literals are mere constants. Hence, we can not
            # "de-reference" the enumeration literals from an enumeration, but
            # generate the constant name here.
            return (
                self._transform_enumeration_literal(
                    enumeration_name=instance_type.our_type.name, literal_name=node.name
                ),
                None,
            )

        elif isinstance(member_type, intermediate_type_inference.MethodTypeAnnotation):
            member_accessor = golang_naming.method_name(node.name)

        elif isinstance(
            instance_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type.our_type, intermediate.Class):
            if node.name in instance_type.our_type.properties_by_name:
                getter_name = golang_naming.getter_name(node.name)
                member_accessor = f"{getter_name}()"
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
                # NOTE (mristin):
                # The member denotes an enumeration literal of an enumeration.
                # In Go, enumeration literals are mere constants. Hence, we can not
                # "de-reference" the enumeration literals from an enumeration, but
                # generate the constant name here.
                return (
                    self._transform_enumeration_literal(
                        enumeration_name=instance_type.enumeration.name,
                        literal_name=node.name,
                    ),
                    None,
                )
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

        return Stripped(f"{instance}.{member_accessor}"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_index(
        self, node: parse_tree.Index
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        collection, error = self.transform(node.collection)
        if error is not None:
            return None, error
        assert collection is not None

        collection_type = intermediate_type_inference.beneath_optional(
            self.type_map[node.collection]
        )

        if isinstance(collection_type, intermediate_type_inference.TupleTypeAnnotation):
            # NOTE (mristin):
            # Tuples are heterogeneous, so the index must be a literal integer which
            # we resolve statically to the corresponding ``ItemN`` field. This has
            # already been verified in
            # :py:class:`aas_core_codegen.intermediate.type_inference.Inferrer`.
            assert isinstance(node.index, parse_tree.Constant) and isinstance(
                node.index.value, int
            )

            index_value = node.index.value
            if index_value < 0:
                index_value += len(collection_type.items)

            no_parentheses_types = (
                parse_tree.Member,
                parse_tree.FunctionCall,
                parse_tree.IsInstance,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.Constant,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.IsIn,
            )

            if not isinstance(node.collection, no_parentheses_types):
                collection = Stripped(f"({collection})")

            return Stripped(f"{collection}.Item{index_value + 1}"), None

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
            if "\n" in collection:
                index = Stripped(
                    f"""\
len(
{I}{indent_but_first_line(collection, I)}
) - {-index_as_int}"""
                )
            else:
                index = Stripped(f"len({collection}) - {-index_as_int}")

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.IsInstance,
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
        # We explicitly do *not* dereference index access. Make sure you use
        # :py:meth:`_transform_and_dereference_if_necessary` where appropriate. Notably,
        # the operators ``is None`` and ``is not None`` have to compare against
        # references instead of values. That is why we can not simply de-reference
        # all the index access.

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
        # We do not use the native slicing as it counts the UTF-8 bytes instead of
        # the characters, panics on the positions out of range, and does not count
        # the negative ones from the end, unlike Python. See ``SliceStr`` in
        # the generated common package.
        start_int64 = (
            self._as_int64_position(node.start, start)
            if node.start is not None and start is not None
            else Stripped("0")
        )

        if node.end is None:
            return (
                Stripped(f"ourcommon.SliceStrFrom({collection}, {start_int64})"),
                None,
            )

        assert end is not None
        end_int64 = self._as_int64_position(node.end, end)

        return (
            Stripped(f"ourcommon.SliceStr({collection}, {start_int64}, {end_int64})"),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_comparison(
        self, node: parse_tree.Comparison
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        comparator = Transpiler._GOLANG_COMPARISON_MAP[node.op]

        errors = []

        left, error = self._transform_and_dereference_if_necessary(node.left)
        if error is not None:
            errors.append(error)

        right, error = self._transform_and_dereference_if_necessary(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the comparison", errors
            )

        # NOTE (mristin):
        # Go does not order the booleans, so we compare them with our helper, where
        # ``false`` comes before ``true`` as in Python. We need no helper for
        # the strings, as Go orders them by their UTF-8 bytes, which gives the same
        # order as the characters (code points) in Python.
        if node.op not in (parse_tree.Comparator.EQ, parse_tree.Comparator.NE,) and (
            intermediate_type_inference.try_primitive_type(self.type_map[node.left])
            is intermediate_type_inference.PrimitiveType.BOOL
        ):
            return (
                Stripped(
                    f"{golang_common.COMMON_PACKAGE}.CompareBools({left}, {right}) "
                    f"{comparator} 0"
                ),
                None,
            )

        # NOTE (mristin):
        # The modulo is transpiled either as a function call or as the native
        # operator ``%``, and the negation as the unary ``-``. Both bind stronger
        # than the comparison in Go, so they need no parentheses.
        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.IsInstance,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
            parse_tree.Mod,
            parse_tree.Neg,
        )

        # NOTE (mristin):
        # The lengths are ``int``'s in Go, while the other integers are ``int64``'s,
        # and Go does not compare the two. We widen the length if it is compared
        # against an integer which is not a literal. The integer literals are
        # untyped constants in Go and need no conversion.
        left_a_type = intermediate_type_inference.try_primitive_type(
            self.type_map[node.left]
        )
        right_a_type = intermediate_type_inference.try_primitive_type(
            self.type_map[node.right]
        )

        length = intermediate_type_inference.PrimitiveType.LENGTH
        integer = intermediate_type_inference.PrimitiveType.INT

        if (
            left_a_type is length
            and right_a_type is integer
            and not isinstance(node.right, parse_tree.Constant)
        ):
            left = Stripped(f"int64({left})")

        elif not isinstance(node.left, no_parentheses_types):
            left = Stripped(f"({left})")

        if (
            right_a_type is length
            and left_a_type is integer
            and not isinstance(node.left, parse_tree.Constant)
        ):
            right = Stripped(f"int64({right})")

        elif not isinstance(node.right, no_parentheses_types):
            right = Stripped(f"({right})")

        return Stripped(f"{left} {comparator} {right}"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_is_in(
        self, node: parse_tree.IsIn
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []

        member, error = self._transform_and_dereference_if_necessary(node.member)
        if error is not None:
            errors.append(error)

        container, error = self._transform_and_dereference_if_necessary(node.container)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node,
                "Failed to transpile the membership relation",
                errors,
            )

        assert container is not None
        assert member is not None

        container_type = self.type_map[node.container]

        # NOTE (mristin):
        # The lengths are ``int``'s, so we convert them to our integers to look
        # them up in a set or a list.
        if isinstance(
            container_type,
            (
                intermediate_type_inference.SetTypeAnnotation,
                intermediate_type_inference.ListTypeAnnotation,
            ),
        ):
            member = self._as_int64_position(node.member, member)

        # NOTE (mristin):
        # A JSON-able object is a ``map[string]interface{}``, so the membership
        # is a question about its keys, just as it is for a set.
        if isinstance(
            container_type,
            (
                intermediate_type_inference.SetTypeAnnotation,
                intermediate_type_inference.JsonObjectTypeAnnotation,
            ),
        ):
            return (
                Stripped(
                    f"""\
ourcommon.MapContains(
{I}{indent_but_first_line(container, I)},
{I}{indent_but_first_line(member, I)},
)"""
                ),
                None,
            )

        elif isinstance(container_type, intermediate_type_inference.ListTypeAnnotation):
            # NOTE (mristin):
            # The ``ourcommon.SliceContains`` infers its type parameter from both
            # the slice and the member, so that the untyped constants take the type of
            # the items. The instances of the classes are never constants, but they
            # can be of a different type than the items, *e.g.*, if the items are of
            # the type parameter of a generic sequence, see
            # :py:func:`intermediate.generic_sequence_item_class`, or if the member
            # is an instance of a descendant. Hence, we look them up as ``any``'s.
            function_name = "SliceContains"
            if isinstance(
                container_type.items, intermediate_type_inference.OurTypeAnnotation
            ) and isinstance(container_type.items.our_type, intermediate.Class):
                function_name = "SliceContainsInstance"

            return (
                Stripped(
                    f"""\
ourcommon.{function_name}(
{I}{indent_but_first_line(container, I)},
{I}{indent_but_first_line(member, I)},
)"""
                ),
                None,
            )

        elif (
            intermediate_type_inference.try_primitive_type(container_type)
            is intermediate_type_inference.PrimitiveType.STR
        ):
            # NOTE (mristin):
            # The native ``strings.Contains`` works on the UTF-8 bytes, which is
            # equivalent to the check on the characters for a valid UTF-8.
            return (
                Stripped(
                    f"""\
strings.Contains(
{I}{indent_but_first_line(container, I)},
{I}{indent_but_first_line(member, I)},
)"""
                ),
                None,
            )

        else:
            return None, Error(
                node.original_node,
                f"We do not know how to generate the is-in operation for "
                f"the container {node.container}. The inferred type of "
                f"the container was {container_type}. "
                f"Please contact the developers if you need this feature.",
            )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_is_instance(
        self, node: parse_tree.IsInstance
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        # NOTE (mristin):
        # We do not de-reference the value as neither classes nor named unions are
        # represented as pointers which we would need to de-reference.
        value, error = self.transform(node.value)
        if error is not None:
            return None, error

        assert value is not None

        value_type = self.type_map[node.value]
        assert isinstance(value_type, intermediate_type_inference.OurTypeAnnotation), (
            f"Expected the value of a successfully inferred isinstance to be "
            f"our type, but got {value_type} for {parse_tree.dump(node)}"
        )

        # NOTE (mristin):
        # Go interfaces are structural, so a type assertion to an interface might
        # succeed for an instance of another class with the same method set. That is
        # why we check the run-time model type with the generated ``Is*`` functions.
        subject: Stripped
        if isinstance(value_type.our_type, intermediate.Class):
            subject = value

        elif isinstance(value_type.our_type, intermediate.NamedUnion):
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

            subject = Stripped(f"{value}.Underlying()")

        else:
            return None, Error(
                node.original_node,
                f"Expected the value of isinstance to be a class or "
                f"a named union, but got {value_type}; "
                f"this is an assertion violation!",
            )

        checks: List[Stripped] = []
        for cls_name in node.classes:
            function_name = self._our_type_name(
                golang_naming.function_name(Identifier(f"is_{cls_name.identifier}"))
            )

            if "\n" in subject:
                checks.append(
                    Stripped(
                        f"""\
{function_name}(
{I}{indent_but_first_line(subject, I)},
)"""
                    )
                )
            else:
                checks.append(Stripped(f"{function_name}({subject})"))

        if len(checks) == 1:
            return checks[0], None

        # NOTE (mristin):
        # We always wrap the disjunction in parentheses so that the ``isinstance``
        # can be treated as a primary expression regardless of the context.
        checks_joined = " ||\n".join(checks)
        return Stripped(f"({checks_joined})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_implication(
        self, node: parse_tree.Implication
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []

        antecedent, error = self._transform_and_dereference_if_necessary(
            node.antecedent
        )
        if error is not None:
            errors.append(error)

        consequent, error = self._transform_and_dereference_if_necessary(
            node.consequent
        )
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
            parse_tree.IsInstance,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
        )

        if isinstance(node.antecedent, no_parentheses_types_in_this_context):
            not_antecedent = f"!{antecedent}"
        else:
            not_antecedent = f"!({antecedent})"

        if not isinstance(node.consequent, no_parentheses_types_in_this_context):
            consequent = Stripped(f"({consequent})")

        return Stripped(f"{not_antecedent} ||\n{consequent}"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_method_call(
        self, node: parse_tree.MethodCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        instance, error = self._transform_and_dereference_if_necessary(
            node.member.instance
        )
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
        if isinstance(
            member_type, intermediate_type_inference.BuiltinMethodTypeAnnotation
        ):
            kind = member_type.method.kind

            if kind is intermediate_type_inference.BuiltinMethodKind.STR_FIND:
                # NOTE (mristin):
                # We do not use the native ``strings.Index`` as it counts the UTF-8
                # bytes instead of the characters, and has no start, unlike Python.
                # See ``FindStr`` in the generated common package.
                start = (
                    self._as_int64_position(node.args[1], args[1])
                    if len(args) == 2
                    else Stripped("0")
                )
                return (
                    Stripped(f"ourcommon.FindStr({instance}, {args[0]}, {start})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_LSTRIP:
                # NOTE (mristin):
                # The native ``strings.TrimLeft`` strips the characters (runes) as
                # the Python ``str.lstrip`` does.
                return (
                    Stripped(f"strings.TrimLeft({instance}, {args[0]})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_RSTRIP:
                # NOTE (mristin):
                # The native ``strings.TrimRight`` strips the characters (runes) as
                # the Python ``str.rstrip`` does.
                return (
                    Stripped(f"strings.TrimRight({instance}, {args[0]})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_STARTSWITH:
                # NOTE (mristin):
                # The native ``strings.HasPrefix`` compares the UTF-8 bytes, which
                # gives the same result as the Python ``str.startswith`` for
                # the well-formed strings.
                return (
                    Stripped(f"strings.HasPrefix({instance}, {args[0]})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_ENDSWITH:
                # NOTE (mristin):
                # The native ``strings.HasSuffix`` compares the UTF-8 bytes, which
                # gives the same result as the Python ``str.endswith`` for
                # the well-formed strings.
                return (
                    Stripped(f"strings.HasSuffix({instance}, {args[0]})"),
                    None,
                )

            elif (
                kind is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
                or kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
            ):
                # NOTE (mristin):
                # See ``SetIntersection`` and ``SetDifference`` in the generated
                # common package, which give a new set as Python does.
                function_name: str
                if (
                    kind
                    is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
                ):
                    function_name = "SetIntersection"
                elif (
                    kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
                ):
                    function_name = "SetDifference"
                else:
                    assert_never(kind)

                return (
                    Stripped(
                        f"""\
ourcommon.{function_name}(
{I}{indent_but_first_line(instance, I)},
{I}{indent_but_first_line(args[0], I)},
)"""
                    ),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.SET_ADD:
                # NOTE (mristin):
                # A set is a map to empty structs. A narrowed optional is still
                # a pointer, so we de-reference it, and the lengths are ``int``'s,
                # so we convert them to our integers.
                item, error = self._transform_and_dereference_if_necessary(node.args[0])
                if error is not None:
                    return None, error

                assert item is not None
                item = self._as_int64_position(node.args[0], item)
                return Stripped(f"{instance}[{item}] = struct{{}}{{}}"), None

            elif kind is intermediate_type_inference.BuiltinMethodKind.LIST_APPEND:
                # NOTE (mristin):
                # The ``append`` gives a new slice whenever the array beneath has
                # to grow, so we assign it back. The type inference allows
                # ``append`` only on a local variable, which nobody else sees.
                assert isinstance(node.member.instance, parse_tree.Name)

                item, error = self._transform_and_dereference_if_necessary(node.args[0])
                if error is not None:
                    return None, error

                assert item is not None
                item = self._as_int64_position(node.args[0], item)

                return Stripped(f"{instance} = append({instance}, {item})"), None

            else:
                assert_never(kind)

        if not isinstance(node.member.instance, (parse_tree.Name, parse_tree.Member)):
            instance = Stripped(f"({instance})")

        method_name = golang_naming.method_name(node.member.name)

        args = [
            self._as_int64_position(arg_node, arg)
            for arg_node, arg in zip(node.args, args, strict=True)
        ]

        args_joined = ", ".join(args)

        # Apply heuristic for breaking the lines
        if len(args_joined) > 50:
            args_joined = "\n".join(f"{arg}," for arg in args)

            return (
                Stripped(
                    f"""\
{instance}.{method_name}(
{I}{indent_but_first_line(args_joined, I)}
)"""
                ),
                None,
            )
        else:
            return Stripped(f"{instance}.{method_name}({args_joined})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_function_call(
        self, node: parse_tree.FunctionCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

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

        args: List[Stripped] = []
        for i, arg_node in enumerate(node.args):
            # NOTE (mristin):
            # The type parameter of a generic sequence can not be inferred from
            # an untyped ``nil``, so we pass on a typed ``nil`` instead, see
            # :py:func:`intermediate.generic_sequence_item_class`.
            if (
                isinstance(
                    func_type, intermediate_type_inference.VerificationTypeAnnotation
                )
                and isinstance(arg_node, parse_tree.Constant)
                and arg_node.value is None
                and intermediate.generic_sequence_item_class(
                    func_type.func.arguments[i]
                )
                is not None
            ):
                list_type_anno = intermediate.beneath_optional(
                    func_type.func.arguments[i].type_annotation
                )
                assert isinstance(list_type_anno, intermediate.ListTypeAnnotation)

                list_type = golang_common.generate_type(
                    type_annotation=list_type_anno, types_package=self._types_package
                )
                args.append(Stripped(f"{list_type}(nil)"))
                continue

            # NOTE (mristin):
            # We pass on a pointer to an optional argument of a verification
            # function, and de-reference the values otherwise.
            if isinstance(
                func_type, intermediate_type_inference.VerificationTypeAnnotation
            ) and golang_pointering.is_pointer_type(
                func_type.func.arguments[i].type_annotation
            ):
                arg, error = self._transform_as_pointer(arg_node)
            else:
                arg, error = self._transform_and_dereference_if_necessary(arg_node)

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
            function_name, error = self.transform_name(node.name)
            if error is not None:
                return None, error

            assert function_name is not None

            args = [
                self._as_int64_position(arg_node, arg)
                for arg_node, arg in zip(node.args, args, strict=True)
            ]

            args_joined = ", ".join(args)

            # Apply heuristic for breaking the lines
            if len(function_name) + len(args_joined) > 50:
                args_joined = "\n".join(f"{arg}," for arg in args)
                return (
                    Stripped(
                        f"""\
{function_name}(
{I}{indent_but_first_line(args_joined, I)}
)"""
                    ),
                    None,
                )
            else:
                return Stripped(f"{function_name}({args_joined})"), None

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

                if isinstance(
                    self.type_map[node.args[0]],
                    intermediate_type_inference.TupleTypeAnnotation,
                ):
                    no_parentheses_types = (
                        parse_tree.Member,
                        parse_tree.FunctionCall,
                        parse_tree.IsInstance,
                        parse_tree.MethodCall,
                        parse_tree.Name,
                        parse_tree.Constant,
                        parse_tree.Index,
                        parse_tree.Slice,
                        parse_tree.IsIn,
                    )

                    # NOTE (mristin):
                    # We put the de-referencing in parentheses as ``*x.Len()``
                    # would de-reference the length instead of the tuple.
                    collection = args[0]
                    if not isinstance(
                        node.args[0], no_parentheses_types
                    ) or collection.startswith("*"):
                        collection = Stripped(f"({collection})")

                    return Stripped(f"{collection}.Len()"), None

                len_function = "len"

                # NOTE (mristin):
                # We do not use the native ``len`` on strings as it counts
                # the UTF-8 bytes instead of the characters, unlike Python. See
                # ``LenStr`` in the generated common package.
                if (
                    intermediate_type_inference.try_primitive_type(
                        intermediate_type_inference.beneath_optional(
                            self.type_map[node.args[0]]
                        )
                    )
                    is intermediate_type_inference.PrimitiveType.STR
                ):
                    len_function = "ourcommon.LenStr"

                if "\n" in args[0]:
                    return (
                        Stripped(
                            f"""\
{len_function}(
{I}{indent_but_first_line(args[0], I)},
)"""
                        ),
                        None,
                    )

                return Stripped(f"{len_function}({args[0]})"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.ABS
            ):
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                # NOTE (mristin):
                # The type of the result of ``abs`` equals the type of its argument,
                # and has been inferred at the call site.
                a_type = intermediate_type_inference.try_primitive_type(
                    self.type_map[node]
                )

                abs_function: str
                if a_type is intermediate_type_inference.PrimitiveType.FLOAT:
                    abs_function = "math.Abs"

                elif a_type is intermediate_type_inference.PrimitiveType.INT:
                    # NOTE (mristin):
                    # Go provides no absolute value of integers in its standard
                    # library, so we call our own helper, see
                    # :py:data:`aas_core_codegen.golang.lib._generate_common.ABS_INT64`.
                    abs_function = f"ourcommon.{ABS_INT64_FUNCTION_NAME}"

                else:
                    return None, Error(
                        node.original_node,
                        f"Expected the result of abs to be either an integer or "
                        f"a floating-point number, but got {self.type_map[node]}; "
                        f"this should have been caught before",
                    )

                if "\n" in args[0]:
                    return (
                        Stripped(
                            f"""\
{abs_function}(
{I}{indent_but_first_line(args[0], I)},
)"""
                        ),
                        None,
                    )

                return Stripped(f"{abs_function}({args[0]})"), None

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
                # which we transpile as an ``append`` to an empty slice of
                # the same type.
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

                return Stripped(f"append({the_list}[:0:0], {the_list}...)"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.SET
            ):
                set_type, error_msg = generate_type(
                    self.type_map[node], types_package=self._types_package
                )
                if error_msg is not None:
                    return None, Error(node.original_node, error_msg)

                assert set_type is not None
                return Stripped(f"make({set_type})"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.INT
            ):
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                # NOTE (mristin):
                # We parse the strings with our own helper so that all the SDKs
                # accept the very same texts, see
                # :py:data:`aas_core_codegen.golang.lib._generate_common.PARSE_SAFE_INT`.
                if "\n" in args[0]:
                    return (
                        Stripped(
                            f"""\
ourcommon.{PARSE_SAFE_INT_FUNCTION_NAME}(
{I}{indent_but_first_line(args[0], I)},
)"""
                        ),
                        None,
                    )

                return (
                    Stripped(f"ourcommon.{PARSE_SAFE_INT_FUNCTION_NAME}({args[0]})"),
                    None,
                )

            else:
                assert_never(func_type.func.kind)
        else:
            assert_never(func_type)

        raise AssertionError("Should not have gotten here")

    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.value is None:
            return Stripped("nil"), None
        elif isinstance(node.value, bool):
            return Stripped("true" if node.value else "false"), None
        elif isinstance(node.value, (int, float)):
            return Stripped(str(node.value)), None
        elif isinstance(node.value, str):
            return Stripped(golang_common.string_literal(node.value)), None
        else:
            assert_never(node.value)

        raise AssertionError("Should not have gotten here")

    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        item_exprs: List[Stripped] = []

        for value_node in node.values:
            item_expr, error = self._transform_and_dereference_if_necessary(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert item_expr is not None
            item_exprs.append(item_expr)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the tuple", errors
            )

        tuple_type_anno = self.type_map[node]

        go_tuple_type, error_msg = generate_type(
            type_annotation=tuple_type_anno, types_package=self._types_package
        )
        if error_msg is not None:
            return None, Error(node.original_node, error_msg)

        assert go_tuple_type is not None

        joined_item_exprs = ",\n".join(item_exprs)

        return (
            Stripped(
                f"""\
{go_tuple_type}{{
{I}{indent_but_first_line(joined_item_exprs, I)},
}}"""
            ),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_list_literal(
        self, node: parse_tree.ListLiteral
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        items: List[Stripped] = []

        for item_node in node.items:
            item, error = self._transform_and_dereference_if_necessary(item_node)
            if error is not None:
                errors.append(error)
                continue

            assert item is not None

            # NOTE (mristin):
            # The lengths are ``int``'s, so we convert them to our integers.
            items.append(self._as_int64_position(item_node, item))

        go_list_type, error_msg = generate_type(
            type_annotation=self.type_map[node], types_package=self._types_package
        )
        if error_msg is not None:
            errors.append(Error(node.original_node, error_msg))

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the list literal", errors
            )

        assert go_list_type is not None

        if len(items) == 0:
            return Stripped(f"{go_list_type}{{}}"), None

        one_liner = f"{go_list_type}{{{', '.join(items)}}}"
        if "\n" not in one_liner and len(one_liner) <= 60:
            return Stripped(one_liner), None

        items_joined = ",\n".join(items)
        return (
            Stripped(
                f"""\
{go_list_type}{{
{I}{indent_but_first_line(items_joined, I)},
}}"""
            ),
            None,
        )

    def transform_is_none(
        self, node: parse_tree.IsNone
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        # NOTE (mristin):
        # We explicitly do not call :py:meth:`_transform_and_dereference_if_necessary`
        # here as we have to work on the pointer, not the value.

        value, error = self.transform(node.value)
        if error is not None:
            return None, error

        no_parentheses_types = (
            parse_tree.Name,
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
            parse_tree.IsInstance,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
        )
        if isinstance(node.value, no_parentheses_types):
            return Stripped(f"{value} == nil"), None
        else:
            return Stripped(f"({value}) == nil"), None

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
            parse_tree.IsInstance,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
        )
        if isinstance(node.value, no_parentheses_types_in_this_context):
            return Stripped(f"{value} != nil"), None
        else:
            return Stripped(f"({value}) != nil"), None

    @abc.abstractmethod
    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        raise NotImplementedError

    def transform_not(
        self, node: parse_tree.Not
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        operand, error = self._transform_and_dereference_if_necessary(node.operand)
        if error is not None:
            return None, error

        no_parentheses_types_in_this_context = (
            parse_tree.Name,
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
            parse_tree.IsInstance,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
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
            value, error = self._transform_and_dereference_if_necessary(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert value is not None

            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.IsInstance,
                parse_tree.Comparison,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.All,
                parse_tree.Any,
            )

            if not isinstance(value_node, no_parentheses_types_in_this_context):
                value = Stripped(f"({value})")

            values.append(value)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the conjunction", errors
            )

        values_joined = " &&\n".join(values)
        return Stripped(values_joined), None

    def transform_or(
        self, node: parse_tree.Or
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        values: List[Stripped] = []

        for value_node in node.values:
            value, error = self._transform_and_dereference_if_necessary(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert value is not None

            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.IsInstance,
                parse_tree.Comparison,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.All,
                parse_tree.Any,
            )

            if not isinstance(value_node, no_parentheses_types_in_this_context):
                value = Stripped(f"({value})")

            values.append(value)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the conjunction", errors
            )

        values_joined = " ||\n".join(values)
        return Stripped(values_joined), None

    def _transform_add_or_sub(
        self, node: Union[parse_tree.Add, parse_tree.Sub]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        left, error = self._transform_and_dereference_if_necessary(node.left)
        if error is not None:
            errors.append(error)

        right, error = self._transform_and_dereference_if_necessary(node.right)
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
            parse_tree.IsInstance,
            parse_tree.Constant,
            parse_tree.Name,
            parse_tree.IsIn,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
        )

        # NOTE (mristin):
        # The lengths are represented as ``int`` in Go, while the other integers
        # are ``int64``'s, and Go does not mix the two in arithmetic. If a length is
        # combined with an integer which is not a literal, the result is an integer,
        # see :py:func:`aas_core_codegen.intermediate.type_inference._combines_to_length`,
        # so we widen the length to ``int64``. The integer literals are untyped
        # constants in Go and need no conversion.
        is_integer = (
            intermediate_type_inference.try_primitive_type(self.type_map[node])
            is intermediate_type_inference.PrimitiveType.INT
        )

        length = intermediate_type_inference.PrimitiveType.LENGTH

        if (
            is_integer
            and intermediate_type_inference.try_primitive_type(self.type_map[node.left])
            is length
        ):
            left = Stripped(f"int64({left})")
        elif not isinstance(node.left, no_parentheses_types_in_this_context):
            left = Stripped(f"({left})")

        if (
            is_integer
            and intermediate_type_inference.try_primitive_type(
                self.type_map[node.right]
            )
            is length
        ):
            right = Stripped(f"int64({right})")
        elif not isinstance(node.right, no_parentheses_types_in_this_context):
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

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_mod(
        self, node: parse_tree.Mod
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        left, error = self._transform_and_dereference_if_necessary(node.left)
        if error is not None:
            errors.append(error)

        right, error = self._transform_and_dereference_if_necessary(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the modulo operation", errors
            )

        assert left is not None
        assert right is not None

        # NOTE (mristin):
        # The constrained primitives behave like their constrainees in arithmetic.
        left_a_type = intermediate_type_inference.try_primitive_type(
            self.type_map[node.left]
        )
        right_a_type = intermediate_type_inference.try_primitive_type(
            self.type_map[node.right]
        )
        result_a_type = intermediate_type_inference.try_primitive_type(
            self.type_map[node]
        )

        length = intermediate_type_inference.PrimitiveType.LENGTH
        integer = intermediate_type_inference.PrimitiveType.INT

        if (
            left_a_type not in (integer, length)
            or right_a_type not in (integer, length)
            or result_a_type not in (integer, length)
        ):
            return None, Error(
                node.original_node,
                f"Expected the operands and the result of the modulo to be integers "
                f"or lengths, but got the left operand {self.type_map[node.left]}, "
                f"the right operand {self.type_map[node.right]} and "
                f"the result {self.type_map[node]}; "
                f"this should have been caught before",
            )

        # NOTE (mristin):
        # We deliberately do not use the native Go operator ``%`` in general. Go
        # truncates the division towards zero so that its remainder takes the sign
        # of the dividend (``-7 % 3 == -1``). The meta-model is written in Python
        # where the division is floored so that the remainder takes the sign of
        # the divisor (``-7 % 3 == 2``). The two only coincide when the operands have
        # the same sign, but the invariants must behave the same in all the SDKs for
        # all the inputs. Hence, we call the helper which computes the floored
        # remainder, see
        # :py:data:`aas_core_codegen.golang.lib._generate_common.FLOOR_MOD`.
        #
        # However, a length is never negative. When the dividend is a length and
        # the divisor is either a length or a positive integer literal, both operands
        # are non-negative, so the native operator gives the same remainder as
        # the floored division. We use the native operator in that case for
        # readability, *e.g.*, ``len(text) % 2``. Both operands are ``int`` or
        # untyped constants in that case, so no conversion is necessary either.
        if left_a_type is length and (
            right_a_type is length
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

        # NOTE (mristin):
        # The lengths are represented as ``int`` in Go, while the helper works on
        # ``int64``, so we have to convert them explicitly. The integer literals are
        # untyped constants in Go and need no conversion.
        if left_a_type is length:
            left = Stripped(f"int64({left})")

        if right_a_type is length:
            right = Stripped(f"int64({right})")

        args_joined = f"{left}, {right}"
        call: Stripped
        if "\n" in args_joined or len(args_joined) > 50:
            call = Stripped(
                f"""\
ourcommon.{FLOOR_MOD_FUNCTION_NAME}(
{I}{indent_but_first_line(left, I)},
{I}{indent_but_first_line(right, I)},
)"""
            )
        else:
            call = Stripped(f"ourcommon.{FLOOR_MOD_FUNCTION_NAME}({args_joined})")

        if result_a_type is length:
            # NOTE (mristin):
            # The remainder of a length is a length, and lengths are represented as
            # ``int`` in Go.
            if "\n" in call:
                return (
                    Stripped(
                        f"""\
int(
{I}{indent_but_first_line(call, I)},
)"""
                    ),
                    None,
                )

            return Stripped(f"int({call})"), None

        return call, None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_neg(
        self, node: parse_tree.Neg
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        operand, error = self._transform_and_dereference_if_necessary(node.operand)
        if error is not None:
            return None, Error(
                node.original_node,
                "Failed to transpile the arithmetic negation",
                [error],
            )

        assert operand is not None

        # NOTE (mristin):
        # We have to put a negation (or a negative constant) in parentheses as well,
        # since ``--x`` would be lexed as a decrement in Go.
        no_parentheses_types_in_this_context = (
            parse_tree.Member,
            parse_tree.MethodCall,
            parse_tree.FunctionCall,
            parse_tree.Name,
            parse_tree.Index,
        )

        if not isinstance(node.operand, no_parentheses_types_in_this_context):
            operand = Stripped(f"({operand})")

        elif operand.startswith("*"):
            # NOTE (mristin):
            # ``-*x`` is valid Go, but we put the de-referencing in parentheses
            # for readability.
            operand = Stripped(f"({operand})")

        return Stripped(f"-{operand}"), None

    def transform_joined_str(
        self, node: parse_tree.JoinedStr
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if all(isinstance(value, str) for value in node.values):
            text = "".join(node.values)  # type: ignore
            return golang_common.string_literal(text), None

        # NOTE (mristin):
        # We need the interpolation if we got so far.

        text_parts: List[str] = []
        args: List[str] = []

        for value in node.values:
            if isinstance(value, str):
                string_literal = golang_common.string_literal(value.replace("%", "%%"))

                # We need to remove double-quotes since we are joining everything
                # ourselves later.

                assert string_literal.startswith('"') and string_literal.endswith('"')

                string_literal_wo_quotes = string_literal[1:-1]
                text_parts.append(string_literal_wo_quotes)

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self._transform_and_dereference_if_necessary(value.value)
                if error is not None:
                    return None, error

                assert code is not None

                text_parts.append("%v")
                args.append(code)
            else:
                assert_never(value)

        string_literal = golang_common.string_literal("".join(text_parts))

        args_joined = ",\n".join(args)

        return (
            Stripped(
                f"""\
fmt.Sprintf(
{I}{indent_but_first_line(string_literal, I)},
{I}{indent_but_first_line(args_joined, I)},
)"""
            ),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_range_bound(
        self, node: parse_tree.Expression, loop_variable_go_type: Stripped
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the bound of a range, and convert it to the loop variable type.

        Go does not implicitly convert between ``int`` and ``int64``, so we
        convert the bound explicitly if its type differs from the type of
        the loop variable. The integer literals are untyped in Go, so we leave
        them as-is.
        """
        code, error = self._transform_and_dereference_if_necessary(node)
        if error is not None:
            return None, error

        assert code is not None

        if isinstance(node, parse_tree.Constant):
            return code, None

        bound_type = intermediate_type_inference.beneath_optional(self.type_map[node])
        assert isinstance(
            bound_type, intermediate_type_inference.PrimitiveTypeAnnotation
        ), f"{bound_type=}"

        if PRIMITIVE_TYPE_MAP[bound_type.a_type] == loop_variable_go_type:
            return code, None

        return Stripped(f"{loop_variable_go_type}({code})"), None

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
            # NOTE (mristin):
            # The helpers ``SomeRange`` and ``AllRange`` are generic, so the bounds
            # need to match the type of the loop variable exactly.
            variable_type = self.type_map[node.generator.variable]
            assert isinstance(
                variable_type, intermediate_type_inference.PrimitiveTypeAnnotation
            ), f"{variable_type=}"

            variable_go_type = PRIMITIVE_TYPE_MAP[variable_type.a_type]

            start, error = self._transform_range_bound(
                node.generator.start, variable_go_type
            )
            if error is not None:
                errors.append(error)

            end, error = self._transform_range_bound(
                node.generator.end, variable_go_type
            )
            if error is not None:
                errors.append(error)

        else:
            assert_never(node.generator)

        variable_name = node.generator.variable.identifier
        variable_type_annotation = self.type_map[node.generator.variable]

        variable_name_go = golang_naming.variable_name(variable_name)

        # NOTE (mristin):
        # The items of a generic sequence are of the type parameter, and
        # the ``ourcommon.All`` and ``ourcommon.Some`` infer their type from both
        # the condition and the slice, so the condition needs to expect the type
        # parameter as well.
        type_parameter = self._type_parameter_of(variable_type_annotation)
        if type_parameter is not None:
            variable_type_go: Optional[Stripped] = Stripped(type_parameter)
        else:
            variable_type_go, error_msg = generate_type(
                type_annotation=variable_type_annotation,
                types_package=self._types_package,
            )
            if error_msg is not None:
                errors.append(Error(node.generator.variable.original_node, error_msg))

        try:
            self._environment.set(
                identifier=variable_name, type_annotation=variable_type_annotation
            )
            self._variable_name_set.add(variable_name)

            condition, error = self._transform_and_dereference_if_necessary(
                node.condition
            )
            if error is not None:
                errors.append(error)

            variable, error = self._transform_and_dereference_if_necessary(
                node.generator.variable
            )
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

        assert (iteration is not None) ^ (start is not None and end is not None)

        assert variable is not None
        assert condition is not None

        if isinstance(node.generator, parse_tree.ForEach):
            assert iteration is not None

            # NOTE (mristin):
            # A set is a map, so we iterate over its keys, see ``SomeKey`` and
            # ``AllKeys`` in the generated common package.
            over_set = isinstance(
                self.type_map[node.generator.iteration],
                intermediate_type_inference.SetTypeAnnotation,
            )

            qualifier_function: str
            if isinstance(node, parse_tree.Any):
                qualifier_function = "SomeKey" if over_set else "Some"
            elif isinstance(node, parse_tree.All):
                qualifier_function = "AllKeys" if over_set else "All"
            else:
                assert_never(node)

            assert qualifier_function is not None

            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.IsInstance,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.All,
                parse_tree.Any,
            )

            if not isinstance(
                node.generator.iteration, no_parentheses_types_in_this_context
            ):
                source = Stripped(f"({iteration})")
            else:
                source = iteration

            return (
                Stripped(
                    f"""\
ourcommon.{qualifier_function}(
{I}func({variable_name_go} {variable_type_go}) bool {{
{II}return {indent_but_first_line(condition, III)}
{I}}},
{I}{indent_but_first_line(source, I)},
)"""
                ),
                None,
            )

        elif isinstance(node.generator, parse_tree.ForRange):
            if isinstance(node, parse_tree.Any):
                qualifier_function = "SomeRange"
            elif isinstance(node, parse_tree.All):
                qualifier_function = "AllRange"
            else:
                assert_never(node)

            assert start is not None
            assert end is not None

            return (
                Stripped(
                    f"""\
ourcommon.{qualifier_function}(
{I}func({variable_name_go} {variable_type_go}) bool {{
{II}return {indent_but_first_line(condition, III)}
{I}}},
{I}{indent_but_first_line(start, I)},
{I}{indent_but_first_line(end, I)},
)"""
                ),
                None,
            )

        else:
            assert_never(node.generator)

    def transform_any(
        self, node: parse_tree.Any
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_any_or_all(node)

    def transform_all(
        self, node: parse_tree.All
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_any_or_all(node)

    def _wrap_into_named_union_if_necessary(
        self,
        value: Stripped,
        target_type: intermediate_type_inference.TypeAnnotationUnion,
        value_type: intermediate_type_inference.TypeAnnotationUnion,
    ) -> Stripped:
        """
        Wrap the instance of a class, given as ``value``, into the named union.

        A named union is a pointer to a wrapper struct in Go, so we wrap
        the instance as the most specific root of the union.
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

        function_name = self._our_type_name(
            golang_naming.function_name(
                Identifier(f"new_{union_type.our_type.name}_from_{root.name}")
            )
        )

        return Stripped(f"{function_name}({value})")

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        if isinstance(node.target, parse_tree.Member):
            # NOTE (mristin):
            # The type inference allows only the properties of a class as member
            # targets, which we assign to with the setters.
            instance_type = self.type_map[node.target.instance]
            assert isinstance(
                instance_type, intermediate_type_inference.OurTypeAnnotation
            ) and isinstance(instance_type.our_type, intermediate.Class)

            prop = instance_type.our_type.properties_by_name[node.target.name]

            instance, error = self.transform(node.target.instance)
            if error is not None:
                errors.append(error)

            if golang_pointering.is_pointer_type(prop.type_annotation):
                value, error = self._transform_as_pointer(node.value)
            else:
                value, error = self._transform_and_dereference_if_necessary(node.value)
                if error is None:
                    assert value is not None

                    # NOTE (mristin):
                    # A length can only be assigned to an integer property,
                    # an ``int64``, while the lengths are ``int``'s.
                    value = self._as_int64_position(node.value, value)

            if error is not None:
                errors.append(error)

            if len(errors) > 0:
                return None, Error(
                    node.original_node, "Failed to transpile the assignment", errors
                )

            assert instance is not None
            assert value is not None

            value = self._wrap_into_named_union_if_necessary(
                value=value,
                target_type=self.type_map[node.target],
                value_type=self.type_map[node.value],
            )

            setter_name = golang_naming.setter_name(node.target.name)

            # NOTE (mristin):
            # This is a rudimentary heuristic for basic line breaks, but works well in
            # practice.
            if "\n" in value or len(value) > 50:
                return (
                    Stripped(
                        f"""\
{instance}.{setter_name}(
{I}{indent_but_first_line(value, I)},
)"""
                    ),
                    None,
                )

            return Stripped(f"{instance}.{setter_name}({value})"), None

        # NOTE (mristin):
        # A variable holding an optional value is a pointer. We re-bind the pointer
        # instead of writing through it, since the pointer might alias a property,
        # while Python only re-binds the name.
        rebinds_pointer = (
            isinstance(node.target, parse_tree.Name)
            and self._is_pointer_map[node.target]
        )

        value, error = (
            self._transform_as_pointer(node.value)
            if rebinds_pointer
            else self._transform_and_dereference_if_necessary(node.value)
        )
        if error is not None:
            errors.append(error)

        is_definition = False

        target: Optional[Stripped] = None
        if (
            isinstance(node.target, parse_tree.Name)
            and self._environment.find(identifier=node.target.identifier) is None
        ):
            # NOTE (mristin):
            # This is a variable definition as we did not specify the identifier
            # in the environment.

            is_definition = True

            type_anno = self.type_map[node.target]
            self._variable_name_set.add(node.target.identifier)
            self._environment.set(
                identifier=node.target.identifier, type_annotation=type_anno
            )

            target, error = self.transform_name(node=node.target)
            if error is not None:
                errors.append(error)
        else:
            # NOTE (mristin):
            # The slices share their underlying arrays, so the assignment to an item
            # of a list is visible through all the references to the list, as in
            # Python.
            target, error = self.transform(node=node.target)
            if error is not None:
                errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assignment", errors
            )

        assert target is not None
        assert value is not None

        if not rebinds_pointer and self._is_pointer_map[node.target]:
            target = Stripped(f"*{target}")

        # NOTE (mristin):
        # A length can be assigned to an integer variable or an integer item of
        # a list, which are ``int64``'s, while the lengths are ``int``'s. A variable
        # defined by a length is an ``int`` itself, unless it is declared as
        # an integer with a type annotation.
        if (not is_definition or node.annotation is not None) and not rebinds_pointer:
            target_type = (
                self._environment.find(node.target.identifier)
                if isinstance(node.target, parse_tree.Name)
                else self.type_map[node.target]
            )

            if (
                target_type is not None
                and intermediate_type_inference.try_primitive_type(
                    intermediate_type_inference.beneath_optional(target_type)
                )
                is intermediate_type_inference.PrimitiveType.INT
            ):
                value = self._as_int64_position(node.value, value)

        # NOTE (mristin):
        # The integer literals are untyped in Go, and would be inferred as ``int`` in
        # the short variable declaration, while we represent the integers as
        # ``int64``. Hence, we need to explicitly convert them.
        if (
            is_definition
            and not rebinds_pointer
            and isinstance(node.value, parse_tree.Constant)
            and isinstance(node.value.value, int)
            and not isinstance(node.value.value, bool)
        ):
            value = Stripped(f"int64({value})")

        value = self._wrap_into_named_union_if_necessary(
            value=value,
            target_type=self.type_map[node.target],
            value_type=self.type_map[node.value],
        )

        assignment = "=" if not is_definition else ":="

        if is_definition and node.annotation is not None:
            # NOTE (mristin):
            # We spell out the declared type, as it might differ from the type of
            # the value, *e.g.*, for ``nil``.
            declared_type, error_msg = generate_type(
                type_annotation=self.type_map[node.target],
                types_package=self._types_package,
            )
            if error_msg is not None:
                return None, Error(node.annotation.original_node, error_msg)

            # NOTE (mristin):
            # An immutable alias of a generic sequence shares its type annotation,
            # see :py:meth:`intermediate_type_inference._Inferrer.transform_assignment`,
            # so we declare the alias with the type parameter as well. The optional
            # slices are not pointers, as the slices are nilable.
            target_type_beneath = intermediate_type_inference.beneath_optional(
                self.type_map[node.target]
            )
            if isinstance(
                target_type_beneath, intermediate_type_inference.ListTypeAnnotation
            ):
                type_parameter = self._type_parameter_of(target_type_beneath.items)
                if type_parameter is not None:
                    declared_type = Stripped(f"[]{type_parameter}")

            target = Stripped(f"var {target} {declared_type}")
            assignment = "="

        # NOTE (mristin):
        # This is a rudimentary heuristic for basic line breaks, but works well in
        # practice.
        if "\n" in value or len(value) > 50:
            return (
                Stripped(
                    f"""\
{target} {assignment}
{I}{indent_but_first_line(value, I)}"""
                ),
                None,
            )

        return Stripped(f"{target} {assignment} {value}"), None

    def transform_return(
        self, node: parse_tree.Return
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.value is None:
            return Stripped("return"), None

        # NOTE (mristin):
        # The type inference narrows the types based on the nullability checks, so
        # the inferred type of the value might be a non-nullable, but Golang pointers
        # remain pointers even after we check for them. The type inference records
        # the return type of the function on the return, so we know whether to
        # return a pointer or de-reference it.
        returns = self.type_map[node]
        value_type = self.type_map[node.value]

        value: Optional[Stripped]
        if isinstance(value_type, intermediate_type_inference.OptionalTypeAnnotation):
            value, error = self.transform(node.value)
        elif golang_pointering.is_pointer_type(returns):
            value, error = self._transform_as_pointer(node.value)
        else:
            value, error = self._transform_and_dereference_if_necessary(node.value)

        if error is not None:
            return None, error

        assert value is not None

        # NOTE (mristin):
        # A length can only be returned from a function returning an integer,
        # an ``int64``, while the lengths are ``int``'s.
        value = self._as_int64_position(node.value, value)

        # NOTE (mristin):
        # This is a rudimentary heuristic for basic line breaks, but works well in
        # practice.
        if "\n" in value or len(value) > 50:
            return (
                Stripped(
                    f"""\
return {indent_but_first_line(value, I)}"""
                ),
                None,
            )

        return Stripped(f"return {value}"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_branch(
        self, statements: Sequence[parse_tree.StatementUnion]
    ) -> Tuple[Optional[Tuple[List[Stripped], bool]], Optional[Error]]:
        """
        Transpile the ``statements`` of a block in a new scope.

        The block is a switch branch or the body of a for-loop. Each clause of a Go
        switch is an implicit block, and so is the body of a loop, so the variables
        defined in the ``statements`` are not visible after the block.

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
        subject, error = self._transform_and_dereference_if_necessary(node.subject)
        if error is not None:
            return None, error

        assert subject is not None

        errors: List[Error] = []

        # NOTE (mristin):
        # We collect the headers of the clauses together with their statements, and
        # treat the default as the last clause.
        clauses: List[Tuple[str, Sequence[parse_tree.StatementUnion]]] = []

        for case in node.cases:
            labels: List[Stripped] = []
            for label in case.labels:
                label_code, error = self.transform(label)
                if error is not None:
                    errors.append(error)
                    continue

                assert label_code is not None
                labels.append(label_code)

            clauses.append((f"case {', '.join(labels)}:", case.body))

        if node.default is not None:
            clauses.append(("default:", node.default))

        writer = io.StringIO()
        writer.write(f"switch {subject} {{")

        for header, statements in clauses:
            stmts_and_defines, error = self._transform_branch(statements)
            if error is not None:
                errors.append(error)
                continue

            assert stmts_and_defines is not None

            # NOTE (mristin):
            # Each clause is an implicit block in Go, so we need no explicit block
            # for the variables. Go does not fall through, so we need no ``break``.
            stmts, _ = stmts_and_defines

            writer.write(f"\n{header}")
            for stmt in stmts:
                writer.write("\n")
                writer.write(textwrap.indent(stmt, I))

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
        variable_type_annotation = self.type_map[node.generator.variable]
        variable = golang_naming.variable_name(variable_name)

        header: Optional[str] = None
        if isinstance(node.generator, parse_tree.ForEach):
            # NOTE (mristin):
            # Lists are represented as slices in Go, which are never pointers.
            # Sets are represented as maps, and we iterate over their keys.
            iteration, error = self.transform(node.generator.iteration)
            if error is not None:
                errors.append(error)
            else:
                assert iteration is not None
                if isinstance(
                    self.type_map[node.generator.iteration],
                    intermediate_type_inference.SetTypeAnnotation,
                ):
                    header = (
                        f"for {variable} := range "
                        f"{indent_but_first_line(iteration, I)}"
                    )
                else:
                    header = (
                        f"for _, {variable} := range "
                        f"{indent_but_first_line(iteration, I)}"
                    )

        elif isinstance(node.generator, parse_tree.ForRange):
            assert isinstance(
                variable_type_annotation,
                intermediate_type_inference.PrimitiveTypeAnnotation,
            ), f"{variable_type_annotation=}"

            variable_go_type = PRIMITIVE_TYPE_MAP[variable_type_annotation.a_type]

            start, error = self._transform_range_bound(
                node.generator.start, variable_go_type
            )
            if error is not None:
                errors.append(error)

            end, error = self._transform_range_bound(
                node.generator.end, variable_go_type
            )
            if error is not None:
                errors.append(error)

            if start is not None and end is not None:
                # NOTE (mristin):
                # The integer literals are untyped in Go, and would be inferred as
                # ``int`` in the short variable declaration, so we explicitly
                # convert the start if the loop variable is not an ``int``.
                if (
                    isinstance(node.generator.start, parse_tree.Constant)
                    and variable_go_type != "int"
                ):
                    start = Stripped(f"{variable_go_type}({start})")

                header = (
                    f"for {variable} := {indent_but_first_line(start, I)}; "
                    f"{variable} < {indent_but_first_line(end, I)}; "
                    f"{variable}++"
                )

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
        loop_environment.set(
            identifier=variable_name, type_annotation=variable_type_annotation
        )
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
        writer.write(f"{header} {{")
        for stmt in stmts:
            writer.write("\n")
            writer.write(textwrap.indent(stmt, I))
        writer.write("\n}")

        return Stripped(writer.getvalue()), None

    def transform_continue(
        self, node: parse_tree.Continue
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return Stripped("continue"), None

    def transform_break(
        self, node: parse_tree.Break
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return Stripped("break"), None

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
            message = golang_common.string_literal(
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
            # NOTE (mristin):
            # Go inserts a semicolon at the end of a line which ends with
            # an operand, so we need to close the parenthesis on the last line
            # of the condition.
            header = f"""\
if (
{I}{indent_but_first_line(negation, I)})"""
        else:
            header = f"if {negation}"

        return (
            Stripped(
                f"""\
{header} {{
{I}panic(
{II}{indent_but_first_line(message, II)},
{I})
}}"""
            ),
            None,
        )

    def transform_expression_statement(
        self, node: parse_tree.ExpressionStatement
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self.transform(node.expression)

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
            condition, error = self._transform_and_dereference_if_necessary(
                branch.condition
            )
            if error is not None:
                errors.append(error)
                continue

            assert condition is not None

            keyword = "if" if i == 0 else "else if"
            if "\n" in condition:
                # NOTE (mristin):
                # Go inserts a semicolon at the end of a line which ends with
                # an operand, so we need to close the parenthesis on the last line
                # of the condition.
                header = f"""\
{keyword} (
{I}{indent_but_first_line(condition, I)})"""
            else:
                header = f"{keyword} {condition}"

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
                writer.write(" ")

            writer.write(f"{header} {{")
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
assert all(op in Transpiler._GOLANG_COMPARISON_MAP for op in parse_tree.Comparator)
