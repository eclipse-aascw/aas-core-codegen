from typing import Optional

from icontract import DBC, invariant

from aas_core_meta.marker import JSONArray, JSONObject, JSONValue, verification


@verification
def specifies_the_type(mapping: JSONObject[str]) -> bool:
    """Check that the :paramref:`mapping` specifies the type."""
    return "type" in mapping


@verification
def is_acceptable(value: JSONValue) -> bool:
    """
    Check that the :paramref:`value` is acceptable.

    A JSON-able value is opaque to the meta-model, so there is nothing to be
    checked about it here. This function exists so that an indexing into
    a JSON-able object or array has somewhere to be handed over to.
    """
    return True


@invariant(
    lambda self: "type" in self.mapping,
    "The mapping must specify the type",
)
@invariant(
    lambda self:
    not (self.optional_mapping is not None)
    or ("type" in self.optional_mapping),
    "The optional mapping must specify the type",
)
@invariant(
    lambda self: specifies_the_type(self.mapping),
    "The mapping must specify the type, checked in a verification function",
)
@invariant(
    lambda self:
    not ("type" in self.mapping)
    or is_acceptable(self.mapping["type"]),
    "The type of the mapping must be acceptable",
)
@invariant(
    lambda self: len(self.mapping) > 1,
    "The mapping must specify something besides the type",
)
@invariant(
    lambda self: len(self.values) > 0,
    "There must be at least one value",
)
@invariant(
    lambda self:
    not (len(self.values) > 0)
    or is_acceptable(self.values[0]),
    "The first value must be acceptable",
)
@invariant(
    lambda self:
    not (len(self.values) >= 1)
    or is_acceptable(self.values[-1]),
    "The last value must be acceptable",
)
class Something(DBC):
    #: Test the length of, the membership in and the indexing into a JSON-able
    #: object
    mapping: JSONObject[str]

    #: Test the length of and the indexing into a JSON-able array
    values: JSONArray

    #: Test the membership in an optional JSON-able object
    optional_mapping: Optional[JSONObject[str]]

    def __init__(
        self,
        mapping: JSONObject[str],
        values: JSONArray,
        optional_mapping: Optional[JSONObject[str]] = None,
    ) -> None:
        self.mapping = mapping
        self.values = values
        self.optional_mapping = optional_mapping


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
