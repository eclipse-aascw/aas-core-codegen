from typing import Optional

from icontract import DBC, invariant

from aas_core_meta.marker import JSONObject, verification


@verification
def specifies_the_type(mapping: JSONObject[str]) -> bool:
    """Check that the :paramref:`mapping` specifies the type."""
    return "type" in mapping


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
class Something(DBC):
    #: Test the membership in a JSON-able object
    mapping: JSONObject[str]

    #: Test the membership in an optional JSON-able object
    optional_mapping: Optional[JSONObject[str]]

    def __init__(
        self,
        mapping: JSONObject[str],
        optional_mapping: Optional[JSONObject[str]] = None,
    ) -> None:
        self.mapping = mapping
        self.optional_mapping = optional_mapping


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
