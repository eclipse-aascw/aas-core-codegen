"""
Check the Python generated code with mypy and pylint, but do not run the tests.

This is meant to fail fast before running the slow live tests. The projects are
prepared exactly as in the live test so that both can share ``--output_dir``.

Unlike the live test, we skip the tests and only run mypy and pylint, which are
installed once in the virtual environment shared by all the cases.
"""

import argparse
import os
import pathlib
import subprocess
import sys
from typing import Optional, Pattern

from live_tests import common as live_tests_common
from live_tests import live_test_python


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_python_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "python" / "expected"
    )

    assert main_python_expected_dir.exists() and main_python_expected_dir.is_dir()

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        venv_python = live_test_python.prepare_venv(output_dir)
        if venv_python is None:
            return 1

        for case_dir in live_tests_common.select_case_dirs(
            main_python_expected_dir, select
        ):
            print(f"Fast-checking {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            qualified_module_name = live_test_python.prepare_project(
                case_dir, project_dir
            )

            for cmd in [
                [
                    str(venv_python),
                    "-m",
                    "mypy",
                    "--strict",
                    qualified_module_name,
                    "dev/tests",
                ],
                [
                    str(venv_python),
                    "-m",
                    "pylint",
                    "--rcfile=dev/pylint.rc",
                    qualified_module_name,
                ],
            ]:
                print(
                    f"Running {live_tests_common.escape_and_join_command(cmd)} "
                    f"in {project_dir}"
                )
                subprocess.check_call(cmd, cwd=project_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
