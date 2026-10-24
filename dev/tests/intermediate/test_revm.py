import os
import pathlib
import unittest
from typing import List, Tuple, Optional

from aas_core_codegen.parse import retree as parse_retree
from aas_core_codegen.intermediate import revm as intermediate_revm

import tests.common


class Test_against_recorded(unittest.TestCase):
    def test_cases(self) -> None:
        repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent.parent
        test_cases_dir = repo_root / "dev/test_data/intermediate_revm"

        assert test_cases_dir.exists(), f"{test_cases_dir=}"
        assert test_cases_dir.is_dir(), f"{test_cases_dir=}"

        # The expected cases should have no errors.
        expected_pths = sorted((test_cases_dir / "expected").glob("**/pattern.regex"))
        regex_pths_expected_exception: List[Tuple[pathlib.Path, bool]] = [
            (pth, False) for pth in expected_pths
        ]

        unexpected_pths = sorted(
            (test_cases_dir / "unexpected").glob("**/pattern.regex")
        )
        regex_pths_expected_exception.extend((pth, True) for pth in unexpected_pths)

        for regex_pth, expected_exception in regex_pths_expected_exception:
            case_dir = regex_pth.parent

            try:
                regex_text = regex_pth.read_text(encoding="utf-8")
            except Exception as exception:
                raise AssertionError(
                    f"Unexpected exception when reading "
                    f"from {regex_pth.relative_to(repo_root)}"
                ) from exception

            try:
                regex, error = parse_retree.parse([regex_text])
            except Exception as exception:
                raise AssertionError(
                    f"Unexpected exception in parsing "
                    f"the regex pattern {regex_text!r} "
                    f"from {regex_pth.relative_to(repo_root)}"
                ) from exception

            if error is not None:
                regex_line, pointer_line = parse_retree.render_pointer(error.cursor)
                raise AssertionError(
                    f"Unexpected error in parsing "
                    f"the regex pattern "
                    f"from {regex_pth.relative_to(repo_root)}:\n"
                    f"{error.message}:\n"
                    f"{regex_line}\n"
                    f"{pointer_line}"
                )

            assert regex is not None

            program: Optional[intermediate_revm.NodeOrLeaf] = None
            caught: Optional[Exception] = None

            try:
                program = intermediate_revm.translate(regex=regex)
            except Exception as exception:
                caught = exception

            if not expected_exception and caught is not None:
                raise AssertionError(
                    f"Expected no errors in the test "
                    f"case {case_dir.relative_to(test_cases_dir)}, but got:\n"
                    f"{caught}"
                ) from caught

            elif expected_exception and caught is None:
                raise AssertionError(
                    f"Expected exception in the test "
                    f"case {case_dir.relative_to(test_cases_dir)}, but got none."
                )

            else:
                pass

            expected_program_pth = case_dir / "program.txt"
            expected_exception_pth = case_dir / "exception.txt"

            if expected_exception:
                assert program is None
                assert caught is not None

                caught_str = str(caught)

                if tests.common.RERECORD:
                    expected_program_pth.unlink(missing_ok=True)
                    expected_exception_pth.write_text(caught_str, encoding="utf-8")
                else:
                    assert not expected_program_pth.exists(), (
                        f"Unexpected program stored in the test case "
                        f"where we expect an exception: {expected_program_pth}"
                    )
                    expected_caught_str = expected_exception_pth.read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(expected_caught_str, caught_str, f"{case_dir=}")

            else:
                assert program is not None
                assert caught is None

                program_str = intermediate_revm.dump(program)

                if tests.common.RERECORD:
                    expected_program_pth.write_text(program_str, encoding="utf-8")
                    expected_exception_pth.unlink(missing_ok=True)
                else:
                    assert not expected_exception_pth.exists(), (
                        f"Unexpected exception stored in the test case "
                        f"where we expect a program: {expected_exception_pth}"
                    )

                    expected_program_str = expected_program_pth.read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(expected_program_str, program_str, f"{case_dir=}")


if __name__ == "__main__":
    unittest.main()
