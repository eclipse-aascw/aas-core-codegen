import unittest

import aas_core_codegen.csharp.common as csharp_common


class TestStringLiteral(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual('""', csharp_common.string_literal(""))

    def test_identifier(self) -> None:
        self.assertEqual('"something"', csharp_common.string_literal("something"))

    def test_single_quote(self) -> None:
        self.assertEqual('"some\'thing"', csharp_common.string_literal("some'thing"))

    def test_double_quotes(self) -> None:
        self.assertEqual('"some\\"thing"', csharp_common.string_literal('some"thing'))

    def test_special_chars(self) -> None:
        self.assertEqual(
            '"some\\n\\\\thing"', csharp_common.string_literal("some\n\\thing")
        )


if __name__ == "__main__":
    unittest.main()
