"""Generate code to test the dispatch of xmlization for abstract classes."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
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
    INDENT5 as IIIII,
)


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
    """Generate implementation to test the dispatch of xmlization for abstract classes."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common_examples.hpp"

#include <{include_prefix_path}/xmlization.hpp>

#include <catch2/catch.hpp>

namespace our = {library_namespace};"""
        ),
    ]

    for cls in symbol_table.classes:
        if len(cls.concrete_descendants) == 0:
            continue

        concrete_cls = cls.concrete_descendants[0]

        interface_name = cpp_naming.interface_name(cls.name)
        concrete_interface_name = cpp_naming.interface_name(concrete_cls.name)

        load_min_concrete = cpp_naming.function_name(
            Identifier(f"load_min_{concrete_cls.name}")
        )

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test the round-trip of an expected {interface_name}") {{
{I}const std::shared_ptr<
{II}our::types::{concrete_interface_name}
{I}> original_instance(
{II}test::common::examples::{load_min_concrete}()
{I});

{I}std::stringstream ss;
{I}our::xmlization::Serialize(
{II}*original_instance,
{II}{{}},
{II}ss
{I});

{I}const std::string original_xml = ss.str();

{I}ss.seekp(0);

{I}our::common::expected<
{II}std::shared_ptr<our::types::IClass>,
{II}our::xmlization::DeserializationError
{I}> deserialized = our::xmlization::From(
{II}ss
{I});

{I}if (!deserialized.has_value()) {{
{II}INFO(
{III}our::common::Concat(
{IIII}"Failed to make the round-trip Serialize-Deserialize "
{IIII}"a minimal instance of {concrete_interface_name}: ",
{IIII}our::common::WstringToUtf8(
{IIIII}deserialized.error().path.ToWstring()
{IIII}),
{IIII}": ",
{IIII}our::common::WstringToUtf8(
{IIIII}deserialized.error().cause
{IIII})
{III})
{II})
{II}REQUIRE(deserialized.has_value());
{I}}}

{I}std::shared_ptr<
{II}our::types::{interface_name}
{I}> abstract = std::dynamic_pointer_cast<
{II}our::types::{interface_name}
{I}>(deserialized.value());

{I}std::stringstream another_ss;
{I}our::xmlization::Serialize(
{II}*abstract,
{II}{{}},
{II}another_ss
{I});

{I}INFO(
{II}"Original XML and the XML at the end of "
{II}"the chain Serialize-Deserialize-Serialize for "
{II}"a minimal instance of {concrete_interface_name} "
{II}"serialized as {interface_name} "
{II}"must coincide"
{I})
{I}REQUIRE(
{II}original_xml
{II}== another_ss.str()
{I});
}}"""
            )
        )

    blocks.append(cpp_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
