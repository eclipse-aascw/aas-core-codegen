from icontract import invariant


@invariant(lambda self: len(self) > 0, "At least one character")
class Non_empty_string(str):
    pass


class Something:
    value: JSONObject[Non_empty_string]

    def __init__(self, value: JSONObject[Non_empty_string]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
