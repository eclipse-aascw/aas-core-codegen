# pylint: disable=missing-docstring

import unittest

import tests.common
import tests.infer_for_schema.common
from aas_core_codegen import infer_for_schema


class Test_expected(unittest.TestCase):
    def test_no_constraints(self) -> None:
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

    def test_min_value_constant_left(self) -> None:
        source = """\
@invariant(
    lambda self: 10 < len(self),
    "The string must be more than 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=11,
    max_value=None),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_min_value_constant_right(self) -> None:
        source = """\
@invariant(
    lambda self: len(self) > 10,
    "The string must be more than 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=11,
    max_value=None),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_max_value_constant_right(self) -> None:
        source = """\
@invariant(
    lambda self: len(self) < 10,
    "The string must be less than 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=None,
    max_value=9),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_max_value_constant_left(self) -> None:
        source = """\
@invariant(
    lambda self: 10 > len(self),
    "The string must be less than 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=None,
    max_value=9),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_exact_value_constant_left(self) -> None:
        source = """\
@invariant(
    lambda self: 10 == len(self),
    "The string must be exactly 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=10,
    max_value=10),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_exact_value_constant_right(self) -> None:
        source = """\
@invariant(
    lambda self: len(self) == 10,
    "The string must be exactly 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=10,
    max_value=10),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_inheritance_between_constrained_primitives(self) -> None:
        source = """\
@invariant(
    lambda self: len(self) > 3,
    "The string must be more than 3 characters long."
)
class Parent_constrained_primitive(str):
    pass


@invariant(
    lambda self: len(self) < 6,
    "The string must be less than 6 characters long."
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
  len_constraint=LenConstraint(
    min_value=4,
    max_value=5),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )


class Test_unexpected(unittest.TestCase):
    def test_conflicting_min_and_max(self) -> None:
        source = """\
@invariant(
    lambda self: len(self) > 10,
    "The string must be more than 10 characters long."
)
@invariant(
    lambda self: len(self) < 3,
    "The string must be less than 3 characters long."
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

        (
            symbol_table,
            _,
        ) = tests.infer_for_schema.common.parse_to_symbol_table_and_something_cls(
            source=source
        )

        _, error = infer_for_schema.infer_constraints_by_class(
            symbol_table=symbol_table
        )

        assert error is not None
        self.assertEqual(
            "There are conflicting invariants on the length: "
            "the minimum length, 11, contradicts the maximum length 2.",
            tests.common.most_underlying_messages(error),
        )

    def test_conflicting_min_and_exact(self) -> None:
        source = """\
@invariant(
    lambda self: len(self) > 10,
    "The string must be more than 10 characters long."
)
@invariant(
    lambda self: len(self) == 3,
    "The string must be exactly 3 characters long."
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

        (
            symbol_table,
            _,
        ) = tests.infer_for_schema.common.parse_to_symbol_table_and_something_cls(
            source=source
        )

        _, error = infer_for_schema.infer_constraints_by_class(
            symbol_table=symbol_table
        )

        assert error is not None
        self.assertEqual(
            "There are conflicting invariants on the length: "
            "the minimum length, 11, contradicts the exactly expected length 3.",
            tests.common.most_underlying_messages(error),
        )

    def test_conflicting_max_and_exact(self) -> None:
        source = """\
@invariant(
    lambda self: len(self) < 10,
    "The string must be less than 10 characters long."
)
@invariant(
    lambda self: len(self) == 30,
    "The string must be exactly 30 characters long."
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

        (
            symbol_table,
            _,
        ) = tests.infer_for_schema.common.parse_to_symbol_table_and_something_cls(
            source=source
        )

        _, error = infer_for_schema.infer_constraints_by_class(
            symbol_table=symbol_table
        )

        assert error is not None
        self.assertEqual(
            "There are conflicting invariants on the length: "
            "the maximum length, 9, contradicts the exactly expected length 30.",
            tests.common.most_underlying_messages(error),
        )


if __name__ == "__main__":
    unittest.main()
