@invariant(lambda self: self > 0, "Larger than zero")
class Positive_int(int, DBC):
    pass


class Some_class:
    pass


Some_union = Union[Positive_int, Some_class]


class Something:
    some_property: Some_union

    def __init__(self, some_property: Some_union) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
