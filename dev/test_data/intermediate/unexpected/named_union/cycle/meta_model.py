class Some_class:
    pass


class Another_class:
    pass


Some_union = Union[Another_union, Some_class]
Another_union = Union[Some_union, Another_class]


class Something:
    some_property: Some_union

    def __init__(self, some_property: Some_union) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
