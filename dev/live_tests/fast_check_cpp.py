"""
Check the C++ generated code with ``-fsyntax-only``, but do not build it.

This is meant to fail fast before running the slow live tests. The projects are
prepared and configured exactly as in the live test so that both can share
``--output_dir``.

We run the compile commands exported by CMake with ``-fsyntax-only`` in parallel.
The compiler thus performs the full semantic analysis, including template
instantiation, but neither generates nor links the code. This saves both time and
disk space, but we miss the linker errors.

Set ``CC``, ``CXX`` and ``CXXFLAGS`` as for the live test, *e.g.*,
``CC=clang CXX=clang++ CXXFLAGS=-DDEBUG``.
"""

import argparse
import concurrent.futures
import json
import os
import pathlib
import shlex
import subprocess
import sys
from typing import AbstractSet, Any, Final, List, Mapping, Optional, Pattern

from live_tests import common as live_tests_common
from live_tests import live_test_cpp

#: Flags, followed by a value, which we remove from the compile commands since
#: they produce files
_FLAGS_WITH_OUTPUT: Final[AbstractSet[str]] = frozenset(["-o", "-MF", "-MT", "-MQ"])

#: Flags which we remove from the compile commands since they produce files
_FLAGS_PRODUCING_DEPENDENCY_FILES: Final[AbstractSet[str]] = frozenset(["-MD", "-MMD"])


def _check_translation_unit(entry: Mapping[str, Any]) -> Optional[str]:
    """
    Run the compile command ``entry`` with ``-fsyntax-only``.

    Return the output of the compiler on failure, or ``None`` on success.
    """
    command = (
        list(entry["arguments"])
        if "arguments" in entry
        else shlex.split(entry["command"])
    )

    cmd: List[str] = []
    skip_next = False
    for part in command:
        if skip_next:
            skip_next = False
        elif part in _FLAGS_WITH_OUTPUT:
            skip_next = True
        elif part not in _FLAGS_PRODUCING_DEPENDENCY_FILES:
            cmd.append(part)

    cmd.append("-fsyntax-only")

    completed = subprocess.run(
        cmd,
        cwd=entry["directory"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        check=False,
    )

    if completed.returncode != 0:
        return (
            f"Failed to run {live_tests_common.escape_and_join_command(cmd)} "
            f"in {entry['directory']}:\n{completed.stdout}"
        )

    return None


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    parser.add_argument(
        "--jobs",
        help="Number of translation units to check in parallel",
        type=int,
        default=os.cpu_count() or 1,
    )
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select
    jobs = int(args.jobs)

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_cpp_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "cpp" / "expected"
    )

    assert main_cpp_expected_dir.exists() and main_cpp_expected_dir.is_dir()

    vcpkg_cmake = live_test_cpp.find_vcpkg_cmake()
    if vcpkg_cmake is None:
        return 1

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        for case_dir in live_tests_common.select_case_dirs(
            main_cpp_expected_dir, select
        ):
            print(f"Fast-checking {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            live_test_cpp.prepare_project(case_dir, project_dir, vcpkg_cmake)

            entries = json.loads(
                (project_dir / "build" / "compile_commands.json").read_text(
                    encoding="utf-8"
                )
            )

            print(
                f"Checking {len(entries)} translation unit(s) "
                f"with -fsyntax-only in {jobs} job(s) ..."
            )

            with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
                future_to_file = {
                    executor.submit(_check_translation_unit, entry): entry["file"]
                    for entry in entries
                }

                for future in concurrent.futures.as_completed(future_to_file):
                    error = future.result()
                    if error is not None:
                        print(error, file=sys.stderr)

                        # NOTE (mristin):
                        # We fail fast, but still need to wait for the running
                        # checks when leaving the executor.
                        executor.shutdown(cancel_futures=True)
                        return 1

                    print(f"Checked {future_to_file[future]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
