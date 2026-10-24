import unittest
from typing import Optional, List

import aas_core_codegen.java.description as java_description


class TestRemoveRedundantP(unittest.TestCase):
    def test_empty(self) -> None:
        tokens: List[java_description._Token] = []

        result = java_description._remove_redundant_p(tokens)
        self.assertListEqual([], result)

    def test_prefix_chain(self) -> None:
        tokens: List[java_description._Token] = [
            java_description._TokenP(),
            java_description._TokenP(),
            java_description._TokenText("hello world"),
        ]

        result = java_description._remove_redundant_p(tokens)
        self.assertListEqual(
            [
                java_description._TokenP(),
                java_description._TokenText("hello world"),
            ],
            result,
        )

    def test_suffix_chain(self) -> None:
        tokens: List[java_description._Token] = [
            java_description._TokenP(),
            java_description._TokenText("hello world"),
            java_description._TokenP(),
            java_description._TokenP(),
        ]

        result = java_description._remove_redundant_p(tokens)
        self.assertListEqual(
            [
                java_description._TokenP(),
                java_description._TokenText("hello world"),
            ],
            result,
        )

    def test_chain_in_the_middle(self) -> None:
        tokens: List[java_description._Token] = [
            java_description._TokenP(),
            java_description._TokenText("hello"),
            java_description._TokenP(),
            java_description._TokenP(),
            java_description._TokenText("world"),
        ]

        result = java_description._remove_redundant_p(tokens)
        self.assertListEqual(
            [
                java_description._TokenP(),
                java_description._TokenText("hello"),
                java_description._TokenP(),
                java_description._TokenText("world"),
            ],
            result,
        )


class TestIndentionMachine(unittest.TestCase):
    def test_empty(self) -> None:
        machine = java_description._IndentionMachine()
        result = machine.render()

        self.assertEqual("", result)

    def test_only_text(self) -> None:
        machine = java_description._IndentionMachine()
        machine.write("hello world")
        result = machine.render()

        self.assertEqual("hello world", result)

    def test_indent_prefix(self) -> None:
        machine = java_description._IndentionMachine()
        machine.indent()
        machine.write("hello world")
        result = machine.render()

        self.assertEqual("  hello world", result)

    def test_indent_dedent(self) -> None:
        machine = java_description._IndentionMachine()

        machine.write("hello\n")
        machine.indent()
        machine.write("wor\nld\n")
        machine.dedent()
        machine.write("!")
        result = machine.render()

        self.assertEqual(
            """\
hello
  wor
  ld
!""",
            result,
        )

    def test_negative_indention(self) -> None:
        machine = java_description._IndentionMachine()

        machine.write("hello\n")

        value_error: Optional[ValueError] = None

        try:
            machine.dedent()
        except ValueError as a_value_error:
            value_error = a_value_error

        assert value_error is not None
        self.assertEqual("Unexpected negative indention", str(value_error))


if __name__ == "__main__":
    unittest.main()
