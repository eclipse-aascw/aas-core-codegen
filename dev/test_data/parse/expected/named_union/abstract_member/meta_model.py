from typing import Union

from aas_core_meta.marker import abstract


@abstract
class Some_abstract_class:
    pass


class Some_concrete_class(Some_abstract_class):
    pass


class Another_concrete_class(Some_abstract_class):
    pass


class Yet_another_class:
    pass


Some_union = Union[Some_abstract_class, Yet_another_class]


class Something:
    some_property: Some_union


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
