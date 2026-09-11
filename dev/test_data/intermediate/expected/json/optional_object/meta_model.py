from typing import Optional


class Something:
    value: Optional[JSONObject[str, JSONValue]]

    def __init__(
        self, value: Optional[JSONObject[str, JSONValue]] = None
    ) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
