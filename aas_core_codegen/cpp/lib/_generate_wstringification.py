"""Generate code for wstring de/serialization of enumerations."""

import io
from typing import List

from icontract import ensure

import aas_core_codegen.naming
from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.cpp import (
    common as cpp_common,
    naming as cpp_naming,
)
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_model_type_from_wstring_definition() -> List[Stripped]:
    """Generate the definition of translation of a model type from wstring."""
    enum_name = cpp_naming.enum_name(Identifier("Model_type"))
    from_wstring = cpp_naming.function_name(Identifier("model_type_from_wstring"))
    must_from_wstring = cpp_naming.function_name(
        Identifier("must_model_type_from_wstring")
    )

    return [
        Stripped(
            f"""\
/**
 * Try to parse the \\p text as a model type literal.
 *
 * \\param text to be parsed
 * \\return literal, or nothing, if \\p text invalid
 */
common::optional<types::{enum_name}> {from_wstring}(
{I}const std::wstring& text
);"""
        ),
        Stripped(
            f"""\
/**
 * Parse the \\p text as a model type literal.
 *
 * \\param text to be parsed
 * \\return literal
 * \\throw std::invalid_argument if \\p text invalid
 */
types::{enum_name} {must_from_wstring}(
{I}const std::wstring& text
);"""
        ),
    ]


def _generate_model_type_from_wstring_implementation(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the implementation of translation of a model type from wstring."""
    blocks: List[Stripped] = []

    # region Map

    enum_name = cpp_naming.enum_name(Identifier("Model_type"))

    items: List[str] = []
    for cls in symbol_table.concrete_classes:
        literal_name = cpp_naming.enum_literal_name(cls.name)

        literal_value = cpp_common.wstring_literal(
            aas_core_codegen.naming.json_model_type(cls.name)
        )

        items.append(
            Stripped(
                f"""\
{{
{I}{literal_value},
{I}types::{enum_name}::{literal_name}
}}"""
            )
        )

    map_name = cpp_naming.constant_name(Identifier("model_type_from_wstring_map"))

    items_joined = ",\n".join(items)

    blocks.append(
        Stripped(
            f"""\
const std::unordered_map<
{I}std::wstring,
{I}types::{enum_name}
> {map_name} = {{
{I}{indent_but_first_line(items_joined, I)}
}};"""
        )
    )

    # endregion

    # region From function

    from_wstring = cpp_naming.function_name(Identifier("model_type_from_wstring"))

    blocks.append(
        Stripped(
            f"""\
common::optional<types::{enum_name}> {from_wstring}(
{I}const std::wstring& text
) {{
{I}const auto it = {map_name}.find(
{II}text
{I});
{I}if (it == {map_name}.end()) {{
{II}return {{}};
{I}}}
{I}return it->second;
}}"""
        )
    )

    # endregion

    # region Must-from function

    must_from_wstring = cpp_naming.function_name(
        Identifier("must_model_type_from_wstring")
    )

    blocks.append(
        Stripped(
            f"""\
types::{enum_name} {must_from_wstring}(
{I}const std::wstring& text
) {{
{I}const auto it = {map_name}.find(
{II}text
{I});
{I}if (it == {map_name}.end()) {{
{II}throw std::invalid_argument(
{III}common::WstringToUtf8(
{IIII}common::Concat(
{IIIII}L"Unexpected {enum_name} literal: ",
{IIIII}text
{IIII})
{III})
{II});
{I}}}
{I}return it->second;
}}"""
        )
    )

    # endregion

    return blocks


def _generate_model_type_to_wstring_definition() -> Stripped:
    """Generate the definition for translating a wstring to a model type."""
    enum_name = cpp_naming.enum_name(Identifier("Model_type"))

    model_type_arg = cpp_naming.argument_name(Identifier("model_type"))

    # NOTE (mristin):
    # We use ``to_wstring`` naming to resemble the functions in standard library.
    return Stripped(
        f"""\
/**
 * Translate the enumeration literal \\p {model_type_arg} to text.
 *
 * \\param {model_type_arg} to be converted into text
 * \\return text representation of \\p {model_type_arg}
 * \\throw std::invalid_argument if \\p {model_type_arg} invalid
 */
std::wstring to_wstring(
{I}types::{enum_name} {model_type_arg}
);"""
    )


def _generate_model_type_to_wstring_implementation(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the implementation for translating a wstring to a model type."""
    enum_name = cpp_naming.enum_name(Identifier("Model_type"))

    case_blocks: List[Stripped] = []
    for cls in symbol_table.concrete_classes:
        literal_name = cpp_naming.enum_literal_name(cls.name)
        literal_value = cpp_common.wstring_literal(
            aas_core_codegen.naming.json_model_type(cls.name)
        )

        case_blocks.append(
            Stripped(
                f"""\
case types::{enum_name}::{literal_name}:
return {literal_value};"""
            )
        )

    model_type_arg = cpp_naming.argument_name(Identifier("model_type"))

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::invalid_argument(
{II}common::Concat(
{III}"Unexpected {enum_name} literal: ",
{III}std::to_string(
{IIII}static_cast<std::uint32_t>({model_type_arg})
{III})
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    # NOTE (mristin):
    # We use ``to_wstring`` naming to resemble the functions in standard library.
    return Stripped(
        f"""\
std::wstring to_wstring(
{I}types::{enum_name} {model_type_arg}
) {{
{I}switch ({model_type_arg}) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}}
}}"""
    )


def _generate_enum_from_wstring_definition(
    enum: intermediate.Enumeration,
) -> List[Stripped]:
    """Generate the definition of translation of an enum from wstring."""
    enum_name = cpp_naming.enum_name(enum.name)
    from_wstring = cpp_naming.function_name(Identifier(f"{enum.name}_from_wstring"))
    must_from_wstring = cpp_naming.function_name(
        Identifier(f"must_{enum.name}_from_wstring")
    )

    return [
        Stripped(
            f"""\
/**
 * Try to parse the \\p text as a literal of
 * types::{enum_name}.
 *
 * \\param text to be parsed
 * \\return literal, or nothing, if \\p text invalid
 */
common::optional<types::{enum_name}> {from_wstring}(
{I}const std::wstring& text
);"""
        ),
        Stripped(
            f"""\
/**
 * Parse the \\p text as a literal of
 * types::{enum_name}.
 *
 * \\param text to be parsed
 * \\return literal
 * \\throw std::invalid_argument if \\p text invalid
 */
types::{enum_name} {must_from_wstring}(
{I}const std::wstring& text
);"""
        ),
    ]


def _generate_enum_from_wstring_implementation(
    enum: intermediate.Enumeration,
) -> List[Stripped]:
    """Generate the implementation of translation of an  enum from wstring."""
    blocks: List[Stripped] = []

    # region Map

    enum_name = cpp_naming.enum_name(enum.name)

    items: List[str] = []
    for literal in enum.literals:
        literal_name = cpp_naming.enum_literal_name(literal.name)
        literal_value = cpp_common.wstring_literal(literal.value)

        items.append(
            Stripped(
                f"""\
{{
{I}{literal_value},
{I}types::{enum_name}::{literal_name}
}}"""
            )
        )

    map_name = cpp_naming.constant_name(Identifier(f"{enum.name}_from_wstring_map"))

    items_joined = ",\n".join(items)

    blocks.append(
        Stripped(
            f"""\
const std::unordered_map<
{I}std::wstring,
{I}types::{enum_name}
> {map_name} = {{
{I}{indent_but_first_line(items_joined, I)}
}};"""
        )
    )

    # endregion

    # region From function

    from_wstring = cpp_naming.function_name(Identifier(f"{enum.name}_from_wstring"))

    blocks.append(
        Stripped(
            f"""\
common::optional<types::{enum_name}> {from_wstring}(
{I}const std::wstring& text
) {{
{I}const auto it = {map_name}.find(
{II}text
{I});
{I}if (it == {map_name}.end()) {{
{II}return {{}};
{I}}}
{I}return it->second;
}}"""
        )
    )

    # endregion

    # region Must-from function

    must_from_wstring = cpp_naming.function_name(
        Identifier(f"must_{enum.name}_from_wstring")
    )

    blocks.append(
        Stripped(
            f"""\
types::{enum_name} {must_from_wstring}(
{I}const std::wstring& text
) {{
{I}const auto it = {map_name}.find(
{II}text
{I});
{I}if (it == {map_name}.end()) {{
{II}throw std::invalid_argument(
{III}common::WstringToUtf8(
{IIII}common::Concat(
{IIIII}L"Unexpected {enum_name} literal: ",
{IIIII}text
{IIII})
{III})
{II});
{I}}}
{I}return it->second;
}}"""
        )
    )

    # endregion

    return blocks


def _generate_enum_to_wstring_definition(enum: intermediate.Enumeration) -> Stripped:
    """Generate the definition for translating a wstring to an enum literal."""
    enum_name = cpp_naming.enum_name(enum.name)

    literal_arg = cpp_naming.argument_name(Identifier("literal"))

    # NOTE (mristin):
    # We use ``to_wstring`` naming to resemble the functions in standard library.
    return Stripped(
        f"""\
/**
 * Translate the enumeration literal \\p {literal_arg}
 * of types::{enum_name} to text.
 *
 * \\param {literal_arg} to be converted into text
 * \\return text representation of \\p {literal_arg}
 * \\throw std::invalid_argument if \\p {literal_arg} invalid
 */
std::wstring to_wstring(
{I}types::{enum_name} {literal_arg}
);"""
    )


def _generate_enum_to_wstring_implementation(
    enum: intermediate.Enumeration,
) -> Stripped:
    """Generate the implementation for translating a wstring to an enum literal."""
    enum_name = cpp_naming.enum_name(enum.name)

    case_blocks: List[Stripped] = []
    for literal in enum.literals:
        literal_name = cpp_naming.enum_literal_name(literal.name)
        literal_value = cpp_common.wstring_literal(literal.value)

        case_blocks.append(
            Stripped(
                f"""\
case types::{enum_name}::{literal_name}:
{I}return {literal_value};"""
            )
        )

    literal_arg = cpp_naming.argument_name(Identifier("literal"))

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::invalid_argument(
{II}common::Concat(
{III}"Unexpected {enum_name} literal: ",
{III}std::to_string(
{IIII}static_cast<std::uint32_t>({literal_arg})
{III})
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    # NOTE (mristin):
    # We use ``to_wstring`` naming to resemble the functions in standard library.
    return Stripped(
        f"""\
std::wstring to_wstring(
{I}types::{enum_name} {literal_arg}
) {{
{I}switch ({literal_arg}) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}}
}}"""
    )


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate header for wstring de/serialization of enumerations."""
    namespace = Stripped(f"{library_namespace}::wstringification")

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
#include "{include_prefix_path}/common.hpp"
#include "{include_prefix_path}/types.hpp"

#pragma warning(push, 0)
#include <string>
#include <vector>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            """\
/**
 * \\defgroup wstringification De/wstringify to and from wstrings (where applicable).
 * @{
 */
namespace wstringification {"""
        ),
        *_generate_model_type_from_wstring_definition(),
        _generate_model_type_to_wstring_definition(),
    ]

    for enum in symbol_table.enumerations:
        blocks.extend(_generate_enum_from_wstring_definition(enum=enum))
        blocks.append(_generate_enum_to_wstring_definition(enum=enum))

    blocks.extend(
        [
            Stripped(
                """\
}  // namespace wstringification
/**@}*/"""
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

    return writer.getvalue()


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate implementation for wstring de/serialization of enumerations."""
    namespace = Stripped(f"{library_namespace}::wstringification")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/wstringification.hpp"

#pragma warning(push, 0)
#include <unordered_map>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        *_generate_model_type_from_wstring_implementation(symbol_table=symbol_table),
        _generate_model_type_to_wstring_implementation(symbol_table=symbol_table),
    ]

    for enum in symbol_table.enumerations:
        blocks.extend(_generate_enum_from_wstring_implementation(enum=enum))
        blocks.append(_generate_enum_to_wstring_implementation(enum=enum))

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

    return writer.getvalue()


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
