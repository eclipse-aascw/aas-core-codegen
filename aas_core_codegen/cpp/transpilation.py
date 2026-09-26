"""Transpile meta-model Python code to C++ code."""
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

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Stripped,
    assert_never,
    indent_but_first_line,
    Identifier,
)
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.parse import tree as parse_tree
from aas_core_codegen.cpp import (
    common as cpp_common,
    naming as cpp_naming,
)


# fmt: off
@require(
    lambda type_annotation:
    not isinstance(type_annotation, intermediate_type_inference.OurTypeAnnotation)
    or isinstance(type_annotation.our_type, intermediate.ConstrainedPrimitive)
)
# fmt: on
def _determine_which_to_wstring(
    type_annotation: Union[
        intermediate_type_inference.PrimitiveTypeAnnotation,
        intermediate_type_inference.OurTypeAnnotation,
    ]
) -> Optional[str]:
    """
    Determine which to-wstring function should be used.

    None indicates that the value needs not be converted (*i.e.*, it is already
    a wstring).
    """
    if isinstance(type_annotation, intermediate_type_inference.PrimitiveTypeAnnotation):
        if type_annotation.a_type is intermediate_type_inference.PrimitiveType.STR:
            return None
        elif type_annotation.a_type is intermediate_type_inference.PrimitiveType.INT:
            return "std::to_wstring"
        elif type_annotation.a_type is intermediate_type_inference.PrimitiveType.FLOAT:
            return "std::to_wstring"
        elif (
            type_annotation.a_type
            is intermediate_type_inference.PrimitiveType.BYTEARRAY
        ):
            base64_encode = cpp_naming.function_name(Identifier("base64_encode"))
            return f"wstringification::{base64_encode}"
        else:
            return "wstringification::to_wstring"

    elif isinstance(
        type_annotation, intermediate_type_inference.OurTypeAnnotation
    ) and isinstance(type_annotation.our_type, intermediate.ConstrainedPrimitive):
        constrainee = type_annotation.our_type.constrainee

        if constrainee is intermediate.PrimitiveType.BOOL:
            return "wstringification::to_wstring"
        elif constrainee is intermediate.PrimitiveType.INT:
            return "std::to_wstring"
        elif constrainee is intermediate.PrimitiveType.FLOAT:
            return "std::to_wstring"
        elif constrainee is intermediate.PrimitiveType.STR:
            return None
        elif constrainee is intermediate.PrimitiveType.BYTEARRAY:
            base64_encode = cpp_naming.function_name(Identifier("base64_encode"))
            return f"wstringification::{base64_encode}"
        else:
            assert_never(constrainee)

    else:
        raise ValueError(
            f"Unexpected type annotation for which we can not determine "
            f"the to-wstring function: {type_annotation!r}"
        )


# NOTE (mristin):
# We have to implement a very similar function for generating type annotations to
# ``aas_core_codegen.cpp.common.generate_type`` since we can not simply pass
# ``intermediate_type_inference.TypeAnnotationUnion`` to
# ``aas_core_codegen.cpp.common.generate_type``.

PRIMITIVE_TYPE_MAP = {
    intermediate_type_inference.PrimitiveType.BOOL: Stripped("bool"),
    intermediate_type_inference.PrimitiveType.INT: Stripped("int64_t"),
    intermediate_type_inference.PrimitiveType.FLOAT: Stripped("double"),
    intermediate_type_inference.PrimitiveType.STR: Stripped("std::wstring"),
    intermediate_type_inference.PrimitiveType.BYTEARRAY: Stripped(
        "std::vector<std::uint8_t>"
    ),
    intermediate_type_inference.PrimitiveType.NONE: Stripped("void*"),
    intermediate_type_inference.PrimitiveType.LENGTH: Stripped("size_t"),
}


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def generate_type(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
    types_namespace: Optional[Identifier] = None,
) -> Tuple[Optional[Stripped], Optional[str]]:
    """
    Generate the C++ type for the given type annotation.

    If ``types_namespace`` is specified, it is prepended to all our types.

    (mristin): We do not handle all the type annotations from
    :py:mod:`aas_core_codegen.intermediate.type_inference` as that would be
    YAGNI (*e.g.*, verification functions, built-in functions *etc.*).
    If we do not know how to generate the type in C++, we return an error message.
    """
    if isinstance(type_annotation, intermediate_type_inference.PrimitiveTypeAnnotation):
        return PRIMITIVE_TYPE_MAP[type_annotation.a_type], None

    elif isinstance(type_annotation, intermediate_type_inference.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            enum_name = cpp_naming.enum_name(type_annotation.our_type.name)
            if types_namespace is None:
                return enum_name, None

            return Stripped(f"{types_namespace}::{enum_name}"), None

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return cpp_common.PRIMITIVE_TYPE_MAP[our_type.constrainee], None

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # NOTE (mristin):
            # We always refer to interfaces even in cases of concrete classes without
            # concrete descendants since we want to allow enhancing.
            interface_name = cpp_naming.interface_name(our_type.name)

            if types_namespace is None:
                return interface_name, None

            return (
                Stripped(f"std::shared_ptr<{types_namespace}::{interface_name}>"),
                None,
            )

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is declared as a ``using`` alias to a
            # ``common::variant``, so we refer to it only by its name.
            union_name = cpp_naming.union_name(our_type.name)

            if types_namespace is None:
                return union_name, None

            return Stripped(f"{types_namespace}::{union_name}"), None

    elif isinstance(type_annotation, intermediate_type_inference.ListTypeAnnotation):
        item_type, error_msg = generate_type(
            type_annotation=type_annotation.items, types_namespace=types_namespace
        )
        if error_msg is not None:
            return None, error_msg

        assert item_type is not None
        if item_type.endswith(">"):
            return Stripped(f"std::vector<{item_type} >"), None

        return Stripped(f"std::vector<{item_type}>"), None

    elif isinstance(type_annotation, intermediate_type_inference.TupleTypeAnnotation):
        item_types = []  # type: List[Stripped]
        for item in type_annotation.items:
            item_type, error_msg = generate_type(
                type_annotation=item, types_namespace=types_namespace
            )
            if error_msg is not None:
                return None, error_msg

            assert item_type is not None
            item_types.append(item_type)

        item_types_joined = ",\n".join(item_types)

        return (
            Stripped(
                f"""\
std::tuple<
{I}{indent_but_first_line(item_types_joined, I)}
>"""
            ),
            None,
        )

    elif isinstance(
        type_annotation, intermediate_type_inference.OptionalTypeAnnotation
    ):
        value_type, error_msg = generate_type(
            type_annotation=type_annotation.value, types_namespace=types_namespace
        )

        if error_msg is not None:
            return None, error_msg

        assert value_type is not None

        if value_type.endswith(">"):
            return Stripped(f"common::optional<{value_type} >"), None

        return Stripped(f"common::optional<{value_type}>"), None

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


def determine_whether_referencable(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
) -> Tuple[Optional[bool], Optional[str]]:
    """
    Return ``True`` if the type annotation denotes a referencable value.

    (mristin): We do not handle all the type annotations from
    :py:mod:`aas_core_codegen.intermediate.type_inference` as that would be
    YAGNI (*e.g.*, verification functions, built-in functions *etc.*).
    If we do not know how to generate the type in C++, we return an error message.
    """
    if isinstance(type_annotation, intermediate_type_inference.PrimitiveTypeAnnotation):
        return False, None

    elif isinstance(type_annotation, intermediate_type_inference.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return False, None

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return False, None

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            return True, None

        elif isinstance(our_type, intermediate.NamedUnion):
            return True, None

    elif isinstance(type_annotation, intermediate_type_inference.ListTypeAnnotation):
        return True, None

    elif isinstance(type_annotation, intermediate_type_inference.TupleTypeAnnotation):
        return True, None

    elif isinstance(
        type_annotation, intermediate_type_inference.OptionalTypeAnnotation
    ):
        return True, None

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


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def generate_type_with_const_ref_if_applicable(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
    types_namespace: Optional[Identifier] = None,
) -> Tuple[Optional[Stripped], Optional[str]]:
    """
    Generate the C++ type and wrap it in ``const T&``, if applicable.

    If ``types_namespace`` is specified, it is prepended to all our types.

    (mristin): We do not handle all the type annotations from
    :py:mod:`aas_core_codegen.intermediate.type_inference` as that would be
    YAGNI (*e.g.*, verification functions, built-in functions *etc.*).
    If we do not know how to generate the type in C++, we return an error message.
    """
    code, error = generate_type(
        type_annotation=type_annotation, types_namespace=types_namespace
    )

    if error is not None:
        return None, error

    assert code is not None

    referencable, error = determine_whether_referencable(type_annotation)
    if error is not None:
        return None, error

    assert referencable is not None

    if referencable:
        return Stripped(f"const {code}&"), None

    return code, None


def _generate_call_with_single_argument(function: str, argument: str) -> Stripped:
    """
    Generate the call of ``function`` on the single ``argument``.

    We break the line if the argument spans multiple lines or is too long.
    """
    # NOTE (mristin):
    # This is a rudimentary heuristic for basic line breaks, but works well in
    # practice.
    if "\n" in argument or len(argument) > 50:
        return Stripped(
            f"""\
{function}(
{I}{indent_but_first_line(argument, I)}
)"""
        )

    return Stripped(f"{function}({argument})")


class Transpiler(
    parse_tree.RestrictedTransformer[Tuple[Optional[Stripped], Optional[Error]]]
):
    """Transpile a node of our AST to C++ code, or return an error."""

    _CPP_COMPARISON_MAP = {
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
        is_optional_map: Mapping[parse_tree.Node, bool],
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        is_optional_before_downcast_map: Mapping[parse_tree.Node, bool],
        environment: intermediate_type_inference.Environment,
        types_namespace: Optional[Identifier] = None,
    ) -> None:
        """
        Initialize with the given values.

        The ``downcast_map`` comes from the type inference, while
        the ``is_optional_map`` and the ``is_optional_before_downcast_map`` come
        from :py:class:`aas_core_codegen.cpp.optionaling.Inferrer`.

        If ``types_namespace`` is specified, it is prepended to all our types.
        """
        self.type_map = type_map
        self.is_optional_map = is_optional_map
        self.downcast_map = downcast_map
        self.is_optional_before_downcast_map = is_optional_before_downcast_map
        self._environment = intermediate_type_inference.MutableEnvironment(
            parent=environment
        )
        self._types_namespace = types_namespace

        # NOTE (mristin):
        # Keep track whenever we define a variable name, so that we can know how to
        # resolve it as a name in the C++ code.
        #
        # While this class does not directly use it, the descendants of this class do!
        self._variable_name_set = set()  # type: Set[Identifier]

    def _transform_enumeration_literal(
        self, enumeration_name: Identifier, literal_name: Identifier
    ) -> Stripped:
        """Generate code to represent an enumeration literal."""
        cpp_enum_name = cpp_naming.enum_name(enumeration_name)
        cpp_literal_name = cpp_naming.enum_literal_name(literal_name)
        if self._types_namespace is not None:
            return Stripped(
                f"{self._types_namespace}::{cpp_enum_name}::{cpp_literal_name}"
            )

        return Stripped(f"{cpp_enum_name}::{cpp_literal_name}")

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_and_value_if_necessary(
        self, node: parse_tree.Node
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Call ``.value()`` on the given node if it is a ``common::optional``.

        If the value denoted by ``node`` is not a ``common::optional``, it is returned
        transpiled as-is.
        """
        code, error = self.transform(node)
        if error is not None:
            return None, error

        if self.is_optional_map[node]:
            no_parentheses_types = (
                parse_tree.FunctionCall,
                parse_tree.Name,
                parse_tree.Constant,
            )
            if isinstance(node, no_parentheses_types):
                return Stripped(f"*{code}"), None

            return Stripped(f"(*({code}))"), None

        return code, None

    def _qualify_with_types_namespace(self, identifier: Identifier) -> Stripped:
        """Prepend the types namespace to ``identifier``, if specified."""
        if self._types_namespace is None:
            return Stripped(identifier)

        return Stripped(f"{self._types_namespace}::{identifier}")

    def _extract_underlying_instance(
        self, named_union: intermediate.NamedUnion, code: Stripped
    ) -> Stripped:
        """
        Generate the extraction of the instance held in ``named_union``.

        The ``code`` denotes the value of the named union. The extracted instance
        is a ``std::shared_ptr`` to ``IClass``.
        """
        underlying_of = self._qualify_with_types_namespace(
            cpp_naming.underlying_of_function_name(named_union.name)
        )

        return _generate_call_with_single_argument(
            function=underlying_of, argument=code
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform(
        self, node: parse_tree.Node
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        code, error = node.transform(self)
        if error is not None:
            return None, error

        assert code is not None

        downcast = self.downcast_map.get(node, None)
        if downcast is None:
            return code, None

        # NOTE (mristin):
        # The value has been narrowed down by an ``isinstance`` guard. We need to
        # down-cast it explicitly as C++ does not narrow the types. Since the classes
        # inherit the interfaces with ``virtual public``, we have to use
        # ``std::dynamic_pointer_cast``, as a static cast is not possible.
        #
        # The optional inferrer marks the down-cast nodes as non-optional. Hence,
        # we de-reference the value here, if necessary, before we cast it.

        if self.is_optional_before_downcast_map[node]:
            # NOTE (mristin):
            # The de-referenced value is passed on as an argument to a function
            # so that we need no outer parentheses.
            no_parentheses_types = (
                parse_tree.Member,
                parse_tree.FunctionCall,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.Index,
                parse_tree.Slice,
            )
            if isinstance(node, no_parentheses_types):
                code = Stripped(f"*{code}")
            else:
                code = Stripped(f"*({code})")

        source_type = downcast.source.our_type
        if isinstance(source_type, intermediate.NamedUnion):
            code = self._extract_underlying_instance(named_union=source_type, code=code)
        elif isinstance(source_type, intermediate.Class):
            pass
        else:
            return None, Error(
                node.original_node,
                f"Unexpected type of a value down-cast by an ``isinstance`` guard; "
                f"expected a class or a named union, but got: {downcast.source}",
            )

        target_type = downcast.target.our_type
        if not isinstance(target_type, intermediate.Class):
            return None, Error(
                node.original_node,
                f"Unexpected type to which a value needs to be down-cast by "
                f"an ``isinstance`` guard; expected a class, "
                f"but got: {downcast.target}",
            )

        interface_name = self._qualify_with_types_namespace(
            cpp_naming.interface_name(target_type.name)
        )

        return (
            _generate_call_with_single_argument(
                function=f"std::dynamic_pointer_cast<{interface_name}>", argument=code
            ),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_member(
        self, node: parse_tree.Member
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        instance, error = self._transform_and_value_if_necessary(node.instance)
        if error is not None:
            return None, error

        instance_type = self.type_map[node.instance]

        instance_type_beneath = intermediate_type_inference.beneath_optional(
            instance_type
        )

        member_type = self.type_map[node]
        member_type_beneath = intermediate_type_inference.beneath_optional(member_type)

        member_accessor: str

        if isinstance(
            instance_type_beneath, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type_beneath.our_type, intermediate.Enumeration):
            # NOTE (mristin):
            # This member denotes an enumeration literal of an enumeration.
            # In C++, enumeration literals are mere constants. Hence, we can not
            # "de-reference" the enumeration literals from an enumeration, but
            # generate the constant name here.
            return (
                self._transform_enumeration_literal(
                    enumeration_name=instance_type_beneath.our_type.name,
                    literal_name=node.name,
                ),
                None,
            )

        elif isinstance(
            member_type_beneath, intermediate_type_inference.MethodTypeAnnotation
        ):
            member_accessor = cpp_naming.method_name(node.name)

        elif isinstance(
            instance_type_beneath, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type_beneath.our_type, intermediate.Class):
            if node.name in instance_type_beneath.our_type.properties_by_name:
                getter_name = cpp_naming.getter_name(node.name)
                member_accessor = f"{getter_name}()"
            else:
                return None, Error(
                    node.original_node,
                    f"The property {node.name!r} has not been defined "
                    f"in the class {instance_type_beneath.our_type.name!r}",
                )

        elif isinstance(
            instance_type_beneath,
            intermediate_type_inference.EnumerationAsTypeTypeAnnotation,
        ):
            if node.name in instance_type_beneath.enumeration.literals_by_name:
                # NOTE (mristin):
                # The member denotes an enumeration literal of an enumeration.
                # In C++, enumeration literals are mere constants. Hence, we can not
                # "de-reference" the enumeration literals from an enumeration, but
                # generate the constant name here.
                return (
                    self._transform_enumeration_literal(
                        enumeration_name=instance_type_beneath.enumeration.name,
                        literal_name=node.name,
                    ),
                    None,
                )
            else:
                return None, Error(
                    node.original_node,
                    f"The literal {node.name!r} has not been defined "
                    f"in the enumeration {instance_type_beneath.enumeration.name!r}",
                )
        else:
            return None, Error(
                node.original_node,
                f"We do not know how to generate the member access. The inferred type "
                f"of the instance was {instance_type}, while the member type "
                f"was {member_type}. However, we do not know how to resolve "
                f"the member {node.name!r} in {instance_type}.",
            )

        assert isinstance(
            instance_type_beneath, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(instance_type_beneath.our_type, intermediate.Class), (
            f"The access to enumeration literals is expected to have been handled "
            f"before. If we got to this point, the instance is expected to be "
            f"an instance of a class, as we access its members with '->' and "
            f"assume it is a ``std::shared_ptr``. However, we got: {instance_type}"
        )

        return Stripped(f"{instance}->{member_accessor}"), None

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
            # not be indexed at runtime. Instead, the index must be a literal
            # integer known at the time of the code generation so that we can
            # generate a call to ``std::get<...>``.
            #
            # This is enforced in
            # :py:meth:`aas_core_codegen.intermediate.type_inference.Inferrer.transform_index`.
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

            collection, error = self._transform_and_value_if_necessary(node.collection)
            if error is not None:
                return None, error
            assert collection is not None

            no_parentheses_types = (
                parse_tree.Member,
                parse_tree.FunctionCall,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.Constant,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.Tuple,
            )
            if not isinstance(node.collection, no_parentheses_types):
                collection = Stripped(f"({collection})")

            return Stripped(f"std::get<{index_value}>({collection})"), None

        collection, error = self._transform_and_value_if_necessary(node.collection)
        if error is not None:
            return None, error

        index, error = self._transform_and_value_if_necessary(node.index)
        if error is not None:
            return None, error
        assert index is not None

        if isinstance(
            intermediate_type_inference.beneath_optional(collection_type),
            intermediate_type_inference.JsonObjectTypeAnnotation,
        ):
            # NOTE (mristin):
            # The keys of a ``nlohmann::json`` object are UTF-8 encoded, while
            # a string in the transpiled code is a wide string, so the key has
            # to be converted. Unlike a list, an object knows no negative
            # index, so there is nothing to resolve from its back.
            wstring_to_utf8 = cpp_naming.function_name(Identifier("wstring_to_utf8"))

            return (
                Stripped(
                    f"""\
{collection}.at(
{I}common::{wstring_to_utf8}(
{II}{indent_but_first_line(index, II)}
{I})
)"""
                ),
                None,
            )

        index_as_int = None  # type: Optional[int]
        try:
            index_as_int = int(index)
        except ValueError:
            pass

        if index_as_int is not None and index_as_int == -1:
            return Stripped(f"{collection}.back()"), None

        if index_as_int is not None and index_as_int < -1:
            # pylint: disable=invalid-unary-operand-type
            index = Stripped(f"{collection}.size() - {-index_as_int}")

        if "\n" in index:
            return (
                Stripped(
                    f"""\
{collection}.at(
{I}{indent_but_first_line(index, I)}
)"""
                ),
                None,
            )

        return Stripped(f"{collection}.at({index})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]
        value_reprs = []  # type: List[Stripped]

        for value_node in node.values:
            value_repr, error = self._transform_and_value_if_necessary(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert value_repr is not None
            value_reprs.append(value_repr)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the tuple", errors
            )

        if len(value_reprs) == 0:
            return Stripped("std::make_tuple()"), None

        joined_values = ",\n".join(value_reprs)
        return (
            Stripped(
                f"""\
std::make_tuple(
{I}{indent_but_first_line(joined_values, I)}
)"""
            ),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_comparison(
        self, node: parse_tree.Comparison
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        comparator = Transpiler._CPP_COMPARISON_MAP[node.op]

        errors = []

        left, error = self._transform_and_value_if_necessary(node.left)
        if error is not None:
            errors.append(error)

        right, error = self._transform_and_value_if_necessary(node.right)
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

        member, error = self._transform_and_value_if_necessary(node.member)
        if error is not None:
            errors.append(error)

        container, error = self._transform_and_value_if_necessary(node.container)
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

        container_type = self.type_map[node.container]

        # NOTE (mristin):
        # A JSON-able object is a ``nlohmann::json`` which holds an object, so
        # the membership is a question about its keys, and not about the values
        # which the generic ``common::Contains`` would iterate over. The keys
        # are UTF-8 encoded, while a string in the transpiled code is
        # a wide string, so the member has to be converted.
        if isinstance(
            container_type, intermediate_type_inference.JsonObjectTypeAnnotation
        ):
            wstring_to_utf8 = cpp_naming.function_name(Identifier("wstring_to_utf8"))

            return (
                Stripped(
                    f"""\
{container}.contains(
{I}common::{wstring_to_utf8}(
{II}{indent_but_first_line(member, II)}
{I})
)"""
                ),
                None,
            )

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

        contains_function = cpp_naming.function_name(Identifier("contains"))

        return (
            Stripped(
                f"""\
common::{contains_function}(
{I}{indent_but_first_line(container, I)},
{I}{indent_but_first_line(member, I)}
)"""
            ),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_is_instance(
        self, node: parse_tree.IsInstance
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        value, error = self._transform_and_value_if_necessary(node.value)
        if error is not None:
            return None, error

        assert value is not None

        value_type = self.type_map[node.value]
        if not isinstance(value_type, intermediate_type_inference.OurTypeAnnotation):
            return None, Error(
                node.original_node,
                f"Expected the value of ``isinstance`` to be a class or "
                f"a named union as checked in the type inference, "
                f"but got: {value_type}",
            )

        instance: Stripped

        if isinstance(value_type.our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # We de-reference the result of a function call so that we need
            # no parentheses.
            underlying = self._extract_underlying_instance(
                named_union=value_type.our_type, code=value
            )
            instance = Stripped(f"*{underlying}")

        elif isinstance(value_type.our_type, intermediate.Class):
            # NOTE (mristin):
            # The de-referenced optional value is already wrapped in parentheses,
            # and the down-cast value is a function call. Hence, we can
            # de-reference both without additional parentheses.
            no_parentheses_types = (
                parse_tree.Member,
                parse_tree.FunctionCall,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.Index,
                parse_tree.Slice,
            )

            if (
                isinstance(node.value, no_parentheses_types)
                or self.is_optional_map[node.value]
                or node.value in self.downcast_map
            ):
                instance = Stripped(f"*{value}")
            else:
                instance = Stripped(f"*({value})")

        else:
            return None, Error(
                node.original_node,
                f"Expected the value of ``isinstance`` to be a class or "
                f"a named union as checked in the type inference, "
                f"but got: {value_type}",
            )

        checks = []  # type: List[Stripped]
        for cls_name in node.classes:
            is_cls = self._qualify_with_types_namespace(
                cpp_naming.is_function_name(cls_name.identifier)
            )

            checks.append(
                _generate_call_with_single_argument(function=is_cls, argument=instance)
            )

        if len(checks) == 1:
            return checks[0], None

        # NOTE (mristin):
        # We always wrap the disjunction in parentheses so that the callers never
        # need to wrap ``isinstance`` in additional parentheses.
        checks_joined = "\n|| ".join(checks)
        return (
            Stripped(
                f"""\
(
{I}{indent_but_first_line(checks_joined, I)}
)"""
            ),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_implication(
        self, node: parse_tree.Implication
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []

        antecedent, error = self._transform_and_value_if_necessary(node.antecedent)
        if error is not None:
            errors.append(error)

        consequent, error = self._transform_and_value_if_necessary(node.consequent)
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
            parse_tree.IsInstance,
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

        return Stripped(f"{not_antecedent}\n|| {consequent}"), None

    def _as_int64_position(self, node: parse_tree.Node, code: Stripped) -> Stripped:
        """
        Convert the transpiled position ``node`` to an ``int64_t``.

        The string helpers take the positions as ``int64_t``'s, our integers,
        while the lengths are ``size_t``'s.
        """
        type_anno = self.type_map[node]
        if (
            isinstance(type_anno, intermediate_type_inference.PrimitiveTypeAnnotation)
            and type_anno.a_type is intermediate_type_inference.PrimitiveType.LENGTH
        ):
            return Stripped(f"static_cast<int64_t>({code})")

        return code

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_slice(
        self, node: parse_tree.Slice
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]

        collection, error = self._transform_and_value_if_necessary(node.collection)
        if error is not None:
            errors.append(error)

        start = None  # type: Optional[Stripped]
        if node.start is not None:
            start, error = self._transform_and_value_if_necessary(node.start)
            if error is not None:
                errors.append(error)

        end = None  # type: Optional[Stripped]
        if node.end is not None:
            end, error = self._transform_and_value_if_necessary(node.end)
            if error is not None:
                errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the slice", errors
            )

        assert collection is not None

        if node.start is not None:
            assert start is not None
            start = self._as_int64_position(node.start, start)

        if node.end is not None:
            assert end is not None
            end = self._as_int64_position(node.end, end)

        # NOTE (mristin):
        # We do not use the native ``substr`` as it throws on a start out of range,
        # and does not count the negative positions from the end, unlike Python.
        # See ``SliceStr`` in the generated common module.
        args = [collection, start if start is not None else "0"]  # type: List[str]
        if end is not None:
            args.append(end)

        return Stripped(f"common::SliceStr({', '.join(args)})"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_builtin_method_call(
        self,
        node: parse_tree.MethodCall,
        method: intermediate_type_inference.BuiltinMethod,
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Transpile the call to a built-in method such as ``str.find``."""
        errors = []  # type: List[Error]

        instance, error = self._transform_and_value_if_necessary(node.member.instance)
        if error is not None:
            errors.append(error)

        args = []  # type: List[Stripped]
        for arg_node in node.args:
            arg, error = self._transform_and_value_if_necessary(arg_node)
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

        if method is intermediate_type_inference.STR_FIND:
            # NOTE (mristin):
            # We do not use the native ``find`` as it gives ``npos`` instead of -1,
            # and does not count a negative start from the end, unlike Python. See
            # ``FindStr`` in the generated common module.
            if len(args) == 2:
                args[1] = self._as_int64_position(node.args[1], args[1])

            return (
                Stripped(f"common::FindStr({', '.join([instance] + args)})"),
                None,
            )

        return None, Error(
            node.original_node,
            f"The handling of the built-in method {method.name!r} "
            f"has not been implemented",
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_method_call(
        self, node: parse_tree.MethodCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        member_type = self.type_map[node.member]
        if isinstance(
            member_type, intermediate_type_inference.BuiltinMethodTypeAnnotation
        ):
            return self._transform_builtin_method_call(
                node=node, method=member_type.method
            )

        errors = []  # type: List[Error]

        member_access, error = self._transform_and_value_if_necessary(node.member)
        if error is not None:
            errors.append(error)

        args = []  # type: List[Stripped]
        for arg_node in node.args:
            arg_type = self.type_map[arg_node]

            # NOTE (mristin):
            # This is a tough call to make. We decide that a value, for which we
            # know that it might be null, will not be de-referenced. On the other
            # hand, if the value is certainly not null, we de-reference it.
            #
            # The problem here is that the actual type of the argument in C++ changes
            # depending on whether we check for its nullness before with an implication.

            arg: Optional[Stripped]
            if isinstance(arg_type, intermediate_type_inference.OptionalTypeAnnotation):
                arg, error = self.transform(arg_node)
            else:
                arg, error = self._transform_and_value_if_necessary(arg_node)

            if error is not None:
                errors.append(error)
                continue

            assert arg is not None

            args.append(arg)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the method call", errors
            )

        assert member_access is not None

        if len(args) == 0:
            return Stripped(f"{member_access}()"), None

        joined_args = ",\n".join(args)
        return (
            Stripped(
                f"""\
{member_access}(
{I}{indent_but_first_line(joined_args, I)}
)"""
            ),
            None,
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_function_call(
        self, node: parse_tree.FunctionCall
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]

        args = []  # type: List[Stripped]
        for arg_node in node.args:
            arg_type = self.type_map[arg_node]

            # NOTE (mristin):
            # This is a tough call to make. We decide that a value, for which we
            # know that it might be null, will not be de-referenced. On the other
            # hand, if the value is certainly not null, we de-reference it.
            #
            # The problem here is that the actual type of the argument in C++ changes
            # depending on whether we check for its nullness before with an implication.
            arg: Optional[Stripped]
            if isinstance(arg_type, intermediate_type_inference.OptionalTypeAnnotation):
                arg, error = self.transform(arg_node)
            else:
                arg, error = self._transform_and_value_if_necessary(arg_node)

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

            if len(args) == 0:
                return Stripped(f"{function_name}()"), None

            joined_args = ",\n".join(args)
            return (
                Stripped(
                    f"""\
{function_name}(
{I}{indent_but_first_line(joined_args, I)}
)"""
                ),
                None,
            )

        elif isinstance(
            func_type, intermediate_type_inference.BuiltinFunctionTypeAnnotation
        ):
            if func_type.func.name == "len":
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                no_parentheses_types_in_this_context = (
                    parse_tree.Member,
                    parse_tree.FunctionCall,
                    parse_tree.MethodCall,
                    parse_tree.Name,
                    parse_tree.IsIn,
                    parse_tree.IsInstance,
                    parse_tree.Index,
                    parse_tree.Slice,
                    parse_tree.All,
                    parse_tree.Any,
                )

                first_arg, error = self._transform_and_value_if_necessary(node.args[0])
                if error is not None:
                    return None, error

                assert first_arg is not None

                if not isinstance(node.args[0], no_parentheses_types_in_this_context):
                    first_arg = Stripped(f"({first_arg})")

                return Stripped(f"{first_arg}.size()"), None

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
            return Stripped(cpp_common.float_literal(node.value)), None
        elif isinstance(node.value, str):
            return Stripped(cpp_common.wstring_literal(node.value)), None
        elif isinstance(node.value, bytes):
            literal, multiline = cpp_common.bytes_literal(node.value)

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

    def transform_is_none(
        self, node: parse_tree.IsNone
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        value, error = self.transform(node.value)
        if error is not None:
            return None, error

        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.IsIn,
            parse_tree.IsInstance,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
        )
        if isinstance(node.value, no_parentheses_types):
            return Stripped(f"!({value}.has_value())"), None
        else:
            return Stripped(f"!(({value}).has_value())"), None

    def transform_is_not_none(
        self, node: parse_tree.IsNotNone
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        value, error = self.transform(node.value)
        if error is not None:
            return None, error

        no_parentheses_types_in_this_context = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.IsIn,
            parse_tree.IsInstance,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
        )
        if isinstance(node.value, no_parentheses_types_in_this_context):
            return Stripped(f"{value}.has_value()"), None
        else:
            return Stripped(f"({value}).has_value()"), None

    @abc.abstractmethod
    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        raise NotImplementedError()

    def transform_not(
        self, node: parse_tree.Not
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        operand, error = self._transform_and_value_if_necessary(node.operand)
        if error is not None:
            return None, error

        no_parentheses_types_in_this_context = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.IsIn,
            parse_tree.IsInstance,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.All,
            parse_tree.Any,
        )
        if not isinstance(node.operand, no_parentheses_types_in_this_context):
            return Stripped(f"!({operand})"), None
        else:
            return Stripped(f"!{operand}"), None

    def _transform_and_or_or(
        self, node: Union[parse_tree.And, parse_tree.Or]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors = []  # type: List[Error]
        values = []  # type: List[Stripped]

        for value_node in node.values:
            value, error = self._transform_and_value_if_necessary(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert value is not None

            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.FunctionCall,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.IsInstance,
                parse_tree.Index,
                parse_tree.Slice,
                parse_tree.All,
                parse_tree.Any,
                parse_tree.Comparison,
            )

            if not isinstance(value_node, no_parentheses_types_in_this_context):
                # NOTE (mristin):
                # This is a very rudimentary heuristic for breaking the lines, and can
                # be greatly improved by rendering into C++ code. However, at this
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
        errors = []  # type: List[Error]

        left, error = self._transform_and_value_if_necessary(node.left)
        if error is not None:
            errors.append(error)

        right, error = self._transform_and_value_if_necessary(node.right)
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
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.IsIn,
            parse_tree.IsInstance,
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
            return cpp_common.wstring_literal(text), None

        # NOTE (mristin):
        # We need the interpolation if we got so far.

        args = []  # type: List[str]

        for value in node.values:
            if isinstance(value, str):
                args.append(cpp_common.wstring_literal(value))

            elif isinstance(value, parse_tree.FormattedValue):
                code, error = self._transform_and_value_if_necessary(value.value)
                if error is not None:
                    return None, error

                assert code is not None

                value_type = self.type_map[value.value]

                if not isinstance(
                    value_type, intermediate_type_inference.PrimitiveTypeAnnotation
                ) and not (
                    isinstance(
                        value_type, intermediate_type_inference.OurTypeAnnotation
                    )
                    and isinstance(
                        value_type.our_type, intermediate.ConstrainedPrimitive
                    )
                ):
                    return None, Error(
                        value.original_node,
                        f"Unexpected non-primitive formatted value type: {value_type}",
                    )

                to_wstring = _determine_which_to_wstring(value_type)

                if to_wstring is None:
                    args.append(code)
                else:
                    if "\n" in code:
                        args.append(
                            f"""\
{to_wstring}(
{I}{indent_but_first_line(code, I)}
)"""
                        )
                    else:
                        args.append(f"{to_wstring}({code})")

        args_joined = ",\n".join(args)

        concat = cpp_naming.function_name(Identifier("concat"))
        return (
            Stripped(
                f"""\
common::{concat}(
{I}{indent_but_first_line(args_joined, I)}
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
            iteration, error = self._transform_and_value_if_necessary(
                node.generator.iteration
            )
            if error is not None:
                errors.append(error)

        elif isinstance(node.generator, parse_tree.ForRange):
            start, error = self._transform_and_value_if_necessary(node.generator.start)
            if error is not None:
                errors.append(error)

            end, error = self._transform_and_value_if_necessary(node.generator.end)
            if error is not None:
                errors.append(error)

        else:
            assert_never(node.generator)

        variable_name = node.generator.variable.identifier
        variable_type_annotation = self.type_map[node.generator.variable]

        variable_name_cpp = cpp_naming.variable_name(variable_name)
        variable_type_cpp, error_msg = generate_type_with_const_ref_if_applicable(
            type_annotation=variable_type_annotation,
            types_namespace=self._types_namespace,
        )
        if error_msg is not None:
            errors.append(Error(node.generator.variable.original_node, error_msg))

        try:
            self._environment.set(
                identifier=variable_name, type_annotation=variable_type_annotation
            )
            self._variable_name_set.add(variable_name)

            condition, error = self._transform_and_value_if_necessary(node.condition)
            if error is not None:
                errors.append(error)

            variable, error = self._transform_and_value_if_necessary(
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
                qualifier_function = cpp_naming.function_name(Identifier("Some"))
            elif isinstance(node, parse_tree.All):
                qualifier_function = cpp_naming.function_name(Identifier("All"))
            else:
                assert_never(node)

            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.MethodCall,
                parse_tree.FunctionCall,
                parse_tree.Name,
                parse_tree.IsIn,
                parse_tree.IsInstance,
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

            # NOTE (mristin):
            # We implicitly capture all the variables by reference,
            # see: https://en.cppreference.com/w/cpp/language/lambda#Lambda_capture.

            return (
                Stripped(
                    f"""\
common::{qualifier_function}(
{I}[&]({variable_type_cpp} {variable_name_cpp}) -> bool {{
{II}return {indent_but_first_line(condition, II)};
{I}}},
{I}{indent_but_first_line(source, I)}
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
common::{qualifier_function}(
{I}[&]({variable_type_cpp} {variable_name_cpp}) -> bool {{
{II}return {indent_but_first_line(condition, II)};
{I}}},
{I}{indent_but_first_line(start, I)},
{I}{indent_but_first_line(end, I)}
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

        value_type = self.type_map[node.value]

        is_definition = False

        target = None  # type: Optional[Stripped]
        if isinstance(node.target, parse_tree.Name):
            target_type = self._environment.find(identifier=node.target.identifier)
            if target_type is None:
                # NOTE (mristin):
                # This is a variable definition as we did not specify the identifier
                # in the environment.

                is_definition = True

                target_type = value_type
                self._variable_name_set.add(node.target.identifier)
                self._environment.set(
                    identifier=node.target.identifier, type_annotation=target_type
                )

                target, error = self.transform_name(node=node.target)
                if error is not None:
                    errors.append(error)
            else:
                target, error = self.transform(node=node.target)
                if error is not None:
                    errors.append(error)
        else:
            target_type = self.type_map[node.target]

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assignment", errors
            )

        assert target is not None
        assert target_type is not None

        value: Optional[Stripped]

        if isinstance(
            target_type, intermediate_type_inference.OptionalTypeAnnotation
        ) and isinstance(
            value_type, intermediate_type_inference.OptionalTypeAnnotation
        ):
            value, error = self.transform(node.value)
        elif not isinstance(
            target_type, intermediate_type_inference.OptionalTypeAnnotation
        ) and isinstance(
            value_type, intermediate_type_inference.OptionalTypeAnnotation
        ):
            value, error = self._transform_and_value_if_necessary(node.value)
        else:
            # NOTE (mristin):
            # This is the case covering (target non-optional, value non-optional) and
            # (target optional, value non-optional).
            value, error = self.transform(node.value)

        if error is not None:
            return None, error
        assert value is not None

        maybe_definition_prefix = ""
        if is_definition:
            # NOTE (mristin):
            # We spell out the primitive types, as ``auto`` would deduce the type
            # from the literal, *e.g.*, ``int`` instead of ``int64_t`` for ``0``, or
            # ``const wchar_t*`` instead of ``std::wstring`` for ``L"..."``.
            if isinstance(
                value_type, intermediate_type_inference.PrimitiveTypeAnnotation
            ) and value_type.a_type is not (
                intermediate_type_inference.PrimitiveType.NONE
            ):
                maybe_definition_prefix = f"{PRIMITIVE_TYPE_MAP[value_type.a_type]} "
            else:
                maybe_definition_prefix = "auto "

        # NOTE (mristin):
        # This is a rudimentary heuristic for basic line breaks, but works well in
        # practice.
        if "\n" in value or len(value) > 50:
            return (
                Stripped(
                    f"""\
{maybe_definition_prefix}{target} = (
{I}{indent_but_first_line(value, I)}
);"""
                ),
                None,
            )

        return Stripped(f"{maybe_definition_prefix}{target} = {value};"), None

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
        if "\n" in value or len(value) > 50:
            return (
                Stripped(
                    f"""\
return (
{I}{indent_but_first_line(value, I)}
);"""
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

    @staticmethod
    def _block(stmts: Sequence[Stripped]) -> Stripped:
        """Enclose the ``stmts`` in a block."""
        if len(stmts) == 0:
            return Stripped("{}")

        body = "\n".join(stmts)
        return Stripped(
            f"""\
{{
{I}{indent_but_first_line(body, I)}
}}"""
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_switch_as_if_chain(
        self, node: parse_tree.Switch, subject: Stripped
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``node`` as a chain of ``if``, ``else if`` and ``else``.

        We need this for the subjects which C++ can not switch on, namely strings.
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

        errors = []  # type: List[Error]
        writer = io.StringIO()

        for i, case in enumerate(node.cases):
            comparisons = []  # type: List[str]
            for label in case.labels:
                label_code, error = self.transform(label)
                if error is not None:
                    errors.append(error)
                    continue

                assert label_code is not None
                comparisons.append(f"{subject} == {label_code}")

            stmts_and_defines, error = self._transform_branch(case.body)
            if error is not None:
                errors.append(error)
                continue

            assert stmts_and_defines is not None
            body = Transpiler._block(stmts_and_defines[0])

            condition = " || ".join(comparisons)
            if i == 0:
                writer.write(f"if ({condition}) {body}")
            else:
                writer.write(f" else if ({condition}) {body}")

        if node.default is not None:
            stmts_and_defines, error = self._transform_branch(node.default)
            if error is not None:
                errors.append(error)
            else:
                assert stmts_and_defines is not None
                writer.write(f" else {Transpiler._block(stmts_and_defines[0])}")

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the switch", errors
            )

        return Stripped(writer.getvalue()), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_switch(
        self, node: parse_tree.Switch
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        subject, error = self._transform_and_value_if_necessary(node.subject)
        if error is not None:
            return None, error

        assert subject is not None

        subject_type = self.type_map[node.subject]
        primitive_type = intermediate_type_inference.try_primitive_type(subject_type)

        # NOTE (mristin):
        # C++ can not switch on strings.
        if primitive_type is intermediate_type_inference.PrimitiveType.STR:
            return self._transform_switch_as_if_chain(node=node, subject=subject)

        errors = []  # type: List[Error]

        # NOTE (mristin):
        # We collect the headers of the clauses together with their statements, and
        # treat the default as the last clause.
        clauses = []  # type: List[Tuple[str, Sequence[parse_tree.StatementUnion]]]

        for case in node.cases:
            headers = []  # type: List[str]
            for label in case.labels:
                if isinstance(label, parse_tree.Constant):
                    # NOTE (mristin):
                    # We render the integers directly as the constants are otherwise
                    # rendered as floating-point literals.
                    assert isinstance(label.value, int) and not isinstance(
                        label.value, bool
                    )
                    headers.append(f"case {label.value}:")
                else:
                    label_code, error = self.transform(label)
                    if error is not None:
                        errors.append(error)
                        continue

                    assert label_code is not None
                    headers.append(f"case {label_code}:")

            clauses.append(("\n".join(headers), case.body))

        if node.default is not None:
            clauses.append(("default:", node.default))
        elif primitive_type is None:
            # NOTE (mristin):
            # We add an explicit default to the switches over enumerations to
            # signal that the missing literals are intentional, and silence
            # the ``-Wswitch`` warning.
            clauses.append(("default:", []))

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
            # C++ falls through, so we end the clause with a ``break`` if its
            # execution can complete.
            if parse_tree.can_complete_normally(statements):
                stmts = stmts + [Stripped("break;")]

            writer.write("\n")
            writer.write(textwrap.indent(header, I))

            # NOTE (mristin):
            # We enclose the statements in a block only if they define variables as
            # C++ does not allow to jump over the initialization of a variable.
            if defines_variables:
                writer.write(" ")
                writer.write(indent_but_first_line(Transpiler._block(stmts), I))
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


# noinspection PyProtectedMember,PyProtectedMember
assert all(op in Transpiler._CPP_COMPARISON_MAP for op in parse_tree.Comparator)
