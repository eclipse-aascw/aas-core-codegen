"""This module provides an inferrer to resolve optional type information."""

from typing import Final, List, MutableMapping, Optional, Union, Mapping

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    assert_never,
    Error,
)
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.parse import tree as parse_tree


def is_optional_type(
    type_annotation: Union[
        intermediate_type_inference.TypeAnnotationUnion,
        intermediate.TypeAnnotationUnion,
    ]
) -> bool:
    """Check whether ``type_annotation`` denotes an optional type."""
    if isinstance(type_annotation, intermediate_type_inference.TypeAnnotation):
        return isinstance(
            type_annotation, intermediate_type_inference.OptionalTypeAnnotation
        )
    elif isinstance(type_annotation, intermediate.TypeAnnotation):
        return isinstance(type_annotation, intermediate.OptionalTypeAnnotation)
    else:
        assert_never(type_annotation)


class OptionalInferrer(parse_tree.Transformer[Optional[Error]]):
    """
    Infer optional types of the given parse tree.
    """

    def __init__(
        self,
        environment: intermediate_type_inference.Environment,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
    ) -> None:
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )

        self._type_map = type_map

        self.is_optional_map = {}  # type: Final[MutableMapping[parse_tree.Node, bool]]

        self.errors = []  # type: Final[List[Error]]

    def transform_member(self, node: parse_tree.Member) -> Optional[Error]:
        error = self.transform(node.instance)
        if error is not None:
            return error

        instance_type_anno = intermediate_type_inference.beneath_optional(
            self._type_map[node.instance]
        )

        if isinstance(
            instance_type_anno, intermediate_type_inference.OurTypeAnnotation
        ):
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
                self.is_optional_map[node] = is_optional_type(prop.type_annotation)
                return None

            method = our_type.methods_by_name.get(node.name, None)
            if method is not None:
                self.is_optional_map[node] = False
                return None

            error = Error(
                node.original_node,
                f"The member {node.name} not found in the class {our_type.name!r}",
            )
            self.errors.append(error)
            return error
        else:
            self.is_optional_map[node] = False

        return None

    def transform_index(self, node: parse_tree.Index) -> Optional[Error]:
        error = self.transform(node.collection)
        if error is not None:
            return error

        error = self.transform(node.index)
        if error is not None:
            return error

        self.is_optional_map[node] = False
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

        self.is_optional_map[node] = False
        return None

    def transform_is_in(self, node: parse_tree.IsIn) -> Optional[Error]:
        error = self.transform(node.member)
        if error is not None:
            return error

        error = self.transform(node.container)
        if error is not None:
            return error

        self.is_optional_map[node] = False
        return None

    def transform_implication(self, node: parse_tree.Implication) -> Optional[Error]:
        error = self.transform(node.antecedent)
        if error is not None:
            return error

        error = self.transform(node.consequent)
        if error is not None:
            return error

        self.is_optional_map[node] = False
        return None

    def transform_method_call(self, node: parse_tree.MethodCall) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for arg in node.args:
            error = self.transform(arg)

            # NOTE (empwilli):
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
            self.is_optional_map[node] = False
        else:
            self.is_optional_map[node] = is_optional_type(method.returns)

        return None

    def transform_function_call(self, node: parse_tree.FunctionCall) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for arg in node.args:
            error = self.transform(arg)

            # NOTE (empwilli):
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
            self.is_optional_map[node] = False
        else:
            self.is_optional_map[node] = is_optional_type(func_type.func.returns)

        return None

    def transform_constant(self, node: parse_tree.Constant) -> Optional[Error]:
        self.is_optional_map[node] = False
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

        self.is_optional_map[node] = False
        return None

    def transform_is_none(self, node: parse_tree.IsNone) -> Optional[Error]:
        error = self.transform(node.value)

        if error is not None:
            return error

        self.is_optional_map[node] = False
        return None

    def transform_is_not_none(self, node: parse_tree.IsNotNone) -> Optional[Error]:
        error = self.transform(node.value)

        if error is not None:
            return error

        self.is_optional_map[node] = False
        return None

    def transform_not(self, node: parse_tree.Not) -> Optional[Error]:
        error = self.transform(node.operand)
        if error is not None:
            return error

        self.is_optional_map[node] = False
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

        self.is_optional_map[node] = is_optional_type(type_in_env)

        return None

    def transform_and(self, node: parse_tree.And) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for value in node.values:
            # NOTE (empwilli):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(value)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_optional_map[node] = False
        return None

    def transform_or(self, node: parse_tree.Or) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for value in node.values:
            # NOTE (empwilli):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(value)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_optional_map[node] = False
        return None

    def transform_add(self, node: parse_tree.Add) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for operand in (node.left, node.right):
            # NOTE (empwilli):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(operand)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_optional_map[node] = False
        return None

    def transform_sub(self, node: parse_tree.Sub) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for operand in (node.left, node.right):
            # NOTE (empwilli):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(operand)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_optional_map[node] = False
        return None

    def transform_formatted_value(
        self, node: parse_tree.FormattedValue
    ) -> Optional[Error]:
        error = self.transform(node.value)
        if error is not None:
            return error

        self.is_optional_map[node] = False
        return None

    def transform_joined_str(self, node: parse_tree.JoinedStr) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for value in node.values:
            if isinstance(value, str):
                continue
            # NOTE (empwilli):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            error = self.transform(value)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_optional_map[node] = False
        return None

    def transform_for_each(self, node: parse_tree.ForEach) -> Optional[Error]:
        error: Optional[Error]

        variable_type_in_env = self._environment.find(node.variable.identifier)
        if variable_type_in_env is not None:
            error = Error(
                node.variable.original_node,
                f"The variable {node.variable.identifier} "
                f"has been already defined before",
            )
            self.errors.append(error)
            return error

        error = self.transform(node.iteration)
        if error is not None:
            return error

        self.is_optional_map[node.variable] = False

        self.is_optional_map[node] = False
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

            # NOTE (empwilli):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_optional_map[node.variable] = False

        self.is_optional_map[node] = False
        return None

    def _transform_any_or_all(
        self, node: Union[parse_tree.Any, parse_tree.All]
    ) -> Optional[Error]:
        error = self.transform(node.generator)
        if error is not None:
            return error

        loop_variable_type = self._type_map[node.generator.variable]
        try:
            self._environment.set(
                identifier=node.generator.variable.identifier,
                type_annotation=loop_variable_type,
            )

            error = self.transform(node.condition)
            if error is not None:
                return error
        finally:
            self._environment.remove(identifier=node.generator.variable.identifier)

        self.is_optional_map[node] = False
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

        self.is_optional_map[node] = False
        return None

    def transform_return(self, node: parse_tree.Return) -> Optional[Error]:
        # Just recurse to fill ``type_map`` on ``value`` even though we know the type
        # in advance
        if node.value is not None:
            error = self.transform(node.value)
            if error is not None:
                return error

        self.is_optional_map[node] = False

        return None
