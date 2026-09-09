class Something:
    def __init__(self) -> None:
        pass

    @non_mutating
    def make_pair(self) -> Tuple[str, int]:
        return ("oi", 3)


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
