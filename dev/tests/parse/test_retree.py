import ast
import os
import pathlib
import unittest
from typing import Tuple, List, Union, Sequence

import asttokens

from aas_core_codegen.common import assert_never
from aas_core_codegen.parse import (
    tree as parse_tree,
    _rules as parse_rules,
    retree as parse_retree,
)

import tests.common


def parse_values_from_source(
    root_node: ast.AST,
) -> Sequence[Union[str, parse_tree.FormattedValue]]:
    """Extract the values from the ``root_node`` representing a regular expression."""
    assert isinstance(
        root_node, ast.Module
    ), f"Expected a module, but got: {type(root_node)=}"
    assert (
        len(root_node.body) == 1
    ), f"Expected only a single statement, but got: {ast.dump(root_node)}"

    expr_node = root_node.body[0]
    assert isinstance(expr_node, ast.Expr), (
        f"Expected only an expression in the module body, "
        f"but got: {type(expr_node)=}"
    )

    value_node = expr_node.value

    our_node, rule_error = parse_rules.ast_node_to_our_node(node=value_node)
    assert rule_error is None, (
        f"Unexpected translation error at the parse stage: "
        f"{tests.common.most_underlying_messages(rule_error)}"
    )
    del value_node  # Delete so that we do not use it anymore by mistake

    values: Sequence[Union[str, parse_tree.FormattedValue]] = []

    if isinstance(our_node, parse_tree.Constant):
        assert isinstance(our_node.value, str), (
            f"Expected either a string constant or a joined string, "
            f"but got: {type(our_node.value)=}"
        )
        values = [our_node.value]

    elif isinstance(our_node, parse_tree.JoinedStr):
        values = our_node.values

    else:
        raise AssertionError(
            f"Expected either a string constant or a joined string, "
            f"but got: {type(our_node)=}"
        )

    return values


class Test_cursor(unittest.TestCase):
    def test_empty_values(self) -> None:
        cursor = parse_retree.Cursor(values=[])
        self.assertTrue(cursor.done())

    def test_empty_string(self) -> None:
        source = '""'
        atok = asttokens.ASTTokens(source_text=source, parse=True)
        assert atok.tree is not None
        values = parse_values_from_source(root_node=atok.tree)

        cursor = parse_retree.Cursor(values=values)
        self.assertTrue(cursor.done())

    def test_iteration(self) -> None:
        table = [
            ('"abc"', ["a", "b", "c"]),
            ('f"{x}"', ["<formatted value>"]),
            ('f"{x}ab"', ["<formatted value>", "a", "b"]),
            ('f"a{x}b"', ["a", "<formatted value>", "b"]),
            ('f"ab{x}"', ["a", "b", "<formatted value>"]),
        ]

        for source, expected_tokens in table:
            atok = asttokens.ASTTokens(source_text=source, parse=True)
            assert atok.tree is not None
            values = parse_values_from_source(root_node=atok.tree)

            cursor = parse_retree.Cursor(values=values)

            tokens: List[str] = []
            while not cursor.done():
                formatted_value = cursor.try_formatted_value()
                if formatted_value:
                    tokens.append("<formatted value>")
                else:
                    character = cursor.try_substring(length=1)
                    assert character is not None
                    tokens.append(character)

            self.assertListEqual(expected_tokens, tokens, f"{source=}")

    def test_try_string_in_formatted_value(self) -> None:
        source = 'f"{x}"'
        atok = asttokens.ASTTokens(source_text=source, parse=True)
        assert atok.tree is not None
        values = parse_values_from_source(root_node=atok.tree)

        cursor = parse_retree.Cursor(values=values)

        assert not cursor.try_literal("a")
        self.assertIsNone(cursor.try_substring(length=1))

        assert not cursor.done()

        assert cursor.try_formatted_value() is not None
        assert cursor.done()

    def test_try_jump_over_to_formatted_value(self) -> None:
        source = 'f"abc{x}"'
        atok = asttokens.ASTTokens(source_text=source, parse=True)
        assert atok.tree is not None
        values = parse_values_from_source(root_node=atok.tree)

        cursor = parse_retree.Cursor(values=values)

        assert not cursor.try_literal("abcd")
        self.assertIsNone(cursor.try_substring(length=4))

        assert not cursor.done()


class Test_against_recorded(unittest.TestCase):
    def test_cases(self) -> None:
        repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent.parent
        test_cases_dir = repo_root / "dev/test_data/parse_retree"

        assert test_cases_dir.exists(), f"{test_cases_dir=}"
        assert test_cases_dir.is_dir(), f"{test_cases_dir=}"

        # The expected cases should have no errors.
        expected_pths = sorted((test_cases_dir / "expected").glob("**/source.py"))
        pths_expected_errors: List[Tuple[pathlib.Path, bool]] = [
            (pth, False) for pth in expected_pths
        ]

        unexpected_pths = sorted((test_cases_dir / "unexpected").glob("**/source.py"))

        pths_expected_errors.extend((pth, True) for pth in unexpected_pths)

        for source_pth, expected_errors in pths_expected_errors:
            case_dir = source_pth.parent

            try:
                source = source_pth.read_text(encoding="utf-8")

                atok = asttokens.ASTTokens(
                    source_text=source, parse=True, filename=str(source_pth)
                )

                assert atok.tree is not None

                values = parse_values_from_source(root_node=atok.tree)

                parsed_regex, error = parse_retree.parse(values=values)

            except Exception as exception:
                raise AssertionError(
                    f"Expected no exception "
                    f"for the test case {case_dir.relative_to(test_cases_dir)}"
                ) from exception

            if not expected_errors and error is not None:
                regex_line, pointer_line = parse_retree.render_pointer(error.cursor)

                raise AssertionError(
                    f"Expected no errors in the test "
                    f"case {case_dir.relative_to(test_cases_dir)}, but got:\n"
                    f"{error.message}\n"
                    f"{regex_line}\n"
                    f"{pointer_line}"
                )

            elif expected_errors and error is None:
                raise AssertionError(
                    f"Expected errors in the test "
                    f"case {case_dir.relative_to(test_cases_dir)}, but got none."
                )

            else:
                pass

            expected_parsed_regex_pth = case_dir / "expected_parsed_regex.txt"
            rendered_regex_pth = case_dir / "rendered_regex.txt"
            expected_error_pth = case_dir / "expected_error.txt"

            if expected_errors:
                if expected_parsed_regex_pth.exists():
                    raise AssertionError(
                        f"Unexpected recorded regex file when errors "
                        f"are expected: {expected_parsed_regex_pth}"
                    )

                assert error is not None

                regex_line, pointer_line = parse_retree.render_pointer(error.cursor)
                error_str = f"{error.message}\n{regex_line}\n{pointer_line}\n"

                if tests.common.RERECORD:
                    expected_error_pth.write_text(error_str, encoding="utf-8")
                else:
                    expected_error_str = expected_error_pth.read_text(encoding="utf-8")
                    self.assertEqual(expected_error_str, error_str, f"{case_dir=}")

            else:
                if expected_error_pth.exists():
                    raise AssertionError(
                        f"Unexpected recorded error file when no errors "
                        f"are expected: {expected_error_pth}"
                    )

                assert parsed_regex is not None

                parsed_regex_str = parse_retree.dump(parsed_regex)

                rendered_parts: List[str] = []
                for value in parse_retree.render(parsed_regex):
                    if isinstance(value, str):
                        rendered_parts.append(value)
                    elif isinstance(value, parse_tree.FormattedValue):
                        rendered_parts.append("<formatted value>")
                    else:
                        assert_never(value)
                rendered_regex_str = "".join(rendered_parts)

                if tests.common.RERECORD:
                    expected_parsed_regex_pth.write_text(
                        parsed_regex_str, encoding="utf-8"
                    )

                    rendered_regex_pth.write_text(rendered_regex_str, encoding="utf-8")
                else:
                    expected_parsed_regex_str = expected_parsed_regex_pth.read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(
                        expected_parsed_regex_str,
                        parsed_regex_str,
                        f"{case_dir=}",
                    )

                    expected_rendered_regex_str = rendered_regex_pth.read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(
                        expected_rendered_regex_str,
                        rendered_regex_str,
                        f"{case_dir=}",
                    )


if __name__ == "__main__":
    unittest.main()
