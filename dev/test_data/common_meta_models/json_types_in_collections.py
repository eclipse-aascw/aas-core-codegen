from typing import List, Optional, Tuple

from icontract import DBC

from aas_core_meta.marker import JSONArray, JSONObject, JSONValue, non_mutating


class Something(DBC):
    #: Test a list of bare, fully open JSON values
    values: List[JSONValue]

    #: Test a tuple mixing a primitive with a fully open JSON value,
    #: a fully open JSON array and a JSON object
    tuple_with_json: Tuple[str, JSONValue, JSONArray, JSONObject[str]]

    #: Test an optional list of JSON objects, iterated over by
    #: an ``over_X_or_empty`` method
    optional_objects: Optional[List[JSONObject[str]]]

    #: Test an optional JSON object, returned by an ``X_or_default`` method
    optional_object: Optional[JSONObject[str]]

    @non_mutating
    def optional_object_or_default(self) -> JSONObject[str]:
        """Return :attr:`optional_object` if set, or the one from the tuple."""
        if self.optional_object is not None:
            return self.optional_object

        return self.tuple_with_json[3]

    def __init__(
        self,
        values: List[JSONValue],
        tuple_with_json: Tuple[str, JSONValue, JSONArray, JSONObject[str]],
        optional_objects: Optional[List[JSONObject[str]]] = None,
        optional_object: Optional[JSONObject[str]] = None,
    ) -> None:
        self.values = values
        self.tuple_with_json = tuple_with_json
        self.optional_objects = optional_objects
        self.optional_object = optional_object


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
