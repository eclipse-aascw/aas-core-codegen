"""Generate code to test ``Descent`` and ``DescentOnce`` iterations."""


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
    """Generate implementation to test ``Descent`` and ``DescentOnce`` iterations."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common.hpp"
#include "./common_examples.hpp"
#include "./common_xmlization.hpp"

#include <{include_prefix_path}/iteration.hpp>
#include <{include_prefix_path}/stringification.hpp>
#include <{include_prefix_path}/types.hpp>

#include <catch2/catch.hpp>

#include <deque>

namespace our = {library_namespace};"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineXmlDir() {{
{I}static our::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "Xml";
{I}}}

{I}return *result;
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineDescentDir() {{
{I}static our::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "Descent";
{I}}}

{I}return *result;
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineDescentOnceDir() {{
{I}static our::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "DescentOnce";
{I}}}

{I}return *result;
}}"""
        ),
        Stripped(
            f"""\
void AssertOrRerecordDescent(
{I}const std::filesystem::path& xml_path,
{I}const std::filesystem::path& trace_path
) {{
{I}std::shared_ptr<
{II}our::types::IClass
{I}> instance(
{II}test::common::xmlization::MustDeserializeFile(xml_path)
{I});

{I}std::deque<std::wstring> parts;

{I}for (
{II}const std::shared_ptr<our::types::IClass>& something
{II}: our::iteration::Descent(instance)
{I}) {{
{II}parts.emplace_back(test::common::TraceMark(*something));
{II}parts.push_back(L"\\n");
{I}}}

{I}test::common::AssertContentEqualsExpectedOrRecord(
{II}our::common::WstringToUtf8(
{III}test::common::JoinWstrings(parts, L"")
{II}),
{II}trace_path
{I});
}}"""
        ),
        Stripped(
            f"""\
void AssertOrRerecordDescentOnce(
{I}const std::shared_ptr<our::types::IClass>& instance,
{I}const std::filesystem::path& trace_path
) {{
{I}std::deque<std::wstring> parts;

{I}for (
{II}const std::shared_ptr<our::types::IClass>& something
{II}: our::iteration::DescentOnce(instance)
{I}) {{
{II}parts.emplace_back(test::common::TraceMark(*something));
{II}parts.push_back(L"\\n");
{I}}}

{I}test::common::AssertContentEqualsExpectedOrRecord(
{II}our::common::WstringToUtf8(
{III}test::common::JoinWstrings(parts, L"")
{II}),
{II}trace_path
{I});
}}"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        xml_class_name = naming.xml_class_name(concrete_cls.name)

        cls_name = cpp_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test Descent over an {cls_name}") {{
{I}const std::deque<std::filesystem::path> paths(
{II}test::common::FindFilesBySuffixRecursively(
{III}DetermineXmlDir()
{IIII}/ "Expected"
{IIII}/ {cpp_common.string_literal(xml_class_name)},
{III}".xml"
{II})
{I});

{I}for (const std::filesystem::path& path : paths) {{
{II}const std::filesystem::path parent(
{III}(
{IIII}DetermineDescentDir()
{IIIII}/ std::filesystem::relative(path, DetermineXmlDir())
{III}).parent_path()
{II});

{II}const std::filesystem::path trace_path(
{III}parent
{IIII}/ (path.filename().string() + ".trace")
{II});

{II}AssertOrRerecordDescent(path, trace_path);
{I}}}
}}"""
            )
        )

        interface_name = cpp_naming.interface_name(concrete_cls.name)
        load_max = cpp_naming.function_name(Identifier(f"load_max_{concrete_cls.name}"))

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test DescentOnce over an {cls_name}") {{
{I}const std::shared_ptr<
{II}our::types::{interface_name}
{I}> instance(
{II}test::common::examples::{load_max}()
{I});

{I}const std::filesystem::path trace_path(
{II}DetermineDescentOnceDir()
{III}/ "Max{cls_name}.trace"
{I});

{I}AssertOrRerecordDescentOnce(instance, trace_path);
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
