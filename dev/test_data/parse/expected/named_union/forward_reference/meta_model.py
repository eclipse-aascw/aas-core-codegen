from typing import Union

# The named union is defined before its members, which are only defined later
# in the meta-model. This is expected to work, as the members are resolved
# only after the whole meta-model has been parsed.
Some_union = Union[Some_class, Another_class]


class Some_class:
    pass


class Another_class:
    pass


class Something:
    some_property: Some_union


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
