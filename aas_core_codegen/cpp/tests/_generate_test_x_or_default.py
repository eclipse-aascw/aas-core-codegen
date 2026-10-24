"""Generate code to test the ``XxxOrDefault`` methods."""
import io
from typing import List, Optional

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
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
    """Generate implementation to test the ``XxxOrDefault`` methods."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common.hpp"
#include "./common_examples.hpp"

#include <{include_prefix_path}/stringification.hpp>
#include <{include_prefix_path}/types.hpp>

#include <catch2/catch.hpp>

namespace our = {library_namespace};"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineLogDir() {{
{I}static our::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "XxxOrDefault";
{I}}}

{I}return *result;
}}"""
        ),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        cls_name = cpp_naming.class_name(cls.name)
        interface_name = cpp_naming.interface_name(cls.name)

        load_max = cpp_naming.function_name(Identifier(f"load_max_{cls.name}"))
        load_min = cpp_naming.function_name(Identifier(f"load_min_{cls.name}"))

        for method in cls.methods:
            if (
                not method.name.endswith("_or_default")
                or method.visibility is not intermediate.Visibility.PUBLIC
            ):
                continue

            assert method.returns is not None, (
                f"Unexpected no return type "
                f"from the method {method.name!r} of {cls.name!r}"
            )

            method_name = cpp_naming.method_name(method.name)

            serialization_snippet: Optional[Stripped] = None

            primitive_type = intermediate.try_primitive_type(method.returns)
            if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                serialization_snippet = Stripped(
                    f"""\
const std::string serialized(
{I}our::stringification::Base64Encode(
{II}instance->{method_name}()
{I})
);"""
                )
            elif primitive_type is intermediate.PrimitiveType.STR:
                # NOTE (mristin):
                # We use std::wstring's so we have to convert to a UTF-8.
                serialization_snippet = Stripped(
                    f"""\
const std::string serialized(
{I}our::common::WstringToUtf8(
{II}instance->{method_name}()
{I})
);"""
                )
            elif primitive_type is not None:
                serialization_snippet = Stripped(
                    f"""\
const std::string serialized(
{I}std::to_string(
{II}instance->{method_name}()
{I})
);"""
                )
            elif isinstance(
                method.returns,
                (
                    intermediate.JsonValueTypeAnnotation,
                    intermediate.JsonArrayTypeAnnotation,
                    intermediate.JsonObjectTypeAnnotation,
                ),
            ):
                # NOTE (mristin):
                # The objects of nlohmann::json keep their keys sorted, so
                # the dump does not depend on the order of the keys.
                serialization_snippet = Stripped(
                    f"""\
const std::string serialized(
{I}instance->{method_name}().dump()
);"""
                )
            else:
                if isinstance(
                    method.returns, intermediate.OurTypeAnnotation
                ) and isinstance(method.returns.our_type, intermediate.Enumeration):
                    serialization_snippet = Stripped(
                        f"""\
const std::string serialized(
{I}our::stringification::to_string(
{II}instance->{method_name}()
{I})
);"""
                    )

            if serialization_snippet is None:
                raise NotImplementedError(
                    "We have not implemented the serialization of the type "
                    f"{method.returns} in the tests. If you see this message, "
                    f"please revisit the testgen code and implement it."
                )

            blocks.append(
                Stripped(
                    f"""\
TEST_CASE("Test {method_name} on a min. {cls_name}") {{
{I}const std::shared_ptr<
{II}our::types::{interface_name}
{I}> instance(
{II}test::common::examples::{load_min}()
{I});

{I}const std::filesystem::path log_path(
{II}DetermineLogDir()
{III}/ "{cls_name}.{method_name}.min.log"
{I});

{I}{indent_but_first_line(serialization_snippet, I)}

{I}test::common::AssertContentEqualsExpectedOrRecord(
{II}serialized,
{II}log_path
{I});
}}"""
                )
            )

            blocks.append(
                Stripped(
                    f"""\
TEST_CASE("Test {method_name} on a max. {cls_name}") {{
{I}const std::shared_ptr<
{II}our::types::{interface_name}
{I}> instance(
{II}test::common::examples::{load_max}()
{I});

{I}const std::filesystem::path log_path(
{II}DetermineLogDir()
{III}/ "{cls_name}.{method_name}.max.log"
{I});

{I}{indent_but_first_line(serialization_snippet, I)}

{I}test::common::AssertContentEqualsExpectedOrRecord(
{II}serialized,
{II}log_path
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
