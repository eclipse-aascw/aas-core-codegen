# pylint: disable=missing-docstring


import unittest

import tests.common
import tests.infer_for_schema.common
from aas_core_codegen import infer_for_schema


class Test_property_in_set(unittest.TestCase):
    def test_no_constraints(self) -> None:
        source = """\
class Something:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        # fmt: off
        (
            _,
            something_cls,
            constraints_by_class,
        ) = (
            tests.infer_for_schema.common
            .parse_to_symbol_table_and_something_cls_and_constraints_by_class(
                source=source
            )
        )
        # fmt: on

        constraints = tests.infer_for_schema.common.select_constraints_of_property(
            something_cls, "some_property", constraints_by_class
        )

        assert constraints is None

    def test_property_in_set(self) -> None:
        source = """\
Some_set: Set[str] = constant_set(
    values=["A", "B"])

@invariant(
    lambda self:
    self.some_property in Some_set,
    "Some property must be part of some set."
)
class Something:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        # fmt: off
        (
            _,
            something_cls,
            constraints_by_class,
        ) = (
            tests.infer_for_schema.common
            .parse_to_symbol_table_and_something_cls_and_constraints_by_class(
                source=source
            )
        )
        # fmt: on

        constraints = tests.infer_for_schema.common.select_constraints_of_property(
            something_cls, "some_property", constraints_by_class
        )

        text = infer_for_schema.dump(constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=None,
  patterns=None,
  set_of_primitives=SetOfPrimitivesConstraint(
    a_type='STR',
    literals=[
      PrimitiveSetLiteral(
        value='A',
        a_type='STR',
        parsed=...),
      PrimitiveSetLiteral(
        value='B',
        a_type='STR',
        parsed=...)]),
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_property_in_set_in_conjunction(self) -> None:
        source = """\
Some_set: Set[str] = constant_set(
    values=["A", "B"])

Another_set: Set[str] = constant_set(
    values=["B", "C"])

@invariant(
    lambda self:
    self.some_property in Some_set
    and self.some_property in Another_set,
    "Some property must be part of some set and another set."
)
class Something:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        # fmt: off
        (
            _,
            something_cls,
            constraints_by_class,
        ) = (
            tests.infer_for_schema.common
            .parse_to_symbol_table_and_something_cls_and_constraints_by_class(
                source=source
            )
        )
        # fmt: on

        constraints = tests.infer_for_schema.common.select_constraints_of_property(
            something_cls, "some_property", constraints_by_class
        )

        text = infer_for_schema.dump(constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=None,
  patterns=None,
  set_of_primitives=SetOfPrimitivesConstraint(
    a_type='STR',
    literals=[
      PrimitiveSetLiteral(
        value='B',
        a_type='STR',
        parsed=...)]),
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_property_in_set_in_implication(self) -> None:
        source = """\
Some_set: Set[str] = constant_set(
    values=["A", "B"])

@invariant(
    lambda self:
    not (self.some_property is not None)
    or self.some_property in Some_set,
    "Some property must be part of some set."
)
class Something:
    some_property: Optional[str]

    def __init__(self, some_property: Optional[str] = None) -> None:
        self.some_property = some_property

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        # fmt: off
        (
            _,
            something_cls,
            constraints_by_class,
        ) = (
            tests.infer_for_schema.common
            .parse_to_symbol_table_and_something_cls_and_constraints_by_class(
                source=source
            )
        )
        # fmt: on

        constraints = tests.infer_for_schema.common.select_constraints_of_property(
            something_cls, "some_property", constraints_by_class
        )

        text = infer_for_schema.dump(constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=None,
  patterns=None,
  set_of_primitives=SetOfPrimitivesConstraint(
    a_type='STR',
    literals=[
      PrimitiveSetLiteral(
        value='A',
        a_type='STR',
        parsed=...),
      PrimitiveSetLiteral(
        value='B',
        a_type='STR',
        parsed=...)]),
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_property_in_set_in_implication_and_conjunction(self) -> None:
        source = """\
Some_set: Set[str] = constant_set(
    values=["A", "B"])

Another_set: Set[str] = constant_set(
    values=["B", "C"])

@invariant(
    lambda self:
    not (self.some_property is not None)
    or (
        self.some_property in Some_set
        and self.some_property in Another_set
    ),
    "Some property must be part of some set and another set."
)
class Something:
    some_property: Optional[str]

    def __init__(self, some_property: Optional[str] = None) -> None:
        self.some_property = some_property

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        # fmt: off
        (
            _,
            something_cls,
            constraints_by_class,
        ) = (
            tests.infer_for_schema.common
            .parse_to_symbol_table_and_something_cls_and_constraints_by_class(
                source=source
            )
        )
        # fmt: on

        constraints = tests.infer_for_schema.common.select_constraints_of_property(
            something_cls, "some_property", constraints_by_class
        )

        text = infer_for_schema.dump(constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=None,
  patterns=None,
  set_of_primitives=SetOfPrimitivesConstraint(
    a_type='STR',
    literals=[
      PrimitiveSetLiteral(
        value='B',
        a_type='STR',
        parsed=...)]),
  set_of_enumeration_literals=None)""",
            text,
        )


class Test_stacking(unittest.TestCase):
    def test_only_inherited_and_no_constraints_of_its_own(self) -> None:
        source = """\
Some_set: Set[str] = constant_set(
    values=["A", "B"])

@invariant(
    lambda self:
    self.some_property in Some_set,
    "Some property must be part of some set."
)
class Parent(DBC):
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property

class Something(Parent):
    def __init__(self, some_property: str) -> None:
        Parent.__init__(self, some_property)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        # fmt: off
        (
            _,
            something_cls,
            constraints_by_class,
        ) = (
            tests.infer_for_schema.common
            .parse_to_symbol_table_and_something_cls_and_constraints_by_class(
                source=source
            )
        )
        # fmt: on

        constraints = tests.infer_for_schema.common.select_constraints_of_property(
            something_cls, "some_property", constraints_by_class
        )

        text = infer_for_schema.dump(constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=None,
  patterns=None,
  set_of_primitives=SetOfPrimitivesConstraint(
    a_type='STR',
    literals=[
      PrimitiveSetLiteral(
        value='A',
        a_type='STR',
        parsed=...),
      PrimitiveSetLiteral(
        value='B',
        a_type='STR',
        parsed=...)]),
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_merge_with_parent(self) -> None:
        source = """\
Some_set: Set[str] = constant_set(
    values=["A", "B"])

Another_set: Set[str] = constant_set(
    values=["B", "C"])

@invariant(
    lambda self:
    self.some_property in Some_set,
    "Some property must be part of some set."
)
class Parent(DBC):
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property

@invariant(
    lambda self:
    self.some_property in Another_set,
    "Some property must be part of another set."
)
class Something(Parent):
    def __init__(self, some_property: str) -> None:
        Parent.__init__(self, some_property)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        # fmt: off
        (
            _,
            something_cls,
            constraints_by_class,
        ) = (
            tests.infer_for_schema.common
            .parse_to_symbol_table_and_something_cls_and_constraints_by_class(
                source=source
            )
        )
        # fmt: on

        constraints = tests.infer_for_schema.common.select_constraints_of_property(
            something_cls, "some_property", constraints_by_class
        )

        text = infer_for_schema.dump(constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=None,
  patterns=None,
  set_of_primitives=SetOfPrimitivesConstraint(
    a_type='STR',
    literals=[
      PrimitiveSetLiteral(
        value='B',
        a_type='STR',
        parsed=...)]),
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_merge_with_parent_and_grand_parent(self) -> None:
        source = """\
Some_set: Set[str] = constant_set(
    values=["A", "B", "C"])

Another_set: Set[str] = constant_set(
    values=["B", "C", "D"])

Yet_another_set: Set[str] = constant_set(
    values=["C", "D", "E"])

@invariant(
    lambda self:
    self.some_property in Some_set,
    "Some property must be part of some set."
)
class Grand_parent(DBC):
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property

@invariant(
    lambda self:
    self.some_property in Another_set,
    "Some property must be part of another set."
)
class Parent(Grand_parent):
    def __init__(self, some_property: str) -> None:
        Grand_parent.__init__(self, some_property)

@invariant(
    lambda self:
    self.some_property in Yet_another_set,
    "Some property must be part of yet another set."
)
class Something(Parent):
    def __init__(self, some_property: str) -> None:
        Parent.__init__(self, some_property)


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        # fmt: off
        (
            _,
            something_cls,
            constraints_by_class,
        ) = (
            tests.infer_for_schema.common
            .parse_to_symbol_table_and_something_cls_and_constraints_by_class(
                source=source
            )
        )
        # fmt: on

        constraints = tests.infer_for_schema.common.select_constraints_of_property(
            something_cls, "some_property", constraints_by_class
        )

        text = infer_for_schema.dump(constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=None,
  patterns=None,
  set_of_primitives=SetOfPrimitivesConstraint(
    a_type='STR',
    literals=[
      PrimitiveSetLiteral(
        value='C',
        a_type='STR',
        parsed=...)]),
  set_of_enumeration_literals=None)""",
            text,
        )


if __name__ == "__main__":
    unittest.main()
