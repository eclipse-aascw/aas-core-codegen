"""Render descriptions to documentation comments."""
import io
import textwrap
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
from aas_core_codegen.python import (
    common as python_common,
    naming as python_naming,
)


class Context:
    """Structure the context of the rendering of a description."""

    #: Qualified module name of the base module for the SDK
    qualified_module_name: Final[python_common.QualifiedModuleName]

    #: Our internal module in which the description resides
    module: Final[Identifier]

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
        qualified_module_name: python_common.QualifiedModuleName,
        module: Identifier,
        cls_or_enum: Optional[Union[intermediate.ClassUnion, intermediate.Enumeration]],
    ) -> None:
        """Initialize with the given values."""
        self.qualified_module_name = qualified_module_name
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
        result: str

        name = python_naming.class_name(element.our_type.name)

        if isinstance(
            element.our_type,
            (
                intermediate.Enumeration,
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            if self.context.module == "types":
                result = f":py:class:`{name}`"
            else:
                result = f":py:class:`.types.{name}`"

        elif isinstance(element.our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # We keep this as its own branch, separate from the case above,
            # even though the code is identical at the moment. We might want
            # to support unions of primitives in the future, at which point
            # this branch would need to diverge.
            if self.context.module == "types":
                result = f":py:class:`{name}`"
            else:
                result = f":py:class:`.types.{name}`"

        elif isinstance(element.our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin, 2022-09-08):
            # We do not generate a class for constrained primitives, but we
            # leave it here as a literal.
            result = f"``{name}``"

        else:
            assert_never(element.our_type)

        return result, None

    def transform_reference_to_attribute_in_doc(
        self, element: intermediate_doc.ReferenceToAttribute
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        result: str

        if isinstance(element.reference, intermediate_doc.ReferenceToProperty):
            cls_name = python_naming.class_name(element.reference.cls.name)
            prop_name = python_naming.property_name(element.reference.prop.name)

            if self.context.module == "types":
                if self.context.cls_or_enum is element.reference.cls:
                    result = f":py:attr:`{prop_name}`"
                else:
                    result = f":py:attr:`{cls_name}.{prop_name}`"
            else:
                result = f":py:attr:`.types.{cls_name}.{prop_name}`"

        elif isinstance(
            element.reference, intermediate_doc.ReferenceToEnumerationLiteral
        ):
            cls_name = python_naming.class_name(element.reference.enumeration.name)
            literal_name = python_naming.enum_literal_name(
                element.reference.literal.name
            )

            if self.context.module == "types":
                if self.context.cls_or_enum is element.reference.enumeration:
                    result = f":py:attr:`{literal_name}`"
                else:
                    result = f":py:attr:`{cls_name}.{literal_name}`"
            else:
                result = f":py:attr:`.types.{cls_name}.{literal_name}`"
        else:
            assert_never(element.reference)

        return result, None

    def transform_reference_to_argument_in_doc(
        self, element: intermediate_doc.ReferenceToArgument
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        # NOTE (mristin, 2022-09-08):
        # We rely here on sphinx-paramlinks extension.

        arg_name = python_naming.argument_name(Identifier(element.reference))

        return f":paramref:`{arg_name}`", None

    def transform_reference_to_constraint_in_doc(
        self, element: intermediate_doc.ReferenceToConstraint
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        assert isinstance(element.reference, str)

        return (
            f":ref:`Constraint {element.reference} <constraint_{element.reference}>`",
            None,
        )

    def transform_reference_to_constant_in_doc(
        self, element: intermediate_doc.ReferenceToConstant
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        name = python_naming.constant_name(element.constant.name)

        if self.context.module == "constants":
            result = f":py:attr:`{name}`"
        else:
            result = f":py:attr:`.constants.{name}`"

        return result, None

    def transform_literal(
        self, element: docutils.nodes.literal
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        # NOTE (mristin, 2022-09-08):
        # We fail here catastrophically if there are backticks as there is no easy way
        # to escape them in RST. However, since our meta-model is also written in
        # Python, this assertion will almost always pass.
        #
        # See: https://stackoverflow.com/questions/66435475/how-to-escape-the-backtick-character-in-a-rst-file
        text = element.astext()
        assert "`" not in text
        return f"``{text}``", None

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

            # NOTE (mristin, 2022-09-14):
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
        writer.write(".. note::\n\n")

        (
            text,
            errors,
        ) = self._render_children_concatenated_with_paragraph_breaks_where_necessary(
            element.children
        )
        if errors is not None:
            return None, errors

        assert text is not None
        writer.write(textwrap.indent(text, "    "))
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


def generate_summary_remarks(
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

    return Stripped("\n\n".join(blocks)), None


def generate_summary_remarks_constraints(
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
            writer.write(f":constraint {constraint_id}:\n")
            writer.write(f"    .. _constraint_{constraint_id}:\n\n")
            writer.write(textwrap.indent(constraint_body, "    "))
            blocks.append(writer.getvalue())

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    return Stripped("\n\n".join(blocks)), None


def docstring(text: Stripped) -> Stripped:
    """Generate a docstring out of the text."""
    escaped = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if 3 + len(escaped) + 3 < 70:
        return Stripped(f'"""{escaped}"""')

    return Stripped(f'"""\n{escaped}\n"""')


def documentation_comment(text: Stripped) -> Stripped:
    """Generate the documentation comment with the given ``text``."""
    commented_lines = []  # type: List[str]
    for line in text.splitlines():
        if len(line.strip()) == 0:
            commented_lines.append("#:")
        else:
            commented_lines.append(f"#: {line}")

    return Stripped("\n".join(commented_lines))


def generate_docstring_for_signature(
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

    param_and_return_blocks = []  # type: List[Stripped]
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
                Stripped(f":param {arg_name}: {rendered_arg_description}")
            )
        else:
            writer = io.StringIO()
            writer.write(f":param {arg_name}:\n")
            writer.write(textwrap.indent(rendered_arg_description, "    "))
            param_and_return_blocks.append(Stripped(writer.getvalue()))

    if description.returns is not None:
        rendered_returns, returns_errors = renderer.transform(description.returns)
        if returns_errors is not None:
            errors.extend(returns_errors)
        else:
            assert rendered_returns is not None

            if "\n" not in rendered_returns and (9 + len(rendered_returns) < 60):
                param_and_return_blocks.append(Stripped(f":return: {rendered_returns}"))
            else:
                writer = io.StringIO()
                writer.write(":return:\n")
                writer.write(textwrap.indent(rendered_returns, "    "))
                param_and_return_blocks.append(Stripped(writer.getvalue()))

    if len(param_and_return_blocks) > 0:
        blocks.append("\n".join(param_and_return_blocks))

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    text = Stripped("\n\n".join(blocks))

    return docstring(text), None
