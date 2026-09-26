"""Transpile Python to Go code."""
import abc
import io
import textwrap
from typing import (
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


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def generate_type(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
    types_package: Optional[Identifier] = None,
) -> Tuple[Optional[Stripped], Optional[str]]:
    """
    Generate the Go type for the given type annotation.

    If ``types_package`` is specified, it is prepended to all our types.

    (mristin, 2023-06-01): We do not handle all the type annotations from
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
        item_types = []  # type: List[Stripped]
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
            f"(mristin, 2023-06-01): We do not handle "
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

    _GOLANG_COMPARISON_MAP = {
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
        self._variable_name_set = set()  # type: Set[Identifier]

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
        raise NotImplementedError()

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

        index_as_int = None  # type: Optional[int]
        try:
            index_as_int = int(index)
        except ValueError:
            pass

        if index_as_int is not None and index_as_int < 0:
            if "\n" in collection:
                # pylint: disable=invalid-unary-operand-type
                index = Stripped(
                    f"""\
len(
{I}{indent_but_first_line(collection, I)}
) - {-index_as_int}"""
                )
            else:
                index = Stripped(
                    f"len({collection}) - {-index_as_int}"  # pylint: disable=invalid-unary-operand-type
                )

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

    def _as_int64_position(self, node: parse_tree.Node, code: Stripped) -> Stripped:
        """
        Convert the transpiled position ``node`` to an ``int64``.

        The string helpers take the positions as ``int64``'s, our integers,
        while the lengths are ``int``'s.
        """
        type_anno = self.type_map[node]
        if (
            isinstance(type_anno, intermediate_type_inference.PrimitiveTypeAnnotation)
            and type_anno.a_type is intermediate_type_inference.PrimitiveType.LENGTH
        ):
            return Stripped(f"int64({code})")

        return code

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_slice(
        self, node: parse_tree.Slice
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]

        collection, error = self.transform(node.collection)
        if error is not None:
            errors.append(error)

        start = None  # type: Optional[Stripped]
        if node.start is not None:
            start, error = self.transform(node.start)
            if error is not None:
                errors.append(error)

        end = None  # type: Optional[Stripped]
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
        # We do not use the native slicing as it panics on the positions out of
        # range, and does not count the negative ones from the end, unlike Python.
        # See ``SliceStr`` in the generated common package.
        start_int64 = (
            self._as_int64_position(node.start, start)
            if node.start is not None and start is not None
            else Stripped("0")
        )

        if node.end is None:
            return (
                Stripped(f"aascommon.SliceStrFrom({collection}, {start_int64})"),
                None,
            )

        assert end is not None
        end_int64 = self._as_int64_position(node.end, end)

        return (
            Stripped(f"aascommon.SliceStr({collection}, {start_int64}, {end_int64})"),
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
        )

        if not isinstance(node.left, no_parentheses_types):
            left = Stripped(f"({left})")

        if not isinstance(node.right, no_parentheses_types):
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
aascommon.MapContains(
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

        checks = []  # type: List[Stripped]
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
        errors = []  # type: List[Error]

        instance, error = self._transform_and_dereference_if_necessary(
            node.member.instance
        )
        if error is not None:
            errors.append(error)

        args = []  # type: List[Stripped]
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
            if member_type.method is intermediate_type_inference.STR_FIND:
                if len(args) == 1:
                    return (
                        Stripped(f"int64(strings.Index({instance}, {args[0]}))"),
                        None,
                    )

                # NOTE (mristin):
                # The ``strings.Index`` has no start, so we use a helper which
                # follows the Python implementation of ``str.find``. See
                # ``FindStr`` in the generated common package.
                start = self._as_int64_position(node.args[1], args[1])
                return (
                    Stripped(f"aascommon.FindStr({instance}, {args[0]}, {start})"),
                    None,
                )

            return None, Error(
                node.original_node,
                f"The handling of the built-in method {member_type.method.name!r} "
                f"has not been implemented",
            )

        if not isinstance(node.member.instance, (parse_tree.Name, parse_tree.Member)):
            instance = Stripped(f"({instance})")

        method_name = golang_naming.method_name(node.member.name)

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
        errors = []  # type: List[Error]

        args = []  # type: List[Stripped]
        for arg_node in node.args:
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
            function_name, error = self.transform_name(node.name)
            if error is not None:
                return None, error

            assert function_name is not None

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
            if func_type.func.name == "len":
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                if "\n" in args[0]:
                    return (
                        Stripped(
                            f"""\
len(
{I}{indent_but_first_line(args[0], I)},
)"""
                        ),
                        None,
                    )

                return Stripped(f"len({args[0]})"), None

            else:
                return None, Error(
                    node.original_node,
                    f"The handling of the built-in function {node.name!r} has not "
                    f"been implemented",
                )
        else:
            assert_never(func_type)

        raise AssertionError("Should not have gotten here")

    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if isinstance(node.value, bool):
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
        errors = []  # type: List[Error]
        item_exprs = []  # type: List[Stripped]

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
        raise NotImplementedError()

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
        errors = []  # type: List[Error]
        values = []  # type: List[Stripped]

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
        errors = []  # type: List[Error]
        values = []  # type: List[Stripped]

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
        errors = []  # type: List[Error]

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

    def transform_joined_str(
        self, node: parse_tree.JoinedStr
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if all(isinstance(value, str) for value in node.values):
            text = "".join(node.values)  # type: ignore
            return golang_common.string_literal(text), None

        # NOTE (mristin):
        # We need the interpolation if we got so far.

        text_parts = []  # type: List[str]
        args = []  # type: List[str]

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

        args_joined = "\n".join(f"{arg}," for arg in args)

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

    def _transform_any_or_all(
        self, node: Union[parse_tree.Any, parse_tree.All]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]

        iteration = None  # type: Optional[Stripped]
        start = None  # type: Optional[Stripped]
        end = None  # type: Optional[Stripped]

        if isinstance(node.generator, parse_tree.ForEach):
            iteration, error = self.transform(node.generator.iteration)
            if error is not None:
                errors.append(error)

        elif isinstance(node.generator, parse_tree.ForRange):
            start, error = self._transform_and_dereference_if_necessary(
                node.generator.start
            )
            if error is not None:
                errors.append(error)

            end, error = self._transform_and_dereference_if_necessary(
                node.generator.end
            )
            if error is not None:
                errors.append(error)

        else:
            assert_never(node.generator)

        variable_name = node.generator.variable.identifier
        variable_type_annotation = self.type_map[node.generator.variable]

        variable_name_go = golang_naming.variable_name(variable_name)
        variable_type_go, error_msg = generate_type(
            type_annotation=variable_type_annotation, types_package=self._types_package
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

            qualifier_function: str
            if isinstance(node, parse_tree.Any):
                qualifier_function = "Some"
            elif isinstance(node, parse_tree.All):
                qualifier_function = "All"
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
aascommon.{qualifier_function}(
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
aascommon.{qualifier_function}(
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

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]

        value, error = self._transform_and_dereference_if_necessary(node.value)
        if error is not None:
            errors.append(error)

        is_definition = False

        target = None  # type: Optional[Stripped]
        if isinstance(node.target, parse_tree.Name):
            type_anno = self._environment.find(identifier=node.target.identifier)
            if type_anno is None:
                # NOTE (mristin):
                # This is a variable definition as we did not specify the identifier
                # in the environment.

                is_definition = True

                type_anno = self.type_map[node.value]
                self._variable_name_set.add(node.target.identifier)
                self._environment.set(
                    identifier=node.target.identifier, type_annotation=type_anno
                )

                target, error = self.transform_name(node=node.target)
                if error is not None:
                    errors.append(error)
            else:
                target, error = self.transform(node=node.target)
                if error is not None:
                    errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assignment", errors
            )

        assert target is not None
        assert value is not None

        target_is_pointer = self._is_pointer_map[node.target]
        if target_is_pointer:
            target = Stripped(f"*{target}")

        assignment = "=" if not is_definition else ":="

        # NOTE (mristin):
        # This is a rudimentary heuristic for basic line breaks, but works well in
        # practice.
        if "\n" in value or len(value) > 50:
            return (
                Stripped(
                    f"""\
{target} {assignment}
{I}{indent_but_first_line(value, I)})"""
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
        # This is a potential source of error. We infer the types based on nullability
        # checks, so the inferred type might be a non-nullable, but Golang pointers
        # remain pointers even after we check for them.
        #
        # The following transformation can not be resolved unless we know the explicit
        # return type that we are expected — if it is an optional, we should return
        # the value as-is, and if it is a non-optional we have to de-reference it.
        # For now, we leave it as-is, and will revisit this part of the code once
        # the meta-model requires it.

        value, error = self.transform(node.value)
        if error is not None:
            return None, error

        assert value is not None

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
        Transpile the ``statements`` of a switch branch in a new scope.

        Each clause of a Go switch is an implicit block, so the variables defined
        in the ``statements`` are not visible after the branch.

        Return the transpiled statements, and whether they define any variables.
        We leave the layout of the statements to the caller.
        """
        parent_environment = self._environment
        scope_environment = intermediate_type_inference.MutableEnvironment(
            parent=parent_environment
        )
        self._environment = scope_environment

        errors = []  # type: List[Error]
        stmts = []  # type: List[Stripped]
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

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_switch(
        self, node: parse_tree.Switch
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        subject, error = self._transform_and_dereference_if_necessary(node.subject)
        if error is not None:
            return None, error

        assert subject is not None

        errors = []  # type: List[Error]

        # NOTE (mristin):
        # We collect the headers of the clauses together with their statements, and
        # treat the default as the last clause.
        clauses = []  # type: List[Tuple[str, Sequence[parse_tree.StatementUnion]]]

        for case in node.cases:
            labels = []  # type: List[Stripped]
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


# noinspection PyProtectedMember,PyProtectedMember
assert all(op in Transpiler._GOLANG_COMPARISON_MAP for op in parse_tree.Comparator)
