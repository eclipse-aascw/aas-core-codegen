class Something:
    value: JSONObject[str, bytearray]

    def __init__(self, value: JSONObject[str, bytearray]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
