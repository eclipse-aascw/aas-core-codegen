from enum import Enum


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


@verification
def some_func(number: float) -> bool:
    if number == 1.0:
        return False

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
