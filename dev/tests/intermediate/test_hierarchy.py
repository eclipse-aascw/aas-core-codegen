# pylint: disable=missing-docstring

import unittest

from aas_core_codegen.intermediate import _hierarchy as intermediate_hierarchy
from aas_core_codegen.common import Identifier

import tests.common


class Test_ontology_ok(unittest.TestCase):
    def test_no_ancestors(self) -> None:
        symbol_table, error = tests.common.parse_source(
            """\
class Something:
    pass

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        )

        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        ontology, errors = intermediate_hierarchy.map_symbol_table_to_ontology(
            symbol_table
        )
        assert errors is None, f"{errors=}"
        assert ontology is not None

        ancestors = ontology.list_ancestors(
            cls=symbol_table.must_find_class(Identifier("Something"))
        )

        ancestor_names = [cls.name for cls in ancestors]
        self.assertListEqual([], ancestor_names)

    def test_complex_graph(self) -> None:
        symbol_table, error = tests.common.parse_source(
            """\
@abstract
class Another_grand_parent:
    pass

@abstract
class Grand_parent:
    pass

@abstract
class Parent(Grand_parent, Another_grand_parent):
    pass

@abstract
class Another_parent(Grand_parent, Another_grand_parent):
    pass

class Something(Parent, Another_parent):
    pass

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        )

        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        ontology, errors = intermediate_hierarchy.map_symbol_table_to_ontology(
            symbol_table
        )
        assert errors is None, f"{errors=}"
        assert ontology is not None

        ancestors = ontology.list_ancestors(
            cls=symbol_table.must_find_class(Identifier("Something"))
        )

        ancestor_names = [cls.name for cls in ancestors]

        self.assertListEqual(
            [
                "Another_grand_parent",
                "Grand_parent",
                "Another_parent",
                "Another_grand_parent",
                "Grand_parent",
                "Parent",
            ],
            ancestor_names,
        )


class Test_ontology_fail(unittest.TestCase):
    def test_duplicate_properties_in_ancestors(self) -> None:
        symbol_table, error = tests.common.parse_source(
            """\
@abstract
class SomethingAbstract:
    x: int

@abstract
class Something(SomethingAbstract):
    x: int

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        _, errors = intermediate_hierarchy.map_symbol_table_to_ontology(symbol_table)
        assert errors is not None and len(errors) == 1

        self.assertEqual(
            "The property has already been defined "
            "in the ancestor class SomethingAbstract: x",
            tests.common.most_underlying_messages(errors[0]),
        )

    def test_duplicate_methods_in_ancestors(self) -> None:
        symbol_table, error = tests.common.parse_source(
            """\
@abstract
class SomethingAbstract:
    def do_something(self) -> None:
        pass

@abstract
class Something(SomethingAbstract):
    def do_something(self) -> None:
        pass

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        _, errors = intermediate_hierarchy.map_symbol_table_to_ontology(symbol_table)
        assert errors is not None and len(errors) == 1

        self.assertEqual(
            "The method has already been defined "
            "in the ancestor class SomethingAbstract: do_something",
            tests.common.most_underlying_messages(errors[0]),
        )

    def test_missing_constructor_when_the_parent_has_one(self) -> None:
        symbol_table, error = tests.common.parse_source(
            """\
@abstract
class SomethingAbstract:
    def __init__(self, x: int) -> None:
        pass

class Something(SomethingAbstract):
    pass

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        _, errors = intermediate_hierarchy.map_symbol_table_to_ontology(symbol_table)
        assert errors is not None and len(errors) == 1

        self.assertEqual(
            "The class Something does not specify a constructor, "
            "but the ancestor class SomethingAbstract specifies a constructor "
            "with arguments: self, x",
            tests.common.most_underlying_messages(errors[0]),
        )

    def test_cycle_inheritance(self) -> None:
        symbol_table, error = tests.common.parse_source(
            """\
@abstract
class Cycle(Something):
    pass

@abstract
class Something(Cycle):
    pass

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        _, errors = intermediate_hierarchy.map_symbol_table_to_ontology(symbol_table)
        assert errors is not None and len(errors) == 1

        self.assertEqual(
            "Expected no cycles in the inheritance, "
            "but the class Cycle has been observed in a cycle",
            tests.common.most_underlying_messages(errors[0]),
        )


if __name__ == "__main__":
    unittest.main()
