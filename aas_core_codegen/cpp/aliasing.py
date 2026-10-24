"""
Decide how to declare the variables in C++ so that they alias as in Python.

Python shares the lists and the objects by reference, while C++ copies
the ``std::vector``'s by value. We declare the local variables and the loop variables
as references wherever a copy would diverge from Python, and copy them wherever
a reference would diverge. If neither is faithful, we report an error instead of
silently miscompiling the meta-model.
"""

import collections
import enum
from typing import (
    AbstractSet,
    Final,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Error, Identifier, assert_never
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.parse import tree as parse_tree


class _Category(enum.Enum):
    """Categorize the values by how C++ copies them."""

    #: Arithmetic values and enumeration literals, cheap to copy
    CHEAP = 0

    #: Strings, byte arrays and instances, which are always faithfully copied,
    #: as the strings and the byte arrays are immutable in the meta-model, and
    #: the instances are shared pointers
    VALUE = 1

    #: Lists, sets, tuples and JSON-able values, which C++ copies deeply
    CONTAINER = 2


def _categorize(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
) -> _Category:
    """Categorize the value of ``type_annotation`` by how C++ copies it."""
    type_anno = intermediate_type_inference.beneath_optional(type_annotation)

    if isinstance(
        type_anno,
        (
            intermediate_type_inference.ListTypeAnnotation,
            intermediate_type_inference.SetTypeAnnotation,
            intermediate_type_inference.TupleTypeAnnotation,
            intermediate_type_inference.JsonValueTypeAnnotation,
            intermediate_type_inference.JsonArrayTypeAnnotation,
            intermediate_type_inference.JsonObjectTypeAnnotation,
        ),
    ):
        return _Category.CONTAINER

    primitive_type = intermediate_type_inference.try_primitive_type(type_anno)
    if primitive_type is not None:
        if primitive_type in (
            intermediate_type_inference.PrimitiveType.STR,
            intermediate_type_inference.PrimitiveType.BYTEARRAY,
        ):
            return _Category.VALUE

        return _Category.CHEAP

    if isinstance(
        type_anno, intermediate_type_inference.OurTypeAnnotation
    ) and isinstance(type_anno.our_type, intermediate.Enumeration):
        return _Category.CHEAP

    return _Category.VALUE


def _is_primitive_or_enumeration(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
) -> bool:
    """Check that ``type_annotation`` denotes a primitive value or an enumeration."""
    type_anno = intermediate_type_inference.beneath_optional(type_annotation)

    return intermediate_type_inference.try_primitive_type(type_anno) is not None or (
        isinstance(type_anno, intermediate_type_inference.OurTypeAnnotation)
        and isinstance(type_anno.our_type, intermediate.Enumeration)
    )


class Declaration(enum.Enum):
    """Specify how to declare a local or a loop variable in C++."""

    #: Declare as before, *i.e.*, spell out the primitive types, and use ``auto``
    #: for the rest; a loop variable is a copy if cheap, and a constant reference
    #: otherwise.
    DEFAULT = 0

    #: Copy the value with ``auto``, or the spelled-out type for a loop variable
    COPY = 1

    #: Declare a constant reference, ``const auto&`` or ``const T&``
    CONST_REF = 2

    #: Declare a mutable reference to a mutable path, ``auto&`` or ``T&``
    MUT_REF = 3


class _BindingKind(enum.Enum):
    ARGUMENT = 0
    LOCAL = 1
    LOOP = 2


class _Binding:
    """Represent a single definition of a variable."""

    identifier: Final[Identifier]
    kind: Final[_BindingKind]

    #: The assignment defining a local variable, or the generator defining a loop
    #: variable; None for an argument
    definition: Final[Optional[parse_tree.Node]]

    def __init__(
        self,
        identifier: Identifier,
        kind: _BindingKind,
        definition: Optional[parse_tree.Node],
    ) -> None:
        self.identifier = identifier
        self.kind = kind
        self.definition = definition


_Path = Tuple[_Binding, Sequence[Union[parse_tree.Member, parse_tree.Index]]]


def _is_access_path(node: parse_tree.Node) -> bool:
    """Check that ``node`` is a chain of member and index accesses on a name."""
    while isinstance(node, (parse_tree.Member, parse_tree.Index)):
        node = node.instance if isinstance(node, parse_tree.Member) else node.collection

    return isinstance(node, parse_tree.Name)


class _Collector(parse_tree.Visitor):
    """Resolve the names to their bindings, and collect the facts of a function."""

    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        arguments: Sequence[intermediate.Argument],
        binds_self: bool,
    ) -> None:
        """
        Initialize with the given values.

        If ``binds_self`` is set, ``self`` is bound as an argument, as in a method.
        """
        self.type_map = type_map

        self.binding_by_name: MutableMapping[parse_tree.Name, _Binding] = dict()

        self.binding_by_definition: MutableMapping[parse_tree.Node, _Binding] = dict()

        self.reassigned: Set[_Binding] = set()

        #: Expressions whose values are mutated in place: the collections of
        #: the index targets, the sets which we add to, and the lists and the sets
        #: passed to the mutable arguments
        self.mutated: List[parse_tree.Expression] = []

        #: Names of the properties replaced by a setter
        self.set_property_names: Set[Identifier] = set()

        #: Set if an index target replaces an item which is not a primitive value
        self.replaces_non_primitive_item = False

        #: Set if the function passes a mutable argument holding non-primitive
        #: values, including the instances of the non-``@non_mutating`` method calls
        self.passes_mutable_non_primitive = False

        #: Set if the function mutates a list or a set in place
        self.mutates_in_place = False

        #: Nodes whose values are copied in C++ from an access path, while Python
        #: shares them
        self.copies: List[Tuple[parse_tree.Node, str]] = []

        #: Local sets which we move into a returned tuple literal
        self.moved: Set[parse_tree.Node] = set()

        #: Generators of the ``any`` and ``all`` expressions, whose loop variables
        #: are parameters of lambdas in C++
        self.lambda_generators: Set[
            Union[parse_tree.ForEach, parse_tree.ForRange]
        ] = set()

        self.errors: List[Error] = []

        argument_names = [arg.name for arg in arguments]
        if binds_self:
            argument_names.append(Identifier("self"))

        self._scopes: List[MutableMapping[Identifier, _Binding]] = [
            {
                name: _Binding(
                    identifier=name, kind=_BindingKind.ARGUMENT, definition=None
                )
                for name in argument_names
            }
        ]

    def _find(self, identifier: Identifier) -> Optional[_Binding]:
        for scope in reversed(self._scopes):
            binding = scope.get(identifier, None)
            if binding is not None:
                return binding

        return None

    def _visit_in_new_scope(
        self,
        statements: Sequence[parse_tree.StatementUnion],
        loop_binding: Optional[_Binding] = None,
    ) -> None:
        self._scopes.append(
            dict() if loop_binding is None else {loop_binding.identifier: loop_binding}
        )
        try:
            for stmt in statements:
                self.visit(stmt)
        finally:
            self._scopes.pop()

    def visit_name(self, node: parse_tree.Name) -> None:
        binding = self._find(node.identifier)
        if binding is not None:
            self.binding_by_name[node] = binding

    def visit_assignment(self, node: parse_tree.Assignment) -> None:
        self.visit(node.value)

        value_is_container_path = _categorize(
            self.type_map[node.value]
        ) is _Category.CONTAINER and _is_access_path(node.value)

        if isinstance(node.target, parse_tree.Name):
            binding = self._find(node.target.identifier)
            if binding is None:
                binding = _Binding(
                    identifier=node.target.identifier,
                    kind=_BindingKind.LOCAL,
                    definition=node,
                )
                self._scopes[-1][node.target.identifier] = binding
                self.binding_by_definition[node] = binding
            else:
                self.reassigned.add(binding)

                if binding.kind is _BindingKind.ARGUMENT:
                    self.errors.append(
                        Error(
                            node.original_node,
                            f"The argument {node.target.identifier!r} can not be "
                            f"re-assigned in C++, since the list arguments are "
                            f"passed in as references, so that the re-assignment "
                            f"would overwrite the caller's list, while Python "
                            f"re-binds only the local name. Please assign to "
                            f"a new variable.",
                        )
                    )

                if value_is_container_path:
                    self.copies.append(
                        (
                            node,
                            f"re-assigning the variable {node.target.identifier!r}",
                        )
                    )

            self.binding_by_name[node.target] = binding

        elif isinstance(node.target, parse_tree.Member):
            # NOTE (mristin):
            # The type inference requires an explicit copy of every stored list, so
            # the setter copies nothing which Python would share.
            self.visit(node.target)
            self.set_property_names.add(node.target.name)

        elif isinstance(node.target, parse_tree.Index):
            self.visit(node.target)
            self.mutated.append(node.target.collection)
            self.mutates_in_place = True

            if not _is_primitive_or_enumeration(self.type_map[node.value]):
                self.replaces_non_primitive_item = True

        else:
            raise AssertionError(
                f"Unexpected assignment target: {parse_tree.dump(node.target)}; "
                f"this should have been caught in the type inference"
            )

    def _collect_mutable_arguments(
        self,
        arg_nodes: Sequence[parse_tree.Expression],
        arguments: Sequence[intermediate.Argument],
    ) -> None:
        """Collect the facts about the ``arg_nodes`` passed to mutable arguments."""
        for arg_node, argument in zip(arg_nodes, arguments, strict=False):
            if not argument.mutable:
                continue

            self.mutates_in_place = True

            type_anno = intermediate_type_inference.beneath_optional(
                self.type_map[arg_node]
            )

            if isinstance(
                type_anno,
                (
                    intermediate_type_inference.ListTypeAnnotation,
                    intermediate_type_inference.SetTypeAnnotation,
                ),
            ):
                self.mutated.append(arg_node)

                if not _is_primitive_or_enumeration(type_anno.items):
                    self.passes_mutable_non_primitive = True
            else:
                self.passes_mutable_non_primitive = True

    def visit_function_call(self, node: parse_tree.FunctionCall) -> None:
        for arg in node.args:
            self.visit(arg)

        func_type = self.type_map.get(node.name, None)
        if isinstance(
            func_type, intermediate_type_inference.VerificationTypeAnnotation
        ):
            self._collect_mutable_arguments(
                arg_nodes=node.args, arguments=func_type.func.arguments
            )

    def visit_method_call(self, node: parse_tree.MethodCall) -> None:
        self.visit(node.member)
        for arg in node.args:
            self.visit(arg)

        method_type = self.type_map.get(node.member, None)

        if isinstance(
            method_type, intermediate_type_inference.BuiltinMethodTypeAnnotation
        ) and method_type.method.kind in (
            intermediate_type_inference.BuiltinMethodKind.SET_ADD,
            intermediate_type_inference.BuiltinMethodKind.LIST_APPEND,
        ):
            self.mutated.append(node.member.instance)
            self.mutates_in_place = True
            return

        if not isinstance(
            method_type, intermediate_type_inference.MethodTypeAnnotation
        ):
            return

        self._collect_mutable_arguments(
            arg_nodes=node.args, arguments=method_type.method.arguments
        )

        if not method_type.method.non_mutating:
            self.mutates_in_place = True
            self.passes_mutable_non_primitive = True

    def visit_tuple(self, node: parse_tree.Tuple) -> None:
        for value in node.values:
            self.visit(value)

            if _categorize(
                self.type_map[value]
            ) is _Category.CONTAINER and _is_access_path(value):
                self.copies.append((value, "constructing a tuple"))

    def visit_return(self, node: parse_tree.Return) -> None:
        if node.value is None:
            return

        # NOTE (mristin):
        # The function ends with the return, so no in-place mutation can follow
        # which the copies of the lists in a returned tuple literal would miss.
        # The type inference requires the returned lists and sets to be fresh,
        # so the caller can not observe the sharing either.
        if not isinstance(node.value, parse_tree.Tuple):
            self.visit(node.value)
            return

        for value in node.value.values:
            self.visit(value)

        # NOTE (mristin):
        # C++ moves a local variable implicitly only if it is returned on its own,
        # but not as an item of a tuple, so we move the local sets explicitly.
        # They are fresh, and the function ends here. We must not move a variable
        # which occurs more than once in the returned value, as its later
        # occurrences would see the moved-from variable.
        occurrences_by_identifier = collections.Counter(
            name_node.identifier
            for name_node in parse_tree.over_nodes(node.value)
            if isinstance(name_node, parse_tree.Name)
        )

        for value in node.value.values:
            if not isinstance(value, parse_tree.Name):
                continue

            binding = self.binding_by_name.get(value, None)
            if (
                binding is not None
                and binding.kind is _BindingKind.LOCAL
                and isinstance(
                    intermediate_type_inference.beneath_optional(self.type_map[value]),
                    intermediate_type_inference.SetTypeAnnotation,
                )
                and occurrences_by_identifier[value.identifier] == 1
            ):
                self.moved.add(value)

    def _visit_generator_expression(
        self, node: Union[parse_tree.Any, parse_tree.All]
    ) -> None:
        self.visit(node.generator)

        binding = _Binding(
            identifier=node.generator.variable.identifier,
            kind=_BindingKind.LOOP,
            definition=node.generator,
        )
        self.binding_by_definition[node.generator] = binding
        self.lambda_generators.add(node.generator)

        self._scopes.append({binding.identifier: binding})
        try:
            self.visit(node.condition)
        finally:
            self._scopes.pop()

    def visit_any(self, node: parse_tree.Any) -> None:
        self._visit_generator_expression(node)

    def visit_all(self, node: parse_tree.All) -> None:
        self._visit_generator_expression(node)

    def visit_switch(self, node: parse_tree.Switch) -> None:
        self.visit(node.subject)
        for case in node.cases:
            for label in case.labels:
                self.visit(label)

            self._visit_in_new_scope(case.body)

        if node.default is not None:
            self._visit_in_new_scope(node.default)

    def visit_if(self, node: parse_tree.If) -> None:
        for branch in node.branches:
            self.visit(branch.condition)
            self._visit_in_new_scope(branch.body)

        if node.default is not None:
            self._visit_in_new_scope(node.default)

    def visit_for(self, node: parse_tree.For) -> None:
        self.visit(node.generator)

        binding = _Binding(
            identifier=node.generator.variable.identifier,
            kind=_BindingKind.LOOP,
            definition=node.generator,
        )
        self.binding_by_definition[node.generator] = binding

        self._visit_in_new_scope(node.body, loop_binding=binding)


class Aliasing:
    """Specify how to declare the variables of a function or a method in C++."""

    #: Declarations of the local variables by their defining assignments, and of
    #: the loop variables by their generators
    declaration_by_definition: Final[Mapping[parse_tree.Node, Declaration]]

    #: Items of the returned tuple literals which we move instead of copying
    moved_set: Final[AbstractSet[parse_tree.Node]]

    def __init__(
        self,
        declaration_by_definition: Mapping[parse_tree.Node, Declaration],
        moved_set: AbstractSet[parse_tree.Node],
    ) -> None:
        self.declaration_by_definition = declaration_by_definition
        self.moved_set = moved_set


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def analyze(
    body: Sequence[parse_tree.Node],
    arguments: Sequence[intermediate.Argument],
    type_map: Mapping[parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion],
    binds_self: bool,
) -> Tuple[Optional[Aliasing], Optional[List[Error]]]:
    """
    Decide how to declare the variables of a function or a method in C++.

    The ``body`` and the ``arguments`` belong to a verification function or to
    a method. If ``binds_self`` is set, ``self`` is bound as an argument, as in
    a method.
    """
    collector = _Collector(
        type_map=type_map, arguments=arguments, binds_self=binds_self
    )
    for stmt in body:
        collector.visit(stmt)

    errors = list(collector.errors)

    def path_of(node: parse_tree.Node) -> Optional[_Path]:
        segments: List[Union[parse_tree.Member, parse_tree.Index]] = []
        while isinstance(node, (parse_tree.Member, parse_tree.Index)):
            segments.append(node)
            node = (
                node.instance
                if isinstance(node, parse_tree.Member)
                else node.collection
            )

        if not isinstance(node, parse_tree.Name):
            return None

        binding = collector.binding_by_name.get(node, None)
        if binding is None:
            # NOTE (mristin):
            # The name refers to a constant, which is never mutated.
            return None

        segments.reverse()
        return binding, segments

    def reference_is_faithful(path: _Path, through_item: bool) -> bool:
        """
        Check that a reference to ``path`` behaves as in Python.

        If ``through_item`` is set, the reference is to an item of the collection
        at ``path``, as a loop variable.
        """
        binding, segments = path

        if binding in collector.reassigned:
            return False

        if any(
            isinstance(segment, parse_tree.Member)
            and segment.name in collector.set_property_names
            for segment in segments
        ):
            return False

        through_index = through_item or any(
            isinstance(segment, parse_tree.Index) for segment in segments
        )

        if collector.replaces_non_primitive_item and through_index:
            return False

        if collector.passes_mutable_non_primitive and (
            through_item or len(segments) > 0
        ):
            return False

        return True

    copy_is_faithful = not collector.mutates_in_place

    # region Determine the bindings which need to be mutable references

    def mutated_binding(node: parse_tree.Node) -> Optional[_Binding]:
        """Return the binding which needs to be mutable to mutate ``node`` in place."""
        path = path_of(node)
        if path is None:
            return None

        binding, segments = path

        # NOTE (mristin):
        # The mutation of a value reached through an instance goes through
        # the shared pointer, which is mutable even if held as a constant.
        if any(isinstance(segment, parse_tree.Member) for segment in segments):
            return None

        return binding

    mutable_bindings: Set[_Binding] = set()
    worklist = list(collector.mutated)
    while len(worklist) > 0:
        binding = mutated_binding(worklist.pop())
        if binding is None or binding in mutable_bindings:
            continue

        mutable_bindings.add(binding)

        # NOTE (mristin):
        # A mutable reference to a value needs a mutable path to it.
        if binding.kind is _BindingKind.LOCAL:
            assert isinstance(binding.definition, parse_tree.Assignment)
            worklist.append(binding.definition.value)

        elif binding.kind is _BindingKind.LOOP:
            if isinstance(binding.definition, parse_tree.ForEach):
                worklist.append(binding.definition.iteration)

        elif binding.kind is _BindingKind.ARGUMENT:
            pass

        else:
            assert_never(binding.kind)

    # endregion

    declaration_by_definition: MutableMapping[parse_tree.Node, Declaration] = dict()

    for definition, binding in collector.binding_by_definition.items():
        if isinstance(definition, parse_tree.Assignment):
            if _categorize(type_map[definition.target]) is not _Category.CONTAINER:
                declaration_by_definition[definition] = Declaration.DEFAULT
                continue

            # NOTE (mristin):
            # A variable declared with a type different from the type of its value,
            # *e.g.*, ``Optional[List[str]]`` for a ``List[str]``, holds a converted
            # copy of the value in C++, so it can not reference the value.
            is_converted = str(type_map[definition.target]) != str(
                type_map[definition.value]
            )

            path = path_of(definition.value)
            if path is None:
                # NOTE (mristin):
                # The value is fresh, so copying it is faithful.
                declaration_by_definition[definition] = Declaration.COPY
                continue

            is_reference_faithful = (
                not is_converted
                and binding not in collector.reassigned
                and reference_is_faithful(path, through_item=False)
            )

            if binding in mutable_bindings:
                if is_converted:
                    errors.append(
                        Error(
                            definition.original_node,
                            f"The variable {binding.identifier!r} is mutated in "
                            f"place, so we would need to declare it as a reference "
                            f"in C++. However, the variable is declared with "
                            f"the type {type_map[definition.target]}, while its "
                            f"value is of the type {type_map[definition.value]}, "
                            f"so C++ would mutate a converted copy instead of "
                            f"the value. Please declare the variable with the type "
                            f"of its value.",
                        )
                    )
                    continue

                if not is_reference_faithful:
                    errors.append(
                        Error(
                            definition.original_node,
                            f"The variable {binding.identifier!r} is mutated in "
                            f"place, so we would need to declare it as a reference "
                            f"in C++. However, the reference would not behave as "
                            f"in Python, since the variable, or the variable its "
                            f"value comes from, is re-assigned, or the value is "
                            f"replaced in its container in this function.",
                        )
                    )
                    continue

                declaration_by_definition[definition] = Declaration.MUT_REF

            elif is_reference_faithful:
                declaration_by_definition[definition] = Declaration.CONST_REF

            elif copy_is_faithful:
                declaration_by_definition[definition] = Declaration.COPY

            else:
                errors.append(
                    Error(
                        definition.original_node,
                        f"We can neither reference nor copy the value of "
                        f"the variable {binding.identifier!r} in C++. A reference "
                        f"would not behave as in Python, since the variable, "
                        f"or the variable its value comes from, is re-assigned, or "
                        f"the value is replaced in its container in this function. "
                        f"A copy would miss the in-place mutations of the list, "
                        f"which Python shares instead of copying.",
                    )
                )

        elif isinstance(definition, (parse_tree.ForEach, parse_tree.ForRange)):
            if isinstance(definition, parse_tree.ForRange):
                declaration_by_definition[definition] = Declaration.DEFAULT
                continue

            iteration_path = path_of(definition.iteration)

            if iteration_path is not None and not reference_is_faithful(
                iteration_path, through_item=False
            ):
                errors.append(
                    Error(
                        definition.iteration.original_node,
                        "We can not iterate over the collection in C++, since "
                        "the collection, or the variable it comes from, is "
                        "re-assigned, or the collection is replaced in its "
                        "container in this function, while C++ iterates over "
                        "the collection by reference.",
                    )
                )
                continue

            category = _categorize(type_map[definition.variable])

            is_reference_faithful = iteration_path is None or reference_is_faithful(
                iteration_path, through_item=True
            )

            if category is _Category.CHEAP:
                declaration_by_definition[definition] = Declaration.DEFAULT

            elif category is _Category.VALUE:
                declaration_by_definition[definition] = (
                    Declaration.CONST_REF if is_reference_faithful else Declaration.COPY
                )

            elif category is _Category.CONTAINER:
                if binding in mutable_bindings:
                    if definition in collector.lambda_generators:
                        errors.append(
                            Error(
                                definition.variable.original_node,
                                f"The loop variable {binding.identifier!r} of "
                                f"the generator expression is mutated in place, "
                                f"which is not supported yet in C++, as we would "
                                f"need to pass it as a mutable reference to "
                                f"a lambda.",
                            )
                        )
                        continue

                    if not is_reference_faithful:
                        errors.append(
                            Error(
                                definition.variable.original_node,
                                f"The loop variable {binding.identifier!r} is "
                                f"mutated in place, so we would need to declare it "
                                f"as a reference in C++. However, the reference "
                                f"would not behave as in Python, since the items are "
                                f"replaced in their container in this function.",
                            )
                        )
                        continue

                    declaration_by_definition[definition] = Declaration.MUT_REF

                elif is_reference_faithful:
                    declaration_by_definition[definition] = Declaration.CONST_REF

                elif copy_is_faithful:
                    declaration_by_definition[definition] = Declaration.COPY

                else:
                    errors.append(
                        Error(
                            definition.variable.original_node,
                            f"We can neither reference nor copy the loop variable "
                            f"{binding.identifier!r} in C++. A reference would not "
                            f"behave as in Python, since the items are replaced in "
                            f"their container in this function. A copy would miss "
                            f"the in-place mutations of the list, which Python "
                            f"shares instead of copying.",
                        )
                    )

            else:
                assert_never(category)

        else:
            raise AssertionError(f"Unexpected definition: {definition}")

    for node, what in collector.copies:
        if not copy_is_faithful:
            errors.append(
                Error(
                    node.original_node,
                    f"C++ copies the list when {what}, while Python shares it. "
                    f"The copy would miss the in-place mutations of the list in "
                    f"this function, so we can not transpile it faithfully.",
                )
            )

    if len(errors) > 0:
        return None, errors

    return (
        Aliasing(
            declaration_by_definition=declaration_by_definition,
            moved_set=collector.moved,
        ),
        None,
    )
