from typing import Tuple


class Something:
    nested: Tuple[Tuple[str, int], bool]

    def __init__(self, nested: Tuple[Tuple[str, int], bool]) -> None:
        self.nested = nested


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
