@invariant(
    lambda self: not ("modelType" in self.value),
    "The value must not contain a reserved ``modelType`` key.",
)
class Something:
    value: JSONObject[str]

    def __init__(self, value: JSONObject[str]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
