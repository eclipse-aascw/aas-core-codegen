# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""
Compile the C# generated code, but do not run the tests.

This is meant to fail fast before running the slow live tests. The solutions are
prepared exactly as in the live test so that both can share ``--output_dir``.
"""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Optional, Pattern

from live_tests import common as live_tests_common
from live_tests import live_test_csharp


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    if shutil.which("dotnet") is None:
        print(
            "dotnet could not be found on your PATH -- have you installed .NET SDK?",
            file=sys.stderr,
        )
        return 1

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_csharp_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "csharp" / "expected"
    )

    assert main_csharp_expected_dir.exists() and main_csharp_expected_dir.is_dir()

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        for case_dir in live_tests_common.select_case_dirs(
            main_csharp_expected_dir, select
        ):
            print(f"Fast-checking {case_dir.name} ...")

            solution_dir = output_dir / case_dir.name
            live_test_csharp.prepare_solution(case_dir, solution_dir)

            cmd = ["dotnet", "build", "-nologo", "--verbosity", "quiet"]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"in {solution_dir}"
            )
            subprocess.check_call(cmd, cwd=solution_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
