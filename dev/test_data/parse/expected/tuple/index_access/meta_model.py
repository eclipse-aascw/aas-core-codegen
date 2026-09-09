class Something:
    def __init__(self) -> None:
        pass

    @non_mutating
    def first(self, pair: Tuple[str, int]) -> str:
        return pair[0]


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
