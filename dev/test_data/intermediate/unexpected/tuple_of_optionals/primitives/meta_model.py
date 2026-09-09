from typing import Optional, Tuple


class Something:
    maybe_pair: Tuple[Optional[str], int]

    def __init__(self, maybe_pair: Tuple[Optional[str], int]) -> None:
        self.maybe_pair = maybe_pair


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
