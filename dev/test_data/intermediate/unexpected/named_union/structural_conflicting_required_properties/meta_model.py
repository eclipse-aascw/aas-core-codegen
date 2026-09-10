class Some_class:
    shared_property: str

    def __init__(self, shared_property: str) -> None:
        self.shared_property = shared_property


class Another_class:
    shared_property: str

    def __init__(self, shared_property: str) -> None:
        self.shared_property = shared_property


Some_union = Union[Some_class, Another_class]


class Something:
    some_property: Some_union

    def __init__(self, some_property: Some_union) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
