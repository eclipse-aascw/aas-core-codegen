from enum import Enum
from typing import Tuple

from icontract import invariant


class Result(Enum):
    Ok = "ok"
    Fail = "fail"


class Something:
    some_results: Tuple[Result, Result]

    def __init__(self, some_results: Tuple[Result, Result]) -> None:
        self.some_results = some_results


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
