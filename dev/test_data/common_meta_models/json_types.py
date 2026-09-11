from typing import Optional

from icontract import DBC, invariant

from aas_core_meta.marker import JSONArray, JSONObject, JSONValue


@invariant(lambda self: len(self) > 0, "At least one character")
class Non_empty_string(str, DBC):
    pass


@invariant(lambda self: self > 0, "Larger than zero")
class Positive_int(int, DBC):
    pass


class Something(DBC):
    #: Test a bare, fully open JSON value
    value: JSONValue

    #: Test a bare, fully open JSON array
    values: JSONArray

    #: Test a JSON object with a plain ``str`` key and an open value
    mapping: JSONObject[str, JSONValue]

    #: Test a JSON object with a constrained-string key
    mapping_with_constrained_key: JSONObject[Non_empty_string, JSONValue]

    #: Test a JSON object with a constrained-primitive value
    mapping_with_constrained_value: JSONObject[str, Positive_int]

    #: Test a JSON object with both a constrained-string key and
    #: a constrained-primitive value
    mapping_with_constrained_key_and_value: JSONObject[Non_empty_string, Positive_int]

    #: Test a JSON object nested as the value of another JSON object
    nested_mapping: JSONObject[str, JSONObject[str, JSONValue]]

    #: Test an optional, fully open JSON value
    optional_value: Optional[JSONValue]

    #: Test an optional, fully open JSON array
    optional_values: Optional[JSONArray]

    #: Test an optional JSON object
    optional_mapping: Optional[JSONObject[str, JSONValue]]

    def __init__(
        self,
        value: JSONValue,
        values: JSONArray,
        mapping: JSONObject[str, JSONValue],
        mapping_with_constrained_key: JSONObject[Non_empty_string, JSONValue],
        mapping_with_constrained_value: JSONObject[str, Positive_int],
        mapping_with_constrained_key_and_value: JSONObject[
            Non_empty_string, Positive_int
        ],
        nested_mapping: JSONObject[str, JSONObject[str, JSONValue]],
        optional_value: Optional[JSONValue] = None,
        optional_values: Optional[JSONArray] = None,
        optional_mapping: Optional[JSONObject[str, JSONValue]] = None,
    ) -> None:
        self.value = value
        self.values = values
        self.mapping = mapping
        self.mapping_with_constrained_key = mapping_with_constrained_key
        self.mapping_with_constrained_value = mapping_with_constrained_value
        self.mapping_with_constrained_key_and_value = (
            mapping_with_constrained_key_and_value
        )
        self.nested_mapping = nested_mapping
        self.optional_value = optional_value
        self.optional_values = optional_values
        self.optional_mapping = optional_mapping


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
