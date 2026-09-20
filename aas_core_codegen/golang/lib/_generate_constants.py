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
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    description as golang_description,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
)


def _generate_documentation_comment_for_constant(
    description: intermediate.DescriptionOfConstant,
    context: golang_description.Context,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given constant."""
    # fmt: off
    comment, errors = (
        golang_description
        .generate_comment_for_summary_remarks(
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
    """Generate constants corresponding to the constants of the meta-model."""
    writer = io.StringIO()

    if constant.description is not None:
        comment, comment_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=golang_description.Context(
                package=golang_common.CONSTANTS_PACKAGE, cls_or_enum=None
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

    constant_name = golang_naming.constant_name(constant.name)

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        assert isinstance(constant.value, bool)
        literal = golang_common.boolean_literal(constant.value)
        writer.write(f"const {constant_name} bool = {literal}")

    elif constant.a_type is intermediate.PrimitiveType.INT:
        assert isinstance(constant.value, int)

        if constant.value > 2**63 - 1 or constant.value < -(2**63):
            return None, Error(
                constant.parsed.node,
                f"The value of the constant {constant.name!r} overflows "
                f"64-bit signed integer",
            )
        writer.write(f"const {constant_name} int64 = {str(constant.value)}")

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        assert isinstance(constant.value, float)

        # NOTE (mristin):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.
        literal = golang_common.float_literal(constant.value)

        writer.write(f"const {constant_name} float64 = {literal}")

    elif constant.a_type is intermediate.PrimitiveType.STR:
        assert isinstance(constant.value, str)
        literal = golang_common.string_literal(constant.value)

        writer.write(f"const {constant_name} string = {literal}")

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        assert isinstance(constant.value, bytearray)

        literal, _ = golang_common.bytes_literal(value=constant.value)

        writer.write(
            f"""\
var {constant_name} = {indent_but_first_line(literal, I)}"""
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
            context=golang_description.Context(
                package=golang_common.CONSTANTS_PACKAGE, cls_or_enum=None
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
        set_type = "map[bool]struct{}"
        for literal in constant.literals:
            assert isinstance(literal.value, bool)
            literal_codes.append(golang_common.boolean_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.INT:
        set_type = "map[int64]struct{}"
        for literal in constant.literals:
            assert isinstance(literal.value, int)

            literal_codes.append(str(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        set_type = "map[float64]struct{}"

        for literal in constant.literals:
            assert isinstance(literal.value, float)

            literal_codes.append(golang_common.float_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.STR:
        set_type = "map[string]struct{}"

        for literal in constant.literals:
            assert isinstance(literal.value, str)
            literal_value = golang_common.string_literal(literal.value)
            literal_codes.append(f"{literal_value}: struct{{}}{{}}")

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        errors.append(
            Error(
                constant.parsed.node,
                f"Golang does not support sets of byte arrays, so we can not transpile "
                f"the constant set {constant.name!r}",
            )
        )

    else:
        assert_never(constant.a_type)

    literals_joined = ",\n".join(literal_codes)

    constant_name = golang_naming.constant_name(constant.name)

    writer.write(
        f"""\
var {constant_name} = {set_type} {{
{I}{indent_but_first_line(literals_joined, I)},
}}"""
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
            context=golang_description.Context(
                package=golang_common.CONSTANTS_PACKAGE, cls_or_enum=None
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

    enum_name = golang_naming.enum_name(constant.enumeration.name)

    literal_codes = []  # type: List[str]

    for literal in constant.literals:
        literal_name = golang_naming.enum_literal_name(
            constant.enumeration.name, literal.name
        )

        literal_codes.append(f"aastypes.{literal_name}: struct{{}}{{}}")

    constant_name = golang_naming.constant_name(constant.name)

    literals_joined = ",\n".join(literal_codes)

    writer.write(
        f"""\
var {constant_name} = map[aastypes.{enum_name}]struct{{}} {{
{I}{indent_but_first_line(literals_joined, I)},
}}"""
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
    symbol_table: intermediate.SymbolTable, repo_url: Stripped
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code to define the constants of the meta-model."""
    errors = []  # type: List[Error]

    aastypes_url_literal = golang_common.string_literal(f"{repo_url}/types")

    blocks = [
        Stripped(
            """\
// Package constants provides immutable values of the meta-model.
//
// These are not necessarily constants in the sense of Go language, but
// variables that are expected not to be mutated by the clients.
package constants"""
        ),
        golang_common.WARNING,
        # NOTE (mristin):
        # The import block is filled in at the very end: it depends on what
        # the constants below actually name, and an unused import does not
        # compile in Go.
        Stripped(""),
    ]  # type: List[Stripped]

    import_index = len(blocks) - 1

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

    blocks.append(golang_common.WARNING)

    import_lines = []  # type: List[str]
    if golang_common.names_package(blocks, "aastypes"):
        import_lines.append(f"{I}aastypes {aastypes_url_literal}")

    if len(import_lines) == 0:
        del blocks[import_index]
    else:
        blocks[import_index] = Stripped("import (\n" + "\n".join(import_lines) + "\n)")

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
