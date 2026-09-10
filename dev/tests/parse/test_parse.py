# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import ast
import os
import pathlib
import re
import unittest
from typing import Optional, Tuple, List

import asttokens
import docutils.nodes

from aas_core_codegen import parse
from aas_core_codegen.common import Error, Identifier

import tests.common


class Test_parsing_AST(unittest.TestCase):
    def test_valid_code(self) -> None:
        source = """\
class Something:
    pass
"""

        atok, error = parse.source_to_atok(source=source)
        assert atok is not None
        assert error is None

    def test_invalid_code(self) -> None:
        source = """\
class Something: 12 this is wrong
"""

        _, error = parse.source_to_atok(source=source)
        assert error is not None
        assert isinstance(error, SyntaxError)
        self.assertEqual(1, error.lineno)


class Test_checking_imports(unittest.TestCase):
    @staticmethod
    def replace_column_number_with_x(errors: List[str]) -> List[str]:
        """
        Replace the column number with ``"X"``.

        We need to remove the column number as it changes between Python versions
        (notably, it is more precise from Python 3.10 on).
        """
        return [re.sub(r"column [0-9]+", "column X", error) for error in errors]

    def test_import_reported(self) -> None:
        source = """\
import typing
"""

        atok, error = parse.source_to_atok(source=source)
        assert error is None, f"{error=}"
        assert atok is not None

        errors = parse.check_expected_imports(atok=atok)
        self.assertListEqual(
            [
                "At line 1 and column X: "
                "Unexpected ``import ...``. "
                "Only ``from ... import...`` statements are expected."
            ],
            Test_checking_imports.replace_column_number_with_x(errors),
        )

    def test_from_import_as_reported(self) -> None:
        source = """\
from typing import List as Lst
"""

        atok, error = parse.source_to_atok(source=source)
        assert error is None, f"{error=}"
        assert atok is not None

        # NOTE (mristin, 2022-01-22):
        # We need to remove the column number as it changes between Python versions
        # (notably, it is more precise from Python 3.10 on.)

        errors = parse.check_expected_imports(atok=atok)
        self.assertListEqual(
            [
                "At line 1 and column X: Unexpected ``from ... import ... as ...``. "
                "Only ``from ... import...`` statements are expected."
            ],
            Test_checking_imports.replace_column_number_with_x(errors),
        )

    def test_unexpected_name_from_module(self) -> None:
        source = """\
from enum import List
"""

        atok, error = parse.source_to_atok(source=source)
        assert atok is not None
        assert error is None

        errors = parse.check_expected_imports(atok=atok)
        self.assertListEqual(
            [
                "At line 1 and column X: "
                "Expected to import 'List' from the module typing, "
                "but it is imported from enum."
            ],
            Test_checking_imports.replace_column_number_with_x(errors),
        )

    def test_unexpected_import_from_a_module(self) -> None:
        source = """\
from something import Else
"""

        atok, error = parse.source_to_atok(source=source)
        assert atok is not None
        assert error is None

        errors = parse.check_expected_imports(atok=atok)
        self.assertListEqual(
            ["At line 1 and column X: Unexpected import of a name 'Else'."],
            Test_checking_imports.replace_column_number_with_x(errors),
        )


class Test_parsing_docstring(unittest.TestCase):
    @staticmethod
    def parse_and_extract_docstring(source: str) -> docutils.nodes.document:
        """
        Parse the ``source`` and extract a description.

        The description is expected to belong to a single class, ``Some_class``.
        """
        symbol_table, error = tests.common.parse_source(source)
        assert error is None, f"{error}"
        assert symbol_table is not None

        cls = symbol_table.must_find_class(Identifier("Some_class"))
        assert cls.description is not None
        return cls.description.document

    def test_empty(self) -> None:
        source = '''\
class Some_class:
    """"""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        document = Test_parsing_docstring.parse_and_extract_docstring(source=source)

        self.assertEqual(0, len(document.children))

    def test_simple_single_line(self) -> None:
        source = '''\
class Some_class:
    """This is some documentation."""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        document = Test_parsing_docstring.parse_and_extract_docstring(source=source)

        self.assertEqual(1, len(document.children))
        self.assertIsInstance(document.children[0], docutils.nodes.paragraph)

    def test_that_multi_line_docstring_is_not_parsed_as_a_block_quote(self) -> None:
        source = '''\
class Some_class:
    """
    This is some documentation.

    Another paragraph.
    """

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        document = Test_parsing_docstring.parse_and_extract_docstring(source=source)
        self.assertEqual(2, len(document.children))
        self.assertIsInstance(document.children[0], docutils.nodes.paragraph)
        self.assertIsInstance(document.children[1], docutils.nodes.paragraph)


class Test_unexpected_class_definitions(unittest.TestCase):
    @staticmethod
    def error_from_source(source: str) -> Optional[Error]:
        """Encapsulate the observation of the error when parsing a class."""
        atok, parse_exception = parse.source_to_atok(source=source)
        assert parse_exception is None, f"{parse_exception=}"
        assert atok is not None

        _, error = parse.atok_to_symbol_table(atok=atok)
        return error


class Test_parse_type_annotation(unittest.TestCase):
    @staticmethod
    def parse_type_annotation_from_ann_assign(
        source: str,
    ) -> Tuple[ast.AST, asttokens.ASTTokens]:
        """Encapsulate the parsing of the type annotation of a variable."""
        atok = asttokens.ASTTokens(source, parse=True)

        module = atok.tree
        assert isinstance(module, ast.Module)
        assert len(module.body) == 1, f"{module.body=}"

        ann_assign = module.body[0]
        assert isinstance(ann_assign, ast.AnnAssign), f"{ann_assign=}"

        assert ann_assign.annotation is not None

        return ann_assign.annotation, atok

    def test_atomic(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: int"
        )

        type_annotation, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is None, tests.common.most_underlying_messages(error)

        self.assertEqual("int", str(type_annotation))

    def test_subscripted_with_a_single_value(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: List[int]"
        )

        type_annotation, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is None, tests.common.most_underlying_messages(error)

        self.assertEqual("List[int]", str(type_annotation))

    def test_subscripted_with_a_tuple(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: Mapping[str, Optional[int]]"
        )

        type_annotation, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is None, tests.common.most_underlying_messages(error)

        self.assertEqual("Mapping[str, Optional[int]]", str(type_annotation))

    def test_nested(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: Optional[List[Reference]]"
        )

        type_annotation, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is None, tests.common.most_underlying_messages(error)

        self.assertEqual("Optional[List[Reference]]", str(type_annotation))


class Test_parse_type_annotation_fail(unittest.TestCase):
    def test_ellipsis(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: Mapping[str, ...]"
        )

        _, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is not None

        self.assertEqual(
            "Expected a string literal if the type annotation is given as a constant, "
            "but got: Ellipsis (as <class 'ellipsis'>)",
            error.message,
        )

    def test_non_name_type_identifier(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: (int if True else str)"
        )

        _, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is not None

        # NOTE (mristin, 2022-01-22):
        # We need to remove the type since it differs between Python 3.8 and newer
        # versions.

        self.assertEqual(
            "Expected either atomic type annotation (as name or string literal) "
            "or a subscripted one (as a subscript), "
            "but got: int if True else str",
            re.sub(r" \(as <class .*>\)$", "", error.message),
        )

    def test_unexpected_slice_in_index(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: Optional[str:int]"
        )

        _, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is not None

        self.assertEqual(
            "Expected an index to define a subscripted type annotation, "
            "but got a slice: str:int",
            error.message,
        )

    def test_unexpected_ext_slice_in_index(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: Optional[1:2, 3]"
        )

        _, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is not None

        self.assertEqual(
            "Expected an index to define a subscripted type annotation, "
            "but got an extended slice: 1:2, 3",
            error.message,
        )

    def test_unexpected_expression_in_index(self) -> None:
        anno, atok = Test_parse_type_annotation.parse_type_annotation_from_ann_assign(
            "x: Optional[str if True else int]"
        )

        _, error = parse._translate._type_annotation(node=anno, atok=atok)
        assert error is not None

        self.assertEqual(
            "Expected a tuple, a name, a subscript or a string literal "
            "for a subscripted type annotation, but got: str if True else int",
            error.message,
        )


class Test_against_recorded(unittest.TestCase):
    def test_cases(self) -> None:
        repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent.parent
        test_cases_dir = repo_root / "dev/test_data/parse"

        assert test_cases_dir.exists(), f"{test_cases_dir=}"
        assert test_cases_dir.is_dir(), f"{test_cases_dir=}"

        # The expected cases should have no errors.
        expected_pths = sorted((test_cases_dir / "expected").glob("**/meta_model.py"))
        meta_model_pths_expected_errors = [
            (pth, False) for pth in expected_pths
        ]  # type: List[Tuple[pathlib.Path, bool]]

        unexpected_pths = sorted(
            (test_cases_dir / "unexpected").glob("**/meta_model.py")
        )

        meta_model_pths_expected_errors.extend((pth, True) for pth in unexpected_pths)

        for meta_model_pth, expected_errors in meta_model_pths_expected_errors:
            case_dir = meta_model_pth.parent

            try:
                source = meta_model_pth.read_text(encoding="utf-8")

                symbol_table, error = tests.common.parse_source(source)

            except Exception as exception:
                raise AssertionError(
                    f"Expected no exception "
                    f"for the test case {case_dir.relative_to(test_cases_dir)}"
                ) from exception

            if not expected_errors and error is not None:
                raise AssertionError(
                    f"Expected no errors in the test "
                    f"case {case_dir.relative_to(test_cases_dir)}, but got:\n"
                    f"{tests.common.most_underlying_messages(error)}"
                )

            elif expected_errors and error is None:
                raise AssertionError(
                    f"Expected errors in the test "
                    f"case {case_dir.relative_to(test_cases_dir)}, but got none."
                )

            else:
                pass

            expected_symbol_table_pth = case_dir / "expected_symbol_table.txt"
            expected_error_pth = case_dir / "expected_error.txt"

            if expected_errors:
                if expected_symbol_table_pth.exists():
                    raise AssertionError(
                        f"Unexpected recorded symbol table file when errors "
                        f"are expected: {expected_symbol_table_pth}"
                    )

                assert error is not None

                error_str = tests.common.most_underlying_messages(error)

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

                assert symbol_table is not None

                symbol_table_str = parse.dump(symbol_table)

                if tests.common.RERECORD:
                    expected_symbol_table_pth.write_text(
                        symbol_table_str, encoding="utf-8"
                    )
                else:
                    expected_symbol_table_str = expected_symbol_table_pth.read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(
                        expected_symbol_table_str,
                        symbol_table_str,
                        f"{case_dir=}, {error=}",
                    )

    def test_common_meta_models(self) -> None:
        repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent.parent
        test_cases_dir = repo_root / "dev/test_data/parse/common_meta_models"

        assert test_cases_dir.exists(), f"{test_cases_dir=}"
        assert test_cases_dir.is_dir(), f"{test_cases_dir=}"

        for meta_model_pth in tests.common.COMMON_META_MODEL_PATHS:
            case_dir = test_cases_dir / meta_model_pth.stem

            try:
                source = meta_model_pth.read_text(encoding="utf-8")

                symbol_table, error = tests.common.parse_source(source)

            except Exception as exception:
                raise AssertionError(
                    f"Expected no exception when parsing "
                    f"the real meta-model {meta_model_pth}"
                ) from exception

            if error is not None:
                raise AssertionError(
                    f"Expected no errors when parsing "
                    f"the real meta-model {meta_model_pth}, but got:\n"
                    f"{tests.common.most_underlying_messages(error)}"
                )

            expected_symbol_table_pth = case_dir / "expected_symbol_table.txt"

            assert symbol_table is not None

            symbol_table_str = parse.dump(symbol_table)

            if tests.common.RERECORD:
                expected_symbol_table_pth.parent.mkdir(exist_ok=True, parents=True)
                expected_symbol_table_pth.write_text(symbol_table_str, encoding="utf-8")
            else:
                expected_symbol_table_str = expected_symbol_table_pth.read_text(
                    encoding="utf-8"
                )
                self.assertEqual(
                    expected_symbol_table_str,
                    symbol_table_str,
                    f"{case_dir=}, {error=}",
                )


if __name__ == "__main__":
    unittest.main()
