"""Translate the abstract syntax tree of the meta-model into parsed structures."""
import ast
import collections
import enum
import io
import itertools
import sys
import textwrap
from typing import (
    List,
    Any,
    Optional,
    Type,
    Tuple,
    Union,
    Mapping,
    MutableMapping,
    Dict,
    Set,
    Iterable,
)

import asttokens
import docutils.core
import docutils.io
import docutils.nodes

from icontract import ensure, require

from aas_core_codegen.common import (
    Error,
    Identifier,
    IDENTIFIER_RE,
    LinenoColumner,
    NonEmptyString,
    assert_never,
    is_stripped,
    Stripped,
    XMLTagName,
    XML_TAG_NAME_RE,
)
from aas_core_codegen.parse import tree, _rules
from aas_core_codegen.parse._types import (
    AbstractClass,
    Argument,
    AtomicTypeAnnotation,
    ConcreteClass,
    Invariant,
    Contract,
    Contracts,
    Default,
    Class,
    Enumeration,
    EnumerationLiteral,
    is_string_expr,
    Serialization,
    Property,
    SelfTypeAnnotation,
    Snapshot,
    SubscriptedTypeAnnotation,
    OurType,
    SymbolTable,
    TypeAnnotation,
    UnverifiedSymbolTable,
    PRIMITIVE_TYPES,
    GENERIC_TYPES,
    Description,
    MetaModel,
    ImplementationSpecificMethod,
    UnderstoodMethod,
    ConstructorToBeUnderstood,
    FunctionUnion,
    MethodUnion,
    ConstantSet,
    Constant,
    ConstantPrimitive,
    ConstantUnion,
    SetLiteral,
)


# noinspection GrazieInspection
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def source_to_atok(
    source: str,
) -> Tuple[Optional[asttokens.ASTTokens], Optional[Exception]]:
    """
    Parse the Python code.

    :param source: Python code as text
    :return: parsed module or error, if any
    """
    try:
        atok = asttokens.ASTTokens(source, parse=True)
    except Exception as error:
        return None, error

    return atok, None


class _ExpectedImportsVisitor(ast.NodeVisitor):
    _EXPECTED_NAME_FROM_MODULE = collections.OrderedDict(
        [
            ("match", "re"),
            ("Enum", "enum"),
            ("Annotated", "typing"),
            ("List", "typing"),
            ("Optional", "typing"),
            ("Set", "typing"),
            ("Tuple", "typing"),
            ("DBC", "icontract"),
            ("invariant", "icontract"),
            ("ensure", "icontract"),
            ("require", "icontract"),
            ("abstract", "aas_core_meta.marker"),
            ("constant_set", "aas_core_meta.marker"),
            ("implementation_specific", "aas_core_meta.marker"),
            ("json_name", "aas_core_meta.marker"),
            ("serialization", "aas_core_meta.marker"),
            ("verification", "aas_core_meta.marker"),
            ("non_mutating", "aas_core_meta.marker"),
            ("xml_name", "aas_core_meta.marker"),
        ]
    )

    # pylint: disable=missing-docstring

    def __init__(self) -> None:
        self.errors = []  # type: List[Error]

    def visit_Import(self, node: ast.Import) -> Any:
        self.errors.append(
            Error(
                node,
                "Unexpected ``import ...``. "
                "Only ``from ... import...`` statements are expected.",
            )
        )

    # noinspection PyTypeChecker
    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        for name in node.names:
            assert isinstance(name, ast.alias)
            if name.asname is not None:
                self.errors.append(
                    Error(
                        name,
                        "Unexpected ``from ... import ... as ...``. "
                        "Only ``from ... import...`` statements are expected.",
                    )
                )
            else:
                if name.name not in self._EXPECTED_NAME_FROM_MODULE:
                    self.errors.append(
                        Error(name, f"Unexpected import of a name {name.name!r}.")
                    )

                else:
                    expected_module = self._EXPECTED_NAME_FROM_MODULE[name.name]
                    if expected_module != node.module:
                        self.errors.append(
                            Error(
                                name,
                                f"Expected to import {name.name!r} "
                                f"from the module {expected_module}, "
                                f"but it is imported from {node.module}.",
                            )
                        )


def check_expected_imports(atok: asttokens.ASTTokens) -> List[str]:
    """
    Check that only expected imports are stated in the module.

    This is important so that we can parse type annotations and inheritances.

    Return errors, if any.
    """
    visitor = _ExpectedImportsVisitor()
    assert atok.tree is not None
    visitor.visit(atok.tree)

    if len(visitor.errors) == 0:
        return []

    lineno_columner = LinenoColumner(atok=atok)
    return [lineno_columner.error_message(error) for error in visitor.errors]


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _subscript_index_node(
    node: ast.Subscript, atok: asttokens.ASTTokens
) -> Tuple[Optional[ast.AST], Optional[Error]]:
    """
    Extract the index node of a subscript, *e.g.*, ``int`` out of ``List[int]``.

    This bridges the breaking changes between Python 3.8 and 3.9 in the ``ast``
    module, relevant to this particular piece of parsing logic, where
    ``ast.Index`` and ``ast.ExtSlice`` got deprecated in favor of the wrapped
    value and ``ast.Tuple``, respectively.

    See the deprecation notes just at the end of:
    https://docs.python.org/3/library/ast.html#ast.AST
    """
    if isinstance(node.slice, ast.Slice):
        return (
            None,
            Error(
                node.slice,
                f"Expected an index to define a subscripted type annotation, "
                f"but got a slice: {atok.get_text(node.slice)}",
            ),
        )

    # noinspection PyUnresolvedReferences
    if (sys.version_info < (3, 9) and isinstance(node.slice, ast.ExtSlice)) or (
        sys.version_info >= (3, 9)
        and isinstance(node.slice, ast.Tuple)
        and any(isinstance(elt, ast.Slice) for elt in node.slice.elts)
    ):
        return (
            None,
            Error(
                node.slice,
                f"Expected an index to define a subscripted type annotation, "
                f"but got an extended slice: {atok.get_text(node.slice)}",
            ),
        )

    if sys.version_info < (3, 9):
        # noinspection PyUnresolvedReferences
        if isinstance(node.slice, ast.Index):
            return node.slice.value, None
        else:
            return (
                None,
                Error(
                    node.slice,
                    f"Expected an index to define a subscripted type annotation, "
                    f"but got: {atok.get_text(node.slice)}",
                ),
            )
    else:
        return node.slice, None


def _type_annotation(
    node: ast.AST, atok: asttokens.ASTTokens
) -> Tuple[Optional[TypeAnnotation], Optional[Error]]:
    """Parse the type annotation."""
    if isinstance(node, ast.Name):
        return AtomicTypeAnnotation(identifier=Identifier(node.id), node=node), None

    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, str):
            return (
                None,
                Error(
                    node,
                    f"Expected a string literal "
                    f"if the type annotation is given as a constant, "
                    f"but got: "
                    f"{node.value!r} (as {type(node.value)})",
                ),
            )

        return AtomicTypeAnnotation(identifier=Identifier(node.value), node=node), None

    elif isinstance(node, ast.Subscript):
        if not isinstance(node.value, ast.Name):
            return (
                None,
                Error(
                    node.value,
                    f"Expected a name to define "
                    f"a subscripted type annotation,"
                    f"but got: {atok.get_text(node.value)}",
                ),
            )

        index_node, error = _subscript_index_node(node=node, atok=atok)
        if error is not None:
            return None, error

        assert index_node is not None

        subscripts = []  # type: List[TypeAnnotation]

        if isinstance(index_node, ast.Tuple):
            for elt in index_node.elts:
                subscript_annotation, error = _type_annotation(node=elt, atok=atok)
                if error is not None:
                    return None, error

                assert subscript_annotation is not None

                subscripts.append(subscript_annotation)

        elif isinstance(index_node, (ast.Name, ast.Subscript, ast.Constant)):
            subscript_annotation, error = _type_annotation(node=index_node, atok=atok)
            if error is not None:
                return None, error

            assert subscript_annotation is not None

            subscripts.append(subscript_annotation)

        else:
            return (
                None,
                Error(
                    index_node,
                    f"Expected a tuple, a name, a subscript or a string literal "
                    f"for a subscripted type annotation, "
                    f"but got: {atok.get_text(index_node)}",
                ),
            )

        return (
            SubscriptedTypeAnnotation(
                identifier=Identifier(node.value.id),
                subscripts=subscripts,
                node=node,
            ),
            None,
        )

    else:
        return (
            None,
            Error(
                node,
                f"Expected either atomic type annotation (as name or string literal) "
                f"or a subscripted one (as a subscript), "
                f"but got: {atok.get_text(node)} (as {type(node)})",
            ),
        )


#: Markers accepted as the metadata items of ``Annotated[...]`` on a property's
#: type annotation, to specify an explicit name of the property in
#: a serialization, *e.g.*,
#: ``Annotated[Optional[str], json_name("someFoo"), xml_name("someFoo")]``.
_SERIALIZATION_NAME_MARKERS = ("json_name", "xml_name")


_PRIMITIVE_TYPE_NAMES_TO_CONSTANT_FUNCTION_NAMES: Dict[Identifier, Identifier] = {
    Identifier("bool"): Identifier("constant_bool"),
    Identifier("int"): Identifier("constant_int"),
    Identifier("float"): Identifier("constant_float"),
    Identifier("str"): Identifier("constant_str"),
    Identifier("bytearray"): Identifier("constant_bytearray"),
}
# fmt: off
assert all(
    primitive_type in _PRIMITIVE_TYPE_NAMES_TO_CONSTANT_FUNCTION_NAMES
    for primitive_type in PRIMITIVE_TYPES
)
# fmt: on

# fmt: off
_PRIMITIVE_TYPE_NAMES_TO_PYTHON_TYPES: Mapping[
    Identifier,
    Union[Type[bool], Type[int], Type[float], Type[str], Type[bytearray]]
] = {
    Identifier("bool"): bool,
    Identifier("int"): int,
    Identifier("float"): float,
    Identifier("str"): str,
    Identifier("bytearray"): bytearray,
}
assert all(
    primitive_type in _PRIMITIVE_TYPE_NAMES_TO_PYTHON_TYPES
    for primitive_type in PRIMITIVE_TYPES
)


@require(lambda constant: isinstance(constant.value, str))
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _ast_constant_string_to_description(
    constant: ast.Constant,
) -> Tuple[Optional[Description], Optional[Error]]:
    """Extract the docstring from the given string constant."""
    text = constant.value
    assert isinstance(
        text, str
    ), f"Expected a string constant node, but got: {ast.dump(constant)!r}"

    dedented = textwrap.dedent(text)

    warnings = io.StringIO()

    document: docutils.nodes.document
    try:
        document = docutils.core.publish_doctree(
            dedented, settings_overrides={"warning_stream": warnings}
        )
    except Exception as err:
        return None, Error(
            constant, f"Failed to parse the description with docutils: {err}"
        )

    warnings_text = warnings.getvalue()
    if warnings_text:
        return None, Error(
            constant,
            f"Failed to parse the description with docutils:\n"
            f"{warnings_text.strip()}\n\n"
            f"The original text was: {dedented!r}",
        )

    assert document is not None

    return Description(document=document, node=constant), None
# fmt: on


# noinspection PyTypeChecker
# fmt: off
@require(
    lambda primitive_type: primitive_type in PRIMITIVE_TYPES,
    "Expected the type annotation as primitive type"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _parse_constant_primitive(
    name: Identifier,
    primitive_type: Identifier,
    node: ast.AnnAssign,
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[ConstantPrimitive], Optional[Error]]:
    """Parse the definition of a constant as a call to ``constant_primitive`` marker."""
    expected_func_name = _PRIMITIVE_TYPE_NAMES_TO_CONSTANT_FUNCTION_NAMES[
        primitive_type
    ]

    if (
        not isinstance(node.value, ast.Call)
        or not isinstance(node.value.func, ast.Name)
        or node.value.func.id != expected_func_name
    ):
        return (
            None,
            Error(
                node.value,
                f"Expected the value of the constant definition {name!r} "
                f"of type {primitive_type} to be "
                f"a call to the function {expected_func_name}, "
                f"but got: {atok.get_text(node.value)}",
            ),
        )

    value_arg_node = None  # type: Optional[ast.expr]
    description_arg_node = None  # type: Optional[ast.expr]

    if len(node.value.args) > 0:
        value_arg_node = node.value.args[0]

    if len(node.value.args) > 1:
        description_arg_node = node.value.args[1]

    if len(node.value.args) > 3:
        return None, Error(
            node.value.args[3],
            f"Expected only 3 arguments to {expected_func_name}, "
            f"but got {len(node.value.args)}: {atok.get_text(node.value)}",
        )

    for kwarg in node.value.keywords:
        if kwarg.arg == "value":
            value_arg_node = kwarg.value
        elif kwarg.arg == "description":
            description_arg_node = kwarg.value
        else:
            return None, Error(
                kwarg,
                f"Unexpected keyword argument "
                f"to {expected_func_name}: {atok.get_text(kwarg)}",
            )

    # region Parse ``value``

    if not isinstance(value_arg_node, ast.Constant):
        return (
            None,
            Error(
                value_arg_node,
                f"Expected a literal value, but got: {atok.get_text(value_arg_node)}",
            ),
        )

    if value_arg_node.value is None:
        return (
            None,
            Error(
                value_arg_node,
                "We do not handle None as a constant at this moment. "
                "Please contact the developers if you need this feature",
            ),
        )

    expected_type = _PRIMITIVE_TYPE_NAMES_TO_PYTHON_TYPES[primitive_type]
    # noinspection PyTypeHints
    if not isinstance(value_arg_node.value, expected_type):
        return None, Error(
            value_arg_node,
            f"Expected the value as {expected_type}, "
            f"but got {type(value_arg_node.value)}",
        )

    # endregion

    # region Parse ``description``

    description = None  # type: Optional[Description]
    if description_arg_node is not None:
        if not isinstance(description_arg_node, ast.Constant) or not isinstance(
            description_arg_node.value, str
        ):
            return None, Error(
                description_arg_node,
                f"Expected string literal as the ``description`` argument, "
                f"but got: {atok.get_text(description_arg_node)}",
            )

        description, error = _ast_constant_string_to_description(
            constant=description_arg_node
        )

        if error is not None:
            return None, Error(
                node.value, "Failed to parse the ``description`` argument", [error]
            )

        assert description is not None

    # endregion

    return (
        ConstantPrimitive(
            name=name,
            value=value_arg_node.value,
            description=description,
            node=node,
        ),
        None,
    )


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _parse_constant_set(
    name: Identifier,
    items_type_annotation: AtomicTypeAnnotation,
    node: ast.AnnAssign,
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[ConstantSet], Optional[Error]]:
    expected_func_name = "constant_set"

    if (
        not isinstance(node.value, ast.Call)
        or not isinstance(node.value.func, ast.Name)
        or node.value.func.id != expected_func_name
    ):
        return (
            None,
            Error(
                node.value,
                f"Expected the value of the constant set definition {name!r} "
                f"to be a call to the function {expected_func_name}, "
                f"but got: {atok.get_text(node.value)}",
            ),
        )

    # region Determine arguments

    values_arg_node = None  # type: Optional[ast.expr]
    description_arg_node = None  # type: Optional[ast.expr]
    superset_of_arg_node = None  # type: Optional[ast.expr]

    if len(node.value.args) > 0:
        values_arg_node = node.value.args[0]

    if len(node.value.args) > 1:
        description_arg_node = node.value.args[1]

    if len(node.value.args) > 2:
        superset_of_arg_node = node.value.args[3]

    if len(node.value.args) > 3:
        return None, Error(
            node.value.args[4],
            f"Expected only 4 arguments to {expected_func_name}, "
            f"but got {len(node.value.args)}: {atok.get_text(node.value)}",
        )

    for kwarg in node.value.keywords:
        if kwarg.arg == "values":
            values_arg_node = kwarg.value
        elif kwarg.arg == "description":
            description_arg_node = kwarg.value
        elif kwarg.arg == "superset_of":
            superset_of_arg_node = kwarg.value
        else:
            return None, Error(
                kwarg,
                f"Unexpected keyword argument "
                f"to {expected_func_name}: {atok.get_text(kwarg)}",
            )

    # endregion

    # region Parse ``values``

    if values_arg_node is None:
        return None, Error(node.value, "Missing values argument")

    if not isinstance(values_arg_node, ast.List):
        return None, Error(
            values_arg_node,
            f"Expected the values of a constant set to be a list literal, "
            f"but got: {atok.get_text(values_arg_node)}; "
            f"in AST: {ast.dump(values_arg_node)}",
        )

    set_literals = []  # type: List[SetLiteral]
    for i, elt in enumerate(values_arg_node.elts):
        if not isinstance(elt, (ast.Attribute, ast.Constant)):
            return None, Error(
                elt,
                f"Expected the values of a constant set to be all literals "
                f"(either an enumeration literal or a literal of a primitive type "
                f"such as str or int), but got at the index {i}: "
                f"{atok.get_text(elt)}; in AST: {ast.dump(elt)}",
            )

        set_literals.append(SetLiteral(node=elt))

    # endregion

    # region Parse ``description``

    description = None  # type: Optional[Description]

    if description_arg_node is not None:
        if not isinstance(description_arg_node, ast.Constant) or not isinstance(
            description_arg_node.value, str
        ):
            return None, Error(
                description_arg_node,
                f"Expected string literal as the ``description`` argument, "
                f"but got: {atok.get_text(description_arg_node)}; "
                f"in AST: {ast.dump(description_arg_node)}",
            )

        description, error = _ast_constant_string_to_description(
            constant=description_arg_node
        )

        if error is not None:
            return None, Error(
                node.value, "Failed to parse the ``description`` argument", [error]
            )

        assert description is not None

    # endregion

    # region Parse ``superset_of``

    subsets = []  # type: List[Identifier]

    if superset_of_arg_node is not None:
        if not isinstance(superset_of_arg_node, ast.List):
            return None, Error(
                superset_of_arg_node,
                f"Expected the ``superset_of`` of a constant set to be a list literal, "
                f"but got: {atok.get_text(superset_of_arg_node)}; "
                f"in AST: {ast.dump(superset_of_arg_node)}",
            )

        for i, elt in enumerate(superset_of_arg_node.elts):
            if not isinstance(elt, ast.Name) or not IDENTIFIER_RE.fullmatch(elt.id):
                return None, Error(
                    elt,
                    f"Expected the elements of the ``superset_of`` of a constant set "
                    f"to be a list of variables (referring to the other sets), "
                    f"but got at index {i}: "
                    f"{atok.get_text(elt)}; in AST: {ast.dump(elt)}",
                )

            subsets.append(Identifier(elt.id))

    # endregion

    return (
        ConstantSet(
            name=name,
            items_type_annotation=items_type_annotation,
            set_literals=set_literals,
            subsets=subsets,
            description=description,
            node=node,
        ),
        None,
    )


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _ann_assign_to_constant(
    node: ast.AnnAssign, atok: asttokens.ASTTokens
) -> Tuple[Optional[ConstantUnion], Optional[Error]]:
    if not isinstance(node.target, ast.Name):
        return (
            None,
            Error(
                node.target,
                f"Expected target of a constant to be a name, "
                f"but got: {atok.get_text(node.target)}",
            ),
        )

    if not node.simple:
        return (
            None,
            Error(
                node.target,
                "Expected a constant definition with a simple target (no parentheses!)",
            ),
        )

    if node.annotation is None:
        return (
            None,
            Error(node.target, "Expected the constant to be annotated with a type"),
        )

    if node.value is None:
        return (
            None,
            Error(node.value, "Unexpected constant definition without a value"),
        )

    type_annotation, error = _type_annotation(node=node.annotation, atok=atok)
    if error is not None:
        return None, error

    assert type_annotation is not None

    if isinstance(type_annotation, AtomicTypeAnnotation):
        if type_annotation.identifier not in PRIMITIVE_TYPES:
            return (
                None,
                Error(
                    node.annotation,
                    "We only handle definition of constant sets and primitive values "
                    f"at the moment, but you defined a constant "
                    f"of type {type_annotation.identifier!r}. "
                    f"Please contact the developers if you really need this feature",
                ),
            )

        return _parse_constant_primitive(
            name=Identifier(node.target.id),
            primitive_type=type_annotation.identifier,
            node=node,
            atok=atok,
        )
    elif isinstance(type_annotation, SubscriptedTypeAnnotation):
        if type_annotation.identifier == "Set":
            if len(type_annotation.subscripts) != 1:
                return (
                    None,
                    Error(
                        node.annotation,
                        f"Expected exactly one subscript in the type annotation "
                        f"of the constant set {node.target.id!r}, "
                        f"but got {len(type_annotation.subscripts)}: "
                        f"{atok.get_text(node.annotation)}",
                    ),
                )

            items_type_annotation = type_annotation.subscripts[0]
            if not isinstance(items_type_annotation, AtomicTypeAnnotation):
                return (
                    None,
                    Error(
                        node.annotation,
                        f"We only support constant sets of atomic types at the moment, "
                        f"but we got a subscripted type "
                        f"for the items: {atok.get_text(items_type_annotation)}. "
                        f"Please contact the developers if you need this feature",
                    ),
                )

            return _parse_constant_set(
                name=Identifier(node.target.id),
                items_type_annotation=items_type_annotation,
                node=node,
                atok=atok,
            )
        else:
            return (
                None,
                Error(
                    node.annotation,
                    f"We do not know how to handle "
                    f"the type annotation: {type_annotation.identifier!r}",
                ),
            )

    elif isinstance(type_annotation, SelfTypeAnnotation):
        raise AssertionError(
            f"Unexpected {SelfTypeAnnotation.__name__} in the constant definition. "
            f"This is a bug as {SelfTypeAnnotation.__name__} are generated by our "
            f"code, but can not be supplied through user input"
        )
    else:
        assert_never(type_annotation)


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _ann_assign_to_property(
    node: ast.AnnAssign, description: Optional[Description], atok: asttokens.ASTTokens
) -> Tuple[Optional[Property], Optional[Error]]:
    if not isinstance(node.target, ast.Name):
        return (
            None,
            Error(
                node.target,
                f"Expected property target to be a name, "
                f"but got: {atok.get_text(node.target)}",
            ),
        )

    if not node.simple:
        return (
            None,
            Error(
                node.target,
                "Expected a property with a simple target (no parentheses!)",
            ),
        )

    if node.annotation is None:
        return (
            None,
            Error(node.target, "Expected property to be annotated with a type"),
        )

    json_name = None  # type: Optional[NonEmptyString]
    xml_name = None  # type: Optional[XMLTagName]

    if (
        isinstance(node.annotation, ast.Subscript)
        and isinstance(node.annotation.value, ast.Name)
        and node.annotation.value.id == "Annotated"
    ):
        # NOTE (2026-09-01):
        # We unwrap ``Annotated[...]`` here, at the property level, and nowhere
        # else, since the ``json_name``/``xml_name`` markers only make sense as
        # metadata on a property's type annotation.
        index_node, error = _subscript_index_node(node=node.annotation, atok=atok)
        if error is not None:
            return None, error

        assert index_node is not None

        if not isinstance(index_node, ast.Tuple) or len(index_node.elts) < 2:
            return (
                None,
                Error(
                    index_node,
                    f"Expected ``Annotated`` to wrap the type annotation "
                    f"together with at least one metadata item "
                    f"such as ``json_name(...)`` or ``xml_name(...)``, "
                    f"but got: {atok.get_text(index_node)}",
                ),
            )

        type_annotation, error = _type_annotation(node=index_node.elts[0], atok=atok)
        if error is not None:
            return None, error

        assert type_annotation is not None

        for metadata_node in index_node.elts[1:]:
            if (
                not isinstance(metadata_node, ast.Call)
                or not isinstance(metadata_node.func, ast.Name)
                or metadata_node.func.id not in _SERIALIZATION_NAME_MARKERS
            ):
                joined_markers = " or ".join(
                    f"``{marker}(...)``" for marker in _SERIALIZATION_NAME_MARKERS
                )
                return (
                    None,
                    Error(
                        metadata_node,
                        f"Expected a call to {joined_markers} "
                        f"as the metadata of ``Annotated``, "
                        f"but got: {atok.get_text(metadata_node)}",
                    ),
                )

            marker_name = metadata_node.func.id

            if len(metadata_node.args) + len(metadata_node.keywords) != 1:
                return (
                    None,
                    Error(
                        metadata_node,
                        f"Expected exactly one argument ``name`` "
                        f"to the marker {marker_name!r}, "
                        f"but got: {atok.get_text(metadata_node)}",
                    ),
                )

            name_arg_node: ast.expr
            if len(metadata_node.args) == 1:
                name_arg_node = metadata_node.args[0]
            else:
                kwarg = metadata_node.keywords[0]
                if kwarg.arg != "name":
                    return (
                        None,
                        Error(
                            metadata_node,
                            f"Unexpected keyword argument {kwarg.arg!r} "
                            f"to the marker {marker_name!r}: "
                            f"{atok.get_text(metadata_node)}",
                        ),
                    )
                name_arg_node = kwarg.value

            if not isinstance(name_arg_node, ast.Constant) or not isinstance(
                name_arg_node.value, str
            ):
                return (
                    None,
                    Error(
                        name_arg_node,
                        f"Expected a string literal as the argument "
                        f"to the marker {marker_name!r}, "
                        f"but got: {atok.get_text(name_arg_node)}",
                    ),
                )

            if marker_name == "json_name":
                if json_name is not None:
                    return (
                        None,
                        Error(
                            metadata_node,
                            "Unexpected multiple ``json_name`` markers "
                            "in ``Annotated``",
                        ),
                    )

                if len(name_arg_node.value) == 0:
                    return (
                        None,
                        Error(
                            name_arg_node,
                            "Expected a non-empty string as the argument "
                            "to the marker 'json_name'",
                        ),
                    )

                json_name = NonEmptyString(name_arg_node.value)
            else:
                if xml_name is not None:
                    return (
                        None,
                        Error(
                            metadata_node,
                            "Unexpected multiple ``xml_name`` markers "
                            "in ``Annotated``",
                        ),
                    )

                if not XML_TAG_NAME_RE.fullmatch(name_arg_node.value):
                    return (
                        None,
                        Error(
                            name_arg_node,
                            f"Expected a valid local XML tag name "
                            f"(matching {XML_TAG_NAME_RE.pattern!r}) as the argument "
                            f"to the marker 'xml_name', "
                            f"but got: {name_arg_node.value!r}",
                        ),
                    )

                xml_name = XMLTagName(name_arg_node.value)
    else:
        type_annotation, error = _type_annotation(node=node.annotation, atok=atok)
        if error is not None:
            return None, error

        assert type_annotation is not None

    if node.value is not None:
        return (
            None,
            Error(node.value, "Unexpected assignment of a value to a property"),
        )

    return (
        Property(
            name=Identifier(node.target.id),
            type_annotation=type_annotation,
            description=description,
            node=node,
            json_name=json_name,
            xml_name=xml_name,
        ),
        None,
    )


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _args_to_arguments(
    node: ast.arguments, atok: asttokens.ASTTokens
) -> Tuple[Optional[List[Argument]], Optional[Error]]:
    """Parse arguments of a method."""
    if hasattr(node, "posonlyargs") and len(node.posonlyargs) > 0:
        return None, Error(node, "Unexpected positional-only arguments")

    if node.vararg is not None or node.kwarg is not None:
        return None, Error(node, "Unexpected variable arguments")

    if len(node.kwonlyargs) > 0:
        return None, Error(node, "Unexpected keyword-only arguments")

    assert len(node.kw_defaults) == 0, (
        "No keyword-only arguments implies "
        "there should be no defaults "
        "for keyword-only arguments either."
    )

    if len(node.args) == 0:
        return None, Error(node, "Unexpected no arguments")

    arguments = []  # type: List[Argument]

    # region ``self``

    found_self = False

    if len(node.args) >= 1 and node.args[0].arg == "self":
        found_self = True

        if node.args[0].annotation is not None:
            return (
                None,
                Error(
                    node.args[0],
                    "Unexpected type annotation for the method argument ``self``",
                ),
            )

        if len(node.defaults) == len(node.args):
            return (
                None,
                Error(
                    node.args[0],
                    "Unexpected default value for the method argument ``self``",
                ),
            )

        arguments.append(
            Argument(
                name=Identifier("self"),
                type_annotation=SelfTypeAnnotation(),
                default=None,
                node=node.args[0],
            )
        )

    # endregion

    # region Non-self arguments

    # We skip the first argument if we found ``self`` as it has been added to
    # ``arguments`` already.

    for i in range(1 if found_self else 0, len(node.args)):
        arg_node = node.args[i]

        # region Type annotation
        if arg_node.annotation is None:
            return (
                None,
                Error(
                    arg_node,
                    f"Unexpected method argument without a type annotation: "
                    f"{arg_node.arg}",
                ),
            )

        type_annotation, error = _type_annotation(node=arg_node.annotation, atok=atok)
        if error is not None:
            return (
                None,
                Error(
                    arg_node,
                    f"Failed to parse the type annotation "
                    f"of the method argument {arg_node.arg}: "
                    f"{atok.get_text(arg_node.annotation)}",
                    underlying=[error],
                ),
            )

        assert type_annotation is not None

        # endregion

        # region Default
        default = None  # type: Optional[Default]

        # NOTE (mristin, 2021-12-16):
        # A simple hypothetical test calculation:
        # 5 args
        # 2 defaults
        #
        # i = 3
        #   i - offset = 0 🠒 index in the node.defaults
        #   offset must be 3
        #   offset = len(node.args) - len(node.defaults) = 5 - 2 = 3

        offset = len(node.args) - len(node.defaults)
        if i >= offset:
            default = Default(node=node.defaults[i - offset])

        # endregion

        arguments.append(
            Argument(
                name=Identifier(arg_node.arg),
                type_annotation=type_annotation,
                default=default,
                node=arg_node,
            )
        )

    # endregion

    return arguments, None


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _parse_contract_condition(
    node: ast.Call, atok: asttokens.ASTTokens
) -> Tuple[Optional[Contract], Optional[Error]]:
    """Parse the contract decorator."""
    condition_node = None  # type: Optional[ast.AST]
    description_node = None  # type: Optional[ast.AST]

    if len(node.args) >= 1:
        condition_node = node.args[0]

    if len(node.args) >= 2:
        description_node = node.args[1]

    for keyword in node.keywords:
        if keyword.arg == "condition":
            condition_node = keyword.value

        elif keyword.arg == "description":
            description_node = keyword.value

        else:
            # We simply ignore to parse the argument.
            pass

    if condition_node is None:
        return (
            None,
            Error(node, "Expected the condition to be defined for a contract"),
        )

    if not isinstance(condition_node, ast.Lambda):
        return (
            None,
            Error(
                condition_node,
                f"Expected a lambda function as a contract condition, "
                f"but got: {atok.get_text(condition_node)}",
            ),
        )

    description = None  # type: Optional[str]
    if description_node is not None:
        if not (
            isinstance(description_node, ast.Constant)
            and isinstance(description_node.value, str)
        ):
            return (
                None,
                Error(
                    description_node,
                    f"Expected a string literal as a contract description, "
                    f"but got: {atok.get_text(description_node)!r}",
                ),
            )

        description = description_node.value

    body, error = _rules.ast_node_to_our_node(node=condition_node.body)
    if error is not None:
        return None, Error(condition_node.body, "Failed to parse the contract", [error])

    assert body is not None

    if not isinstance(body, tree.Expression):
        return None, Error(
            condition_node.body,
            f"Expected an expression in the contract condition body, "
            f"but got: {tree.dump(body)}",
        )

    return (
        Contract(
            args=[Identifier(arg.arg) for arg in condition_node.args.args],
            description=description,
            body=body,
            node=node,
        ),
        None,
    )


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _parse_snapshot(
    node: ast.Call, atok: asttokens.ASTTokens
) -> Tuple[Optional[Snapshot], Optional[Error]]:
    """Parse the snapshot decorator."""
    capture_node = None  # type: Optional[ast.AST]
    name_node = None  # type: Optional[ast.AST]

    if len(node.args) >= 1:
        capture_node = node.args[0]

    if len(node.args) >= 2:
        name_node = node.args[1]

    for keyword in node.keywords:
        if keyword.arg == "capture":
            capture_node = keyword.value

        elif keyword.arg == "name":
            name_node = keyword.value

        else:
            # We simply ignore to parse the argument.
            pass

    if capture_node is None:
        return None, Error(node, "Expected the capture to be defined for a snapshot")

    if not isinstance(capture_node, ast.Lambda):
        return (
            None,
            Error(
                capture_node,
                f"Expected a lambda function as a capture of a snapshot, "
                f"but got: {atok.get_text(capture_node)}",
            ),
        )

    if name_node is not None and not (
        isinstance(name_node, ast.Constant) and isinstance(name_node.value, str)
    ):
        return (
            None,
            Error(
                name_node,
                f"Expected a string literal as a capture name, "
                f"but got: {atok.get_text(name_node)}",
            ),
        )

    name: str
    if name_node is not None:
        assert isinstance(name_node, ast.Constant) and isinstance(
            name_node.value, str
        ), (
            "We checked for this above -- "
            "if name node is set, it must be a string literal."
        )

        name = name_node.value
    elif len(capture_node.args.args) == 1 and name_node is None:
        name = capture_node.args.args[0].arg
    else:
        return (
            None,
            Error(
                node,
                "Expected the name of the snapshot to be defined, "
                "but there was neither the single argument in the capture "
                "nor explicit ``name`` given",
            ),
        )

    if not IDENTIFIER_RE.fullmatch(name):
        return (
            None,
            Error(
                name_node if name_node is not None else node,
                f"Expected a capture name to be a valid identifier, but got: {name!r}",
            ),
        )

    body, error = _rules.ast_node_to_our_node(node=capture_node.body)
    if error is not None:
        return None, Error(capture_node.body, "Failed to parse the snapshot", [error])

    assert body is not None

    if not isinstance(body, tree.Expression):
        return None, Error(
            capture_node.body,
            f"Expected an expression in the contract condition body, "
            f"but got: {tree.dump(body)}",
        )

    return (
        Snapshot(
            args=[Identifier(arg.arg) for arg in capture_node.args.args],
            name=Identifier(name),
            body=body,
            node=node,
        ),
        None,
    )


# fmt: off
# noinspection PyTypeChecker,PyUnresolvedReferences
@ensure(
    lambda expect_self, result:
    not (result[0] is not None and not expect_self)
    or 'self' not in result[0].arguments_by_name,
    "No ``self`` argument if not ``expect_self``"
)
@ensure(
    lambda expect_self, result:
    not (result[0] is not None and expect_self)
    or (
            len(result[0].arguments) >= 0
            and result[0].arguments[0].name == 'self'
            and isinstance(result[0].arguments[0].type_annotation, SelfTypeAnnotation)
    ),
    "If ``expect_self`` set, expect at least one argument and that should be ``self``"
)
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
# fmt: on
def _function_def_to_method(
    node: ast.FunctionDef, expect_self: bool, atok: asttokens.ASTTokens
) -> Tuple[Optional[MethodUnion], Optional[Error]]:
    """
    Parse the function definition into a method.

    Though we have to distinguish in Python between a function and a method, we term
    both of them "methods" in our model.

    If ``expect_self`` is set, the first argument is expected to be ``self``. Otherwise,
    no ``self`` argument is expected.
    """
    # NOTE (mristin, 2021-12-19):
    # This run-time check is necessary as we already burned our fingers with it.
    assert isinstance(node, ast.FunctionDef)

    name = node.name

    if name != "__init__" and name.startswith("__") and name.endswith("__"):
        return (
            None,
            Error(
                node,
                f"Among all dunder methods, only ``__init__`` is expected, "
                f"but got: {name}",
            ),
        )

    preconditions = []  # type: List[Contract]
    postconditions = []  # type: List[Contract]
    snapshots = []  # type: List[Snapshot]

    is_implementation_specific = False
    verification = False  # Set if the function is decorated with ``@verification``
    non_mutating = False  # Set if the function is decorated with ``@non_mutating``

    # region Parse decorators

    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                if decorator.func.id == "require":
                    precondition, error = _parse_contract_condition(
                        node=decorator, atok=atok
                    )
                    if error is not None:
                        return None, error

                    assert precondition is not None

                    preconditions.append(precondition)

                elif decorator.func.id == "ensure":
                    postcondition, error = _parse_contract_condition(
                        node=decorator, atok=atok
                    )
                    if error is not None:
                        return None, error

                    assert postcondition is not None

                    postconditions.append(postcondition)

                elif decorator.func.id == "snapshot":
                    snapshot, error = _parse_snapshot(node=decorator, atok=atok)
                    if error is not None:
                        return None, error

                    assert snapshot is not None

                    snapshots.append(snapshot)

                else:
                    return (
                        None,
                        Error(
                            decorator,
                            f"Unexpected decorator of a method: {decorator.func.id}; "
                            f"expected at most "
                            f"``require``, ``ensure`` or ``snapshot``",
                        ),
                    )
            else:
                return (
                    None,
                    Error(
                        decorator,
                        f"Unexpected non-name decorator of a method: "
                        f"{atok.get_text(decorator.func)!r}",
                    ),
                )

        elif isinstance(decorator, ast.Name):
            if decorator.id == "implementation_specific":
                is_implementation_specific = True

            elif decorator.id == "verification":
                verification = True

            elif decorator.id == "non_mutating":
                non_mutating = True

            else:
                return (
                    None,
                    Error(
                        decorator,
                        f"Unexpected simple decorator of a method: {decorator.id}; "
                        f"expected at most ``implementation_specific``",
                    ),
                )
        else:
            return (
                None,
                Error(
                    decorator,
                    f"Expected decorators of a method to be "
                    f"only ``ast.Name`` and ``ast.Call``, "
                    f"but got: {atok.get_text(decorator)!r}",
                ),
            )

    # endregion

    # region Reverse contracts

    # We need to reverse the contracts since the decorators are evaluated from bottom
    # up, while we parsed them from top to bottom.
    preconditions = list(reversed(preconditions))
    snapshots = list(reversed(snapshots))
    postconditions = list(reversed(postconditions))

    # endregion

    # region Parse arguments and body

    description = None  # type: Optional[Description]
    body = node.body

    if len(node.body) >= 1 and is_string_expr(expr=node.body[0]):
        assert isinstance(node.body[0], ast.Expr)
        assert isinstance(node.body[0].value, ast.Constant)

        description, error = _ast_constant_string_to_description(
            constant=node.body[0].value
        )

        if error is not None:
            return None, error

        body = node.body[1:]

    arguments, error = _args_to_arguments(node=node.args, atok=atok)
    if error is not None:
        return (
            None,
            Error(
                node,
                f"Failed to parse arguments of the method: {name}",
                underlying=[error],
            ),
        )

    assert arguments is not None

    returns = None  # type: Optional[TypeAnnotation]
    if node.returns is None:
        return (
            None,
            Error(
                node,
                f"Unexpected method without a type annotation for the result: {name}",
            ),
        )

    if not (isinstance(node.returns, ast.Constant) and node.returns.value is None):
        returns, error = _type_annotation(node=node.returns, atok=atok)
        if error is not None:
            return None, error

    # endregion

    # region All contract arguments are included in the function arguments

    function_arg_set = set(arg.name for arg in arguments)

    for contract in preconditions:
        for arg in contract.args:
            if arg not in function_arg_set:
                return (
                    None,
                    Error(
                        contract.node,
                        f"The argument of the precondition is not provided "
                        f"in the method: {arg}",
                    ),
                )

    has_snapshots = len(snapshots) > 0
    for contract in postconditions:
        for arg in contract.args:
            if arg == "OLD":
                if not has_snapshots and arg == "OLD":
                    return (
                        None,
                        Error(
                            contract.node,
                            f"The argument OLD of the postcondition is not provided "
                            f"since there were no snapshots defined "
                            f"for the method: {name}",
                        ),
                    )

            elif arg == "result":
                continue

            elif arg not in function_arg_set:
                return (
                    None,
                    Error(
                        contract.node,
                        f"The argument of the postcondition is not provided "
                        f"in the method: {arg}",
                    ),
                )
            else:
                # Everything is OK.
                pass

    for snapshot in snapshots:
        for arg in snapshot.args:
            if arg not in function_arg_set:
                return (
                    None,
                    Error(
                        snapshot.node,
                        f"The argument of the snapshot is not provided "
                        f"in the method: {arg}",
                    ),
                )

    # endregion

    # region Check __init__ constraints
    if name == "__init__":
        # Must return None
        if returns is not None:
            return (
                None,
                Error(
                    node,
                    f"Expected __init__ to return None, "
                    f"but got: {atok.get_text(node.returns)}",
                ),
            )

        # Must not be a verification
        if verification:
            return (
                None,
                Error(
                    node,
                    "Expected __init__ not to be a verification function",
                ),
            )

    # endregion

    # region Check that the parsed method conforms to ``expect_self``

    if expect_self and len(arguments) == 0:
        return (
            None,
            Error(
                node,
                f"A ``self`` argument is expected, but no arguments were specified "
                f"in the method {name!r}",
            ),
        )

    if expect_self and len(arguments) >= 1:
        if arguments[0].name != "self":
            return (
                None,
                Error(
                    node,
                    f"Expected the first argument to be ``self`` "
                    f"in the method {name!r}, but got {arguments[0].name!r}",
                ),
            )

        if not isinstance(arguments[0].type_annotation, SelfTypeAnnotation):
            return (
                None,
                Error(
                    node,
                    f"Expected the ``self`` argument to have no annotation "
                    f"in the method {name!r}, but got {arguments[0].type_annotation!r}",
                ),
            )

    # endregion

    if is_implementation_specific:
        return (
            ImplementationSpecificMethod(
                name=Identifier(name),
                verification=verification,
                arguments=arguments,
                returns=returns,
                description=description,
                contracts=Contracts(
                    preconditions=preconditions,
                    snapshots=snapshots,
                    postconditions=postconditions,
                ),
                non_mutating=non_mutating,
                node=node,
            ),
            None,
        )
    else:
        if name == "__init__":
            assert not verification
            assert returns is None

            if non_mutating:
                return (
                    None,
                    Error(
                        node,
                        "Unexpected non-mutating constructor",
                    ),
                )

            return (
                ConstructorToBeUnderstood(
                    arguments=arguments,
                    description=description,
                    contracts=Contracts(
                        preconditions=preconditions,
                        snapshots=snapshots,
                        postconditions=postconditions,
                    ),
                    body=body,
                    node=node,
                ),
                None,
            )
        else:
            understanding_errors = []  # type: List[Error]

            understood_body = []  # type: List[tree.Node]

            for body_child in body:
                # NOTE (mristin, 2021-12-27):
                # We deliberately ignore ``pass`` as it makes no sense in our
                # context of multiple programming languages.
                if isinstance(body_child, ast.Pass):
                    continue

                understood_node, understanding_error = _rules.ast_node_to_our_node(
                    body_child
                )

                if understanding_error is not None:
                    understanding_errors.append(understanding_error)
                    continue

                assert understood_node is not None
                understood_body.append(understood_node)

            if len(understanding_errors) > 0:
                return None, Error(
                    node,
                    f"Failed to understand the body of the function {name!r}",
                    understanding_errors,
                )

            return (
                UnderstoodMethod(
                    name=Identifier(name),
                    verification=verification,
                    arguments=arguments,
                    returns=returns,
                    description=description,
                    contracts=Contracts(
                        preconditions=preconditions,
                        snapshots=snapshots,
                        postconditions=postconditions,
                    ),
                    non_mutating=non_mutating,
                    body=understood_body,
                    node=node,
                ),
                None,
            )


class _ClassMarker(enum.Enum):
    ABSTRACT = "abstract"
    IMPLEMENTATION_SPECIFIC = "implementation_specific"
    TEMPLATE = "template"


_CLASS_MARKER_FROM_STRING: Mapping[str, _ClassMarker] = {
    marker.value: marker for marker in _ClassMarker
}


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _class_decorator_to_marker(
    decorator: ast.Name,
) -> Tuple[Optional[_ClassMarker], Optional[Error]]:
    """Parse a simple decorator as a class marker."""
    class_marker = _CLASS_MARKER_FROM_STRING.get(decorator.id, None)

    if class_marker is None:
        return (
            None,
            Error(
                decorator,
                f"The handling of the marker has not been "
                f"implemented: {decorator.id!r}",
            ),
        )

    return class_marker, None


# fmt: off
# noinspection PyTypeChecker
@require(
    lambda decorator:
    isinstance(decorator.func, ast.Name)
    and isinstance(decorator.func.ctx, ast.Load)
    and decorator.func.id == 'serialization'
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _class_decorator_to_serialization(
    decorator: ast.Call,
) -> Tuple[Optional[Serialization], Optional[Error]]:
    """Translate a decorator to general serialization settings."""
    with_model_type_node = None  # type: Optional[ast.AST]

    if len(decorator.args) >= 1:
        with_model_type_node = decorator.args[0]

    if len(decorator.keywords) > 0:
        for kwarg in decorator.keywords:
            if kwarg.arg == "with_model_type":
                with_model_type_node = kwarg.value
            else:
                return (
                    None,
                    Error(
                        decorator,
                        f"Handling of the keyword argument {kwarg.arg!r} "
                        f"for the serialization decorator has not been implemented",
                    ),
                )

    with_model_type = None  # type: Optional[bool]
    if with_model_type_node is not None:
        if not isinstance(with_model_type_node, ast.Constant):
            return (
                None,
                Error(
                    with_model_type_node,
                    f"Expected the value for ``with_model_type`` parameter "
                    f"to be a constant, but got: {ast.dump(with_model_type_node)}",
                ),
            )

        if not isinstance(with_model_type_node.value, bool):
            return (
                None,
                Error(
                    with_model_type_node,
                    f"Expected the value for ``with_model_type`` parameter "
                    f"to be a boolean, but got: {with_model_type_node.value!r}",
                ),
            )

        with_model_type = with_model_type_node.value

    return Serialization(with_model_type=with_model_type), None


# fmt: off
# noinspection PyTypeChecker
@require(
    lambda decorator:
    isinstance(decorator.func, ast.Name)
    and isinstance(decorator.func.ctx, ast.Load)
    and decorator.func.id == 'invariant'
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _class_decorator_to_invariant(
    decorator: ast.Call, atok: asttokens.ASTTokens
) -> Tuple[Optional[Invariant], Optional[Error]]:
    """Parse the decorator node as a class invariant."""
    condition_node = None  # type: Optional[ast.AST]
    description_node = None  # type: Optional[ast.AST]

    if len(decorator.args) >= 1:
        condition_node = decorator.args[0]

    if len(decorator.args) >= 2:
        description_node = decorator.args[1]

    if len(decorator.keywords) > 0:
        for kwarg in decorator.keywords:
            if kwarg.arg == "condition":
                condition_node = kwarg.value
            elif kwarg.arg == "description":
                description_node = kwarg.value
            else:
                return (
                    None,
                    Error(
                        decorator,
                        f"Handling of the keyword argument {kwarg.arg!r} "
                        f"for the invariant has not been implemented",
                    ),
                )

    if not isinstance(condition_node, ast.Lambda):
        return (
            None,
            Error(
                decorator,
                f"Expected the condition of an invariant to be a lambda, "
                f"but got {type(condition_node)}: {atok.get_text(decorator)}",
            ),
        )

    if description_node is None:
        return (
            None,
            Error(decorator, "The invariant must have a human-readable description"),
        )

    if not isinstance(description_node, ast.Constant) or not isinstance(
        description_node.value, str
    ):
        return (
            None,
            Error(
                decorator,
                f"Expected the description of an invariant to be "
                f"a string literal, but got: {type(description_node)}",
            ),
        )

    if len(condition_node.args.args) != 1 or condition_node.args.args[0].arg != "self":
        return (
            None,
            Error(
                decorator, "Expected the invariant to have a single argument, ``self``"
            ),
        )

    body, error = _rules.ast_node_to_our_node(node=condition_node.body)
    if error is not None:
        return None, Error(
            condition_node.body, "Failed to parse the invariant", [error]
        )

    assert body is not None

    if not isinstance(body, tree.Expression):
        return None, Error(
            condition_node.body,
            f"Expected an expression in an invariant, but got: {tree.dump(body)}",
        )

    return (
        Invariant(
            description=description_node.value,
            body=body,
            node=decorator,
        ),
        None,
    )


_ClassDecoratorUnion = Union[
    _ClassMarker,
    Serialization,
    Invariant,
]


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _parse_class_decorator(
    decorator: ast.AST, atok: asttokens.ASTTokens
) -> Tuple[Optional[_ClassDecoratorUnion], Optional[Error]]:
    """
    Parse a class decorator.

    The decorator needs to be further interpreted in the context of the class.
    The class here refers to a general Python class, not the concrete or abstract
    class of the meta-model. For example, an enumeration is also defined as a Python
    class inheriting from ``Enum``.
    """
    if isinstance(decorator, ast.Name):
        return _class_decorator_to_marker(decorator=decorator)
    elif isinstance(decorator, ast.Call):
        if not isinstance(decorator.func, ast.Name):
            return None, Error(
                decorator,
                f"Expected a name for a decorator function, "
                f"but got: {ast.dump(decorator.func)}",
            )

        if not isinstance(decorator.func.ctx, ast.Load):
            return None, Error(
                decorator,
                f"Unexpected decorator function in "
                f"a non-Load context: {decorator.func.ctx=}",
            )

        if decorator.func.id == "serialization":
            return _class_decorator_to_serialization(decorator=decorator)
        elif decorator.func.id == "invariant":
            return _class_decorator_to_invariant(decorator=decorator, atok=atok)
        else:
            return None, Error(
                decorator,
                f"We do not know how to handle "
                f"the class decorator: {decorator.func.id}.",
            )
    else:
        return None, Error(
            decorator,
            f"Handling of a non-name or a non-call class decorator "
            f"has not been implemented: {ast.dump(decorator)}",
        )


# noinspection PyTypeChecker,PyUnresolvedReferences
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _classdef_to_enumeration(
    node: ast.ClassDef, atok: asttokens.ASTTokens
) -> Tuple[Optional[Enumeration], Optional[Error]]:
    """Interpret a class which defines an enumeration."""
    for decorator_node in node.decorator_list:
        decorator, error = _parse_class_decorator(decorator=decorator_node, atok=atok)
        if error is not None:
            return None, error
        assert decorator is not None

        return None, Error(
            node,
            f"Unexpected class decorator {decorator} "
            f"for the enumeration {node.name!r}",
        )

    if len(node.body) == 0:
        return (
            Enumeration(
                name=Identifier(node.name),
                literals=[],
                description=None,
                node=node,
            ),
            None,
        )

    enumeration_literals = []  # type: List[EnumerationLiteral]

    description = None  # type: Optional[Description]

    cursor = 0
    while cursor < len(node.body):
        old_cursor = cursor

        body_node = node.body[cursor]  # type: ast.AST

        if cursor == 0 and is_string_expr(body_node):
            assert isinstance(body_node, ast.Expr)
            assert isinstance(body_node.value, ast.Constant)
            description, error = _ast_constant_string_to_description(body_node.value)
            if error is not None:
                return None, error

            cursor += 1

        elif isinstance(body_node, ast.Pass):
            cursor += 1

        elif isinstance(body_node, ast.Assign):
            assign = body_node

            if len(assign.targets) != 1:
                return (
                    None,
                    Error(
                        assign,
                        f"Expected a single target in the assignment, "
                        f"but got: {len(assign.targets)}",
                    ),
                )

            if not isinstance(assign.targets[0], ast.Name):
                return (
                    None,
                    Error(
                        assign.targets[0],
                        f"Expected a name as a target of the assignment, "
                        f"but got: {assign.targets[0]}",
                    ),
                )

            if not isinstance(assign.value, ast.Constant):
                return (
                    None,
                    Error(
                        assign.value,
                        f"Expected a constant in the enumeration assignment, "
                        f"but got: {atok.get_text(assign.value)}",
                    ),
                )

            if not isinstance(assign.value.value, str):
                return (
                    None,
                    Error(
                        assign.value,
                        f"Expected a string literal in the enumeration, "
                        f"but got: {assign.value.value!r}",
                    ),
                )

            literal_name = Identifier(assign.targets[0].id)
            literal_value = assign.value.value

            literal_description = None  # type: Optional[Description]
            next_expr = node.body[cursor + 1] if cursor < len(node.body) - 1 else None

            if next_expr is not None and is_string_expr(next_expr):
                assert isinstance(next_expr, ast.Expr)
                assert isinstance(next_expr.value, ast.Constant)
                literal_description, error = _ast_constant_string_to_description(
                    next_expr.value
                )

                if error is not None:
                    return None, error

                cursor += 1

            enumeration_literals.append(
                EnumerationLiteral(
                    name=literal_name,
                    value=literal_value,
                    description=literal_description,
                    node=assign,
                )
            )

            cursor += 1

        else:

            return (
                None,
                Error(
                    node.body[cursor],
                    f"Expected either a docstring at the beginning or an assignment "
                    f"in an enumeration, "
                    f"but got an unexpected body element at index {cursor} "
                    f"of the class definition {node.name!r}: "
                    f"{atok.get_text(node.body[cursor])}",
                ),
            )

        assert cursor > old_cursor, f"Loop invariant: {cursor=}, {old_cursor=}"

    return (
        Enumeration(
            name=Identifier(node.name),
            literals=enumeration_literals,
            description=description,
            node=node,
        ),
        None,
    )


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _classdef_to_our_type(
    node: ast.ClassDef, atok: asttokens.ASTTokens
) -> Tuple[Optional[OurType], Optional[Error]]:
    """Interpret the class definition as our type."""
    underlying_errors = []  # type: List[Error]

    base_names = []  # type: List[str]
    for base in node.bases:
        if not isinstance(base, ast.Name):
            underlying_errors.append(
                Error(
                    base, f"Expected a base as a name, but got: {atok.get_text(base)}"
                )
            )
        else:
            base_names.append(base.id)

    if len(underlying_errors) > 0:
        return (
            None,
            Error(
                node,
                f"Failed to parse the class definition: {node.name}",
                underlying=underlying_errors,
            ),
        )

    if "Enum" in base_names and len(base_names) > 1:
        return (
            None,
            Error(
                node,
                f"Expected an enumeration to only inherit from ``Enum``, "
                f"but it inherits from: {base_names}",
            ),
        )

    if "Enum" in base_names:
        return _classdef_to_enumeration(node=node, atok=atok)

    # We have to parse the class definition from here on.

    # DBC is only used for inheritance of the contracts in the meta-model
    # so that the developers tinkering with the meta-model can play with it
    # at runtime. We can safely ignore it as we are not looking into any
    # runtime code.
    inheritances = [
        Identifier(base_name) for base_name in base_names if base_name != "DBC"
    ]

    # region Decorators

    invariants = []  # type: List[Invariant]

    is_abstract = False
    is_implementation_specific = False

    serialization = None  # type: Optional[Serialization]

    for decorator_node in node.decorator_list:
        decorator, error = _parse_class_decorator(decorator=decorator_node, atok=atok)
        if error is not None:
            underlying_errors.append(error)
            continue

        assert decorator is not None
        if isinstance(decorator, _ClassMarker):
            if decorator is _ClassMarker.ABSTRACT:
                is_abstract = True
            elif decorator is _ClassMarker.IMPLEMENTATION_SPECIFIC:
                is_implementation_specific = True
            elif decorator is _ClassMarker.TEMPLATE:
                # NOTE (mristin, 2021-11-28):
                # We ignore the template marker at this moment. However, we will most
                # probably have to consider them in the future, so we leave them in the
                # meta-model, but ignore them in the code generation.
                pass

            else:
                assert_never(decorator)

        elif isinstance(decorator, Serialization):
            if serialization is not None:
                underlying_errors.append(
                    Error(decorator_node, "Unexpected double serialization markers")
                )
                continue

            serialization = decorator

        elif isinstance(decorator, Invariant):
            invariants.append(decorator)

        else:
            assert_never(decorator)

    if len(underlying_errors) > 0:
        return (
            None,
            Error(
                node,
                f"Failed to parse the class definition: {node.name}",
                underlying=underlying_errors,
            ),
        )

    # NOTE (mristin, 20222-01-02):
    # We need to inverse the invariants as we collect them top-down, while
    # the decorators are applied bottom-up.
    invariants = list(reversed(invariants))

    # endregion

    if is_abstract and is_implementation_specific:
        return (
            None,
            Error(
                node,
                "Abstract classes can not be implementation-specific "
                "at the same time "
                "(otherwise we can not convert them to interfaces etc.)",
            ),
        )

    description = None  # type: Optional[Description]

    properties = []  # type: List[Property]
    methods = []  # type: List[MethodUnion]

    cursor = 0
    while cursor < len(node.body):
        old_cursor = cursor

        expr = node.body[cursor]

        if cursor == 0 and is_string_expr(expr):
            assert isinstance(expr, ast.Expr)
            assert isinstance(expr.value, ast.Constant)
            description, error = _ast_constant_string_to_description(expr.value)
            if error is not None:
                return None, error

            assert description is not None

            cursor += 1
            continue

        if isinstance(expr, ast.Pass):
            cursor += 1
            continue

        if isinstance(expr, ast.AnnAssign):
            description_of_property = None  # type: Optional[Description]

            next_expr = node.body[cursor + 1] if cursor < len(node.body) - 1 else None
            if next_expr is not None and is_string_expr(next_expr):
                assert isinstance(next_expr, ast.Expr)
                assert isinstance(next_expr.value, ast.Constant)
                description_of_property, error = _ast_constant_string_to_description(
                    next_expr.value
                )

                if error is not None:
                    return None, error

                assert description_of_property is not None

                cursor += 1

            prop, error = _ann_assign_to_property(
                node=expr, description=description_of_property, atok=atok
            )
            cursor += 1

            if error is not None:
                return (
                    None,
                    Error(expr, "Failed to parse a property", underlying=[error]),
                )

            assert prop is not None

            properties.append(prop)

        elif isinstance(expr, ast.FunctionDef):
            method, error = _function_def_to_method(
                node=expr, expect_self=True, atok=atok
            )

            if error is not None:
                return (
                    None,
                    Error(
                        expr,
                        f"Failed to parse the method: {expr.name}",
                        underlying=[error],
                    ),
                )

            assert method is not None
            methods.append(method)

            cursor += 1

        else:
            return (
                None,
                Error(
                    expr,
                    f"Expected only either "
                    f"properties explicitly annotated with types or "
                    f"instance methods, but got: {atok.get_text(expr)}",
                ),
            )

        assert old_cursor < cursor, f"Loop invariant: {old_cursor=}, {cursor=}"

    if is_abstract:
        factory_for_class = (
            AbstractClass
        )  # type: Union[Type[AbstractClass], Type[ConcreteClass]]
    else:
        factory_for_class = ConcreteClass

    return (
        factory_for_class(
            name=Identifier(node.name),
            is_implementation_specific=is_implementation_specific,
            inheritances=inheritances,
            properties=properties,
            methods=methods,
            invariants=invariants,
            serialization=serialization,
            description=description,
            node=node,
        ),
        None,
    )


def _verify_arity_of_type_annotation_subscript(
    type_annotation: SubscriptedTypeAnnotation,
) -> Optional[Error]:
    """
    Check that the subscripted type annotation has the expected number of arguments.

    :return: error message, if any
    """
    if type_annotation.identifier == "Tuple":
        # NOTE (mristin, 2026-09-02):
        # A tuple denotes a fixed-length sequence of possibly heterogeneous types,
        # so, unlike ``List`` or ``Optional``, it has no single expected arity. We
        # only require that at least one element type is given.
        if len(type_annotation.subscripts) < 1:
            return Error(
                type_annotation.node,
                f"Expected at least 1 argument of "
                f"a subscripted type annotation {type_annotation.identifier!r}, "
                f"but got {len(type_annotation.subscripts)}: {type_annotation}",
            )

        return None

    expected_arity_map = {"List": 1, "Optional": 1}
    expected_arity = expected_arity_map.get(type_annotation.identifier, None)
    if expected_arity is None:
        raise AssertionError(
            f"Unexpected subscripted type annotation: {type_annotation}"
        )

    assert expected_arity >= 0
    if len(type_annotation.subscripts) != expected_arity:
        return Error(
            type_annotation.node,
            f"Expected {expected_arity} arguments of "
            f"a subscripted type annotation {type_annotation.identifier!r}, "
            f"but got {len(type_annotation.subscripts)}: {type_annotation}",
        )

    return None


# fmt: off
@ensure(
    lambda result:
    result[1] is None or len(result[1]) > 0,
    "If errors are not None, there must be at least one error"
)
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
# fmt: on
def _verify_symbol_table(
    symbol_table: UnverifiedSymbolTable,
) -> Tuple[Optional[SymbolTable], Optional[List[Error]]]:
    """
    Check that the symbol table is consistent.

    For example, check that there are no dangling references in type annotations or
    inheritances.
    """
    errors = []  # type: List[Error]

    # region Check reserved names

    # NOTE (mristin):
    # These are the types that we use across different generators which would conflict
    # in names in the generated code.
    # noinspection SpellCheckingInspection
    reserved_type_names = {
        "aas",
        "accept",
        "context",
        "class",
        "error",
        "errors",
        "iclass",
        "itransformer_with_context",
        "ivisitor",
        "ivisitor_with_context",
        "jsonization",
        "path",
        "stringification",
        "transform",
        "transformer",
        "transformer_with_context",
        "verification",
        "visit",
        "visitation",
        "visitor",
        "visitor_with_context",
        "match",
        "constants",
        "model_type",
        "enhancement",
        "enhanced",
        "descent",
        "iterator",
        "serialization_error",
        "deserialization_error",
        "verification_error",
    }

    # NOTE (mristin, 2023-06-30):
    # We check against the lower-case to report even if the case is different, so
    # the type names are lower-cased in this set as well.
    for type_name in reserved_type_names:
        assert type_name == type_name.lower(), f"{type_name=}, {type_name.lower()=}"

    reserved_member_names = {
        "descend",
        "descend_once",
        "accept",
        "transform",
        "type_name",
        "property_name",
        "match",
        "model_type",
        "get_model_type",
        "set_model_type",
        "set_enhancement",
        "get_enhancement",
        "enhancement",
    }

    for our_type in symbol_table.our_types:
        if our_type.name.startswith("I_"):
            errors.append(
                Error(
                    our_type.node,
                    f"The prefix ``I_`` in the name of the type is reserved "
                    f"for the code generation: {our_type.name!r}",
                )
            )

        if our_type.name.startswith("Must_"):
            errors.append(
                Error(
                    our_type.node,
                    f"The prefix ``Must_`` in the name of the type is reserved "
                    f"for the code generation: {our_type.name!r}",
                )
            )

        if our_type.name.lower() in reserved_type_names:
            errors.append(
                Error(
                    our_type.node,
                    f"The name of the type is reserved "
                    f"for the code generation: {our_type.name!r}",
                )
            )

        if isinstance(our_type, Class):
            for method in our_type.methods:
                if method.name.lower() in reserved_member_names:
                    errors.append(
                        Error(
                            method.node,
                            f"The name of the method is reserved "
                            f"for the code generation: {method.name!r}",
                        )
                    )

                # noinspection SpellCheckingInspection
                if method.name.lower().startswith("over") and (
                    method.name.lower().endswith("or_empty")
                    or method.name.lower().endswith("orempty")
                ):
                    errors.append(
                        Error(
                            method.node,
                            f"The name of the method is reserved "
                            f"for the code generation of "
                            f'enumerable "Over_X_or_Empty" getters: {method.name!r}',
                        )
                    )

                if method.name.lower().startswith("mutable"):
                    errors.append(
                        Error(
                            method.node,
                            f"The prefix 'mutable' in the name of the method "
                            f"is reserved for the code generation in languages "
                            f"such as C++ which distinguish between "
                            f"mutating and const getters: {method.name!r}",
                        )
                    )

            for prop in our_type.properties:
                if prop.name.lower() in reserved_member_names:
                    errors.append(
                        Error(
                            prop.node,
                            f"The name of the property is reserved "
                            f"for the code generation: {prop.name!r}",
                        )
                    )

                if prop.name.lower().startswith("mutable"):
                    errors.append(
                        Error(
                            prop.node,
                            f"The prefix 'mutable' in the name of the property is "
                            f"reserved for the code generation in languages "
                            f"such as C++ which distinguish between "
                            f"mutating and const getters: {prop.name!r}",
                        )
                    )

    for constant in symbol_table.constants:
        constant_name_lower = constant.name.lower()
        if (
            constant_name_lower in reserved_member_names
            or constant_name_lower in reserved_type_names
        ):
            errors.append(
                Error(
                    constant.node,
                    f"The name of the constant is reserved "
                    f"for the code generation: {constant.name!r}",
                )
            )

    for func in symbol_table.verification_functions:
        func_name_lower = func.name.lower()
        if (
            func_name_lower in reserved_member_names
            or func_name_lower in reserved_type_names
        ):
            errors.append(
                Error(
                    func.node,
                    f"The name of the verification function is reserved "
                    f"for the code generation: {func.name!r}",
                )
            )

    # endregion

    # region Check that there are no duplicate type names

    observed_type_names = dict()  # type: MutableMapping[Identifier, OurType]
    for our_type in symbol_table.our_types:
        another_our_type = observed_type_names.get(our_type.name, None)
        if another_our_type is None:
            observed_type_names[our_type.name] = our_type
        else:
            errors.append(
                Error(
                    our_type.node,
                    f"Our type with the name {our_type.name!r} conflicts with "
                    f"other type with the same name.",
                )
            )

    # endregion

    # region Check that there are no duplicate names of the constants

    observed_constant_names = dict()  # type: MutableMapping[Identifier, Constant]
    for constant in symbol_table.constants:
        another_constant = observed_constant_names.get(constant.name, None)
        if another_constant is None:
            observed_constant_names[constant.name] = constant
        else:
            errors.append(
                Error(
                    constant.node,
                    f"The constant with the name {constant.name!r} conflicts with "
                    f"another constant with the same name.",
                )
            )

    # endregion

    # region Check that there are no duplicate names of the verification functions

    observed_verification_func_names = (
        dict()
    )  # type: MutableMapping[Identifier, FunctionUnion]

    for func in symbol_table.verification_functions:
        another_func = observed_verification_func_names.get(func.name, None)
        if another_func is None:
            observed_verification_func_names[func.name] = func
        else:
            errors.append(
                Error(
                    func.node,
                    f"The verification function with the name {func.name!r} conflicts "
                    f"with another verification function with the same name.",
                )
            )

    # endregion

    if len(errors) > 0:
        return None, errors

    # region Check that imported symbols are not re-assigned in an understood method

    for understood_method in itertools.chain(
        (
            method
            for method in symbol_table.verification_functions
            if isinstance(method, UnderstoodMethod)
        ),
        (
            method
            for our_type in symbol_table.our_types
            if isinstance(our_type, Class)
            for method in our_type.methods
            if isinstance(method, UnderstoodMethod)
        ),
    ):
        for stmt in understood_method.body:
            if (
                isinstance(stmt, tree.Assignment)
                and isinstance(stmt.target, tree.Name)
                and stmt.target.identifier == "match"
            ):
                errors.append(
                    Error(
                        stmt.original_node,
                        "The name ``match`` is reserved "
                        "for the function ``match`` "
                        "imported from the ``re`` module of "
                        "the standard Python library",
                    )
                )

    # endregion

    # region Check that no class methods are used in verification

    for our_type in symbol_table.our_types:
        if not isinstance(our_type, Class):
            continue

        for method in our_type.methods:
            if method.verification:
                errors.append(
                    Error(
                        method.node,
                        f"Unexpected verification function "
                        f"in a class {our_type.name!r}: {method.name!r}",
                    )
                )

    # endregion

    # region Check that only instance methods are non-mutating

    for verification_func in symbol_table.verification_functions:
        if verification_func.non_mutating:
            errors.append(
                Error(
                    verification_func.node,
                    f"Functions can not be non-mutating: {verification_func.name!r}",
                )
            )

    # endregion

    # region Check dangling inheritances

    for our_type in symbol_table.our_types:
        if not isinstance(our_type, Class):
            continue

        for inheritance in our_type.inheritances:
            # NOTE (mristin, 2021-12-22):
            # Inheritance from primitive types allows us to constrain a primitive type.
            if inheritance in PRIMITIVE_TYPES:
                continue

            parent_type = symbol_table.find_our_type(name=inheritance)

            if parent_type is None:
                errors.append(
                    Error(
                        our_type.node,
                        f"A parent of the class {our_type.name!r} "
                        f"is dangling: {inheritance!r}",
                    )
                )

            elif isinstance(parent_type, Class):
                # A class can inherit from a class.
                pass
            else:
                errors.append(
                    Error(
                        our_type.node,
                        f"Expected the class {our_type.name!r} to inherit "
                        f"from another class, "
                        f"but it inherits from our type {parent_type.name!r} which is "
                        f"a {parent_type.__class__.__name__!r}",
                    )
                )

    if len(errors) > 0:
        return None, errors

    # endregion

    # region Check dangling subsets in constant sets

    for constant in symbol_table.constants:
        if not isinstance(constant, ConstantSet):
            continue

        for subset_name in constant.subsets:
            subset = symbol_table.find_constant(name=subset_name)

            if subset is None:
                errors.append(
                    Error(
                        constant.node,
                        f"The subset {subset_name!r} "
                        f"of the constant set {constant.name!r} is dangling",
                    )
                )
            elif not isinstance(subset, ConstantSet):
                errors.append(
                    Error(
                        constant.node,
                        f"The subset {subset_name!r} "
                        f"of the constant set {constant.name!r} is not a constant set, "
                        f"but: {constant.__class__.__name__}",
                    )
                )
            else:
                pass

    # endregion

    # region Check type annotations

    expected_subscripted_types = GENERIC_TYPES

    # NOTE (mristin, 2021-11-19):
    # If you expect type qualifiers such as ``Final``, make a copy of
    # the ``GENERIC_TYPES`` and add them to the copy.

    def verify_no_dangling_references_in_type_annotation(
        type_annotation: TypeAnnotation,
    ) -> Optional[Error]:
        """
        Check that the type annotation contains no dangling references.

        :return: error message, if any
        """
        if isinstance(type_annotation, AtomicTypeAnnotation):
            if type_annotation.identifier in PRIMITIVE_TYPES:
                return None

            if type_annotation.identifier in expected_subscripted_types:
                return Error(
                    type_annotation.node,
                    f"The type annotation is expected with subscript(s), "
                    f"but got none: {type_annotation.identifier}",
                )

            if symbol_table.find_our_type(type_annotation.identifier) is not None:
                return None

            return Error(
                type_annotation.node,
                f"Our type could not be found "
                f"in the symbol table: {type_annotation.identifier}",
            )

        elif isinstance(type_annotation, SubscriptedTypeAnnotation):
            if type_annotation.identifier not in expected_subscripted_types:
                return Error(
                    type_annotation.node,
                    f"Unexpected subscripted type: {type_annotation.identifier}",
                )

            for subscript in type_annotation.subscripts:
                error_in_subscript = verify_no_dangling_references_in_type_annotation(
                    type_annotation=subscript
                )
                if error_in_subscript is not None:
                    return error_in_subscript

            return None

        elif isinstance(type_annotation, SelfTypeAnnotation):
            return None

        else:
            assert_never(type_annotation)

    for our_type in symbol_table.our_types:
        if not isinstance(our_type, Class):
            continue

        for prop in our_type.properties:
            error = verify_no_dangling_references_in_type_annotation(
                type_annotation=prop.type_annotation
            )

            if error is not None:
                errors.append(error)
            else:
                if isinstance(prop.type_annotation, SubscriptedTypeAnnotation):
                    error = _verify_arity_of_type_annotation_subscript(
                        prop.type_annotation
                    )

                    if error is not None:
                        errors.append(error)

        for method in our_type.methods:
            for arg in method.arguments:
                error = verify_no_dangling_references_in_type_annotation(
                    type_annotation=arg.type_annotation
                )

                if error is not None:
                    errors.append(error)
                else:
                    if isinstance(arg.type_annotation, SubscriptedTypeAnnotation):
                        error = _verify_arity_of_type_annotation_subscript(
                            arg.type_annotation
                        )

                        if error is not None:
                            errors.append(error)

            if method.returns is not None:
                error = verify_no_dangling_references_in_type_annotation(
                    type_annotation=method.returns
                )
                if error is not None:
                    errors.append(error)
                else:
                    if isinstance(method.returns, SubscriptedTypeAnnotation):
                        error = _verify_arity_of_type_annotation_subscript(
                            method.returns
                        )

                        if error is not None:
                            errors.append(error)

    for constant in symbol_table.constants:
        if isinstance(constant, ConstantPrimitive):
            pass

        elif isinstance(constant, ConstantSet):
            error = verify_no_dangling_references_in_type_annotation(
                type_annotation=constant.items_type_annotation
            )

            if error is not None:
                errors.append(error)

        else:
            assert_never(constant)

    if len(errors) > 0:
        return None, errors

    # endregion

    if len(errors) > 0:
        return None, errors

    return SymbolTable(symbol_table), None


Symbol = Union[
    AbstractClass,
    ConcreteClass,
    Enumeration,
    ConstantPrimitive,
    ConstantSet,
    UnderstoodMethod,
    ImplementationSpecificMethod,
]


# fmt: off
@ensure(
    lambda result: not (result is not None) or (len(result) >= 1),
    "Either null errors or at least one error"
)
# fmt: on
def _verify_duplicate_names(
    symbols: Iterable[Symbol],
) -> Optional[List[Error]]:
    """Determine the duplicate names in the given sequence of nameable instances."""
    name_set = set()  # type: Set[Identifier]
    errors = []  # type: List[Error]
    for symbol in symbols:
        if symbol.name in name_set:
            errors.append(Error(symbol.node, f"Duplicate for {symbol.name!r}"))
        else:
            name_set.add(symbol.name)

    if len(errors) > 0:
        return errors

    return None


# noinspection PyTypeChecker,PyUnresolvedReferences
@require(lambda atok: isinstance(atok.tree, ast.Module))
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _atok_to_symbol_table(
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[SymbolTable], Optional[Error]]:
    our_types = []  # type: List[OurType]
    underlying_errors = []  # type: List[Error]

    description = None  # type: Optional[Description]
    version = None  # type: Optional[str]
    xml_namespace = None  # type: Optional[Stripped]

    verification_functions = []  # type: List[FunctionUnion]
    constants = []  # type: List[ConstantUnion]

    # region Parse

    assert atok.tree is not None

    for node in atok.tree.body:
        # NOTE (mristin, 2021-12-27):
        # Pass statement makes no sense in our multi-language setting.
        if isinstance(node, ast.Pass):
            continue

        # NOTE (mristin, 2022-07-10):
        # We currently decided to ignore assertions though we leave them in
        # the meta-model as documentation
        if isinstance(node, ast.Assert):
            continue

        # noinspection PyUnusedLocal
        matched = False

        if isinstance(node, ast.ClassDef):
            matched = True

            our_type, our_type_error = _classdef_to_our_type(node=node, atok=atok)
            if our_type_error:
                underlying_errors.append(
                    Error(
                        node,
                        f"Failed to parse the class definition: {node.name}",
                        [our_type_error],
                    )
                )
            else:
                assert our_type is not None
                our_types.append(our_type)

        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            matched = True

            # The first string literal is assumed to be the docstring of the meta-model.
            description, description_error = _ast_constant_string_to_description(
                constant=node.value
            )

            if description_error is not None:
                assert description is None
                underlying_errors.append(description_error)
                continue

        elif isinstance(node, ast.FunctionDef):
            matched = True

            method, error = _function_def_to_method(
                node=node, expect_self=False, atok=atok
            )

            if error is not None:
                underlying_errors.append(error)
                continue

            assert method is not None

            if not method.verification:
                underlying_errors.append(
                    Error(
                        node,
                        f"We do not know how to interpret a non-verification function "
                        f"in the meta-model: {method.name!r}",
                    )
                )

            assert isinstance(method, (UnderstoodMethod, ImplementationSpecificMethod))
            verification_functions.append(method)

        elif isinstance(node, ast.ImportFrom):
            matched = True

            # Ignore import statements
            pass

        elif isinstance(node, ast.Assign):
            if len(node.targets) == 1:
                if (
                    isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    matched = True

                    if node.targets[0].id == "__version__":
                        version = node.value.value
                    elif node.targets[0].id == "__xml_namespace__":
                        if not is_stripped(node.value.value):
                            underlying_errors.append(
                                Error(
                                    node.value,
                                    f"Expected the XML namespace to have no leading "
                                    f"or trailing whitespace: {node.value.value!r}",
                                )
                            )
                            continue

                        if node.value.value.endswith("/"):
                            underlying_errors.append(
                                Error(
                                    node.value,
                                    f"Expected the XML namespace to have no trailing "
                                    f"slash ('/'), but got: {node.value.value!r}",
                                )
                            )
                            continue

                        contains_unexpected_char = False
                        for unexpected_char, unexpected_char_name in [
                            ('"', "double-quote"),
                            ("'", "single-quote"),
                        ]:
                            if unexpected_char in node.value.value:
                                underlying_errors.append(
                                    Error(
                                        node.value,
                                        f"Expected the XML namespace to have no  "
                                        f"{unexpected_char_name} ({unexpected_char!r}),"
                                        f"but got: {node.value.value!r}",
                                    )
                                )
                                contains_unexpected_char = True

                        if contains_unexpected_char:
                            continue

                        xml_namespace = Stripped(node.value.value)
                    else:
                        underlying_errors.append(
                            Error(
                                node,
                                f"We do not know how to interpret "
                                f"the assignment node: {ast.dump(node)}",
                            )
                        )
                        continue
                else:
                    if (
                        isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name)
                        and node.value.func.id.startswith("constant_")
                    ):
                        underlying_errors.append(
                            Error(
                                node,
                                f"We do not know how to interpret "
                                f"the assignment: {atok.get_text(node)}. "
                                f"You probably forgot to specify the type annotation "
                                f"for the constant?",
                            )
                        )
                    else:
                        underlying_errors.append(
                            Error(
                                node,
                                f"We do not know how to interpret "
                                f"the assignment: {atok.get_text(node)}",
                            )
                        )

            elif len(node.targets) > 1:
                underlying_errors.append(
                    Error(
                        node,
                        f"We do not know how to parse a multi-target assignment: "
                        f"{atok.get_text(node)}; in AST: {ast.dump(node)}",
                    )
                )
                continue

        elif isinstance(node, ast.AnnAssign):
            matched = True

            constant, error = _ann_assign_to_constant(node=node, atok=atok)
            if error is not None:
                underlying_errors.append(error)
                continue

            assert constant is not None
            constants.append(constant)
        else:
            matched = False

        if not matched:
            underlying_errors.append(
                Error(
                    node, f"We do not know how to parse the AST node: {ast.dump(node)}"
                )
            )

    if version is None:
        underlying_errors.append(
            Error(
                None,
                "The version (given as assignment to ``__version__``) is missing",
            )
        )

    if xml_namespace is None:
        underlying_errors.append(
            Error(
                None,
                "The XML namespace (given as assignment to ``__xml_namespace__``) "
                "is missing",
            )
        )

    duplicate_name_errors = _verify_duplicate_names(
        itertools.chain(our_types, constants, verification_functions)
    )
    if duplicate_name_errors is not None:
        underlying_errors.append(
            Error(
                None,
                "One or more symbols in the meta-model have duplicate names",
                duplicate_name_errors,
            )
        )

    if len(underlying_errors) > 0:
        return None, Error(None, "Failed to parse the meta-model", underlying_errors)

    # endregion

    assert version is not None
    assert xml_namespace is not None

    unverified_symbol_table = UnverifiedSymbolTable(
        our_types=our_types,
        constants=constants,
        verification_functions=verification_functions,
        meta_model=MetaModel(
            version=version,
            xml_namespace=xml_namespace,
            description=description,
        ),
    )

    symbol_table, verification_errors = _verify_symbol_table(unverified_symbol_table)

    if verification_errors is not None:
        return (
            None,
            Error(
                atok.tree, "Verification of the meta-model failed", verification_errors
            ),
        )

    assert symbol_table is not None
    return symbol_table, None


@require(lambda atok: isinstance(atok.tree, ast.Module))
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def atok_to_symbol_table(
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[SymbolTable], Optional[Error]]:
    """Construct the symbol table based on the parsed AST."""
    table, error = _atok_to_symbol_table(atok=atok)
    if error is not None:
        return None, error

    return table, None
