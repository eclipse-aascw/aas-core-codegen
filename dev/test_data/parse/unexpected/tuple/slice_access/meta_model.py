class Something:
    def __init__(self) -> None:
        pass

    @non_mutating
    def do_something(self, pair: Tuple[int, int]) -> int:
        return pair[0:1]


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
