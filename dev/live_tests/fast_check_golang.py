# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""
Compile the Golang generated code, but do not run the tests.

This is meant to fail fast before running the slow live tests. The projects are
prepared exactly as in the live test so that both can share ``--output_dir``.
"""

import argparse
import os
import pathlib
import subprocess
import sys
from typing import Optional, Pattern

from live_tests import common as live_tests_common
from live_tests import live_test_golang


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    goimports_path = live_test_golang.find_goimports()
    if goimports_path is None:
        return 1

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_golang_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "golang" / "expected"
    )

    assert main_golang_expected_dir.exists() and main_golang_expected_dir.is_dir()

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        for case_dir in live_tests_common.select_case_dirs(
            main_golang_expected_dir, select
        ):
            print(f"Fast-checking {case_dir.name} ...")

            module_dir = output_dir / case_dir.name
            live_test_golang.prepare_module(case_dir, module_dir, goimports_path)

            # NOTE (mristin):
            # We compile the tests, but pass ``true`` as the test runner instead of
            # running the test binaries. Unlike ``go vet``, this runs only the subset
            # of vet checks which ``go test`` runs in the live test.
            cmd = ["go", "test", "-exec", "true", "./..."]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"in {module_dir}"
            )
            subprocess.check_call(cmd, cwd=module_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
