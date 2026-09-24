from enum import Enum


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


@verification
def some_func(kind: Kind, text: str) -> bool:
    if kind == Kind.Alpha:
        len(text)

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
