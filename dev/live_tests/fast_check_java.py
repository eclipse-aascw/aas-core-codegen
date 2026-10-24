"""
Compile the Java generated code with ``javac``, but do not run the tests.

This is meant to fail fast before running the slow live tests. The projects are
prepared exactly as in the live test so that both can share ``--output_dir``.

We invoke Maven only once to resolve the classpath of the dependencies, and
compile each case directly with ``javac`` to avoid the overhead of Maven.
"""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Optional, Pattern

from live_tests import common as live_tests_common
from live_tests import live_test_java


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    for executable in ["mvn", "javac"]:
        if shutil.which(executable) is None:
            print(
                f"{executable} could not be found on your PATH -- "
                f"have you installed Maven and JDK?",
                file=sys.stderr,
            )
            return 1

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_java_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "java" / "expected"
    )

    assert main_java_expected_dir.exists() and main_java_expected_dir.is_dir()

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        # NOTE (mristin):
        # All the cases share the same dependencies, so we resolve the classpath
        # only once, lazily with the first case.
        classpath: Optional[str] = None

        for case_dir in live_tests_common.select_case_dirs(
            main_java_expected_dir, select
        ):
            print(f"Fast-checking {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            live_test_java.prepare_project(case_dir, project_dir)

            if classpath is None:
                classpath_path = output_dir / "fast_check_classpath.txt"
                cmd = [
                    "mvn",
                    "--batch-mode",
                    "--quiet",
                    "dependency:build-classpath",
                    f"-Dmdep.outputFile={classpath_path}",
                ]
                print(
                    f"Running {live_tests_common.escape_and_join_command(cmd)} "
                    f"in {project_dir}"
                )
                subprocess.check_call(cmd, cwd=project_dir)

                classpath = classpath_path.read_text(encoding="utf-8").strip()

            # NOTE (mristin):
            # We pass the sources through an argument file to avoid hitting
            # the limit on the command-line length.
            sources_path = project_dir / "target" / "fast_check_sources.txt"
            sources_path.parent.mkdir(exist_ok=True)
            sources_path.write_text(
                "\n".join(
                    f'"{path.relative_to(project_dir).as_posix()}"'
                    for path in sorted((project_dir / "src").glob("**/*.java"))
                ),
                encoding="utf-8",
            )

            cmd = [
                "javac",
                "-proc:none",
                "--release",
                "17",
                "-encoding",
                "UTF-8",
                "-cp",
                classpath,
                "-d",
                "target/fast_check_classes",
                f"@{sources_path.relative_to(project_dir)}",
            ]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"in {project_dir}"
            )
            subprocess.check_call(cmd, cwd=project_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
