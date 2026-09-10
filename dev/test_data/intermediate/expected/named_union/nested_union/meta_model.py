@abstract
@serialization(with_model_type=True)
class Some_abstract_class:
    pass


@serialization(with_model_type=True)
class Some_concrete_class(Some_abstract_class):
    pass


@serialization(with_model_type=True)
class Another_concrete_class(Some_abstract_class):
    pass


@serialization(with_model_type=True)
class Yet_another_class:
    pass


Inner_union = Union[Some_abstract_class, Yet_another_class]

Outer_union = Union[Inner_union, Another_concrete_class]


class Something:
    some_property: Outer_union

    def __init__(self, some_property: Outer_union) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
