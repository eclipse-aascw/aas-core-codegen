"""Split the given file in blocks and convert each block into a Stripped one."""

import argparse
import enum
import pathlib
import re
import sys
from typing import List

from aas_core_codegen.common import assert_never


def _split_in_blocks(text: str, indention: str) -> List[str]:
    """
    Split the given text into blocks based on indention and empty lines.

    >>> _split_in_blocks("", indention="  ")
    []

    >>> _split_in_blocks("single line", indention="  ")
    ['single line']

    >>> _split_in_blocks("line1\\n\\nline2", indention="  ")
    ['line1', 'line2']

    >>> _split_in_blocks("line1\\n\\n\\nline2", indention="  ")
    ['line1', 'line2']

    >>> some_text = '''A {
    ...   something
    ...
    ...   else
    ... }
    ...
    ... B {
    ...   something
    ... }'''
    >>> blocks = _split_in_blocks(some_text, indention="  ")
    >>> len(blocks)
    2
    >>> print(blocks[0])
    A {
      something
    <BLANKLINE>
      else
    }
    >>> print(blocks[1])
    B {
      something
    }
    """
    lines = text.splitlines()
    blocks: List[str] = []
    accumulator: List[str] = []
    in_indented_section = False

    for line in lines:
        if len(line.strip()) == 0:
            if in_indented_section:
                # NOTE (mristin):
                # We keep empty lines within indented sections as part of current block.
                accumulator.append(line)
            else:
                # NOTE (mristin):
                # An empty line at top level separates two blocks.
                if len(accumulator) > 0:
                    blocks.append("\n".join(accumulator))
                    accumulator = []
        else:
            if line.startswith(indention):
                in_indented_section = True
                accumulator.append(line)
            else:
                # NOTE (mristin):
                # A non-indented line means it finishes a block, and we are back
                # at top level.
                in_indented_section = False
                accumulator.append(line)

    if len(accumulator) > 0:
        blocks.append("\n".join(accumulator))

    return blocks


class Indention(enum.Enum):
    """List the possible indentations to be considered."""

    TWO_SPACES = "two-spaces"
    FOUR_SPACES = "four-spaces"
    TABS = "tabs"


def main() -> int:
    """Execute the main routine."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        help="Path to the file",
        required=True,
    )
    parser.add_argument(
        "--indention",
        help="What character sequence is considered indention",
        default=Indention.FOUR_SPACES.value,
        choices=[literal.value for literal in Indention],
    )
    args = parser.parse_args()

    path = pathlib.Path(args.path)

    str_to_indention = {literal.value: literal for literal in Indention}

    indention_literal = str_to_indention[args.indention]

    if indention_literal is Indention.TWO_SPACES:
        indention = " " * 2
    elif indention_literal is Indention.FOUR_SPACES:
        indention = " " * 4
    elif indention_literal is Indention.TABS:
        indention = "\t"
    else:
        # noinspection PyTypeChecker
        assert_never(indention_literal)

    text = path.read_text(encoding="utf-8")

    blocks = _split_in_blocks(text, indention=indention)

    for block in blocks:
        needs_f = any(
            re.match(r"^.*{\s+[a-zA-Z_0-9]+\s*}", line) is not None
            or line.startswith(indention)
            for line in block.splitlines()
        )

        escaped_block = block.replace("\\", "\\\\")

        if needs_f:
            escaped_block = escaped_block.replace("{", "{{").replace("}", "}}")

        lines = escaped_block.split("\n")

        # NOTE (mristin):
        # We replace indentation with {I}, {II}, etc. placeholders.
        processed_lines = []

        for line in lines:
            if len(line.strip()) == 0:
                processed_lines.append(line)
            else:
                indent_count = 0
                pos = 0
                while pos + len(indention) <= len(line) and line.startswith(
                    indention, pos
                ):
                    indent_count += 1
                    pos += len(indention)

                if indent_count > 0:
                    placeholder = "{" + "I" * indent_count + "}"
                    processed_line = placeholder + line[len(indention) * indent_count :]
                else:
                    processed_line = line

                processed_lines.append(processed_line)

        processed_block = "\n".join(processed_lines)

        maybe_f = "f" if needs_f else ""

        print(
            f"""\
Stripped(
    {maybe_f}'''\\
{processed_block}'''
),"""
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
