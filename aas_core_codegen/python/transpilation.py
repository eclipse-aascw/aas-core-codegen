"""Transpile meta-model Python code to Python code."""
import abc
import io
from typing import (
    Tuple,
    Optional,
    List,
    Mapping,
    Union,
    Set,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Stripped,
    assert_never,
    indent_but_first_line,
    Identifier,
)
from aas_core_codegen.python.common import (
    INDENT as I,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.parse import tree as parse_tree
from aas_core_codegen.python import (
    common as python_common,
    naming as python_naming,
)


class Transpiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a node of our AST to Python code, or return an error."""

    _PYTHON_COMPARISON_MAP = {
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
    ) -> None:
        """Initialize with the given values."""
        self.type_map = type_map
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )

        # NOTE (mristin, 2022-09-30):
        # Keep track whenever we define a variable name, so that we can know how to
        # resolve it as a name in the Python code.
        #
        # While this class does not directly use it, the descendants of this class do!
        self._variable_name_set = set()  # type: Set[Identifier]

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
            member_name = python_naming.enum_literal_name(node.name)

        elif isinstance(member_type, intermediate_type_inference.MethodTypeAnnotation):
            member_name = python_naming.method_name(node.name)

        elif isinstance(
            instance_type, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type.our_type, intermediate.Class):
            if node.name in instance_type.our_type.properties_by_name:
                member_name = python_naming.property_name(node.name)
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
                member_name = python_naming.enum_literal_name(node.name)
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
        collection, error = self.transform(node.collection)
        if error is not None:
            return None, error

        index, error = self.transform(node.index)
        if error is not None:
            return None, error
        assert index is not None

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.Index,
            parse_tree.Tuple,
        )

        if not isinstance(node.collection, no_parentheses_types):
            collection = Stripped(f"({collection})")

        return Stripped(f"{collection}[{index}]"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_comparison(
        self, node: parse_tree.Comparison
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        comparator = Transpiler._PYTHON_COMPARISON_MAP[node.op]

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

        assert member is not None
        assert container is not None

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.Index,
        )

        if not isinstance(node.container, no_parentheses_types):
            container = Stripped(f"({container})")

        if not isinstance(node.member, no_parentheses_types):
            member = Stripped(f"({member})")

        return Stripped(f"{member} in {container}"), None

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
            parse_tree.Index,
        )

        if isinstance(node.antecedent, no_parentheses_types_in_this_context):
            not_antecedent = f"not {antecedent}"
        else:
            # NOTE (mristin, 2022-09-30):
            # This is a very rudimentary heuristic for breaking the lines, and can be
            # greatly improved by rendering into Python code. However, at this point, we
            # lack time for more sophisticated reformatting approaches.
            if "\n" in antecedent:
                not_antecedent = f"""\
not (
{I}{indent_but_first_line(antecedent, I)}
)"""
            else:
                not_antecedent = f"not ({antecedent})"

        if not isinstance(node.consequent, no_parentheses_types_in_this_context):
            # NOTE (mristin, 2022-09-30):
            # This is a very rudimentary heuristic for breaking the lines, and can be
            # greatly improved by rendering into Python code. However, at this point, we
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

        return Stripped(f"{not_antecedent}\nor {consequent}"), None

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

        no_parentheses_types_in_this_context = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Index,
        )

        if not isinstance(node.member.instance, no_parentheses_types_in_this_context):
            instance = Stripped(f"({instance})")

        method_name = python_naming.method_name(node.member.name)

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

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_function_call(
        self, node: parse_tree.FunctionCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]

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
                node.original_node, "Failed to transpile the function call", errors
            )

        # NOTE (mristin, 2022-09-30):
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

        elif isinstance(
            func_type, intermediate_type_inference.BuiltinFunctionTypeAnnotation
        ):
            if func_type.func.name == "len":
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
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
            return Stripped("True" if node.value else "False"), None
        elif isinstance(node.value, (int, float)):
            return Stripped(str(node.value)), None
        elif isinstance(node.value, str):
            return Stripped(python_common.string_literal(node.value)), None
        elif isinstance(node.value, bytes):
            literal, multiline = python_common.bytes_literal(node.value)

            if not multiline:
                return Stripped(literal), None
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

    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        value_reprs = []  # type: List[Stripped]
        for value_node in node.values:
            value_repr, error = self.transform(value_node)
            if error is not None:
                return None, error

            assert value_repr is not None
            value_reprs.append(value_repr)

        if len(value_reprs) == 1:
            # NOTE (mristin):
            # A single-element Python tuple needs a trailing comma to be
            # distinguished from a parenthesized expression.
            return Stripped(f"({value_reprs[0]},)"), None

        joined_values = ", ".join(value_reprs)
        return Stripped(f"({joined_values})"), None

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
            parse_tree.Index,
        )
        if isinstance(node.value, no_parentheses_types):
            return Stripped(f"{value} is None"), None
        else:
            return Stripped(f"({value}) is None"), None

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
            parse_tree.Index,
        )
        if isinstance(node.value, no_parentheses_types_in_this_context):
            return Stripped(f"{value} is not None"), None
        else:
            return Stripped(f"({value}) is not None"), None

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
            parse_tree.Index,
        )
        if not isinstance(node.operand, no_parentheses_types_in_this_context):
            return Stripped(f"not ({operand})"), None
        else:
            return Stripped(f"not {operand}"), None

    def _transform_and_or_or(
        self, node: Union[parse_tree.And, parse_tree.Or]
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
                parse_tree.Name,
                parse_tree.Index,
                parse_tree.Comparison,
            )

            if not isinstance(value_node, no_parentheses_types_in_this_context):
                # NOTE (mristin, 2022-09-30):
                # This is a very rudimentary heuristic for breaking the lines, and can
                # be greatly improved by rendering into Python code. However, at this
                # point, we lack time for more sophisticated reformatting approaches.
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
                writer.write(f"{I}{value}\n")
            else:
                if isinstance(node, parse_tree.And):
                    writer.write(f"{I}and {indent_but_first_line(value, I)}\n")
                elif isinstance(node, parse_tree.Or):
                    writer.write(f"{I}or {indent_but_first_line(value, I)}\n")
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
        errors = []  # type: List[Error]

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
        # If we do not need interpolation, simply return the string literals
        # joined together by newlines.
        needs_interpolation = any(
            isinstance(value, parse_tree.FormattedValue) for value in node.values
        )
        if not needs_interpolation:
            return (
                Stripped(
                    python_common.string_literal(
                        "".join(value for value in node.values)  # type: ignore
                    )
                ),
                None,
            )

        parts = []  # type: List[str]

        # NOTE (mristin, 2022-09-30):
        # See which quotes occur more often in the non-interpolated parts, so that we
        # pick the escaping scheme which will result in as little escapes as possible.
        double_quotes_count = 0
        single_quotes_count = 0

        for value in node.values:
            if isinstance(value, str):
                double_quotes_count += value.count('"')
                single_quotes_count += value.count("'")

            elif isinstance(value, parse_tree.FormattedValue):
                pass
            else:
                assert_never(value)

        # Pick the escaping scheme
        if single_quotes_count <= double_quotes_count:
            enclosing = "'"
            quoting = python_common.StringQuoting.SINGLE_QUOTES
        else:
            enclosing = '"'
            quoting = python_common.StringQuoting.DOUBLE_QUOTES

        for value in node.values:
            if isinstance(value, str):
                parts.append(
                    python_common.string_literal(
                        value,
                        quoting=quoting,
                        without_enclosing=True,
                        duplicate_curly_brackets=True,
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

                parts.append(f"{{{code}}}")
            else:
                assert_never(value)

        writer = io.StringIO()
        writer.write("f")
        writer.write(enclosing)
        for part in parts:
            writer.write(part)
        writer.write(enclosing)

        return Stripped(writer.getvalue()), None

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

        qualifier_function: str
        if isinstance(node, parse_tree.Any):
            qualifier_function = "any"
        elif isinstance(node, parse_tree.All):
            qualifier_function = "all"
        else:
            assert_never(node)

        source: Stripped
        if isinstance(node.generator, parse_tree.ForEach):
            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.Name,
                parse_tree.Index,
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
range(
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
{I}{indent_but_first_line(condition, I)}
{I}for {variable} in {indent_but_first_line(source, I)}
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
        errors = []  # type: List[Error]

        value, error = self.transform(node.value)
        if error is not None:
            errors.append(error)

        if isinstance(node.target, parse_tree.Name):
            type_anno = self._environment.find(identifier=node.target.identifier)
            if type_anno is None:
                # NOTE (mristin, 2022-09-30):
                # This is a variable definition as we did not specify the identifier
                # in the environment.

                type_anno = self.type_map[node.value]
                self._variable_name_set.add(node.target.identifier)
                self._environment.set(
                    identifier=node.target.identifier, type_annotation=type_anno
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

        # NOTE (mristin, 2022-09-30):
        # This is a rudimentary heuristic for basic line breaks, but works well in
        # practice.
        if "\n" in value or len(value) > 50:
            return (
                Stripped(
                    f"""\
{target} = (
{I}{indent_but_first_line(value, I)})"""
                ),
                None,
            )

        return Stripped(f"{target} = {value}"), None

    def transform_return(
        self, node: parse_tree.Return
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.value is None:
            return Stripped("return"), None

        value, error = self.transform(node.value)
        if error is not None:
            return None, error

        assert value is not None

        # NOTE (mristin, 2022-09-30):
        # This is a rudimentary heuristic for basic line breaks, but works well in
        # practice.
        if "\n" in value or len(value) > 50:
            return (
                Stripped(
                    f"""\
return (
{I}{indent_but_first_line(value, I)})"""
                ),
                None,
            )

        return Stripped(f"return {value}"), None


# noinspection PyProtectedMember,PyProtectedMember
assert all(op in Transpiler._PYTHON_COMPARISON_MAP for op in parse_tree.Comparator)
