@invariant(
    lambda self: all(isinstance(item, str) for item in self.value.values()),
    "All the values must be strings.",
)
class Something:
    value: JSONObject[str]

    def __init__(self, value: JSONObject[str]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
