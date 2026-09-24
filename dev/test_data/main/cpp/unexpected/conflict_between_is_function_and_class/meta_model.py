class Leaf(DBC):
    pass


class Is_leaf(DBC):
    """Collide with the function ``IsLeaf`` generated for :class:`Leaf`."""


class Something(DBC):
    leaf: Leaf
    is_leaf: Is_leaf

    def __init__(self, leaf: Leaf, is_leaf: Is_leaf) -> None:
        self.leaf = leaf
        self.is_leaf = is_leaf


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
