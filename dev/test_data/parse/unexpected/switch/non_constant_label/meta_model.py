from enum import Enum


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


@verification
def some_func(kind: Kind, other: Kind) -> bool:
    if kind == other:
        return False

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
