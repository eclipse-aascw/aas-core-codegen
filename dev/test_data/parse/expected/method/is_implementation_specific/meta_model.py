class Something:
    x: int

    @implementation_specific
    def do_something(self) -> int:
        return self.x

    def __init__(self, x: int) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
