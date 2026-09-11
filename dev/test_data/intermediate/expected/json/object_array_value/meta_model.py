class Something:
    value: JSONObject[str, JSONArray]

    def __init__(self, value: JSONObject[str, JSONArray]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
