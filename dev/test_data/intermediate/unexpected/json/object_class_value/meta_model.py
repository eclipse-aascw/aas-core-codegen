class Some_class:
    pass


class Something:
    value: JSONObject[str, Some_class]

    def __init__(self, value: JSONObject[str, Some_class]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
