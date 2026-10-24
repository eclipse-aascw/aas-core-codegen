"""Compare the rendered regexes against their original form in ``source.py``."""

import os
import pathlib
import sys
from typing import Optional


def main() -> int:
    """Execute the main routine."""

    repo_dir = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent
    test_cases_dir = repo_dir / "dev/test_data/parse_retree"
    expected_pths = sorted((test_cases_dir / "expected").glob("**/source.py"))

    for pth in expected_pths:
        rendered_regex_pth = pth.parent / "rendered_regex.txt"

        source = pth.read_text(encoding="utf-8").strip()

        source_stem: Optional[str] = None
        if source.startswith('"') and source.endswith('"'):
            source_stem = source[1:-1]
        elif source.startswith('f"') and source.endswith('"'):
            source_stem = source[2:-1]
        else:
            pass

        rendered = rendered_regex_pth.read_text(encoding="utf-8")
        rendered_repr_stem = repr(rendered)[1:-1]

        if source_stem is None or rendered_repr_stem != source_stem:
            print()
            print(str(pth))
            print(source)
            print(repr(rendered))

    return 0


if __name__ == "__main__":
    sys.exit(main())
