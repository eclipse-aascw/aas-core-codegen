"""Infer and retrieve whether a node in our AST denotes a Golang pointer."""
from typing import Optional, Final, MutableMapping, List, Mapping, Union

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    assert_never,
)
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.parse import tree as parse_tree

_OPTIONAL_PRIMITIVE_INFERRED_TYPE_IS_POINTER = {
    intermediate_type_inference.PrimitiveType.BOOL: True,
    intermediate_type_inference.PrimitiveType.INT: True,
    intermediate_type_inference.PrimitiveType.FLOAT: True,
    intermediate_type_inference.PrimitiveType.STR: True,
    intermediate_type_inference.PrimitiveType.BYTEARRAY: False,
    intermediate_type_inference.PrimitiveType.LENGTH: True,
    intermediate_type_inference.PrimitiveType.NONE: False,
}

assert all(
    a_type in _OPTIONAL_PRIMITIVE_INFERRED_TYPE_IS_POINTER
    for a_type in intermediate_type_inference.PrimitiveType
)

_OPTIONAL_PRIMITIVE_TYPE_IS_POINTER = {
    intermediate.PrimitiveType.BOOL: True,
    intermediate.PrimitiveType.INT: True,
    intermediate.PrimitiveType.FLOAT: True,
    intermediate.PrimitiveType.STR: True,
    intermediate.PrimitiveType.BYTEARRAY: False,
}

assert all(
    a_type in _OPTIONAL_PRIMITIVE_TYPE_IS_POINTER
    for a_type in intermediate.PrimitiveType
)


def is_pointer_type(
    type_annotation: Union[
        intermediate_type_inference.TypeAnnotationUnion,
        intermediate.TypeAnnotationUnion,
    ]
) -> bool:
    """Check whether ``type_annotation`` denotes a pointer type."""
    if isinstance(type_annotation, intermediate_type_inference.TypeAnnotation):
        if not isinstance(
            type_annotation, intermediate_type_inference.OptionalTypeAnnotation
        ):
            return False

        if isinstance(
            type_annotation.value, intermediate_type_inference.PrimitiveTypeAnnotation
        ):
            return _OPTIONAL_PRIMITIVE_INFERRED_TYPE_IS_POINTER[
                type_annotation.value.a_type
            ]

        elif isinstance(
            type_annotation.value, intermediate_type_inference.OurTypeAnnotation
        ):
            if isinstance(type_annotation.value.our_type, intermediate.Enumeration):
                return True

            elif isinstance(
                type_annotation.value.our_type, intermediate.ConstrainedPrimitive
            ):
                return _OPTIONAL_PRIMITIVE_INFERRED_TYPE_IS_POINTER[
                    intermediate_type_inference.PRIMITIVE_TYPE_MAP[
                        type_annotation.value.our_type.constrainee
                    ]
                ]
            else:
                return False

        elif isinstance(
            type_annotation.value, intermediate_type_inference.TupleTypeAnnotation
        ):
            # NOTE (mristin, 2026-09-03):
            # Tuples are represented as Go structs, which are not nilable, so we
            # need a pointer to represent the optional.
            return True

        else:
            return False

    elif isinstance(type_annotation, intermediate.TypeAnnotation):
        # NOTE (mristin, 2023-05-24):
        # This is almost identical as the previous if-branch, but not completely.
        # Note the map ``_OPTIONAL_PRIMITIVE_TYPE_IS_POINTER``.

        if not isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
            return False

        if isinstance(type_annotation.value, intermediate.PrimitiveTypeAnnotation):
            return _OPTIONAL_PRIMITIVE_TYPE_IS_POINTER[type_annotation.value.a_type]

        elif isinstance(type_annotation.value, intermediate.OurTypeAnnotation):
            if isinstance(type_annotation.value.our_type, intermediate.Enumeration):
                return True

            elif isinstance(
                type_annotation.value.our_type, intermediate.ConstrainedPrimitive
            ):
                return _OPTIONAL_PRIMITIVE_TYPE_IS_POINTER[
                    type_annotation.value.our_type.constrainee
                ]
            else:
                return False

        elif isinstance(type_annotation.value, intermediate.TupleTypeAnnotation):
            # NOTE (mristin, 2026-09-03):
            # Tuples are represented as Go structs, which are not nilable, so we
            # need a pointer to represent the optional.
            return True

        else:
            return False

    else:
        assert_never(type_annotation)


class Inferrer(parse_tree.Transformer[Optional[Error]]):
    """
    Infer the types of the given parse tree.

    Since we also handle non-nullness, you need to pre-compute the canonical
    representation of the nodes that you want to infer the types for. To that end,
    use :class:`~CanonicalRepresenter`.
    """

    #: Track of the inferred is-pointer features; ``True`` if the type of the node is
    #: represented as a pointer type in Golang.
    is_pointer_map: Final[MutableMapping[parse_tree.Node, bool]]

    #: Errors encountered during the inference
    errors: Final[List[Error]]

    def __init__(
        self,
        environment: intermediate_type_inference.Environment,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
    ) -> None:
        """Initialize with the given values."""
        # We need to create our own child environment so that we can introduce new
        # entries without affecting the variables from the outer scopes.
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )

        self._type_map = type_map

        self.is_pointer_map = dict()
        self.errors = []

    def transform_member(self, node: parse_tree.Member) -> Optional[Error]:
        error = self.transform(node.instance)
        if error is not None:
            return error

        instance_type_anno = intermediate_type_inference.beneath_optional(
            self._type_map[node.instance]
        )

        if isinstance(
            instance_type_anno,
            intermediate_type_inference.EnumerationAsTypeTypeAnnotation,
        ):
            self.is_pointer_map[node] = False
            return None

        if not (
            isinstance(
                instance_type_anno, intermediate_type_inference.OurTypeAnnotation
            )
        ):
            error = Error(
                node.instance.original_node,
                f"Unexpected {instance_type_anno}; expected the instance of "
                f"a member access to be annotated with our type",
            )
            self.errors.append(error)
            return error

        our_type = instance_type_anno.our_type

        if not isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            error = Error(
                node.instance.original_node,
                f"Unexpected {instance_type_anno.our_type}; expected the instance of "
                f"a member access to be annotated as an abstract or a concrete class",
            )
            self.errors.append(error)
            return error

        prop = our_type.properties_by_name.get(node.name, None)
        if prop is not None:
            self.is_pointer_map[node] = is_pointer_type(prop.type_annotation)
            return None

        method = our_type.methods_by_name.get(node.name, None)
        if method is not None:
            self.is_pointer_map[node] = False
            return None

        error = Error(
            node.original_node,
            f"The member {node.name} not found in the class {our_type.name!r}",
        )
        self.errors.append(error)
        return error

    def transform_index(self, node: parse_tree.Index) -> Optional[Error]:
        error = self.transform(node.collection)
        if error is not None:
            return error

        error = self.transform(node.index)
        if error is not None:
            return error

        collection_type_anno = intermediate_type_inference.beneath_optional(
            self._type_map[node.collection]
        )

        if isinstance(
            collection_type_anno, intermediate_type_inference.TupleTypeAnnotation
        ):
            # NOTE (mristin, 2026-09-03):
            # The index into a tuple must be a literal integer, which has already
            # been verified in
            # :py:class:`aas_core_codegen.intermediate.type_inference.Inferrer`.
            assert isinstance(node.index, parse_tree.Constant) and isinstance(
                node.index.value, int
            )

            index_value = node.index.value
            if index_value < 0:
                index_value += len(collection_type_anno.items)

            item_type_anno = intermediate_type_inference.beneath_optional(
                collection_type_anno.items[index_value]
            )

            self.is_pointer_map[node] = is_pointer_type(item_type_anno)
            return None

        if not isinstance(
            collection_type_anno, intermediate_type_inference.ListTypeAnnotation
        ):
            error = Error(
                node.collection.original_node,
                f"Expected the collection to be a list in the index, "
                f"but got: {collection_type_anno}",
            )
            self.errors.append(error)
            return error

        items_type_anno = intermediate_type_inference.beneath_optional(
            collection_type_anno.items
        )

        self.is_pointer_map[node] = is_pointer_type(items_type_anno)
        return None

    def transform_comparison(self, node: parse_tree.Comparison) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for operand in (node.left, node.right):
            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(operand)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_pointer_map[node] = False
        return None

    def transform_is_in(self, node: parse_tree.IsIn) -> Optional[Error]:
        error = self.transform(node.member)
        if error is not None:
            return error

        error = self.transform(node.container)
        if error is not None:
            return error

        self.is_pointer_map[node] = False
        return None

    def transform_implication(self, node: parse_tree.Implication) -> Optional[Error]:
        error = self.transform(node.antecedent)
        if error is not None:
            return error

        error = self.transform(node.consequent)
        if error is not None:
            return error

        self.is_pointer_map[node] = False
        return None

    def transform_method_call(self, node: parse_tree.MethodCall) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for arg in node.args:
            error = self.transform(arg)

            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.
            if error is not None:
                last_error = error

        error = self.transform(node.member)
        if error is not None:
            last_error = error

        if last_error is not None:
            return last_error

        instance_type_anno = intermediate_type_inference.beneath_optional(
            self._type_map[node.member.instance]
        )

        if not (
            isinstance(
                instance_type_anno, intermediate_type_inference.OurTypeAnnotation
            )
        ):
            error = Error(
                node.member.instance.original_node,
                f"Unexpected {instance_type_anno}; expected the instance of "
                f"a member access to be annotated with our type",
            )
            self.errors.append(error)
            return error

        our_type = instance_type_anno.our_type

        if not isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            error = Error(
                node.member.instance.original_node,
                f"Unexpected {instance_type_anno.our_type}; expected the instance of "
                f"a member access to be annotated as an abstract or a concrete class",
            )
            self.errors.append(error)
            return error

        method = our_type.methods_by_name[node.member.name]
        if method.returns is None:
            self.is_pointer_map[node] = False
        else:
            self.is_pointer_map[node] = is_pointer_type(method.returns)

        return None

    def transform_function_call(self, node: parse_tree.FunctionCall) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for arg in node.args:
            error = self.transform(arg)

            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.
            if error is not None:
                last_error = error

        error = self.transform(node.name)
        if error is not None:
            last_error = error

        if last_error is not None:
            return last_error

        func_type = self._type_map[node.name]

        if not isinstance(
            func_type,
            (
                intermediate_type_inference.VerificationTypeAnnotation,
                intermediate_type_inference.BuiltinFunctionTypeAnnotation,
            ),
        ):
            error = Error(
                node.name.original_node,
                f"Expected the function to be either "
                f"{intermediate_type_inference.VerificationTypeAnnotation.__name__} or "
                f"{intermediate_type_inference.BuiltinFunctionTypeAnnotation}, "
                f"but got {func_type}",
            )
            self.errors.append(error)
            return error

        if func_type.func.returns is None:
            self.is_pointer_map[node] = False
        else:
            self.is_pointer_map[node] = is_pointer_type(func_type.func.returns)

        return None

    def transform_constant(self, node: parse_tree.Constant) -> Optional[Error]:
        self.is_pointer_map[node] = False
        return None

    def transform_tuple(self, node: parse_tree.Tuple) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for value in node.values:
            error = self.transform(value)

            # NOTE (mristin):
            # Do not immediately return so that other values are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_pointer_map[node] = False
        return None

    def transform_is_none(self, node: parse_tree.IsNone) -> Optional[Error]:
        error = self.transform(node.value)
        if error is not None:
            return error

        self.is_pointer_map[node] = False
        return None

    def transform_is_not_none(self, node: parse_tree.IsNotNone) -> Optional[Error]:
        error = self.transform(node.value)
        if error is not None:
            return error

        self.is_pointer_map[node] = False
        return None

    def transform_not(self, node: parse_tree.Not) -> Optional[Error]:
        error = self.transform(node.operand)
        if error is not None:
            return error

        self.is_pointer_map[node] = False
        return None

    def transform_name(self, node: parse_tree.Name) -> Optional[Error]:
        type_in_env = self._environment.find(node.identifier)
        if type_in_env is None:
            error = Error(
                node.original_node,
                f"We do not know how to infer the type of "
                f"the variable with the identifier {node.identifier!r} from the "
                f"given environment. Mind that we do not consider the module "
                f"scope nor handle all built-in functions due to simplicity! If "
                f"you believe this needs to work, please notify the developers.",
            )
            self.errors.append(error)
            return error

        self.is_pointer_map[node] = is_pointer_type(type_in_env)
        return None

    def transform_and(self, node: parse_tree.And) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for value in node.values:
            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(value)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_pointer_map[node] = False
        return None

    def transform_or(self, node: parse_tree.Or) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for value in node.values:
            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(value)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_pointer_map[node] = False
        return None

    def transform_add(self, node: parse_tree.Add) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for operand in (node.left, node.right):
            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(operand)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_pointer_map[node] = False
        return None

    def transform_sub(self, node: parse_tree.Sub) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for operand in (node.left, node.right):
            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(operand)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_pointer_map[node] = False
        return None

    def transform_formatted_value(
        self, node: parse_tree.FormattedValue
    ) -> Optional[Error]:
        error = self.transform(node.value)
        if error is not None:
            return error

        self.is_pointer_map[node] = False
        return None

    def transform_joined_str(self, node: parse_tree.JoinedStr) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for value in node.values:
            if isinstance(value, str):
                continue

            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.
            error = self.transform(value)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_pointer_map[node] = False
        return None

    def transform_for_each(self, node: parse_tree.ForEach) -> Optional[Error]:
        variable_type_in_env = self._environment.find(node.variable.identifier)
        if variable_type_in_env is not None:
            error = Error(
                node.variable.original_node,
                f"The variable {node.variable.identifier} "
                f"has been already defined before",
            )
            self.errors.append(error)
            return error

        loop_variable_type = self._type_map[node.variable]
        self.is_pointer_map[node.variable] = is_pointer_type(loop_variable_type)

        self.is_pointer_map[node] = False
        return None

    def transform_for_range(self, node: parse_tree.ForRange) -> Optional[Error]:
        # noinspection PyUnusedLocal
        error = None  # type: Optional[Error]

        variable_type_in_env = self._environment.find(node.variable.identifier)
        if variable_type_in_env is not None:
            error = Error(
                node.variable.original_node,
                f"The variable {node.variable.identifier} "
                f"has been already defined before",
            )
            self.errors.append(error)
            return error

        last_error = None  # type: Optional[Error]
        for value in (node.start, node.end):
            error = self.transform(value)

            # NOTE (mristin, 2023-05-24):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        loop_variable_type = self._type_map[node.variable]
        self.is_pointer_map[node.variable] = is_pointer_type(loop_variable_type)

        self.is_pointer_map[node] = False
        return None

    def _transform_any_or_all(
        self, node: Union[parse_tree.Any, parse_tree.All]
    ) -> Optional[Error]:
        error = self.transform(node.generator)
        if error is not None:
            return error

        try:
            loop_variable_type = self._type_map[node.generator.variable]

            self._environment.set(
                identifier=node.generator.variable.identifier,
                type_annotation=loop_variable_type,
            )

            error = self.transform(node.condition)
            if error is not None:
                return error
        finally:
            self._environment.remove(identifier=node.generator.variable.identifier)

        self.is_pointer_map[node] = False
        return None

    def transform_any(self, node: parse_tree.Any) -> Optional[Error]:
        return self._transform_any_or_all(node)

    def transform_all(self, node: parse_tree.All) -> Optional[Error]:
        return self._transform_any_or_all(node)

    def transform_assignment(self, node: parse_tree.Assignment) -> Optional[Error]:
        error = self.transform(node.value)
        if error is not None:
            return error

        error = self.transform(node.target)
        if error is not None:
            return error

        self.is_pointer_map[node] = False
        return None

    def transform_return(self, node: parse_tree.Return) -> Optional[Error]:
        # Just recurse to fill ``type_map`` on ``value`` even though we know the type
        # in advance
        if node.value is not None:
            error = self.transform(node.value)
            if error is not None:
                return error

        self.is_pointer_map[node] = False
        return None
