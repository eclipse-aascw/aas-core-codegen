from typing import Union


class Some_class:
    pass


class Another_class:
    pass


Some_union = Union[Some_class, Another_class]


class Something:
    some_property: Some_union


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
