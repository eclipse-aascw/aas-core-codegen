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
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
)
from aas_core_codegen.intermediate import (
    doc as intermediate_doc,
)


class Context:
    """Structure the context of the rendering of a description."""

    #: Our package in which the description resides
    package: Final[Identifier]

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
        package: Identifier,
        cls_or_enum: Optional[Union[intermediate.ClassUnion, intermediate.Enumeration]],
    ) -> None:
        """Initialize with the given values."""
        self.package = package
        self.cls_or_enum = cls_or_enum


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
                name = golang_naming.enum_name(element.our_type.name)

            elif isinstance(
                element.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                # NOTE (mristin, 2023-03-28):
                # We always refer to interfaces even in cases of concrete classes without
                # concrete descendants since we want to allow enhancing.
                name = golang_naming.interface_name(element.our_type.name)

            else:
                assert_never(element.our_type)

            if self.context.package == golang_common.TYPES_PACKAGE:
                result = f"[{name}]"
            else:
                result = f"[{golang_common.TYPES_PACKAGE}.{name}]"

        elif isinstance(element.our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin, 2022-09-08):
            # We do not generate a class for constrained primitives, but we
            # leave it here as a literal.

            name = golang_naming.struct_name(element.our_type.name)
            result = f"`{name}`"

        elif isinstance(element.our_type, intermediate.NamedUnion):
            name = golang_naming.union_name(element.our_type.name)

            if self.context.package == golang_common.TYPES_PACKAGE:
                result = f"[{name}]"
            else:
                result = f"[{golang_common.TYPES_PACKAGE}.{name}]"

        else:
            assert_never(element.our_type)

        return result, None

    def transform_reference_to_attribute_in_doc(
        self, element: intermediate_doc.ReferenceToAttribute
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        result: str

        if isinstance(element.reference, intermediate_doc.ReferenceToProperty):
            interface_name = golang_naming.interface_name(element.reference.cls.name)
            getter_name = golang_naming.getter_name(element.reference.prop.name)

            if self.context.package == golang_common.TYPES_PACKAGE:
                result = f"[{interface_name}.{getter_name}]"
            else:
                result = (
                    f"[{golang_common.TYPES_PACKAGE}.{interface_name}.{getter_name}]"
                )

        elif isinstance(
            element.reference, intermediate_doc.ReferenceToEnumerationLiteral
        ):
            literal_name = golang_naming.enum_literal_name(
                element.reference.enumeration.name, element.reference.literal.name
            )

            if self.context.package == golang_common.TYPES_PACKAGE:
                result = f"[{literal_name}]"
            else:
                result = f"[{golang_common.TYPES_PACKAGE}.{literal_name}]"
        else:
            assert_never(element.reference)

        return result, None

    def transform_reference_to_argument_in_doc(
        self, element: intermediate_doc.ReferenceToArgument
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        arg_name = golang_naming.argument_name(Identifier(element.reference))

        return arg_name, None

    def transform_reference_to_constraint_in_doc(
        self, element: intermediate_doc.ReferenceToConstraint
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        assert isinstance(element.reference, str)

        return f"Constraint {element.reference}", None

    def transform_reference_to_constant_in_doc(
        self, element: intermediate_doc.ReferenceToConstant
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        name = golang_naming.constant_name(element.constant.name)

        if self.context.package == golang_common.CONSTANTS_PACKAGE:
            result = f"[{name}]"
        else:
            result = f"[{golang_common.CONSTANTS_PACKAGE}.{name}]"

        return result, None

    def transform_literal(
        self, element: docutils.nodes.literal
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        # NOTE (mristin, 2023-03-28):
        # We fail here catastrophically if there are backticks as there is no easy way
        # to escape them in godoc. However, since our meta-model is written in
        # Python, this assertion will almost always pass as we can not escape backtics
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

        # NOTE (mristin, 2023-03-28):
        # At this point, godoc still does not support emphasis :(.
        return content, None

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

            writer.write("  • ")

            # NOTE (mristin, 2023-03-28):
            # This has a potentially exponential complexity w.r.t. indention level.
            # However, as the indention level is thus far limited to only a single
            # level, we ignore this pitfall for the moment.
            #
            # In the future, if the indention level increases, we need to 1) change
            # the logic anyhow to allow for nested bullet lists, and 2) use data
            # structures that allow for more dynamic handling of the indention.
            writer.write(indent_but_first_line(child_text, "    "))

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
        return f"NOTE: {text}", None

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
    """
    Generate the documentation comment with the given ``text``.

    >>> documentation_comment(Stripped('hello world'))
    '// hello world'

    >>> documentation_comment(Stripped('hello\\nworld'))
    '// hello\\n// world'
    """
    commented_lines = []  # type: List[str]
    for line in text.splitlines():
        if len(line.strip()) == 0:
            commented_lines.append("//")
        else:
            commented_lines.append(f"// {line}")

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
        blocks.append(rendered_summary)

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
        blocks.append(rendered_summary)

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
            writer = io.StringIO()
            writer.write(f"Constraint {constraint_id}:\n")
            writer.write(constraint_body)
            blocks.append(writer.getvalue())

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
        blocks.append(rendered_summary)

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
                Stripped(f"`{arg_name}`: {rendered_arg_description}")
            )
        else:
            writer = io.StringIO()
            writer.write(f"`{arg_name}`:\n")
            writer.write(rendered_arg_description)
            param_and_return_blocks.append(Stripped(writer.getvalue()))

    if description.returns is not None:
        rendered_returns, returns_errors = renderer.transform(description.returns)
        if returns_errors is not None:
            errors.extend(returns_errors)
        else:
            assert rendered_returns is not None

            if "\n" not in rendered_returns and (9 + len(rendered_returns) < 60):
                param_and_return_blocks.append(f"Return {rendered_returns}")
            else:
                writer = io.StringIO()
                writer.write("Return\n")
                writer.write(rendered_returns)
                param_and_return_blocks.append(writer.getvalue())

    param_and_return_blocks = [
        indent_but_first_line(f"  • {block}", "   ")
        for block in param_and_return_blocks
    ]

    if len(param_and_return_blocks) > 0:
        blocks.append("\n".join(param_and_return_blocks))

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    text = Stripped("\n\n".join(blocks))

    return documentation_comment(text), None
