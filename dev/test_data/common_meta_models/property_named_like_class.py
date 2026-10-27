from icontract import DBC


class Something(DBC):
    something: str

    def __init__(self, something: str) -> None:
        self.something = something


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
