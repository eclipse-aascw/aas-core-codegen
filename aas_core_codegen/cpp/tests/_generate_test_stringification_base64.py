# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code to test the base64 encoding and decoding."""

import io

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.cpp import common as cpp_common
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
def generate_implementation(library_namespace: Stripped) -> str:
    """Generate implementation to test the base64 encoding and decoding."""
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            """\
/**
 * Test base64 encoding and decoding.
 */"""
        ),
        Stripped(
            f'''\
#include "{include_prefix_path}/stringification.hpp"'''
        ),
        Stripped(
            """\
#include <catch2/catch.hpp>"""
        ),
        Stripped(
            f"""\
namespace our = {library_namespace};"""
        ),
        Stripped(
            f"""\
std::string BytesToString(const std::vector<uint8_t>& bytes) {{
{I}std::string result;
{I}result.resize(bytes.size());
{I}for (size_t i = 0; i < bytes.size(); ++i
{II}) {{
{II}result[i] = bytes[i];
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
std::vector<uint8_t> StringToBytes(const std::string& text) {{
{I}std::vector<uint8_t> result;
{I}result.resize(text.size());
{I}for (size_t i = 0; i < text.size(); ++i
{II}) {{
{II}result[i] = text[i];
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
void AssertEncodeDecode(
{I}const std::string& text,
{I}const std::string& expected_encoded
) {{
{I}const std::string encoded = our::stringification::Base64Encode(
{II}StringToBytes(text)
{I});

{I}REQUIRE(
{II}expected_encoded
{III}== encoded
{I});

{I}our::common::expected<
{II}std::vector<std::uint8_t>,
{II}std::string
{I}> bytes = our::stringification::Base64Decode(encoded);

{I}REQUIRE(bytes.has_value());

{I}REQUIRE(
{II}BytesToString(bytes.value())
{III}== text
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test '' is encoded ''") {{
{I}AssertEncodeDecode(
{II}"",
{II}""
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test 'f' is encoded 'Zg=='") {{
{I}AssertEncodeDecode(
{II}"f",
{II}"Zg=="
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test 'fo' is encoded 'Zm8='") {{
{I}AssertEncodeDecode(
{II}"fo",
{II}"Zm8="
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test 'foo' is encoded 'Zm9v'") {{
{I}AssertEncodeDecode(
{II}"foo",
{II}"Zm9v"
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test 'foob' is encoded 'Zm9vYg=='") {{
{I}AssertEncodeDecode(
{II}"foob",
{II}"Zm9vYg=="
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test 'fooba' is encoded 'Zm9vYmE='") {{
{I}AssertEncodeDecode(
{II}"fooba",
{II}"Zm9vYmE="
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test 'foobar' is encoded 'Zm9vYmFy'") {{
{I}AssertEncodeDecode(
{II}"foobar",
{II}"Zm9vYmFy"
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test unexpected padding in the middle") {{
{I}const std::string encoded = "Zm9vYmFy";
{I}for (size_t i = 0; i < encoded.size() - 1; ++i
{II}) {{
{II}const std::string bad_encoded(
{III}encoded.substr(0, i)
{IIII}+ "="
{IIII}+ encoded.substr(i + 1, encoded.size() - i)
{II});

{II}our::common::expected<
{III}std::vector<std::uint8_t>,
{III}std::string
{II}> bytes = our::stringification::Base64Decode(bad_encoded);

{II}REQUIRE(!bytes.has_value());

{II}std::stringstream ss;
{II}ss
{III}<< "Expected a valid character from base64-encoded string, "
{III}<< "but got at index " << i << ": 61 (code: 61)";

{II}REQUIRE(
{III}bytes.error()
{IIII}== ss.str()
{II});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// NOTE (mristin):
// The following checks come from: https://eprint.iacr.org/2022/361.pdf
TEST_CASE("Test 'Hello' is encoded as 'SGVsbG8='") {{
{I}AssertEncodeDecode(
{II}"Hello",
{II}"SGVsbG8="
{I});
}}"""
        ),
        Stripped(
            f"""\
// NOTE (mristin):
// This is not a test case, but we merely document that there is a possible
// attack vector where different strings encode the *same* byte sequence.
TEST_CASE("Test that our implementation suffers from padding inconsistency of 'Hello' as 'SGVsbG9='") {{
{I}const std::string encoded = "SGVsbG9=";

{I}our::common::expected<
{II}std::vector<std::uint8_t>,
{II}std::string
{I}> bytes = our::stringification::Base64Decode(encoded);

{I}REQUIRE(bytes.has_value());

{I}REQUIRE(
{II}BytesToString(bytes.value())
{III}== "Hello"
{I});
}}"""
        ),
        Stripped(
            f"""\
void AssertDecode(
{I}const std::string& encoded,
{I}const std::vector<std::uint8_t>& expected_decoded
) {{
{I}our::common::expected<
{II}std::vector<std::uint8_t>,
{II}std::string
{I}> bytes = our::stringification::Base64Decode(encoded);

{I}INFO(encoded)
{I}REQUIRE(bytes.has_value());

{I}INFO(encoded)
{I}REQUIRE(bytes->size() == expected_decoded.size());

{I}for (size_t i = 0; i < bytes->size(); ++i
{II}) {{
{II}INFO(encoded + " is not correctly decoded at " + std::to_string(i))
{II}REQUIRE(bytes->at(i) == expected_decoded[i]);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
// NOTE (mristin):
// The following tests have been scraped from:
// https://github.com/rickkas7/Base64RK/blob/183d20e62b96ef9b0230c80c7a172715ca6f661e/test/unit-test/unit-test.cpp
TEST_CASE("Test table from rickkas7/Base64RK") {{
{I}AssertDecode(
{II}"",
{II}{{}}
{I});

{I}AssertDecode(
{II}"HA==",
{II}{{28}}
{I});

{I}AssertDecode(
{II}"rtA=",
{II}{{174, 208}}
{I});

{I}AssertDecode(
{II}"MuDQ",
{II}{{50, 224, 208}}
{I});

{I}AssertDecode(
{II}"LRLrBg==",
{II}{{45, 18, 235, 6}}
{I});

{I}AssertDecode(
{II}"dceZ3aA=",
{II}{{117, 199, 153, 221, 160}}
{I});

{I}AssertDecode(
{II}"jQy8MK0t",
{II}{{141, 12, 188, 48, 173, 45}}
{I});

{I}AssertDecode(
{II}"RY+UfdUDlA==",
{II}{{69, 143, 148, 125, 213, 3, 148}}
{I});

{I}AssertDecode(
{II}"+6KmPIGDLg0=",
{II}{{251, 162, 166, 60, 129, 131, 46, 13}}
{I});

{I}AssertDecode(
{II}"zyjM/k1HPQiA",
{II}{{207, 40, 204, 254, 77, 71, 61, 8, 128}}
{I});

{I}AssertDecode(
{II}"nJbVrnU7RtzSPw==",
{II}{{156, 150, 213, 174, 117, 59, 70, 220, 210, 63}}
{I});

{I}AssertDecode(
{II}"wDatE35UGvqnBTI=",
{II}{{192, 54, 173, 19, 126, 84, 26, 250, 167, 5, 50}}
{I});

{I}AssertDecode(
{II}"FAEPTeCNmS+6qsjj",
{II}{{20, 1, 15, 77, 224, 141, 153, 47, 186, 170, 200, 227}}
{I});

{I}AssertDecode(
{II}"VaaCqcF1wlHuQLTkfw==",
{II}{{85, 166, 130, 169, 193, 117, 194, 81, 238, 64, 180, 228, 127}}
{I});

{I}AssertDecode(
{II}"QYKREfdjniR1CMABweo=",
{II}{{65, 130, 145, 17, 247, 99, 158, 36, 117, 8, 192, 1, 193, 234}}
{I});

{I}AssertDecode(
{II}"CTf9s8td7Tr8yKiRczUf",
{II}{{9, 55, 253, 179, 203, 93, 237, 58, 252, 200, 168, 145, 115, 53, 31}}
{I});

{I}AssertDecode(
{II}"/kyMTRA0d+W64W21hiLlmesBEH4RDg0MivjmPEmAdMzP",
{II}{{254, 76, 140, 77, 16, 52, 119, 229, 186, 225, 109, 181, 134, 34,
{II} 229, 153, 235, 1, 16, 126, 17, 14, 13, 12, 138,
{II} 248, 230, 60, 73, 128, 116, 204, 207}}
{I});

{I}AssertDecode(
{II}"m5/QqN3YcQg6iE1dVjJQWw5mCjYCnsNLKPVUsXQ269l86M1xbyHn+/aIKafJ6hRT4UOD0mH"
{II}"CAfye/VSHdwH+C7bQ",
{II}{{155, 159, 208, 168, 221, 216, 113, 8, 58, 136, 77, 93, 86, 50, 80,
{II} 91, 14, 102, 10, 54, 2, 158, 195, 75, 40, 245,
{II} 84, 177, 116, 54, 235, 217, 124, 232, 205, 113, 111, 33, 231, 251, 246, 136, 41,
{II} 167, 201, 234, 20, 83, 225, 67,
{II} 131, 210, 97, 194, 1, 252, 158, 253, 84, 135, 119, 1, 254, 11, 182, 208}}
{I});

{I}AssertDecode(
{II}"ZSsh3WyA3d00CyimeMZPAI1/t+LF6DQdiAEQG9hHlfuDXhZ2Gf/Wd1u2y+RDFli0oSq2fbfv"
{II}"utgXCxGQfMmxA1NEg/k0vQIcSqzWdX7571oWzKHz6KZnlhTwPF27QznnAWbdwkyiCFlIlpL3tYbyzbMT"
{II}"m0ReUtY4AW9tTpvYSQdQ8w==",
{II}{{101, 43, 33, 221, 108, 128, 221, 221, 52, 11, 40, 166, 120, 198,
{II} 79, 0, 141, 127, 183, 226, 197, 232, 52, 29, 136,
{II} 1, 16, 27, 216, 71, 149, 251, 131, 94, 22, 118, 25, 255, 214, 119, 91, 182, 203,
{II} 228, 67, 22, 88, 180, 161, 42,
{II} 182, 125, 183, 239, 186, 216, 23, 11, 17, 144, 124, 201, 177, 3, 83, 68, 131,
{II} 249, 52, 189, 2, 28, 74, 172, 214,
{II} 117, 126, 249, 239, 90, 22, 204, 161, 243, 232, 166, 103, 150, 20, 240, 60, 93,
{II} 187, 67, 57, 231, 1, 102, 221, 194,
{II} 76, 162, 8, 89, 72, 150, 146, 247, 181, 134, 242, 205, 179, 19, 155, 68, 94, 82,
{II} 214, 56, 1, 111, 109, 78, 155,
{II} 216, 73, 7, 80, 243}}
{I});

{I}AssertDecode(
{II}"seCV0jbCe42d4GMBvXIl5vqVoZ6K4gUSg6nKgi5tZiNxx22yYon5ReOC6PZpZWHqeJcfKVo"
{II}"UD/Za1ieLVjROriNfP+Lxf6Tbroz/EXh2YYOFI+d110oObkYqbgcl6ovS4CRH40Sb7L89Uwu9WDzQA"
{II}"215IEepOn1wdBCZyEryWY2PGdNcs+Pft9sSNtBQ/QtMRZYEMO5JpRmFyFDPVLZA+5xM/3Dj65odv1b"
{II}"ZdtszJq0Gbw43ww0t7EK0J21uBy89Z2R1N1kjQGpqKu4lRhQIgCKDOHhnfZW2gtkmZhiqby9xT44Ep1"
{II}"AMrmZKgW3MDPzIX2Ez16mUv3Gb5JHrI/w1sQ==",
{II}{{177, 224, 149, 210, 54, 194, 123, 141, 157, 224, 99, 1, 189,
{II} 114, 37, 230, 250, 149, 161, 158, 138, 226, 5, 18,
{II} 131, 169, 202, 130, 46, 109, 102, 35, 113, 199, 109, 178, 98, 137, 249, 69, 227,
{II} 130, 232, 246, 105, 101, 97, 234,
{II} 120, 151, 31, 41, 90, 20, 15, 246, 90, 214, 39, 139, 86, 52, 78, 174, 35, 95, 63,
{II} 226, 241, 127, 164, 219, 174,
{II} 140, 255, 17, 120, 118, 97, 131, 133, 35, 231, 117, 215, 74, 14, 110, 70, 42,
{II} 110, 7, 37, 234, 139, 210, 224, 36,
{II} 71, 227, 68, 155, 236, 191, 61, 83, 11, 189, 88, 60, 208, 3, 109, 121, 32, 71,
{II} 169, 58, 125, 112, 116, 16, 153,
{II} 200, 74, 242, 89, 141, 143, 25, 211, 92, 179, 227, 223, 183, 219, 18, 54, 208,
{II} 80, 253, 11, 76, 69, 150, 4, 48,
{II} 238, 73, 165, 25, 133, 200, 80, 207, 84, 182, 64, 251, 156, 76, 255, 112, 227,
{II} 235, 154, 29, 191, 86, 217, 118,
{II} 219, 51, 38, 173, 6, 111, 14, 55, 195, 13, 45, 236, 66, 180, 39, 109, 110, 7,
{II} 47, 61, 103, 100, 117, 55, 89, 35,
{II} 64, 106, 106, 42, 238, 37, 70, 20, 8, 128, 34, 131, 56, 120, 103, 125, 149,
{II} 182, 130, 217, 38, 102, 24, 170, 111,
{II} 47, 113, 79, 142, 4, 167, 80, 12, 174, 102, 74, 129, 109, 204, 12, 252, 200,
{II} 95, 97, 51, 215, 169, 148, 191, 113,
{II} 155, 228, 145, 235, 35, 252, 53, 177}}
{I});
}}"""
        ),
        cpp_common.WARNING,
    ]

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
