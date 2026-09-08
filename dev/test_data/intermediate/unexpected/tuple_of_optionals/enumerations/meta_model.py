from enum import Enum
from typing import Optional, Tuple

from icontract import invariant


class Answer(Enum):
    Ok = "ok"
    NotOk = "not-ok"


class Something:
    maybe_answers: Tuple[Optional[Answer], Answer]

    def __init__(self, maybe_answers: Tuple[Optional[Answer], Answer]) -> None:
        self.maybe_answers = maybe_answers


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
