class Some_class:
    unique_to_some: str

    def __init__(self, unique_to_some: str) -> None:
        self.unique_to_some = unique_to_some


class Another_class:
    unique_to_another: str

    def __init__(self, unique_to_another: str) -> None:
        self.unique_to_another = unique_to_another


Some_union = Union[Some_class, Another_class]


class Something:
    some_property: Some_union

    def __init__(self, some_property: Some_union) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
