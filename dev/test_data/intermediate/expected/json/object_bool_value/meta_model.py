class Something:
    value: JSONObject[str, bool]

    def __init__(self, value: JSONObject[str, bool]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
