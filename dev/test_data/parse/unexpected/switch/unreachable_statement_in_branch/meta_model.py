from enum import Enum


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


@verification
def some_func(kind: Kind) -> bool:
    x = True
    if kind == Kind.Alpha:
        return False
        x = False

    return x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
