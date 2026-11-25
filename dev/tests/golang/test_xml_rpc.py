# SPDX-FileCopyrightText: 2026 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

import unittest

from aas_core_codegen.common import Stripped
from aas_core_codegen.golang import tests as golang_tests
import tests.common


class TestGenerateXmlRpcTest(unittest.TestCase):
    def test_custom_xml_property_name(self) -> None:
        model_path = next(
            path
            for path in tests.common.COMMON_META_MODEL_PATHS
            if path.stem == "json_types"
        )
        source = model_path.read_text(encoding="utf-8")
        source = source.replace(
            "from typing import Optional", "from typing import Annotated, Optional"
        ).replace(
            "import JSONArray, JSONObject, JSONValue",
            "import JSONArray, JSONObject, JSONValue, xml_name",
        )
        source = source.replace(
            "    value: JSONValue\n",
            '    value: Annotated[JSONValue, xml_name("payload")]\n',
        )
        symbol_table = tests.common.must_translate_source_to_intermediate(source)
        code = golang_tests.generate_xml_rpc_test(
            symbol_table=symbol_table, repo_url=Stripped("github.com/dummy-works/dummy")
        )
        self.assertIn('<something xmlns=\\"https://dummy.com\\"><payload>', code)
        self.assertIn("</payload></something>", code)
        self.assertNotIn('<something xmlns=\\"https://dummy.com\\"><value>', code)

    def test_enum_tuple_siblings_are_xml_safe(self) -> None:
        model_path = next(
            path
            for path in tests.common.COMMON_META_MODEL_PATHS
            if path.stem == "json_types_in_collections"
        )
        source = model_path.read_text(encoding="utf-8")
        source = "from enum import Enum\n" + source
        source = source.replace(
            "class Something(DBC):",
            "class Mode(Enum):\n"
            '    Bad = "\\v"\n'
            '    Good = "ok"\n\n\n'
            "class Something(DBC):",
        ).replace(
            "Tuple[str, JSONValue, JSONArray, JSONObject[str]]",
            "Tuple[Mode, JSONValue, JSONArray, JSONObject[str], Mode]",
        )
        symbol_table = tests.common.must_translate_source_to_intermediate(source)
        code = golang_tests.generate_xmlization_test_common_test(
            symbol_table=symbol_table, repo_url=Stripped("github.com/dummy-works/dummy")
        )
        tuple_examples = "\n".join(
            line
            for line in code.splitlines()
            if '"Something.tuple_with_json/tuple[' in line
        )
        self.assertIn("<v1>text</v1><v2>", tuple_examples)
        self.assertIn("</v4><v5>text</v5>", tuple_examples)
        self.assertNotIn(r"\v", tuple_examples)


if __name__ == "__main__":
    unittest.main()
