from typing import List, Optional, Tuple, Union

from icontract import DBC, invariant

from aas_core_meta.marker import abstract, serialization


# region Structural dispatch: no ``with_model_type``, disjoint required properties


@invariant(lambda self: len(self.unique_to_first) > 0, "The value must not be empty.")
class Structural_first(DBC):
    unique_to_first: str

    def __init__(self, unique_to_first: str) -> None:
        self.unique_to_first = unique_to_first


@invariant(lambda self: len(self.unique_to_second) > 0, "The value must not be empty.")
class Structural_second(DBC):
    unique_to_second: str

    def __init__(self, unique_to_second: str) -> None:
        self.unique_to_second = unique_to_second


Structural_union = Union[Structural_first, Structural_second]

# endregion

# region Mixed dispatch: some implementers by ``modelType``, some structurally
#
# ``Mixed_abstract_member``'s descendants and ``Mixed_concrete_leaf`` have no
# ``modelType`` of their own, and are dispatched structurally (each has a
# required property unique among that group). ``Mixed_concrete_with_descendants``
# (and, inherited, its own descendant) *does* carry a ``modelType``, since a
# concrete class with descendants always contributes itself as an implementer,
# and its own required properties would otherwise be inherited by -- and hence
# never disjoint from -- its descendant's.


@abstract
class Mixed_abstract_member:
    pass


@invariant(
    lambda self: len(self.unique_to_abstract_descendant_one) > 0,
    "The value must not be empty.",
)
class Mixed_abstract_descendant_one(Mixed_abstract_member):
    unique_to_abstract_descendant_one: str

    def __init__(self, unique_to_abstract_descendant_one: str) -> None:
        self.unique_to_abstract_descendant_one = unique_to_abstract_descendant_one


@invariant(
    lambda self: len(self.unique_to_abstract_descendant_two) > 0,
    "The value must not be empty.",
)
class Mixed_abstract_descendant_two(Mixed_abstract_member):
    unique_to_abstract_descendant_two: str

    def __init__(self, unique_to_abstract_descendant_two: str) -> None:
        self.unique_to_abstract_descendant_two = unique_to_abstract_descendant_two


@invariant(
    lambda self: len(self.some_base_property) > 0, "The value must not be empty."
)
@serialization(with_model_type=True)
class Mixed_concrete_with_descendants(DBC):
    some_base_property: str

    def __init__(self, some_base_property: str) -> None:
        self.some_base_property = some_base_property


@invariant(
    lambda self: len(self.some_child_property) > 0,
    "The child value must not be empty.",
)
class Mixed_concrete_with_descendants_child(Mixed_concrete_with_descendants):
    some_child_property: str

    def __init__(self, some_base_property: str, some_child_property: str) -> None:
        Mixed_concrete_with_descendants.__init__(self, some_base_property)
        self.some_child_property = some_child_property


@invariant(
    lambda self: len(self.unique_to_concrete_leaf) > 0, "The value must not be empty."
)
class Mixed_concrete_leaf(DBC):
    unique_to_concrete_leaf: str

    def __init__(self, unique_to_concrete_leaf: str) -> None:
        self.unique_to_concrete_leaf = unique_to_concrete_leaf


Mixed_union = Union[
    Mixed_abstract_member, Mixed_concrete_with_descendants, Mixed_concrete_leaf
]

# endregion

# region Model-type dispatch: every implementer carries ``with_model_type``


@invariant(lambda self: len(self.some_property) > 0, "The value must not be empty.")
@serialization(with_model_type=True)
class Model_typed_first(DBC):
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property


@invariant(lambda self: len(self.some_property) > 0, "The value must not be empty.")
@serialization(with_model_type=True)
class Model_typed_second(DBC):
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property


Model_typed_union = Union[Model_typed_first, Model_typed_second]

# endregion


class Something(DBC):
    structural_property: Structural_union
    mixed_property: Mixed_union
    model_typed_property: Model_typed_union

    #: Test a list of a named union, one property per dispatch kind
    list_structural_property: List[Structural_union]
    list_mixed_property: List[Mixed_union]
    list_model_typed_property: List[Model_typed_union]

    #: Test a tuple mixing all three dispatch kinds of named unions
    tuple_property: Tuple[Structural_union, Mixed_union, Model_typed_union]

    #: Test an optional named union, one property per dispatch kind
    optional_structural_property: Optional[Structural_union]
    optional_mixed_property: Optional[Mixed_union]
    optional_model_typed_property: Optional[Model_typed_union]

    def __init__(
        self,
        structural_property: Structural_union,
        mixed_property: Mixed_union,
        model_typed_property: Model_typed_union,
        list_structural_property: List[Structural_union],
        list_mixed_property: List[Mixed_union],
        list_model_typed_property: List[Model_typed_union],
        tuple_property: Tuple[Structural_union, Mixed_union, Model_typed_union],
        optional_structural_property: Optional[Structural_union] = None,
        optional_mixed_property: Optional[Mixed_union] = None,
        optional_model_typed_property: Optional[Model_typed_union] = None,
    ) -> None:
        self.structural_property = structural_property
        self.mixed_property = mixed_property
        self.model_typed_property = model_typed_property
        self.list_structural_property = list_structural_property
        self.list_mixed_property = list_mixed_property
        self.list_model_typed_property = list_model_typed_property
        self.tuple_property = tuple_property
        self.optional_structural_property = optional_structural_property
        self.optional_mixed_property = optional_mixed_property
        self.optional_model_typed_property = optional_model_typed_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
