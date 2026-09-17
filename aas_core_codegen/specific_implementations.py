"""Handle implementation snippets regardless for all implementation languages."""

import pathlib
import re
from typing import cast, Mapping, Tuple, Optional, List

from icontract import require, ensure

from aas_core_codegen.common import Stripped

# noinspection RegExpSimplifiable
IMPLEMENTATION_KEY_RE = re.compile("[a-zA-Z_][a-zA-Z_0-9.]*(/[a-zA-Z_][a-zA-Z_0-9.]*)*")


class ImplementationKey(str):
    """Represent a key in the map of specific implementations."""

    @require(lambda key: IMPLEMENTATION_KEY_RE.fullmatch(key))
    def __new__(cls, key: str) -> "ImplementationKey":
        return cast(ImplementationKey, key)


SpecificImplementations = Mapping[ImplementationKey, Stripped]


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def read_from_directory(
    snippets_dir: pathlib.Path,
) -> Tuple[Optional[SpecificImplementations], Optional[List[str]]]:
    """
    Read all the implementation-specific code snippets from the ``snippets_dir``.

    :return: either the map of the implementations, or the errors
    """
    mapping = dict()  # pylint: disable=use-dict-literal

    errors = []  # type: List[str]
    for pth in snippets_dir.glob("**/*"):
        # NOTE (mristin):
        # Ignore hidden or special files. In particular, we do not want Git-related
        # files such as ``.gitignore`` to be included as snippets.
        if pth.name.startswith("."):
            continue

        if pth.is_dir():
            continue

        maybe_key = (pth.relative_to(snippets_dir).parent / pth.name).as_posix()
        if IMPLEMENTATION_KEY_RE.fullmatch(maybe_key) is None:
            errors.append(
                f"The snippet key is not valid "
                f"according to {IMPLEMENTATION_KEY_RE.pattern}: {maybe_key}"
            )
            continue

        key = ImplementationKey(maybe_key)

        try:
            value = Stripped(pth.read_text(encoding="utf-8").strip())
        except UnicodeDecodeError as error:
            errors.append(
                f"The snippet file is not a valid UTF-8: {pth}. "
                f"This was the decoding error: {error}"
            )
            continue

        mapping[key] = value

    if errors:
        return None, errors

    return mapping, None
