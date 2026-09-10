@serialization(with_model_type=True)
class Some_class:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property


@serialization(with_model_type=True)
class Another_class:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property


Some_union = Union[Some_class, Another_class]


class Something:
    some_property: Tuple[str, Some_union]

    def __init__(self, some_property: Tuple[str, Some_union]) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
