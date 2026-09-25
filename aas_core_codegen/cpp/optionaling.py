"""Infer and retrieve whether a node in our AST denotes a ``common::optional``."""
from typing import Optional, Final, MutableMapping, List, Mapping, Sequence, Union

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    assert_never,
)
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.parse import tree as parse_tree


def is_optional(
    type_annotation: Union[
        intermediate_type_inference.TypeAnnotationUnion,
        intermediate.TypeAnnotationUnion,
    ]
) -> bool:
    """Check whether ``type_annotation`` denotes a ``std::optional``."""
    if isinstance(type_annotation, intermediate_type_inference.TypeAnnotation):
        return isinstance(
            type_annotation, intermediate_type_inference.OptionalTypeAnnotation
        )

    elif isinstance(type_annotation, intermediate.TypeAnnotation):
        return isinstance(type_annotation, intermediate.OptionalTypeAnnotation)
    else:
        assert_never(type_annotation)


class Inferrer(parse_tree.Transformer[Optional[Error]]):
    """Infer the optional/non-optionals of the given parse tree."""

    #: Track of the inferred is-optional features; ``True`` if the type of the node is
    #: represented as a ``std::optional`` in C++.
    is_optional_map: Final[MutableMapping[parse_tree.Node, bool]]

    #: Track of the is-optional features of the nodes narrowed by ``isinstance``
    #: *before* their down-cast; ``True`` if the value of the node is represented
    #: as a ``std::optional`` in C++ before it is down-cast.
    #:
    #: The down-cast values are never ``std::optional``, so all the down-cast
    #: nodes are marked as non-optional in :py:attr:`is_optional_map`.
    is_optional_before_downcast_map: Final[MutableMapping[parse_tree.Node, bool]]

    #: Errors encountered during the inference
    errors: Final[List[Error]]

    def __init__(
        self,
        environment: intermediate_type_inference.Environment,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
    ) -> None:
        """Initialize with the given values."""
        # We need to create our own child environment so that we can introduce new
        # entries without affecting the variables from the outer scopes.
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )

        self._type_map = type_map
        self._downcast_map = downcast_map

        self.is_optional_map = dict()
        self.is_optional_before_downcast_map = dict()
        self.errors = []

    def transform(self, node: parse_tree.Node) -> Optional[Error]:
        result = node.transform(self)
        assert node in self.is_optional_map, (
            f"The node has not been properly added to the is_optional_map: {node}, "
            f"dumped {parse_tree.dump(node)}"
        )

        if node in self._downcast_map:
            # NOTE (mristin):
            # The transpiler de-references the value, if necessary, before it
            # down-casts it. Hence, the down-cast value is never optional.
            self.is_optional_before_downcast_map[node] = self.is_optional_map[node]
            self.is_optional_map[node] = False

        return result

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
            self.is_optional_map[node] = False
            return None

        if isinstance(
            self._type_map[node],
            intermediate_type_inference.BuiltinMethodTypeAnnotation,
        ):
            self.is_optional_map[node] = False
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
            self.is_optional_map[node] = is_optional(prop.type_annotation)
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
            # NOTE (mristin):
            # Tuple items are restricted to atomic types (primitives, constrained
            # primitives, classes and enumerations) by
            # intermediate._translate._verify_only_simple_type_patterns, so none of
            # them can ever be optional.
            self.is_optional_map[node] = False
            return None

        if isinstance(
            collection_type_anno,
            (
                intermediate_type_inference.JsonArrayTypeAnnotation,
                intermediate_type_inference.JsonObjectTypeAnnotation,
            ),
        ):
            # NOTE (mristin):
            # An item of a JSON-able array, and a value of a JSON-able object,
            # is itself a JSON-able value. A JSON-able value is never optional
            # -- JSON knows a ``null``, but a ``JSONValue`` deliberately does
            # not.
            self.is_optional_map[node] = False
            return None

        if not isinstance(
            collection_type_anno, intermediate_type_inference.ListTypeAnnotation
        ):
            error = Error(
                node.collection.original_node,
                f"Expected the collection to be a list or a tuple in the index, "
                f"but got: {collection_type_anno}",
            )
            self.errors.append(error)
            return error

        self.is_optional_map[node] = is_optional(collection_type_anno.items)
        return None

    def transform_slice(self, node: parse_tree.Slice) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for child in (node.collection, node.start, node.end):
            if child is None:
                continue

            # NOTE (mristin):
            # Do not immediately return so that other children are processed as
            # well. This way we get a longer list of errors which the caller can
            # report using :py:prop:`errors`.
            error = self.transform(child)
            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        self.is_optional_map[node] = False
        return None

    def transform_comparison(self, node: parse_tree.Comparison) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for operand in (node.left, node.right):
            # NOTE (mristin):
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

    def transform_is_instance(self, node: parse_tree.IsInstance) -> Optional[Error]:
        # NOTE (mristin):
        # We do not recurse into the classes as they are not values, but only
        # refer to our types.
        error = self.transform(node.value)
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

            # NOTE (mristin):
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

        if isinstance(
            self._type_map[node.member],
            intermediate_type_inference.BuiltinMethodTypeAnnotation,
        ):
            # NOTE (mristin):
            # The built-in methods on strings never return an optional.
            self.is_optional_map[node] = False
            return None

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
            self.is_optional_map[node] = is_optional(method.returns)

        return None

    def transform_function_call(self, node: parse_tree.FunctionCall) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for arg in node.args:
            error = self.transform(arg)

            # NOTE (mristin):
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
            self.is_optional_map[node] = is_optional(func_type.func.returns)

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
                f"We do not know how to infer the is-optional of "
                f"the variable with the identifier {node.identifier!r} from the "
                f"given environment. Mind that we do not consider the module "
                f"scope nor handle all built-in functions due to simplicity! If "
                f"you believe this needs to work, please notify the developers.",
            )
            self.errors.append(error)
            return error

        self.is_optional_map[node] = is_optional(type_in_env)
        return None

    def transform_and(self, node: parse_tree.And) -> Optional[Error]:
        last_error = None  # type: Optional[Error]
        for value in node.values:
            # NOTE (mristin):
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
            # NOTE (mristin):
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
            # NOTE (mristin):
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
            # NOTE (mristin):
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

            # NOTE (mristin):
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
        variable_type_in_env = self._environment.find(node.variable.identifier)

        error: Optional[Error]

        if variable_type_in_env is not None:
            error = Error(
                node.variable.original_node,
                f"The loop variable {node.variable.identifier!r} "
                f"in a for-each has been already defined before",
            )
            self.errors.append(error)
            return error

        loop_variable_type = self._type_map[node.variable]
        self.is_optional_map[node.variable] = is_optional(loop_variable_type)

        error = self.transform(node.iteration)
        if error is not None:
            return error

        self.is_optional_map[node] = False
        return None

    def transform_for_range(self, node: parse_tree.ForRange) -> Optional[Error]:
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

        last_error = None  # type: Optional[Error]
        for value in (node.start, node.end):
            error = self.transform(value)

            # NOTE (mristin):
            # Do not immediately return so that other arguments are processed as well.
            # This way we get a longer list of errors which the caller can report
            # using :py:prop:`errors`.

            if error is not None:
                last_error = error

        if last_error is not None:
            return last_error

        loop_variable_type = self._type_map[node.variable]
        self.is_optional_map[node.variable] = is_optional(loop_variable_type)

        self.is_optional_map[node] = False
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

        if (
            isinstance(node.target, parse_tree.Name)
            and self._environment.find(node.target.identifier) is None
        ):
            # NOTE (mristin):
            # This is a variable definition, so we introduce the variable in
            # the current scope.
            self._environment.set(
                identifier=node.target.identifier,
                type_annotation=self._type_map[node.value],
            )

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

    def _transform_in_new_scope(
        self, statements: Sequence[parse_tree.StatementUnion]
    ) -> Optional[Error]:
        """
        Transform the ``statements`` of a switch branch in a new block scope.

        A scope is the region of the code where a variable is visible. We look up
        the variables in the scopes, *i.e.*, in :attr:`_environment`, to infer
        the is-optional of the names.

        Python has only function-level scopes, while the switch branches of
        the generated code are blocks, each with its own scope. We mirror this here:

        * The ``statements`` see the variables of the enclosing scopes, *e.g.*,
          the function arguments and the variables defined before the switch.
        * A variable newly defined in the ``statements`` is introduced in a fresh
          child environment. We discard the child environment once the branch has
          been transformed, so the variable is not visible after the branch.
          Consequently, the sibling branches can define the variables of the same
          name independently of each other.

        The type inference already refused the references to a variable outside
        of the branch where it has been defined, so here we only need to keep
        the environments in line with the generated code.
        """
        parent_environment = self._environment
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=parent_environment
        )

        try:
            for stmt in statements:
                error = self.transform(stmt)
                if error is not None:
                    return error
        finally:
            self._environment = parent_environment

        return None

    def transform_switch(self, node: parse_tree.Switch) -> Optional[Error]:
        error = self.transform(node.subject)
        if error is not None:
            return error

        for case in node.cases:
            for label in case.labels:
                error = self.transform(label)
                if error is not None:
                    return error

            error = self._transform_in_new_scope(case.body)
            if error is not None:
                return error

        if node.default is not None:
            error = self._transform_in_new_scope(node.default)
            if error is not None:
                return error

        self.is_optional_map[node] = False
        return None
