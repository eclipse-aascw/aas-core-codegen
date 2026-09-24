@serialization(with_model_type=True)
class Parent:
    pass


@serialization(with_model_type=True)
class Child(Parent):
    pass


@serialization(with_model_type=True)
class Grandchild(Child):
    pass


@serialization(with_model_type=True)
class Unrelated:
    pass


Some_union = Union[Grandchild, Unrelated, Parent, Child]


class Something:
    some_property: Some_union

    def __init__(self, some_property: Some_union) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
