# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""
Type-check and lint the TypeScript generated code, but do not run the tests.

This is meant to fail fast before running the slow live tests. The projects are
prepared exactly as in the live test so that both can share ``--output_dir``.
Unlike the live test, we skip bundling and running the tests.
"""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Optional, Pattern

from live_tests import common as live_tests_common
from live_tests import live_test_typescript


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    if shutil.which("npm") is None:
        print(
            "npm could not be found on your PATH -- have you installed Node.js?",
            file=sys.stderr,
        )
        return 1

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_typescript_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "typescript" / "expected"
    )

    assert (
        main_typescript_expected_dir.exists() and main_typescript_expected_dir.is_dir()
    )

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        live_test_typescript.install_dependencies(output_dir)

        for case_dir in live_tests_common.select_case_dirs(
            main_typescript_expected_dir, select
        ):
            print(f"Fast-checking {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            live_test_typescript.prepare_project(case_dir, project_dir)

            # NOTE (mristin):
            # The ``tsconfig.json`` of the live test covers only the sources, while
            # ts-jest type-checks the tests only once they run. Hence, we include
            # the tests explicitly.
            (project_dir / "tsconfig.fast_check.json").write_text(
                """\
{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "noEmit": true,
    "emitDeclarationOnly": false,
    "declaration": false,
    "declarationMap": false
  },
  "include": [
    "src/**/*",
    "test/**/*"
  ]
}
""",
                encoding="utf-8",
            )

            for cmd in [
                ["npx", "tsc", "--project", "tsconfig.fast_check.json"],
                ["npm", "run", "format"],
                ["npm", "run", "lint"],
            ]:
                print(
                    f"Running {live_tests_common.escape_and_join_command(cmd)} "
                    f"in {project_dir}"
                )
                subprocess.check_call(cmd, cwd=project_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
