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


if __name__ == "__main__":
    unittest.main()
