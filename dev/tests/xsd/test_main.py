# pylint: disable=missing-docstring
import os
import pathlib
import re
import unittest
from typing import Optional
from xml.sax import saxutils as xml_saxutils

import xmlschema

from aas_core_codegen import infer_for_schema, intermediate
from aas_core_codegen.xsd import main as xsd_main


def _schema_source(pattern: str) -> str:
    """Build a schema for a string constrained by the given pattern."""
    return f"""\
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="value"><xs:simpleType><xs:restriction base="xs:string">
<xs:pattern value={xml_saxutils.quoteattr(pattern)}/>
</xs:restriction></xs:simpleType></xs:element></xs:schema>"""


class Test_translate_pattern(unittest.TestCase):
    # NOTE (mristin):
    # This is relevant since XSD are always anchored.
    # See: https://stackoverflow.com/questions/4367914/regular-expression-in-xml-schema-definition-fails

    def test_table_for_removing_anchors(self) -> None:
        for pattern, expected, identifier in [
            ("^$", "", "empty"),
            ("^something$", "something", "simple_literal"),
            ("(^.*$)", "(.*)", "within_a_group"),
        ]:
            fixed, error = xsd_main._translate_pattern(pattern)
            assert error is None, identifier
            assert fixed is not None, identifier

            self.assertEqual(expected, fixed, identifier)

    def test_table_for_rendering_quantifiers(self) -> None:
        # NOTE (mristin):
        # We explicitly test for quantifiers to make sure that they all comply with
        # XSD patterns. For example, when only the maximum quantifier is given,
        # the minimum quantifier of 0 must be indicated explicitly.
        for pattern, expected, identifier in [
            ("a{1}", "a{1}", "exact repetition"),
            ("a{1,}", "a+", "min 1 repetition"),
            ("a{2,}", "a{2,}", "more than 1 min repetition"),
            ("a{,2}", "a{0,2}", "only max repetition"),
            ("a{1,2}", "a{1,2}", "min and max repetition"),
        ]:
            fixed, error = xsd_main._translate_pattern(pattern)
            assert error is None, identifier
            assert fixed is not None, identifier

            self.assertEqual(expected, fixed, identifier)

    def test_encoded_characters_match_original_pattern(self) -> None:
        """Preserve encoded literals when validating with the generated XSD pattern."""
        for pattern, samples in [
            (r"^a\x2eb$", ["a.b", "axb", "a-b"]),
            (r"^\x24aas$", ["$aas", "aas", ""]),
            (r"^\x5bx\x5d$", ["[x]", "x"]),
            (r"^[\x20-\x5B\x5D-\x7E]+$", ["hello world", "[x]", "a\\b", ""]),
            (r"^[\x5e\x2d\x5d\x5c]+$", ["^-]\\", "a", ""]),
            (r"^\x7c$", ["|", "x", ""]),
            (r"^\u002e$", [".", "x"]),
            (r"^\U0001F600$", ["\U0001F600", "x"]),
            (r"^\\x2e$", [r"\x2e", "."]),
        ]:
            with self.subTest(pattern=pattern):
                translated, error = xsd_main._translate_pattern(pattern)
                self.assertIsNone(error)
                assert translated is not None
                schema = xmlschema.XMLSchema(_schema_source(translated))
                for text in samples:
                    with self.subTest(text=text):
                        self.assertEqual(
                            re.fullmatch(pattern, text) is not None,
                            schema.is_valid(
                                f"<value>{xml_saxutils.escape(text)}</value>"
                            ),
                        )

    def test_combined_patterns_preserve_encoded_characters(self) -> None:
        """Preserve encoded literals when intersecting multiple pattern constraints."""
        for patterns, samples in [
            ([r"^a\x2eb$", r"^...$"], ["a.b", "axb", "a-b"]),
            (
                [r"^[\x20-\x5B\x5D-\x7E]+$", r"^.{1,12}$"],
                ["hello world", "[x]", "a\\b", ""],
            ),
            ([r"^\x24aas$", r"^.{4}$"], ["$aas", "aas", ""]),
            ([r"^\x5ex$", r"^..$"], ["^x", "ax"]),
            ([r"^\x7c$", r"^.$"], ["|", "x", ""]),
            ([r"^[\x5e]+$", r"^.{1,2}$"], ["^", "^^", "^^^", "a"]),
            ([r"^\\x2e$", r"^.{4}$"], [r"\x2e", "."]),
            ([r"^\u002e$", r"^.$"], [".", "x"]),
            ([r"^\U0001F600$", r"^.$"], ["\U0001F600", "x"]),
            ([r"^[^\x20]+$", r"^.{1,2}$"], [" ", "x", "xx", "xxx"]),
            ([r"^\x7bx\x7d$", r"^...$"], ["{x}", "xxx"]),
            ([r"^[\^-z]+$", r"^[a-z]+$"], ["a", "az", "^", "A", ""]),
            ([r"^[\x5e-z]+$", r"^[a-z]+$"], ["a", "az", "^", "A", ""]),
        ]:
            with self.subTest(patterns=patterns):
                translated, error = xsd_main._translate_to_simple_type(
                    primitive_type=intermediate.PrimitiveType.STR,
                    constraints=infer_for_schema.Constraints(
                        patterns=[
                            infer_for_schema.PatternConstraint(pattern)
                            for pattern in patterns
                        ]
                    ),
                )
                self.assertIsNone(error)
                assert translated is not None
                assert translated.restriction is not None
                assert translated.restriction.pattern is not None
                schema = xmlschema.XMLSchema(
                    _schema_source(translated.restriction.pattern)
                )
                for text in samples:
                    with self.subTest(text=text):
                        self.assertEqual(
                            all(re.fullmatch(pattern, text) for pattern in patterns),
                            schema.is_valid(
                                f"<value>{xml_saxutils.escape(text)}</value>"
                            ),
                        )


class Test_examples(unittest.TestCase):
    def test_examples_comply_with_schema(self) -> None:
        repo_dir = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent.parent

        expected_dir = repo_dir / "dev" / "test_data" / "main" / "xsd" / "expected"
        assert expected_dir.exists() and expected_dir.is_dir(), expected_dir

        for case_dir in sorted(expected_dir.iterdir()):
            assert case_dir.is_dir(), case_dir

            schema_pth = case_dir / "expected_output" / "schema.xsd"

            schema = xmlschema.XMLSchema(str(schema_pth))

            for data_pth in sorted(
                (case_dir / "examples" / "Expected").glob("**/*.xml")
            ):
                try:
                    schema.validate(str(data_pth))
                except xmlschema.XMLSchemaException as err:
                    raise AssertionError(
                        f"Failed to validate {data_pth} against {schema_pth}"
                    ) from err

            for data_pth in sorted(
                (case_dir / "examples" / "Unexpected").glob("**/*.xml")
            ):
                schema_exception = None  # type: Optional[xmlschema.XMLSchemaException]
                try:
                    schema.validate(str(data_pth))
                except xmlschema.XMLSchemaException as err:
                    schema_exception = err

                if schema_exception is None:
                    raise AssertionError(
                        f"Expected the data from {data_pth} to fail with validation "
                        f"of {schema_pth}, but no schema exception was observed."
                    )


if __name__ == "__main__":
    unittest.main()
