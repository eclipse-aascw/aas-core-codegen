# pylint: disable=missing-docstring

import unittest

import tests.common
import tests.infer_for_schema.common
from aas_core_codegen import infer_for_schema


class Test_expected(unittest.TestCase):
    def test_no_pattern(self) -> None:
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

    def test_single_pattern(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    prefix = "something"
    return match(f"^{prefix}-[a-zA-Z]+$", text) is not None


@invariant(
    lambda self: matches_something(self.some_property),
    "Some property must match something."
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
  patterns=[
    PatternConstraint(
      pattern='^something-[a-zA-Z]+$')],
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_two_patterns(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    return match("^something-[a-zA-Z]+$", text) is not None

@verification
def matches_acme(text: str) -> bool:
    return match("^.*acme.*$", text) is not None


@invariant(
    lambda self: matches_acme(self.some_property),
    "Some property must match acme."
)
@invariant(
    lambda self: matches_something(self.some_property),
    "Some property must match something."
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
  patterns=[
    PatternConstraint(
      pattern='^something-[a-zA-Z]+$'),
    PatternConstraint(
      pattern='^.*acme.*$')],
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_conditioned_on_property(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    return match("^something-[a-zA-Z]+$", text) is not None

@invariant(
    lambda self:
    not (self.some_property is not None)
    or  matches_something(self.some_property),
    "Some property must match something."
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
  patterns=[
    PatternConstraint(
      pattern='^something-[a-zA-Z]+$')],
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )


class Test_stacking(unittest.TestCase):
    def test_no_inheritance_involved(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    prefix = "something"
    return match(f"^{prefix}-[a-zA-Z]+$", text) is not None


@invariant(
    lambda self: matches_something(self.some_property),
    "Some property must match something."
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
  patterns=[
    PatternConstraint(
      pattern='^something-[a-zA-Z]+$')],
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_inheritance_from_parent_with_no_patterns_of_own(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    prefix = "something"
    return match(f"^{prefix}-[a-zA-Z]+$", text) is not None


@invariant(
    lambda self: matches_something(self.some_property),
    "Some property must match something."
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
  patterns=[
    PatternConstraint(
      pattern='^something-[a-zA-Z]+$')],
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_merge_with_parent(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    return match("^something-[a-zA-Z]+$", text) is not None

@verification
def matches_acme(text: str) -> bool:
    return match("^.*acme.*$", text) is not None

@invariant(
    lambda self: matches_something(self.some_property),
    "Some property must match something."
)
class Parent:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property


@invariant(
    lambda self: matches_acme(self.some_property),
    "Some property must match acme."
)
class Something(Parent):
    def __init__(self, some_property: str) -> None:
        Parent.__init__(self, some_property=some_property)


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
  patterns=[
    PatternConstraint(
      pattern='^something-[a-zA-Z]+$'),
    PatternConstraint(
      pattern='^.*acme.*$')],
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_merge_with_parent_and_grand_parent(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    return match("^something-[a-zA-Z]+$", text) is not None

@invariant(
    lambda self: matches_something(self.some_property),
    "Some property must match something."
)
class GrandParent:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property

class Parent(GrandParent):
    def __init__(self, some_property: str) -> None:
        GrandParent.__init__(self, some_property=some_property)

class Something(Parent):
    def __init__(self, some_property: str) -> None:
        Parent.__init__(self, some_property=some_property)


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
  patterns=[
    PatternConstraint(
      pattern='^something-[a-zA-Z]+$')],
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_merge_with_parent_over_constrained_primitive(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    return match("^something-[a-zA-Z]+$", text) is not None

@invariant(
    lambda self: matches_something(self),
    "Some property must match something."
)
class SomeConstrainedPrimitive(str):
    pass

class Parent:
    some_property: SomeConstrainedPrimitive

    def __init__(self, some_property: SomeConstrainedPrimitive) -> None:
        self.some_property = some_property

class Something(Parent):
    def __init__(self, some_property: SomeConstrainedPrimitive) -> None:
        Parent.__init__(self, some_property=some_property)


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
  patterns=[
    PatternConstraint(
      pattern='^something-[a-zA-Z]+$')],
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )


if __name__ == "__main__":
    unittest.main()
