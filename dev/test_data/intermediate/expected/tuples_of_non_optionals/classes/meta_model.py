from typing import Tuple

from icontract import invariant


@abstract
@serialization(with_model_type=True)
class AbstractItem:
    pass


class SomeItem(AbstractItem):
    name: str

    def __init__(self, name: str) -> None:
        self.name = name


class AnotherItem(AbstractItem):
    serial_number: int

    def __init__(self, serial_number: int) -> None:
        self.serial_number = serial_number


class Something:
    some_items: Tuple[AbstractItem, AbstractItem]

    def __init__(self, some_items: Tuple[AbstractItem, AbstractItem]) -> None:
        self.some_items = some_items


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
