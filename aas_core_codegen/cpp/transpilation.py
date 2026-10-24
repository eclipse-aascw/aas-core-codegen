"""Transpile meta-model Python code to C++ code."""
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
    aliasing as cpp_aliasing,
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
        elif type_annotation.a_type in (
            intermediate_type_inference.PrimitiveType.INT,
            intermediate_type_inference.PrimitiveType.LENGTH,
        ):
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
                return Stripped(f"std::shared_ptr<{interface_name}>"), None

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
        item_types: List[Stripped] = []
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

    elif isinstance(type_annotation, intermediate_type_inference.SetTypeAnnotation):
        item_type, error_msg = generate_type(
            type_annotation=type_annotation.items, types_namespace=types_namespace
        )

        if error_msg is not None:
            return None, error_msg

        assert item_type is not None

        items_are_enumeration_literals = isinstance(
            type_annotation.items, intermediate_type_inference.OurTypeAnnotation
        ) and isinstance(type_annotation.items.our_type, intermediate.Enumeration)

        return (
            cpp_common.generate_set_type(
                item_type=item_type,
                items_are_enumeration_literals=items_are_enumeration_literals,
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

    elif isinstance(type_annotation, intermediate_type_inference.SetTypeAnnotation):
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


_ARITHMETIC_PRIMITIVE_TYPES = (
    intermediate_type_inference.PrimitiveType.BOOL,
    intermediate_type_inference.PrimitiveType.INT,
    intermediate_type_inference.PrimitiveType.FLOAT,
    intermediate_type_inference.PrimitiveType.LENGTH,
)


def _is_cheap_to_copy(
    type_annotation: intermediate_type_inference.TypeAnnotationUnion,
) -> bool:
    """Check whether the value is arithmetic or an enumeration literal."""
    if isinstance(type_annotation, intermediate_type_inference.PrimitiveTypeAnnotation):
        return type_annotation.a_type in _ARITHMETIC_PRIMITIVE_TYPES

    if isinstance(type_annotation, intermediate_type_inference.OurTypeAnnotation):
        our_type = type_annotation.our_type
        if isinstance(our_type, intermediate.Enumeration):
            return True

        if isinstance(our_type, intermediate.ConstrainedPrimitive):
            return our_type.constrainee in (
                intermediate.PrimitiveType.BOOL,
                intermediate.PrimitiveType.INT,
                intermediate.PrimitiveType.FLOAT,
            )

    return False


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

    _CPP_COMPARISON_MAP: Final[Mapping[parse_tree.Comparator, str]] = {
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
        aliasing: Optional[cpp_aliasing.Aliasing] = None,
    ) -> None:
        """
        Initialize with the given values.

        The ``downcast_map`` comes from the type inference, while
        the ``is_optional_map`` and the ``is_optional_before_downcast_map`` come
        from :py:class:`aas_core_codegen.cpp.optionaling.Inferrer`.

        If ``types_namespace`` is specified, it is prepended to all our types.

        The ``aliasing`` specifies how to declare the variables. If not specified,
        we declare them by default, as there are no assignments in the invariants.
        """
        self._aliasing = aliasing
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
        self._variable_name_set: Set[Identifier] = set()

    def _type_parameter_of(
        self, type_annotation: intermediate_type_inference.TypeAnnotationUnion
    ) -> Optional[Identifier]:
        """
        Determine the template parameter which stands for the ``type_annotation``.

        Only the verification functions are templates, namely over the items of
        the generic sequences, see :py:func:`intermediate.generic_sequence_item_class`.
        The transpiler of the verification functions overrides this method.

        We declare the loop and the generator variables over a generic sequence with
        the template parameter so that the items are not converted to
        temporary shared pointers of the parent class.

        :param type_annotation: inferred type of a value
        :return:
            the template parameter, if the value is an item of a generic sequence,
            and None otherwise
        """
        return None

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
            # NOTE (mristin):
            # We always parenthesize the de-referenced value, since the postfix
            # operators bind stronger than ``*``. For example, ``*item->name()``
            # would access the member on the optional itself.
            no_parentheses_types = (
                parse_tree.FunctionCall,
                parse_tree.Name,
                parse_tree.Constant,
            )
            if isinstance(node, no_parentheses_types):
                return Stripped(f"(*{code})"), None

            return Stripped(f"(*({code}))"), None

        return code, None

    def _declaration(self, definition: parse_tree.Node) -> cpp_aliasing.Declaration:
        """Look up how to declare the variable defined at ``definition``."""
        if self._aliasing is None:
            return cpp_aliasing.Declaration.DEFAULT

        return self._aliasing.declaration_by_definition.get(
            definition, cpp_aliasing.Declaration.DEFAULT
        )

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_item_access(
        self, collection: Stripped, index_node: parse_tree.Expression
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """Access the item of the list ``collection`` at ``index_node``."""
        index, error = self._transform_and_value_if_necessary(index_node)
        if error is not None:
            return None, error
        assert index is not None

        index_as_int: Optional[int] = None
        try:
            index_as_int = int(index)
        except ValueError:
            pass

        if index_as_int is not None and index_as_int == -1:
            return Stripped(f"{collection}.back()"), None

        if index_as_int is not None and index_as_int < -1:
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
    def _transform_mutable_path(
        self, node: parse_tree.Expression, dereference: bool
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the access path ``node`` so that it can be mutated in place.

        We access the properties with the mutable getters, and the items of the lists
        on their mutable containers. If ``dereference`` is set, we dereference
        the ``common::optional`` at the end of the path.
        """
        code: Optional[Stripped]

        if isinstance(node, parse_tree.Name):
            code, error = self.transform_name(node)
            if error is not None:
                return None, error

        elif isinstance(node, parse_tree.Member):
            # NOTE (mristin):
            # The instance is a shared pointer, which gives us a mutable instance
            # even if it is held as a constant.
            instance, error = self._transform_and_value_if_necessary(node.instance)
            if error is not None:
                return None, error

            code = Stripped(
                f"{instance}->{cpp_naming.mutable_getter_name(node.name)}()"
            )

        elif isinstance(node, parse_tree.Index):
            collection, error = self._transform_mutable_path(
                node.collection, dereference=True
            )
            if error is not None:
                return None, error
            assert collection is not None

            collection_type = intermediate_type_inference.beneath_optional(
                self.type_map[node.collection]
            )
            if isinstance(
                collection_type, intermediate_type_inference.TupleTypeAnnotation
            ):
                assert isinstance(node.index, parse_tree.Constant) and isinstance(
                    node.index.value, int
                )

                index_value = node.index.value
                if index_value < 0:
                    index_value += len(collection_type.items)

                code = Stripped(f"std::get<{index_value}>({collection})")
            else:
                code, error = self._transform_item_access(
                    collection=collection, index_node=node.index
                )
                if error is not None:
                    return None, error

        else:
            return None, Error(
                node.original_node,
                f"Expected a variable, a property or an item of a list as a path "
                f"to be mutated, but got: {parse_tree.dump(node)}; this should have "
                f"been caught in the type inference.",
            )

        assert code is not None

        if dereference and self.is_optional_map[node]:
            return Stripped(f"(*{code})"), None

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

        assert collection is not None

        if isinstance(
            intermediate_type_inference.beneath_optional(collection_type),
            intermediate_type_inference.JsonObjectTypeAnnotation,
        ):
            index, error = self._transform_and_value_if_necessary(node.index)
            if error is not None:
                return None, error
            assert index is not None

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

        return self._transform_item_access(collection=collection, index_node=node.index)

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_tuple(
        self, node: parse_tree.Tuple
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        value_reprs: List[Stripped] = []

        for value_node in node.values:
            value_repr, error = self._transform_and_value_if_necessary(value_node)
            if error is not None:
                errors.append(error)
                continue

            assert value_repr is not None

            if self._aliasing is not None and value_node in self._aliasing.moved_set:
                value_repr = Stripped(f"std::move({value_repr})")

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
    def transform_list_literal(
        self, node: parse_tree.ListLiteral
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        items: List[Stripped] = []

        for item_node in node.items:
            item, error = self._transform_and_value_if_necessary(item_node)
            if error is not None:
                errors.append(error)
                continue

            assert item is not None

            # NOTE (mristin):
            # The lengths are ``size_t``'s, which an initializer list of our
            # integers does not accept, as it would be a narrowing conversion.
            items.append(self._as_int64_position(item_node, item))

        list_type, error_msg = generate_type(
            self.type_map[node], types_namespace=self._types_namespace
        )
        if error_msg is not None:
            errors.append(Error(node.original_node, error_msg))

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the list literal", errors
            )

        assert list_type is not None

        if len(items) == 0:
            return Stripped(f"{list_type}()"), None

        one_liner = f"{list_type}{{{', '.join(items)}}}"
        if "\n" not in one_liner and len(one_liner) <= 60:
            return Stripped(one_liner), None

        items_joined = ",\n".join(items)
        return (
            Stripped(
                f"""\
{list_type}{{
{I}{indent_but_first_line(items_joined, I)}
}}"""
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

        # NOTE (mristin):
        # The operators ``<``, ``<=``, ``>`` and ``>=`` order ``std::wstring``'s by
        # their ``wchar_t``'s, which are UTF-16 code units on Windows, while Python
        # orders the strings by their characters (code points). Hence, we order
        # the strings with our helpers on all the platforms. The booleans are ordered
        # natively, where ``false`` comes before ``true`` as in Python.
        if node.op not in (parse_tree.Comparator.EQ, parse_tree.Comparator.NE,) and (
            intermediate_type_inference.try_primitive_type(self.type_map[node.left])
            is intermediate_type_inference.PrimitiveType.STR
        ):
            return (
                Stripped(
                    f"{cpp_common.COMMON_NAMESPACE}::CompareByCodePoints("
                    f"{left}, {right}) {comparator} 0"
                ),
                None,
            )

        # NOTE (mristin):
        # The modulo is transpiled either to a function call or to the native
        # operator ``%``, and the arithmetic negation to the unary ``-``. Both bind
        # stronger than the comparison operators in C++.
        no_parentheses_types = (
            parse_tree.Member,
            parse_tree.FunctionCall,
            parse_tree.MethodCall,
            parse_tree.Name,
            parse_tree.Constant,
            parse_tree.Index,
            parse_tree.Slice,
            parse_tree.Mod,
            parse_tree.Neg,
        )

        left_needs_no_parentheses = isinstance(node.left, no_parentheses_types)
        right_needs_no_parentheses = isinstance(node.right, no_parentheses_types)

        # NOTE (mristin):
        # The lengths are unsigned ``size_t``'s in C++, while the other integers are
        # ``int64_t``'s. C++ would compare the two as unsigned, so that a negative
        # integer compares larger than a length. Hence, we widen the length if it is
        # compared against an integer which is not a literal.
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
            left = Stripped(f"static_cast<int64_t>({left})")
            left_needs_no_parentheses = True

        elif (
            right_a_type is length
            and left_a_type is integer
            and not isinstance(node.left, parse_tree.Constant)
        ):
            right = Stripped(f"static_cast<int64_t>({right})")
            right_needs_no_parentheses = True

        if left_needs_no_parentheses and right_needs_no_parentheses:
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

        # NOTE (mristin):
        # The membership in a string is a check for a sub-string, while
        # ``common::Contains`` would look for a single character.
        if (
            intermediate_type_inference.try_primitive_type(container_type)
            is intermediate_type_inference.PrimitiveType.STR
        ):
            if not isinstance(node.container, parse_tree.Name):
                container = Stripped(f"({container})")

            one_liner = f"{container}.find({member}) != std::wstring::npos"
            if "\n" not in one_liner and len(one_liner) <= 60:
                return Stripped(one_liner), None

            return (
                Stripped(
                    f"""\
{container}.find(
{I}{indent_but_first_line(member, I)}
) != std::wstring::npos"""
                ),
                None,
            )

        # NOTE (mristin):
        # We look up the member in a set in constant time, while
        # ``common::Contains`` iterates over all the items.
        if isinstance(container_type, intermediate_type_inference.SetTypeAnnotation):
            member = self._as_int64_position(node.member, member)

            if not isinstance(node.container, parse_tree.Name):
                container = Stripped(f"({container})")

            one_liner = f"{container}.find({member}) != {container}.end()"
            if "\n" not in one_liner and len(one_liner) <= 60:
                return Stripped(one_liner), None

            return (
                Stripped(
                    f"""\
{container}.find(
{I}{indent_but_first_line(member, I)}
) != {container}.end()"""
                ),
                None,
            )

        # NOTE (mristin):
        # The lengths are ``size_t``'s, so we convert them to our integers to avoid
        # comparing the signed and the unsigned integers in ``std::find``.
        if isinstance(container_type, intermediate_type_inference.ListTypeAnnotation):
            member = self._as_int64_position(node.member, member)

        # NOTE (mristin):
        # The ``std::find`` compares the shared pointers by their raw pointers, so
        # the classes of the items and of the member need to be related. This holds
        # for the declared classes, as the type inference checks that one is
        # a subclass of the other. However, the template parameter of a generic
        # sequence, see :py:func:`intermediate.generic_sequence_item_class`, can be
        # any descendant, *e.g.*, a sibling of the class of the member. Hence, we
        # convert the member to the more general of the two declared classes.
        member_type = self.type_map[node.member]
        if (
            isinstance(container_type, intermediate_type_inference.ListTypeAnnotation)
            and isinstance(
                container_type.items, intermediate_type_inference.OurTypeAnnotation
            )
            and isinstance(container_type.items.our_type, intermediate.Class)
            and isinstance(member_type, intermediate_type_inference.OurTypeAnnotation)
            and isinstance(member_type.our_type, intermediate.Class)
            and (
                self._type_parameter_of(container_type.items) is not None
                or self._type_parameter_of(member_type) is not None
            )
        ):
            general_type = (
                container_type.items
                if member_type.our_type.is_subclass_of(container_type.items.our_type)
                else member_type
            )

            general_type_cpp, error_msg = generate_type(
                type_annotation=intermediate_type_inference.OurTypeAnnotation(
                    our_type=general_type.our_type
                ),
                types_namespace=self._types_namespace,
            )
            if error_msg is not None:
                return None, Error(node.member.original_node, error_msg)

            assert general_type_cpp is not None

            member = Stripped(
                f"""\
{general_type_cpp}(
{I}{indent_but_first_line(member, I)}
)"""
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

        checks: List[Stripped] = []
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

    def _is_set_membership(self, node: parse_tree.Node) -> bool:
        """
        Check whether ``node`` is a membership in a set.

        We transpile it as a comparison, ``find(...) != end()``, so it needs
        parentheses under a negation, unlike the other memberships, which we
        transpile as function calls.
        """
        return isinstance(node, parse_tree.IsIn) and isinstance(
            self.type_map[node.container],
            intermediate_type_inference.SetTypeAnnotation,
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

        if isinstance(
            node.antecedent, no_parentheses_types_in_this_context
        ) and not self._is_set_membership(node.antecedent):
            not_antecedent = f"!{antecedent}"
        else:
            not_antecedent = f"!({antecedent})"

        if not isinstance(node.consequent, no_parentheses_types_in_this_context):
            consequent = Stripped(f"({consequent})")

        return Stripped(f"{not_antecedent}\n|| {consequent}"), None

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_slice(
        self, node: parse_tree.Slice
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        collection, error = self._transform_and_value_if_necessary(node.collection)
        if error is not None:
            errors.append(error)

        start: Optional[Stripped] = None
        if node.start is not None:
            start, error = self._transform_and_value_if_necessary(node.start)
            if error is not None:
                errors.append(error)

        end: Optional[Stripped] = None
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
        # We do not use the native ``substr`` as it counts the UTF-16 code units
        # instead of the characters on Windows, throws on a start out of range,
        # and does not count the negative positions from the end, unlike Python.
        # See ``SliceStr`` in the generated common module.
        args: List[str] = [collection, start if start is not None else "0"]
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
        errors: List[Error] = []

        instance, error = self._transform_and_value_if_necessary(node.member.instance)
        if error is not None:
            errors.append(error)

        args: List[Stripped] = []
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

        kind = method.kind

        if kind is intermediate_type_inference.BuiltinMethodKind.STR_FIND:
            # NOTE (mristin):
            # We do not use the native ``find`` as it counts the UTF-16 code units
            # instead of the characters on Windows, gives ``npos`` instead of -1,
            # and does not count a negative start from the end, unlike Python. See
            # ``FindStr`` in the generated common module.
            if len(args) == 2:
                args[1] = self._as_int64_position(node.args[1], args[1])

            return (
                Stripped(f"common::FindStr({', '.join([instance] + args)})"),
                None,
            )

        elif kind is intermediate_type_inference.BuiltinMethodKind.STR_LSTRIP:
            # NOTE (mristin):
            # We do not use the native ``find_first_not_of`` as it strips
            # the UTF-16 code units instead of the characters on Windows, unlike
            # Python. See ``LStrip`` in the generated common module.
            return (
                Stripped(f"common::LStrip({instance}, {args[0]})"),
                None,
            )

        elif kind is intermediate_type_inference.BuiltinMethodKind.STR_RSTRIP:
            # NOTE (mristin):
            # We do not use the native ``find_last_not_of`` as it strips
            # the UTF-16 code units instead of the characters on Windows, unlike
            # Python. See ``RStrip`` in the generated common module.
            return (
                Stripped(f"common::RStrip({instance}, {args[0]})"),
                None,
            )

        elif kind is intermediate_type_inference.BuiltinMethodKind.STR_STARTSWITH:
            # NOTE (mristin):
            # C++11 has no native ``starts_with``. See ``StartsWith`` in
            # the generated common module.
            return (
                Stripped(f"common::StartsWith({instance}, {args[0]})"),
                None,
            )

        elif kind is intermediate_type_inference.BuiltinMethodKind.STR_ENDSWITH:
            # NOTE (mristin):
            # C++11 has no native ``ends_with``. See ``EndsWith`` in
            # the generated common module.
            return (
                Stripped(f"common::EndsWith({instance}, {args[0]})"),
                None,
            )

        elif kind is intermediate_type_inference.BuiltinMethodKind.SET_ADD:
            # NOTE (mristin):
            # The lengths are ``size_t``'s, so we convert them to our integers.
            item = self._as_int64_position(node.args[0], args[0])

            if not isinstance(node.member.instance, parse_tree.Name):
                instance = Stripped(f"({instance})")

            return Stripped(f"{instance}.insert({item})"), None

        elif kind is intermediate_type_inference.BuiltinMethodKind.LIST_APPEND:
            # NOTE (mristin):
            # The type inference allows ``append`` only on a local variable.
            assert isinstance(node.member.instance, parse_tree.Name)

            # NOTE (mristin):
            # The lengths are ``size_t``'s, so we convert them to our integers.
            item = self._as_int64_position(node.args[0], args[0])

            return Stripped(f"{instance}.push_back({item})"), None

        elif (
            kind is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION
            or kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE
        ):
            # NOTE (mristin):
            # See ``Intersection`` and ``Difference`` in the generated common
            # module, which give a new set as Python does.
            function_name: str
            if kind is intermediate_type_inference.BuiltinMethodKind.SET_INTERSECTION:
                function_name = "Intersection"
            elif kind is intermediate_type_inference.BuiltinMethodKind.SET_DIFFERENCE:
                function_name = "Difference"
            else:
                assert_never(kind)

            return (
                Stripped(
                    f"""\
common::{function_name}(
{I}{indent_but_first_line(instance, I)},
{I}{indent_but_first_line(args[0], I)}
)"""
                ),
                None,
            )

        else:
            assert_never(kind)

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _transform_call_arguments(
        self,
        arg_nodes: Sequence[parse_tree.Expression],
        arguments: Sequence[intermediate.Argument],
    ) -> Tuple[Optional[List[Stripped]], Optional[List[Error]]]:
        """
        Transpile the ``arg_nodes`` passed to a function or a method call.

        The ``arguments`` are the arguments of the called verification function or
        of our method, which we need to pass the mutable lists by reference. They are
        empty for the built-in functions and methods.
        """
        mutable_arg_set: Set[parse_tree.Expression] = set()
        for arg_node, argument in zip(arg_nodes, arguments, strict=False):
            if argument.mutable and isinstance(
                intermediate_type_inference.beneath_optional(self.type_map[arg_node]),
                (
                    intermediate_type_inference.ListTypeAnnotation,
                    intermediate_type_inference.SetTypeAnnotation,
                ),
            ):
                mutable_arg_set.add(arg_node)

        errors: List[Error] = []
        args: List[Stripped] = []
        for arg_node in arg_nodes:
            arg_type = self.type_map[arg_node]

            # NOTE (mristin):
            # This is a tough call to make. We decide that a value, for which we
            # know that it might be null, will not be de-referenced. On the other
            # hand, if the value is certainly not null, we de-reference it.
            #
            # The problem here is that the actual type of the argument in C++ changes
            # depending on whether we check for its nullness before with an implication.
            arg: Optional[Stripped]
            error: Optional[Error]
            if arg_node in mutable_arg_set:
                # NOTE (mristin):
                # The mutable lists are passed in as mutable references, so we
                # need a mutable path to them.
                arg, error = self._transform_mutable_path(
                    arg_node,
                    dereference=not isinstance(
                        arg_type, intermediate_type_inference.OptionalTypeAnnotation
                    ),
                )
            elif isinstance(
                arg_type, intermediate_type_inference.OptionalTypeAnnotation
            ):
                arg, error = self.transform(arg_node)
            else:
                arg, error = self._transform_and_value_if_necessary(arg_node)

            if error is not None:
                errors.append(error)
                continue

            assert arg is not None
            args.append(arg)

        if len(errors) > 0:
            return None, errors

        return args, None

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

        errors: List[Error] = []

        member_access, error = self._transform_and_value_if_necessary(node.member)
        if error is not None:
            errors.append(error)

        args, args_errors = self._transform_call_arguments(
            arg_nodes=node.args,
            arguments=(
                member_type.method.arguments
                if isinstance(
                    member_type, intermediate_type_inference.MethodTypeAnnotation
                )
                else []
            ),
        )
        if args_errors is not None:
            errors.extend(args_errors)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the method call", errors
            )

        assert args is not None

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
        errors: List[Error] = []

        func_type = self.type_map[node.name]

        args, args_errors = self._transform_call_arguments(
            arg_nodes=node.args,
            arguments=(
                func_type.func.arguments
                if isinstance(
                    func_type, intermediate_type_inference.VerificationTypeAnnotation
                )
                else []
            ),
        )
        if args_errors is not None:
            errors.extend(args_errors)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the function call", errors
            )

        assert args is not None

        # NOTE (mristin):
        # The validity of the arguments is checked in
        # :py:func:`aas_core_codegen.intermediate._translate.translate`, so we do not
        # have to test for argument arity here.

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

            # NOTE (mristin):
            # A transpiled verification function is a template over the items of
            # its generic sequences, see
            # :py:func:`intermediate.generic_sequence_item_class`. C++ deduces
            # the template parameters without any implicit conversions, so we pass
            # ``None`` to an optional generic sequence as a typed empty optional,
            # and a required vector through ``common::make_optional``.
            if isinstance(func_type.func, intermediate.TranspilableVerification):
                for i, (arg_node, argument) in enumerate(
                    zip(node.args, func_type.func.arguments, strict=False)
                ):
                    if intermediate.generic_sequence_item_class(argument) is None:
                        continue

                    if not isinstance(
                        argument.type_annotation, intermediate.OptionalTypeAnnotation
                    ):
                        continue

                    if (
                        isinstance(arg_node, parse_tree.Constant)
                        and arg_node.value is None
                    ):
                        optional_type = cpp_common.generate_type(
                            type_annotation=argument.type_annotation,
                            types_namespace=self._types_namespace,
                        )
                        args[i] = Stripped(f"{optional_type}()")

                    elif not isinstance(
                        self.type_map[arg_node],
                        intermediate_type_inference.OptionalTypeAnnotation,
                    ):
                        args[i] = Stripped(
                            f"""\
common::make_optional(
{I}{indent_but_first_line(args[i], I)}
)"""
                        )

                    else:
                        pass

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
            if (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.LEN
            ):
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

                if isinstance(
                    self.type_map[node.args[0]],
                    intermediate_type_inference.TupleTypeAnnotation,
                ):
                    return Stripped(f"common::LenTuple({first_arg})"), None

                # NOTE (mristin):
                # We do not use the native ``size()`` on strings as it counts
                # the UTF-16 code units instead of the characters on Windows,
                # unlike Python. See ``LenStr`` in the generated common module.
                if (
                    intermediate_type_inference.try_primitive_type(
                        intermediate_type_inference.beneath_optional(
                            self.type_map[node.args[0]]
                        )
                    )
                    is intermediate_type_inference.PrimitiveType.STR
                ):
                    return Stripped(f"common::LenStr({first_arg})"), None

                if not isinstance(node.args[0], no_parentheses_types_in_this_context):
                    first_arg = Stripped(f"({first_arg})")

                return Stripped(f"{first_arg}.size()"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.ABS
            ):
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                # NOTE (mristin):
                # The argument is never optional here as the type inference refuses
                # the optional arguments, so it has been already de-referenced above
                # if it had been a narrowed ``common::optional``.
                #
                # The overloads of ``std::abs`` for ``int64_t`` live in ``<cstdlib>``,
                # while the overloads for ``double`` live in ``<cmath>``. We include
                # both in the verification.
                return Stripped(f"std::abs({args[0]})"), None

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.INT
            ):
                assert len(args) == 1, (
                    f"Expected exactly one argument, but got: {args}; "
                    f"this should have been caught before."
                )

                # NOTE (mristin):
                # We do not use the native ``std::stoll`` as it skips the leading
                # white space, ignores the trailing garbage and depends on
                # the locale. See ``ParseSafeInt`` in the generated common module.
                # We qualify the helper with the namespace as the invariants are
                # transpiled in the anonymous namespace.
                return (
                    Stripped(f"{cpp_common.COMMON_NAMESPACE}::ParseSafeInt({args[0]})"),
                    None,
                )

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.LIST
            ):
                assert len(node.args) == 1, (
                    f"Expected exactly one argument, but got: {node.args}; "
                    f"this should have been caught before."
                )

                the_list, error = self._transform_and_value_if_necessary(node.args[0])
                if error is not None:
                    return None, Error(
                        node.original_node,
                        "Failed to transpile the argument of list",
                        [error],
                    )

                assert the_list is not None

                # NOTE (mristin):
                # The type inference allows ``list(...)`` only to copy a list,
                # which we transpile as an explicit copy of the vector.
                list_type, error_msg = generate_type(
                    type_annotation=self.type_map[node],
                    types_namespace=self._types_namespace,
                )
                if error_msg is not None:
                    return None, Error(node.original_node, error_msg)

                assert list_type is not None
                return (
                    _generate_call_with_single_argument(
                        function=list_type, argument=the_list
                    ),
                    None,
                )

            elif (
                func_type.func.kind
                is intermediate_type_inference.BuiltinFunctionKind.SET
            ):
                set_type, error_msg = generate_type(
                    self.type_map[node], types_namespace=self._types_namespace
                )
                if error_msg is not None:
                    return None, Error(node.original_node, error_msg)

                assert set_type is not None
                return Stripped(f"{set_type}()"), None

            else:
                assert_never(func_type.func.kind)
        else:
            assert_never(func_type)

        raise AssertionError("Should not have gotten here")

    def transform_constant(
        self, node: parse_tree.Constant
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.value is None:
            return Stripped("common::nullopt"), None
        elif isinstance(node.value, bool):
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
        raise NotImplementedError

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
        if not isinstance(
            node.operand, no_parentheses_types_in_this_context
        ) or self._is_set_membership(node.operand):
            return Stripped(f"!({operand})"), None
        else:
            return Stripped(f"!{operand}"), None

    def _transform_and_or_or(
        self, node: Union[parse_tree.And, parse_tree.Or]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []
        values: List[Stripped] = []

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
        errors: List[Error] = []

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

        if (
            isinstance(node, parse_tree.Add)
            and intermediate_type_inference.try_primitive_type(self.type_map[node])
            is intermediate_type_inference.PrimitiveType.STR
        ):
            # NOTE (mristin):
            # C++ can not add two string literals, as they are pointers, so we
            # convert the left one to ``std::wstring``. A single literal can be
            # added to a ``std::wstring`` natively.
            if isinstance(node.left, parse_tree.Constant) and isinstance(
                node.right, parse_tree.Constant
            ):
                left = Stripped(f"std::wstring({left})")
            elif not isinstance(
                node.left, (parse_tree.Constant, *no_parentheses_types_in_this_context)
            ):
                left = Stripped(f"({left})")

            if not isinstance(
                node.right, (parse_tree.Constant, *no_parentheses_types_in_this_context)
            ):
                right = Stripped(f"({right})")

            return Stripped(f"{left} + {right}"), None

        # NOTE (mristin):
        # The lengths are unsigned ``size_t``'s in C++, while the other integers are
        # ``int64_t``'s. C++ would compute the mix of the two as unsigned, so that
        # a negative result would wrap around. If a length is combined with
        # an integer which is not a literal, the result is an integer, see
        # :py:func:`aas_core_codegen.intermediate.type_inference._combines_to_length`,
        # so we widen the length to ``int64_t``.
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
            left = Stripped(f"static_cast<int64_t>({left})")
        elif not isinstance(node.left, no_parentheses_types_in_this_context):
            left = Stripped(f"({left})")

        if (
            is_integer
            and intermediate_type_inference.try_primitive_type(
                self.type_map[node.right]
            )
            is length
        ):
            right = Stripped(f"static_cast<int64_t>({right})")
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

    def _is_non_negative_in_cpp(self, node: parse_tree.Expression) -> bool:
        """
        Check that the ``node`` is certainly non-negative in the generated C++ code.

        This is the case for the lengths, which we represent as unsigned ``size_t``,
        and for the non-negative integer literals.
        """
        if (
            isinstance(node, parse_tree.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
        ):
            return node.value >= 0

        return (
            intermediate_type_inference.try_primitive_type(self.type_map[node])
            is intermediate_type_inference.PrimitiveType.LENGTH
        )

    def transform_mod(
        self, node: parse_tree.Mod
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        left, error = self._transform_and_value_if_necessary(node.left)
        if error is not None:
            errors.append(error)

        right, error = self._transform_and_value_if_necessary(node.right)
        if error is not None:
            errors.append(error)

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the modulo operation", errors
            )

        assert left is not None
        assert right is not None

        result_type = intermediate_type_inference.try_primitive_type(
            self.type_map[node]
        )
        assert result_type in (
            intermediate_type_inference.PrimitiveType.INT,
            intermediate_type_inference.PrimitiveType.LENGTH,
        ), (
            f"Expected the modulo to be only defined on integers, "
            f"but got the result type {self.type_map[node]}; "
            f"this should have been caught before."
        )

        if (
            result_type is intermediate_type_inference.PrimitiveType.LENGTH
            and self._is_non_negative_in_cpp(node.left)
            and self._is_non_negative_in_cpp(node.right)
        ):
            # NOTE (mristin):
            # The native operator ``%`` is safe here. Both operands are non-negative:
            # the lengths are unsigned ``size_t``'s, and the literals are
            # non-negative. The truncated and the floored division coincide
            # for non-negative operands, so the native remainder equals the remainder
            # in Python. See below why we can not use the native operator in general.
            no_parentheses_types_in_this_context = (
                parse_tree.Member,
                parse_tree.FunctionCall,
                parse_tree.MethodCall,
                parse_tree.Name,
                parse_tree.Constant,
                parse_tree.Index,
            )

            if not isinstance(node.left, no_parentheses_types_in_this_context):
                left = Stripped(f"({left})")

            if not isinstance(node.right, no_parentheses_types_in_this_context):
                right = Stripped(f"({right})")

            return Stripped(f"{left} % {right}"), None

        # NOTE (mristin):
        # We deliberately do not use the native C++ operator ``%`` for the signed
        # operands. C++ truncates the division towards zero so that its remainder
        # takes the sign of the dividend (``-7 % 3 == -1``). The meta-model is
        # written in Python where the division is floored so that the remainder takes
        # the sign of the divisor (``-7 % 3 == 2``). The two only coincide for
        # the operands of the same sign, but the invariants must behave the same in
        # all the SDKs for all the inputs. Hence, we call the helper which computes
        # the floored remainder, see
        # :py:data:`aas_core_codegen.cpp.lib._generate_common.FLOOR_MOD_DEFINITION`.
        #
        # The helper works on ``int64_t``'s, so we convert the lengths, which are
        # unsigned ``size_t``'s in C++. If the meta-model expects a length as
        # the result, we convert the result back to ``size_t`` so that the comparisons
        # with other lengths do not trigger the warnings about the signed/unsigned
        # mismatch.
        if (
            intermediate_type_inference.try_primitive_type(self.type_map[node.left])
            is intermediate_type_inference.PrimitiveType.LENGTH
        ):
            left = Stripped(f"static_cast<int64_t>({left})")

        if (
            intermediate_type_inference.try_primitive_type(self.type_map[node.right])
            is intermediate_type_inference.PrimitiveType.LENGTH
        ):
            right = Stripped(f"static_cast<int64_t>({right})")

        # NOTE (mristin):
        # We qualify the helper with the namespace as the invariants are transpiled
        # in the anonymous namespace.
        function = f"{cpp_common.COMMON_NAMESPACE}::FloorMod"

        call = Stripped(f"{function}({left}, {right})")
        if "\n" in call or len(call) > 70:
            call = Stripped(
                f"""\
{function}(
{I}{indent_but_first_line(left, I)},
{I}{indent_but_first_line(right, I)}
)"""
            )

        if result_type is intermediate_type_inference.PrimitiveType.LENGTH:
            if "\n" in call:
                return (
                    Stripped(
                        f"""\
static_cast<size_t>(
{I}{indent_but_first_line(call, I)}
)"""
                    ),
                    None,
                )

            return Stripped(f"static_cast<size_t>({call})"), None

        return call, None

    def transform_neg(
        self, node: parse_tree.Neg
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        operand, error = self._transform_and_value_if_necessary(node.operand)
        if error is not None:
            return None, Error(
                node.original_node,
                "Failed to transpile the arithmetic negation",
                [error],
            )

        assert operand is not None

        # NOTE (mristin):
        # We have to put a negative constant in parentheses as well, since ``--1``
        # would be parsed as a decrement in C++.
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
        if all(isinstance(value, str) for value in node.values):
            text = "".join(node.values)  # type: ignore
            return cpp_common.wstring_literal(text), None

        # NOTE (mristin):
        # We need the interpolation if we got so far.

        args: List[str] = []

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
        errors: List[Error] = []

        iteration: Optional[Stripped] = None
        start: Optional[Stripped] = None
        end: Optional[Stripped] = None

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

        # NOTE (mristin):
        # The aliasing analysis refuses the loop variables which need to be
        # mutable, as we would need to pass them to the lambda as mutable references.
        assert self._declaration(node.generator) is not (
            cpp_aliasing.Declaration.MUT_REF
        )

        type_parameter = self._type_parameter_of(variable_type_annotation)

        variable_type_cpp: Optional[Stripped]
        error_msg: Optional[str]
        if type_parameter is not None:
            variable_type_cpp = Stripped(f"std::shared_ptr<{type_parameter}>")
            error_msg = None

            if self._declaration(node.generator) is not cpp_aliasing.Declaration.COPY:
                variable_type_cpp = Stripped(f"const {variable_type_cpp}&")

        elif self._declaration(node.generator) is cpp_aliasing.Declaration.COPY:
            variable_type_cpp, error_msg = generate_type(
                type_annotation=variable_type_annotation,
                types_namespace=self._types_namespace,
            )
        else:
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

            # NOTE (mristin):
            # The helpers are templated on the integer type of the range, which we
            # give explicitly so that the integer literals among the bounds are
            # converted to it.
            return (
                Stripped(
                    f"""\
common::{qualifier_function}<{variable_type_cpp}>(
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
        errors: List[Error] = []

        value_type = self.type_map[node.value]

        is_definition = False

        target: Optional[Stripped] = None
        if isinstance(node.target, parse_tree.Name):
            target_type = self._environment.find(identifier=node.target.identifier)
            if target_type is None:
                # NOTE (mristin):
                # This is a variable definition as we did not specify the identifier
                # in the environment.

                is_definition = True

                # NOTE (mristin):
                # The type inference recorded the type of the variable, which is
                # the declared type if the variable is annotated.
                target_type = self.type_map[node.target]
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
        elif isinstance(node.target, parse_tree.Member):
            # NOTE (mristin):
            # The type inference allows only the properties of a class as member
            # targets, which we set with the setters.
            instance, error = self._transform_and_value_if_necessary(
                node.target.instance
            )
            if error is not None:
                errors.append(error)
            else:
                assert instance is not None
                target = Stripped(
                    f"{instance}->{cpp_naming.setter_name(node.target.name)}"
                )

            target_type = self.type_map[node.target]

        elif isinstance(node.target, parse_tree.Index):
            # NOTE (mristin):
            # The type inference allows only the items of a list as index targets,
            # which we access on the mutable list.
            collection, error = self._transform_mutable_path(
                node.target.collection, dereference=True
            )
            if error is not None:
                errors.append(error)
            else:
                assert collection is not None
                target, error = self._transform_item_access(
                    collection=collection, index_node=node.target.index
                )
                if error is not None:
                    errors.append(error)

            target_type = self.type_map[node.target]

        else:
            return None, Error(
                node.target.original_node,
                f"Unexpected target of the assignment: {parse_tree.dump(node.target)}; "
                f"this should have been caught in the type inference.",
            )

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assignment", errors
            )

        assert target is not None
        assert target_type is not None

        declaration = (
            self._declaration(node)
            if is_definition
            else cpp_aliasing.Declaration.DEFAULT
        )

        value: Optional[Stripped]

        if declaration is cpp_aliasing.Declaration.MUT_REF:
            value, error = self._transform_mutable_path(node.value, dereference=False)
        elif isinstance(
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

        if intermediate_type_inference.needs_wrapping_into_named_union(
            target_type=target_type, value_type=value_type
        ):
            # NOTE (mristin):
            # A named union is a ``common::variant`` over the shared pointers to its
            # roots. We up-cast the instance explicitly to the most specific root so
            # that the alternative of the variant is unambiguous, even if the roots
            # overlap.
            union_type = intermediate_type_inference.beneath_optional(target_type)
            assert isinstance(union_type, intermediate_type_inference.OurTypeAnnotation)
            assert isinstance(union_type.our_type, intermediate.NamedUnion)
            assert isinstance(value_type, intermediate_type_inference.OurTypeAnnotation)
            assert isinstance(value_type.our_type, intermediate.Class)

            root = union_type.our_type.most_specific_root_of(value_type.our_type)

            union_code, error_msg = generate_type(
                type_annotation=union_type, types_namespace=self._types_namespace
            )
            if error_msg is not None:
                return None, Error(node.value.original_node, error_msg)
            assert union_code is not None

            if root is not value_type.our_type:
                interface_name = cpp_naming.interface_name(root.name)
                qualified_interface_name = (
                    interface_name
                    if self._types_namespace is None
                    else f"{self._types_namespace}::{interface_name}"
                )

                value = _generate_call_with_single_argument(
                    function=f"std::static_pointer_cast<{qualified_interface_name}>",
                    argument=value,
                )

            value = _generate_call_with_single_argument(
                function=union_code, argument=value
            )

        if isinstance(node.target, parse_tree.Member):
            # NOTE (mristin):
            # This is a rudimentary heuristic for basic line breaks, but works well
            # in practice.
            if "\n" in value or len(value) > 50:
                return (
                    Stripped(
                        f"""\
{target}(
{I}{indent_but_first_line(value, I)}
);"""
                    ),
                    None,
                )

            return Stripped(f"{target}({value});"), None

        maybe_definition_prefix = ""
        if is_definition and node.annotation is not None:
            # NOTE (mristin):
            # We spell out the declared type, as it might differ from the type of
            # the value, *e.g.*, ``common::optional<...>`` for ``None``.
            declared_type, error_msg = generate_type(
                type_annotation=target_type, types_namespace=self._types_namespace
            )
            if error_msg is not None:
                return None, Error(node.annotation.original_node, error_msg)

            assert declared_type is not None

            # NOTE (mristin):
            # An immutable alias of a generic sequence shares its type annotation,
            # see :py:meth:`intermediate_type_inference._Inferrer.transform_assignment`,
            # so we declare the alias with the template parameter as well.
            target_type_beneath = intermediate_type_inference.beneath_optional(
                target_type
            )
            if isinstance(
                target_type_beneath, intermediate_type_inference.ListTypeAnnotation
            ):
                type_parameter = self._type_parameter_of(target_type_beneath.items)
                if type_parameter is not None:
                    declared_type = Stripped(
                        f"std::vector<std::shared_ptr<{type_parameter}> >"
                    )

                    if isinstance(
                        target_type, intermediate_type_inference.OptionalTypeAnnotation
                    ):
                        declared_type = Stripped(f"common::optional<{declared_type} >")

            # NOTE (mristin):
            # A variable declared as ``Final[...]`` is neither re-assigned nor
            # mutated, so we can declare it as ``const``.
            maybe_const = (
                "const "
                if intermediate_type_inference.is_final_annotation(node.annotation)
                else ""
            )

            if (
                declaration is cpp_aliasing.Declaration.DEFAULT
                or declaration is cpp_aliasing.Declaration.COPY
            ):
                maybe_definition_prefix = f"{maybe_const}{declared_type} "
            elif declaration is cpp_aliasing.Declaration.CONST_REF:
                maybe_definition_prefix = f"const {declared_type}& "
            elif declaration is cpp_aliasing.Declaration.MUT_REF:
                maybe_definition_prefix = f"{declared_type}& "
            else:
                assert_never(declaration)

        elif is_definition:
            if declaration is cpp_aliasing.Declaration.DEFAULT:
                # NOTE (mristin):
                # We spell out the primitive types, as ``auto`` would deduce the type
                # from the literal, *e.g.*, ``int`` instead of ``int64_t`` for ``0``,
                # or ``const wchar_t*`` instead of ``std::wstring`` for ``L"..."``.
                if isinstance(
                    value_type, intermediate_type_inference.PrimitiveTypeAnnotation
                ) and value_type.a_type is not (
                    intermediate_type_inference.PrimitiveType.NONE
                ):
                    maybe_definition_prefix = (
                        f"{PRIMITIVE_TYPE_MAP[value_type.a_type]} "
                    )
                else:
                    maybe_definition_prefix = "auto "
            elif declaration is cpp_aliasing.Declaration.COPY:
                maybe_definition_prefix = "auto "
            elif declaration is cpp_aliasing.Declaration.CONST_REF:
                maybe_definition_prefix = "const auto& "
            elif declaration is cpp_aliasing.Declaration.MUT_REF:
                maybe_definition_prefix = "auto& "
            else:
                assert_never(declaration)

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

        # NOTE (mristin):
        # A value narrowed down to non-null is still a ``common::optional`` in C++,
        # so we de-reference it if the function returns a non-optional. The type
        # inference records the return type of the function on the return.
        value: Optional[Stripped]
        if isinstance(
            self.type_map[node], intermediate_type_inference.OptionalTypeAnnotation
        ):
            value, error = self.transform(node.value)
        else:
            value, error = self._transform_and_value_if_necessary(node.value)

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
    def _transform_if_chain(
        self, branches: Sequence[Tuple[str, Sequence[parse_tree.StatementUnion]]]
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        """
        Transpile the ``branches`` as a chain of ``if``, ``else if`` and ``else``.

        Each branch is given as its header, *e.g.*, ``else if (x > 0)``, together
        with its statements.
        """
        errors: List[Error] = []
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
            writer.write(f"{header} {Transpiler._block(stmts)}")

        if len(errors) > 0:
            return None, Error(None, "Failed to transpile the branches", errors)

        return Stripped(writer.getvalue()), None

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

        errors: List[Error] = []

        # NOTE (mristin):
        # We collect the headers of the branches together with their statements,
        # and treat the default as the last branch.
        branches: List[Tuple[str, Sequence[parse_tree.StatementUnion]]] = []

        for i, case in enumerate(node.cases):
            comparisons: List[str] = []
            for label in case.labels:
                label_code, error = self.transform(label)
                if error is not None:
                    errors.append(error)
                    continue

                assert label_code is not None
                comparisons.append(f"{subject} == {label_code}")

            condition = " || ".join(comparisons)
            keyword = "if" if i == 0 else "else if"
            branches.append((f"{keyword} ({condition})", case.body))

        if node.default is not None:
            branches.append(("else", node.default))

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the switch", errors
            )

        code, error = self._transform_if_chain(branches)
        if error is not None:
            return None, Error(
                node.original_node, "Failed to transpile the switch", [error]
            )

        return code, None

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

        errors: List[Error] = []

        # NOTE (mristin):
        # We collect the headers of the clauses together with their statements, and
        # treat the default as the last clause.
        clauses: List[Tuple[str, Sequence[parse_tree.StatementUnion]]] = []

        for case in node.cases:
            headers: List[str] = []
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

    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def transform_for(
        self, node: parse_tree.For
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        errors: List[Error] = []

        variable_name = node.generator.variable.identifier
        variable_type_annotation = self.type_map[node.generator.variable]

        variable_name_cpp = cpp_naming.variable_name(variable_name)

        header: Optional[str] = None
        if isinstance(node.generator, parse_tree.ForEach):
            type_parameter = self._type_parameter_of(variable_type_annotation)

            variable_type_cpp: Optional[Stripped]
            error_msg: Optional[str]
            if type_parameter is not None:
                variable_type_cpp = Stripped(f"std::shared_ptr<{type_parameter}>")
                error_msg = None
            else:
                variable_type_cpp, error_msg = generate_type(
                    type_annotation=variable_type_annotation,
                    types_namespace=self._types_namespace,
                )
            if error_msg is not None:
                errors.append(Error(node.generator.variable.original_node, error_msg))

            declaration = self._declaration(node.generator)

            if variable_type_cpp is not None:
                if declaration is cpp_aliasing.Declaration.DEFAULT:
                    # NOTE (mristin):
                    # We iterate over the items by constant reference to avoid
                    # the copies, except for the arithmetic values and
                    # the enumerations which are cheap to copy.
                    if not _is_cheap_to_copy(variable_type_annotation):
                        variable_type_cpp = Stripped(f"const {variable_type_cpp}&")
                elif declaration is cpp_aliasing.Declaration.COPY:
                    pass
                elif declaration is cpp_aliasing.Declaration.CONST_REF:
                    variable_type_cpp = Stripped(f"const {variable_type_cpp}&")
                elif declaration is cpp_aliasing.Declaration.MUT_REF:
                    variable_type_cpp = Stripped(f"{variable_type_cpp}&")
                else:
                    assert_never(declaration)

            if declaration is cpp_aliasing.Declaration.MUT_REF:
                # NOTE (mristin):
                # The items are mutated through the loop variable, so we need to
                # iterate over the mutable collection.
                iteration, error = self._transform_mutable_path(
                    node.generator.iteration, dereference=True
                )
            else:
                iteration, error = self._transform_and_value_if_necessary(
                    node.generator.iteration
                )
            if error is not None:
                errors.append(error)

            if variable_type_cpp is not None and iteration is not None:
                if "\n" not in iteration:
                    header = (
                        f"for ({variable_type_cpp} {variable_name_cpp} : {iteration})"
                    )
                else:
                    header = f"""\
for (
{I}{variable_type_cpp} {variable_name_cpp} :
{I}{indent_but_first_line(iteration, I)}
)"""

        elif isinstance(node.generator, parse_tree.ForRange):
            variable_type_cpp, error_msg = generate_type(
                type_annotation=variable_type_annotation,
                types_namespace=self._types_namespace,
            )
            if error_msg is not None:
                errors.append(Error(node.generator.variable.original_node, error_msg))

            start, error = self._transform_and_value_if_necessary(node.generator.start)
            if error is not None:
                errors.append(error)

            end, error = self._transform_and_value_if_necessary(node.generator.end)
            if error is not None:
                errors.append(error)

            if variable_type_cpp is not None and start is not None and end is not None:
                # NOTE (mristin):
                # If the loop variable is an integer, a bound which is a length
                # needs to be widened, as C++ would compare the unsigned ``size_t``
                # and the signed ``int64_t`` as unsigned.
                if (
                    intermediate_type_inference.try_primitive_type(
                        variable_type_annotation
                    )
                    is intermediate_type_inference.PrimitiveType.INT
                ):
                    start = self._as_int64_position(node.generator.start, start)
                    end = self._as_int64_position(node.generator.end, end)

                if "\n" not in start and "\n" not in end:
                    header = (
                        f"for ({variable_type_cpp} {variable_name_cpp} = {start}; "
                        f"{variable_name_cpp} < {end}; ++{variable_name_cpp})"
                    )
                else:
                    header = f"""\
for (
{I}{variable_type_cpp} {variable_name_cpp} = {indent_but_first_line(start, I)};
{I}{variable_name_cpp} < {indent_but_first_line(end, I)};
{I}++{variable_name_cpp}
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

        return Stripped(f"{header} {Transpiler._block(stmts)}"), None

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

        # NOTE (mristin):
        # The exceptions of the standard library expect a narrow string, which
        # we encode in UTF-8. We convert only the f-strings at run time, since
        # they are transpiled as wide strings.
        what: Optional[Stripped] = None
        if node.message is None:
            what = cpp_common.string_literal(
                f"Assertion failed: {ast.unparse(node.condition.original_node)}"
            )
        elif isinstance(node.message, parse_tree.Constant):
            assert isinstance(node.message.value, str)
            what = cpp_common.string_literal(node.message.value)
        else:
            message, error = self.transform(node.message)
            if error is not None:
                errors.append(error)
            else:
                assert message is not None
                what = Stripped(
                    f"""\
common::WstringToUtf8(
{I}{indent_but_first_line(message, I)}
)"""
                )

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the assertion", errors
            )

        assert negation is not None
        assert what is not None

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
{I}throw std::logic_error(
{II}{indent_but_first_line(what, II)}
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
            condition, error = self._transform_and_value_if_necessary(branch.condition)
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

        if len(errors) > 0:
            return None, Error(
                node.original_node, "Failed to transpile the if-statement", errors
            )

        code, error = self._transform_if_chain(branches)
        if error is not None:
            return None, Error(
                node.original_node, "Failed to transpile the if-statement", [error]
            )

        return code, None


# noinspection PyProtectedMember,PyProtectedMember
assert all(op in Transpiler._CPP_COMPARISON_MAP for op in parse_tree.Comparator)
