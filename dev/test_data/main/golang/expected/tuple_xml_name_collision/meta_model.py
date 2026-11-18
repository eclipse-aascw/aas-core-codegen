from typing import Tuple


class V2:
    """Share an XML name with the second, primitive item of a tuple."""

    text: str

    def __init__(self, text: str) -> None:
        self.text = text


class Something:
    pair: Tuple[V2, float]

    def __init__(self, pair: Tuple[V2, float]) -> None:
        self.pair = pair


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
