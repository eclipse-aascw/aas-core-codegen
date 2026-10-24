import unittest

import aas_core_codegen.python.common as python_common


class TestStringLiteral(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual("''", python_common.string_literal(""))

    def test_no_quotes(self) -> None:
        self.assertEqual("'x'", python_common.string_literal("x"))

    def test_double_quotes_but_no_single_quotes(self) -> None:
        self.assertEqual("'a\"b'", python_common.string_literal('a"b'))

    def test_single_quotes_but_no_double_quotes(self) -> None:
        self.assertEqual('"a\'b"', python_common.string_literal("a'b"))

    def test_equal_number_of_single_quotes_and_double_quotes(self) -> None:
        self.assertEqual("'a\\'\"b'", python_common.string_literal("a'\"b"))

    def test_more_single_quotes_than_double_quotes(self) -> None:
        self.assertEqual('"a\'\'\\"b"', python_common.string_literal("a''\"b"))

    def test_less_single_quotes_than_double_quotes(self) -> None:
        self.assertEqual("'a\\'\"\"b'", python_common.string_literal('a\'""b'))

    def test_tab(self) -> None:
        self.assertEqual("'a\\tb'", python_common.string_literal("a\tb"))

    def test_unset_duplicate_curly_brackets_no_quotes(self) -> None:
        self.assertEqual(
            "'{AAA}'",
            python_common.string_literal("{AAA}", duplicate_curly_brackets=False),
        )

        self.assertEqual("'{AAA}'", python_common.string_literal("{AAA}"))

    def test_duplicate_curly_brackets_no_quotes(self) -> None:
        self.assertEqual(
            "'{{AAA}}'",
            python_common.string_literal("{AAA}", duplicate_curly_brackets=True),
        )

    def test_unset_duplicate_curly_brackets_single_quote(self) -> None:
        self.assertEqual(
            '"{A\'A}"',
            python_common.string_literal("{A'A}", duplicate_curly_brackets=False),
        )

        self.assertEqual('"{A\'A}"', python_common.string_literal("{A'A}"))

    def test_duplicate_curly_brackets_single_quote(self) -> None:
        self.assertEqual(
            '"{{A\'A}}"',
            python_common.string_literal("{A'A}", duplicate_curly_brackets=True),
        )

    def test_unset_duplicate_curly_brackets_double_quote(self) -> None:
        self.assertEqual(
            "'{A\"A}'",
            python_common.string_literal('{A"A}', duplicate_curly_brackets=False),
        )

        self.assertEqual("'{A\"A}'", python_common.string_literal('{A"A}'))

    def test_duplicate_curly_brackets_double_quote(self) -> None:
        self.assertEqual(
            "'{{A\"A}}'",
            python_common.string_literal('{A"A}', duplicate_curly_brackets=True),
        )


class TestBytesLiteral(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertTupleEqual(('b""', False), python_common.bytes_literal(b""))

    def test_one(self) -> None:
        self.assertTupleEqual(('b"\\x00"', False), python_common.bytes_literal(b"\x00"))

    def test_eight(self) -> None:
        self.assertTupleEqual(
            ('b"\\x00\\x01\\x02\\x03\\x04\\x05\\x06\\x07"', False),
            python_common.bytes_literal(b"\x00\x01\x02\x03\x04\x05\x06\x07"),
        )

    def test_nine(self) -> None:
        self.assertTupleEqual(
            (
                '''\
b"\\x00\\x01\\x02\\x03\\x04\\x05\\x06\\x07"
b"\\x08"''',
                True,
            ),
            python_common.bytes_literal(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08"),
        )

    def test_sixteen(self) -> None:
        self.assertTupleEqual(
            (
                '''\
b"\\x00\\x01\\x02\\x03\\x04\\x05\\x06\\x07"
b"\\x08\\x09\\x10\\x11\\x12\\x13\\x14\\x15"''',
                True,
            ),
            python_common.bytes_literal(
                b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x10\x11\x12\x13\x14\x15"
            ),
        )


if __name__ == "__main__":
    unittest.main()
