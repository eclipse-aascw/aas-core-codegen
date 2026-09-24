@serialization(with_model_type=True)
class First(DBC):
    pass


@serialization(with_model_type=True)
class Second(DBC):
    pass


Value = Union[First, Second]


@serialization(with_model_type=True)
class Underlying_of_value(DBC):
    """Collide with the function ``UnderlyingOfValue`` generated for ``Value``."""


class Something(DBC):
    value: Value
    underlying_of_value: Underlying_of_value

    def __init__(self, value: Value, underlying_of_value: Underlying_of_value) -> None:
        self.value = value
        self.underlying_of_value = underlying_of_value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
