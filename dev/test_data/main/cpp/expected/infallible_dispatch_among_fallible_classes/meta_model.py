from typing import List, Optional, Union

from icontract import DBC


@abstract
@serialization(with_model_type=True)
class Abstract_without_numbers(DBC):
    """Represent an abstract class whose serialization can not fail."""

    some_text: str

    def __init__(self, some_text: str) -> None:
        self.some_text = some_text


@serialization(with_model_type=True)
class Abstract_descendant_without_numbers(Abstract_without_numbers):
    another_text: str

    def __init__(self, some_text: str, another_text: str) -> None:
        Abstract_without_numbers.__init__(self, some_text)
        self.another_text = another_text


@serialization(with_model_type=True)
class Parent_without_numbers(DBC):
    """Represent a concrete class with descendants which can not fail."""

    some_text: str

    def __init__(self, some_text: str) -> None:
        self.some_text = some_text


@serialization(with_model_type=True)
class Child_without_numbers(Parent_without_numbers):
    another_text: str

    def __init__(self, some_text: str, another_text: str) -> None:
        Parent_without_numbers.__init__(self, some_text)
        self.another_text = another_text


@serialization(with_model_type=True)
class With_number(DBC):
    """Represent a class whose serialization can fail."""

    some_int: int

    def __init__(self, some_int: int) -> None:
        self.some_int = some_int


Union_without_numbers = Union[Abstract_without_numbers, Parent_without_numbers]

Union_with_numbers = Union[Abstract_without_numbers, With_number]


class Something(DBC):
    """
    Hold values whose declared type leaves the run-time type open.

    The serialization of :class:`With_number` can fail, while
    the serialization of the classes and the union without numbers can not.
    The latter must stay infallible even though the dispatch over all
    the classes can fail.
    """

    abstract_property: Abstract_without_numbers
    parent_property: Parent_without_numbers
    list_abstract_property: List[Abstract_without_numbers]
    optional_parent_property: Optional[Parent_without_numbers]
    union_without_numbers_property: Union_without_numbers
    union_with_numbers_property: Union_with_numbers

    def __init__(
        self,
        abstract_property: Abstract_without_numbers,
        parent_property: Parent_without_numbers,
        list_abstract_property: List[Abstract_without_numbers],
        union_without_numbers_property: Union_without_numbers,
        union_with_numbers_property: Union_with_numbers,
        optional_parent_property: Optional[Parent_without_numbers] = None,
    ) -> None:
        self.abstract_property = abstract_property
        self.parent_property = parent_property
        self.list_abstract_property = list_abstract_property
        self.optional_parent_property = optional_parent_property
        self.union_without_numbers_property = union_without_numbers_property
        self.union_with_numbers_property = union_with_numbers_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
