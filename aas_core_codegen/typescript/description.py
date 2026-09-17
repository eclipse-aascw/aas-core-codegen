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
from aas_core_codegen.intermediate import (
    doc as intermediate_doc,
)
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)


class Context:
    """Structure the context of the rendering of a description."""

    #: Our internal module in which the description resides
    module: Final[Identifier]

    #: Scope in which the description resides.
    #:
    #: This narrows down the outer scope of the description, while the description
    #: does not necessarily describe a class, but can also describe a method,
    #: a property, an enumeration literal *etc.*
    cls_or_enum: Final[
        Optional[Union[intermediate.ClassUnion, intermediate.Enumeration]]
    ]

    def __init__(
        self,
        module: Identifier,
        cls_or_enum: Optional[Union[intermediate.ClassUnion, intermediate.Enumeration]],
    ) -> None:
        """Initialize with the given values."""
        self.module = module
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
        if isinstance(element.our_type, intermediate.ConstrainedPrimitive):
            return f"`{typescript_naming.class_name(element.our_type.name)}`", None

        # NOTE (mristin):
        # We refer to interfaces everywhere where we assume abstract or concrete
        # classes with descendants.
        if (
            isinstance(
                element.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            )
            and element.our_type.interface is not None
        ):
            name = typescript_naming.interface_name(element.our_type.name)
        else:
            name = typescript_naming.name_of(element.our_type)

        if self.context.module == typescript_common.TYPES_MODULE:
            return f"{{@link {name}}}", None
        else:
            return f"{{@link {typescript_common.TYPES_MODULE}!{name}}}", None

    def transform_reference_to_attribute_in_doc(
        self, element: intermediate_doc.ReferenceToAttribute
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        if isinstance(element.reference, intermediate_doc.ReferenceToProperty):
            # NOTE (mristin):
            # We refer to interfaces everywhere where we assume abstract or concrete
            # classes with descendants.
            if (
                isinstance(
                    element.reference.cls,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                )
                and element.reference.cls.interface is not None
            ):
                cls_name = typescript_naming.interface_name(element.reference.cls.name)
            else:
                cls_name = typescript_naming.class_name(element.reference.cls.name)

            prop_name = typescript_naming.property_name(element.reference.prop.name)

            if self.context.module == typescript_common.TYPES_MODULE:
                if self.context.cls_or_enum is element.reference.cls:
                    return f"{{@link {prop_name}}}", None
                else:
                    return f"{{@link {cls_name}.{prop_name}}}", None
            else:
                return (
                    f"{{@link {typescript_common.TYPES_MODULE}!"
                    f"{cls_name}.{prop_name}}}",
                    None,
                )

        elif isinstance(
            element.reference, intermediate_doc.ReferenceToEnumerationLiteral
        ):
            enum_name = typescript_naming.enum_name(element.reference.enumeration.name)
            literal_name = typescript_naming.enum_literal_name(
                element.reference.literal.name
            )

            if self.context.module == typescript_common.TYPES_MODULE:
                if self.context.cls_or_enum is element.reference.enumeration:
                    return f"{{@link {literal_name}}}", None
                else:
                    return f"{{@link {enum_name}.{literal_name}}}", None
            else:
                return (
                    f"{{@link {typescript_common.TYPES_MODULE}!"
                    f"{enum_name}.{literal_name}}}",
                    None,
                )
        else:
            assert_never(element.reference)

    def transform_reference_to_argument_in_doc(
        self, element: intermediate_doc.ReferenceToArgument
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        arg_name = typescript_naming.argument_name(Identifier(element.reference))
        return f"`{arg_name}`", None

    def transform_reference_to_constraint_in_doc(
        self, element: intermediate_doc.ReferenceToConstraint
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        assert isinstance(element.reference, str)

        return f"Constraint {element.reference}", None

    def transform_reference_to_constant_in_doc(
        self, element: intermediate_doc.ReferenceToConstant
    ) -> Tuple[Optional[str], Optional[List[str]]]:

        name = typescript_naming.constant_name(element.constant.name)

        if self.context.module == typescript_common.CONSTANTS_MODULE:
            result = f"{{@link {name}}}"
        else:
            result = f"{{@link {typescript_common.CONSTANTS_MODULE}!{name}}}"

        return result, None

    def transform_literal(
        self, element: docutils.nodes.literal
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        # NOTE (mristin):
        # Theoretically, we could escape the backticks properly here, see
        # https://meta.stackexchange.com/questions/82718/how-do-i-escape-a-backtick-within-in-line-code-in-markdown.
        # However, this is not necessary since our meta-model is written in
        # Python, and escaping backticks in ReST is not well-defined. For now, we simply
        # assume no backticks.
        #
        # See: https://stackoverflow.com/questions/66435475/how-to-escape-the-backtick-character-in-a-rst-file
        text = element.astext()
        assert "`" not in text, (
            "(mristin, 2022-09-08): Theoretically, we could escape the backticks "
            "properly here, see [how to escape backticks in markdown].\n\n"
            "However, this is not necessary as our meta-model is written in Python, "
            "and escaping backticks in ReST is not well-defined, see [how to escape "
            "backticks in ReST]. At this moment, we simply assume no backticks in the "
            "code literals.\n\n"
            "[how to escape backticks in markdown]: https://meta.stackexchange.com/"
            "questions/82718/how-do-i-escape-a-backtick-within-in-line-"
            "code-in-markdown\n"
            "[how to escape backticks in ReST]: https://stackoverflow.com/questions/"
            "66435475/how-to-escape-the-backtick-character-in-a-rst-file"
        )
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
        return f"*{content}*", None

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
        writer = io.StringIO()
        writer.write("**Note**:\n")

        (
            text,
            errors,
        ) = self._render_children_concatenated_with_paragraph_breaks_where_necessary(
            element.children
        )
        if errors is not None:
            return None, errors

        assert text is not None
        writer.write(text)
        return writer.getvalue(), None

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
    """Generate a documentation comment out of the text."""
    lines = text.splitlines()
    writer = io.StringIO()
    writer.write("/**\n")
    for line in lines:
        if len(line.strip()) > 0:
            writer.write(f" * {line}\n")
        else:
            writer.write(" *\n")

    writer.write(" */")

    return Stripped(writer.getvalue())


def generate_documentation_comment_for_summary_remarks(
    description: intermediate.SummaryRemarksDescription, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for a summary-remarks."""
    errors = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    rendered_summary, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert rendered_summary is not None

    remark_blocks = []  # type: List[str]
    for remark in description.remarks:
        rendered_remark, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert rendered_remark is not None
            remark_blocks.append(rendered_remark)

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    assert rendered_summary is not None

    blocks = [rendered_summary]
    if len(remark_blocks) > 0:
        blocks.append("@remarks")
        blocks.extend(remark_blocks)

    return documentation_comment(Stripped("\n\n".join(blocks))), None


def generate_documentation_comment_for_summary_remarks_constraints(
    description: intermediate.SummaryRemarksConstraintsDescription, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for a summary-remarks-constraints."""
    errors = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    rendered_summary, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert rendered_summary is not None

    remark_blocks = []  # type: List[str]
    for remark in description.remarks:
        rendered_remark, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert rendered_remark is not None
            remark_blocks.append(rendered_remark)

    constraint_blocks = []  # type: List[str]
    for constraint_id, constraint in description.constraints_by_identifier.items():
        constraint_body, constraint_errors = renderer.transform(constraint)
        if constraint_errors is not None:
            errors.extend(constraint_errors)
        else:
            assert constraint_body is not None
            constraint_blocks.append(
                f"""\
Constraint `{constraint_id}`:
{constraint_body}"""
            )

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    assert rendered_summary is not None

    blocks = [rendered_summary]
    if len(remark_blocks) > 0:
        remark_blocks[0] = f"@remarks\n{remark_blocks[0]}"
        blocks.extend(remark_blocks)

    blocks.extend(constraint_blocks)

    return documentation_comment(Stripped("\n\n".join(blocks))), None


def generate_documentation_comment_for_signature(
    description: intermediate.DescriptionOfSignature, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """
    Generate the docstring for the given signature.

    A signature, in this context, means a function or a method signature.
    """
    errors = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    rendered_summary, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert rendered_summary is not None

    remark_blocks = []  # type: List[str]
    for remark in description.remarks:
        rendered_remark, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert rendered_remark is not None
            remark_blocks.append(rendered_remark)

    param_and_return_blocks = []  # type: List[Stripped]
    for arg_name, arg_description in description.arguments_by_name.items():
        rendered_arg_description, arg_errors = renderer.transform(arg_description)
        if arg_errors is not None:
            errors.extend(arg_errors)
            continue

        assert rendered_arg_description is not None

        if "\n" not in rendered_arg_description and (
            7 + len(arg_name) + 3 + len(rendered_arg_description) < 60
        ):
            param_and_return_blocks.append(
                Stripped(f"@param {arg_name} - {rendered_arg_description}")
            )
        else:
            writer = io.StringIO()
            writer.write(f"@param {arg_name} -\n")
            writer.write(rendered_arg_description)
            param_and_return_blocks.append(Stripped(writer.getvalue()))

    if description.returns is not None:
        rendered_returns, returns_errors = renderer.transform(description.returns)
        if returns_errors is not None:
            errors.extend(returns_errors)
        else:
            assert rendered_returns is not None

            if "\n" not in rendered_returns and (9 + len(rendered_returns) < 60):
                param_and_return_blocks.append(Stripped(f"@returns {rendered_returns}"))
            else:
                writer = io.StringIO()
                writer.write("@returns\n")
                writer.write(rendered_returns)
                param_and_return_blocks.append(Stripped(writer.getvalue()))

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    assert rendered_summary is not None

    blocks = [rendered_summary]
    if len(remark_blocks) > 0:
        blocks.append("@remarks")
        blocks.extend(remark_blocks)

    blocks.extend(param_and_return_blocks)

    return documentation_comment(Stripped("\n\n".join(blocks))), None
