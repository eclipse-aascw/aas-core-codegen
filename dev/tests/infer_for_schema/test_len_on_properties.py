# pylint: disable=missing-docstring

import unittest

import tests.common
import tests.infer_for_schema.common
from aas_core_codegen import infer_for_schema


class Test_expected(unittest.TestCase):
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

    def test_min_value_constant_left(self) -> None:
        source = """\
@invariant(
    lambda self: 10 < len(self.some_property),
    "Some property must be more than 10 characters long."
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
    lambda self: len(self.some_property) > 10,
    "Some property must be more than 10 characters long."
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
    lambda self: len(self.some_property) < 10,
    "Some property must be less than 10 characters long."
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
    lambda self: 10 > len(self.some_property),
    "Some property must be less than 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=None,
    max_value=9),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_max_value_constant_right_and_not_required(self) -> None:
        source = """\
@invariant(
    lambda self:
    not (self.some_property is not None)
    or len(self.some_property) <= 128,
    "Some property must be at most 128 characters long."
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
  len_constraint=LenConstraint(
    min_value=None,
    max_value=128),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_exact_value_constant_left(self) -> None:
        source = """\
@invariant(
    lambda self: 10 == len(self.some_property),
    "Some property must be exactly 10 characters long."
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
    lambda self: len(self.some_property) == 10,
    "Some property must be exactly 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=10,
    max_value=10),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_conditioned_on_property(self) -> None:
        source = """\
@invariant(
    lambda self:
    not (self.some_property is not None)
    or len(self.some_property) == 10,
    "Some property must be exactly 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=10,
    max_value=10),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )


class Test_unexpected(unittest.TestCase):
    def test_conflicting_min_and_max(self) -> None:
        source = """\
@invariant(
    lambda self: len(self.some_property) > 10,
    "Some property must be more than 10 characters long."
)
@invariant(
    lambda self: len(self.some_property) < 3,
    "Some property must be less than 3 characters long."
)
class Something:
    some_property: str

    def __init__(self, some_property: str) -> None:
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
            "The property some_property has conflicting invariants on the length: "
            "the minimum length, 11, contradicts the maximum length 2.",
            tests.common.most_underlying_messages(error),
        )

    def test_conflicting_min_and_exact(self) -> None:
        source = """\
@invariant(
    lambda self: len(self.some_property) > 10,
    "Some property must be more than 10 characters long."
)
@invariant(
    lambda self: len(self.some_property) == 3,
    "Some property must be exactly 3 characters long."
)
class Something:
    some_property: str

    def __init__(self, some_property: str) -> None:
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
            "The property some_property has conflicting invariants on the length: "
            "the minimum length, 11, contradicts the exactly expected length 3.",
            tests.common.most_underlying_messages(error),
        )

    def test_conflicting_max_and_exact(self) -> None:
        source = """\
@invariant(
    lambda self: len(self.some_property) < 10,
    "Some property must be less than 10 characters long."
)
@invariant(
    lambda self: len(self.some_property) == 30,
    "Some property must be exactly 30 characters long."
)
class Something:
    some_property: str

    def __init__(self, some_property: str) -> None:
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
            "The property some_property has conflicting invariants on the length: "
            "the maximum length, 9, contradicts the exactly expected length 30.",
            tests.common.most_underlying_messages(error),
        )


class Test_stacking(unittest.TestCase):
    def test_no_inheritance_involved(self) -> None:
        source = """\
@invariant(
    lambda self: len(self.some_property) < 10,
    "Some property must be less than 10 characters long."
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
  len_constraint=LenConstraint(
    min_value=None,
    max_value=9),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_inheritance_from_parent_with_no_patterns_of_own(self) -> None:
        source = """\
@invariant(
    lambda self: len(self.some_property) > 3,
    "Some property must be more than 3 characters long."
)
class Parent:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property


class Something(Parent):
    def __init__(self, some_property: str) -> None:
        Parent.__init__(
            self,
            some_property=some_property
        )


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
    max_value=None),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_merge_with_parent(self) -> None:
        source = """\
@invariant(
    lambda self: len(self.some_property) > 3,
    "Some property must be more than 3 characters long."
)
class Parent:
    some_property: str

    def __init__(self, some_property: str) -> None:
        self.some_property = some_property


@invariant(
    lambda self: len(self.some_property) < 10,
    "Some property must be less than 10 characters long."
)
class Something(Parent):
    def __init__(self, some_property: str) -> None:
        Parent.__init__(
            self,
            some_property=some_property
        )


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
    max_value=9),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )

    def test_invariant_on_inherited_property(self) -> None:
        # NOTE (mristin):
        # We encountered a bug when designing V3.0. The schema constraints on
        # the descendant classes where not inferred if an invariant involved properties
        # inherited from the parent class.
        #
        # This unit test illustrates the setting, and prevents regressions.

        source = """\
@abstract
class Abstract_lang_string(DBC):
    text: str

    def __init__(
        self, text: str
    ) -> None:
        self.text = text


@invariant(
    lambda self: len(self.text) <= 128,
    "String shall have a maximum length of 128 characters."
)
class Something(Abstract_lang_string, DBC):
    def __init__(
        self, text: str
    ) -> None:
        Abstract_lang_string.__init__(self, text=text)


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
            something_cls, "text", constraints_by_class
        )

        text = infer_for_schema.dump(constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=LenConstraint(
    min_value=None,
    max_value=128),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )


if __name__ == "__main__":
    unittest.main()
