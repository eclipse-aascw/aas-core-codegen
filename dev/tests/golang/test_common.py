import unittest

import aas_core_codegen.golang.common as golang_common


class TestStringLiteral(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual('""', golang_common.string_literal(""))

    def test_no_quotes(self) -> None:
        self.assertEqual('"x"', golang_common.string_literal("x"))

    def test_double_quotes_but_no_single_quotes(self) -> None:
        self.assertEqual('"a\\"b"', golang_common.string_literal('a"b'))

    def test_single_quotes_but_no_double_quotes(self) -> None:
        self.assertEqual('"a\'b"', golang_common.string_literal("a'b"))

    def test_tab(self) -> None:
        self.assertEqual('"a\\tb"', golang_common.string_literal("a\tb"))


class TestBytesLiteral(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertTupleEqual(("[...]byte{}", False), golang_common.bytes_literal(b""))

    def test_one(self) -> None:
        self.assertTupleEqual(
            ("[...]byte{0x00}", False),
            golang_common.bytes_literal(b"\x00"),
        )

    def test_eight(self) -> None:
        self.assertTupleEqual(
            ("[...]byte{0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07}", False),
            golang_common.bytes_literal(b"\x00\x01\x02\x03\x04\x05\x06\x07"),
        )

    def test_nine(self) -> None:
        code, multiline = golang_common.bytes_literal(
            b"\x00\x01\x02\x03\x04\x05\x06\x07\x08"
        )

        self.assertEqual(
            """\
[...]byte {
\t0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
\t0x08
}""",
            code,
        )
        self.assertTrue(multiline)

    def test_sixteen(self) -> None:
        code, multiline = golang_common.bytes_literal(
            b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x10\x11\x12\x13\x14\x15"
        )

        self.assertEqual(
            """\
[...]byte {
\t0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
\t0x08, 0x09, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15
}""",
            code,
        )

        self.assertTrue(multiline)


if __name__ == "__main__":
    unittest.main()
