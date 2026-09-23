# pylint: disable=missing-docstring

import unittest
from typing import List

from aas_core_codegen.common import Stripped, Identifier

# noinspection PyProtectedMember
from aas_core_codegen.cpp.lib import (
    _generate_verification as cpp_lib_generate_verification,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from tests import common as tests_common


class Test_against_recorded(unittest.TestCase):
    def test_optional_vector_in_invariant_not_deferenced(self) -> None:
        # NOTE (mristin):
        # This is a regression test where we check that an optional list without
        # implication is not de-referenced in the invariant's transpiled code.

        source = """\
class Item:
    value: str
    
    def __init__(self, value: str) -> None:
        self.value = value

@verification
@implementation_specific
def check_something(value: Optional[List[Item]]) -> bool:
    pass

@invariant(
    lambda self:
    check_something(self.value),
    "Some description"
)
class Something:
    value: Optional[List[Item]]
    
    def __init__(self, value: Optional[List[Item]] = None) -> None:
        self.value = value
        
__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table = tests_common.must_translate_source_to_intermediate(source=source)

        base_environment = intermediate_type_inference.populate_base_environment(
            symbol_table=symbol_table
        )

        something_cls = symbol_table.must_find_concrete_class(
            name=Identifier("Something")
        )

        environment = intermediate_type_inference.MutableEnvironment(
            parent=base_environment
        )
        environment.set(
            identifier=Identifier("self"),
            type_annotation=intermediate_type_inference.OurTypeAnnotation(
                our_type=something_cls
            ),
        )

        blocks = []  # type: List[Stripped]
        for invariant in something_cls.invariants:
            (
                condition_expr,
                error,
            ) = cpp_lib_generate_verification._transpile_invariant(
                invariant=invariant, symbol_table=symbol_table, environment=environment
            )
            assert error is None, (
                f"Unexpected generation error for an invariant: "
                f"{tests_common.most_underlying_messages(error)}"
            )
            assert condition_expr is not None

            blocks.append(condition_expr)

        assert len(blocks) == 1, (
            f"Expected only a single block for a single invariant "
            f"in the class {something_cls.name!r}"
        )

        # NOTE (mristin):
        # The implementation of ``CheckSomething`` needs to deal with the optional
        # values. As soon as something is optional in C++, it will be provided to
        # the function as-is. This is intentional.
        self.assertEqual(
            """\
verification::CheckSomething(
  that->value()
)""",
            blocks[0],
        )

    def test_optional_in_invariant_dereferenced_if_certainly_not_null(
        self,
    ) -> None:
        # NOTE (mristin):
        # This is a regression test where we check that an optional value is correctly
        # de-referenced in the invariant's transpiled code if type inference determines
        # that it is certainly not null.

        source = """\
class Item:
    value: str

    def __init__(self, value: str) -> None:
        self.value = value

@verification
@implementation_specific
def check_something(value: Optional[List[Item]]) -> bool:
    pass

@invariant(
    lambda self:
    (self.value is None) or check_something(self.value),
    "Some description"
)
class Something:
    value: Optional[List[Item]]

    def __init__(self, value: Optional[List[Item]] = None) -> None:
        self.value = value

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table = tests_common.must_translate_source_to_intermediate(source=source)

        base_environment = intermediate_type_inference.populate_base_environment(
            symbol_table=symbol_table
        )

        something_cls = symbol_table.must_find_concrete_class(
            name=Identifier("Something")
        )

        environment = intermediate_type_inference.MutableEnvironment(
            parent=base_environment
        )
        environment.set(
            identifier=Identifier("self"),
            type_annotation=intermediate_type_inference.OurTypeAnnotation(
                our_type=something_cls
            ),
        )

        blocks = []  # type: List[Stripped]
        for invariant in something_cls.invariants:
            (
                condition_expr,
                error,
            ) = cpp_lib_generate_verification._transpile_invariant(
                invariant=invariant, symbol_table=symbol_table, environment=environment
            )
            assert error is None, (
                f"Unexpected generation error for an invariant: "
                f"{tests_common.most_underlying_messages(error)}"
            )
            assert condition_expr is not None

            blocks.append(condition_expr)

        assert len(blocks) == 1, (
            f"Expected only a single block for a single invariant "
            f"in the class {something_cls.name!r}"
        )

        # NOTE (mristin):
        # If we know that the value is not optional, we explicitly de-reference it.
        self.assertEqual(
            """\
(
  (!(that->value().has_value()))
  || verification::CheckSomething(
    (*(that->value()))
  )
)""",
            blocks[0],
        )


if __name__ == "__main__":
    unittest.main()
