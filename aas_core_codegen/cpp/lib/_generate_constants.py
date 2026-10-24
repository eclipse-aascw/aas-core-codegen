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
from aas_core_codegen.cpp import (
    common as cpp_common,
    naming as cpp_naming,
    description as cpp_description,
)
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
)


def _generate_documentation_comment_for_constant(
    description: intermediate.DescriptionOfConstant,
    context: cpp_description.Context,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the documentation comment for the given constant."""
    # fmt: off
    comment, errors = (
        cpp_description
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
def _generate_constant_primitive_definition(
    constant: intermediate.ConstantPrimitive,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant primitive."""
    writer = io.StringIO()

    if constant.description is not None:
        comment, comment_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=cpp_description.Context(
                namespace=cpp_common.CONSTANTS_NAMESPACE, cls_or_enum=None
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

    constant_name = cpp_naming.constant_name(constant.name)

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        writer.write(f"extern const bool {constant_name};")

    elif constant.a_type is intermediate.PrimitiveType.INT:
        writer.write(f"extern const int64_t {constant_name};")

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        writer.write(f"extern const double {constant_name};")

    elif constant.a_type is intermediate.PrimitiveType.STR:
        writer.write(f"extern const std::wstring {constant_name};")

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        writer.write(f"extern const std::vector<std::uint8_t> {constant_name};")

    else:
        # noinspection PyTypeChecker
        assert_never(constant.a_type)

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_primitive_implementation(
    constant: intermediate.ConstantPrimitive,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the implementation of a constant primitive."""
    constant_name = cpp_naming.constant_name(constant.name)

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        assert isinstance(constant.value, bool)
        literal = cpp_common.boolean_literal(constant.value)

        return Stripped(f"const bool {constant_name} = {literal};"), None

    elif constant.a_type is intermediate.PrimitiveType.INT:
        assert isinstance(constant.value, int)

        if constant.value > 2**63 - 1 or constant.value < -(2**63):
            return None, Error(
                constant.parsed.node,
                f"The value of the constant {constant.name!r} overflows "
                f"64-bit signed integer",
            )
        return Stripped(f"const int64_t {constant_name} = {constant.value!s};"), None

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        assert isinstance(constant.value, float)

        # NOTE (mristin):
        # We assume that the float constants are not meant to be all to precise.
        # Therefore, we use a string representation here. However, beware that we
        # might have to use a more precise representation in the future if the spec
        # change.
        literal = cpp_common.float_literal(constant.value)

        return Stripped(f"const double {constant_name} = {literal};"), None

    elif constant.a_type is intermediate.PrimitiveType.STR:
        assert isinstance(constant.value, str)
        literal = cpp_common.wstring_literal(constant.value)

        return (
            Stripped(
                f"""\
const std::wstring {constant_name} = (
{I}{indent_but_first_line(literal, I)}
);"""
            ),
            None,
        )

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        assert isinstance(constant.value, bytes)

        literal, _ = cpp_common.bytes_literal(value=constant.value)

        return (
            Stripped(
                f"""\
const std::vector<std::uint_8> {constant_name} = (
{I}{indent_but_first_line(literal, I)}
);"""
            ),
            None,
        )

    else:
        # noinspection PyTypeChecker
        assert_never(constant.a_type)


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_primitives_definition(
    constant: intermediate.ConstantSetOfPrimitives,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of primitives."""
    errors: List[Error] = []

    writer = io.StringIO()

    if constant.description is not None:
        comment, comment_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=cpp_description.Context(
                namespace=cpp_common.CONSTANTS_NAMESPACE, cls_or_enum=None
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

    set_type: Optional[str]

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        set_type = "std::unordered_set<bool>"

    elif constant.a_type is intermediate.PrimitiveType.INT:
        set_type = "std::unordered_set<int64_t>"

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        set_type = "std::unordered_set<double>"

    elif constant.a_type is intermediate.PrimitiveType.STR:
        set_type = "std::unordered_set<std::wstring>"

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        set_type = "std::unordered_set<std::vector<std::uint8_t>, HashBytes>"

    else:
        # noinspection PyTypeChecker
        assert_never(constant.a_type)

    constant_name = cpp_naming.constant_name(constant.name)

    writer.write(
        f"""\
extern const {set_type} {constant_name};"""
    )

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_primitives_implementation(
    constant: intermediate.ConstantSetOfPrimitives,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the implementation of a constant set of primitives."""
    literal_codes: List[str] = []

    set_type: str

    if constant.a_type is intermediate.PrimitiveType.BOOL:
        set_type = "std::unordered_set<bool>"

        for literal in constant.literals:
            assert isinstance(literal.value, bool)
            literal_codes.append(cpp_common.boolean_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.INT:
        set_type = "std::unordered_set<int64_t>"

        for literal in constant.literals:
            assert isinstance(literal.value, int)

            literal_codes.append(str(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.FLOAT:
        set_type = "std::unordered_set<double>"

        for literal in constant.literals:
            assert isinstance(literal.value, float)

            literal_codes.append(cpp_common.float_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.STR:
        set_type = "std::unordered_set<std::wstring>"

        for literal in constant.literals:
            assert isinstance(literal.value, str)
            literal_codes.append(cpp_common.wstring_literal(literal.value))

    elif constant.a_type is intermediate.PrimitiveType.BYTEARRAY:
        set_type = Stripped(
            f"""\
std::unordered_set<
{I}std::vector<std::uint8_t>,
{I}HashBytes
>"""
        )

        for literal in constant.literals:
            assert isinstance(literal.value, bytes)
            literal_code, _ = cpp_common.bytes_literal(literal.value)
            literal_codes.append(literal_code)

    else:
        # noinspection PyTypeChecker
        assert_never(constant.a_type)

    literals_joined = ",\n".join(literal_codes)

    constant_name = cpp_naming.constant_name(constant.name)

    return (
        Stripped(
            f"""\
const {set_type} {constant_name} = {{
{I}{indent_but_first_line(literals_joined, I)}
}};"""
        ),
        None,
    )


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_enumeration_literals_definition(
    constant: intermediate.ConstantSetOfEnumerationLiterals,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of enumeration literals."""
    writer = io.StringIO()

    if constant.description is not None:
        comment, comment_errors = _generate_documentation_comment_for_constant(
            description=constant.description,
            context=cpp_description.Context(
                namespace=cpp_common.CONSTANTS_NAMESPACE, cls_or_enum=None
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

    enum_name = cpp_naming.enum_name(constant.enumeration.name)

    constant_name = cpp_naming.constant_name(constant.name)

    set_type = cpp_common.generate_set_type(
        item_type=Stripped(f"types::{enum_name}"),
        items_are_enumeration_literals=True,
    )

    writer.write(f"extern const {set_type} {constant_name};")

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_constant_set_of_enumeration_literals_implementation(
    constant: intermediate.ConstantSetOfEnumerationLiterals,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a constant set of enumeration literals."""

    enum_name = cpp_naming.enum_name(constant.enumeration.name)

    literal_codes: List[str] = []
    for literal in constant.literals:
        literal_name = cpp_naming.enum_literal_name(literal.name)

        literal_codes.append(f"types::{enum_name}::{literal_name}")

    constant_name = cpp_naming.constant_name(constant.name)

    literals_joined = ",\n".join(literal_codes)

    set_type = cpp_common.generate_set_type(
        item_type=Stripped(f"types::{enum_name}"),
        items_are_enumeration_literals=True,
    )

    return (
        Stripped(
            f"""\
const {set_type} {constant_name} = {{
{I}{indent_but_first_line(literals_joined, I)}
}};"""
        ),
        None,
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(
    symbol_table: intermediate.SymbolTable,
    library_namespace: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate header to define the constants of the meta-model."""
    errors: List[Error] = []

    namespace = Stripped(f"{library_namespace}::{cpp_common.CONSTANTS_NAMESPACE}")

    include_guard_var = cpp_common.include_guard_var(namespace)

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/types.hpp"

#pragma warning(push, 0)
#include <cstdint>
#include <unordered_set>
#include <vector>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            f"""\
/**
 * \\defgroup constants Pre-defined constants of the meta-model
 * @{{
 */
namespace {cpp_common.CONSTANTS_NAMESPACE} {{"""
        ),
        Stripped(
            f"""\
/**
 * Hash a blob of bytes based on the Java's String hash.
 */
struct HashBytes {{
{I}std::size_t operator()(const std::vector<std::uint8_t>& bytes) const;
}};"""
        ),
    ]

    for constant in symbol_table.constants:
        block: Optional[Stripped]
        error: Optional[Error]

        if isinstance(constant, intermediate.ConstantPrimitive):
            block, error = _generate_constant_primitive_definition(constant=constant)
        elif isinstance(constant, intermediate.ConstantSetOfPrimitives):
            block, error = _generate_constant_set_of_primitives_definition(
                constant=constant
            )
        elif isinstance(constant, intermediate.ConstantSetOfEnumerationLiterals):
            block, error = _generate_constant_set_of_enumeration_literals_definition(
                constant=constant
            )
        else:
            # noinspection PyTypeChecker
            assert_never(constant)

        if error is not None:
            errors.append(error)
            continue

        assert block is not None
        blocks.append(block)

    if len(errors) > 0:
        return None, errors

    blocks.extend(
        [
            Stripped(
                f"""\
}}  // namespace {cpp_common.COMMON_NAMESPACE}
/**@}}*/"""
            ),
            cpp_common.generate_namespace_closing(library_namespace),
            cpp_common.WARNING,
            Stripped(f"#endif  // {include_guard_var}"),
        ]
    )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable,
    library_namespace: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate implementation to define the constants of the meta-model."""
    errors: List[Error] = []

    namespace = Stripped(f"{library_namespace}::constants")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        Stripped(
            f'''\
#include "{include_prefix_path}/constants.hpp"'''
        ),
        cpp_common.WARNING,
        cpp_common.generate_namespace_opening(namespace),
        Stripped(
            f"""\
std::size_t HashBytes::operator()(
{I}const std::vector<std::uint8_t>& bytes
) const {{
{I}std::size_t result = 0;
{I}const std::size_t prime = 31;
{I}const std::size_t size = bytes.size();
{I}for (std::size_t i = 0; i < size; ++i) {{
{II}result = bytes[i] + (result * prime);
{I}}}
{I}return result;
}}"""
        ),
    ]

    for constant in symbol_table.constants:
        block: Optional[Stripped]
        error: Optional[Error]

        if isinstance(constant, intermediate.ConstantPrimitive):
            block, error = _generate_constant_primitive_implementation(
                constant=constant
            )
        elif isinstance(constant, intermediate.ConstantSetOfPrimitives):
            block, error = _generate_constant_set_of_primitives_implementation(
                constant=constant
            )
        elif isinstance(constant, intermediate.ConstantSetOfEnumerationLiterals):
            (
                block,
                error,
            ) = _generate_constant_set_of_enumeration_literals_implementation(
                constant=constant
            )
        else:
            # noinspection PyTypeChecker
            assert_never(constant)

        if error is not None:
            errors.append(error)
            continue

        assert block is not None
        blocks.append(block)

    if len(errors) > 0:
        return None, errors

    blocks.extend(
        [
            cpp_common.generate_namespace_closing(namespace),
            cpp_common.WARNING,
        ]
    )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
