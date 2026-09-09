"""Transpile Python to Java code."""
import abc
import io
from typing import (
    Tuple,
    List,
    Mapping,
    Optional,
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

    elif isinstance(type_annotation, intermediate_type_inference.ListTypeAnnotation):
        item_type, error = generate_type(type_annotation=type_annotation.items)
        if error is not None:
            return None, error

        return Stripped(f"List<{item_type}>"), None

    elif isinstance(type_annotation, intermediate_type_inference.TupleTypeAnnotation):
        item_types = []  # type: List[Stripped]
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
        value_type = generate_type(type_annotation=type_annotation.value)

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


class Transpiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a node of our AST to Java code, or return an error."""

    _JAVA_COMPARISON_MAP = {
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
    ) -> None:
        """Initialize with the given values."""
        self.type_map = type_map
        self._optional_map = optional_map
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )

        # Keep track of optionals in is none checks, here we don't want to call
        # .get()
        self._beneath_none_check = set()  # type: Set[parse_tree.Node]

        # Keep track of method calls. In Java we don't pass around optionals
        # but Null. Optional should solely be used for return types. Thus, we
        # have to unpack the value and fall back if it is not set.
        self._beneath_call = set()  # type: Set[parse_tree.Node]

        # Keep track whenever we define a variable name, so that we can know how to
        # generate the reference in the Java code.
        self._variable_name_set = set()  # type: Set[Identifier]

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

        index_as_int = None  # type: Optional[int]
        try:
            index_as_int = int(index)
        except ValueError:
            pass

        if index_as_int is not None and index_as_int < 0:
            # pylint: disable=invalid-unary-operand-type
            index = Stripped(f"{collection}.size() - {abs(index_as_int)}")

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.Index,
            parse_tree.IsIn,
        )

        if not isinstance(node.collection, no_parentheses_types):
            collection = Stripped(f"({collection})")

        return Stripped(f"{collection}.get({index})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]
        item_exprs = []  # type: List[Stripped]

        for value_node in node.values:
            item_expr, error = self.transform(value_node)
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

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.IsIn,
            parse_tree.Index,
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

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.IsIn,
            parse_tree.Index,
        )

        if not isinstance(node.container, no_parentheses_types):
            container = Stripped(f"({container})")

        return Stripped(f"{container}.contains({member})"), None

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
        )

        if isinstance(node.antecedent, no_parentheses_types_in_this_context):
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

        if not isinstance(node.consequent, no_parentheses_types_in_this_context):
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

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_method_call(
        self, node: parse_tree.MethodCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]

        instance, error = self.transform(node.member.instance)
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
        errors = []  # type: List[Error]

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

        args = []  # type: List[Stripped]
        for arg_node in node.args:
            if isinstance(
                func_type, intermediate_type_inference.VerificationTypeAnnotation
            ):
                self._beneath_call.add(arg_node)
                arg, error = self.transform(arg_node)
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
            if func_type.func.name == "len":
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                collection_node = node.args[0]
                if not isinstance(
                    collection_node,
                    (parse_tree.Name, parse_tree.Member, parse_tree.MethodCall),
                ):
                    collection = f"({args[0]})"
                else:
                    collection = args[0]

                arg_type = self.type_map[node.args[0]]

                while isinstance(
                    arg_type, intermediate_type_inference.OptionalTypeAnnotation
                ):
                    arg_type = arg_type.value

                if (
                    isinstance(
                        arg_type, intermediate_type_inference.PrimitiveTypeAnnotation
                    )
                    and arg_type.a_type == intermediate_type_inference.PrimitiveType.STR
                ):
                    return Stripped(f"{collection}.length()"), None

                elif (
                    isinstance(arg_type, intermediate_type_inference.OurTypeAnnotation)
                    and isinstance(arg_type.our_type, intermediate.ConstrainedPrimitive)
                    and arg_type.our_type.constrainee == intermediate.PrimitiveType.STR
                ):
                    return Stripped(f"{collection}.length()"), None

                elif (
                    isinstance(
                        arg_type, intermediate_type_inference.PrimitiveTypeAnnotation
                    )
                    and arg_type.a_type
                    == intermediate_type_inference.PrimitiveType.BYTEARRAY
                ):
                    return Stripped(f"{collection}.length"), None

                elif (
                    isinstance(arg_type, intermediate_type_inference.OurTypeAnnotation)
                    and isinstance(arg_type.our_type, intermediate.ConstrainedPrimitive)
                    and arg_type.our_type.constrainee
                    == intermediate.PrimitiveType.BYTEARRAY
                ):
                    return Stripped(f"{collection}.length"), None

                elif isinstance(
                    arg_type, intermediate_type_inference.ListTypeAnnotation
                ):
                    return Stripped(f"{collection}.size()"), None

                else:
                    return None, Error(
                        node.original_node,
                        f"We do not know how to compute the length on type {arg_type}",
                        errors,
                    )
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
        )

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
        )

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
        raise NotImplementedError()

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
                parse_tree.Index,
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
        errors = []  # type: List[Error]
        values = []  # type: List[Stripped]

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
                parse_tree.Index,
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
        errors = []  # type: List[Error]

        left, error = self.transform(node.left)
        if error is not None:
            errors.append(error)

        right, error = self.transform(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            operation_name = None  # type: Optional[str]
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

    def transform_joined_str(
        self, node: parse_tree.JoinedStr
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        parts = []  # type: List[str]
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
        errors = []  # type: List[Error]

        iteration = None  # type: Optional[Stripped]
        start = None  # type: Optional[Stripped]
        end = None  # type: Optional[Stripped]

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

        qualifier_function = None  # type: Optional[str]
        if isinstance(node, parse_tree.Any):
            qualifier_function = "anyMatch"
        elif isinstance(node, parse_tree.All):
            qualifier_function = "allMatch"
        else:
            assert_never(node)

        source = None  # type: Optional[Stripped]
        if isinstance(node.generator, parse_tree.ForEach):
            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.Index,
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

            source = Stripped(
                f"""\
IntStream.range(
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

    def transform_assignment(
        self, node: parse_tree.Assignment
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]

        value, error = self.transform(node.value)
        if error is not None:
            errors.append(error)

        target = None  # type: Optional[Stripped]
        if isinstance(node.target, parse_tree.Name):
            type_anno = self._environment.find(identifier=node.target.identifier)
            if type_anno is None:
                # NOTE (empwilli):
                # This is a variable definition as we did not specify the identifier
                # in the environment.

                type_anno = self.type_map[node.value]
                self._variable_name_set.add(node.target.identifier)
                self._environment.set(
                    identifier=node.target.identifier, type_annotation=type_anno
                )

                target, error = self.transform_name(node=node.target)
                if error is not None:
                    errors.append(error)
                else:
                    target = Stripped(f"{type_anno} {target}")
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

        value, error = self.transform(node.value)
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


# noinspection PyProtectedMember,PyProtectedMember
assert all(op in Transpiler._JAVA_COMPARISON_MAP for op in parse_tree.Comparator)
