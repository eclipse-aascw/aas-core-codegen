from typing import List


class Something:
    value: JSONObject[str, List[str]]

    def __init__(self, value: JSONObject[str, List[str]]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
