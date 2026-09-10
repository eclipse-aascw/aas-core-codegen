from typing import Union


class Some_class:
    pass


class Another_class:
    pass


Some_union = Union[Some_class, Another_class]
Yet_another_union = Union[Some_union, Some_class]


class Something:
    some_property: Yet_another_union


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
