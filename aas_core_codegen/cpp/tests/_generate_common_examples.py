# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code to load minimal and maximal examples."""


import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    Identifier,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_load_min_max_definitions(
    cls: intermediate.ConcreteClass, library_namespace: Stripped
) -> List[Stripped]:
    """Generate the def. of loading minimal and maximal example, respectively."""
    interface_name = cpp_naming.interface_name(cls.name)

    load_min = cpp_naming.function_name(Identifier(f"load_min_{cls.name}"))
    load_max = cpp_naming.function_name(Identifier(f"load_max_{cls.name}"))

    return [
        Stripped(
            f"""\
/**
 * Load a minimal example of {interface_name} by
 * de-serializing it from an XML file.
 */
std::shared_ptr<
{I}{library_namespace}::types::{interface_name}
> {load_min}();"""
        ),
        Stripped(
            f"""\
/**
 * Load a maximal example of {interface_name} by
 * de-serializing it from an XML file.
 */
std::shared_ptr<
{I}{library_namespace}::types::{interface_name}
> {load_max}();"""
        ),
    ]


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
    """Generate header to load minimal and maximal examples."""
    include_guard_var = cpp_common.include_guard_var(Stripped("test::common::examples"))

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        # NOTE (mristin):
        # We de-serialize from an XML file instead of JSON to avoid problems
        # with missing `modelType` JSON properties for some classes such as
        # `Abstract_lang_string`.
        Stripped(
            """\
/**
* Load minimal and maximal examples from an XML file.
*/"""
        ),
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}

#include <{include_prefix_path}/types.hpp>

namespace test {{
namespace common {{
namespace examples {{"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        blocks.extend(
            _generate_load_min_max_definitions(
                cls=concrete_cls, library_namespace=library_namespace
            )
        )

    blocks.extend(
        [
            Stripped(
                f"""\
}}  // namespace examples
}}  // namespace common
}}  // namespace test

#endif // {include_guard_var}"""
            ),
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


def _generate_static_type_name(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the specialization of a templated struct to retrieve the type name."""
    interface_name = cpp_naming.interface_name(cls.name)

    return Stripped(
        f"""\
template<>
struct StaticTypeName<
{I}our::types::{interface_name}
> {{
  static const char* name;
}};
const char* StaticTypeName<
{I}our::types::{interface_name}
>::name = "{interface_name}";"""
    )


def _generate_load_min_max_implementations(
    cls: intermediate.ConcreteClass,
) -> List[Stripped]:
    """Generate the impl. of loading minimal and maximal example, respectively."""
    interface_name = cpp_naming.interface_name(cls.name)

    load = cpp_naming.function_name(Identifier(f"load_{cls.name}"))
    load_min = cpp_naming.function_name(Identifier(f"load_min_{cls.name}"))
    load_max = cpp_naming.function_name(Identifier(f"load_max_{cls.name}"))

    xml_class_name = naming.xml_class_name(cls.name)

    return [
        Stripped(
            f"""\
std::shared_ptr<
{I}our::types::{interface_name}
> {load}(
{I}const std::filesystem::path& path
) {{
{I}

{I}std::shared_ptr<
{II}our::types::IClass
{I}> abstract = test::common::xmlization::MustReadInstance(
{II}path
{I});

{I}std::shared_ptr<
{II}our::types::{interface_name}
{I}> instance(
{II}std::dynamic_pointer_cast<
{III}our::types::{interface_name}
{II}>(
{III}abstract
{II})
{I});

{I}if (instance == nullptr) {{
{II}throw std::runtime_error(
{III}our::common::Concat(
{IIII}"Failed to cast the instance to {interface_name} from ",
{IIII}path.string()
{III})
{II});
{I}}}

{I}return instance;
}}"""
        ),
        Stripped(
            f"""\
std::shared_ptr<
{I}our::types::{interface_name}
> {load_min}() {{
{I}const std::filesystem::path path(
{II}test::common::DetermineTestDataDir()
{III}/ "Xml"
{III}/ "Expected"
{III}/ {cpp_common.string_literal(xml_class_name)}
{III}/ "minimal.xml"
{I});

{I}return {load}(
{II}path
{I});
}}"""
        ),
        Stripped(
            f"""\
std::shared_ptr<
{I}our::types::{interface_name}
> {load_max}() {{
{I}const std::filesystem::path path(
{II}test::common::DetermineTestDataDir()
{III}/ "Xml"
{III}/ "Expected"
{III}/ {cpp_common.string_literal(xml_class_name)}
{III}/ "maximal.xml"
{I});

{I}return {load}(
{II}path
{I});
}}"""
        ),
    ]


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
    """Generate implementation to load minimal and maximal examples."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common.hpp"
#include "./common_examples.hpp"
#include "./common_xmlization.hpp"

#include <{include_prefix_path}/iteration.hpp>
#include <{include_prefix_path}/stringification.hpp>

#include <filesystem>

namespace our = {library_namespace};

namespace test {{
namespace common {{
namespace examples {{"""
        ),
        Stripped(
            """\
template<typename T>
struct StaticTypeName;"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        blocks.append(_generate_static_type_name(concrete_cls))

    for concrete_cls in symbol_table.concrete_classes:
        blocks.extend(_generate_load_min_max_implementations(cls=concrete_cls))

    blocks.extend(
        [
            Stripped(
                """\
}  // namespace examples
}  // namespace common
}  // namespace test"""
            ),
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
