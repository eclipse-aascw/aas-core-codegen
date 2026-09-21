from typing import Optional

from icontract import DBC, invariant

from aas_core_meta.marker import JSONArray, JSONObject, JSONValue


@invariant(lambda self: len(self) > 0, "At least one character")
class Non_empty_string(str, DBC):
    pass


class Something(DBC):
    #: Test a bare, fully open JSON value
    value: JSONValue

    #: Test a bare, fully open JSON array
    values: JSONArray

    #: Test a JSON object with a plain ``str`` key
    mapping: JSONObject[str]

    #: Test a JSON object with a constrained-string key
    mapping_with_constrained_key: JSONObject[Non_empty_string]

    #: Test an optional, fully open JSON value
    optional_value: Optional[JSONValue]

    #: Test an optional, fully open JSON array
    optional_values: Optional[JSONArray]

    #: Test an optional JSON object
    optional_mapping: Optional[JSONObject[str]]

    def __init__(
        self,
        value: JSONValue,
        values: JSONArray,
        mapping: JSONObject[str],
        mapping_with_constrained_key: JSONObject[Non_empty_string],
        optional_value: Optional[JSONValue] = None,
        optional_values: Optional[JSONArray] = None,
        optional_mapping: Optional[JSONObject[str]] = None,
    ) -> None:
        self.value = value
        self.values = values
        self.mapping = mapping
        self.mapping_with_constrained_key = mapping_with_constrained_key
        self.optional_value = optional_value
        self.optional_values = optional_values
        self.optional_mapping = optional_mapping


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
