"""Generate code to test the jsonization of classes with descendants."""

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
    """Generate implementation to test the jsonization of classes with descendants."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common.hpp"
#include "./common_jsonization.hpp"
#include "./common_examples.hpp"

#include <{include_prefix_path}/jsonization.hpp>

#include <catch2/catch.hpp>

namespace our = {library_namespace};"""
        ),
    ]

    for cls in symbol_table.classes:
        if len(cls.concrete_descendants) == 0:
            continue

        # NOTE (mristin):
        # We can not de-serialize a JSON without a model type. Some classes indeed
        # lack a model type, although they are abstract. This is the case for
        # the classes where no meta-model property uses the abstract class, and only the
        # concrete descendants are used.
        if not cls.serialization.with_model_type:
            continue

        concrete_cls = cls.concrete_descendants[0]

        interface_name = cpp_naming.interface_name(cls.name)
        concrete_interface_name = cpp_naming.interface_name(concrete_cls.name)

        load_min = cpp_naming.function_name(Identifier(f"load_min_{concrete_cls.name}"))

        from_json = cpp_naming.function_name(Identifier(f"{cls.name}_from"))

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test the round-trip of an expected {interface_name}") {{
{I}const std::shared_ptr<
{II}our::types::{concrete_interface_name}
{I}> concrete_instance(
{II}test::common::examples::{load_min}()
{I});

{I}const nlohmann::json json = our::jsonization::Serialize(
{II}*concrete_instance
{I});

{I}our::common::expected<
{II}std::shared_ptr<
{III}our::types::{interface_name}
{II}>,
{II}our::jsonization::DeserializationError
{I}> instance = our::jsonization::{from_json}(
{II}json
{I});

{I}if (!instance.has_value()) {{
{II}INFO(
{III}our::common::Concat(
{IIII}"Failed to deserialize a {interface_name} "
{IIII}"from a minimal {concrete_interface_name}: ",
{IIII}our::common::WstringToUtf8(instance.error().path.ToWstring()),
{IIII}": ",
{IIII}our::common::WstringToUtf8(instance.error().cause)
{III})
{II})
{II}CHECK(instance.has_value());
{I}}}

{I}const nlohmann::json another_json = our::jsonization::Serialize(
{II}**instance
{I});

{I}const std::optional<
{II}std::string
{I}> patch_message = test::common::jsonization::CompareJsons(
{II}json,
{II}another_json
{I});
{I}if (patch_message.has_value()) {{
{II}INFO(
{III}our::common::Concat(
{IIII}"Failed to make a round-trip of a {interface_name} "
{IIII}"over a minimal {concrete_interface_name}: ",
{IIII}*patch_message
{IIII})
{III})
{III}CHECK(!patch_message.has_value());
{I}}}
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
