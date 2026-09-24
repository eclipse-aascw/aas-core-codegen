from enum import Enum


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


@verification
def some_func(text: str) -> bool:
    if text in ():
        return False

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
