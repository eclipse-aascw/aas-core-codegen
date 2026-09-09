from typing import Optional, Tuple

from icontract import invariant


class Item:
    pass


class Something:
    maybe_items: Tuple[Optional[Item], Item]

    def __init__(self, maybe_items: Tuple[Optional[Item], Item]) -> None:
        self.maybe_items = maybe_items


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
