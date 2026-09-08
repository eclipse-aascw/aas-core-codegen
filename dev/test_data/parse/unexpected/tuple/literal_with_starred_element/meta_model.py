class Something:
    def __init__(self) -> None:
        pass

    @non_mutating
    def do_something(self, values: Tuple[int, int]) -> Tuple[int, int, int]:
        return (*values, 3)


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
