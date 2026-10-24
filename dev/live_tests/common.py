"""Provide common functionality shared across the live tests."""
import argparse
import contextlib
import os
import pathlib
import re
import shlex
import shutil
import tempfile
from typing import Sequence, Final, Optional, Pattern, List, Iterator


def escape_and_join_command(command: Sequence[str]) -> str:
    """Prepare the command and join it so that you can copy+paste+run it in console."""
    return " ".join(shlex.quote(part) for part in command)


_REPO_ROOT: Final[pathlib.Path] = pathlib.Path(
    os.path.realpath(__file__)
).parent.parent.parent


def common_test_data_dir_for_case(case_name: str) -> pathlib.Path:
    """Determine the path to the shared test data directory for the given case."""
    return (
        _REPO_ROOT / "dev" / "test_data" / "live_tests" / "common_test_data" / case_name
    )


def add_output_dir_argument(parser: argparse.ArgumentParser) -> None:
    """Add the ``--output_dir`` argument to ``parser``."""
    parser.add_argument(
        "--output_dir",
        help=(
            "Path to where all the assembled project data including the test data "
            "should be copied to. If not specified, everything will be put into "
            "a temporary directory and deleted after the test. The live tests and "
            "the fast checks of the same language can share the output directory."
        ),
    )


@contextlib.contextmanager
def open_output_dir(output_dir: Optional[str]) -> Iterator[pathlib.Path]:
    """
    Create ``output_dir``, or a temporary directory if ``output_dir`` is not given.

    The temporary directory is deleted on exit.
    """
    if output_dir is None:
        with tempfile.TemporaryDirectory() as temp_dir:
            yield pathlib.Path(temp_dir)
    else:
        path = pathlib.Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        yield path


def _compile_select(text: str) -> Pattern[str]:
    """Compile the ``--select`` argument, and report errors to argparse."""
    try:
        return re.compile(text)
    except re.error as exception:
        raise argparse.ArgumentTypeError(
            f"Invalid regular expression {text!r}: {exception}"
        ) from exception


def add_select_argument(parser: argparse.ArgumentParser) -> None:
    """Add the ``--select`` argument, parsed as a regular expression, to ``parser``."""
    parser.add_argument(
        "--select",
        help="Run only the test cases which match the regular expression",
        type=_compile_select,
    )


def select_case_dirs(
    expected_dir: pathlib.Path, select: Optional[Pattern[str]]
) -> List[pathlib.Path]:
    """
    List the case directories in ``expected_dir`` matching ``select``.

    The skipped cases are reported to STDOUT.
    """
    result: List[pathlib.Path] = []

    for case_dir in sorted(path for path in expected_dir.iterdir() if path.is_dir()):
        if select is not None and select.match(case_dir.name) is None:
            print(f"Skipping {case_dir.name} since not selected.")
            continue

        result.append(case_dir)

    return result


def copy_expected_output(
    expected_output_dir: pathlib.Path, target_dir: pathlib.Path
) -> None:
    """Copy the generated files from ``expected_output_dir`` to ``target_dir``."""
    print(f"Copying all the files from {expected_output_dir} to {target_dir} ...")
    for path in sorted(
        path
        for path in expected_output_dir.glob("**/*")
        if path.name != "stdout.txt" and path.is_file()
    ):
        target_path = target_dir / (path.relative_to(expected_output_dir))

        # NOTE (mristin):
        # We check whether there is a change to avoid unnecessary recompilations
        # due to modification timestamps of the files.

        if not target_path.exists() or target_path.read_text(
            encoding="utf-8"
        ) != path.read_text(encoding="utf-8"):
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, target_path)
