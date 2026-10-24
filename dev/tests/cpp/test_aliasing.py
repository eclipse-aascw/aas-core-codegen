import unittest

# noinspection PyProtectedMember
from aas_core_codegen.cpp.lib import (
    _generate_verification as cpp_lib_generate_verification,
)
from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from tests import common as tests_common


def _source_with_verification(verification: str) -> str:
    return f"""\
class Item(DBC):
    text: str
    texts: List[str]

    def __init__(self, text: str, texts: List[str]) -> None:
        self.text = text
        self.texts = texts


@verification
def fill(texts: List[str], text: str) -> bool:
    texts[0] = text
    return True


{verification}


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""


class Test_unfaithful_aliasing_fails(unittest.TestCase):
    """
    Test that we refuse to transpile ``some_func`` to C++ where C++ would diverge.

    The type inference accepts all the functions, as they are faithful in the other
    targets. However, C++ copies the lists by value, while Python shares them.
    """

    def expect_error(self, verification: str, expected_message: str) -> None:
        symbol_table, error = tests_common.translate_source_to_intermediate(
            source=_source_with_verification(verification)
        )
        assert error is None, tests_common.most_underlying_messages(error)
        assert symbol_table is not None

        type_inference, inference_errors = intermediate_type_inference.infer(
            symbol_table=symbol_table
        )
        assert inference_errors is None, tests_common.most_underlying_messages(
            inference_errors
        )
        assert type_inference is not None

        verification_func = symbol_table.verification_functions_by_name[
            Identifier("some_func")
        ]
        assert isinstance(verification_func, intermediate.TranspilableVerification)

        # fmt: off
        _, error = (
            cpp_lib_generate_verification
            ._generate_implementation_of_transpilable_verification(
                verification=verification_func,
                symbol_table=symbol_table,
                type_inference=type_inference,
            )
        )
        # fmt: on

        assert error is not None, "Expected an error, but got none"

        self.assertEqual(
            expected_message, tests_common.most_underlying_messages([error])
        )

    def test_reassigned_argument(self) -> None:
        self.expect_error(
            verification="""\
@verification
def some_func(texts: List[str], others: List[str]) -> bool:
    texts = others
    return True""",
            expected_message=(
                "The argument 'texts' can not be re-assigned in C++, since "
                "the list arguments are passed in as references, so that the "
                "re-assignment would overwrite the caller's list, while "
                "Python re-binds only the local name. Please assign to a new "
                "variable."
            ),
        )

    def test_mutated_alias_of_reassigned_root(self) -> None:
        self.expect_error(
            verification="""\
@verification
def some_func(item: Mutable["Item"], other: Mutable["Item"], text: str) -> bool:
    owner = item
    texts = owner.texts
    texts[0] = text
    owner = other
    return True""",
            expected_message=(
                "The variable 'texts' is mutated in place, so we would need "
                "to declare it as a reference in C++. However, the reference "
                "would not behave as in Python, since the variable, or the "
                "variable its value comes from, is re-assigned, or the value "
                "is replaced in its container in this function."
            ),
        )

    def test_tuple_of_mutated_list(self) -> None:
        self.expect_error(
            verification="""\
@verification
def some_func(texts: List[str], text: str) -> bool:
    t = (texts, 1)
    t[0][0] = text
    return True""",
            expected_message=(
                "C++ copies the list when constructing a tuple, while Python "
                "shares it. The copy would miss the in-place mutations of the "
                "list in this function, so we can not transpile it "
                "faithfully."
            ),
        )

    def test_alias_of_replaced_item(self) -> None:
        self.expect_error(
            verification="""\
@verification
def some_func(items: List[Item], other: Mutable["Item"], text: str) -> bool:
    texts = items[0].texts
    items[0] = other
    return texts[0] == text""",
            expected_message=(
                "We can neither reference nor copy the value of the variable "
                "'texts' in C++. A reference would not behave as in Python, "
                "since the variable, or the variable its value comes from, is "
                "re-assigned, or the value is replaced in its container in "
                "this function. A copy would miss the in-place mutations of "
                "the list, which Python shares instead of copying."
            ),
        )

    def test_iteration_over_replaced_property(self) -> None:
        self.expect_error(
            verification="""\
@verification
def some_func(item: Mutable["Item"], texts: Sequence[str]) -> bool:
    for text in item.texts:
        item.texts = list(texts)
    return True""",
            expected_message=(
                "We can not iterate over the collection in C++, since the "
                "collection, or the variable it comes from, is re-assigned, "
                "or the collection is replaced in its container in this "
                "function, while C++ iterates over the collection by "
                "reference."
            ),
        )

    def test_mutated_generator_variable(self) -> None:
        self.expect_error(
            verification="""\
@verification
def some_func(lists: List[List[str]]) -> bool:
    return all(fill(texts, "x") for texts in lists)""",
            expected_message=(
                "The loop variable 'texts' of the generator expression is "
                "mutated in place, which is not supported yet in C++, as we "
                "would need to pass it as a mutable reference to a lambda."
            ),
        )

    def test_mutated_loop_variable_over_replaced_items(self) -> None:
        self.expect_error(
            verification="""\
@verification
def some_func(lists: List[List[str]], other: Sequence[str]) -> bool:
    for texts in lists:
        texts[0] = "x"
    lists[0] = list(other)
    return True""",
            expected_message=(
                "The loop variable 'texts' is mutated in place, so we would "
                "need to declare it as a reference in C++. However, the "
                "reference would not behave as in Python, since the items are "
                "replaced in their container in this function."
            ),
        )


if __name__ == "__main__":
    unittest.main()
