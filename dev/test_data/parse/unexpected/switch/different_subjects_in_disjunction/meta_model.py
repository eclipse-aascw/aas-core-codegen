from enum import Enum


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


@verification
def some_func(text: str, other: str) -> bool:
    if text == "a" or other == "b":
        return False

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
