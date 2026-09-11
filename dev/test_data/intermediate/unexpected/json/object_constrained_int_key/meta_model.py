from icontract import invariant


@invariant(lambda self: self > 0, "Larger than zero")
class Positive_int(int):
    pass


class Something:
    value: JSONObject[Positive_int]

    def __init__(self, value: JSONObject[Positive_int]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
