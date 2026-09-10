"""Render descriptions to documentation comments."""
import io
from typing import (
    Tuple,
    Optional,
    List,
    Sequence,
    Final,
    Union,
)

import docutils.nodes
import docutils.utils

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    Error,
    assert_never,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.cpp import (
    common as cpp_common,
    naming as cpp_naming,
)
from aas_core_codegen.intermediate import (
    doc as intermediate_doc,
)


class Context:
    """Structure the context of the rendering of a description."""

    #: Our namespace in which the description resides
    namespace: Final[Identifier]

    #: Scope in which the description resides.
    #:
    #: This narrows down the outer scope of the description, while the description
    #: does not necessarily describe a class, but can also describe a method,
    #: a property, an enumeration literal *etc.*
    #:
    cls_or_enum: Final[
        Optional[Union[intermediate.ClassUnion, intermediate.Enumeration]]
    ]

    def __init__(
        self,
        namespace: Identifier,
        cls_or_enum: Optional[Union[intermediate.ClassUnion, intermediate.Enumeration]],
    ) -> None:
        """Initialize with the given values."""
        self.namespace = namespace
        self.cls_or_enum = cls_or_enum


class _IsSingleParagrapher(intermediate_doc.DocutilsElementTransformer[bool]):
    def transform_text(
        self, element: docutils.nodes.Text
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return True, None

    def transform_reference_to_our_type_in_doc(
        self, element: intermediate_doc.ReferenceToOurType
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return True, None

    def transform_reference_to_attribute_in_doc(
        self, element: intermediate_doc.ReferenceToAttribute
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return True, None

    def transform_reference_to_argument_in_doc(
        self, element: intermediate_doc.ReferenceToArgument
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return True, None

    def transform_reference_to_constraint_in_doc(
        self, element: intermediate_doc.ReferenceToConstraint
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return True, None

    def transform_reference_to_constant_in_doc(
        self, element: intermediate_doc.ReferenceToConstant
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return True, None

    def transform_literal(
        self, element: docutils.nodes.literal
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return True, None

    def _children_are_not_paragraph_blocks(
        self, children: Sequence[docutils.nodes.Element]
    ) -> bool:
        for child in children:
            # NOTE (mristin):
            # We have to handle ``docutils.nodes.paragraph`` differently,
            # outside ``transform``, as a single paragraph with non-block children
            # is still OK.
            if isinstance(child, docutils.nodes.paragraph):
                return False

            if not self.transform(child):
                return False

        return True

    def transform_paragraph(
        self, element: docutils.nodes.paragraph
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return self._children_are_not_paragraph_blocks(element.children), None

    def transform_emphasis(
        self, element: docutils.nodes.emphasis
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return self._children_are_not_paragraph_blocks(element.children), None

    def transform_list_item(
        self, element: docutils.nodes.list_item
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return self._children_are_not_paragraph_blocks(element.children), None

    def transform_bullet_list(
        self, element: docutils.nodes.bullet_list
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return False, None

    def transform_note(
        self, element: docutils.nodes.note
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return False, None

    def transform_reference(
        self, element: docutils.nodes.reference
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return True, None

    def transform_field_body(
        self, element: docutils.nodes.field_body
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return self._children_are_not_paragraph_blocks(element.children), None

    def transform_document(
        self, element: docutils.nodes.document
    ) -> Tuple[Optional[bool], Optional[List[str]]]:
        return False, None


_IS_SINGLE_PARAGRAPHER = _IsSingleParagrapher()


def _is_single_paragraph(para: docutils.nodes.paragraph) -> bool:
    """
    Check whether the given paragraph ``para`` will be rendered as a single block.

    This is relevant in doxygen as we have to decide whether we need a ``\\parblock``
    or not.
    """
    result, error = _IS_SINGLE_PARAGRAPHER.transform(para)

    assert error is None, f"Unexpected error: {error}"
    assert result is not None

    return result


class _ElementRenderer(intermediate_doc.DocutilsElementTransformer[str]):
    """Render descriptions as a content of a docstring."""

    def __init__(self, context: Context) -> None:
        """Initialize with the given values."""
        self.context = context

    def transform_text(
        self, element: docutils.nodes.Text
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        return element.astext(), None

    def transform_reference_to_our_type_in_doc(
        self, element: intermediate_doc.ReferenceToOurType
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        result: str

        if isinstance(
            element.our_type,
            (
                intermediate.Enumeration,
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            name: str

            if isinstance(element.our_type, intermediate.Enumeration):
                name = cpp_naming.enum_name(element.our_type.name)

            elif isinstance(
                element.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                # NOTE (mristin):
                # We always refer to interfaces even in cases of concrete classes without
                # concrete descendants since we want to allow enhancing.
                name = cpp_naming.interface_name(element.our_type.name)

            else:
                assert_never(element.our_type)

            if self.context.namespace == cpp_common.TYPES_NAMESPACE:
                result = f"{name}"
            else:
                result = f"{cpp_common.TYPES_NAMESPACE}::{name}"

        elif isinstance(element.our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is declared as a real ``using`` alias in
            # types.hpp (see ``_generate_types.py``), so, unlike a
            # constrained primitive, it has an actual symbol to refer to.
            union_name = cpp_naming.union_name(element.our_type.name)

            if self.context.namespace == cpp_common.TYPES_NAMESPACE:
                result = f"{union_name}"
            else:
                result = f"{cpp_common.TYPES_NAMESPACE}::{union_name}"

        elif isinstance(element.our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin):
            # We do not generate a class for constrained primitives, but we
            # leave it here as a literal.

            name = cpp_naming.class_name(element.our_type.name)
            result = f"`{name}`"

        else:
            assert_never(element.our_type)

        return result, None

    def transform_reference_to_attribute_in_doc(
        self, element: intermediate_doc.ReferenceToAttribute
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        result: str

        if isinstance(element.reference, intermediate_doc.ReferenceToProperty):
            interface_name = cpp_naming.interface_name(element.reference.cls.name)
            getter_name = cpp_naming.getter_name(element.reference.prop.name)

            if self.context.namespace == cpp_common.TYPES_NAMESPACE:
                result = f"{interface_name}::{getter_name}"
            else:
                result = (
                    f"{cpp_common.TYPES_NAMESPACE}::{interface_name}::{getter_name}"
                )

        elif isinstance(
            element.reference, intermediate_doc.ReferenceToEnumerationLiteral
        ):
            enum_name = cpp_naming.enum_name(element.reference.enumeration.name)
            literal_name = cpp_naming.enum_literal_name(element.reference.literal.name)

            if self.context.namespace == cpp_common.TYPES_NAMESPACE:
                result = f"{enum_name}::{literal_name}"
            else:
                result = f"{cpp_common.TYPES_NAMESPACE}::{enum_name}::{literal_name}"
        else:
            assert_never(element.reference)

        return result, None

    def transform_reference_to_argument_in_doc(
        self, element: intermediate_doc.ReferenceToArgument
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        arg_name = cpp_naming.argument_name(Identifier(element.reference))

        return f"\\p {arg_name}", None

    def transform_reference_to_constraint_in_doc(
        self, element: intermediate_doc.ReferenceToConstraint
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        assert isinstance(element.reference, str)

        return f"Constraint {element.reference}", None

    def transform_reference_to_constant_in_doc(
        self, element: intermediate_doc.ReferenceToConstant
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        name = cpp_naming.constant_name(element.constant.name)

        if self.context.namespace == cpp_common.CONSTANTS_NAMESPACE:
            result = f"{name}"
        else:
            result = f"{cpp_common.CONSTANTS_NAMESPACE}::{name}"

        return result, None

    def transform_literal(
        self, element: docutils.nodes.literal
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        # NOTE (mristin):
        # We fail here catastrophically if there are backticks as there is no easy way
        # to escape them in doxygen. However, since our meta-model is written in
        # Python, this assertion will almost always pass as we can not escape backticks
        # in Python docstrings either.
        text = element.astext()
        assert "`" not in text
        return f"`{text}`", None

    def _render_children_concatenated_with_paragraph_breaks_where_necessary(
        self, children: Sequence[docutils.nodes.Element]
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        """Render the children and join them by empty lines, where appropriate."""
        writer = io.StringIO()
        previous_child = None  # type: Optional[docutils.nodes.Element]

        errors = []  # type: List[str]

        for child in children:
            text, child_errors = self.transform(child)
            if child_errors is not None:
                errors.extend(child_errors)
                continue
            else:
                assert text is not None
                if isinstance(
                    previous_child,
                    (
                        docutils.nodes.paragraph,
                        docutils.nodes.bullet_list,
                        docutils.nodes.note,
                    ),
                ):
                    writer.write("\n\n")

                writer.write(text)

            previous_child = child

        if len(errors) > 0:
            return None, errors

        return writer.getvalue(), None

    def transform_paragraph(
        self, element: docutils.nodes.paragraph
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        return self._render_children_concatenated_with_paragraph_breaks_where_necessary(
            element.children
        )

    def transform_emphasis(
        self, element: docutils.nodes.emphasis
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        children = []  # type: List[str]
        errors = []  # type: List[str]
        for child in element.children:
            rendered_child, child_errors = self.transform(child)
            if child_errors is not None:
                errors.extend(child_errors)
            else:
                assert rendered_child is not None
                children.append(rendered_child)

        if len(errors) > 0:
            return None, errors

        content = "".join(children)

        return Stripped(f"*{content}*"), None

    def transform_list_item(
        self, element: docutils.nodes.list_item
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        return self._render_children_concatenated_with_paragraph_breaks_where_necessary(
            element.children
        )

    def transform_bullet_list(
        self, element: docutils.nodes.bullet_list
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        errors = []  # type: List[str]
        writer = io.StringIO()

        for i, child in enumerate(element.children):
            assert isinstance(child, docutils.nodes.list_item), (
                f"Expected a list item in the bullet list, "
                f"but got an instance of {type(child)}: {child}"
            )

            child_text, child_errors = self.transform(child)
            if child_errors is not None:
                errors.extend(child_errors)
                continue

            assert child_text is not None
            if i > 0:
                writer.write("\n")

            writer.write("* ")

            # NOTE (mristin):
            # This has a potentially exponential complexity w.r.t. indention level.
            # However, as the indention level is thus far limited to only a single
            # level, we ignore this pitfall for the moment.
            #
            # In the future, if the indention level increases, we need to 1) change
            # the logic anyhow to allow for nested bullet lists, and 2) use data
            # structures that allow for more dynamic handling of the indention.
            writer.write(indent_but_first_line(child_text, "  "))

        if len(errors) > 0:
            return None, errors

        return writer.getvalue(), None

    def transform_note(
        self, element: docutils.nodes.note
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        (
            text,
            errors,
        ) = self._render_children_concatenated_with_paragraph_breaks_where_necessary(
            element.children
        )
        if errors is not None:
            return None, errors

        assert text is not None

        if (
            len(element.children) == 1
            and isinstance(element.children[0], docutils.nodes.paragraph)
            and _is_single_paragraph(element.children[0])
        ):
            return Stripped(f"\\note {text}"), None

        return (
            Stripped(
                f"""\
\\note \\parblock
{text}
\\endparblock"""
            ),
            None,
        )

    def transform_reference(
        self, element: docutils.nodes.reference
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        return element.astext(), None

    def transform_field_body(
        self, element: docutils.nodes.field_body
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        return self._render_children_concatenated_with_paragraph_breaks_where_necessary(
            element.children
        )

    def transform_document(
        self, element: docutils.nodes.document
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        return self._render_children_concatenated_with_paragraph_breaks_where_necessary(
            element.children
        )


def documentation_comment(text: Stripped) -> Stripped:
    """Generate the documentation comment with the given ``text``."""
    commented_lines = []  # type: List[str]
    for line in text.splitlines():
        if len(line.strip()) == 0:
            commented_lines.append("///")
        else:
            commented_lines.append(f"/// {line}")

    return Stripped("\n".join(commented_lines))


def generate_comment_for_summary_remarks(
    description: intermediate.SummaryRemarksDescription, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for a summary-remarks."""
    errors = []  # type: List[str]

    blocks = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    rendered_summary, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert rendered_summary is not None
        if _is_single_paragraph(description.summary):
            blocks.append(f"\\brief {rendered_summary}")
        else:
            blocks.append(
                f"""\
\\brief \\parblock
{rendered_summary}
\\endparblock"""
            )

    for remark in description.remarks:
        rendered_remark, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert rendered_remark is not None
            blocks.append(rendered_remark)

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    return documentation_comment(Stripped("\n\n".join(blocks))), None


def generate_comment_for_summary_remarks_constraints(
    description: intermediate.SummaryRemarksConstraintsDescription, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for a summary-remarks-constraints."""
    errors = []  # type: List[str]

    blocks = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    rendered_summary, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert rendered_summary is not None
        if _is_single_paragraph(description.summary):
            blocks.append(f"\\brief {rendered_summary}")
        else:
            blocks.append(
                f"""\
\\brief \\parblock
{rendered_summary}
\\endparblock"""
            )

    for remark in description.remarks:
        rendered_remark, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert rendered_remark is not None
            blocks.append(rendered_remark)

    for constraint_id, constraint in description.constraints_by_identifier.items():
        constraint_body, constraint_errors = renderer.transform(constraint)
        if constraint_errors is not None:
            errors.extend(constraint_errors)
        else:
            assert constraint_body is not None

            blocks.append(
                f"""\
Constraint {constraint_id}:\\n
{constraint_body}"""
            )

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    return documentation_comment(Stripped("\n\n".join(blocks))), None


def generate_comment_for_signature(
    description: intermediate.DescriptionOfSignature, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """
    Generate the docstring for the given signature.

    A signature, in this context, means a function or a method signature.
    """
    errors = []  # type: List[str]

    blocks = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    rendered_summary, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert rendered_summary is not None
        if _is_single_paragraph(description.summary):
            blocks.append(f"\\brief {rendered_summary}")
        else:
            blocks.append(
                f"""\
\\brief \\parblock
{rendered_summary}
\\endparblock"""
            )

    for remark in description.remarks:
        rendered_remark, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert rendered_remark is not None
            blocks.append(rendered_remark)

    param_and_return_blocks = []  # type: List[str]
    for arg_name, arg_description in description.arguments_by_name.items():
        rendered_arg_description, arg_errors = renderer.transform(arg_description)
        if arg_errors is not None:
            errors.extend(arg_errors)
            continue

        assert rendered_arg_description is not None

        if "\n" not in rendered_arg_description and (
            7 + len(arg_name) + 1 + len(rendered_arg_description) < 60
        ):
            param_and_return_blocks.append(
                Stripped(f"\\param {arg_name} {rendered_arg_description}")
            )
        else:
            param_and_return_blocks.append(
                Stripped(
                    f"""\
\\param {arg_name} \\parblock
{rendered_arg_description}
\\endparblock"""
                )
            )

    if description.returns is not None:
        rendered_returns, returns_errors = renderer.transform(description.returns)
        if returns_errors is not None:
            errors.extend(returns_errors)
        else:
            assert rendered_returns is not None

            if "\n" not in rendered_returns and (9 + len(rendered_returns) < 60):
                param_and_return_blocks.append(f"\\return {rendered_returns}")
            else:
                param_and_return_blocks.append(
                    Stripped(
                        f"""\
\\return \\parblock
{rendered_returns}
\\endparblock"""
                    )
                )

    if len(param_and_return_blocks) > 0:
        blocks.append("\n".join(param_and_return_blocks))

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    text = Stripped("\n\n".join(blocks))

    return documentation_comment(text), None
