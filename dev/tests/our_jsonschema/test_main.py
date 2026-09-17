# pylint: disable=missing-docstring

import json
import os
import pathlib
import unittest
import warnings
from typing import Optional

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    # NOTE (mristin):
    # We need to disable warnings. Jsonschema package at the latest version (4.4.0) has
    # a problem with JSON schema draft 2019-09 and crashes with an recursion error,
    # see: https://github.com/python-jsonschema/jsonschema/issues/847.
    #
    # We revert back to jsonschema 3.2.0, which can not handle 2019-09, but still seems
    # to validate correctly our examples.
    import jsonschema

import aas_core_codegen.main
import aas_core_codegen.jsonschema.main


class Test_examples(unittest.TestCase):
    def test_examples_comply_with_schema(self) -> None:
        repo_dir = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent.parent

        expected_dir = (
            repo_dir / "dev" / "test_data" / "main" / "jsonschema" / "expected"
        )
        assert expected_dir.exists() and expected_dir.is_dir(), expected_dir

        for case_dir in sorted(expected_dir.iterdir()):
            assert case_dir.is_dir(), case_dir

            schema_pth = case_dir / "expected_output" / "schema.json"

            with schema_pth.open("rt", encoding="utf-8") as fid:
                schema = json.load(fid)

            expected_dir = case_dir / "examples" / "Expected"

            if expected_dir.exists():
                for data_pth in sorted(expected_dir.glob("**/*.json")):
                    with data_pth.open("rt", encoding="utf-8") as fid:
                        instance = json.load(fid)

                    try:
                        jsonschema.validate(instance=instance, schema=schema)
                    except jsonschema.ValidationError as err:
                        raise AssertionError(
                            f"Failed to validate {data_pth} against {schema_pth}"
                        ) from err

            unexpected_dir = case_dir / "examples" / "Unexpected"

            if unexpected_dir.exists():
                for data_pth in sorted(unexpected_dir.glob("**/*.json")):
                    with data_pth.open("rt", encoding="utf-8") as fid:
                        instance = json.load(fid)

                    validation_error = (
                        None
                    )  # type: Optional[jsonschema.ValidationError]
                    try:
                        jsonschema.validate(instance=instance, schema=schema)
                    except jsonschema.ValidationError as err:
                        validation_error = err

                    if validation_error is None:
                        raise AssertionError(
                            f"Expected validation error on {data_pth} "
                            f"against {schema_pth}, but got no error"
                        )


class Test_pattern_transpilation(unittest.TestCase):
    def test_unescaped_above_ascii_character_in_bmp(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16("\ud7ff")
        self.assertEqual("\ud7ff", pattern)

    def test_escaped_above_ascii_character_in_bmp(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16("\\ud7ff")
        self.assertEqual("\\ud7ff", pattern)

    def test_unescaped_range_in_bmp(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16(
            "[\x20-\uD7FF]"
        )
        self.assertEqual("[\x20-\uD7FF]", pattern)

    def test_escaped_range_in_bmp(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16(
            "[\\x20-\\ud7ff]"
        )
        self.assertEqual("[\\x20-\\ud7ff]", pattern)

    def test_escaped_range_in_bmp_always_lowercase(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16(
            "[\\x20-\\uD7FF]"
        )
        self.assertEqual("[\\x20-\\ud7ff]", pattern)

    def test_unescaped_above_bmp(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16(
            "[\U00010000-\U0010FFFF]"
        )
        self.assertEqual(
            "(\\ud800[\\udc00-\\udfff]|[\\ud801-\\udbfe][\\udc00-\\udfff]"
            "|\\udbff[\\udc00-\\udfff])",
            pattern,
        )

    def test_escaped_above_bmp(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16(
            "[\\U00010000-\\U0010FFFF]"
        )
        self.assertEqual(
            "(\\ud800[\\udc00-\\udfff]|[\\ud801-\\udbfe][\\udc00-\\udfff]"
            "|\\udbff[\\udc00-\\udfff])",
            pattern,
        )

    def test_unescaped_special_ascii_characters(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16("[\t\n\r]")
        self.assertEqual("[\\t\\n\\r]", pattern)

    def test_escaped_special_ascii_characters(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16("[\\t\\n\\r]")
        self.assertEqual("[\\t\\n\\r]", pattern)

    def test_on_XML_string_pattern(self) -> None:
        pattern = aas_core_codegen.jsonschema.main.fix_pattern_for_utf16(
            r"^[\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]*$"
        )
        self.assertEqual(
            "^([\\x09\\x0a\\x0d\\x20-\\ud7ff\\ue000-\\ufffd]|\\ud800[\\udc00-\\udfff]"
            "|[\\ud801-\\udbfe][\\udc00-\\udfff]|\\udbff[\\udc00-\\udfff])*$",
            pattern,
        )

        # NOTE (mristin):
        # We also test for the JSON representation to test against a possible bug
        # reported in:
        # https://github.com/admin-shell-io/aas-specs/pull/426 and
        # https://github.com/aas-core-works/aas-core-codegen/issues/485

        pattern_json = json.dumps(pattern)
        self.assertEqual(
            # NOTE (mristin):
            # Mind the ``r`` modifier for the string literals!
            r'"^([\\x09\\x0a\\x0d\\x20-\\ud7ff\\ue000-\\ufffd]'
            r"|\\ud800[\\udc00-\\udfff]|[\\ud801-\\udbfe][\\udc00-\\udfff]"
            r'|\\udbff[\\udc00-\\udfff])*$"',
            pattern_json,
        )


if __name__ == "__main__":
    unittest.main()
