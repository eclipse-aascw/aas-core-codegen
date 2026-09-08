from typing import Tuple


class Something:
    name_and_count: Tuple[str, int]

    def __init__(self, name_and_count: Tuple[str, int]) -> None:
        self.name_and_count = name_and_count


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
