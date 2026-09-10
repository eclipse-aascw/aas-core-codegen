# pylint: disable=missing-docstring

import unittest

import tests.common
import tests.infer_for_schema.common
from aas_core_codegen import infer_for_schema


class Test_expected(unittest.TestCase):
    def test_no_pattern(self) -> None:
        source = """\
class Some_constrained_primitive(str):
    pass


class Something:
    some_property: Some_constrained_primitive

    def __init__(self, some_property: Some_constrained_primitive) -> None:
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
    lambda self: matches_something(self),
    "Some property must match something."
)
class Some_constrained_primitive(str):
    pass

class Something:
    some_property: Some_constrained_primitive

    def __init__(self, some_property: Some_constrained_primitive) -> None:
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
    lambda self: matches_acme(self),
    "Some property must match acme."
)
@invariant(
    lambda self: matches_something(self),
    "Some property must match something."
)
class Some_constrained_primitive(str):
    pass

class Something:
    some_property: Some_constrained_primitive

    def __init__(self, some_property: Some_constrained_primitive) -> None:
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

    def test_inheritance_between_constrained_primitives_parent_first(self) -> None:
        source = """\
@verification
def matches_something(text: str) -> bool:
    return match("^something-[a-zA-Z]+$", text) is not None

@verification
def matches_acme(text: str) -> bool:
    return match("^.*acme.*$", text) is not None

@invariant(
    lambda self: matches_something(self),
    "Some property must match something."
)
class Parent_constrained_primitive(str):
    pass

@invariant(
    lambda self: matches_acme(self),
    "Some property must match acme."
)
class Some_constrained_primitive(Parent_constrained_primitive):
    pass

class Something:
    some_property: Some_constrained_primitive

    def __init__(self, some_property: Some_constrained_primitive) -> None:
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


if __name__ == "__main__":
    unittest.main()
