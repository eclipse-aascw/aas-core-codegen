"""Transpile meta-model Python code to TypeScript code."""
import abc
import ast
import io
import textwrap
from typing import (
    Final,
    AbstractSet,
    Tuple,
    Optional,
    List,
    Mapping,
    MutableMapping,
    Sequence,
    Union,
    Set,
)

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Stripped,
    assert_never,
    indent_but_first_line,
    Identifier,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.parse import tree as parse_tree
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)


def _collect_reassigned_definitions_in_scope(
    statements: Sequence[parse_tree.Node],
    visible: Mapping[Identifier, parse_tree.Assignment],
    result: Set[parse_tree.Assignment],
) -> None:
    """
    Collect recursively the re-assigned definitions of the variables into ``result``.

    The ``visible`` maps the variables of the enclosing scopes to their definitions.
    """
    definitions: MutableMapping[Identifier, parse_tree.Assignment] = dict(visible)

    for stmt in statements:
        if isinstance(stmt, parse_tree.Assignment) and isinstance(
            stmt.target, parse_tree.Name
        ):
            definition = definitions.get(stmt.target.identifier)
            if definition is None:
                definitions[stmt.target.identifier] = stmt
            else:
                result.add(definition)

        elif isinstance(stmt, parse_tree.Switch):
            for case in stmt.cases:
                _collect_reassigned_definitions_in_scope(
                    statements=case.body, visible=definitions, result=result
                )

            if stmt.default is not None:
                _collect_reassigned_definitions_in_scope(
                    statements=stmt.default, visible=definitions, result=result
                )

        elif isinstance(stmt, parse_tree.For):
            _collect_reassigned_definitions_in_scope(
                statements=stmt.body, visible=definitions, result=result
            )

        elif isinstance(stmt, parse_tree.If):
            for branch in stmt.branches:
                _collect_reassigned_definitions_in_scope(
                    statements=branch.body, visible=definitions, result=result
                )

            if stmt.default is not None:
                _collect_reassigned_definitions_in_scope(
                    statements=stmt.default, visible=definitions, result=result
                )


def collect_reassigned_definitions(
    body: Sequence[parse_tree.Node],
) -> Set[parse_tree.Assignment]:
    """
    Collect the definitions of the variables which are re-assigned later.

    We need to know this to define the variables with ``const`` whenever possible,
    as ESLint otherwise complains. The variables defined in a switch branch or
    in a for-loop are scoped to the branch or the loop, respectively, so a variable
    of the same name in a sibling branch or a sibling loop is a different variable.
    """
    result: Set[parse_tree.Assignment] = set()
    _collect_reassigned_definitions_in_scope(
        statements=body, visible=dict(), result=result
    )
    return result


def generate_type(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
    types_module: Optional[Identifier],
) -> Tuple[Optional[Stripped], Optional[str]]:
    """
    Generate the TypeScript type for the given type annotation.

    If ``types_module`` is specified, it is prepended to all our types.

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
            typescript_common.PRIMITIVE_TYPE_MAP[
                intermediate.PrimitiveType(type_annotation.a_type.value)
            ],
            None,
        )

    elif isinstance(type_annotation, intermediate_type_inference.OurTypeAnnotation):
        our_type = type_annotation.our_type

        name: Identifier
        if isinstance(our_type, intermediate.Enumeration):
            name = typescript_naming.enum_name(our_type.name)
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return typescript_common.PRIMITIVE_TYPE_MAP[our_type.constrainee], None
        elif isinstance(our_type, intermediate.ConcreteClass):
            name = typescript_naming.class_name(our_type.name)
        elif isinstance(our_type, intermediate.AbstractClass):
            name = typescript_naming.interface_name(our_type.name)
        elif isinstance(our_type, intermediate.NamedUnion):
            name = typescript_naming.union_name(our_type.name)
        else:
            assert_never(our_type)

        if types_module is None:
            return Stripped(name), None

        return Stripped(f"{types_module}.{name}"), None

    elif isinstance(type_annotation, intermediate_type_inference.ListTypeAnnotation):
        item_type, error_message = generate_type(
            type_annotation=type_annotation.items, types_module=types_module
        )
        if error_message is not None:
            return None, error_message

        return Stripped(f"Array<{item_type}>"), None

    elif isinstance(type_annotation, intermediate_type_inference.SetTypeAnnotation):
        item_type, error_message = generate_type(
            type_annotation=type_annotation.items, types_module=types_module
        )
        if error_message is not None:
            return None, error_message

        return Stripped(f"Set<{item_type}>"), None

    elif isinstance(type_annotation, intermediate_type_inference.TupleTypeAnnotation):
        item_types: List[Stripped] = []
        for item in type_annotation.items:
            item_type, error_message = generate_type(
                type_annotation=item, types_module=types_module
            )
            if error_message is not None:
                return None, error_message

            assert item_type is not None
            item_types.append(item_type)

        return Stripped(f"[{', '.join(item_types)}]"), None

    elif isinstance(
        type_annotation, intermediate_type_inference.OptionalTypeAnnotation
    ):
        value_type, error_message = generate_type(
            type_annotation=type_annotation.value, types_module=types_module
        )
        if error_message is not None:
            return None, error_message

        return Stripped(f"{value_type} | null"), None

    return None, f"Unexpected type annotation of a variable: {type_annotation}"


class Transpiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a node of our AST to TypeScript code, or return an error."""

    _TYPESCRIPT_COMPARISON_MAP: Final[Mapping[parse_tree.Comparator, str]] = {
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
        reassigned_definitions: AbstractSet[parse_tree.Assignment] = frozenset(),
        types_module: Optional[Identifier] = Identifier("OurTypes"),
    ) -> None:
        """
        Initialize with the given values.

        The ``reassigned_definitions`` are defined with ``let``, while
        the other definitions are defined with ``const``, see
        :py:func:`collect_reassigned_definitions`.

        If ``types_module`` is specified, it is prepended to our types and
        the type guards. It is None when we transpile in the types module itself.
        """
        self.type_map = type_map
        self._types_module = types_module
        self._downcast_map = downcast_map
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )
        self._reassigned_definitions = reassigned_definitions

        # NOTE (mristin):
        # Keep track whenever we define a variable name, so that we can know how to
        # resolve it as a name in the TypeScript code.
        #
        # While this class does not directly use it, the descendants of this class do!
        self._variable_name_set: Set[Identifier] = set()

    def _qualify_with_types_module(self, identifier: Identifier) -> Stripped:
        """Prepend the types module to ``identifier``, if necessary."""
        if self._types_module is None:
            return Stripped(identifier)

        return Stripped(f"{self._types_module}.{identifier}")

    def _transform_without_downcast(
        self, node: parse_tree.Node
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Transform the ``node`` ignoring its narrowing by ``isinstance``, if any."""
        return super().transform(node)

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform(
        self, node: parse_tree.Node
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        code, error = self._transform_without_downcast(node)
        if error is not None:
            return None, error

        assert code is not None

        downcast = self._downcast_map.get(node, None)
        if downcast is None:
            return code, None

        # NOTE (mristin):
        # TypeScript does not reliably narrow the values through our conjunctions
        # and implications, especially in the lambdas, so we explicitly cast
        # every value narrowed by an ``isinstance`` guard. The named unions are
        # plain type aliases over the classes in TypeScript, so a cast suffices
        # both for the classes and for the named unions.
        target_type = downcast.target.our_type
        assert isinstance(
            target_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ), (
            f"Expected the target of a down-cast to be a class, "
            f"but got: {target_type}"
        )

        target_type_name: Identifier
        if isinstance(target_type, intermediate.AbstractClass):
            target_type_name = typescript_naming.interface_name(target_type.name)
        elif isinstance(target_type, intermediate.ConcreteClass):
            target_type_name = typescript_naming.class_name(target_type.name)
        else:
            assert_never(target_type)

        qualified_target_type_name = self._qualify_with_types_module(target_type_name)

        if "\n" in code:
            return (
                Stripped(
                    f"""\
(
{I}{indent_but_first_line(code, I)}
{I}as {qualified_target_type_name}
)"""
                ),
                None,
            )

        return Stripped(f"({code} as {qualified_target_type_name})"), None

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
            member_name = typescript_naming.enum_literal_name(node.name)

        elif isinstance(member_type, intermediate_type_inference.MethodTypeAnnotation):
            member_name = typescript_naming.method_name(node.name)

        elif isinstance(
            instance_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type.our_type, intermediate.Class):
            if node.name in instance_type.our_type.properties_by_name:
                member_name = typescript_naming.property_name(node.name)
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
                member_name = typescript_naming.enum_literal_name(node.name)
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
        collection_type = self.type_map[node.collection]

        if isinstance(
            intermediate_type_inference.beneath_optional(collection_type),
            intermediate_type_inference.TupleTypeAnnotation,
        ):
            # NOTE (mristin):
            # Tuples are heterogeneous and fixed-length, so, unlike lists, they can
            # not be indexed dynamically. Instead, the index must be a literal
            # integer known at the time of the code generation. This is enforced
            # in
            # :py:meth:`aas_core_codegen.intermediate.type_inference.Inferrer.transform_index`.
            #
            # We represent tuples as native TypeScript tuple types (arrays under
            # the hood), so we index them directly instead of going through
            # ``OurCommon.at`` -- that helper collapses the item type to a single
            # generic ``T``, which would lose the precise positional item type
            # that a native tuple index access retains.
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
                parse_tree.IsInstance,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.Constant,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.Tuple,
            )
            if not isinstance(node.collection, tuple_no_parentheses_types):
                collection = Stripped(f"({collection})")

            return Stripped(f"{collection}[{index_value}]"), None

        collection, error = self.transform(node.collection)
        if error is not None:
            return None, error

        assert collection is not None

        index, error = self.transform(node.index)
        if error is not None:
            return None, error

        assert index is not None

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.IsInstance,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.Index,
            parse_tree.Slice,
        )

        if not isinstance(node.collection, no_parentheses_types):
            collection = Stripped(f"({collection})")

        if isinstance(
            intermediate_type_inference.beneath_optional(collection_type),
            intermediate_type_inference.JsonObjectTypeAnnotation,
        ):
            # NOTE (mristin):
            # A JSON-able object is a plain object, indexed by its keys, while
            # ``OurCommon.at`` indexes an array by a position, and resolves
            # a negative index from its back.
            return Stripped(f"{collection}[{index}]"), None

        # NOTE (mristin):
        # Poor man's re-flow
        result = Stripped(f"OurCommon.at({collection}, {index})")
        if len(collection) + len(index) < 20:
            return result, None

        return (
            Stripped(
                f"""\
OurCommon.at(
{I}{collection},
{I}{index}
)"""
            ),
            None,
        )

    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        value_reprs: List[Stripped] = []

        for value_node in node.values:
            value_repr, error = self.transform(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert value_repr is not None
            value_reprs.append(value_repr)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the tuple", errors
            )

        joined = ", ".join(value_reprs)
        return Stripped(f"[{joined}]"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_list_literal(
        self, node: parse_tree.ListLiteral
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        items: List[Stripped] = []

        for item_node in node.items:
            item, error = self.transform(item_node)
            if error is not None:
                errors.append(error)
                continue

            assert item is not None
            items.append(item)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the list literal", errors
            )

        one_liner = f"[{', '.join(items)}]"
        if "\n" not in one_liner and len(one_liner) <= 60:
            return Stripped(one_liner), None

        items_joined = ",\n".join(items)
        return (
            Stripped(
                f"""\
[
{I}{indent_but_first_line(items_joined, I)}
]"""
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
        # instead of the characters, swaps the positions and does not count
        # the negative ones from the end, unlike Python. See ``sliceStr`` in
        # the generated common module.
        args: List[str] = [collection, start if start is not None else "0"]
        if end is not None:
            args.append(end)

        return Stripped(f"OurCommon.sliceStr({', '.join(args)})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_comparison(
        self, node: parse_tree.Comparison
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        comparator = Transpiler._TYPESCRIPT_COMPARISON_MAP[node.op]

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
        # TypeScript orders the strings by their UTF-16 code units, while Python
        # orders them by their characters (code points), so we order the strings
        # with our helpers. TypeScript does not order the booleans, so we convert
        # them to numbers, where ``false`` comes before ``true`` as in Python.
        if node.op not in (parse_tree.Comparator.EQ, parse_tree.Comparator.NE):
            primitive_type = intermediate_type_inference.try_primitive_type(
                self.type_map[node.left]
            )

            if primitive_type is intermediate_type_inference.PrimitiveType.STR:
                return (
                    Stripped(
                        f"OurCommon.compareByCodePoints({left}, {right}) "
                        f"{comparator} 0"
                    ),
                    None,
                )

            if primitive_type is intermediate_type_inference.PrimitiveType.BOOL:
                return (
                    Stripped(f"Number({left}) {comparator} Number({right})"),
                    None,
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

        member, error = self.transform(node.member)
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

        assert member is not None
        assert container is not None

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.IsInstance,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.ListLiteral,
        )

        if not isinstance(node.container, no_parentheses_types):
            container = Stripped(f"({container})")

        container_type = self.type_map[node.container]
        if isinstance(container_type, intermediate_type_inference.ListTypeAnnotation):
            return Stripped(f"{container}.includes({member})"), None
        elif isinstance(container_type, intermediate_type_inference.SetTypeAnnotation):
            return Stripped(f"{container}.has({member})"), None
        elif isinstance(
            container_type, intermediate_type_inference.JsonObjectTypeAnnotation
        ):
            # NOTE (mristin):
            # A JSON-able object is a plain object, so the membership is
            # a question about its own keys. The prototype is consulted through
            # ``Object.prototype`` so that an object with a key ``hasOwnProperty``
            # of its own does not shadow the check.
            return (
                Stripped(
                    f"Object.prototype.hasOwnProperty.call({container}, {member})"
                ),
                None,
            )
        elif (
            intermediate_type_inference.try_primitive_type(container_type)
            is intermediate_type_inference.PrimitiveType.STR
        ):
            return Stripped(f"{container}.includes({member})"), None
        else:
            return None, Error(
                node.container.original_node,
                f"We do not not how to generate the code to check whether "
                f"the container {container!r} of type {container_type} contains "
                f"a member {member!r}. Please contact the developers if you need "
                f"this feature.",
            )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_is_instance(
        self, node: parse_tree.IsInstance
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        # NOTE (mristin):
        # The type guards accept any instance of our classes, so we do not need
        # to down-cast the value if it has been already narrowed.
        value, error = self._transform_without_downcast(node.value)
        if error is not None:
            return None, error

        assert value is not None

        checks: List[Stripped] = []
        for cls in node.classes:
            guard = self._qualify_with_types_module(
                typescript_naming.function_name(Identifier(f"is_{cls.identifier}"))
            )
            checks.append(Stripped(f"{guard}({value})"))

        if len(checks) == 1:
            return checks[0], None

        joined_checks = " || ".join(checks)
        if "\n" not in joined_checks and len(joined_checks) <= 70:
            return Stripped(f"({joined_checks})"), None

        writer = io.StringIO()
        writer.write("(\n")
        for i, check in enumerate(checks):
            if i == 0:
                writer.write(f"{I}{indent_but_first_line(check, I)}\n")
            else:
                writer.write(f"{I}|| {indent_but_first_line(check, I)}\n")
        writer.write(")")

        return Stripped(writer.getvalue()), None

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
            parse_tree.IsInstance,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Index,
            parse_tree.Slice,
        )

        if isinstance(node.antecedent, no_parentheses_types_in_this_context):
            not_antecedent = f"!{antecedent}"
        else:
            # NOTE (mristin):
            # This is a very rudimentary heuristic for breaking the lines, and can be
            # greatly improved by rendering into TypeScript code. However, at this
            # point, we lack time for more sophisticated reformatting approaches.
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
            # greatly improved by rendering into TypeScript code. However, at this
            # point, we lack time for more sophisticated reformatting approaches.
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

        no_parentheses_types_in_this_context = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.IsInstance,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Index,
            parse_tree.Slice,
        )

        if not isinstance(node.member.instance, no_parentheses_types_in_this_context):
            instance = Stripped(f"({instance})")

        member_type = self.type_map[node.member]
        if isinstance(
            member_type, intermediate_type_inference.BuiltinMethodTypeAnnotation
        ):
            kind = member_type.method.kind

            if kind is intermediate_type_inference.BuiltinMethodKind.STR_FIND:
                # NOTE (mristin):
                # We do not use the native ``indexOf`` as it counts the UTF-16 code
                # units instead of the characters, and does not count a negative
                # start from the end, unlike Python. See ``findStr`` in
                # the generated common module.
                return (
                    Stripped(f"OurCommon.findStr({instance}, {', '.join(args)})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_LSTRIP:
                # NOTE (mristin):
                # TypeScript has no native equivalent of the Python ``str.lstrip``
                # with the given characters. See ``lstrip`` in the generated
                # common module, which strips the characters (code points) instead
                # of the UTF-16 code units.
                return (
                    Stripped(f"OurCommon.lstrip({instance}, {args[0]})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_RSTRIP:
                # NOTE (mristin):
                # TypeScript has no native equivalent of the Python ``str.rstrip``
                # with the given characters. See ``rstrip`` in the generated
                # common module, which strips the characters (code points) instead
                # of the UTF-16 code units.
                return (
                    Stripped(f"OurCommon.rstrip({instance}, {args[0]})"),
                    None,
                )

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_STARTSWITH:
                # NOTE (mristin):
                # The native ``startsWith`` compares the UTF-16 code units, which
                # gives the same result as the Python ``str.startswith`` unless
                # the prefix ends with a lone surrogate.
                return Stripped(f"{instance}.startsWith({args[0]})"), None

            elif kind is intermediate_type_inference.BuiltinMethodKind.STR_ENDSWITH:
                # NOTE (mristin):
                # The native ``endsWith`` compares the UTF-16 code units, which
                # gives the same result as the Python ``str.endswith`` unless
                # the suffix starts with a lone surrogate.
                return Stripped(f"{instance}.endsWith({args[0]})"), None

            elif kind is intermediate_type_inference.BuiltinMethodKind.SET_ADD:
                return Stripped(f"{instance}.add({args[0]})"), None

            elif kind is intermediate_type_inference.BuiltinMethodKind.LIST_APPEND:
                return Stripped(f"{instance}.push({args[0]})"), None

            elif (
                kind is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
                or kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
            ):
                # NOTE (mristin):
                # See ``setIntersection`` and ``setDifference`` in the generated
                # common module, which give a new set as Python does.
                function_name: str
                if (
                    kind
                    is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
                ):
                    function_name = "setIntersection"
                elif (
                    kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
                ):
                    function_name = "setDifference"
                else:
                    assert_never(kind)

                return (
                    Stripped(f"OurCommon.{function_name}({instance}, {args[0]})"),
                    None,
                )

            else:
                assert_never(kind)

        method_name = typescript_naming.method_name(node.member.name)

        joined_args = ", ".join(args)

        # Apply heuristic for breaking the lines
        if len(joined_args) > 50:
            writer = io.StringIO()
            writer.write(f"{instance}.{method_name}(\n")

            for i, arg in enumerate(args):
                writer.write(f"{I}{indent_but_first_line(arg, I)}")

                if i == len(args) - 1:
                    writer.write(")")
                else:
                    writer.write(",\n")

            return Stripped(writer.getvalue()), None
        else:
            return Stripped(f"{instance}.{method_name}({joined_args})"), None

    def _generate_len(
        self, node: parse_tree.Expression
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Generate code to get the length of a container."""
        collection, error = self.transform(node)
        if error is not None:
            return None, error

        assert collection is not None

        collection_type = intermediate_type_inference.beneath_optional(
            self.type_map[node]
        )

        primitive_type = intermediate_type_inference.try_primitive_type(collection_type)

        if primitive_type is intermediate_type_inference.PrimitiveType.STR:
            # NOTE (mristin):
            # We do not use the native ``length`` as it counts the UTF-16 code units
            # instead of the characters, unlike Python. See ``lenStr`` in
            # the generated common module. As the string is passed as an argument,
            # it needs no parentheses.
            return Stripped(f"OurCommon.lenStr({collection})"), None

        # NOTE (mristin):
        # We access the ``length`` as a member, so we need to parenthesize
        # the compound expressions.
        if not isinstance(
            node,
            (
                parse_tree.Name,
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.IsInstance,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.Constant,
            ),
        ):
            collection = Stripped(f"({collection})")

        if primitive_type is intermediate_type_inference.PrimitiveType.BYTEARRAY:
            return Stripped(f"{collection}.length"), None

        elif isinstance(
            collection_type,
            (
                intermediate_type_inference.ListTypeAnnotation,
                intermediate_type_inference.TupleTypeAnnotation,
            ),
        ):
            return Stripped(f"{collection}.length"), None

        elif isinstance(collection_type, intermediate_type_inference.SetTypeAnnotation):
            return Stripped(f"{collection}.size"), None

        elif isinstance(
            collection_type, intermediate_type_inference.JsonArrayTypeAnnotation
        ):
            # NOTE (mristin):
            # A JSON-able array is a plain array.
            return Stripped(f"{collection}.length"), None

        elif isinstance(
            collection_type, intermediate_type_inference.JsonObjectTypeAnnotation
        ):
            # NOTE (mristin):
            # A JSON-able object is a plain object, so its length is the number
            # of its own keys. A JSON-able *value* has no length at all --
            # the type inference refuses it before we get here.
            return Stripped(f"Object.keys({collection}).length"), None

        else:
            return None, Error(
                node.original_node,
                f"We do not know how to compute the length on type {collection_type}",
            )

    # fmt: off
    @require(
        lambda self, node:
        isinstance(
            self.type_map[node.name], intermediate_type_inference.VerificationTypeAnnotation
        )
    )
    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    # fmt: on
    def _generate_call_to_our_function(
        self, node: parse_tree.FunctionCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Generate the call to a verification function."""
        errors: List[Error] = []

        function_name, error = self.transform_name(node.name)
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
                node.original_node, "Failed to transpile the function call", errors
            )

        assert function_name is not None

        joined_args = ", ".join(args)

        # Apply heuristic for breaking the lines
        if len(function_name) + len(joined_args) > 50:
            writer = io.StringIO()
            writer.write(f"{function_name}(\n")

            for i, arg in enumerate(args):
                writer.write(f"{I}{indent_but_first_line(arg, I)}")

                if i == len(args) - 1:
                    writer.write("\n)")
                else:
                    writer.write(",\n")

            return Stripped(writer.getvalue()), None
        else:
            return Stripped(f"{function_name}({joined_args})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_function_call(
        self, node: parse_tree.FunctionCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
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
            return self._generate_call_to_our_function(node)

        elif isinstance(
            func_type, intermediate_type_inference.BuiltinFunctionTypeAnnotation
        ):
            if (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.LEN
            ):
                assert len(node.args) == 1, (
                    f"Expected exactly one argument, but got: {node.args}; "
                    f"this should have been caught before."
                )

                return self._generate_len(node.args[0])

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.ABS
            ):
                assert len(node.args) == 1, (
                    f"Expected exactly one argument, but got: {node.args}; "
                    f"this should have been caught before."
                )

                arg, error = self.transform(node.args[0])
                if error is not None:
                    return None, Error(
                        node.original_node,
                        "Failed to transpile the argument of abs",
                        [error],
                    )

                assert arg is not None

                return Stripped(f"Math.abs({arg})"), None

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
                # which we transpile as the spread syntax.
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

                return Stripped(f"[...{the_list}]"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.SET
            ):
                set_type, error_message = generate_type(
                    self.type_map[node], types_module=self._types_module
                )
                if error_message is not None:
                    return None, Error(node.original_node, error_message)

                return Stripped(f"new {set_type}()"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.INT
            ):
                assert len(node.args) == 1, (
                    f"Expected exactly one argument, but got: {node.args}; "
                    f"this should have been caught before."
                )

                arg, error = self.transform(node.args[0])
                if error is not None:
                    return None, Error(
                        node.original_node,
                        "Failed to transpile the argument of int",
                        [error],
                    )

                assert arg is not None

                # NOTE (mristin):
                # We do not use the native ``parseInt`` or ``Number`` as they accept
                # much more than the other targets, *e.g.*, the white space, ``1e3``
                # or ``0x10``, and silently lose the precision beyond the safe
                # integers. See ``parseSafeInt`` in the generated common module.
                return Stripped(f"OurCommon.parseSafeInt({arg})"), None

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
            return typescript_common.boolean_literal(node.value), None
        elif isinstance(node.value, int):
            if not typescript_common.representable_as_number(node.value):
                return None, Error(
                    node.original_node,
                    f"The value {node.value} is not representable as "
                    f"a TypeScript number",
                )
            return typescript_common.numeric_literal(node.value), None
        elif isinstance(node.value, float):
            return typescript_common.numeric_literal(node.value), None
        elif isinstance(node.value, str):
            return Stripped(typescript_common.string_literal(node.value)), None
        elif isinstance(node.value, bytes):
            literal, multiline = typescript_common.bytes_literal(node.value)

            if not multiline:
                return literal, None
            else:
                return (
                    Stripped(
                        f"""\
(
{I}{indent_but_first_line(literal, I)}
)"""
                    ),
                    None,
                )
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
            parse_tree.IsInstance,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.Constant,
        )
        if isinstance(node.value, no_parentheses_types):
            return Stripped(f"{value} === null"), None
        else:
            return Stripped(f"({value}) === null"), None

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
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.Constant,
        )
        if isinstance(node.value, no_parentheses_types_in_this_context):
            return Stripped(f"{value} !== null"), None
        else:
            return Stripped(f"({value}) !== null"), None

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
            parse_tree.IsInstance,
            parse_tree.Index,
            parse_tree.Slice,
        )
        if not isinstance(node.operand, no_parentheses_types_in_this_context):
            return Stripped(f"!({operand})"), None
        else:
            return Stripped(f"!{operand}"), None

    def _transform_and_or_or(
        self, node: Union[parse_tree.And, parse_tree.Or]
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
                parse_tree.IsInstance,
                parse_tree.Name,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.Comparison,
            )

            if not isinstance(value_node, no_parentheses_types_in_this_context):
                # NOTE (mristin):
                # This is a very rudimentary heuristic for breaking the lines, and can
                # be greatly improved by rendering into TypeScript code. However, at
                # this point, we lack time for more sophisticated reformatting
                # approaches.
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
            if isinstance(node, parse_tree.And):
                return None, Error(
                    node.original_node, "Failed to transpile the conjunction", errors
                )
            elif isinstance(node, parse_tree.Or):
                return None, Error(
                    node.original_node, "Failed to transpile the disjunction", errors
                )
            else:
                assert_never(node)

        assert len(values) >= 1
        if len(values) == 1:
            return Stripped(values[0]), None

        writer = io.StringIO()
        writer.write("(\n")
        for i, value in enumerate(values):
            if i == 0:
                writer.write(f"{I}{indent_but_first_line(value, I)}\n")
            else:
                if isinstance(node, parse_tree.And):
                    writer.write(f"{I}&& {indent_but_first_line(value, I)}\n")
                elif isinstance(node, parse_tree.Or):
                    writer.write(f"{I}|| {indent_but_first_line(value, I)}\n")
                else:
                    assert_never(node)

        writer.write(")")

        return Stripped(writer.getvalue()), None

    def transform_and(
        self, node: parse_tree.And
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_and_or_or(node)

    def transform_or(
        self, node: parse_tree.Or
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        return self._transform_and_or_or(node)

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
            parse_tree.IsInstance,
            parse_tree.Constant,
            parse_tree.Name,
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

    def transform_mod(
        self, node: parse_tree.Mod
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        left, error = self.transform(node.left)
        if error is not None:
            errors.append(error)

        right, error = self.transform(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the modulo operation", errors
            )

        assert left is not None
        assert right is not None

        # NOTE (mristin):
        # We deliberately do not use the native TypeScript operator ``%``. JavaScript
        # truncates the division towards zero so that its remainder takes the sign of
        # the dividend (``-7 % 3 == -1``). The meta-model is written in Python where
        # the division is floored so that the remainder takes the sign of the divisor
        # (``-7 % 3 == 2``). The two only coincide for the operands of the same sign,
        # but the invariants must behave the same in all the SDKs for all the inputs.
        # Hence, we call the helper which computes the floored remainder, see
        # :py:data:`aas_core_codegen.typescript.lib._generate_common.FLOOR_MOD`.
        joined_args = f"{left}, {right}"
        if "\n" not in joined_args and len(joined_args) <= 50:
            return Stripped(f"OurCommon.floorMod({joined_args})"), None

        return (
            Stripped(
                f"""\
OurCommon.floorMod(
{I}{indent_but_first_line(left, I)},
{I}{indent_but_first_line(right, I)}
)"""
            ),
            None,
        )

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

        assert operand is not None

        # NOTE (mristin):
        # We have to put a negative constant or a nested negation in parentheses
        # as well, since ``--1`` would be parsed as a decrement in TypeScript.
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
        # If we do not need interpolation, simply return the string literals
        # joined together by newlines.
        needs_interpolation = any(
            isinstance(value, parse_tree.FormattedValue) for value in node.values
        )
        if not needs_interpolation:
            return (
                Stripped(
                    typescript_common.string_literal(
                        "".join(value for value in node.values)  # type: ignore
                    )
                ),
                None,
            )

        parts: List[str] = []

        for value in node.values:
            if isinstance(value, str):
                parts.append(
                    typescript_common.string_literal(
                        value, without_enclosing=True, in_backticks=True
                    )
                )

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self.transform(value.value)
                if error is not None:
                    return None, error

                assert code is not None

                assert (
                    "\n" not in code
                ), f"New-lines are not expected in formatted values, but got: {code}"

                parts.append(f"${{{code}}}")
            else:
                assert_never(value)

        writer = io.StringIO()
        writer.write("`")
        for part in parts:
            writer.write(part)
        writer.write("`")

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
            qualifier_function = "OurCommon.some"
        elif isinstance(node, parse_tree.All):
            qualifier_function = "OurCommon.every"
        else:
            assert_never(node)

        source: Stripped
        if isinstance(node.generator, parse_tree.ForEach):
            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.IsInstance,
                parse_tree.Name,
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

            source = Stripped(
                f"""\
OurCommon.range(
{I}{indent_but_first_line(start, I)},
{I}{indent_but_first_line(end, I)}
)"""
            )

        else:
            assert_never(node.generator)

        return (
            Stripped(
                f"""\
{qualifier_function}(
{I}OurCommon.map(
{II}{indent_but_first_line(source, II)},
{II}{variable} =>
{III}{indent_but_first_line(condition, III)}
{I})
)"""
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

        value, error = self.transform(node.value)
        if error is not None:
            errors.append(error)

        is_definition = False

        if isinstance(node.target, parse_tree.Name):
            type_anno = self._environment.find(identifier=node.target.identifier)
            if type_anno is None:
                # NOTE (mristin):
                # This is a variable definition as we did not specify the identifier
                # in the environment.

                is_definition = True

                type_anno = self.type_map[node.target]
                self._variable_name_set.add(node.target.identifier)
                self._environment.set(
                    identifier=node.target.identifier, type_annotation=type_anno
                )

        if isinstance(node.target, parse_tree.Index):
            # NOTE (mristin):
            # The type inference allows only the items of a list as index targets.
            # We can not assign to ``OurCommon.at``, while the plain assignment
            # would not resolve the negative indices, and would silently grow
            # the array on an out-of-bound index.
            collection, error = self.transform(node.target.collection)
            if error is not None:
                errors.append(error)

            index, error = self.transform(node.target.index)
            if error is not None:
                errors.append(error)

            if len(errors) > 0:
                return None, Error(
                    node.original_node, "Failed to transpile the assignment", errors
                )

            assert collection is not None
            assert index is not None
            assert value is not None

            # NOTE (mristin):
            # Poor man's re-flow
            if "\n" not in value and len(collection) + len(index) + len(value) < 50:
                return (
                    Stripped(f"OurCommon.setAt({collection}, {index}, {value});"),
                    None,
                )

            return (
                Stripped(
                    f"""\
OurCommon.setAt(
{I}{indent_but_first_line(collection, I)},
{I}{indent_but_first_line(index, I)},
{I}{indent_but_first_line(value, I)}
);"""
                ),
                None,
            )

        target, error = self.transform(node=node.target)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assignment", errors
            )

        assert target is not None
        assert value is not None

        if is_definition:
            # NOTE (mristin):
            # The linter refuses the type annotations which are trivially inferred
            # from a literal, *e.g.*, ``let count: number = 0``.
            if node.annotation is not None and not (
                isinstance(node.value, parse_tree.Constant)
                and node.value.value is not None
                and isinstance(
                    self.type_map[node.target],
                    intermediate_type_inference.PrimitiveTypeAnnotation,
                )
            ):
                # NOTE (mristin):
                # We spell out the declared type, as it might differ from the type
                # of the value, *e.g.*, for ``null``.
                declared_type, error_message = generate_type(
                    type_annotation=self.type_map[node.target],
                    types_module=self._types_module,
                )
                if error_message is not None:
                    return None, Error(node.annotation.original_node, error_message)

                target = Stripped(f"{target}: {declared_type}")

            if node in self._reassigned_definitions:
                target = Stripped(f"let {target}")
            else:
                target = Stripped(f"const {target}")

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

        value, error = self.transform(node.value)
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
        writer.write(f"switch ({subject}) {{")

        for header, statements in clauses:
            stmts_and_defines, error = self._transform_branch(statements)
            if error is not None:
                errors.append(error)
                continue

            assert stmts_and_defines is not None
            stmts, defines_variables = stmts_and_defines

            # NOTE (mristin):
            # TypeScript falls through, so we end the clause with a ``break`` if its
            # execution can complete.
            if parse_tree.can_complete_normally(statements):
                stmts = stmts + [Stripped("break;")]

            writer.write("\n")
            writer.write(textwrap.indent(header, I))

            # NOTE (mristin):
            # We enclose the statements in a block only if they define variables
            # since all the clauses of a switch share the same scope otherwise.
            if defines_variables:
                writer.write(" {")
                for stmt in stmts:
                    writer.write("\n")
                    writer.write(textwrap.indent(stmt, II))
                writer.write(f"\n{I}}}")
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
        variable = typescript_naming.variable_name(variable_name)

        header: Optional[str] = None
        if isinstance(node.generator, parse_tree.ForEach):
            iteration, error = self.transform(node.generator.iteration)
            if error is not None:
                errors.append(error)
            else:
                assert iteration is not None
                header = (
                    f"for (const {variable} of "
                    f"{indent_but_first_line(iteration, I)})"
                )

        elif isinstance(node.generator, parse_tree.ForRange):
            start, error = self.transform(node.generator.start)
            if error is not None:
                errors.append(error)

            end, error = self.transform(node.generator.end)
            if error is not None:
                errors.append(error)

            if start is not None and end is not None:
                if "\n" not in start and "\n" not in end:
                    header = (
                        f"for (let {variable} = {start}; {variable} < {end}; "
                        f"{variable}++)"
                    )
                else:
                    header = f"""\
for (
{I}let {variable} = {indent_but_first_line(start, I)};
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
        loop_environment.set(
            identifier=variable_name,
            type_annotation=self.type_map[node.generator.variable],
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
            message = Stripped(
                typescript_common.string_literal(
                    f"Assertion failed: {ast.unparse(node.condition.original_node)}"
                )
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
{I}throw new Error(
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

            # NOTE (mristin):
            # ESLint refuses the empty blocks, but accepts a block with a comment.
            if len(stmts) == 0:
                writer.write(f"\n{I}// Intentionally empty.")

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
assert all(op in Transpiler._TYPESCRIPT_COMPARISON_MAP for op in parse_tree.Comparator)
