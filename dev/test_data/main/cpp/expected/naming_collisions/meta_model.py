from typing import List, Tuple

from icontract import DBC, invariant

from aas_core_meta.marker import JSONObject, verification


@verification
def each(text: str) -> bool:
    """
    Check that the :paramref:`text` is not empty.

    Test that a verification function is not hidden by the combinator ``Each``.
    """
    return len(text) > 0


@verification
def chain(text: str) -> bool:
    """
    Check that the :paramref:`text` has more than one character.

    Test that a verification function is not hidden by the combinator ``Chain``.
    """
    return len(text) > 1


@verification
def check(text: str) -> bool:
    """
    Check that the :paramref:`text` has more than two characters.

    Test that a verification function is not hidden by the structure ``Check``.
    """
    return len(text) > 2


@invariant(
    lambda self: check(self.text),
    "The text must have more than two characters",
)
@invariant(
    lambda self: each(self.text),
    "The text must not be empty",
)
class Instance(DBC):
    """Test that the function over this class does not clash with the helpers."""

    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self: chain(self.text),
    "The text must have more than one character",
)
class Pointer(DBC):
    """Test that the function over this class does not clash with the helpers."""

    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self: len(self) > 0,
    "The name must not be empty",
)
class Name(str):
    """Test a constrained primitive as a key of a JSON-able object."""


@invariant(
    lambda self: len(self.text) > 0,
    "The text must not be empty",
)
class Json_object_of_name(DBC):
    """Test that the function over this class does not clash with the items."""

    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self: len(self.text) > 0,
    "The text must not be empty",
)
class List_of(DBC):
    """Test that the leaf of this class does not clash with the head of a list."""

    text: str

    def __init__(self, text: str) -> None:
        self.text = text


class Something(DBC):
    instances: List[Instance]
    pointer: Pointer
    json_object_of_name: Json_object_of_name

    #: Test that the items do not clash with the class ``Json_object_of_name``
    mappings: List[JSONObject[Name]]

    #: Test that the moniker ``listOf_ListOf`` is read back unambiguously
    lists: List[List_of]

    #: Test that the moniker ``tupleOf2_ListOf_str`` is read back unambiguously
    pair: Tuple[List_of, str]

    def __init__(
        self,
        instances: List[Instance],
        pointer: Pointer,
        json_object_of_name: Json_object_of_name,
        mappings: List[JSONObject[Name]],
        lists: List[List_of],
        pair: Tuple[List_of, str],
    ) -> None:
        self.instances = instances
        self.pointer = pointer
        self.json_object_of_name = json_object_of_name
        self.mappings = mappings
        self.lists = lists
        self.pair = pair


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
