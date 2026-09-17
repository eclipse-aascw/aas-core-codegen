"""Generate code to define the constants of the meta-model."""
import io
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
)
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
    description as typescript_description,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
)


def _generate_documentation_comment_for_constant(
    description: intermediate.DescriptionOfConstant,
    context: typescript_description.Context,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given constant."""
    # fmt: off
    comment, errors = (
        typescript_description
        .generate_documentation_comment_for_summary_remarks(
            description=description, context=context
        )
    )
    # fmt: on

    if errors is not None:
        return None, errors

    assert comment is not None
    return comment, None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_primitive(
    constant: intermediate.ConstantPrimitive,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant primitive."""
    writer = io.StringIO()

    if constant.description is not None:
        comment, comment_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=typescript_description.Context(
                module=typescript_common.CONSTANTS_MODULE, cls_or_enum=None
            ),
        )
        if comment_errors is not None:
            return None, Error(
                constant.parsed.node,
                f"Failed to generate the documentation comment for {constant.name!r}",
                comment_errors,
            )

        assert comment is not None
        writer.write(comment)
        writer.write("\n")

    constant_name = typescript_naming.constant_name(constant.name)

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        assert isinstance(constant.value, bool)
        literal = typescript_common.boolean_literal(constant.value)
        writer.write(f"export const {constant_name} = {literal};")

    elif constant.a_type is intermediate.PrimitiveType.INT:
        assert isinstance(constant.value, int)

        if not typescript_common.representable_as_number(constant.value):
            return None, Error(
                constant.parsed.node,
                f"The integer can not be represented as a double-precision "
                f"floating-point number in TypeScript: {constant.value!r}",
            )

        literal = typescript_common.numeric_literal(constant.value)

        writer.write(f"export const {constant_name} = {literal};")

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        assert isinstance(constant.value, float)

        # NOTE (mristin):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.
        literal = typescript_common.numeric_literal(constant.value)

        writer.write(f"export const {constant_name} = {literal};")

    elif constant.a_type is intermediate.PrimitiveType.STR:
        assert isinstance(constant.value, str)
        literal = typescript_common.string_literal(constant.value)

        writer.write(f"export const {constant_name} = {literal};")

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        assert isinstance(constant.value, bytearray)

        literal, _ = typescript_common.bytes_literal(value=constant.value)

        writer.write(
            f"""\
export const {constant_name} =
{I}{indent_but_first_line(literal, I)};"""
        )

    else:
        assert_never(constant.a_type)

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_primitives(
    constant: intermediate.ConstantSetOfPrimitives,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of primitives."""
    errors = []  # type: List[Error]

    writer = io.StringIO()

    if constant.description is not None:
        comment, comment_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=typescript_description.Context(
                module=typescript_common.CONSTANTS_MODULE, cls_or_enum=None
            ),
        )
        if comment_errors is not None:
            errors.append(
                Error(
                    constant.parsed.node,
                    f"Failed to generate the documentation comment for {constant.name!r}",
                    comment_errors,
                )
            )
        else:
            assert comment is not None
            writer.write(comment)
            writer.write("\n")

    literal_codes = []  # type: List[str]
    set_type: str

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        set_type = "boolean"
        for literal in constant.literals:
            assert isinstance(literal.value, bool)
            literal_codes.append(typescript_common.boolean_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.INT:
        set_type = "number"
        for literal in constant.literals:
            assert isinstance(literal.value, int)

            if not typescript_common.representable_as_number(literal.value):
                errors.append(
                    Error(
                        literal.parsed.node,
                        f"The item of the constant set {constant.name!r} can not be represented as "
                        f"a double-precision floating-point number: {literal.value!r}",
                    )
                )
            else:
                literal_codes.append(typescript_common.numeric_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        set_type = "number"

        for literal in constant.literals:
            assert isinstance(literal.value, float)

            # NOTE (mristin):
            # We assume that the float constants are not meant to be all to precise.
            # Therefore, we use a string representation here. However, beware that we
            # might have to use a more precise representation in the future if the spec
            # change.
            literal_codes.append(typescript_common.numeric_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.STR:
        set_type = "string"

        for literal in constant.literals:
            assert isinstance(literal.value, str)
            literal_codes.append(typescript_common.string_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        errors.append(
            Error(
                constant.parsed.node,
                f"TypeScript does not support sets of byte arrays, so we can not transpile "
                f"the constant set {constant.name!r}",
            )
        )

    else:
        assert_never(constant.a_type)

    literals_joined = ",\n".join(literal_codes)

    constant_name = typescript_naming.constant_name(constant.name)

    writer.write(
        f"""\
export const {constant_name} = new Set<{set_type}>([
{I}{indent_but_first_line(literals_joined, I)}
]);"""
    )

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_enumeration_literals(
    constant: intermediate.ConstantSetOfEnumerationLiterals,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of enumeration literals."""
    writer = io.StringIO()

    if constant.description is not None:
        comment, comment_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=typescript_description.Context(
                module=typescript_common.CONSTANTS_MODULE, cls_or_enum=None
            ),
        )
        if comment_errors is not None:
            return None, Error(
                constant.parsed.node,
                f"Failed to generate the documentation comment for {constant.name!r}",
                comment_errors,
            )

        assert comment is not None
        writer.write(comment)
        writer.write("\n")

    enum_name = typescript_naming.enum_name(constant.enumeration.name)

    literal_codes = []  # type: List[str]

    for literal in constant.literals:
        literal_name = typescript_naming.enum_literal_name(literal.name)

        literal_codes.append(f"AasTypes.{enum_name}.{literal_name}")

    constant_name = typescript_naming.constant_name(constant.name)

    literals_joined = ",\n".join(literal_codes)

    writer.write(
        f"""\
export const {constant_name} = new Set<AasTypes.{enum_name}>([
{I}{indent_but_first_line(literals_joined, I)}
]);"""
    )

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
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code to define the constants of the meta-model."""
    errors = []  # type: List[Error]

    blocks = [
        Stripped(
            """\
/**
 * Provide constant values of the meta-model.
 */"""
        ),
        typescript_common.WARNING,
        Stripped("/* eslint-disable @typescript-eslint/no-unused-vars */"),
        Stripped('import * as AasTypes from "./types";'),
    ]  # type: List[Stripped]

    for constant in symbol_table.constants:
        block: Optional[Stripped]
        error: Optional[Error]

        if isinstance(constant, intermediate.ConstantPrimitive):
            block, error = _generate_constant_primitive(constant=constant)
        elif isinstance(constant, intermediate.ConstantSetOfPrimitives):
            block, error = _generate_constant_set_of_primitives(constant=constant)
        elif isinstance(constant, intermediate.ConstantSetOfEnumerationLiterals):
            block, error = _generate_constant_set_of_enumeration_literals(
                constant=constant
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

    blocks.append(Stripped("/* eslint-enable @typescript-eslint/no-unused-vars */"))
    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
