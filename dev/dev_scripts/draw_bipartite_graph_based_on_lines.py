"""
Draw a bipartite graph on matching lines in two files.

This is helpful when you want to minimize the diffs. Unfortunately, ``diff`` is not
really a good tool when it comes to re-shuffling of the blocks.
"""

import argparse
import pathlib
import sys


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ours", help="path to the first file", required=True)
    parser.add_argument("--theirs", help="path to the second file", required=True)
    args = parser.parse_args()

    ours_pth = pathlib.Path(args.ours)
    theirs_pth = pathlib.Path(args.theirs)

    our_lines = ours_pth.read_text(encoding="utf-8").splitlines()
    their_lines = theirs_pth.read_text(encoding="utf-8").splitlines()

    their_lines_by_index = {line: i for i, line in enumerate(their_lines)}

    for i, line in enumerate(our_lines):
        their_i = their_lines_by_index.get(line)
        if their_i is not None:
            print(f"Ours {i+1:4d} to theirs {their_i:4d}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
