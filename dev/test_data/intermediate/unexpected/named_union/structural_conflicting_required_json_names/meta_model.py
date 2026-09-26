class Some_class:
    some_property: Annotated[str, json_name("shared")]

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property


class Another_class:
    another_property: Annotated[str, json_name("shared")]

    def __init__(self, another_property: str) -> None:
        self.another_property = another_property


Some_union = Union[Some_class, Another_class]


class Something:
    some_property: Some_union

    def __init__(self, some_property: Some_union) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
