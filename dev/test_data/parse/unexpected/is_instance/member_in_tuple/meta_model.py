@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    pass


class Another_child(Parent, DBC):
    pass


@invariant(
    lambda self: isinstance(self.some_property, (Child, self.Another_child)),
    "Some description.",
)
class Something(DBC):
    some_property: Parent

    def __init__(self, some_property: Parent) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
