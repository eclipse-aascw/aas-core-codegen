class Some_enum(Enum):
    Some_literal = "some-literal"


@invariant(lambda self: len(self) > 0, "Some constraint.")
class Some_constrained_primitive(str, DBC):
    pass


@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    pass


class Another_child(Parent, DBC):
    pass


Some_union = Union[Child, Another_child]


@invariant(
    lambda self: isinstance(self.some_property, Unknown_class),
    "Some description.",
)
class Something(DBC):
    some_property: Parent

    def __init__(self, some_property: Parent) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
