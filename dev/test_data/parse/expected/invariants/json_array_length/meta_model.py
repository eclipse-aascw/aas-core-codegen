@invariant(
    lambda self: len(self.values) >= 1,
    "There must be at least one value.",
)
class Something:
    values: JSONArray

    def __init__(self, values: JSONArray) -> None:
        self.values = values


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
