import unittest

import aas_core_codegen.typescript.common as typescript_common


class TestStringLiteral(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual('""', typescript_common.string_literal(""))

    def test_no_quotes(self) -> None:
        self.assertEqual('"x"', typescript_common.string_literal("x"))

    def test_double_quotes_but_no_single_quotes(self) -> None:
        self.assertEqual('"a\\"b"', typescript_common.string_literal('a"b'))

    def test_single_quotes_but_no_double_quotes(self) -> None:
        self.assertEqual('"a\'b"', typescript_common.string_literal("a'b"))

    def test_tab(self) -> None:
        self.assertEqual('"a\\tb"', typescript_common.string_literal("a\tb"))

    def test_unset_in_backticks(self) -> None:
        self.assertEqual(
            '"`AAA`"',
            typescript_common.string_literal("`AAA`", in_backticks=False),
        )

        self.assertEqual('"`AAA`"', typescript_common.string_literal("`AAA`"))

    def test_dont_escape_quotes_in_backticks(self) -> None:
        self.assertEqual(
            '"',
            typescript_common.string_literal(
                '"', without_enclosing=True, in_backticks=True
            ),
        )

    def test_escape_backticks_and_dollar_signs_in_backticks(self) -> None:
        self.assertEqual(
            "\\`$\\${something}",
            typescript_common.string_literal(
                "`$${something}", without_enclosing=True, in_backticks=True
            ),
        )


class TestBytesLiteral(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertTupleEqual(
            ("new Uint8Array()", False), typescript_common.bytes_literal(b"")
        )

    def test_one(self) -> None:
        self.assertTupleEqual(
            ("new Uint8Array([0x00])", False),
            typescript_common.bytes_literal(b"\x00"),
        )

    def test_eight(self) -> None:
        self.assertTupleEqual(
            ("new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07])", False),
            typescript_common.bytes_literal(b"\x00\x01\x02\x03\x04\x05\x06\x07"),
        )

    def test_nine(self) -> None:
        code, multiline = typescript_common.bytes_literal(
            b"\x00\x01\x02\x03\x04\x05\x06\x07\x08"
        )

        self.assertEqual(
            """\
new Uint8Array(
  [
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
    0x08
  ]
)""",
            code,
        )
        self.assertTrue(multiline)

    def test_sixteen(self) -> None:
        code, multiline = typescript_common.bytes_literal(
            b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x10\x11\x12\x13\x14\x15"
        )

        self.assertEqual(
            """\
new Uint8Array(
  [
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
    0x08, 0x09, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15
  ]
)""",
            code,
        )

        self.assertTrue(multiline)


if __name__ == "__main__":
    unittest.main()
