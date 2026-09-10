"""Render descriptions to Java documentation comments."""
import dataclasses
import html
import io
import textwrap
import urllib.parse
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
from icontract import require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    Error,
    assert_never,
    Identifier,
)
from aas_core_codegen.intermediate import (
    doc as intermediate_doc,
)
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)


class Context:
    """Structure the context of the rendering of a description."""

    #: Fully qualified dot-path to the base package
    root_package: Final[java_common.PackageIdentifier]

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
        package: java_common.PackageIdentifier,
        cls_or_enum: Optional[Union[intermediate.ClassUnion, intermediate.Enumeration]],
    ) -> None:
        """Initialize with the given values."""
        self.root_package = package
        self.cls_or_enum = cls_or_enum


# NOTE (mristin, 2024-03-28):
# The Javadoc markup is a bit peculiar. In many cases, it requires only the opening
# tag, and tolerates (or even encourages) omission of the closing tag. Consequently,
# this allows us to model the text flow operations as a list of tokens (instead, say,
# a more complex document tree).
#
# At this point, we only care about the text flow (*i.e.*, line breaks, bullets,
# and beginnings of the paragraphs). To keep it all simple, we ignore all the other
# Javadoc tags which do not affect the text flow, and capture them in plain text.

# NOTE (mristin, 2024-03-28):
# We make all token classes as data classes so that the comparisons and
# string representations are automatically generated.


@dataclasses.dataclass
class _TokenText:
    """Model rendered description text, except any text flow operation."""

    content: str


@dataclasses.dataclass
class _TokenULOpen:
    """Capture a beginning of an unordered list."""


@dataclasses.dataclass
class _TokenULClose:
    """Capture the end an unordered list."""


@dataclasses.dataclass
class _TokenLI:
    """Capture a beginning of a list item."""


@dataclasses.dataclass
class _TokenP:
    """Capture a beginning of a paragraph."""


_Token = Union[_TokenText, _TokenULOpen, _TokenULClose, _TokenLI, _TokenP]


class _ElementRenderer(intermediate_doc.DocutilsElementTransformer[List[_Token]]):
    """Render descriptions as a content of a docstring."""

    def __init__(self, context: Context) -> None:
        """Initialize with the given values."""
        self.context = context

    def transform_text(
        self, element: docutils.nodes.Text
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        return [
            _TokenText(
                element.astext()
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
        ], None

    def transform_reference_to_our_type_in_doc(
        self, element: intermediate_doc.ReferenceToOurType
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        reference: Stripped

        if isinstance(element.our_type, intermediate.Enumeration):
            name = java_naming.enum_name(element.our_type.name)
            reference = Stripped(
                f"{{@link {self.context.root_package}.types.enums.{name}}}"
            )
        elif isinstance(element.our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin, 2024-03-27):
            # We do not generate a class for constrained primitives, but we
            # leave it as class name, as that is what we used for ``verify*`` functions.
            name = java_naming.class_name(element.our_type.name)
            reference = Stripped(f"@{{code {name}}}")
        elif isinstance(element.our_type, intermediate.AbstractClass):
            # NOTE (empwilli):
            # We do not generate Java code for abstract classes, so we have to refer
            # to the interface.
            name = java_naming.interface_name(element.our_type.name)
            reference = Stripped(
                f"{{@link {self.context.root_package}.types.model.{name}}}"
            )
        elif isinstance(element.our_type, intermediate.ConcreteClass):
            # NOTE (empwilli):
            # Though a concrete class can have multiple descendants and the writer
            # might actually want to refer to the *interface* instead of
            # the concrete class, we do the best effort here and resolve it to the
            # name of the concrete class.
            name = java_naming.class_name(element.our_type.name)
            reference = Stripped(
                f"{{@link {self.context.root_package}.types.impl.{name}}}"
            )
        elif isinstance(element.our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is represented as a plain class, so we refer to
            # it by its union name, exactly as we do for a constrained
            # primitive.
            name = java_naming.union_name(element.our_type.name)
            reference = Stripped(
                f"{{@link {self.context.root_package}.types.model.{name}}}"
            )
        else:
            assert_never(element.our_type)

        return [_TokenText(reference)], None

    def transform_reference_to_attribute_in_doc(
        self, element: intermediate_doc.ReferenceToAttribute
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        if isinstance(element.reference, intermediate_doc.ReferenceToProperty):
            getter_name = java_naming.getter_name(element.reference.prop.name)

            if element.reference.cls is self.context.cls_or_enum:
                return [_TokenText(f"{{@link #{getter_name}()}}")], None

            base: Stripped
            if isinstance(element.reference.cls, intermediate.AbstractClass):
                # NOTE (empwilli):
                # We do not generate Java code for abstract classes, so we have to refer
                # to the interface.
                interface_name = java_naming.interface_name(element.reference.cls.name)
                base = Stripped(f"types.model.{interface_name}")
            elif isinstance(element.reference.cls, intermediate.ConcreteClass):
                # NOTE (empwilli):
                # Though a concrete class can have multiple descendants and the writer
                # might actually want to refer to the *interface* instead of
                # the concrete class, we do the best effort here and resolve it to the
                # name of the concrete class.
                cls_name = java_naming.class_name(element.reference.cls.name)
                base = Stripped(f"types.impl.{cls_name}")
            else:
                assert_never(element.reference.cls)

            return [
                _TokenText(
                    f"{{@link {self.context.root_package}.{base}#{getter_name}()}}"
                )
            ], None

        elif isinstance(
            element.reference, intermediate_doc.ReferenceToEnumerationLiteral
        ):
            literal_name = java_naming.enum_literal_name(element.reference.literal.name)

            if element.reference.enumeration is self.context.cls_or_enum:
                return [_TokenText(f"{{@link #{literal_name}}}")], None

            enum_name = java_naming.enum_name(element.reference.enumeration.name)

            return [
                _TokenText(
                    f"{{@link {self.context.root_package}.types.enums"
                    f".{enum_name}#{literal_name}}}"
                )
            ], None
        else:
            assert_never(element.reference)

    def transform_reference_to_argument_in_doc(
        self, element: intermediate_doc.ReferenceToArgument
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        arg_name = java_naming.argument_name(Identifier(element.reference))
        return [_TokenText(f"{{@code {arg_name}}}")], None

    def transform_reference_to_constraint_in_doc(
        self, element: intermediate_doc.ReferenceToConstraint
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        assert isinstance(element.reference, str)

        return [_TokenText(f"Constraint {element.reference}")], None

    def transform_reference_to_constant_in_doc(
        self, element: intermediate_doc.ReferenceToConstant
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        name = java_naming.property_name(element.constant.name)

        return [
            _TokenText(
                f"{{@link {self.context.root_package}.constants.Constants#{name}}}"
            )
        ], None

    def transform_literal(
        self, element: docutils.nodes.literal
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        # NOTE (mristin, 2024-03-27):
        # Theoretically, we could escape the backticks properly here, see
        # https://meta.stackexchange.com/questions/82718/how-do-i-escape-a-backtick-within-in-line-code-in-markdown.
        # However, this is not necessary since our meta-model is written in
        # Python, and escaping backticks in ReST is not well-defined. For now, we simply
        # assume no backticks.
        #
        # See: https://stackoverflow.com/questions/66435475/how-to-escape-the-backtick-character-in-a-rst-file
        text = element.astext()
        assert "`" not in text, (
            "(mristin, 2024-03-27): Theoretically, we could escape the backticks "
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

        escaped = (
            text
            # NOTE (mristin, 2024-03-27):
            # See: https://stackoverflow.com/questions/2290757/how-can-you-escape-the-character-in-javadoc
            .replace("@", "&#064;")
        )
        return [_TokenText(f"{{@code {escaped}}}")], None

    def _render_children(
        self,
        children: Sequence[docutils.nodes.Element],
        prefix: Optional[_Token] = None,
        suffix: Optional[_Token] = None,
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        """
        Render the children and concatenate the resulting tokens.

        If ``prefix`` token is defined, it will be prepended to the result.

        If ``suffix`` token is defined, it will be appended to the result
        """
        result = []  # type: List[_Token]

        if prefix is not None:
            result.append(prefix)

        errors = []  # type: List[str]

        for child in children:
            tokens, child_errors = self.transform(child)
            if child_errors is not None:
                errors.extend(child_errors)
                continue

            assert tokens is not None
            result.extend(tokens)

        if len(errors) > 0:
            return None, errors

        if suffix is not None:
            result.append(suffix)

        return result, None

    def transform_paragraph(
        self, element: docutils.nodes.paragraph
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        return self._render_children(children=element.children, prefix=_TokenP())

    def transform_emphasis(
        self, element: docutils.nodes.emphasis
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        return self._render_children(
            children=element.children,
            prefix=_TokenText("<em>"),
            suffix=_TokenText("</em>"),
        )

    def transform_list_item(
        self, element: docutils.nodes.list_item
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        return self._render_children(element.children)

    def transform_bullet_list(
        self, element: docutils.nodes.bullet_list
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        result = [_TokenULOpen()]  # type: List[_Token]

        errors = []  # type: List[str]

        for child in element.children:
            assert isinstance(child, docutils.nodes.list_item), (
                f"Expected a list item in the bullet list, "
                f"but got an instance of {type(child)}: {child}"
            )

            child_tokens, child_errors = self.transform(child)
            if child_errors is not None:
                errors.extend(child_errors)
                continue

            assert child_tokens is not None
            result.append(_TokenLI())
            result.extend(child_tokens)

        result.append(_TokenULClose())

        if len(errors) > 0:
            return None, errors

        return result, None

    def transform_note(
        self, element: docutils.nodes.note
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        return self._render_children(children=element.children, prefix=_TokenP())

    def transform_reference(
        self, element: docutils.nodes.reference
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        text = element.astext()
        escaped_for_href = urllib.parse.quote(element.astext())
        escaped_for_html = html.escape(text)
        return [
            _TokenText(f"<a href='{escaped_for_href}'>{escaped_for_html}</a>")
        ], None

    def transform_field_body(
        self, element: docutils.nodes.field_body
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        return self._render_children(element.children)

    def transform_document(
        self, element: docutils.nodes.document
    ) -> Tuple[Optional[List[_Token]], Optional[List[str]]]:
        return self._render_children(element.children)


def _remove_redundant_p(tokens: List[_Token]) -> List[_Token]:
    """Remove redundant chains of ``<p>`` tokens."""
    result = []  # type: List[_Token]

    # region Remove consecutive ``<p>``
    last_token = None  # type: Optional[_Token]
    for token in tokens:
        if (
            last_token is not None
            and isinstance(last_token, _TokenP)
            and isinstance(token, _TokenP)
        ):
            continue

        result.append(token)
        last_token = token
    # endregion

    # region Remove trailing ``<p>``
    cutoff = 0
    for token in reversed(result):
        if not isinstance(token, _TokenP):
            break

        cutoff += 1

    result = result[: len(result) - cutoff]
    # endregion

    return result


def _strip_prefix_p(tokens: List[_Token]) -> List[_Token]:
    """Strip the ``<p>`` from ``tokens`` if they start with such a token."""
    if len(tokens) == 0:
        return tokens

    if isinstance(tokens[0], _TokenP):
        return tokens[1:]

    return tokens


def _add_prefix_p_if_necessary(tokens: List[_Token]) -> List[_Token]:
    """Add a ``<p>`` at the beginning if the ``tokens`` do not start with a re-flow."""
    if len(tokens) == 0:
        return tokens

    if isinstance(tokens[0], (_TokenP, _TokenULOpen)):
        return tokens

    return [_TokenP()] + tokens


@dataclasses.dataclass
class _TextBlock:
    """Model a text block in the indented output, to be joined with empty strings."""

    text: str


class _RelativeIndention:
    """
    Represent the relative indention.

    Since the indention is *relative*, it can be either positive or negative.
    """

    @require(lambda direction: direction in (-1, 1))
    def __init__(self, direction: int) -> None:
        self.direction = direction

    def __repr__(self) -> str:
        """Generate text representation for easier debugging."""
        return f"{self.__class__.__name__}({self.direction!r})"


_TextDirective = Union[_TextBlock, _RelativeIndention]


class _IndentionMachine:
    """Write the text to a buffer, considering the indention."""

    def __init__(self, indention: str = "  ") -> None:
        self._indention_level = 0
        self._buffer: List[_TextDirective] = []
        self.indention = indention

    def write(self, text: str) -> None:
        """Direct a write of text onto the buffer."""
        self._buffer.append(_TextBlock(text))

    def indent(self) -> None:
        """Direct an indention onto the buffer."""
        self._indention_level += 1
        self._buffer.append(_RelativeIndention(direction=1))

    def dedent(self) -> None:
        """Direct a dedention onto the buffer."""
        self._indention_level -= 1
        if self._indention_level < 0:
            raise ValueError("Unexpected negative indention")

        self._buffer.append(_RelativeIndention(direction=-1))

    def render(self) -> str:
        """Render the buffer as indented text."""
        level = 0
        pending_text_blocks = []  # type: List[_TextBlock]

        writer = io.StringIO()

        for directive in self._buffer:
            if isinstance(directive, _TextBlock):
                pending_text_blocks.append(directive)

            elif isinstance(directive, _RelativeIndention):
                writer.write(
                    textwrap.indent(
                        "".join(block.text for block in pending_text_blocks),
                        self.indention * level,
                    )
                )
                level += directive.direction
                if level < 0:
                    raise AssertionError(
                        "Unexpected indention level below zero; "
                        "expected to catch this in ``dedent()``"
                    )

                pending_text_blocks = []
            else:
                assert_never(directive)

        if len(pending_text_blocks) > 0:
            writer.write(
                textwrap.indent(
                    "".join(block.text for block in pending_text_blocks),
                    self.indention * level,
                )
            )

        return writer.getvalue()


def _render_tokens(tokens: Sequence[_Token]) -> str:
    """Render the output tokens as text."""
    if len(tokens) == 0:
        return ""

    indention_machine = _IndentionMachine()

    for i, token in enumerate(tokens):
        if isinstance(token, _TokenText):
            indention_machine.write(token.content)

        elif isinstance(token, _TokenP):
            if i > 0:
                indention_machine.write("\n\n")

            indention_machine.write("<p>")

        elif isinstance(token, _TokenULOpen):
            if i > 0:
                indention_machine.write("\n\n")

            indention_machine.write("<ul>")
            indention_machine.indent()
        elif isinstance(token, _TokenULClose):
            indention_machine.dedent()
            indention_machine.write("\n</ul>")
        elif isinstance(token, _TokenLI):
            # NOTE (mristin, 2024-03-28):
            # We add a space after ``<li>`` for better readability of the code in, say,
            # a text editor.
            indention_machine.write("\n<li> ")
        else:
            assert_never(token)

    return indention_machine.render()


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


def _post_process_summary(tokens: List[_Token]) -> List[_Token]:
    """Perform the post-processing steps for the summary tokens."""
    return _remove_redundant_p(_strip_prefix_p(tokens))


def _post_process_remark(tokens: List[_Token]) -> List[_Token]:
    """Perform the post-processing steps for the remark tokens."""
    return _remove_redundant_p(_add_prefix_p_if_necessary(tokens))


def _generate_summary_remarks(
    description: intermediate.SummaryRemarksDescription, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for a summary-remarks."""
    errors = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    tokens = []  # type: List[_Token]

    summary_tokens, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert summary_tokens is not None
        tokens.extend(_post_process_summary(summary_tokens))

    for remark in description.remarks:
        remark_tokens, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert remark_tokens is not None
            tokens.extend(_post_process_remark(remark_tokens))

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    return documentation_comment(Stripped(_render_tokens(tokens))), None


def _generate_summary_remarks_constraints(
    description: intermediate.SummaryRemarksConstraintsDescription, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for a summary-remarks-constraints."""
    errors = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    tokens = []  # type: List[_Token]

    summary_tokens, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert summary_tokens is not None
        tokens.extend(_post_process_summary(summary_tokens))

    for remark in description.remarks:
        remark_tokens, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert remark_tokens is not None
            tokens.extend(_post_process_remark(remark_tokens))

    if len(description.constraints_by_identifier) > 0:
        tokens.append(_TokenP())
        tokens.append(_TokenText("Constraints:"))

        tokens.append(_TokenULOpen())

        for constraint_id, constraint in description.constraints_by_identifier.items():
            constraint_tokens, constraint_errors = renderer.transform(constraint)
            if constraint_errors is not None:
                errors.extend(constraint_errors)
            else:
                assert constraint_tokens is not None
                tokens.append(_TokenLI())
                tokens.append(_TokenText(f"Constraint {constraint_id}:\n"))
                tokens.extend(_strip_prefix_p(_remove_redundant_p(constraint_tokens)))

        tokens.append(_TokenULClose())

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    return documentation_comment(Stripped(_render_tokens(tokens))), None


def generate_comment_for_enumeration_literal(
    description: intermediate.DescriptionOfEnumerationLiteral, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given enumeration literal."""
    return _generate_summary_remarks(description=description, context=context)


def generate_comment_for_our_type(
    description: intermediate.DescriptionOfOurType, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for our type."""
    return _generate_summary_remarks_constraints(
        description=description, context=context
    )


def generate_comment_for_property(
    description: intermediate.DescriptionOfProperty, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given property."""
    return _generate_summary_remarks_constraints(
        description=description, context=context
    )


def generate_comment_for_signature(
    description: intermediate.DescriptionOfSignature, context: Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """
    Generate the docstring for the given signature.

    A signature, in this context, means a function or a method signature.
    """
    errors = []  # type: List[str]

    renderer = _ElementRenderer(context=context)

    tokens = []  # type: List[_Token]

    summary_tokens, summary_errors = renderer.transform(description.summary)
    if summary_errors is not None:
        errors.extend(summary_errors)
    else:
        assert summary_tokens is not None
        tokens.extend(_post_process_summary(summary_tokens))

    for remark in description.remarks:
        remark_tokens, remark_errors = renderer.transform(remark)
        if remark_errors:
            errors.extend(remark_errors)
        else:
            assert remark_tokens is not None
            tokens.extend(_post_process_remark(remark_tokens))

    blocks = []  # type: List[Stripped]

    summary_remarks = _render_tokens(tokens)

    if len(summary_remarks) > 0:
        blocks.append(Stripped(summary_remarks))

    param_and_return_blocks = []  # type: List[str]
    for arg_name, arg_description in description.arguments_by_name.items():
        arg_tokens, arg_errors = renderer.transform(arg_description)
        if arg_errors is not None:
            errors.extend(arg_errors)
            continue

        assert arg_tokens is not None

        arg_description = _render_tokens(
            _strip_prefix_p(_remove_redundant_p(arg_tokens))
        )

        param_and_return_blocks.append(Stripped(f"@param {arg_name} {arg_description}"))

    if description.returns is not None:
        returns_tokens, returns_errors = renderer.transform(description.returns)
        if returns_errors is not None:
            errors.extend(returns_errors)
        else:
            assert returns_tokens is not None

            returns_description = _render_tokens(
                _strip_prefix_p(_remove_redundant_p(returns_tokens))
            )

            param_and_return_blocks.append(Stripped(f"@return {returns_description}"))

    if len(errors) > 0:
        return None, [
            Error(description.parsed.node, error_message) for error_message in errors
        ]

    if len(param_and_return_blocks) > 0:
        blocks.append(Stripped("\n".join(param_and_return_blocks)))

    return documentation_comment(Stripped("\n\n".join(blocks))), None
