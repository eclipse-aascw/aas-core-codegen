from enum import Enum
from typing import Tuple

from icontract import DBC, invariant

from aas_core_meta.marker import verification


@verification
def some_verification(x: str, y: int) -> bool:
    return (x, y)[0] == x


@invariant(lambda self: self > 0, "Larger than zero")
class Positive_int(int, DBC):
    pass


class Result(Enum):
    Ok = "ok"
    Not_ok = "not-ok"


@abstract
@serialization(with_model_type=True)
class Abstract_item:
    pass


class Some_item(Abstract_item):
    name: str

    def __init__(self, name: str) -> None:
        self.name = name


class Another_item(Abstract_item):
    serial_number: int

    def __init__(self, serial_number: int) -> None:
        self.serial_number = serial_number


@invariant(
    lambda self: self.pair[1] > 0,
    "The second item of the pair must be positive",
)
class Something(DBC):
    pair: Tuple[str, int]
    items: Tuple[Abstract_item, Abstract_item]

    # NOTE (mristin):
    # This mixes a primitive, a concrete class, a polymorphic (abstract) class,
    # the same concrete class again, a constrained primitive and an enumeration
    # literal in a single tuple, to exercise the trickiest tuple shape we support.
    tricky: Tuple[int, Some_item, Abstract_item, Some_item, Positive_int, Result]

    def __init__(
        self,
        pair: Tuple[str, int],
        items: Tuple[Abstract_item, Abstract_item],
        tricky: Tuple[int, Some_item, Abstract_item, Some_item, Positive_int, Result],
    ) -> None:
        self.pair = pair
        self.items = items
        self.tricky = tricky


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
