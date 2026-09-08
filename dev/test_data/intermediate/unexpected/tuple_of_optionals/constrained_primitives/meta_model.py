from typing import Optional, Tuple

from icontract import invariant


@invariant(lambda self: self > 0, "Larger than zero")
class Positive(int):
    pass


class Something:
    maybe_positives: Tuple[Optional[Positive], Positive]

    def __init__(self, maybe_positives: Tuple[Optional[Positive], Positive]) -> None:
        self.maybe_positives = maybe_positives


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
