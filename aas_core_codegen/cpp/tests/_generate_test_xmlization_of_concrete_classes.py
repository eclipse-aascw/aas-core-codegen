"""Generate code to test the XML de/serialization of concrete classes."""
import io
from typing import Dict, List, Mapping, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


#: The lexical forms which no recorded example can hold, by the primitive they
#: belong to. A recorded example has to serialize back to itself, character for
#: character, so it can hold neither a value written in another form than it
#: was read nor one whose written form the targets spell differently.
_LEXICAL_CASES_BY_PRIMITIVE = {
    intermediate.PrimitiveType.FLOAT: [
        # NOTE (mristin):
        # A literal too large for a double is not an error: XSD rounds it to
        # an infinity, and one too small to zero.
        #
        # See: https://www.w3.org/TR/xmlschema11-2/#double
        ("1e400", "std::numeric_limits<double>::infinity()"),
        ("-1e400", "-std::numeric_limits<double>::infinity()"),
        ("1e-400", "0.0"),
        ("INF", "std::numeric_limits<double>::infinity()"),
        ("+INF", "std::numeric_limits<double>::infinity()"),
        ("-INF", "-std::numeric_limits<double>::infinity()"),
    ],
    intermediate.PrimitiveType.BYTEARRAY: [
        # NOTE (mristin):
        # ``xs:base64Binary`` admits whitespace *between* the characters and
        # not only around them, and an empty value stands for zero bytes.
        # Neither can be a recorded example: the first is written back without
        # the space, and the second as an empty element.
        #
        # See: https://www.w3.org/TR/xmlschema-2/#base64Binary
        ("SGk=", "std::vector<std::uint8_t>{72, 105}"),
        ("SG k=", "std::vector<std::uint8_t>{72, 105}"),
        ("S G k =", "std::vector<std::uint8_t>{72, 105}"),
        ("", "std::vector<std::uint8_t>{}"),
    ],
    intermediate.PrimitiveType.BOOL: [
        # NOTE (mristin):
        # ``xs:boolean`` spells the two values in four ways, not two.
        ("1", "true"),
        ("0", "false"),
        ("true", "true"),
        ("false", "false"),
    ],
}  # type: Mapping[intermediate.PrimitiveType, List[Tuple[str, str]]]


def _generate_lexical_tests(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the tests over the lexical forms which no example can hold."""
    cls = intermediate.first_class_of_only_required_primitives(symbol_table)
    if cls is None:
        return []

    prop_by_a_type = (
        dict()
    )  # type: Dict[intermediate.PrimitiveType, intermediate.Property]
    for prop in cls.properties:
        assert isinstance(prop.type_annotation, intermediate.PrimitiveTypeAnnotation)
        prop_by_a_type.setdefault(prop.type_annotation.a_type, prop)

    relevant = [
        (a_type, prop_by_a_type[a_type])
        for a_type in (
            intermediate.PrimitiveType.FLOAT,
            intermediate.PrimitiveType.BOOL,
            intermediate.PrimitiveType.BYTEARRAY,
        )
        if a_type in prop_by_a_type
    ]

    if len(relevant) == 0:
        return []

    interface_name = cpp_naming.interface_name(cls.name)
    cls_name_xml = naming.xml_class_name(cls.name)

    result = [
        Stripped(
            f"""\
/**
 * \\brief Read the first recorded example of {interface_name} with the content
 * of the element \\p xml_name replaced by \\p text.
 */
std::shared_ptr<aas::types::{interface_name}> ReadWith(
{I}const std::string& xml_name,
{I}const std::string& text
) {{
{I}// NOTE (mristin):
{I}// FindFilesBySuffixRecursively answers a deque, and it is already sorted,
{I}// which is what the round-trip test above relies on as well.
{I}const std::deque<std::filesystem::path> paths(
{II}test::common::FindFilesBySuffixRecursively(
{III}DetermineXmlDir()
{IIII}/ "Expected"
{IIII}/ {cpp_common.string_literal(cls_name_xml)},
{III}".xml"
{II})
{I});

{I}REQUIRE(!paths.empty());

{I}const std::string original(test::common::MustReadString(paths.front()));

{I}const std::size_t start(
{II}original.find(aas::common::Concat("<", xml_name, ">"))
{III}+ xml_name.size() + 2
{I});
{I}const std::size_t end(
{II}original.find(aas::common::Concat("</", xml_name, ">"))
{I});

{I}const std::string patched(
{II}original.substr(0, start) + text + original.substr(end)
{I});

{I}std::istringstream iss(patched);

{I}aas::common::expected<
{II}std::shared_ptr<aas::types::IClass>,
{II}aas::xmlization::DeserializationError
{I}> deserialized = aas::xmlization::From(iss);

{I}INFO(aas::common::Concat("De-serializing: ", patched))
{I}REQUIRE(deserialized.has_value());

{I}std::shared_ptr<aas::types::{interface_name}> casted(
{II}std::dynamic_pointer_cast<aas::types::{interface_name}>(*deserialized)
{I});
{I}REQUIRE(casted != nullptr);

{I}return casted;
}}"""
        )
    ]  # type: List[Stripped]

    for a_type, prop in relevant:
        prop_xml_name = naming.xml_property(prop.name)
        getter_name = cpp_naming.getter_name(prop.name)

        for a_text, expected in _LEXICAL_CASES_BY_PRIMITIVE[a_type]:
            title = f"Read {prop_xml_name} from {a_text}"

            result.append(
                Stripped(
                    f"""\
TEST_CASE({cpp_common.string_literal(title)}) {{
{I}std::shared_ptr<aas::types::{interface_name}> instance(
{II}ReadWith(
{III}{cpp_common.string_literal(prop_xml_name)},
{III}{cpp_common.string_literal(a_text)}
{II})
{I});

{I}REQUIRE(instance->{getter_name}() == {expected});
}}"""
                )
            )

    return result


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
    """Generate implementation to test the XML de/serialization of concrete classes."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "./common.hpp"
#include "./common_xmlization.hpp"

#include <{include_prefix_path}/xmlization.hpp>

#define CATCH_CONFIG_MAIN
#include <catch2/catch.hpp>

namespace aas = {library_namespace};"""
        ),
        Stripped(
            f"""\
void AssertRoundTrip(
{I}const std::filesystem::path& path
) {{
{I}std::shared_ptr<
{II}aas::types::IClass
{I}> deserialized(
{II}test::common::xmlization::MustDeserializeFile(path)
{I});

{I}std::stringstream ss;
{I}aas::xmlization::Serialize(*deserialized, {{}}, ss);

{I}std::string expected_xml = test::common::MustReadString(path);

{I}INFO(aas::common::Concat("XML round-trip on ", path.string()))
{I}REQUIRE(
{II}test::common::xmlization::CanonicalizeXml(expected_xml)
{III}== test::common::xmlization::CanonicalizeXml(ss.str())
{I});
}}"""
        ),
        Stripped(
            f"""\
void AssertDeserializationFailure(
{I}const std::filesystem::path& path,
{I}const std::filesystem::path& error_path
) {{
{I}std::ifstream ifs(path, std::ios::binary);

{I}aas::common::expected<
{II}std::shared_ptr<aas::types::IClass>,
{II}aas::xmlization::DeserializationError
{I}> deserialized = aas::xmlization::From(
{II}ifs
{I});

{I}if (deserialized.has_value()) {{
{II}INFO(
{III}aas::common::Concat(
{IIII}"Expected the de-serialization to fail on ",
{IIII}path.string(),
{IIII}", but the de-serialization succeeded"
{III})
{II})
{II}REQUIRE(!deserialized.has_value());
{I}}}

{I}test::common::AssertContentEqualsExpectedOrRecord(
{II}aas::common::Concat(
{III}aas::common::WstringToUtf8(
{IIII}deserialized.error().path.ToWstring()
{III}),
{III}": ",
{III}aas::common::WstringToUtf8(
{IIII}deserialized.error().cause
{III})
{II}),
{II}error_path
{I});
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineXmlDir() {{
{I}static aas::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "Xml";
{I}}}

{I}return *result;
}}"""
        ),
        Stripped(
            f"""\
const std::filesystem::path& DetermineErrorDir() {{
{I}static aas::common::optional<std::filesystem::path> result;
{I}if (!result.has_value()) {{
{II}result = test::common::DetermineTestDataDir() / "XmlizationError";
{I}}}

{I}return *result;
}}"""
        ),
    ]  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        xml_class_name = naming.xml_class_name(concrete_cls.name)

        cls_name = cpp_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test the round-trip of an expected {cls_name}") {{
{I}const std::deque<std::filesystem::path> paths(
{II}test::common::FindFilesBySuffixRecursively(
{III}DetermineXmlDir()
{IIII}/ "Expected"
{IIII}/ {cpp_common.string_literal(xml_class_name)},
{III}".xml"
{II})
{I});

{I}for (const std::filesystem::path &path : paths) {{
{II}AssertRoundTrip(path);
{I}}}
}}"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test the de-serialization failure on an unexpected {cls_name}") {{
{I}for (
{II}const std::filesystem::path& causeDir
{II}: test::common::ListSubdirectories(
{III}DetermineXmlDir()
{IIII}/ "Unexpected"
{IIII}/ "Unserializable"
{II})
{I}) {{
{II}for (
{III}const std::filesystem::path& path
{III}: test::common::FindFilesBySuffixRecursively(
{IIII}causeDir / {cpp_common.string_literal(xml_class_name)},
{IIII}".xml"
{III})
{II}) {{
{III}const std::filesystem::path parent(
{IIII}(
{IIIII}DetermineErrorDir()
{IIIII}/ std::filesystem::relative(path, DetermineXmlDir())
{IIII}).parent_path()
{III});

{III}const std::filesystem::path error_path(
{IIII}parent
{IIII}/ (path.filename().string() + ".error")
{III});

{III}AssertDeserializationFailure(
{IIII}path,
{IIII}error_path
{III});
{II}}}
{I}}}
}}"""
            )
        )

    duplicate_candidate = intermediate.first_class_with_a_required_property(
        symbol_table
    )
    if duplicate_candidate is not None:
        duplicate_cls, duplicate_prop = duplicate_candidate

        duplicate_cls_name_xml = naming.xml_class_name(duplicate_cls.name)

        open_tag = f"<{duplicate_prop.xml_name}>"
        close_tag = f"</{duplicate_prop.xml_name}>"
        self_closing_tag = f"<{duplicate_prop.xml_name}/>"
        root_close_tag = f"</{duplicate_cls_name_xml}>"

        blocks.append(
            Stripped(
                f"""\
TEST_CASE("Test the de-serialization failure on a duplicate property") {{
{I}const std::filesystem::path path(
{II}DetermineXmlDir()
{III}/ "Expected"
{III}/ {cpp_common.string_literal(duplicate_cls_name_xml)}
{III}/ "minimal.xml"
{I});

{I}const std::string original(test::common::MustReadString(path));

{I}// We cut the element of the property out of the recorded example and put it
{I}// in a second time, just before the closing tag of the instance.
{I}const std::size_t start(
{II}original.find({cpp_common.string_literal(open_tag)})
{I});

{I}std::string property;
{I}if (start != std::string::npos) {{
{II}const std::size_t end(
{III}original.find({cpp_common.string_literal(close_tag)}, start)
{II});
{II}property = original.substr(start, end + {len(close_tag)} - start);
{I}}} else {{
{II}// The element is written self-closing in the example, an empty list being
{II}// the usual reason. We write that very element out ourselves.
{II}property = {cpp_common.string_literal(self_closing_tag)};
{I}}}

{I}const std::size_t insertion_index(
{II}original.rfind({cpp_common.string_literal(root_close_tag)})
{I});

{I}INFO(aas::common::Concat("Looking for {root_close_tag} in ", path.string()))
{I}REQUIRE(insertion_index != std::string::npos);

{I}const std::string broken(
{II}original.substr(0, insertion_index)
{III}+ property
{III}+ original.substr(insertion_index)
{I});

{I}std::istringstream iss(broken);

{I}aas::common::expected<
{II}std::shared_ptr<aas::types::IClass>,
{II}aas::xmlization::DeserializationError
{I}> deserialized = aas::xmlization::From(iss);

{I}INFO(aas::common::Concat("De-serializing: ", broken))
{I}REQUIRE(!deserialized.has_value());
}}"""
            )
        )

    blocks.extend(_generate_lexical_tests(symbol_table))

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
