# pylint: disable=missing-docstring

import unittest

from aas_core_codegen import intermediate, infer_for_schema
from aas_core_codegen.common import Identifier

import tests.infer_for_schema.common


class Test_expected(unittest.TestCase):
    def test_json_value_property(self) -> None:
        source = """\
class Something:
    some_property: JSONValue

    def __init__(self, some_property: JSONValue) -> None:
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

    def test_json_array_property(self) -> None:
        source = """\
class Something:
    some_property: JSONArray

    def __init__(self, some_property: JSONArray) -> None:
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

    def test_json_object_with_str_key_property(self) -> None:
        source = """\
class Something:
    some_property: JSONObject[str]

    def __init__(self, some_property: JSONObject[str]) -> None:
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

    def test_json_object_with_constrained_str_key_property(self) -> None:
        source = """\
@invariant(
    lambda self: len(self) > 0,
    "At least one character"
)
class Non_empty_string(str):
    pass


class Something:
    some_property: JSONObject[Non_empty_string]

    def __init__(self, some_property: JSONObject[Non_empty_string]) -> None:
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

        some_property = something_cls.properties_by_name[Identifier("some_property")]

        type_anno = intermediate.beneath_optional(some_property.type_annotation)
        assert isinstance(type_anno, intermediate.JsonObjectTypeAnnotation)

        # NOTE (mristin):
        # The constraint on the key is inlined onto the key's own type annotation
        # (mirroring how a constrained primitive nested in, say, a ``List[...]`` is
        # keyed by its own type annotation), and *not* on the enclosing
        # ``JSONObject[...]`` type annotation itself.
        constraints_by_value = constraints_by_class[something_cls]

        constraints = constraints_by_value.get(type_anno, None)
        assert constraints is None

        key_constraints = constraints_by_value.get(type_anno.key, None)
        assert key_constraints is not None

        text = infer_for_schema.dump(key_constraints)

        self.assertEqual(
            """\
Constraints(
  len_constraint=LenConstraint(
    min_value=1,
    max_value=None),
  patterns=None,
  set_of_primitives=None,
  set_of_enumeration_literals=None)""",
            text,
        )


if __name__ == "__main__":
    unittest.main()
