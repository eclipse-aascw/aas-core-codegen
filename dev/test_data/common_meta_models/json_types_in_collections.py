from typing import List, Tuple

from icontract import DBC

from aas_core_meta.marker import JSONArray, JSONObject, JSONValue


class Something(DBC):
    #: Test a list of bare, fully open JSON values
    values: List[JSONValue]

    #: Test a tuple mixing a primitive with a fully open JSON value,
    #: a fully open JSON array and a JSON object
    tuple_with_json: Tuple[str, JSONValue, JSONArray, JSONObject[str]]

    def __init__(
        self,
        values: List[JSONValue],
        tuple_with_json: Tuple[str, JSONValue, JSONArray, JSONObject[str]],
    ) -> None:
        self.values = values
        self.tuple_with_json = tuple_with_json


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
