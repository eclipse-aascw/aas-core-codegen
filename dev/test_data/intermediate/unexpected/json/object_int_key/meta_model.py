class Something:
    value: JSONObject[int, JSONValue]

    def __init__(self, value: JSONObject[int, JSONValue]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
