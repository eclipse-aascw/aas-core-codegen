from typing import Tuple


class Something:
    value: Tuple[str, JSONValue, JSONArray, JSONObject[str]]

    def __init__(
        self, value: Tuple[str, JSONValue, JSONArray, JSONObject[str]]
    ) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
