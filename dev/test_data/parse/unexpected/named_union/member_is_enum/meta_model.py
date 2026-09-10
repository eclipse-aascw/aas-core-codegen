from enum import Enum
from typing import Union


class Some_enum(Enum):
    some_literal = "some_literal"


class Some_class:
    pass


Some_union = Union[Some_class, Some_enum]


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
