@abstract
class Abstract_member:
    pass


class Abstract_descendant_one(Abstract_member):
    unique_to_descendant_one: str

    def __init__(self, unique_to_descendant_one: str) -> None:
        self.unique_to_descendant_one = unique_to_descendant_one


class Abstract_descendant_two(Abstract_member):
    unique_to_descendant_two: str

    def __init__(self, unique_to_descendant_two: str) -> None:
        self.unique_to_descendant_two = unique_to_descendant_two


@serialization(with_model_type=True)
class Concrete_with_descendants(DBC):
    some_base_property: str

    def __init__(self, some_base_property: str) -> None:
        self.some_base_property = some_base_property


class Concrete_with_descendants_child(Concrete_with_descendants):
    some_child_property: str

    def __init__(self, some_base_property: str, some_child_property: str) -> None:
        Concrete_with_descendants.__init__(self, some_base_property)
        self.some_child_property = some_child_property


class Concrete_leaf:
    unique_to_concrete_leaf: str

    def __init__(self, unique_to_concrete_leaf: str) -> None:
        self.unique_to_concrete_leaf = unique_to_concrete_leaf


Mixed_union = Union[Abstract_member, Concrete_with_descendants, Concrete_leaf]


class Something:
    mixed_property: Mixed_union

    def __init__(self, mixed_property: Mixed_union) -> None:
        self.mixed_property = mixed_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
