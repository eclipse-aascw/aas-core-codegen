class Something:
    value: JSONObject[str, JSONValue]

    def __init__(self, value: JSONObject[str, JSONValue]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
