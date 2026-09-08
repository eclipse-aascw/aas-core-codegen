from typing import Tuple

from icontract import invariant


@invariant(lambda self: self > 0, "Larger than zero")
class Positive(int):
    pass


class Something:
    some_positives: Tuple[Positive, Positive]

    def __init__(self, some_positives: Tuple[Positive, Positive]) -> None:
        self.some_positives = some_positives


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
