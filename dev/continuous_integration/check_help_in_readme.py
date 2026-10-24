#!/usr/bin/env python3

"""Check that the help snippets in the Readme coincide with the actual output."""
import argparse
import difflib
import os
import pathlib
import re
import subprocess
import sys
from typing import List, Tuple, Optional

import icontract


class Block:
    """Represent a block in the readme that needs to be checked."""

    @icontract.require(lambda command: command != "")
    @icontract.require(
        lambda start_line_idx, end_line_idx: start_line_idx <= end_line_idx
    )
    def __init__(self, command: str, start_line_idx: int, end_line_idx: int) -> None:
        """
        Initialize with the given values.

        :param command: help command
        :param start_line_idx: index of the first relevant line
        :param end_line_idx: index of the first line excluded from the block
        """
        self.command = command
        self.start_line_idx = start_line_idx
        self.end_line_idx = end_line_idx


HELP_STARTS_RE = re.compile(r"^.. Help starts: (?P<command>.*)$")


def parse_readme(lines: List[str]) -> Tuple[List[Block], List[str]]:
    """
    Parse the code blocks that represent help commands in the Readme.

    :param lines: lines of the readme file
    :return: (help blocks, errors if any)
    """
    blocks: List[Block] = []
    errors: List[str] = []

    i = 0
    while i < len(lines):
        mtch = HELP_STARTS_RE.match(lines[i])
        if mtch:
            command = mtch.group("command")
            help_ends = f".. Help ends: {command}"
            try:
                end_index = lines.index(help_ends, i)
            except ValueError:
                end_index = -1

            if end_index == -1:
                return [], [f"Could not find_our_type the end marker {help_ends!r}"]

            blocks.append(
                Block(command=command, start_line_idx=i + 1, end_line_idx=end_index)
            )

            i = end_index + 1

        else:
            i += 1

    return blocks, errors


def capture_output_lines(command: str) -> List[str]:
    """Capture the output of a help command."""
    command_parts = command.split(" ")
    if command_parts[0] in ["python", "python3"]:
        # We need to replace "python" with "sys.executable" on Windows as
        # the environment is not properly inherited.
        command_parts[0] = sys.executable

    proc: Optional[subprocess.Popen[str]] = None
    try:
        proc = subprocess.Popen(
            command_parts,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
    except Exception as exception:
        raise RuntimeError(
            f"Failed to start the command {command_parts!r} "
            f"derived from the command {command!r} in the document"
        ) from exception

    assert proc is not None
    with proc:
        output, err = proc.communicate()
        if err:
            raise RuntimeError(
                f"The command {command!r} failed with exit code {proc.returncode} and "
                f"stderr:\n{err}"
            )

        return output.splitlines()


def output_lines_to_code_block(output_lines: List[str]) -> List[str]:
    """Translate the output of a help command to a RST code block."""
    result = (
        [".. code-block::", ""]
        + ["    " + output_line for output_line in output_lines]
        + [""]
    )

    result = [line.rstrip() for line in result]
    return result


def report_a_difference(
    got_lines: List[str], expected_lines: List[str]
) -> Optional[str]:
    """
    Report a difference between the ``got`` and ``expected``.

    Return None if no difference.
    """
    if got_lines == expected_lines:
        return None

    diff = difflib.ndiff(got_lines, expected_lines)
    return "\n".join(diff)


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overwrite",
        help="If set, overwrite the relevant part of README in-place.",
        action="store_true",
    )

    args = parser.parse_args()
    overwrite = bool(args.overwrite)

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent
    pth = repo_root / "README.rst"

    text = pth.read_text(encoding="utf-8")
    lines = text.splitlines()

    blocks, errors = parse_readme(lines=lines)
    if errors:
        print(f"One or more errors in {pth}:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)

        return -1

    if len(blocks) == 0:
        return 0

    if overwrite:
        result: List[str] = []

        previous_block: Optional[Block] = None
        for block in blocks:
            output_lines = capture_output_lines(command=block.command)
            code_block_lines = output_lines_to_code_block(output_lines=output_lines)

            if previous_block is None:
                result.extend(lines[: block.start_line_idx])
            else:
                result.extend(lines[previous_block.end_line_idx : block.start_line_idx])

            result.extend(code_block_lines)
            previous_block = block

        assert previous_block is not None
        result.extend(lines[previous_block.end_line_idx :])
        result.append("")  # new line at the end of file

        pth.write_text("\n".join(result), encoding="utf-8")

    else:
        for block in blocks:
            output_lines = capture_output_lines(command=block.command)
            code_block_lines = output_lines_to_code_block(output_lines=output_lines)

            expected_lines = lines[block.start_line_idx : block.end_line_idx]
            expected_lines = [line.rstrip() for line in expected_lines]

            diff_error = report_a_difference(
                got_lines=code_block_lines, expected_lines=expected_lines
            )
            if diff_error is not None:
                print(diff_error, file=sys.stderr)
                return -1

    return 0


if __name__ == "__main__":
    sys.exit(main())
