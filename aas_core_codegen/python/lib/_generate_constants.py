"""Generate code to define the constants of the meta-model."""
import io
import textwrap
from typing import (
    Optional,
    List,
    Tuple,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    assert_never,
    Stripped,
    indent_but_first_line,
    Identifier,
)
from aas_core_codegen.python import (
    common as python_common,
    naming as python_naming,
    description as python_description,
)
from aas_core_codegen.python.common import (
    INDENT as I,
)


# region Generation


def _generate_documentation_comment_for_constant(
    description: intermediate.DescriptionOfConstant, context: python_description.Context
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the docstring for the given constant."""
    text, errors = python_description.generate_summary_remarks(
        description=description, context=context
    )

    if errors is not None:
        return None, errors

    assert text is not None

    return python_description.documentation_comment(text), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_primitive(
    constant: intermediate.ConstantPrimitive,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant primitive."""
    writer = io.StringIO()

    if constant.description is not None:
        docstring, docstring_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=python_description.Context(
                qualified_module_name=qualified_module_name,
                module=Identifier("constants"),
                cls_or_enum=None,
            ),
        )
        if docstring_errors is not None:
            return None, Error(
                constant.parsed.node,
                f"Failed to generate the documentation comment for {constant.name!r}",
                docstring_errors,
            )

        assert docstring is not None
        writer.write(docstring)
        writer.write("\n")

    constant_name = python_naming.constant_name(constant.name)

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        literal = "True" if constant.value else "False"

        writer.write(f"{constant_name}: bool = {literal}")

    elif constant.a_type is intermediate.PrimitiveType.INT:
        literal = str(constant.value)

        writer.write(f"{constant_name}: int = {literal}")

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        # NOTE (mristin):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.
        literal = str(constant.value)

        writer.write(f"{constant_name}: float = {literal}")

    elif constant.a_type is intermediate.PrimitiveType.STR:
        assert isinstance(constant.value, str)
        literal = python_common.string_literal(constant.value)

        writer.write(f"{constant_name}: str = {literal}")

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        assert isinstance(constant.value, bytearray)

        literal, _ = python_common.bytes_literal(value=constant.value)

        writer.write(
            f"""\
{constant_name}: bytes = (
{I}{indent_but_first_line(literal, I)}
)"""
        )

    else:
        assert_never(constant.a_type)

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_primitives(
    constant: intermediate.ConstantSetOfPrimitives,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of primitives."""
    writer = io.StringIO()

    if constant.description is not None:
        docstring, docstring_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=python_description.Context(
                qualified_module_name=qualified_module_name,
                module=Identifier("constants"),
                cls_or_enum=None,
            ),
        )
        if docstring_errors is not None:
            return None, Error(
                constant.parsed.node,
                f"Failed to generate the documentation comment for {constant.name!r}",
                docstring_errors,
            )

        assert docstring is not None
        writer.write(docstring)
        writer.write("\n")

    constant_name = python_naming.constant_name(constant.name)

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        writer.write(
            f"""\
{constant_name}: Set[bool] = {{
"""
        )

        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent("True" if literal.value else "False", I))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write("}")

    elif constant.a_type is intermediate.PrimitiveType.INT:
        writer.write(
            f"""\
{constant_name}: Set[int] = {{
"""
        )

        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent(str(literal.value), I))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write("}")

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        # NOTE (mristin):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.

        writer.write(
            f"""\
{constant_name}: Set[float] = {{
"""
        )

        for i, literal in enumerate(constant.literals):
            writer.write(textwrap.indent(str(literal.value), I))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write("}")

    elif constant.a_type is intermediate.PrimitiveType.STR:
        writer.write(
            f"""\
{constant_name}: Set[str] = {{
"""
        )

        for i, literal in enumerate(constant.literals):
            assert isinstance(literal.value, str)

            writer.write(
                textwrap.indent(python_common.string_literal(literal.value), I)
            )

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write("}")

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        writer.write(
            f"""\
{constant_name}: Set[bytes] = {{
"""
        )

        for i, literal in enumerate(constant.literals):
            assert isinstance(literal.value, bytearray)

            literal_in_code, _ = python_common.bytes_literal(bytes(literal.value))

            writer.write(textwrap.indent(literal_in_code, I))

            if i < len(constant.literals) - 1:
                writer.write(",\n")
            else:
                writer.write("\n")

        writer.write("}")

    else:
        assert_never(constant.a_type)

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_enumeration_literals(
    constant: intermediate.ConstantSetOfEnumerationLiterals,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of enumeration literals."""
    writer = io.StringIO()

    if constant.description is not None:
        docstring, docstring_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=python_description.Context(
                qualified_module_name=qualified_module_name,
                module=Identifier("constants"),
                cls_or_enum=None,
            ),
        )
        if docstring_errors is not None:
            return None, Error(
                constant.parsed.node,
                f"Failed to generate the documentation comment for {constant.name!r}",
                docstring_errors,
            )

        assert docstring is not None
        writer.write(docstring)
        writer.write("\n")

    constant_name = python_naming.constant_name(constant.name)
    enum_name = python_naming.enum_name(constant.enumeration.name)

    writer.write(
        f"""\
{constant_name}: Set[aas_types.{enum_name}] = {{
"""
    )

    for i, literal in enumerate(constant.literals):
        literal_name = python_naming.enum_literal_name(literal.name)

        writer.write(textwrap.indent(f"aas_types.{enum_name}.{literal_name}", I))

        if i < len(constant.literals) - 1:
            writer.write(",\n")
        else:
            writer.write("\n")

    writer.write("}")

    return Stripped(writer.getvalue()), None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code to define the constants of the meta-model.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    errors = []  # type: List[Error]

    blocks = [
        Stripped('"""Provide constant values of the meta-model."""'),
        python_common.WARNING,
        Stripped(
            f"""\
from typing import Set

import {qualified_module_name}.types as aas_types"""
        ),
    ]  # type: List[Stripped]

    for constant in symbol_table.constants:
        block: Optional[Stripped]
        error: Optional[Error]

        if isinstance(constant, intermediate.ConstantPrimitive):
            block, error = _generate_constant_primitive(
                constant=constant, qualified_module_name=qualified_module_name
            )
        elif isinstance(constant, intermediate.ConstantSetOfPrimitives):
            block, error = _generate_constant_set_of_primitives(
                constant=constant, qualified_module_name=qualified_module_name
            )
        elif isinstance(constant, intermediate.ConstantSetOfEnumerationLiterals):
            block, error = _generate_constant_set_of_enumeration_literals(
                constant=constant, qualified_module_name=qualified_module_name
            )
        else:
            assert_never(constant)

        if error is not None:
            errors.append(error)
            continue

        assert block is not None
        blocks.append(block)

    if len(errors) > 0:
        return None, errors

    blocks.append(python_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


# endregion

assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
