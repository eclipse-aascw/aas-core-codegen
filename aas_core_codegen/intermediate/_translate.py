"""Translate the parsed representation into the intermediate representation."""
import ast
import collections
import itertools
import re
from typing import (
    Sequence,
    List,
    Optional,
    MutableMapping,
    Tuple,
    Union,
    Iterator,
    TypeVar,
    Generic,
    Final,
    Type,
    Any,
    Set,
    Dict,
    OrderedDict,
    Mapping,
)

import asttokens
import docutils.nodes
import docutils.parsers.rst
import docutils.utils
from icontract import require, ensure, snapshot

from aas_core_codegen import naming, parse
from aas_core_codegen.common import (
    Error,
    Identifier,
    assert_never,
    IDENTIFIER_RE,
    NonEmptyString,
    XMLTagName,
)
from aas_core_codegen.intermediate import (
    _hierarchy,
    construction,
    doc,
    pattern_verification,
)
from aas_core_codegen.intermediate._types import (
    SymbolTable,
    Enumeration,
    EnumerationLiteral,
    PrimitiveType,
    Argument,
    Default,
    DefaultPrimitive,
    Property,
    Invariant,
    Contracts,
    Contract,
    Snapshot,
    Serialization,
    Class,
    Constructor,
    OurType,
    ListTypeAnnotation,
    TupleTypeAnnotation,
    AtomicTypeAnnotationAsTuple,
    OptionalTypeAnnotation,
    OurTypeAnnotation,
    STR_TO_PRIMITIVE_TYPE,
    PrimitiveTypeAnnotation,
    DefaultEnumerationLiteral,
    MetaModel,
    ImplementationSpecificMethod,
    ImplementationSpecificVerification,
    PatternVerification,
    ConstrainedPrimitive,
    ConcreteClass,
    AbstractClass,
    SignatureLike,
    Interface,
    NamedUnion,
    TypeAnnotationUnion,
    ClassUnion,
    VerificationUnion,
    UnderstoodMethod,
    collect_ids_of_our_types_in_properties,
    OurTypeExceptEnumeration,
    DescriptionOfSignature,
    DescriptionOfMetaModel,
    DescriptionOfOurType,
    DescriptionOfProperty,
    DescriptionOfEnumerationLiteral,
    DescriptionUnion,
    find_first_field_list,
    SummaryRemarksConstraintsDescription,
    MethodUnion,
    beneath_optional,
    over_type_annotation_and_nested_type_annotations,
    DescriptionOfConstant,
    ConstantUnion,
    ConstantPrimitive,
    ConstantSetOfPrimitives,
    PRIMITIVE_TYPE_TO_PYTHON_TYPE,
    PYTHON_CONSTANT_TYPE_TO_PRIMITIVE_TYPE,
    PrimitiveSetLiteral,
    ConstantSetOfEnumerationLiterals,
    Constant,
    TranspilableVerification,
    type_annotations_equal,
)
from aas_core_codegen.parse import (
    retree as parse_retree,
    tree as parse_tree,
)

# pylint: disable=unused-argument

_STRIP_SPHINX_FORMATTING_DIRECTIVES_FROM_REFERENCE_RE = re.compile(r"^([!~]+)")


def _strip_sphinx_formatting_directives_from_reference(text: str) -> str:
    """
    Strip Sphinx references formatting prefix from the ``text``.

    See: https://www.sphinx-doc.org/en/master/usage/restructuredtext/roles.html#xref-syntax

    >>> _strip_sphinx_formatting_directives_from_reference('something')
    'something'

    >>> _strip_sphinx_formatting_directives_from_reference('!~something')
    'something'

    >>> _strip_sphinx_formatting_directives_from_reference('!something')
    'something'

    >>> _strip_sphinx_formatting_directives_from_reference('~something')
    'something'
    """
    return _STRIP_SPHINX_FORMATTING_DIRECTIVES_FROM_REFERENCE_RE.sub("", text)


# endregion


class _PlaceholderOurType:
    """Reference something which will be resolved once the table is built."""

    def __init__(self, name: str) -> None:
        """Initialize with the given values."""
        self.name = name

    def __repr__(self) -> str:
        return f"{_PlaceholderOurType.__name__}(name={self.name!r})"


# noinspection PyUnusedLocal
def _role_reference_to_our_type(  # type: ignore
    role, rawtext, text, lineno, inliner, options=None, content=None
) -> Any:
    """Create an element of the description as a reference to our type."""
    # See: https://docutils.sourceforge.io/docs/howto/rst-roles.html
    if options is None:
        options = {}

    # noinspection PyUnresolvedReferences
    options = docutils.parsers.rst.roles.normalize_options(options)

    # NOTE (mristin, 2021-12-27):
    # We need to create a placeholder as the symbol table might not be fully created
    # at the point when we translate the documentation.
    #
    # We have to resolve the placeholders in the second pass of the translation with
    # the actual references to the symbol table.

    name = _strip_sphinx_formatting_directives_from_reference(text)

    # noinspection PyTypeChecker
    node = doc.ReferenceToOurType(
        _PlaceholderOurType(name=name),  # type: ignore
        rawtext,
        docutils.utils.unescape(text),
        refuri=text,
        **options,
    )
    return [node], []


# noinspection RegExpSimplifiable
_REFERENCE_TO_ATTRIBUTE_RE = re.compile(
    r"[a-zA-Z_][a-zA-Z_0-9]*(\.[a-zA-Z_][a-zA-Z_0-9]*)?"
)


class _PlaceholderReferenceToAttribute:
    """
    Represent a placeholder object masking a proper attribute reference.

    The attribute, in this context, refers either to a property of a class or a literal
    of an enumeration. This placeholder needs to be used till we create the symbol
    table in full, so that we can properly de-reference our types.
    """

    @require(lambda path: _REFERENCE_TO_ATTRIBUTE_RE.fullmatch(path))
    def __init__(self, path: str) -> None:
        """Initialize with the given values."""
        self.path = path

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(path={self.path!r})"


# noinspection PyUnusedLocal
def _role_reference_to_attribute(  # type: ignore
    role, rawtext, text, lineno, inliner, options=None, content=None
) -> Any:
    """Create a reference in the documentation to a property or a literal."""
    # See: https://docutils.sourceforge.io/docs/howto/rst-roles.html
    if content is None:
        content = []

    if options is None:
        options = {}

    # noinspection PyUnresolvedReferences
    options = docutils.parsers.rst.roles.normalize_options(options)

    path = _strip_sphinx_formatting_directives_from_reference(text)

    # NOTE (mristin, 2021-12-27):
    # We need to create a placeholder as the symbol table might not be fully created
    # at the point when we translate the documentation.
    #
    # We have to resolve the placeholders in the second pass of the translation with
    # the actual references to the symbol table.

    # noinspection PyTypeChecker
    node = doc.ReferenceToAttribute(
        _PlaceholderReferenceToAttribute(path=path),  # type: ignore
        rawtext,
        docutils.utils.unescape(text),
        refuri=text,
        **options,
    )
    return [node], []


# noinspection PyUnusedLocal
def _role_reference_to_argument(  # type: ignore
    role, rawtext, text, lineno, inliner, options=None, content=None
) -> Any:
    """Create a reference in the documentation to an argument."""
    # See: https://docutils.sourceforge.io/docs/howto/rst-roles.html
    if content is None:
        content = []

    if options is None:
        options = {}

    # noinspection PyUnresolvedReferences
    options = docutils.parsers.rst.roles.normalize_options(options)

    reference = text

    node = doc.ReferenceToArgument(
        reference, rawtext, docutils.utils.unescape(text), refuri=text, **options
    )
    return [node], []


# noinspection PyUnusedLocal
def _role_reference_to_constraint(  # type: ignore
    role, rawtext, text, lineno, inliner, options=None, content=None
) -> Any:
    """Create a reference in the documentation to a constraint."""
    # See: https://docutils.sourceforge.io/docs/howto/rst-roles.html
    if content is None:
        content = []

    if options is None:
        options = {}

    # noinspection PyUnresolvedReferences
    options = docutils.parsers.rst.roles.normalize_options(options)

    reference = text

    node = doc.ReferenceToConstraint(
        reference, rawtext, docutils.utils.unescape(text), refuri=text, **options
    )
    return [node], []


class _PlaceholderReferenceToConstant:
    """
    Represent a placeholder object masking a proper reference to a meta-model constant.

    This placeholder needs to be used till we create the symbol table in full, so that
    we can properly de-reference the constants.
    """

    def __init__(self, name: str) -> None:
        """Initialize with the given values."""
        self.name = name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(path={self.name!r})"


# noinspection PyUnusedLocal
def _role_reference_to_constant(  # type: ignore
    role, rawtext, text, lineno, inliner, options=None, content=None
) -> Any:
    """Create a reference in the documentation to a constant of the meta-model."""
    # See: https://docutils.sourceforge.io/docs/howto/rst-roles.html
    if content is None:
        content = []

    if options is None:
        options = {}

    name = _strip_sphinx_formatting_directives_from_reference(text)

    # NOTE (mristin, 2021-12-27):
    # We need to create a placeholder as the symbol table might not be fully created
    # at the point when we translate the documentation.
    #
    # We have to resolve the placeholders in the second pass of the translation with
    # the actual references to the symbol table.

    # noinspection PyTypeChecker
    node = doc.ReferenceToConstant(
        _PlaceholderReferenceToConstant(name=name),  # type: ignore
        rawtext,
        docutils.utils.unescape(text),
        refuri=text,
        **options,
    )
    return [node], []


# pylint: enable=unused-argument

# The global registration is unfortunate since it is unpredictable and might affect
# other modules, but it is the only way to register the roles.
#
# See: https://docutils.sourceforge.io/docs/howto/rst-roles.html
# noinspection PyUnresolvedReferences
docutils.parsers.rst.roles.register_local_role("class", _role_reference_to_our_type)
# noinspection PyUnresolvedReferences
docutils.parsers.rst.roles.register_local_role("attr", _role_reference_to_attribute)
# noinspection PyUnresolvedReferences
docutils.parsers.rst.roles.register_local_role("paramref", _role_reference_to_argument)
# noinspection PyUnresolvedReferences
docutils.parsers.rst.roles.register_local_role(
    "constraintref", _role_reference_to_constraint
)
# noinspection PyUnresolvedReferences
docutils.parsers.rst.roles.register_local_role("const", _role_reference_to_constant)


# region Descriptions


class _StructuredDescription:
    """Represent a structured description extracted from a docstring."""

    # fmt: off
    @require(
        lambda summary:
        find_first_field_list(summary) is None,
        "Summary expected without field lists"
    )
    @require(
        lambda remarks:
        all(
            find_first_field_list(remark) is None
            for remark in remarks
        ),
        "Remarks expected without field lists"
    )
    @require(
        lambda fields_by_name:
        all(
            find_first_field_list(body) is None
            for body in fields_by_name.values()
        ),
        "Field bodies expected without sub-field lists"
    )
    # fmt: on
    def __init__(
        self,
        summary: docutils.nodes.paragraph,
        remarks: List[docutils.nodes.Element],
        fields_by_name: OrderedDict[str, docutils.nodes.field_body],
    ) -> None:
        """Initialize with the given values."""
        self.summary = summary
        self.remarks = remarks
        self.fields_by_name = fields_by_name


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _extract_structured_description(
    parsed: parse.Description,
) -> Tuple[Optional[_StructuredDescription], Optional[List[Error]]]:
    """Extract structured information from a description."""
    if len(parsed.document.children) == 0:
        return None, [Error(parsed.node, "Unexpected empty description")]

    cursor = iter(parsed.document.children)
    lookahead = next(cursor, None)

    errors = []  # type: List[Error]

    if not isinstance(lookahead, docutils.nodes.paragraph):
        errors.append(
            Error(
                parsed.node,
                f"Expected the first document element to be a summary and "
                f"thus a paragraph, but got: {lookahead}",
            )
        )

    # region Match

    summary = lookahead
    remarks = []  # type: List[docutils.nodes.Element]
    field_list = None  # type: Optional[docutils.nodes.field_list]

    lookahead = next(cursor, None)
    while lookahead is not None:
        if isinstance(lookahead, docutils.nodes.field_list):
            field_list = lookahead
        else:
            assert lookahead is not None
            remarks.append(lookahead)

        lookahead = next(cursor, None)

    if field_list is not None and lookahead is not None:
        errors.append(
            Error(
                parsed.node,
                f"Expected no document elements after the field list, "
                f"but got: {lookahead}",
            )
        )

    # endregion

    # region Check summary and remarks

    assert summary is not None

    field_list_in_summary = next(summary.findall(docutils.nodes.field_list), None)
    if field_list_in_summary is not None:
        errors.append(
            Error(
                parsed.node,
                f"Expected no field lists in the summary, "
                f"but the summary contains one: {field_list_in_summary}",
            )
        )

    for i, remark in enumerate(remarks):
        field_list_in_remark = next(remark.findall(docutils.nodes.field_list), None)
        if field_list_in_remark is not None:
            errors.append(
                Error(
                    parsed.node,
                    f"Expected no field lists in remarks, "
                    f"but the remark {i + 1} contains one: {field_list_in_remark}",
                )
            )

    # endregion

    # region Transform the field list to an ordered dictionary

    fields_by_name = (
        collections.OrderedDict()
    )  # type: OrderedDict[str, docutils.nodes.field_body]

    if field_list is not None:
        for field in field_list.children:
            if len(field.children) != 2:
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected exactly two document elements in a field, "
                        f"but got {len(field.children)}: {field}",
                    )
                )
                continue

            field_name, field_body = field.children
            if not isinstance(field_name, docutils.nodes.field_name):
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected the field name to be a ``field_name``, "
                        f"but got {type(field_name)} : {field_name}",
                    )
                )
                continue
            if not isinstance(field_body, docutils.nodes.field_body):
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected the field body to be a ``field_body``, "
                        f"but got {type(field_body)} : {field_body}",
                    )
                )
                continue

            assert isinstance(field_name, docutils.nodes.field_name)
            assert isinstance(field_body, docutils.nodes.field_body)

            if len(field_name.children) != 1:
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected exactly one sub-element in the field name, "
                        f"but got {len(field_name.children)} : {field_name}",
                    )
                )
                continue

            if not isinstance(field_name.children[0], docutils.nodes.Text):
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected the field name to be text, "
                        f"but got {type(field_name.children[0])} : {field_name}",
                    )
                )
                continue

            name = field_name.children[0].astext()

            field_list_in_body = next(
                field_body.findall(condition=docutils.nodes.field_list), None
            )

            if field_list_in_body is not None:
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected no nested field lists, "
                        f"but got a field list nested "
                        f"under the field {name} : {field_list_in_body}",
                    )
                )
                continue

            fields_by_name[name] = field_body

    # endregion

    if len(errors) > 0:
        return None, errors

    return (
        _StructuredDescription(
            summary=summary, remarks=remarks, fields_by_name=fields_by_name
        ),
        None,
    )


_SummaryRemarksConstraintsDescriptionT = TypeVar(
    "_SummaryRemarksConstraintsDescriptionT", bound=SummaryRemarksConstraintsDescription
)


def _to_summary_remarks_constraints_description(
    parsed: parse.Description, factory: Type[_SummaryRemarksConstraintsDescriptionT]
) -> Tuple[Optional[_SummaryRemarksConstraintsDescriptionT], Optional[List[Error]]]:
    """Translate the description and produce the instance using the ``factory``."""
    structured_desc, structured_desc_errors = _extract_structured_description(
        parsed=parsed
    )
    if structured_desc_errors is not None:
        return None, structured_desc_errors

    assert structured_desc is not None

    errors = []  # type: List[Error]

    constraints_by_identifier = (
        collections.OrderedDict()
    )  # type: OrderedDict[str, docutils.nodes.field_body]

    for name, body in structured_desc.fields_by_name.items():
        parts = name.split()
        if len(parts) != 2:
            errors.append(
                Error(
                    parsed.node,
                    f"Expected only directives such as "
                    f"``constraint some-identifier`` "
                    f"in this context, but got a directive with {len(parts)} part(s): "
                    f"{name}",
                )
            )
            continue

        if parts[0].lower() != "constraint":
            errors.append(
                Error(
                    parsed.node,
                    f"Expected only directives such as "
                    f"``constraint some-identifier`` "
                    f"in this context, but got a directive with "
                    f"the first part {parts[0]!r}: {name}",
                )
            )
            continue

        constraint_id = parts[1]

        if constraint_id in constraints_by_identifier:
            errors.append(
                Error(
                    parsed.node,
                    f"Expected all constraints to have unique identifiers, "
                    f"but two or more constraints share "
                    f"the identifier: {constraint_id}",
                )
            )

        constraints_by_identifier[constraint_id] = body

    if len(errors) > 0:
        return None, errors

    return (
        factory(
            summary=structured_desc.summary,
            remarks=structured_desc.remarks,
            constraints_by_identifier=constraints_by_identifier,
            parsed=parsed,
        ),
        None,
    )


def _to_description_of_meta_model(
    parsed: parse.Description,
) -> Tuple[Optional[DescriptionOfMetaModel], Optional[List[Error]]]:
    """Structure the information from the docstring of the meta-model."""
    return _to_summary_remarks_constraints_description(
        parsed=parsed, factory=DescriptionOfMetaModel
    )


def _to_description_of_our_type(
    parsed: parse.Description,
) -> Tuple[Optional[DescriptionOfOurType], Optional[List[Error]]]:
    """Structure the information from the docstring of our type."""
    return _to_summary_remarks_constraints_description(
        parsed=parsed, factory=DescriptionOfOurType
    )


def _to_description_of_property(
    parsed: parse.Description,
) -> Tuple[Optional[DescriptionOfProperty], Optional[List[Error]]]:
    """Translate the description into a structured property description."""
    return _to_summary_remarks_constraints_description(
        parsed=parsed, factory=DescriptionOfProperty
    )


def _to_description_of_enumeration_literal(
    parsed: parse.Description,
) -> Tuple[Optional[DescriptionOfEnumerationLiteral], Optional[List[Error]]]:
    """Translate ``parsed`` into a structured description of an enumeration literal."""
    structured_desc, structured_desc_errors = _extract_structured_description(
        parsed=parsed
    )
    if structured_desc_errors is not None:
        return None, structured_desc_errors
    assert structured_desc is not None

    field_list = next(parsed.document.findall(docutils.nodes.field_list), None)
    if field_list is not None:
        return None, [
            Error(
                parsed.node,
                f"Expected no field list in a description of an enumeration literal, "
                f"but got at least one: {field_list}",
            )
        ]

    assert (
        len(structured_desc.fields_by_name) == 0
    ), "Expected to match the previous findall"

    return (
        DescriptionOfEnumerationLiteral(
            summary=structured_desc.summary,
            remarks=structured_desc.remarks,
            parsed=parsed,
        ),
        None,
    )


_DocElementT = TypeVar("_DocElementT", bound=docutils.nodes.Element)


def _find_all_in_description_of_signature(
    element_type: Type[_DocElementT], description: DescriptionOfSignature
) -> Iterator[_DocElementT]:
    """
    Iterate over all the fields of the description and yield the desired elements.

    We also return the description for the client to report errors etc.
    """
    yield from description.summary.findall(element_type)

    for remark in description.remarks:
        yield from remark.findall(element_type)

    for arg_description in description.arguments_by_name.values():
        # noinspection PyUnresolvedReferences
        yield from arg_description.findall(element_type)

    if description.returns is not None:
        yield from description.returns.findall(element_type)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_description_of_signature(
    parsed: parse.Description,
    arguments: Sequence["Argument"],
    returns: Optional[TypeAnnotationUnion],
) -> Tuple[Optional[DescriptionOfSignature], Optional[List[Error]]]:
    """Translate ``parsed`` into a structured description of a signature."""
    structured_desc, structured_desc_errors = _extract_structured_description(
        parsed=parsed
    )
    if structured_desc_errors is not None:
        return None, structured_desc_errors
    assert structured_desc is not None

    errors = []  # type: List[Error]

    argument_descriptions_by_name = (
        collections.OrderedDict()
    )  # type: OrderedDict[Identifier, docutils.nodes.field_body]

    returns_description = None  # type: Optional[docutils.nodes.field_body]

    for name, body in structured_desc.fields_by_name.items():
        parts = name.split()
        if len(parts) > 2:
            errors.append(
                Error(
                    parsed.node, f"Unexpected field name with more than 2 parts: {name}"
                )
            )
            continue

        directive = parts[0]
        if directive.lower() == "param":
            arg_name = parts[1]
            if not IDENTIFIER_RE.fullmatch(arg_name):
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected the argument name to be a valid identifier, "
                        f"but got: {arg_name}",
                    )
                )
                continue

            if arg_name in argument_descriptions_by_name:
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected non-duplicate argument descriptions, "
                        f"but got two or more for the argument {arg_name!r}",
                    )
                )
                continue

            argument_descriptions_by_name[Identifier(arg_name)] = body

        elif directive.lower() in ("return", "returns"):
            if len(parts) > 1:
                errors.append(
                    Error(
                        parsed.node,
                        f"Expected return field without additional parts, "
                        f"but got: {parts[1:]}",
                    )
                )
                continue

            if returns_description is not None:
                errors.append(
                    Error(
                        parsed.node,
                        "Expected a single ``return`` field, but got two or more",
                    )
                )
                continue

            returns_description = body
        else:
            errors.append(Error(parsed.node, f"Unexpected field: {name}"))
            continue

    if returns is None and returns_description is not None:
        errors.append(
            Error(
                parsed.node,
                f"No return value is specified, "
                f"but the return value is in the description: {returns_description}",
            )
        )

    arg_name_set = {arg.name for arg in arguments}
    for arg_name, arg_description in argument_descriptions_by_name.items():
        if arg_name not in arg_name_set:
            errors.append(
                Error(
                    parsed.node,
                    f"The argument {arg_name} has not been specified, "
                    f"but is listed in the description: {arg_description}",
                )
            )

    description = DescriptionOfSignature(
        summary=structured_desc.summary,
        remarks=structured_desc.remarks,
        arguments_by_name=argument_descriptions_by_name,
        returns=returns_description,
        parsed=parsed,
    )

    for arg_ref_in_doc in _find_all_in_description_of_signature(
        element_type=doc.ReferenceToArgument, description=description
    ):
        assert isinstance(arg_ref_in_doc.reference, str)

        arg_name = arg_ref_in_doc.reference
        if arg_name not in arg_name_set:
            errors.append(
                Error(
                    parsed.node,
                    f"The argument referenced in the description "
                    f"is not listed as an argument: {arg_name!r}",
                )
            )

    if len(errors) > 0:
        return None, errors

    return description, None


def _to_description_of_constant(
    parsed: parse.Description,
) -> Tuple[Optional[DescriptionOfConstant], Optional[List[Error]]]:
    """Translate ``parsed`` into a structured description of a constant."""
    structured_desc, structured_desc_errors = _extract_structured_description(
        parsed=parsed
    )
    if structured_desc_errors is not None:
        return None, structured_desc_errors
    assert structured_desc is not None

    field_list = next(parsed.document.findall(docutils.nodes.field_list), None)
    if field_list is not None:
        return None, [
            Error(
                parsed.node,
                f"Expected no field list in a description of a constant, "
                f"but got at least one: {field_list}",
            )
        ]

    assert (
        len(structured_desc.fields_by_name) == 0
    ), "Expected to match the previous findall"

    return (
        DescriptionOfConstant(
            summary=structured_desc.summary,
            remarks=structured_desc.remarks,
            parsed=parsed,
        ),
        None,
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_enumeration_literal(
    parsed: parse.EnumerationLiteral,
) -> Tuple[Optional[EnumerationLiteral], Optional[List[Error]]]:
    """Translate the enumeration literal from the meta-model."""
    description = None  # type: Optional[DescriptionOfEnumerationLiteral]

    if parsed.description is not None:
        description, description_errors = _to_description_of_enumeration_literal(
            parsed.description
        )
        if description_errors is not None:
            return None, description_errors

    return (
        EnumerationLiteral(
            name=parsed.name,
            value=parsed.value,
            description=description,
            parsed=parsed,
        ),
        None,
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_enumeration(
    parsed: parse.Enumeration,
) -> Tuple[Optional[Enumeration], Optional[List[Error]]]:
    """Translate an enumeration from the meta-model to an intermediate enumeration."""
    errors = []  # type: List[Error]

    description = None  # type: Optional[DescriptionOfOurType]
    if parsed.description is not None:
        description, description_errors = _to_description_of_our_type(
            parsed.description
        )
        if description_errors is not None:
            errors.extend(description_errors)

    literals = []  # type: List[EnumerationLiteral]
    for parsed_literal in parsed.literals:
        literal, literal_errors = _to_enumeration_literal(parsed_literal)
        if literal_errors is not None:
            errors.append(
                Error(
                    parsed_literal.node,
                    f"Failed to parse the enumeration literal {parsed_literal.name!r}",
                    literal_errors,
                )
            )
            continue

        assert literal is not None
        literals.append(literal)

    if len(errors) > 0:
        return None, errors

    return (
        Enumeration(
            name=parsed.name,
            literals=literals,
            description=description,
            parsed=parsed,
        ),
        None,
    )


def _to_named_union(
    parsed: parse.NamedUnion,
) -> Tuple[Optional[NamedUnion], Optional[List[Error]]]:
    """Translate a named union from the meta-model to an intermediate named union."""
    # NOTE (mristin):
    # The parse stage does not support descriptions on named unions yet (there is
    # no established meta-model syntax to attach one to a plain module-level
    # assignment), so we always translate to ``None`` here.
    #
    # The members of the union are resolved in a later, second pass (see
    # ``_second_pass_to_resolve_named_union_members_in_place``) as the meta-model
    # may contain forward references which can not be resolved at this point.
    return (
        NamedUnion(
            name=parsed.name,
            description=None,
            parsed=parsed,
        ),
        None,
    )


def _to_type_annotation(
    parsed: parse.TypeAnnotation,
) -> TypeAnnotationUnion:
    """
    Translate parsed type annotations to possibly unresolved type annotation.

    We need a two-pass translation to translate atomic type annotations to
    intermediate ones. Namely, we are translating the type annotations as we are
    building the symbol table. At that point, the atomic type annotations referring to
    meta-model classes can not be resolved (as the symbol table is not completely
    built yet). Therefore, we use placeholders which are eventually resolved in the
    second pass.
    """
    if isinstance(parsed, parse.AtomicTypeAnnotation):
        primitive_type = STR_TO_PRIMITIVE_TYPE.get(parsed.identifier, None)

        if primitive_type is not None:
            return PrimitiveTypeAnnotation(a_type=primitive_type, parsed=parsed)

        # noinspection PyTypeChecker
        return OurTypeAnnotation(
            our_type=_PlaceholderOurType(name=parsed.identifier),  # type: ignore
            parsed=parsed,
        )

    elif isinstance(parsed, parse.SubscriptedTypeAnnotation):
        if parsed.identifier == "List":
            assert len(parsed.subscripts) == 1, (
                f"Expected exactly one subscript for the List type annotation, "
                f"but got: {parsed}; this should have been caught before!"
            )

            return ListTypeAnnotation(
                items=_to_type_annotation(parsed.subscripts[0]),
                parsed=parsed,
            )

        elif parsed.identifier == "Optional":
            assert len(parsed.subscripts) == 1, (
                f"Expected exactly one subscript for the Optional type annotation, "
                f"but got: {parsed}; this should have been caught before!"
            )

            return OptionalTypeAnnotation(
                value=_to_type_annotation(parsed.subscripts[0]),
                parsed=parsed,
            )

        elif parsed.identifier == "Tuple":
            assert len(parsed.subscripts) >= 1, (
                f"Expected at least one subscript for the Tuple type annotation, "
                f"but got: {parsed}; this should have been caught before!"
            )

            return TupleTypeAnnotation(
                items=[
                    _to_type_annotation(subscript) for subscript in parsed.subscripts
                ],
                parsed=parsed,
            )

        else:
            raise AssertionError(
                f"Unexpected subscripted type annotation identifier: "
                f"{parsed.identifier}. "
                f"This should have been handled or caught before!"
            )

    elif isinstance(parsed, parse.SelfTypeAnnotation):
        raise AssertionError(
            f"Unexpected self type annotation in the intermediate layer: {parsed}"
        )

    else:
        assert_never(parsed)

    raise AssertionError("Should not have gotten here")


class _DefaultPlaceholder:
    """Hold a place for postponed translation of the default values.

    We can not translate the default argument values immediately while we are
    constructing the symbol table as they might reference, *e.g.*, enumeration
    literals which we still did not observe.

    Therefore, we insert a placeholder and resolve the default values in the second
    translation pass.
    """

    def __init__(self, parsed: parse.Default) -> None:
        """Initialize with the given values."""
        self.parsed = parsed


def _to_arguments(parsed: Sequence[parse.Argument]) -> List[Argument]:
    """Translate the arguments of a method in meta-model to the intermediate ones."""
    return [
        Argument(
            name=parsed_arg.name,
            type_annotation=_to_type_annotation(parsed_arg.type_annotation),
            default=(
                _DefaultPlaceholder(parsed=parsed_arg.default)  # type: ignore
                if parsed_arg.default is not None
                else None
            ),
            parsed=parsed_arg,
        )
        for parsed_arg in parsed
        if not isinstance(parsed_arg.type_annotation, parse.SelfTypeAnnotation)
    ]


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_property(
    parsed: parse.Property, parsed_cls: parse.Class
) -> Tuple[Optional[Property], Optional[List[Error]]]:
    """Translate a parsed property of a class to an intermediate one."""
    description = None  # type: Optional[DescriptionOfProperty]

    if parsed.description is not None:
        description, description_errors = _to_description_of_property(
            parsed.description
        )
        if description_errors is not None:
            return None, description_errors

    json_name = (
        parsed.json_name
        if parsed.json_name is not None
        else NonEmptyString(naming.json_property(parsed.name))
    )
    xml_name = (
        parsed.xml_name
        if parsed.xml_name is not None
        else XMLTagName(naming.xml_property(parsed.name))
    )

    # noinspection PyTypeChecker
    return (
        Property(
            name=parsed.name,
            type_annotation=_to_type_annotation(parsed.type_annotation),
            description=description,
            # NOTE (mristin, 2021-12-26):
            # We can only resolve the ``specified_for`` when the class is actually
            # created. Therefore, we assign here a placeholder and fix it later
            # in a second pass.
            specified_for=_PlaceholderOurType(parsed_cls.name),  # type: ignore
            json_name=json_name,
            xml_name=xml_name,
            parsed=parsed,
        ),
        None,
    )


def _to_contracts(parsed: parse.Contracts) -> Contracts:
    """Translate the parsed contracts into intermediate ones."""
    return Contracts(
        preconditions=[
            Contract(
                args=parsed_pre.args,
                description=parsed_pre.description,
                body=parsed_pre.body,
                parsed=parsed_pre,
            )
            for parsed_pre in parsed.preconditions
        ],
        snapshots=[
            Snapshot(
                args=parsed_snap.args,
                body=parsed_snap.body,
                name=parsed_snap.name,
                parsed=parsed_snap,
            )
            for parsed_snap in parsed.snapshots
        ],
        postconditions=[
            Contract(
                args=parsed_post.args,
                description=parsed_post.description,
                body=parsed_post.body,
                parsed=parsed_post,
            )
            for parsed_post in parsed.postconditions
        ],
    )


# fmt: off
@require(
    lambda parsed:
    parsed.name != "__init__",
    "Constructors are expected to be handled in a special way"
)
@require(
    lambda parsed:
    'self' in parsed.arguments_by_name,
    "Expected ``self`` argument in the ``parsed`` since it is a genuine class method"
)
@require(
    lambda parsed:
    not parsed.verification,
    "Expected only non-verification methods"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_method(
        parsed: Union[parse.UnderstoodMethod, parse.ImplementationSpecificMethod],
        parsed_cls: parse.Class
) -> Tuple[
    Optional[Union[UnderstoodMethod, ImplementationSpecificMethod]],
    Optional[List[Error]]
]:
    """Translate the parsed method into an intermediate representation."""
    arguments = _to_arguments(parsed=parsed.arguments)

    returns = (
        None
        if parsed.returns is None
        else _to_type_annotation(parsed.returns)
    )

    # fmt: on
    description = None  # type: Optional[DescriptionOfSignature]
    if parsed.description:
        description, description_errors = _to_description_of_signature(
            parsed=parsed.description,
            arguments=arguments,
            returns=returns
        )
        if description_errors is not None:
            return None, description_errors

    # NOTE (mristin, 2021-12-26):
    # We can only resolve the ``specified_for`` when the class is actually
    # created. Therefore, we assign here a placeholder and fix it later in a second
    # pass.
    specified_for_placeholder = _PlaceholderOurType(parsed_cls.name)

    contracts = _to_contracts(parsed.contracts)

    if isinstance(parsed, parse.ImplementationSpecificMethod):
        # noinspection PyTypeChecker
        return ImplementationSpecificMethod(
            name=parsed.name,
            arguments=arguments,
            returns=returns,
            description=description,
            specified_for=specified_for_placeholder,  # type: ignore
            contracts=contracts,
            non_mutating=parsed.non_mutating,
            parsed=parsed,
        ), None
    elif isinstance(parsed, parse.UnderstoodMethod):
        # noinspection PyTypeChecker
        return UnderstoodMethod(
            name=parsed.name,
            arguments=arguments,
            returns=returns,
            description=description,
            specified_for=specified_for_placeholder,  # type: ignore
            contracts=contracts,
            non_mutating=parsed.non_mutating,
            body=parsed.body,
            parsed=parsed,
        ), None
    else:
        assert_never(parsed)

    raise AssertionError("Should have never gotten here")


# fmt: off
@ensure(
    lambda parsed_symbol_table, result:
    not (result[1] is not None)
    or (
            all(
                isinstance(
                    parsed_symbol_table.must_find_class(identifier),
                    parse.ConcreteClass)
                for identifier in result[1]
            )
    ),
    "Constrained primitive types must be concrete classes"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _determine_constrained_primitives_by_name(
    parsed_symbol_table: parse.SymbolTable,
    ontology: _hierarchy.Ontology,
) -> Tuple[Optional[MutableMapping[Identifier, PrimitiveType]], Optional[List[Error]]]:
    """
    Determine which classes are constraining a primitive type.

    We also catch errors in case one or more definitions are incorrect.
    For example, if a class that inherits from a primitive type also specifies
    properties or methods.
    """
    # NOTE (mristin, 2022-03-18):
    # While we perform different stackings in second passes, we can not stack the
    # constrainees in the second pass since we need to determine whether a class is a
    # constrained primitive *or* an abstract or a concrete class.

    # NOTE (mristin, 2021-12-22):
    # We consider two sets of constrained primitives. The first set is
    # the initial set that constraints the primitive. The second set, the extended
    # set, is a set of constrained primitive types which inherit from one or
    # more initial ones.
    #
    # We collect the sets in two passes. We collect the initial set in the first pass.
    # Then, in the second pass, we propagate the "is-constrained-primitive-type"
    # through the class hierarchy.

    errors = []  # type: List[Error]

    initial_map = (
        collections.OrderedDict()
    )  # type: MutableMapping[Identifier, PrimitiveType]

    # region First pass to determine the initial set

    for parsed_our_type in parsed_symbol_table.our_types:
        if not isinstance(parsed_our_type, parse.Class):
            continue

        if any(
            parent in parse.PRIMITIVE_TYPES for parent in parsed_our_type.inheritances
        ):
            if len(parsed_our_type.inheritances) > 1:
                errors.append(
                    Error(
                        parsed_our_type.node,
                        f"The class {parsed_our_type.name!r} constrains "
                        f"a primitive type, but also inherits from other classes: "
                        f"{parsed_our_type.inheritances}. We do not know how "
                        f"to generate an implementation for that.",
                    )
                )
                continue

            assert parsed_our_type.name not in initial_map
            initial_map[parsed_our_type.name] = STR_TO_PRIMITIVE_TYPE[
                parsed_our_type.inheritances[0]
            ]

    if len(errors) > 0:
        return None, errors

    # endregion

    # region Second pass to propagate from the initial set

    # NOTE (mristin, 2021-12-23):
    # Find the connected component from all the classes of the initial set.
    # See https://en.wikipedia.org/wiki/Component_(graph_theory)

    # Put all the descendants of the initial set on the stack
    stack = []  # type: List[Tuple[Identifier, PrimitiveType, Identifier]]

    for identifier_of_the_initial, constrainee_of_the_initial in initial_map.items():
        parsed_cls = parsed_symbol_table.must_find_class(name=identifier_of_the_initial)

        for descendant in ontology.list_descendants(parsed_cls):
            stack.append(
                (descendant.name, constrainee_of_the_initial, identifier_of_the_initial)
            )

    # Propagate the constrainees through the ontology

    # Map: identifier 🠒 determined primitive type, the ancestor which determined it
    extended_map = (
        collections.OrderedDict()
    )  # type: MutableMapping[Identifier, Tuple[PrimitiveType, Identifier]]

    while len(stack) > 0 and len(errors) == 0:
        # NOTE (mristin, 2021-12-23):
        # Since we operate on the ontology, we know that the cycles in the inheritance
        # graph would have been already reported as errors, and we would not get
        # thus far.

        identifier, constrainee, ancestor = stack.pop()
        parsed_cls = parsed_symbol_table.must_find_class(name=identifier)

        already_determined_constrainee_and_another_ancestor = extended_map.get(
            identifier, None
        )

        if already_determined_constrainee_and_another_ancestor is not None:
            (
                already_determined_constrainee,
                another_ancestor,
            ) = already_determined_constrainee_and_another_ancestor

            if (
                already_determined_constrainee is not None
                and already_determined_constrainee != constrainee
            ):
                errors.append(
                    Error(
                        parsed_cls.node,
                        f"The primitive type of the constrained primitive type "
                        f"{identifier!r} can not be resolved. The ancestor "
                        f"{ancestor!r} specifies {constrainee.value!r}, while "
                        f"another ancestor, {another_ancestor!r}, specifies "
                        f"{already_determined_constrainee.value!r}",
                    )
                )

        else:
            extended_map[identifier] = (constrainee, ancestor)

        for descendant in ontology.list_descendants(parsed_cls):
            stack.append((descendant.name, constrainee, identifier))

    if len(errors) > 0:
        return None, errors

    # endregion

    # region Convert the initial and extended map into one

    result = (
        collections.OrderedDict()
    )  # type: MutableMapping[Identifier, PrimitiveType]

    for identifier, constrainee in initial_map.items():
        result[identifier] = constrainee

    for identifier, (constrainee, _) in extended_map.items():
        result[identifier] = constrainee

    # endregion

    # region Check the inheritances of all the constrained primitive types

    for identifier in extended_map.keys():
        # We know for sure that the initial set is valid, so we can skip it in
        # the check.
        if identifier in initial_map:
            continue

        parsed_cls = parsed_symbol_table.must_find_class(name=identifier)

        # Make sure that the constrained primitive types only inherit from other
        # constrained primitive types

        constrained_inheritances = []  # type: List[Identifier]
        unexpected_inheritances = []  # type: List[Identifier]

        for inheritance in parsed_cls.inheritances:
            if inheritance not in result:
                unexpected_inheritances.append(inheritance)
            else:
                constrained_inheritances.append(inheritance)

        if len(unexpected_inheritances) > 0:
            constrained_inheritances_str = ", ".join(
                repr(identifier) for identifier in constrained_inheritances
            )

            unexpected_inheritances_str = ", ".join(
                repr(identifier) for identifier in unexpected_inheritances
            )
            errors.append(
                Error(
                    parsed_cls.node,
                    f"The class {parsed_cls.name} inherits both from one or more "
                    f"constrained primitive types ({constrained_inheritances_str}), "
                    f"but also other classes which are not constraining primitive "
                    f"types ({unexpected_inheritances_str}).",
                )
            )

    if len(errors) > 0:
        return None, errors

    # endregion

    # region Check that primitive types do not have unexpected specification

    for identifier in result:
        parsed_cls = parsed_symbol_table.must_find_class(identifier)
        if len(parsed_cls.methods) > 0 or len(parsed_cls.properties) > 0:
            errors.append(
                Error(
                    parsed_cls.node,
                    f"The class {parsed_cls.name!r} constrains a primitive type, "
                    f"but also specifies properties and/or methods. "
                    f"We do not know how to generate an implementation for that.",
                )
            )

        if parsed_cls.serialization is not None:
            errors.append(
                Error(
                    parsed_cls.node,
                    f"The class {parsed_cls.name!r} constrains a primitive type, "
                    f"but the serialization settings are set. We must "
                    f"serialize it as a primitive type and no custom serialization "
                    f"settings are possible.",
                )
            )

        if isinstance(parsed_cls, parse.AbstractClass):
            errors.append(
                Error(
                    parsed_cls.node,
                    f"The class {parsed_cls.name!r} constrains a primitive type, "
                    f"but it is denoted abstract. Every value that "
                    f"fulfills the constraints can be instantiated, so it can not be "
                    f"made abstract.",
                )
            )

    # endregion

    return result, None


class _CheckCodeUsesReVisitor(parse_tree.Visitor):
    """Check whether the code uses ``re`` module."""

    def __init__(self) -> None:
        self.first_re_usage = None  # type: Optional[parse_tree.Node]
        self._variable_name_set = set()  # type: Set[str]

    def visit(self, node: parse_tree.Node) -> None:
        if self.first_re_usage is not None:
            return

        super().visit(node)

    def visit_name(self, node: parse_tree.Name) -> None:
        if node.identifier == "re" and node.identifier not in self._variable_name_set:
            self.first_re_usage = node

    def _visit_any_or_all(self, node: Union[parse_tree.Any, parse_tree.All]) -> None:
        if self.first_re_usage is not None:
            return

        loop_variable_name = node.generator.variable.identifier
        try:
            self._variable_name_set.add(loop_variable_name)
            self.visit(node.generator)
            self.visit(node.condition)
        finally:
            self._variable_name_set.remove(loop_variable_name)

    def visit_any(self, node: parse_tree.Any) -> None:
        self._visit_any_or_all(node)

    def visit_all(self, node: parse_tree.All) -> None:
        self._visit_any_or_all(node)

    def visit_assignment(self, node: parse_tree.Assignment) -> None:
        if isinstance(node.target, parse_tree.Name):
            self._variable_name_set.add(node.target.identifier)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_invariant(
    parsed: parse.Invariant, placeholder_for_our_type: _PlaceholderOurType
) -> Tuple[Optional[Invariant], Optional[Error]]:
    """
    Translate the parsed invariant to the invariant.

    Notably, we already perform some checks to ensure that the invariant can be
    transpiled later in the generation stage.
    """
    check_code_uses_re_visitor = _CheckCodeUsesReVisitor()
    check_code_uses_re_visitor.visit(parsed.body)

    if check_code_uses_re_visitor.first_re_usage is not None:
        return None, Error(
            check_code_uses_re_visitor.first_re_usage.original_node,
            "We can not transpile the usage of ``re`` directly to "
            "the target implementation. Please refactor the invariant such that it "
            "calls a pattern verification function.",
        )

    return (
        Invariant(
            description=parsed.description,
            body=parsed.body,
            specified_for=placeholder_for_our_type,  # type: ignore
            parsed=parsed,
        ),
        None,
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_constrained_primitive(
    parsed: parse.ConcreteClass, constrainee: PrimitiveType
) -> Tuple[Optional[ConstrainedPrimitive], Optional[List[Error]]]:
    """
    Translate a concrete class to a constrained primitive.

    The ``parsed`` is expected to be tested for a valid constrained primitive
    before calling this function.

    The ``constrainee`` is determined by propagation in
    :py:func:`_determine_constrained_primitives_by_name`.
    """
    errors = []  # type: List[Error]

    invariants = []
    for parsed_invariant in parsed.invariants:
        invariant, error = _to_invariant(
            parsed=parsed_invariant,
            placeholder_for_our_type=_PlaceholderOurType(parsed.name),
        )
        if error is not None:
            errors.append(error)
        else:
            assert invariant is not None
            invariants.append(invariant)

    description = None  # type: Optional[DescriptionOfOurType]

    if parsed.description is not None:
        description, description_errors = _to_description_of_our_type(
            parsed.description
        )
        if description_errors is not None:
            errors.extend(description_errors)

    if len(errors) > 0:
        return None, errors

    # noinspection PyTypeChecker
    return (
        ConstrainedPrimitive(
            name=parsed.name,
            # Use placeholders for inheritances, ancestors and descendants as we are
            # still in the first pass and building up the symbol table. They will be
            # resolved in a second pass.
            inheritances=[],
            ancestors=[],
            descendants=[],
            constrainee=constrainee,
            is_implementation_specific=parsed.is_implementation_specific,
            invariants=invariants,
            description=description,
            parsed=parsed,
        ),
        None,
    )


class _MaybeInterfacePlaceholder:
    """
    Represent a placeholder for the interfaces.

    We do not know in the first pass whether a class will have an interface defined
    or not.
    """


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _extract_constructor(
    parsed_class: parse.ClassUnion,
    constructor_statements: Sequence[construction.Statement],
) -> Tuple[Optional[Constructor], Optional[List[Error]]]:
    """
    Extract the constructor from the given ``parsed_class``.

    The ``constructor_statements`` are determined by the constructor table. The calls
    to super-constructors are not expected to be in-lined yet.
    """
    contracts = Contracts(preconditions=[], snapshots=[], postconditions=[])
    arguments = []  # type: List[Argument]
    init_is_implementation_specific = False
    description = None  # type: Optional[DescriptionOfSignature]

    errors = []  # type: List[Error]

    parsed_class_init = parsed_class.methods_by_name.get(Identifier("__init__"), None)
    if parsed_class_init is not None:
        arguments = _to_arguments(parsed=parsed_class_init.arguments)

        init_is_implementation_specific = isinstance(
            parsed_class_init, parse.ImplementationSpecificMethod
        )

        contracts = _to_contracts(parsed_class_init.contracts)

        if parsed_class_init.description is not None:
            (description, description_errors,) = _to_description_of_signature(
                parsed=parsed_class_init.description, arguments=arguments, returns=None
            )
            if description_errors is not None:
                errors.extend(description_errors)

    if len(errors) > 0:
        return None, errors

    constructor = Constructor(
        is_implementation_specific=init_is_implementation_specific,
        arguments=arguments,
        contracts=contracts,
        description=description,
        statements=constructor_statements,
        # NOTE (mristin, 2022-03-19):
        # We ignore the ``Final`` here for the moment and will later in-line
        # ``statements`` to ``inlined_statements`` in the
        # :py:func:`_second_pass_to_stack_constructors` only once we have the whole
        # inheritance hierarchy translated.
        #
        # The qualifier ``Final`` refers in this context rather to the callers outside
        # the module than to the callers inside the module.
        inlined_statements=[],
        parsed=(parsed_class_init if parsed_class_init is not None else None),
    )

    return constructor, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_class(
    parsed: parse.ClassUnion, constructor_statements: Sequence[construction.Statement]
) -> Tuple[Optional[ClassUnion], Optional[List[Error]]]:
    """
    Translate a concrete parsed class to an intermediate class.

    The ``constructor_statements`` are determined by the constructor table. The calls
    to super-constructors are not expected to be in-lined yet.
    """
    serialization = None  # type: Optional[Serialization]
    if parsed.serialization is not None:
        # NOTE (mristin, 2022-03-19):
        # The ``parsed.serialization.with_model_type`` might be None, but we have to
        # allow it here as we will apply a second pass and properly inherit the
        # with_model_type.
        serialization = Serialization(
            with_model_type=parsed.serialization.with_model_type  # type: ignore
        )

    errors = []  # type: List[Error]

    invariants = []
    for parsed_invariant in parsed.invariants:
        invariant, error = _to_invariant(
            parsed=parsed_invariant,
            placeholder_for_our_type=_PlaceholderOurType(parsed.name),
        )
        if error is not None:
            errors.append(error)
        else:
            assert invariant is not None
            invariants.append(invariant)

    properties = []  # type: List[Property]
    for parsed_prop in parsed.properties:
        prop, prop_errors = _to_property(parsed=parsed_prop, parsed_cls=parsed)
        if prop_errors is not None:
            errors.append(
                Error(
                    parsed_prop.node,
                    f"Failed to parse the property {parsed_prop.name!r}",
                    prop_errors,
                )
            )
            continue

        assert prop is not None
        properties.append(prop)

    constructor, constructor_errors = _extract_constructor(
        parsed_class=parsed, constructor_statements=constructor_statements
    )
    if constructor_errors is not None:
        errors.append(
            Error(
                parsed.node,
                f"Failed to parsed the constructor of the class {parsed.name!r}",
                constructor_errors,
            )
        )

    methods = []  # type: List[MethodUnion]
    for parsed_method in parsed.methods:
        if isinstance(parsed_method, parse.ConstructorToBeUnderstood):
            # Constructors are handled in a different way through
            # :py:class:`Constructors`.
            continue

        method, method_errors = _to_method(parsed=parsed_method, parsed_cls=parsed)
        if method_errors is not None:
            errors.append(
                Error(
                    parsed_method.node,
                    f"Failed to parse the method {parsed_method.name!r}",
                    method_errors,
                )
            )
            continue

        assert method is not None
        methods.append(method)

    description = None  # type: Optional[DescriptionOfOurType]
    if parsed.description is not None:
        description, description_errors = _to_description_of_our_type(
            parsed=parsed.description
        )
        if description_errors is not None:
            errors.extend(description_errors)

    if len(errors) > 0:
        return None, errors

    assert constructor is not None

    factory_to_use = None  # type: Optional[Type[Class]]

    if isinstance(parsed, parse.ConcreteClass):
        factory_to_use = ConcreteClass
    elif isinstance(parsed, parse.AbstractClass):
        factory_to_use = AbstractClass
    else:
        assert_never(parsed)

    assert factory_to_use is not None

    # noinspection PyTypeChecker
    return (
        factory_to_use(
            name=parsed.name,
            # Use a placeholder for inheritances, ancestors, descendants and
            # the interface as we can not resolve inheritances at this point
            inheritances=[],
            ancestors=[],
            interface=_MaybeInterfacePlaceholder(),  # type: ignore
            descendants=[],
            is_implementation_specific=parsed.is_implementation_specific,
            properties=properties,
            methods=methods,
            constructor=constructor,
            invariants=invariants,
            # We allow temporarily the ``serialization`` to be possibly None since we
            # have to resolve it in the second pass in
            # :py:func:`_second_pass_to_stack_serializations`.
            serialization=serialization,  # type: ignore
            description=description,
            parsed=parsed,
        ),
        None,
    )


# fmt: off
@require(
    lambda parsed:
    parsed.verification, "Expected a verification function"
)
@require(
    lambda parsed:
    'self' not in parsed.arguments_by_name,
    "Expected no ``self`` in the arguments since a verification function should not be "
    "a method of a class"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _to_verification_function(
    parsed: parse.FunctionUnion,
) -> Tuple[Optional[VerificationUnion], Optional[List[Error]]]:
    """Translate the verification function and try to understand it, if necessary."""
    name = parsed.name
    arguments = _to_arguments(parsed=parsed.arguments)
    returns = None if parsed.returns is None else _to_type_annotation(parsed.returns)

    errors = []  # type: List[Error]

    assert not parsed.non_mutating, (
        "Functions must not be non-mutating as there is no instance. "
        "This is expected to be verified at the parse stage."
    )

    description = None  # type: Optional[DescriptionOfSignature]
    if parsed.description is not None:
        description, description_errors = _to_description_of_signature(
            parsed=parsed.description, arguments=arguments, returns=returns
        )
        if description_errors is not None:
            errors.extend(description_errors)

    contracts = _to_contracts(parsed.contracts)

    if isinstance(parsed, parse.ImplementationSpecificMethod):
        if len(errors) > 0:
            return None, errors

        return (
            ImplementationSpecificVerification(
                name=name,
                arguments=arguments,
                returns=returns,
                description=description,
                contracts=contracts,
                parsed=parsed,
            ),
            None,
        )

    elif isinstance(parsed, parse.UnderstoodMethod):
        pattern, ok_error, fatal_error = pattern_verification.try_to_understand(
            parsed=parsed
        )

        if fatal_error is not None:
            errors.append(fatal_error)

        if len(errors) > 0:
            return None, errors

        if ok_error is None:
            assert pattern is not None

            return (
                PatternVerification(
                    name=name,
                    arguments=arguments,
                    returns=returns,
                    description=description,
                    contracts=contracts,
                    pattern=pattern,
                    parsed=parsed,
                ),
                None,
            )

        # NOTE (mristin, 2021-01-02):
        # ``ok_error`` explains why we could not match the understood method against
        # more sophisticated functions. We check that we do not use ``re`` here as
        # the code using regular expressions can not be easily transpiled to *any*
        # target language.
        #
        # If no ``re`` is used, we try to transpile the verification functions in
        # the generation step.

        check_code_uses_re_visitor = _CheckCodeUsesReVisitor()
        for node in parsed.body:
            check_code_uses_re_visitor.visit(node)

        if check_code_uses_re_visitor.first_re_usage:
            return None, [
                Error(
                    check_code_uses_re_visitor.first_re_usage.original_node,
                    "The function uses ``re`` module, but we could not match it as "
                    "a pattern verification function. We can not transpile the code "
                    "which relies on regular expressions directly to targets. Please make "
                    "sure that your function can be understood as a pattern matching "
                    "function.",
                    [ok_error],
                )
            ]

        return (
            TranspilableVerification(
                name=name,
                arguments=arguments,
                returns=returns,
                description=description,
                contracts=contracts,
                parsed=parsed,
            ),
            None,
        )

    elif isinstance(parsed, parse.ConstructorToBeUnderstood):
        errors.append(
            Error(parsed.node, "Unexpected constructor as a verification function")
        )
        return None, errors
    else:
        assert_never(parsed)

    raise AssertionError("Should not have gotten here")


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_meta_model(
    parsed: parse.MetaModel,
) -> Tuple[Optional[MetaModel], Optional[List[Error]]]:
    """Translate the meta-model meta-data."""
    description = None  # type: Optional[DescriptionOfMetaModel]
    if parsed.description is not None:
        description, description_errors = _to_description_of_meta_model(
            parsed.description
        )
        if description_errors is not None:
            return None, description_errors

    return (
        MetaModel(
            version=parsed.version,
            xml_namespace=parsed.xml_namespace,
            description=description,
        ),
        None,
    )


# region Translate constants


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_constant_primitive(
    parsed: parse.ConstantPrimitive,
) -> Tuple[Optional[ConstantPrimitive], Optional[List[Error]]]:
    """Translate the parsed to an intermediate constant primitive."""
    a_type = PYTHON_CONSTANT_TYPE_TO_PRIMITIVE_TYPE.get(type(parsed.value), None)
    if a_type is None:
        return None, [
            Error(
                parsed.node,
                f"The primitive type could not be determined "
                f"for the type of the constant {parsed.name!r}: {type(parsed.value)}; "
                f"the value was: {parsed.value!r}",
            )
        ]

    description = None  # type: Optional[DescriptionOfConstant]
    if parsed.description is not None:
        description, description_errors = _to_description_of_constant(
            parsed=parsed.description
        )

        if description_errors is not None:
            return None, description_errors

    return (
        ConstantPrimitive(
            name=parsed.name,
            value=parsed.value,
            a_type=a_type,
            description=description,
            parsed=parsed,
        ),
        None,
    )


class _PlaceholderConstant:
    """Reference a constant which will be resolved once the table is built."""

    def __init__(self, name: Identifier) -> None:
        """Initialize with the given values."""
        self.name = name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


# fmt: off
# noinspection PyTypeChecker
@require(
    lambda parsed:
    parsed.items_type_annotation.identifier in STR_TO_PRIMITIVE_TYPE
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _to_constant_set_of_primitives(
    parsed: parse.ConstantSet,
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[ConstantSetOfPrimitives], Optional[List[Error]]]:
    """Translate the parsed constant set to a constant set of primitive values."""
    a_type = STR_TO_PRIMITIVE_TYPE[parsed.items_type_annotation.identifier]

    a_type_in_python = PRIMITIVE_TYPE_TO_PYTHON_TYPE[a_type]

    literals = []  # type: List[PrimitiveSetLiteral]

    errors = []  # type: List[Error]
    for i, literal in enumerate(parsed.set_literals):
        if not isinstance(literal.node, ast.Constant):
            errors.append(
                Error(
                    literal.node,
                    f"The literal at the index {i} of the constant set of "
                    f"primitive values is expected to be a primitive literal. "
                    f"However, we got: {atok.get_text(literal.node)}; "
                    f"in AST: {ast.dump(literal.node)}",
                )
            )
            continue

        if not isinstance(literal.node.value, a_type_in_python):
            errors.append(
                Error(
                    literal.node,
                    f"The literal at the index {i} of the constant set of primitive "
                    f"values is expected to be of type {a_type.value}, "
                    f"but we got {type(literal.node.value).__name__}: "
                    f"{atok.get_text(literal.node)}",
                )
            )
            continue

        literals.append(
            PrimitiveSetLiteral(value=literal.node.value, a_type=a_type, parsed=literal)
        )

    description = None  # type: Optional[DescriptionOfConstant]
    if parsed.description is not None:
        description, description_errors = _to_description_of_constant(
            parsed=parsed.description
        )
        if description_errors is not None:
            errors.append(
                Error(
                    parsed.node, "Failed to parse the description", description_errors
                )
            )
        else:
            assert description is not None

    subsets = []  # type: List[_PlaceholderConstant]
    for subset_name in parsed.subsets:
        if not IDENTIFIER_RE.fullmatch(subset_name):
            errors.append(
                Error(parsed.node, f"The subset name is invalid: {subset_name!r}")
            )

        subsets.append(_PlaceholderConstant(name=Identifier(subset_name)))

    if len(errors) > 0:
        return None, errors

    return (
        ConstantSetOfPrimitives(
            name=parsed.name,
            a_type=a_type,
            literals=literals,
            # NOTE (mristin, 2022-07-06):
            # The subsets will be resolved in the second pass as we want
            # to report as many errors as possible about all the constants
            subsets=subsets,  # type: ignore
            description=description,
            parsed=parsed,
        ),
        None,
    )


# noinspection PyTypeChecker
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_constant_set_of_enumeration_literals(
    enumeration: Enumeration,
    parsed: parse.ConstantSet,
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[ConstantSetOfEnumerationLiterals], Optional[List[Error]]]:
    """Translate a parsed constant set into a constant set of enumeration literals."""
    literals = []  # type: List[EnumerationLiteral]

    errors = []  # type: List[Error]
    for i, parsed_literal in enumerate(parsed.set_literals):
        if not (
            isinstance(parsed_literal.node, ast.Attribute)
            and isinstance(parsed_literal.node.value, ast.Name)
            and parsed_literal.node.value.id == enumeration.name
        ):
            errors.append(
                Error(
                    parsed_literal.node,
                    f"The element at the index {i} of the constant set is expected "
                    f"to be an enumeration literal of "
                    f"the enumeration {enumeration.name!r}. "
                    f"However, we got: {atok.get_text(parsed_literal.node)}",
                )
            )
            continue

        if not IDENTIFIER_RE.fullmatch(parsed_literal.node.attr):
            errors.append(
                Error(
                    parsed_literal.node,
                    f"The element at the index {i} of the constant set is not "
                    f"a valid identifier of an enumeration literal: "
                    f"{parsed_literal.node.attr}",
                )
            )
            continue

        literal = enumeration.literals_by_name.get(
            Identifier(parsed_literal.node.attr), None
        )
        if literal is None:
            errors.append(
                Error(
                    parsed_literal.node,
                    f"The element at the index {i} of the constant set is not a valid "
                    f"literal of the enumeration {enumeration.name!r}: "
                    f"{parsed_literal.node.attr!r}",
                )
            )
            continue

        literals.append(literal)

    description = None  # type: Optional[DescriptionOfConstant]
    if parsed.description is not None:
        description, description_errors = _to_description_of_constant(
            parsed=parsed.description
        )
        if description_errors is not None:
            errors.append(
                Error(
                    parsed.node, "Failed to parse the description", description_errors
                )
            )
        else:
            assert description is not None

    subsets = []  # type: List[_PlaceholderConstant]
    for subset_name in parsed.subsets:
        if not IDENTIFIER_RE.fullmatch(subset_name):
            errors.append(
                Error(parsed.node, f"The subset name is invalid: {subset_name!r}")
            )

        subsets.append(_PlaceholderConstant(name=Identifier(subset_name)))

    if len(errors) > 0:
        return None, errors

    return (
        ConstantSetOfEnumerationLiterals(
            name=parsed.name,
            enumeration=enumeration,
            literals=literals,
            # NOTE (mristin, 2022-07-06):
            # The subsets will be resolved in the second pass as we want
            # to report as many errors as possible about all the constants
            subsets=subsets,  # type: ignore
            description=description,
            parsed=parsed,
        ),
        None,
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _to_constant(
    parsed: parse.ConstantUnion,
    our_types_by_name: Mapping[Identifier, OurType],
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[ConstantUnion], Optional[List[Error]]]:
    """
    Translate the parsed constant to an intermediate constant.

    This translation should be applied only *after* all our types have been translated
    as we wouldn't be able to otherwise dispatch to appropriate constant sets.
    For example, we need to know that the type is an enumeration to produce a constant
    set of enumeration literals.
    """
    if isinstance(parsed, parse.ConstantPrimitive):
        return _to_constant_primitive(parsed=parsed)
    elif isinstance(parsed, parse.ConstantSet):
        primitive_type = STR_TO_PRIMITIVE_TYPE.get(
            parsed.items_type_annotation.identifier, None
        )

        if primitive_type is not None:
            return _to_constant_set_of_primitives(parsed=parsed, atok=atok)

        our_type_name = parsed.items_type_annotation.identifier
        our_type = our_types_by_name.get(our_type_name, None)
        if our_type is None:
            return None, [
                Error(
                    parsed.items_type_annotation.node,
                    f"The constant set refers to an invalid type: {our_type_name}",
                )
            ]

        if not isinstance(our_type, Enumeration):
            return None, [
                Error(
                    parsed.items_type_annotation.node,
                    f"At the moment, we support only constant sets of enumeration "
                    f"literals. However, the constant set {parsed.name} is defined "
                    f"as a set of {our_type_name}. Please contact the developers "
                    f"if you need this feature",
                )
            ]

        return _to_constant_set_of_enumeration_literals(
            enumeration=our_type, parsed=parsed, atok=atok
        )

    else:
        assert_never(parsed)


# endregion


def _over_our_type_annotations(
    something: Union[SymbolTable, OurType, SignatureLike, TypeAnnotationUnion]
) -> Iterator[OurTypeAnnotation]:
    """Iterate over all the atomic type annotations in the ``something``."""
    if isinstance(something, PrimitiveTypeAnnotation):
        pass

    elif isinstance(something, OurTypeAnnotation):
        yield something

    elif isinstance(something, ListTypeAnnotation):
        yield from _over_our_type_annotations(something.items)

    elif isinstance(something, TupleTypeAnnotation):
        for item in something.items:
            yield from _over_our_type_annotations(item)

    elif isinstance(something, OptionalTypeAnnotation):
        yield from _over_our_type_annotations(something.value)

    elif isinstance(something, Enumeration):
        pass

    elif isinstance(something, ConstrainedPrimitive):
        pass

    elif isinstance(something, NamedUnion):
        # NOTE (mristin):
        # A named union has no properties, methods or constructor of its own, so
        # there is nothing to recurse into.
        pass

    elif isinstance(something, Class):
        for prop in something.properties:
            yield from _over_our_type_annotations(prop.type_annotation)

        for method in something.methods:
            yield from _over_our_type_annotations(method)

        yield from _over_our_type_annotations(something.constructor)

    elif isinstance(something, SignatureLike):
        for argument in something.arguments:
            yield from _over_our_type_annotations(argument.type_annotation)

        if something.returns is not None:
            yield from _over_our_type_annotations(something.returns)
    elif isinstance(something, SymbolTable):
        for cls in something.classes:
            yield from _over_our_type_annotations(cls)

        for verification in something.verification_functions:
            yield from _over_our_type_annotations(verification)

    else:
        assert_never(something)


def _second_pass_to_resolve_our_types_in_atomic_type_annotations_in_place(
    symbol_table: SymbolTable,
) -> List[Error]:
    """Resolve the references to our types in the atomic type annotations in-place."""
    errors = []  # type: List[Error]

    for our_type_annotation in _over_our_type_annotations(symbol_table):
        assert isinstance(our_type_annotation.our_type, _PlaceholderOurType), (
            "Expected only placeholder for our types to be assigned "
            "in the first pass"
        )

        if not IDENTIFIER_RE.match(our_type_annotation.our_type.name):
            errors.append(
                Error(
                    our_type_annotation.parsed.node,
                    f"Our type is invalid: {our_type_annotation.our_type.name!r}",
                )
            )
            continue

        identifier = Identifier(our_type_annotation.our_type.name)
        referenced_our_type = symbol_table.find_our_type(identifier)
        if referenced_our_type is None:
            errors.append(
                Error(
                    our_type_annotation.parsed.node,
                    f"Our type with identifier {identifier!r} is not available "
                    f"in the symbol table.",
                )
            )
            continue

        our_type_annotation.our_type = referenced_our_type

    return errors


def _find_all_in_description_of_our_type(
    element_type: Type[_DocElementT], description: DescriptionOfOurType
) -> Iterator[_DocElementT]:
    """Iterate over all the fields of the description and yield the desired elements."""
    yield from description.summary.findall(element_type)

    for remark in description.remarks:
        yield from remark.findall(element_type)

    for constraint in description.constraints_by_identifier.values():
        # noinspection PyUnresolvedReferences
        yield from constraint.findall(element_type)


def _find_all_in_description_of_enumeration_literal(
    element_type: Type[_DocElementT],
    description: DescriptionOfEnumerationLiteral,
) -> Iterator[_DocElementT]:
    """Iterate over all the fields of the description and yield the desired elements."""
    yield from description.summary.findall(element_type)

    for remark in description.remarks:
        yield from remark.findall(element_type)


def _find_all_in_description_of_property(
    element_type: Type[_DocElementT], description: DescriptionOfProperty
) -> Iterator[_DocElementT]:
    """Iterate over all the fields of the description and yield the desired elements."""
    yield from description.summary.findall(element_type)

    for remark in description.remarks:
        yield from remark.findall(element_type)

    for body in description.constraints_by_identifier.values():
        # noinspection PyUnresolvedReferences
        yield from body.findall(element_type)


def _find_all_in_description_of_constant(
    element_type: Type[_DocElementT], description: DescriptionOfConstant
) -> Iterator[_DocElementT]:
    """Iterate over all the fields of the description and yield the desired elements."""
    yield from description.summary.findall(element_type)

    for remark in description.remarks:
        yield from remark.findall(element_type)


def _find_all_in_description_of_meta_model(
    element_type: Type[_DocElementT], description: DescriptionOfMetaModel
) -> Iterator[_DocElementT]:
    """
    Iterate over all the fields of the description and yield the desired elements.

    We also return the description for the client to report errors etc.
    """
    yield from description.summary.findall(element_type)

    for remark in description.remarks:
        yield from remark.findall(element_type)

    for constraint in description.constraints_by_identifier.values():
        # noinspection PyUnresolvedReferences
        yield from constraint.findall(element_type)


def _over_descriptions_and_our_types(
    symbol_table: SymbolTable,
) -> Iterator[Tuple[DescriptionUnion, Optional[OurType]]]:
    """
    Iterate over the descriptions along our types in which they are defined.

    For some descriptions, such as the descriptions of the meta-model itself, none of
    our types exists. We yield None in those cases.
    """
    for our_type in symbol_table.our_types:
        if our_type.description is not None:
            yield our_type.description, our_type

        if isinstance(our_type, Enumeration):
            for literal in our_type.literals:
                if literal.description is not None:
                    yield literal.description, our_type

        elif isinstance(our_type, ConstrainedPrimitive):
            # No special sub-descriptions in the constrained primitive
            pass

        elif isinstance(our_type, NamedUnion):
            # No special sub-descriptions in the named union
            pass

        elif isinstance(our_type, (AbstractClass, ConcreteClass)):
            for prop in our_type.properties:
                if prop.description is not None:
                    yield prop.description, our_type

            for method in our_type.methods:
                if method.description is not None:
                    yield method.description, our_type
        else:
            assert_never(our_type)

    for constant in symbol_table.constants:
        if constant.description is not None:
            yield constant.description, None

    for verification in symbol_table.verification_functions:
        if verification.description is not None:
            yield verification.description, None

    if symbol_table.meta_model.description is not None:
        yield symbol_table.meta_model.description, None


def _find_all_in_descriptions(
    element_type: Type[_DocElementT], symbol_table: SymbolTable
) -> Iterator[Tuple[_DocElementT, DescriptionUnion, Optional[OurType]]]:
    """
    Iterate over the descriptions and yield the desired documentation elements.

    We return the corresponding description containing the element as well as
    the outer our type in which context the description is given.

    If there is none of our types available as a context, which is the case
    for example in constants and verification functions, ``None`` is yielded.
    """
    for description, our_type in _over_descriptions_and_our_types(
        symbol_table=symbol_table
    ):
        if isinstance(description, DescriptionOfOurType):
            for element in _find_all_in_description_of_our_type(
                element_type=element_type, description=description
            ):
                yield element, description, our_type

        elif isinstance(description, DescriptionOfEnumerationLiteral):
            for element in _find_all_in_description_of_enumeration_literal(
                element_type=element_type, description=description
            ):
                yield element, description, our_type

        elif isinstance(description, DescriptionOfProperty):
            for element in _find_all_in_description_of_property(
                element_type=element_type, description=description
            ):
                yield element, description, our_type

        elif isinstance(description, DescriptionOfSignature):
            for element in _find_all_in_description_of_signature(
                element_type=element_type, description=description
            ):
                yield element, description, our_type

        elif isinstance(description, DescriptionOfConstant):
            for element in _find_all_in_description_of_constant(
                element_type=element_type, description=description
            ):
                yield element, description, our_type

        elif isinstance(description, DescriptionOfMetaModel):
            for element in _find_all_in_description_of_meta_model(
                element_type=element_type, description=description
            ):
                yield element, description, our_type

        else:
            assert_never(description)


def _second_pass_to_resolve_references_to_our_types_in_the_descriptions_in_place(
    symbol_table: SymbolTable,
) -> List[Error]:
    """Resolve the references to our types in the descriptions in-place."""
    errors = []  # type: List[Error]

    for ref_to_our_type_in_doc, description, _ in _find_all_in_descriptions(
        element_type=doc.ReferenceToOurType, symbol_table=symbol_table
    ):
        # NOTE (mristin, 2021-12-27):
        # References to our types can be repeated as docutils will cache them,
        # so we need to skip them, and translate only the placeholders.
        if not isinstance(ref_to_our_type_in_doc.our_type, _PlaceholderOurType):
            continue

        raw_identifier = ref_to_our_type_in_doc.our_type.name

        if raw_identifier.startswith("."):
            errors.append(
                Error(
                    description.parsed.node,
                    f"The references with relaxed qualified names to our types "
                    f"are not allowed as we can not resolve references outside "
                    f"of the meta-model: {raw_identifier}",
                )
            )
            continue

        if not IDENTIFIER_RE.match(raw_identifier):
            errors.append(
                Error(
                    description.parsed.node,
                    f"The identifier in the reference to our type "
                    f"is invalid: {raw_identifier}",
                )
            )
            continue

        # Strip the dot
        identifier = Identifier(raw_identifier)

        referenced_our_type = symbol_table.find_our_type(name=identifier)
        if referenced_our_type is None:
            errors.append(
                Error(
                    description.parsed.node,
                    f"The identifier of the reference to our type "
                    f"could not be found in the symbol table: {identifier}",
                )
            )
            continue

        ref_to_our_type_in_doc.our_type = referenced_our_type

    return errors


def _second_pass_to_resolve_references_to_constants_in_the_descriptions_in_place(
    symbol_table: SymbolTable,
) -> List[Error]:
    """Resolve the references to constants in the descriptions in-place."""
    errors = []  # type: List[Error]

    for ref_to_constant_in_doc, description, _ in _find_all_in_descriptions(
        element_type=doc.ReferenceToConstant, symbol_table=symbol_table
    ):
        # NOTE (mristin, 2022-07-06):
        # References to constants can be repeated as docutils will cache them,
        # so we need to skip them, and translate only the placeholders.
        if not isinstance(
            ref_to_constant_in_doc.constant, _PlaceholderReferenceToConstant
        ):
            assert isinstance(ref_to_constant_in_doc.constant, Constant), (
                f"Unexpected type of the constant "
                f"in case when it is not a placeholder: "
                f"{type(ref_to_constant_in_doc.constant)}; "
                f"the value was: {ref_to_constant_in_doc.constant}"
            )
            continue

        raw_identifier = ref_to_constant_in_doc.constant.name

        if raw_identifier.startswith("."):
            errors.append(
                Error(
                    description.parsed.node,
                    f"The references with relaxed qualified names to constants "
                    f"are not allowed as we can not resolve references outside "
                    f"of the meta-model: {raw_identifier}",
                )
            )
            continue

        if not IDENTIFIER_RE.match(raw_identifier):
            errors.append(
                Error(
                    description.parsed.node,
                    f"The identifier in the reference to a constant "
                    f"is invalid: {raw_identifier}",
                )
            )
            continue

        # Strip the dot
        identifier = Identifier(raw_identifier)

        referenced_constant = symbol_table.constants_by_name.get(identifier, None)
        if referenced_constant is None:
            errors.append(
                Error(
                    description.parsed.node,
                    f"The identifier of the reference to a constant "
                    f"could not be found in the symbol table: {identifier}",
                )
            )
            continue

        ref_to_constant_in_doc.constant = referenced_constant

    return errors


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _fill_in_default_placeholder(
    default: _DefaultPlaceholder, symbol_table: SymbolTable
) -> Tuple[Optional[Default], Optional[Error]]:
    """Resolve the default values to reference using the constructed symbol table."""
    # If we do not preemptively return, signal that we do not know how to handle
    # the default

    if isinstance(default.parsed.node, ast.Constant):
        if (
            isinstance(default.parsed.node.value, (bool, int, float, str))
            or default.parsed.node.value is None
        ):
            return (
                DefaultPrimitive(
                    value=default.parsed.node.value, parsed=default.parsed
                ),
                None,
            )

    if (
        isinstance(default.parsed.node, ast.Attribute)
        and isinstance(default.parsed.node.ctx, ast.Load)
        and isinstance(default.parsed.node.value, ast.Name)
        and isinstance(default.parsed.node.value.ctx, ast.Load)
    ):
        name_of_our_type = Identifier(default.parsed.node.value.id)
        attr_name = Identifier(default.parsed.node.attr)

        our_type = symbol_table.find_our_type(name=name_of_our_type)
        if isinstance(our_type, Enumeration):
            literal = our_type.literals_by_name.get(attr_name, None)
            if literal is not None:
                return (
                    DefaultEnumerationLiteral(
                        enumeration=our_type, literal=literal, parsed=default.parsed
                    ),
                    None,
                )

    return None, Error(
        default.parsed.node,
        f"The translation of the default value to the intermediate layer "
        f"has not been implemented: {ast.dump(default.parsed.node)}",
    )


def _over_arguments(symbol_table: SymbolTable) -> Iterator[Argument]:
    """Iterate over all the instances of ``Argument`` from the ``symbol_table``."""
    for cls in symbol_table.classes:
        for method in cls.methods:
            yield from method.arguments

        yield from cls.constructor.arguments

    for verification in symbol_table.verification_functions:
        yield from verification.arguments


def _second_pass_to_resolve_default_argument_values_in_place(
    symbol_table: SymbolTable,
) -> List[Error]:
    """Resolve the default values of the method and function arguments in-place."""
    errors = []  # type: List[Error]

    for arg in _over_arguments(symbol_table):
        if arg.default is None:
            continue

        assert isinstance(arg.default, _DefaultPlaceholder), (
            f"Expected the argument default value to be a placeholder "
            f"since we resolve it only in the second pass, "
            f"but got: {arg.default}"
        )

        filled_default, error = _fill_in_default_placeholder(
            default=arg.default, symbol_table=symbol_table
        )

        if error:
            errors.append(error)
        else:
            # NOTE (mristin, 2021-12-26):
            # We can only resolve the default values now since, for example, we would
            # not know how to resolve the references to enumeration literals.
            # The attribute ``default`` is marked final only for the users of the
            # ``intermediate`` module, not for the translation itself.

            # noinspection PyFinal,PyTypeHints
            arg.default = filled_default

    return errors


def _second_pass_to_resolve_resulting_class_of_specified_for(
    symbol_table: SymbolTable,
) -> None:
    """
    Resolve the resulting class of the ``specified_for`` in-place.

    This is done both for properties and for methods.
    """
    for cls in symbol_table.classes:
        for prop in cls.properties:
            assert isinstance(prop.specified_for, _PlaceholderOurType), (
                f"Expected the placeholder for our type for ``specified_for`` in "
                f"the property {prop} of {cls}, but got: {prop.specified_for}"
            )

            # NOTE (mristin, 2022-01-02):
            # We have to override the ``specified_for`` as we could not set it
            # during the first pass of the translation phase. The ``Final`` in
            # this context is meant for the users of the translation phase, not
            # the translation phase itself.

            specified_for = symbol_table.must_find_class(
                Identifier(prop.specified_for.name)
            )

            # noinspection PyFinal
            prop.specified_for = specified_for

        for method in cls.methods:
            assert isinstance(method.specified_for, _PlaceholderOurType), (
                f"Expected the placeholder for our type for ``specified_for`` in "
                f"the method {method} of {cls}, "
                f"but got: {method.specified_for}"
            )

            # NOTE (mristin, 2022-01-02):
            # We have to override the ``specified_for`` as we could not set it
            # during the first pass of the translation phase. The ``Final`` in
            # this context is meant for the users of the translation phase, not
            # the translation phase itself.

            specified_for = symbol_table.must_find_class(
                name=Identifier(method.specified_for.name)
            )

            # noinspection PyFinal
            method.specified_for = specified_for


def _second_pass_to_resolve_specified_for_in_invariants(
    symbol_table: SymbolTable,
) -> None:
    """Resolve our type according to the ``specified_for`` of an invariant in-place."""
    for our_type in itertools.chain(
        symbol_table.constrained_primitives, symbol_table.classes
    ):
        for invariant in our_type.invariants:
            # NOTE (mristin, 2022-01-02):
            # Since we stack invariants, it might be that we already resolved
            # the invariants coming from the parent. Hence, we need to check that
            # we haven't resolved ``specified_for`` here.

            if isinstance(invariant.specified_for, _PlaceholderOurType):
                our_type = symbol_table.must_find_class_or_constrained_primitive(
                    Identifier(invariant.specified_for.name)
                )

                # NOTE (mristin, 2022-01-02):
                # We have to override the ``specified_for`` as we could not set it
                # during the first pass of the translation phase. The ``Final`` in
                # this context is meant for the users of the translation phase, not
                # the translation phase itself.

                # noinspection PyFinal
                invariant.specified_for = our_type


# fmt: off
@require(
    lambda symbol_table:
    # These are not tight pre-conditions, but they should catch the most obvious
    # bugs, such as if we re-enter this function.
    all(
        isinstance(our_type.inheritances, list)
        and len(our_type.inheritances) == 0
        for our_type in itertools.chain(
            symbol_table.constrained_primitives,
            symbol_table.classes
        )
    ),
    "No inheritances previously resolved"
)
# fmt: on
def _second_pass_to_resolve_inheritances_in_place(symbol_table: SymbolTable) -> None:
    """Resolve the class references in the class inheritances in-place."""
    for our_type in symbol_table.our_types:
        if isinstance(our_type, Enumeration):
            continue

        elif isinstance(our_type, ConstrainedPrimitive):
            resolved_constrained_primitive_inheritances = (
                []
            )  # type: List[ConstrainedPrimitive]

            for inheritance_name in our_type.parsed.inheritances:
                # NOTE (mristin, 2021-12-26):
                # The constrainee is stored at a different property and is not included
                # in the inheritances. The inheritances refer only to ancestor
                # constrained primitives.
                if inheritance_name in parse.PRIMITIVE_TYPES:
                    continue

                parent_constrained_primitive = (
                    symbol_table.must_find_constrained_primitive(
                        Identifier(inheritance_name)
                    )
                )

                resolved_constrained_primitive_inheritances.append(
                    parent_constrained_primitive
                )

            our_type._set_inheritances(resolved_constrained_primitive_inheritances)

        elif isinstance(our_type, (AbstractClass, ConcreteClass)):
            resolved_class_inheritances = []  # type: List[ClassUnion]

            for inheritance_name in our_type.parsed.inheritances:
                parent_cls = symbol_table.must_find_class(Identifier(inheritance_name))

                resolved_class_inheritances.append(parent_cls)

            our_type._set_inheritances(resolved_class_inheritances)

        elif isinstance(our_type, NamedUnion):
            # NOTE (mristin):
            # A named union has no inheritances of its own -- its members are
            # resolved separately, see
            # ``_second_pass_to_resolve_named_union_members_in_place``.
            continue

        else:
            assert_never(our_type)


def _topologically_sort_named_unions_or_find_cycle(
    our_types: Sequence[OurType],
    our_types_by_name: Mapping[Identifier, OurType],
) -> Tuple[Optional[List[NamedUnion]], Optional[Error]]:
    """
    Topologically sort the named unions by their named-union member dependencies.

    A named union may itself be a member of another named union, so the named
    unions form their own dependency graph, on top of (and independent of) the
    class inheritance ontology. This function orders the named unions so that
    every named union follows all of its (transitive) named-union member
    dependencies -- this order is needed both to place the named unions
    correctly in ``our_types_topologically_sorted`` and to flatten the
    ``implementers`` of a named union only after its named-union members'
    ``implementers`` have themselves already been flattened.

    :return:
        the named unions in a valid topological order, or an :class:`Error` if
        the named unions form a cycle (*e.g.*, a named union that is,
        transitively, its own member)
    """
    # NOTE (mristin):
    # 0 = not visited, 1 = on the current recursion stack, 2 = done.
    state = dict()  # type: Dict[Identifier, int]
    stack = []  # type: List[Identifier]
    order = []  # type: List[NamedUnion]

    def visit(named_union: NamedUnion) -> Optional[Error]:
        """Visit the named union and its named-union members, depth-first."""
        current_state = state.get(named_union.name, 0)
        if current_state == 2:
            return None

        if current_state == 1:
            cycle_start = stack.index(named_union.name)
            cycle_str = " -> ".join(repr(name) for name in stack[cycle_start:])
            return Error(
                named_union.parsed.node,
                f"The named union {named_union.name!r} is involved in a cycle "
                f"of named unions, which is not allowed "
                f"(a named union may not be its own member, "
                f"directly or transitively): {cycle_str} -> {named_union.name!r}",
            )

        state[named_union.name] = 1
        stack.append(named_union.name)

        for member_name in named_union.parsed.members:
            member_our_type = our_types_by_name[member_name]
            if isinstance(member_our_type, NamedUnion):
                error = visit(member_our_type)
                if error is not None:
                    return error

        stack.pop()
        state[named_union.name] = 2
        order.append(named_union)

        return None

    for our_type in our_types:
        if not isinstance(our_type, NamedUnion):
            continue

        maybe_error = visit(our_type)
        if maybe_error is not None:
            return None, maybe_error

    return order, None


def _second_pass_to_resolve_named_union_members_in_place(
    symbol_table: SymbolTable,
) -> None:
    """
    Resolve the references in the named union members in-place.

    A member resolves to either a class or another named union. This assumes
    that the members have already been verified to resolve to one of those (as
    opposed to, *e.g.*, an enumeration, or a class re-classified as a
    constrained primitive) -- see the region "Check that the members of named
    unions are indeed classes or named unions" in :func:`translate`.

    Unlike :func:`_second_pass_to_resolve_named_union_implementers_in_place`,
    this does *not* need to run in the topological order over the named-union
    dependency graph -- every named union's object already exists at this point
    (from the first pass of translation), so wiring up a direct reference to it
    does not depend on that other named union's own members being resolved yet.
    """
    for named_union in symbol_table.named_unions:
        resolved_members = []  # type: List[Union[ClassUnion, NamedUnion]]

        for member_name in named_union.parsed.members:
            member = symbol_table.must_find_class_or_named_union(member_name)
            resolved_members.append(member)

        named_union._set_members(resolved_members)


# fmt: off
@require(
    lambda symbol_table:
    all(
        # These are not tight pre-conditions, but they should catch the most obvious
        # bugs, such as if we re-enter this function.
        isinstance(cls.concrete_descendants, list) and
        len(cls.concrete_descendants) == 0
        for cls in symbol_table.classes
    )
)
# fmt: on
def _second_pass_to_resolve_ancestors_and_descendants_in_place(
    symbol_table: SymbolTable, ontology: _hierarchy.Ontology
) -> None:
    """
    Resolve placeholders for ancestors and concrete descendants in the classes in-place.

    All abstract classes as well as concrete classes with at least one descendant
    are mapped to an interface.

    Mind that the concept of the interface is not used in the meta-model, and we
    introduce it only as a convenience for the code generation.
    """
    ancestor_map_constr_primi = collections.defaultdict(
        lambda: []
    )  # type: MutableMapping[ConstrainedPrimitive, List[ConstrainedPrimitive]]

    ancestor_map_cls = collections.defaultdict(
        lambda: []
    )  # type: MutableMapping[ClassUnion, List[ClassUnion]]

    for our_type in symbol_table.our_types:
        if isinstance(our_type, Enumeration):
            pass

        elif isinstance(our_type, NamedUnion):
            # NOTE (mristin):
            # A named union is not part of the class hierarchy, so it has no
            # ancestors or descendants.
            pass

        elif isinstance(our_type, ConstrainedPrimitive):
            constr_primi_descendants = []  # type: List[ConstrainedPrimitive]
            for parsed_descendant in ontology.list_descendants(our_type.parsed):
                descendant_constr_primi = symbol_table.must_find_constrained_primitive(
                    parsed_descendant.name
                )

                constr_primi_descendants.append(descendant_constr_primi)

            our_type._set_descendants(constr_primi_descendants)

            for constr_primi_descendant in constr_primi_descendants:
                ancestor_map_constr_primi[constr_primi_descendant].append(our_type)

        elif isinstance(our_type, (AbstractClass, ConcreteClass)):
            class_descendants = []  # type: List[ClassUnion]
            for parsed_descendant in ontology.list_descendants(our_type.parsed):
                descendant_cls = symbol_table.must_find_class(parsed_descendant.name)

                class_descendants.append(descendant_cls)

            our_type._set_descendants(class_descendants)

            for cls_descendant in class_descendants:
                ancestor_map_cls[cls_descendant].append(our_type)
        else:
            assert_never(our_type)

    for constr_primi, constr_primi_ancestors in ancestor_map_constr_primi.items():
        constr_primi._set_ancestors(constr_primi_ancestors)

    for cls, ancestors in ancestor_map_cls.items():
        cls._set_ancestors(ancestors)


# fmt: off
@snapshot(lambda constant_set: constant_set.subsets[:], name="subsets")
@ensure(
    lambda constant_set, result:
    not (result[0] is not None)
    or (
        all(
            subset_literal.value in constant_set.literal_value_set
            for subset in result[0]
            for subset_literal in subset.literals
        )
    ),
    "Every subset is a true subset"
)
@ensure(
    lambda result, OLD:
    not (result[0] is not None)
    or (
        len(result[0]) == len(OLD.subsets)
        and all(
            subset.name == placeholder.name
            for subset, placeholder in zip(result[0], OLD.subsets)
        )
    ),
    "All the subsets resolved"
)
# fmt: on
def _resolve_subsets_in_constant_set_of_primitives(
    constant_set: ConstantSetOfPrimitives, symbol_table: SymbolTable
) -> Tuple[Optional[List[ConstantSetOfPrimitives]], Optional[List[Error]]]:
    """De-reference the subsets from the placeholders."""
    subsets = []  # type: List[ConstantSetOfPrimitives]
    errors = []  # type: List[Error]

    for placeholder in constant_set.subsets:
        assert isinstance(placeholder, _PlaceholderConstant), (
            f"Expected {_PlaceholderConstant.__name__} from the first pass, "
            f"but got: {placeholder}"
        )

        maybe_subset = symbol_table.constants_by_name.get(placeholder.name, None)

        if maybe_subset is None:
            errors.append(
                Error(
                    constant_set.parsed.node,
                    f"The subset with the name {placeholder.name!r} "
                    f"could not be found",
                )
            )
            continue

        if not isinstance(maybe_subset, ConstantSetOfPrimitives):
            errors.append(
                Error(
                    constant_set.parsed.node,
                    f"Expected a subset as a set of primitive values, "
                    f"but the subset {maybe_subset.name!r} is not: {type(maybe_subset)}",
                )
            )
            continue

        if maybe_subset.a_type is not constant_set.a_type:
            errors.append(
                Error(
                    constant_set.parsed.node,
                    f"Expected the subset {maybe_subset.name!r} "
                    f"to be of the same primitive type, {constant_set.a_type.value}, "
                    f"but it is of the type: {maybe_subset.a_type.value}",
                )
            )
            continue

        for literal in maybe_subset.literals:
            if literal.value not in constant_set.literal_value_set:
                errors.append(
                    Error(
                        constant_set.parsed.node,
                        f"The literal from "
                        f"the subset {maybe_subset.name!r} "
                        f"is not contained in the set {constant_set.name!r}: "
                        f"{literal.value!r}",
                    )
                )
                continue

        subsets.append(maybe_subset)

    if len(errors) > 0:
        return None, errors

    return subsets, None


# fmt: off
@snapshot(lambda constant_set: constant_set.subsets[:], name="subsets")
@ensure(
    lambda constant_set, result:
    not (result[0] is not None)
    or (
        all(
            id(subset_literal) in constant_set.literal_id_set
            for subset in result[0]
            for subset_literal in subset.literals
        )
    ),
    "Every subset is a true subset"
)
@ensure(
    lambda result, OLD:
    not (result[0] is not None)
    or (
        len(result[0]) == len(OLD.subsets)
        and all(
            subset.name == placeholder.name
            for subset, placeholder in zip(result[0], OLD.subsets)
        )
    ),
    "All the subsets resolved"
)
# fmt: on
def _resolve_subsets_in_constant_set_of_enumeration_literals(
    constant_set: ConstantSetOfEnumerationLiterals, symbol_table: SymbolTable
) -> Tuple[Optional[List[ConstantSetOfEnumerationLiterals]], Optional[List[Error]]]:
    """De-reference the subsets from the placeholders."""
    subsets = []  # type: List[ConstantSetOfEnumerationLiterals]
    errors = []  # type: List[Error]

    for placeholder in constant_set.subsets:
        assert isinstance(placeholder, _PlaceholderConstant), (
            f"Expected {_PlaceholderConstant.__name__!r} from the first pass, "
            f"but got: {placeholder}"
        )

        maybe_subset = symbol_table.constants_by_name.get(placeholder.name, None)

        if maybe_subset is None:
            errors.append(
                Error(
                    constant_set.parsed.node,
                    f"The subset with the name {placeholder.name!r} "
                    f"could not be found",
                )
            )
            continue

        if not isinstance(maybe_subset, ConstantSetOfEnumerationLiterals):
            errors.append(
                Error(
                    constant_set.parsed.node,
                    f"Expected a subset as a set of enumeration literals, "
                    f"but the subset {maybe_subset.name!r} is not: {type(maybe_subset)}",
                )
            )
            continue

        if maybe_subset.enumeration is not constant_set.enumeration:
            errors.append(
                Error(
                    constant_set.parsed.node,
                    f"Expected the subset {maybe_subset.name!r} "
                    f"to be of the same enumeration, {constant_set.enumeration.name!r}, "
                    f"but it is of the enumeration: {maybe_subset.enumeration.name!r}",
                )
            )
            continue

        for literal in maybe_subset.literals:
            if id(literal) not in constant_set.literal_id_set:
                errors.append(
                    Error(
                        constant_set.parsed.node,
                        f"The literal from "
                        f"the subset {maybe_subset.name!r} "
                        f"is not contained in the set {constant_set.name!r}: "
                        f"{literal.name!r}",
                    )
                )
                continue

        subsets.append(maybe_subset)

    if len(errors) > 0:
        return None, errors

    return subsets, None


def _second_pass_to_resolve_constant_subsets_in_place(
    symbol_table: SymbolTable,
) -> List[Error]:
    """Resolve the subsets of constant sets in-place."""
    errors = []  # type: List[Error]

    for constant in symbol_table.constants:
        if isinstance(constant, ConstantPrimitive):
            continue

        elif isinstance(constant, ConstantSetOfPrimitives):
            # fmt: off
            subsets_of_primitives, subsets_errors = (
                _resolve_subsets_in_constant_set_of_primitives(
                    constant_set=constant, symbol_table=symbol_table
                )
            )
            # fmt: on

            if subsets_errors is not None:
                errors.extend(subsets_errors)
            else:
                # NOTE (mristin, 2022-07-06):
                # The attribute ``subsets`` is marked final only for the users of the
                # ``intermediate`` module, not for the translation itself.
                constant.subsets = subsets_of_primitives  # type: ignore

        elif isinstance(constant, ConstantSetOfEnumerationLiterals):
            # fmt: off
            subsets_of_enum_literals, subsets_errors = (
                _resolve_subsets_in_constant_set_of_enumeration_literals(
                    constant_set=constant, symbol_table=symbol_table
                )
            )
            # fmt: on

            if subsets_errors is not None:
                errors.extend(subsets_errors)
            else:
                # NOTE (mristin, 2022-07-06):
                # The attribute ``subsets`` is marked final only for the users of the
                # ``intermediate`` module, not for the translation itself.
                constant.subsets = subsets_of_enum_literals  # type: ignore

        else:
            assert_never(constant)

    return errors


T = TypeVar("T")


class _SettingWithSource(Generic[T]):
    """
    Represent a setting from an inheritance chain.

    For example, a setting for JSON serialization.
    """

    def __init__(self, value: T, source: ClassUnion):
        """Initialize with the given values."""
        self.value = value
        self.source = source

    def __repr__(self) -> str:
        return (
            f"{_SettingWithSource.__name__}("
            f"value={self.value!r}, "
            f"source={self.source.name!r}"
            f")"
        )


def _second_pass_to_stack_serializations_in_place(
    symbol_table: SymbolTable,
) -> List[Error]:
    """Pass on the serializations among the classes along the ontology."""
    errors = []  # type: List[Error]

    for our_type in symbol_table.our_types_topologically_sorted:
        # NOTE (mristin, 2022-03-18):
        # Assume that the parents have all the serializations resolved already due to
        # the topological order of the iteration.

        if isinstance(our_type, (Enumeration, NamedUnion, ConstrainedPrimitive)):
            continue
        elif isinstance(our_type, (AbstractClass, ConcreteClass)):
            # NOTE (mristin, 2021-11-03):
            # We do not abstract away different serialization settings at this point
            # as there is only a single one, ``with_model_type``. In the future,
            # if there are more settings, this function needs to be split into multiple
            # ones (one function for a setting each), or maybe we can even think of a
            # more general approach to inheritance of serialization settings.

            with_model_types = []  # type: List[_SettingWithSource[bool]]

            for inheritance in our_type.inheritances:
                if (
                    inheritance.serialization is not None
                    and inheritance.serialization.with_model_type is not None
                ):
                    with_model_types.append(
                        _SettingWithSource(
                            value=inheritance.serialization.with_model_type,
                            source=inheritance,
                        )
                    )

            if (
                our_type.serialization is not None
                and our_type.serialization.with_model_type is not None
            ):
                with_model_types.append(
                    _SettingWithSource(
                        value=our_type.serialization.with_model_type, source=our_type
                    )
                )

            if len(with_model_types) > 0:
                # region Verify that the with_model_type is consistent

                cursor = iter(with_model_types)
                first = next(cursor)

                success = True
                lookahead = next(cursor, None)
                while lookahead is not None:
                    if lookahead.value != first.value:
                        errors.append(
                            Error(
                                our_type.parsed.node,
                                f"The serialization setting ``with_model_type`` "
                                f"between the class {lookahead.source.name!r} "
                                f"and {first.source.name!r} is "
                                f"inconsistent: {lookahead.value!r} != {first.value!r}",
                            )
                        )
                        success = False
                        break

                    lookahead = next(cursor, None)

                if not success:
                    continue

                # endregion

                # Propagate the inferred value to our type
                if our_type.serialization is None:
                    our_type.serialization = Serialization(with_model_type=first.value)
                else:
                    our_type.serialization.with_model_type = first.value

        else:
            assert_never(our_type)

    if len(errors) > 0:
        return errors

    # region Set to default values wherever there was no serialization set

    for our_type in symbol_table.our_types_topologically_sorted:
        # NOTE (mristin, 2022-03-18):
        # Assume that the parents have all the serializations resolved already due to
        # the topological order of the iteration.

        if isinstance(our_type, (Enumeration, NamedUnion, ConstrainedPrimitive)):
            continue
        elif isinstance(our_type, (AbstractClass, ConcreteClass)):
            if our_type.serialization is None:
                our_type.serialization = Serialization(with_model_type=False)
            else:
                if our_type.serialization.with_model_type is None:
                    our_type.serialization.with_model_type = False
        else:
            assert_never(our_type)

    # endregion

    return errors


def _second_pass_to_stack_invariants_in_place(symbol_table: SymbolTable) -> None:
    """Pass on the invariants among the classes along the ontology."""
    for our_type in symbol_table.our_types_topologically_sorted:
        # NOTE (mristin, 2022-03-18):
        # Assume that the parents have all the invariants stacked already due to
        # the topological order of the iteration.

        # Propagate the invariants from the parents to this one of our types
        if isinstance(our_type, (Enumeration, NamedUnion)):
            continue
        elif isinstance(our_type, (ConstrainedPrimitive, AbstractClass, ConcreteClass)):
            inherited_invariants = []  # type: List[Invariant]

            # NOTE (mristin, 2022-03-18):
            # Skip duplicates which might arise from the diamond inheritance
            observed_invariants = set()  # type: Set[int]

            for inheritance in our_type.inheritances:
                for invariant in inheritance.invariants:
                    invariant_id = id(invariant)
                    if invariant_id not in observed_invariants:
                        inherited_invariants.append(invariant)
                        observed_invariants.add(invariant_id)

            our_type._set_invariants(
                list(itertools.chain(inherited_invariants, our_type.invariants))
            )
        else:
            assert_never(our_type)


def _second_pass_to_stack_properties_in_place(symbol_table: SymbolTable) -> List[Error]:
    """Pass on the properties among the classes along the ontology."""
    for our_type in symbol_table.our_types_topologically_sorted:
        # NOTE (mristin, 2022-03-18):
        # Assume that the parents have all the invariants stacked already due to
        # the topological order of the iteration.

        # Propagate the properties from the parents to this one of our types
        if isinstance(our_type, (Enumeration, NamedUnion, ConstrainedPrimitive)):
            continue
        elif isinstance(our_type, (AbstractClass, ConcreteClass)):
            inherited_properties = []  # type: List[Property]

            # NOTE (mristin, 2023-03-25):
            # Skip duplicates which might arise from the diamond inheritance.
            #
            # Mind that we track instances using the Python ``id(.)`` function,
            # which means that the properties are literally equal, including their
            # type annotations.
            observed_properties = set()  # type: Set[int]

            for inheritance in our_type.inheritances:
                for prop in inheritance.properties:
                    property_id = id(prop)
                    if property_id not in observed_properties:
                        inherited_properties.append(prop)
                        observed_properties.add(property_id)

            our_type._set_properties(
                list(itertools.chain(inherited_properties, our_type.properties))
            )
        else:
            assert_never(our_type)

    return []


def _second_pass_to_stack_methods_in_place(symbol_table: SymbolTable) -> List[Error]:
    """Pass on the methods among the classes along the ontology."""
    errors = []  # type: List[Error]
    for our_type in symbol_table.our_types_topologically_sorted:
        # NOTE (mristin, 2022-03-18):
        # Assume that the parents have all the invariants stacked already due to
        # the topological order of the iteration.

        # Propagate the methods from the parents to this one of our types
        if isinstance(our_type, (Enumeration, NamedUnion, ConstrainedPrimitive)):
            continue
        elif isinstance(our_type, (AbstractClass, ConcreteClass)):
            inherited_methods = []  # type: List[MethodUnion]

            # NOTE (mristin, 2022-03-19):
            # We have to disallow diamond inheritance of the methods, so we keep track
            # of the inherited methods and report an error in case of conflicts.

            method_specified_for = dict()  # type: Dict[Identifier, Identifier]
            for inheritance in our_type.inheritances:
                for method in inheritance.methods:
                    conflicting_parent = method_specified_for.get(method.name, None)
                    if conflicting_parent is not None:
                        errors.append(
                            Error(
                                our_type.parsed.node,
                                f"The method {method.name!r} can not be inherited "
                                f"in the class {our_type.name!r} due to "
                                f"the diamond inheritance both "
                                f"from the parent {inheritance.name} and "
                                f"from the parent {conflicting_parent}",
                            )
                        )
                        continue

                    inherited_methods.append(method)
                    method_specified_for[method.name] = inheritance.name

            # NOTE (mristin, 2022-03-19):
            # We still haven't updated the ``methods`` in our type, so it only
            # contains methods specified for that particular class and does not
            # include any inherited methods.

            has_override = False
            for method in our_type.methods:
                conflicting_parent = method_specified_for.get(method.name, None)
                if conflicting_parent is not None:
                    errors.append(
                        Error(
                            method.parsed.node,
                            f"We do not support the overriding of the methods, "
                            f"but the method {method.name!r} is specified both in "
                            f"the class {our_type.name!r} "
                            f"and in {conflicting_parent!r}; "
                            f"if you need this functionality please contact "
                            f"the developers.",
                        )
                    )
                    has_override = True

            if has_override:
                continue

            our_type._set_methods(
                list(itertools.chain(inherited_methods, our_type.methods))
            )
        else:
            assert_never(our_type)

    return errors


def _second_pass_to_stack_constructors_in_place(
    symbol_table: SymbolTable,
) -> List[Error]:
    """In-line the super constructors and inherit the constructor contracts."""
    errors = []  # type: List[Error]

    for cls in symbol_table.classes:
        # NOTE (mristin, 2022-03-18):
        # Assume that the parents have all been processed already due to
        # the topological order of the iteration.

        # region In-line super constructors

        in_lined = []  # type: List[construction.AssignArgument]

        for statement in cls.constructor.statements:
            if isinstance(statement, construction.CallSuperConstructor):
                ancestor = symbol_table.find_our_type(statement.super_name)

                assert isinstance(ancestor, (AbstractClass, ConcreteClass)), (
                    f"Expected the ancestor of a class {cls.name!r} "
                    f"to be a class, but got: {ancestor}"
                )

                if ancestor is None:
                    errors.append(
                        Error(
                            (
                                cls.constructor.parsed.node
                                if cls.constructor.parsed is not None
                                else cls.parsed.node
                            ),
                            f"In the constructor of the class {cls.name!r} "
                            f"the super-constructor for "
                            f"the class {statement.super_name!r} is invoked, "
                            f"but the class {statement.super_name!r} could not "
                            f"be found",
                        )
                    )
                    continue

                if id(ancestor) not in cls.inheritance_id_set:
                    errors.append(
                        Error(
                            (
                                cls.constructor.parsed.node
                                if cls.constructor.parsed is not None
                                else cls.parsed.node
                            ),
                            f"In the constructor of the class {cls.name!r} "
                            f"the super-constructor for "
                            f"the class {statement.super_name!r} is invoked, "
                            f"but the class {statement.super_name!r} is not "
                            f"a direct parent of the class {cls.name!r}",
                        )
                    )
                    continue

                assert all(
                    not isinstance(a_statement, construction.CallSuperConstructor)
                    for a_statement in ancestor.constructor.inlined_statements
                ), (
                    f"Expected all the calls to super-constructors to be in-lined "
                    f"in the ancestor {ancestor.name} of the class {cls.name}"
                )

                in_lined.extend(ancestor.constructor.inlined_statements)
            else:
                in_lined.append(statement)

        # NOTE (mristin, 2022-03-19):
        # Restore the type safety at run-time
        assert all(isinstance(stmt, construction.AssignArgument) for stmt in in_lined)

        # NOTE (mristin, 2022-03-18):
        # The ``Final`` qualifier is meant for the external clients, not for the
        # internal clients in the submodules.
        # noinspection PyFinal,PyTypeHints
        cls.constructor.inlined_statements = in_lined  # type: ignore

        # endregion

        # region Stack contracts

        # NOTE (mristin, 2022-03-19):
        # The pre-conditions are not inherited in the constructors.
        # See a tutorial on design-by-contract. However, we do in-line
        # the calls to the super constructors. We leave it to the user to maintain
        # the list of pre-conditions and copy/paste them from the ancestors
        # manually.

        inherited_snapshots = []  # type: List[Snapshot]
        inherited_postconditions = []  # type: List[Contract]

        # NOTE (mristin, 2022-03-19):
        # We skip the duplicates since we have to deal with the diamond inheritance.
        observed_snapshots = set()  # type: Set[int]
        observed_postconditions = set()  # type: Set[int]

        for inheritance in cls.inheritances:
            for snap in inheritance.constructor.contracts.snapshots:
                snapshot_id = id(snap)
                if snapshot_id not in observed_snapshots:
                    inherited_snapshots.append(snap)
                    observed_snapshots.add(snapshot_id)

            for postcondition in inheritance.constructor.contracts.postconditions:
                postcondition_id = id(postcondition)
                if postcondition_id not in observed_postconditions:
                    inherited_postconditions.append(postcondition)
                    observed_postconditions.add(postcondition_id)

        # NOTE (mristin, 2022-03-18):
        # The ``Final`` qualifier is meant for the external clients, not for the
        # internal clients in the submodules.

        # noinspection PyFinal
        cls.constructor.contracts.snapshots = list(  # type: ignore
            itertools.chain(inherited_snapshots, cls.constructor.contracts.snapshots)
        )

        # noinspection PyFinal
        cls.constructor.contracts.postconditions = list(  # type: ignore
            itertools.chain(
                inherited_postconditions,
                cls.constructor.contracts.postconditions,
            )
        )

        # endregion

    return errors


def _second_pass_to_resolve_references_to_attributes_in_the_descriptions_in_place(
    symbol_table: SymbolTable,
) -> List[Error]:
    """Resolve the references to attributes in the descriptions in-place."""
    errors = []  # type: List[Error]

    # The ``our_type`` is None if the description is in the context outside our type.
    for attr_ref_in_doc, description, our_type in _find_all_in_descriptions(
        element_type=doc.ReferenceToAttribute, symbol_table=symbol_table
    ):
        if isinstance(attr_ref_in_doc.reference, _PlaceholderReferenceToAttribute):
            pth = attr_ref_in_doc.reference.path

            if pth.startswith("."):
                errors.append(
                    Error(
                        description.parsed.node,
                        f"The references with relaxed qualified names to attributes "
                        f"are not allowed as we can not resolve references outside "
                        f"of the meta-model: {pth}",
                    )
                )
                continue

            parts = pth.split(".")

            if any(not IDENTIFIER_RE.match(part) for part in parts):
                errors.append(
                    Error(
                        description.parsed.node,
                        f"Invalid reference to a property or a literal; "
                        f"each part of the path needs to be an identifier, "
                        f"but it is not: {pth}",
                    )
                )
                continue

            part_identifiers = [Identifier(part) for part in parts]

            if len(part_identifiers) == 0:
                errors.append(
                    Error(
                        description.parsed.node,
                        "Unexpected empty reference to a property or a literal",
                    )
                )
                continue

            # noinspection PyUnusedLocal
            target_our_type = None  # type: Optional[OurType]

            # noinspection PyUnusedLocal
            attr_identifier = None  # type: Optional[Identifier]

            if len(part_identifiers) == 1:
                if our_type is None:
                    errors.append(
                        Error(
                            description.parsed.node,
                            f"The attribute reference can not be resolved as there "
                            f"is no encompassing our type in the given "
                            f"context: {pth}",
                        )
                    )
                    continue

                target_our_type = our_type
                attr_identifier = part_identifiers[0]
            elif len(part_identifiers) == 2:
                target_our_type = symbol_table.find_our_type(part_identifiers[0])
                if target_our_type is None:
                    errors.append(
                        Error(
                            description.parsed.node,
                            f"Dangling reference to a non-existing our type: {pth}",
                        )
                    )
                    continue

                attr_identifier = part_identifiers[1]
            else:
                errors.append(
                    Error(
                        description.parsed.node,
                        f"We did not implement the resolution of such "
                        f"a reference to a property or a literal: {pth}",
                    )
                )
                continue

            assert target_our_type is not None
            assert attr_identifier is not None

            reference: Optional[
                Union[doc.ReferenceToProperty, doc.ReferenceToEnumerationLiteral]
            ] = None

            if isinstance(target_our_type, Enumeration):
                literal = target_our_type.literals_by_name.get(attr_identifier, None)

                if literal is None:
                    errors.append(
                        Error(
                            description.parsed.node,
                            f"Dangling reference to a non-existing literal "
                            f"in the enumeration {target_our_type.name!r}: {pth}",
                        )
                    )
                    continue

                reference = doc.ReferenceToEnumerationLiteral(
                    enumeration=target_our_type, literal=literal
                )

            elif isinstance(target_our_type, ConstrainedPrimitive):
                errors.append(
                    Error(
                        description.parsed.node,
                        f"Unexpected references to a property of "
                        f"a constrained primitive {target_our_type.name!r}: {pth}",
                    )
                )
                continue

            elif isinstance(target_our_type, NamedUnion):
                errors.append(
                    Error(
                        description.parsed.node,
                        f"Unexpected references to a property of "
                        f"a named union {target_our_type.name!r}: {pth}",
                    )
                )
                continue

            elif isinstance(target_our_type, (AbstractClass, ConcreteClass)):
                prop = target_our_type.properties_by_name.get(attr_identifier, None)

                if prop is None:
                    errors.append(
                        Error(
                            description.parsed.node,
                            f"Dangling reference to a non-existing property "
                            f"of a class {target_our_type.name!r}: {pth}",
                        )
                    )
                    continue

                reference = doc.ReferenceToProperty(cls=target_our_type, prop=prop)

            else:
                assert_never(target_our_type)

            assert reference is not None
            attr_ref_in_doc.reference = reference

    return errors


# fmt: off
@require(
    lambda symbol_table:
    all(
        isinstance(cls.interface, _MaybeInterfacePlaceholder)
        for cls in symbol_table.classes
    ),
    "None of the interfaces resolved"
)
@ensure(
    lambda symbol_table:
    all(
        # Exhaustive pattern matching
        (
                not isinstance(cls, AbstractClass)
                or isinstance(cls.interface, Interface)
        )
        and (
                not isinstance(cls, ConcreteClass)
                or (
                        cls.interface is None
                        or isinstance(cls.interface, Interface)
                )
        )
        for cls in symbol_table.classes
    ),
    "All interfaces resolved"
)
# fmt: on
def _second_pass_to_resolve_interfaces_in_place(
    symbol_table: SymbolTable, ontology: _hierarchy.Ontology
) -> None:
    """
    Resolve interface placeholders in the classes in-place.

    All abstract classes as well as concrete classes with at least one descendant
    are mapped to an interface.

    Mind that the concept of the interface is not used in the meta-model, and we
    introduce it only as a convenience for the code generation.
    """
    for parsed_cls in ontology.classes:
        cls = symbol_table.must_find_class_or_constrained_primitive(parsed_cls.name)

        assert cls.parsed is parsed_cls

        if isinstance(cls, ConstrainedPrimitive):
            # Constrained primitives do not provide an interface as their interface
            # is the interface of their constrainee.
            continue

        # Make sure we covered all the cases in the if-statement below
        assert isinstance(cls, (AbstractClass, ConcreteClass))

        assert isinstance(cls.interface, _MaybeInterfacePlaceholder), (
            f"Expected the class {cls.name!r} to have a placeholder as an interface, "
            f"but got: {cls.interface!r}"
        )

        if (
            isinstance(cls, AbstractClass)
            or len(ontology.list_descendants(parsed_cls)) > 0
        ):
            parent_interfaces = []  # type: List[Interface]

            for inheritance_name in parsed_cls.inheritances:
                parent_cls = symbol_table.must_find_class(inheritance_name)

                parent_interface = parent_cls.interface
                assert isinstance(parent_interface, Interface), (
                    f"We expect the classes in the ontology to be topologically "
                    f"sorted. Hence the interface for the parent {inheritance_name!r} "
                    f"of the class {parsed_cls.name!r} must have been defined, but "
                    f"it was not: {parent_interface=}."
                )

                parent_interfaces.append(parent_interface)

            interface = Interface(base=cls, inheritances=parent_interfaces)

            cls.interface = interface
        else:
            assert isinstance(cls, ConcreteClass)
            cls.interface = None


def _second_pass_to_resolve_named_union_implementers_in_place(
    symbol_table: SymbolTable,
) -> None:
    """
    Flatten the members of every named union into their concrete implementers.

    This assumes that the named union members have already been resolved (see
    :func:`_second_pass_to_resolve_named_union_members_in_place`), every class's
    ``concrete_descendants`` has already been resolved (see
    :func:`_second_pass_to_resolve_ancestors_and_descendants_in_place`), and that
    we iterate the named unions in the topological order over the named-union
    dependency graph (see
    :func:`_topologically_sort_named_unions_or_find_cycle`) -- via
    ``symbol_table.our_types_topologically_sorted``, *not*
    ``symbol_table.named_unions`` -- so that a named-union member's own
    ``implementers`` is already resolved by the time we need it here.
    """
    for our_type in symbol_table.our_types_topologically_sorted:
        if not isinstance(our_type, NamedUnion):
            continue

        named_union = our_type

        implementers = []  # type: List[ConcreteClass]
        observed_ids = set()  # type: Set[int]

        for member in named_union.members:
            if isinstance(member, NamedUnion):
                # NOTE (mristin):
                # The member's own implementers are already flattened (and
                # transitively include no further named unions), since we
                # iterate in the topological order over the named-union
                # dependency graph.
                candidates = list(member.implementers)
            else:
                # NOTE (mristin):
                # Mirrors ``Interface.__init__``'s computation of
                # ``implementers``: a concrete class can be instantiated
                # directly (so it contributes itself), on top of contributing
                # all of its concrete descendants (whether it is abstract or
                # concrete).
                candidates = list(member.concrete_descendants)
                if isinstance(member, ConcreteClass):
                    candidates.append(member)

            for candidate in candidates:
                if id(candidate) not in observed_ids:
                    implementers.append(candidate)
                    observed_ids.add(id(candidate))

        named_union._set_implementers(implementers)


class _PropertyOfClass:
    """Represent the property with its corresponding class."""

    def __init__(self, prop: Property, cls: Class):
        """Initialize with the given values."""
        self.prop = prop
        self.cls = cls


class _ContractChecker(parse_tree.Visitor):
    """
    Verify that the contracts are well-formed.

    For example, check that the calls to verification functions are valid.
    """

    #: Symbol table to be used for de-referencing our types, functions *etc.*
    symbol_table: Final[SymbolTable]

    #: Errors observed during the verification
    errors: List[Error]

    def __init__(self, symbol_table: SymbolTable):
        """Initialize with the given values."""
        self.symbol_table = symbol_table

        self.errors = []

    def visit_function_call(self, node: parse_tree.FunctionCall) -> None:
        verification_function = self.symbol_table.verification_functions_by_name.get(
            node.name.identifier, None
        )

        if verification_function is not None:
            expected_argument_count = len(verification_function.arguments)
        elif node.name.identifier == "len":
            expected_argument_count = 1
        else:
            self.errors.append(
                Error(
                    node.original_node,
                    f"The handling of the function is "
                    f"not implemented as we do not know how many arguments it expects: "
                    f"{node.name.identifier!r}",
                )
            )
            return

        if len(node.args) != expected_argument_count:
            self.errors.append(
                Error(
                    node.original_node,
                    f"Expected exactly {expected_argument_count} arguments "
                    f"to a function call to {node.name.identifier!r}, "
                    f"but got: {len(node.args)}",
                )
            )

        for arg in node.args:
            self.visit(arg)


def _over_signature_likes(symbol_table: SymbolTable) -> Iterator[SignatureLike]:
    """
    Iterate over all signature-like instances in the symbol table.

    Since interfaces are constructed on top of abstract classes and concrete classes
    with descendants, we do not iterate here over the signatures in the interfaces.
    """
    yield from symbol_table.verification_functions

    for cls in symbol_table.classes:
        yield from cls.methods

        yield cls.constructor

        # We do not recurse here into signatures of interfaces since they are based
        # on the methods of the corresponding class.


def _verify_there_are_no_duplicate_names_of_our_types(
    symbol_table: SymbolTable,
) -> List[Error]:
    errors = []  # type: List[Error]

    observed_names = dict()  # type: MutableMapping[Identifier, OurType]
    for our_type in symbol_table.our_types:
        another_our_type = observed_names.get(our_type.name, None)
        if another_our_type is None:
            observed_names[our_type.name] = our_type
        else:
            errors.append(
                Error(
                    our_type.parsed.node,
                    f"Our type with the name {our_type.name!r} conflicts with "
                    f"another our type with the same name.",
                )
            )

    return errors


def _verify_with_model_type_for_classes_with_at_least_one_concrete_descendant(
    symbol_table: SymbolTable,
) -> List[Error]:
    errors = []  # type: List[Error]

    our_types_in_properties = collect_ids_of_our_types_in_properties(
        symbol_table=symbol_table
    )

    for cls in symbol_table.classes:
        if id(cls) in our_types_in_properties:
            if len(cls.concrete_descendants) >= 1:
                if not cls.serialization.with_model_type:
                    descendants_str = ", ".join(
                        repr(descendant.name) for descendant in cls.concrete_descendants
                    )

                    errors.append(
                        Error(
                            cls.parsed.node,
                            f"The class {cls.name!r} has one or more concrete "
                            f"descendants ({descendants_str}), but its serialization "
                            f"setting ``with_model_type`` has not been set. We need "
                            f"to discriminate on model type at the de-serialization.",
                        )
                    )

                for descendant in cls.concrete_descendants:
                    if not descendant.serialization.with_model_type:
                        errors.append(
                            Error(
                                descendant.parsed.node,
                                f"The class {descendant.name!r} needs to have "
                                f"serialization setting ``with_model_type`` set since "
                                f"it is among the concrete descendant classes of "
                                f"the class {cls.name!r}. We need to discriminate "
                                f"on model type at the de-serialization",
                            )
                        )

    return errors


def _verify_named_unions_are_dispatchable_in_json(
    symbol_table: SymbolTable,
) -> List[Error]:
    """
    Verify that every named union can be de-serialized from JSON unambiguously.

    Every one of a named union's (flattened) implementers must be dispatchable
    either:

    * by its ``modelType`` -- if ``with_model_type`` is set on it, a
      ``modelType`` field is always present on the wire for that implementer to
      dispatch on, and every class name (hence every ``modelType`` value) is
      unique across the whole meta-model, so no two such implementers can ever
      be confused for one another; or
    * structurally -- among *only* the implementers of the same union which do
      *not* have ``with_model_type`` set, every required (non-optional)
      property must be required by at most one such implementer, so the set of
      keys present in a JSON object lacking a ``modelType`` field is enough to
      unambiguously tell them apart.

    These two dispatch mechanisms do not need to agree union-wide -- a single
    union may freely mix implementers dispatched by ``modelType`` with
    implementers dispatched structurally, as the two are mutually exclusive on
    the wire (an object either carries a ``modelType`` field or it does not).
    """
    errors = []  # type: List[Error]

    for named_union in symbol_table.named_unions:
        implementers_without_model_type = [
            implementer
            for implementer in named_union.implementers
            if not implementer.serialization.with_model_type
        ]

        if len(implementers_without_model_type) == 0:
            continue

        # region Check required properties disjoint among non-modelType implementers

        required_property_names_by_implementer = {
            implementer: [
                prop.name
                for prop in implementer.properties
                if not isinstance(prop.type_annotation, OptionalTypeAnnotation)
            ]
            for implementer in implementers_without_model_type
        }

        implementers_without_a_required_property = [
            implementer
            for implementer, required in required_property_names_by_implementer.items()
            if len(required) == 0
        ]

        if len(implementers_without_a_required_property) > 0:
            names_str = ", ".join(
                repr(implementer.name)
                for implementer in implementers_without_a_required_property
            )
            errors.append(
                Error(
                    named_union.parsed.node,
                    f"The named union {named_union.name!r} can not be dispatched "
                    f"unambiguously during the de-serialization from JSON: "
                    f"the following implementer(s) do not have ``with_model_type`` "
                    f"set, so we would need to fall back to distinguishing them by "
                    f"their required properties, but they have no required "
                    f"properties of their own at all, so they can not be told "
                    f"apart from any other implementer this way: {names_str}. "
                    f"Either set ``with_model_type=True`` on the implementer(s) "
                    f"listed above, or make sure they each have at least one "
                    f"required property not shared with any other implementer "
                    f"of the union that also lacks ``with_model_type``.",
                )
            )
            continue

        implementers_by_required_property_name = collections.defaultdict(
            list
        )  # type: MutableMapping[Identifier, List[ConcreteClass]]

        for implementer, required in required_property_names_by_implementer.items():
            for prop_name in required:
                implementers_by_required_property_name[prop_name].append(implementer)

        conflicts = [
            f"the required property {prop_name!r} is shared "
            f"between {', '.join(repr(implementer.name) for implementer in conflicting)}"
            for prop_name, conflicting in implementers_by_required_property_name.items()
            if len(conflicting) > 1
        ]

        if len(conflicts) > 0:
            errors.append(
                Error(
                    named_union.parsed.node,
                    f"The named union {named_union.name!r} can not be dispatched "
                    f"unambiguously during the de-serialization from JSON: "
                    f"the implementer(s) which do not have ``with_model_type`` set "
                    f"would need to be distinguished by their required properties, "
                    f"but their required properties are not pairwise disjoint "
                    f"({'; '.join(conflicts)}). Either set ``with_model_type=True`` "
                    f"on the conflicting implementer(s), or make sure their "
                    f"required properties are disjoint from every other "
                    f"implementer of the union that also lacks ``with_model_type``.",
                )
            )

        # endregion

    return errors


def _verify_all_the_function_calls_in_the_contracts_are_valid(
    symbol_table: SymbolTable,
) -> List[Error]:
    contract_checker = _ContractChecker(symbol_table=symbol_table)

    for signature_like in _over_signature_likes(symbol_table):
        for contract_or_snapshot in itertools.chain(
            signature_like.contracts.preconditions,
            signature_like.contracts.postconditions,
            signature_like.contracts.snapshots,
        ):
            assert isinstance(contract_or_snapshot, (Contract, Snapshot))
            contract_checker.visit(contract_or_snapshot.body)

    for cls in symbol_table.classes:
        for invariant in cls.invariants:
            contract_checker.visit(invariant.body)

    return contract_checker.errors


def _verify_all_properties_are_initialized_in_the_constructor(
    symbol_table: SymbolTable,
) -> List[Error]:
    """
    Check that all required properties of the class are initialized in the constructor.

    For example, check that there is a default value assigned if the constructor
    argument is optional.
    """
    errors = []  # type: List[Error]

    for cls in symbol_table.classes:
        prop_initialized = {prop.name: False for prop in cls.properties}

        for stmt in cls.constructor.inlined_statements:
            # NOTE (mristin, 2021-12-19):
            # Check for type here since it is very likely that we introduce more
            # statement types in the future. This assertion should warn us in that case.
            assert isinstance(stmt, construction.AssignArgument)

            prop = cls.properties_by_name.get(stmt.name, None)
            assert (
                prop is not None
            ), f"This should have been caught before: {stmt.name=}"

            if isinstance(prop.type_annotation, OptionalTypeAnnotation):
                # Since the property is optional, it is enough that we assigned it to
                # *something*, be it a ``None`` or something else.
                prop_initialized[prop.name] = True

            else:
                # The property is mandatory.

                constructor_arg = cls.constructor.arguments_by_name.get(
                    stmt.argument, None
                )
                assert (
                    constructor_arg is not None
                ), f"This should have been caught before. {stmt.argument=}"

                if not isinstance(
                    constructor_arg.type_annotation, OptionalTypeAnnotation
                ):
                    # We know that the property is properly initialized since
                    # the constructor argument is not optional.
                    prop_initialized[prop.name] = True

                elif stmt.default is not None:
                    if isinstance(
                        stmt.default,
                        (construction.EmptyList, construction.DefaultEnumLiteral),
                    ):
                        # The property is mandatory, but a non-None default value is
                        # given in the assign statement, so we know that the property is
                        # properly initialized.
                        prop_initialized[prop.name] = True
                    else:
                        assert_never(stmt.default)
                else:
                    # The property remains improperly initialized since the default
                    # value has not been indicated, the property is not optional and
                    # the constructor argument is optional.
                    pass

        for prop_name, is_initialized in prop_initialized.items():
            if not is_initialized:
                errors.append(
                    Error(
                        (
                            cls.constructor.parsed.node
                            if cls.constructor.parsed is not None
                            else cls.parsed.node
                        ),
                        f"The property {prop_name!r} is not properly initialized "
                        f"in the constructor of the class {cls.name!r}.",
                    )
                )

    return errors


def _verify_optional_constructor_arguments_default_to_none(
    symbol_table: SymbolTable,
) -> List[Error]:
    """
    Check that all optional constructor arguments are set to ``None``.

    While other values are possible, we enforce ``None`` for consistency to avoid
    confusion of the users of the generated code.
    """
    errors = []  # type: List[Error]

    for cls in symbol_table.classes:
        for arg in cls.constructor.arguments:
            if not isinstance(arg.type_annotation, OptionalTypeAnnotation):
                continue

            if arg.default is None:
                errors.append(
                    Error(
                        arg.parsed.node,
                        f"Expected the optional constructor argument {arg.name!r} "
                        f"of class {cls.name!r} to default to ``None``, "
                        f"but no default has been set.",
                    )
                )
                continue

            if (
                not isinstance(arg.default, DefaultPrimitive)
                or arg.default.value is not None
            ):
                errors.append(
                    Error(
                        arg.parsed.node,
                        f"Expected the optional constructor argument {arg.name!r} "
                        f"of class {cls.name!r} to default to ``None``, "
                        f"but it was set to a non-None default.",
                    )
                )

    return errors


def _verify_constructor_arguments_and_properties_match(
    symbol_table: SymbolTable,
) -> List[Error]:
    """
    Verify that the constructor arguments and the properties match for all classes.

    We check both the order and the types.
    """
    errors = []  # type: List[Error]

    for cls in symbol_table.classes:
        if (
            sum(1 for prop in cls.properties if prop.specified_for is cls) > 0
            and cls.constructor.parsed is None
        ):
            errors.append(
                Error(
                    cls.parsed.node,
                    f"No constructor has been specified for the class {cls.name!r}, "
                    f"but there are class-specific properties.",
                )
            )
            continue

        arg_name_set = set(arg.name for arg in cls.constructor.arguments)
        prop_name_set = set(prop.name for prop in cls.properties)
        if arg_name_set != prop_name_set:
            errors.append(
                Error(
                    cls.parsed.node,
                    f"The properties and constructor arguments do not coincide. "
                    f"The set of constructor arguments is: {sorted(arg_name_set)} "
                    f"and the set of properties is: {set(prop_name_set)}",
                )
            )
            continue

        args_without_default = []  # type: List[Identifier]
        args_without_default_set = set()  # type: Set[Identifier]

        args_with_default = []  # type: List[Identifier]
        args_with_default_set = set()  # type: Set[Identifier]

        # NOTE (mristin, 2022-03-25):
        # This verification is only a heuristic since we do not really analyze
        # the code and only look into the names of the properties and arguments.

        for arg in cls.constructor.arguments:
            if arg.name not in cls.properties_by_name:
                continue

            if arg.default is None:
                args_without_default.append(arg.name)
                args_without_default_set.add(arg.name)
            else:
                args_with_default.append(arg.name)
                args_with_default_set.add(arg.name)

        # The order of the properties corresponding to the constructor
        # arguments without the default value
        props_without_default = [
            prop.name
            for prop in cls.properties
            if prop.name in args_without_default_set
        ]

        # The order of the properties corresponding to the constructor arguments
        # with the specified default value
        props_with_default = [
            prop.name for prop in cls.properties if prop.name in args_with_default_set
        ]

        ordered_args = args_without_default + args_with_default
        ordered_props = props_without_default + props_with_default

        if ordered_args != ordered_props:
            errors.append(
                Error(
                    (
                        cls.constructor.parsed.node
                        if cls.constructor.parsed is not None
                        else cls.parsed.node
                    ),
                    f"The order of constructor arguments and properties "
                    f"for the class {cls.name!r} is not maintained "
                    f"where they match by name. "
                    f"The partial order of constructor arguments "
                    f"should be: {ordered_props!r}",
                )
            )
            continue

        if len(errors) > 0:
            return errors

        assert set(cls.properties_by_name.keys()) == set(
            cls.constructor.arguments_by_name.keys()
        )
        for prop in cls.properties:
            assert prop.name in cls.constructor.arguments_by_name, (
                f"Expected th at we already checked that properties and "
                f"constructor arguments match, but the corresponding "
                f"constructor argument is missing for the property: {prop.name!r}"
            )

            arg = cls.constructor.arguments_by_name[prop.name]

            if not type_annotations_equal(prop.type_annotation, arg.type_annotation):
                errors.append(
                    Error(
                        (
                            cls.constructor.parsed.node
                            if cls.constructor.parsed is not None
                            else cls.parsed.node
                        ),
                        f"The constructor argument {arg.name!r} "
                        f"and the property {prop.name!r} "
                        f"for the class {cls.name!r} "
                        f"mismatch in type. The argument is typed "
                        f"as {arg.type_annotation} while the property is "
                        f"typed as {prop.type_annotation}. "
                        f"We expect the constructors and the properties to match "
                        f"in type.",
                    )
                )

    return errors


def _verify_all_references_to_arguments_occur_in_valid_context(
    symbol_table: SymbolTable,
) -> List[Error]:
    # noinspection GrazieInspection
    """Verify that all the argument references occur where they should."""
    errors = []  # type: List[Error]
    for arg_ref_in_doc, description, _ in _find_all_in_descriptions(
        element_type=doc.ReferenceToArgument, symbol_table=symbol_table
    ):
        if not isinstance(description, DescriptionOfSignature):
            errors.append(
                Error(
                    description.parsed.node,
                    f"Unexpected argument reference in the description of "
                    f"a non-signature (*i.e.*, a non-function and a non-method): "
                    f"{arg_ref_in_doc}",
                )
            )

    return errors


def _verify_constraints_and_constraintrefs(symbol_table: SymbolTable) -> List[Error]:
    """Check that each constraint has a unique identifier."""
    errors = []  # type: List[Error]
    observed_constraint_id_set = set()  # type: Set[str]

    def check_and_report_duplicate(
        an_identifier: str, a_description: DescriptionUnion
    ) -> None:
        """If the identifier has been already observed, report a duplicate."""
        if an_identifier in observed_constraint_id_set:
            errors.append(
                Error(
                    a_description.parsed.node,
                    f"The constraint with the same identifier has been already "
                    f"defined: {an_identifier!r}",
                )
            )

    if symbol_table.meta_model.description is not None:
        for identifier in symbol_table.meta_model.description.constraints_by_identifier:
            check_and_report_duplicate(
                an_identifier=identifier,
                a_description=symbol_table.meta_model.description,
            )
            observed_constraint_id_set.add(identifier)

    for our_type in symbol_table.our_types:
        if our_type.description is not None:
            for identifier in our_type.description.constraints_by_identifier:
                check_and_report_duplicate(
                    an_identifier=identifier, a_description=our_type.description
                )
                observed_constraint_id_set.add(identifier)

        if isinstance(our_type, (Enumeration, NamedUnion, ConstrainedPrimitive)):
            pass
        elif isinstance(our_type, (AbstractClass, ConcreteClass)):
            for prop in our_type.properties:
                if prop.specified_for is not our_type:
                    continue

                if prop.description is not None:
                    for identifier in prop.description.constraints_by_identifier:
                        check_and_report_duplicate(
                            an_identifier=identifier, a_description=prop.description
                        )
                        observed_constraint_id_set.add(identifier)
        else:
            assert_never(our_type)

    for constraintref, description, _ in _find_all_in_descriptions(
        element_type=doc.ReferenceToConstraint, symbol_table=symbol_table
    ):
        assert isinstance(constraintref.reference, str)

        if constraintref.reference not in observed_constraint_id_set:
            errors.append(
                Error(
                    description.parsed.node,
                    f"The constraint reference is dangling: {constraintref.reference}",
                )
            )

    return errors


def _verify_description_rendering_with_smoke(symbol_table: SymbolTable) -> List[Error]:
    """Check that we can smoke-render all the descriptions."""

    class DummyRenderer(doc.DocutilsElementTransformer[bool]):
        """Perform a smoke rendering to test that all the elements have been covered."""

        def transform_text(
            self, element: docutils.nodes.Text
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_reference_to_our_type_in_doc(
            self, element: doc.ReferenceToOurType
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_reference_to_attribute_in_doc(
            self, element: doc.ReferenceToAttribute
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_reference_to_argument_in_doc(
            self, element: doc.ReferenceToArgument
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_reference_to_constraint_in_doc(
            self, element: doc.ReferenceToConstraint
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_reference_to_constant_in_doc(
            self, element: doc.ReferenceToConstraint
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_literal(
            self, element: docutils.nodes.literal
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_paragraph(
            self, element: docutils.nodes.paragraph
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_emphasis(
            self, element: docutils.nodes.emphasis
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_list_item(
            self, element: docutils.nodes.list_item
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_bullet_list(
            self, element: docutils.nodes.bullet_list
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_note(
            self, element: docutils.nodes.note
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_reference(
            self, element: docutils.nodes.reference
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_field_body(
            self, element: docutils.nodes.field_body
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

        def transform_document(
            self, element: docutils.nodes.field_body
        ) -> Tuple[Optional[bool], Optional[List[str]]]:
            return True, None

    renderer = DummyRenderer()

    errors_by_description = (
        collections.OrderedDict()
    )  # type: OrderedDict[DescriptionUnion, List[Error]]

    for an_element, description, _ in _find_all_in_descriptions(
        element_type=docutils.nodes.Element, symbol_table=symbol_table
    ):
        _, transformation_errors = renderer.transform(element=an_element)

        if transformation_errors is not None:
            description_errors = errors_by_description.get(description, None)
            if description_errors is None:
                description_errors = []
                errors_by_description[description] = description_errors

            description_errors.extend(
                Error(description.parsed.node, error_message)
                for error_message in transformation_errors
            )

    errors = []  # type: List[Error]
    for description, description_errors in errors_by_description.items():
        assert len(description_errors) > 0
        errors.append(
            Error(
                description.parsed.node,
                "Failed to test-smoke the rendering of the description",
                description_errors,
            )
        )

    return errors


def _verify_only_simple_type_patterns(symbol_table: SymbolTable) -> List[Error]:
    """
    Check that there are only simple type patterns in the meta-model.

    Namely, for a lot of code generators, unrolling arbitrary type annotations is
    quite complex. In contrast, if we can make simplifying assumptions about the types
    in the meta-model, we can write much simpler generators.

    First, the meta-model is quite limited itself at the moment, so the complexity of
    the general solutions is not warranted. Second, we hope that there will be fewer
    bugs in the simple solution which is particularly important at this early adoption
    stage.

    We anticipate that we will want to actually write the more complex generators
    in the future. At this point, we restrict ourselves to the following patterns:

    * Non-nested optional types, *i.e.* optional of optionals, are unexpected;
    * Lists of optionals are unexpected;
    * Lists of non-classes are unexpected;
    * Tuples of optionals are unexpected; and
    * Tuples of non-atomic types (*i.e.* of lists, tuples or optionals) are
      unexpected -- we only support tuples of primitives, constrained primitives,
      classes and enumerations.
    """
    errors = []  # type: List[Error]
    for cls in symbol_table.classes:
        for prop in cls.properties:
            if isinstance(prop.type_annotation, OptionalTypeAnnotation) and isinstance(
                prop.type_annotation.value, OptionalTypeAnnotation
            ):
                errors.append(
                    Error(
                        prop.parsed.node,
                        "We currently support only a limited set of "
                        "type annotation patterns. At the moment, we do not handle "
                        "nested optionals. Please contact the developers if you "
                        "need this functionality",
                    )
                )

            type_anno = beneath_optional(prop.type_annotation)
            if isinstance(type_anno, ListTypeAnnotation):
                if isinstance(type_anno.items, OptionalTypeAnnotation):
                    errors.append(
                        Error(
                            prop.parsed.node,
                            f"We currently support only a limited set of "
                            f"type annotation patterns. At the moment, we handle "
                            f"only lists non-optionals, "
                            f"but the property {prop.name!r} "
                            f"of the class {cls.name!r} "
                            f"has type: {prop.type_annotation}. "
                            f"Please contact the developers if you need "
                            f"this functionality",
                        )
                    )

            elif isinstance(type_anno, TupleTypeAnnotation):
                if not all(
                    isinstance(item, AtomicTypeAnnotationAsTuple)
                    for item in type_anno.items
                ):
                    errors.append(
                        Error(
                            prop.parsed.node,
                            f"We currently support only a limited set of "
                            f"type annotation patterns. At the moment, we handle "
                            f"only tuples of primitives, constrained primitives, "
                            f"classes and enumerations (*i.e.* no tuples of "
                            f"optionals, lists or nested tuples), "
                            f"but the property {prop.name!r} "
                            f"of the class {cls.name!r} "
                            f"has type: {prop.type_annotation}. "
                            f"Please contact the developers if you need "
                            f"this functionality",
                        )
                    )

    return errors


def _verify_invariant_descriptions_unique(symbol_table: SymbolTable) -> List[Error]:
    """Check that no two invariants share the same description."""
    errors = []  # type: List[Error]
    for something_with_invariants in itertools.chain(
        symbol_table.classes, symbol_table.constrained_primitives
    ):
        description_map = dict()  # type: MutableMapping[str, Invariant]

        for invariant in something_with_invariants.invariants:
            conflicting_invariant = description_map.get(invariant.description, None)
            if conflicting_invariant is not None:
                what: str
                if isinstance(something_with_invariants, Class):
                    what = "class"
                elif isinstance(something_with_invariants, ConstrainedPrimitive):
                    what = "constrained primitive"
                else:
                    assert_never(something_with_invariants)

                if conflicting_invariant.specified_for is invariant.specified_for:
                    errors.append(
                        Error(
                            invariant.parsed.node,
                            f"The invariants' descriptions need to be unique, "
                            f"but they conflict "
                            f"in the {what} {invariant.specified_for.name!r} "
                            f"for the description: {invariant.description!r}",
                        )
                    )
                else:
                    errors.append(
                        Error(
                            invariant.parsed.node,
                            f"The invariants' descriptions need to be unique, "
                            f"but an invariant from "
                            f"the {what} {invariant.specified_for.name!r} "
                            f"and from "
                            f"the {what} {conflicting_invariant.specified_for.name!r} "
                            f"conflict for the description: {invariant.description!r}",
                        )
                    )
            else:
                description_map[invariant.description] = invariant

    return errors


def _verify_patterns_anchored_at_start_and_end(
    symbol_table: SymbolTable,
) -> List[Error]:
    """
    Check that the patterns are anchored at the start (``^``) and at the end (``$``).

    We need to make sure that all pattern verification functions can be transpiled into
    many kinds of regular expressions. Some regular expression engines support
    only patterns anchored at both ends (*e.g.*, XSD and the transpilation of regular
    expressions to instructions of a virtual machine). To ensure inter-operability,
    we decide to fail-fast here to prevent that non-anchored patterns propagate
    downstream, which we might probably detect only much later.
    """
    errors = []  # type: List[Error]
    for verification in symbol_table.verification_functions:
        if isinstance(verification, PatternVerification):
            regex, error = parse_retree.parse([verification.pattern])
            if error is not None:
                regex_line, pointer_line = parse_retree.render_pointer(error.cursor)

                errors.append(
                    Error(
                        verification.parsed.node,
                        f"Failed to parse the pattern of "
                        f"the pattern verification function:\n"
                        f"{error.message}\n"
                        f"{regex_line}\n"
                        f"{pointer_line}",
                    )
                )
                continue

            assert regex is not None

            if (
                len(regex.union.uniates) == 0
                or len(regex.union.uniates[0].concatenants) == 0
            ):
                errors.append(
                    Error(
                        verification.parsed.node,
                        f"The pattern is empty. We expect only non-empty patterns "
                        f"all anchored at the start (``^``) and at the end (``$``) "
                        f"for inter-operability with different regex engines, *e.g.*, "
                        f"XSD engines. The pattern in question inferred for "
                        f"the verification function {verification.name!r} "
                        f"was: {verification.pattern}",
                    )
                )
                continue

            first_term = regex.union.uniates[0].concatenants[0]
            last_term = regex.union.uniates[0].concatenants[-1]

            if (
                len(regex.union.uniates) != 1
                or not isinstance(first_term.value, parse_retree.Symbol)
                or not (first_term.value.kind is parse_retree.SymbolKind.START)
                or not isinstance(last_term.value, parse_retree.Symbol)
                or not (last_term.value.kind is parse_retree.SymbolKind.END)
            ):
                errors.append(
                    Error(
                        verification.parsed.node,
                        f"(mristin, 2024-05-31): We expect all the patterns to be "
                        f"anchored at the start (``^``) and at the end (``$``) for "
                        f"inter-operability with different regex engines, *e.g.*, XSD "
                        f"engines. Please consider re-writing your pattern with "
                        f"a prefix ``^.*``, if you want to match an arbitrary prefix, "
                        f"and a suffix ``.*$``, if you want to match an arbitrary "
                        f"suffix. The pattern in question inferred for "
                        f"the verification function {verification.name!r} "
                        f"was: {verification.pattern}",
                    )
                )

    return errors


def _assert_interfaces_defined_correctly(
    symbol_table: SymbolTable, ontology: _hierarchy.Ontology
) -> None:
    # NOTE (mristin, 2021-12-15):
    # We expect the interfaces of the classes to be defined only for abstract classes
    # and for the concrete classes with at least one descendant.

    for cls in symbol_table.classes:
        if (
            isinstance(cls, AbstractClass)
            or len(ontology.list_descendants(cls.parsed)) > 0
        ):
            assert isinstance(cls.interface, Interface)
        else:
            assert cls.interface is None


def _assert_all_class_inheritances_defined_an_interface(
    symbol_table: SymbolTable,
) -> None:
    for cls in symbol_table.classes:
        for inheritance in cls.inheritances:
            assert isinstance(inheritance.interface, Interface), (
                f"Since the class {cls.name!r} inherits "
                f"from {inheritance.name!r}, "
                f"we expect that the class {inheritance.name!r} also has an interface "
                f"defined for it, but it does not."
            )


def _assert_self_not_in_concrete_descendants(symbol_table: SymbolTable) -> None:
    for our_type in symbol_table.our_types:
        if isinstance(our_type, (Enumeration, NamedUnion)):
            continue
        elif isinstance(our_type, (ConstrainedPrimitive, AbstractClass, ConcreteClass)):
            assert id(our_type) not in our_type.descendant_id_set, (
                f"Expected not to find the ID of our type {our_type!r}, {id(our_type)} "
                f"in its descendant_id_set, "
                f"but it was there: {our_type.descendant_id_set}"
            )

            if isinstance(our_type, ConcreteClass):
                assert our_type not in our_type.concrete_descendants, (
                    f"Expected not to find our type {our_type!r} "
                    f"in its concrete descendants, "
                    f"but it was there: {our_type.concrete_descendants}"
                )
        else:
            assert_never(our_type)


def _over_type_annotations_in_class(cls: ClassUnion) -> Iterator[TypeAnnotationUnion]:
    """
    Iterate over the type annotations defined in this class.

    Inherited properties and methods are cross-references to parent classes, so
    we exclude them in the iteration here.
    """
    for prop in cls.properties:
        if prop.specified_for is not cls:
            continue

        yield from over_type_annotation_and_nested_type_annotations(
            prop.type_annotation
        )

    for constructor_arg in cls.constructor.arguments:
        yield from over_type_annotation_and_nested_type_annotations(
            constructor_arg.type_annotation
        )

    for method in cls.methods:
        if method.specified_for is not cls:
            continue

        for arg in method.arguments:
            yield from over_type_annotation_and_nested_type_annotations(
                arg.type_annotation
            )


def _assert_all_type_annotations_are_unique_instances(
    symbol_table: SymbolTable,
) -> None:
    """
    Assert that all type annotations are independent, *i.e.*, no cross-references.

    This is important so that we can represent individual values in the nested
    data structures with the respective type annotation (*e.g.*, items of a list).
    This allows us to perform different kinds of inference on the values such as
    inference of schema constraints.
    """
    class_by_id = {id(cls): cls for cls in symbol_table.classes}

    type_anno_id_to_cls_id: MutableMapping[int, int] = dict()
    observed_set_of_type_anno_ids: Set[int] = set()

    for cls in symbol_table.classes:
        for type_anno in _over_type_annotations_in_class(cls):
            type_anno_id = id(type_anno)

            if type_anno_id in observed_set_of_type_anno_ids:
                other_cls_id = type_anno_id_to_cls_id[type_anno_id]
                other_cls = class_by_id[other_cls_id]

                if cls is not other_cls:
                    prolog = (
                        f"The type annotation {type_anno} is duplicated in "
                        f"the class {cls.name!r} and {other_cls.name!r}."
                    )
                else:
                    prolog = (
                        f"The type annotation {type_anno} is duplicated in "
                        f"the class {cls.name!r}."
                    )

                raise AssertionError(
                    f"{prolog} We expect all the type annotations to be unique "
                    f"instances. This is particularly important for inference of "
                    f"schema constraints as we stack constraints on a value and "
                    f"represent values with the respective type annotations."
                )

            type_anno_id_to_cls_id[type_anno_id] = id(cls)
            observed_set_of_type_anno_ids.add(type_anno_id)


def _verify(symbol_table: SymbolTable, ontology: _hierarchy.Ontology) -> List[Error]:
    """Perform a battery of checks on the consistency of ``symbol_table``."""
    errors = _verify_there_are_no_duplicate_names_of_our_types(
        symbol_table=symbol_table
    )

    if len(errors) > 0:
        return errors

    errors.extend(
        _verify_with_model_type_for_classes_with_at_least_one_concrete_descendant(
            symbol_table=symbol_table
        )
    )

    errors.extend(
        _verify_named_unions_are_dispatchable_in_json(symbol_table=symbol_table)
    )

    errors.extend(
        _verify_all_the_function_calls_in_the_contracts_are_valid(
            symbol_table=symbol_table
        )
    )

    errors.extend(
        _verify_optional_constructor_arguments_default_to_none(
            symbol_table=symbol_table
        )
    )

    errors_if_not_all_properties_are_initialized_in_the_constructor = (
        _verify_all_properties_are_initialized_in_the_constructor(
            symbol_table=symbol_table
        )
    )
    errors.extend(errors_if_not_all_properties_are_initialized_in_the_constructor)
    if len(errors_if_not_all_properties_are_initialized_in_the_constructor) == 0:
        errors.extend(
            _verify_constructor_arguments_and_properties_match(
                symbol_table=symbol_table
            )
        )

    errors.extend(
        _verify_all_references_to_arguments_occur_in_valid_context(
            symbol_table=symbol_table
        )
    )

    errors.extend(_verify_constraints_and_constraintrefs(symbol_table=symbol_table))

    errors.extend(_verify_description_rendering_with_smoke(symbol_table=symbol_table))

    errors.extend(_verify_only_simple_type_patterns(symbol_table=symbol_table))

    errors.extend(_verify_patterns_anchored_at_start_and_end(symbol_table=symbol_table))

    errors.extend(_verify_invariant_descriptions_unique(symbol_table=symbol_table))

    if len(errors) > 0:
        return errors

    _assert_interfaces_defined_correctly(symbol_table=symbol_table, ontology=ontology)

    _assert_all_class_inheritances_defined_an_interface(symbol_table=symbol_table)

    _assert_self_not_in_concrete_descendants(symbol_table=symbol_table)

    _assert_all_type_annotations_are_unique_instances(symbol_table=symbol_table)

    return errors


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def translate(
    parsed_symbol_table: parse.SymbolTable,
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[SymbolTable], Optional[Error]]:
    """Translate the parsed our types into intermediate our types."""
    underlying_errors = []  # type: List[Error]

    def bundle_underlying_errors() -> Error:
        """Bundle underlying errors to the main error."""
        return Error(
            atok.tree,
            "Failed to translate the parsed symbol table "
            "to an intermediate symbol table",
            underlying=underlying_errors,
        )

    # region Infer hierarchy as ontology

    ontology, ontology_errors = _hierarchy.map_symbol_table_to_ontology(
        parsed_symbol_table=parsed_symbol_table
    )
    if ontology_errors is not None:
        underlying_errors.extend(ontology_errors)

    if len(underlying_errors) > 0:
        # If the ontology could not be inferred, we can not perform any error recovery
        # as any further analysis will be invalidated.
        return None, bundle_underlying_errors()

    assert ontology is not None

    # endregion

    # region Understand constructors

    constructor_table, constructor_error = construction.understand_all(
        parsed_symbol_table=parsed_symbol_table, atok=atok
    )

    if constructor_error is not None:
        underlying_errors.append(constructor_error)

    # endregion

    if len(underlying_errors) > 0:
        # We can not proceed and recover from these errors as they concern critical
        # dependencies of the further analysis.
        return None, bundle_underlying_errors()

    # region Figure out the sub-hierarchy of the constrained primitive types

    (
        constrained_primitives_by_name,
        determination_errors,
    ) = _determine_constrained_primitives_by_name(
        parsed_symbol_table=parsed_symbol_table, ontology=ontology
    )

    if determination_errors is not None:
        underlying_errors.extend(determination_errors)

    if len(underlying_errors) > 0:
        # We can not proceed and recover from these errors as they concern critical
        # dependencies of the further analysis.
        return None, bundle_underlying_errors()

    # endregion

    # region First pass of translation

    assert constructor_table is not None
    assert constrained_primitives_by_name is not None

    # Type annotations reference placeholders for our types at this point.

    our_types = []  # type: List[OurType]
    for parsed_our_type in parsed_symbol_table.our_types:
        our_type = None  # type: Optional[OurType]

        constrainee = constrained_primitives_by_name.get(parsed_our_type.name, None)

        if constrainee is not None:
            assert isinstance(
                parsed_our_type, parse.ConcreteClass
            ), "All constrained primitive types must be concrete."

            our_type, parsing_errors = _to_constrained_primitive(
                parsed=parsed_our_type, constrainee=constrainee
            )
            if parsing_errors is not None:
                underlying_errors.append(
                    Error(
                        parsed_our_type.node,
                        f"Failed to translate "
                        f"the constrained primitive {parsed_our_type.name}",
                        parsing_errors,
                    )
                )
                continue

        elif isinstance(parsed_our_type, parse.Enumeration):
            our_type, our_type_errors = _to_enumeration(parsed=parsed_our_type)
            if our_type_errors is not None:
                underlying_errors.append(
                    Error(
                        parsed_our_type.node,
                        f"Failed to translate the enumeration {parsed_our_type.name!r}",
                        our_type_errors,
                    )
                )
                continue

        elif isinstance(parsed_our_type, (parse.AbstractClass, parse.ConcreteClass)):
            our_type, our_type_errors = _to_class(
                parsed=parsed_our_type,
                constructor_statements=constructor_table.must_find(parsed_our_type),
            )

            if our_type_errors is not None:
                underlying_errors.append(
                    Error(
                        parsed_our_type.node,
                        f"Failed to translate the class {parsed_our_type.name!r}",
                        our_type_errors,
                    )
                )
                continue

        elif isinstance(parsed_our_type, parse.NamedUnion):
            our_type, our_type_errors = _to_named_union(parsed=parsed_our_type)
            if our_type_errors is not None:
                underlying_errors.append(
                    Error(
                        parsed_our_type.node,
                        f"Failed to translate the named union "
                        f"{parsed_our_type.name!r}",
                        our_type_errors,
                    )
                )
                continue

        else:
            assert_never(parsed_our_type)

        assert our_type is not None
        our_types.append(our_type)

    meta_model, meta_model_errors = _to_meta_model(
        parsed=parsed_symbol_table.meta_model
    )
    if meta_model_errors is not None:
        underlying_errors.append(
            Error(
                None,
                "Failed to translate the meta-data of the meta-model",
                meta_model_errors,
            )
        )

    verification_functions = []  # type: List[VerificationUnion]
    for func in parsed_symbol_table.verification_functions:
        verification, verification_errors = _to_verification_function(func)

        if verification_errors is not None:
            underlying_errors.append(
                Error(
                    func.node,
                    f"Failed to translate the verification function {func.name!r}",
                    verification_errors,
                )
            )
            continue

        assert verification is not None
        verification_functions.append(verification)

    if len(underlying_errors) > 0:
        return None, bundle_underlying_errors()

    assert meta_model is not None

    # NOTE (mristin, 2022-07-06):
    # We reported as many errors as we could, and now we can be sure that the constants
    # can be translated as we have at least the mapping our type name 🠒 type class.

    our_types_by_name = {our_type.name: our_type for our_type in our_types}

    # region Check that the members of named unions are indeed classes or named unions

    # NOTE (mristin):
    # The parse stage already verifies that a named union's members resolve to
    # classes or other named unions (as opposed to enumerations or dangling names)
    # — see ``parse._verify_symbol_table``. However, a class from the parse stage
    # can still turn out to be re-classified as a constrained primitive at this
    # (intermediate) stage, which the parse stage has no way to know about. Catch
    # that case here, with a clear error, before we resolve the members for real
    # in the second pass (which assumes the members are already valid).
    for our_type in our_types:
        if not isinstance(our_type, NamedUnion):
            continue

        for member_name in our_type.parsed.members:
            member_our_type = our_types_by_name[member_name]

            if not isinstance(
                member_our_type, (AbstractClass, ConcreteClass, NamedUnion)
            ):
                underlying_errors.append(
                    Error(
                        our_type.parsed.node,
                        f"Expected the members of the named union "
                        f"{our_type.name!r} to be classes or named unions, "
                        f"but the member {member_our_type.name!r} is "
                        f"a {member_our_type.__class__.__name__!r}",
                    )
                )

    if len(underlying_errors) > 0:
        return None, bundle_underlying_errors()

    # endregion

    # region Topologically sort named unions, checking for cycles

    (
        named_unions_topologically_sorted,
        named_union_cycle_error,
    ) = _topologically_sort_named_unions_or_find_cycle(
        our_types=our_types, our_types_by_name=our_types_by_name
    )

    if named_union_cycle_error is not None:
        underlying_errors.append(named_union_cycle_error)
        return None, bundle_underlying_errors()

    assert named_unions_topologically_sorted is not None

    # endregion

    constants = []  # type: List[ConstantUnion]
    for parsed_constant in parsed_symbol_table.constants:
        constant, errors = _to_constant(
            parsed=parsed_constant, our_types_by_name=our_types_by_name, atok=atok
        )
        if errors is not None:
            underlying_errors.extend(errors)
            continue
        assert constant is not None

        constants.append(constant)

    if len(underlying_errors) > 0:
        return None, bundle_underlying_errors()

    our_types_topologically_sorted = []  # type: List[OurTypeExceptEnumeration]
    for parsed_cls in ontology.classes:
        our_type = our_types_by_name[parsed_cls.name]
        assert not isinstance(our_type, (Enumeration, NamedUnion)), (
            "``ontology.classes`` is expected to enumerate only classes, "
            "so this our type must be a class or a constrained primitive"
        )
        our_types_topologically_sorted.append(our_type)

    # NOTE (mristin):
    # Named unions are appended *after* all the classes above, in the topological
    # order over the named-union dependency graph computed earlier (see
    # ``named_unions_topologically_sorted``). A named union only ever depends on
    # classes, all of which already precede every named union in
    # ``our_types_topologically_sorted`` at this point, and on other named
    # unions, which is exactly what ``named_unions_topologically_sorted`` already
    # orders correctly. This ordering matters for code generation targets which
    # require types to be declared before they are used (*e.g.*, C++).
    our_types_topologically_sorted.extend(named_unions_topologically_sorted)

    symbol_table = SymbolTable(
        our_types=our_types,
        our_types_topologically_sorted=our_types_topologically_sorted,
        constants=constants,
        verification_functions=verification_functions,
        meta_model=meta_model,
    )

    # endregion

    # NOTE (mristin, 2021-12-14):
    # At first we in-lined all these second-pass code. However, since Python keeps
    # all the variables in the function scope, the code became quite unreadable, and
    # we were never sure which variables are re-used between the passes.
    #
    # Hence, we refactored the second passes in the separate functions. Please keep the
    # order of the functions with their call order here, and do not call them elsewhere
    # in code.

    # region Second passes which do not require the heritage to be inherited

    underlying_errors.extend(
        _second_pass_to_resolve_our_types_in_atomic_type_annotations_in_place(
            symbol_table=symbol_table
        )
    )

    underlying_errors.extend(
        _second_pass_to_resolve_references_to_our_types_in_the_descriptions_in_place(
            symbol_table=symbol_table
        )
    )

    underlying_errors.extend(
        _second_pass_to_resolve_references_to_constants_in_the_descriptions_in_place(
            symbol_table=symbol_table
        )
    )

    underlying_errors.extend(
        _second_pass_to_resolve_default_argument_values_in_place(
            symbol_table=symbol_table
        )
    )

    if len(underlying_errors) > 0:
        return None, bundle_underlying_errors()

    _second_pass_to_resolve_inheritances_in_place(symbol_table=symbol_table)

    _second_pass_to_resolve_named_union_members_in_place(symbol_table=symbol_table)

    _second_pass_to_resolve_resulting_class_of_specified_for(
        symbol_table=symbol_table,
    )

    _second_pass_to_resolve_specified_for_in_invariants(
        symbol_table=symbol_table,
    )

    _second_pass_to_resolve_ancestors_and_descendants_in_place(
        symbol_table=symbol_table, ontology=ontology
    )

    underlying_errors.extend(
        _second_pass_to_resolve_constant_subsets_in_place(symbol_table=symbol_table)
    )

    # endregion

    if len(underlying_errors) > 0:
        return None, bundle_underlying_errors()

    # region Second passes to inherit the heritage

    underlying_errors.extend(
        _second_pass_to_stack_serializations_in_place(symbol_table=symbol_table)
    )

    _second_pass_to_stack_invariants_in_place(symbol_table=symbol_table)

    underlying_errors.extend(
        _second_pass_to_stack_properties_in_place(symbol_table=symbol_table)
    )

    underlying_errors.extend(
        _second_pass_to_stack_methods_in_place(symbol_table=symbol_table)
    )

    underlying_errors.extend(
        _second_pass_to_stack_constructors_in_place(symbol_table=symbol_table)
    )

    # endregion

    if len(underlying_errors) > 0:
        return None, bundle_underlying_errors()

    # region Second passes which assume the inheritance of the heritage

    # NOTE (mristin, 2022-03-18):
    # We might reference inherited properties of our type, so we need to apply
    # this second pass only after the properties have been stacked.
    underlying_errors.extend(
        _second_pass_to_resolve_references_to_attributes_in_the_descriptions_in_place(
            symbol_table=symbol_table
        )
    )

    # NOTE (mristin, 2022-03-18):
    # We need to include all the properties and methods in the interface, so they need
    # to be inherited first.
    _second_pass_to_resolve_interfaces_in_place(
        symbol_table=symbol_table, ontology=ontology
    )

    # NOTE (mristin):
    # This needs the members' ``concrete_descendants`` to be resolved, hence it
    # runs after ``_second_pass_to_resolve_ancestors_and_descendants_in_place``.
    _second_pass_to_resolve_named_union_implementers_in_place(symbol_table=symbol_table)

    # endregion

    underlying_errors.extend(_verify(symbol_table=symbol_table, ontology=ontology))

    if len(underlying_errors) > 0:
        return None, bundle_underlying_errors()

    return symbol_table, None


def errors_if_contracts_for_functions_or_methods_defined(
    symbol_table: SymbolTable,
) -> Optional[List[Error]]:
    """
    Generate an error if one or more contracts for functions or methods defined.

    This does *not* apply to implementation-specific functions as they are going to
    be manually implemented, and we do not have to transpile them.

    We added some support for the pre-conditions, post-conditions and snapshots
    already and keep maintaining it as it is only a matter of time when we will
    introduce their transpilation. Introducing them "after the fact" would have been
    much more difficult.

    At the given moment, however, we deliberately focus only on the invariants.
    """
    errors = []  # type: List[Error]
    for signature_like in _over_signature_likes(symbol_table):
        if (
            len(signature_like.contracts.preconditions) > 0
            or len(signature_like.contracts.postconditions) > 0
            or len(signature_like.contracts.snapshots) > 0
        ):
            # NOTE (mristin, 2022-05-18):
            # We allow implementation-specific methods to have pre- and post-conditions
            # as they are used only for documentation, but are not transpiled.
            if isinstance(
                signature_like,
                (ImplementationSpecificVerification, ImplementationSpecificMethod),
            ):
                continue

            original_node = None  # type: Optional[ast.AST]

            if signature_like.parsed is not None:
                original_node = signature_like.parsed.node

            errors.append(
                Error(
                    original_node,
                    f"Pre-condition, snapshot or post-condition defined "
                    f"for {signature_like.name!r}",
                )
            )

    if len(errors) > 0:
        return errors

    return None


def errors_if_non_implementation_specific_methods(
    symbol_table: SymbolTable,
) -> Optional[List[Error]]:
    """
    Generate an error if one or more class methods are not implementation-specific.

    We added some support for understood methods already and keep maintaining it as
    it is only a matter of time when we will introduce their transpilation. Introducing
    them "after the fact" would have been much more difficult.

    At the given moment, however, we deliberately focus only on implementation-specific
    methods.
    """
    errors = []  # type: List[Error]

    for cls in symbol_table.classes:
        for method in cls.methods:
            if not isinstance(method, ImplementationSpecificMethod):
                errors.append(
                    Error(
                        method.parsed.node,
                        f"Method {method.name!r} of class {cls.name!r} is not "
                        f"implementation-specific",
                    )
                )

    if len(errors) > 0:
        return errors

    return None
