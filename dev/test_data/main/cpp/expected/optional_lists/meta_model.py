from typing import List, Optional

from icontract import DBC

from aas_core_meta.marker import JSONValue


class Item(DBC):
    """Represent something which can be enhanced."""

    text: str

    def __init__(self, text: str) -> None:
        self.text = text


class Something(DBC):
    #: Test an optional list of instances, which have to be wrapped
    optional_items: Optional[List[Item]]

    #: Test an optional list of primitives, which have nothing to wrap
    optional_texts: Optional[List[str]]

    #: Test an optional list of JSON-able values, which have nothing to wrap
    optional_values: Optional[List[JSONValue]]

    def __init__(
        self,
        optional_items: Optional[List[Item]] = None,
        optional_texts: Optional[List[str]] = None,
        optional_values: Optional[List[JSONValue]] = None,
    ) -> None:
        self.optional_items = optional_items
        self.optional_texts = optional_texts
        self.optional_values = optional_values


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
