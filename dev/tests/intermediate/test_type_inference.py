import ast
import textwrap
import unittest
from typing import Final, List, Mapping, Tuple

import tests.common
from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference


class Test_with_smoke(unittest.TestCase):
    @staticmethod
    def execute(source: str) -> None:
        """Execute a smoke test on all the invariants of all the classes."""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)

        assert symbol_table is not None

        base_environment = intermediate_type_inference.populate_base_environment(
            symbol_table=symbol_table
        )

        for our_type in symbol_table.our_types:
            if isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                environment = intermediate_type_inference.MutableEnvironment(
                    parent=base_environment
                )
                environment.set(
                    Identifier("self"),
                    intermediate_type_inference.OurTypeAnnotation(our_type=our_type),
                )

                for invariant in our_type.invariants:
                    # fmt: off
                    _, inference_error = (
                        intermediate_type_inference.infer_for_invariant(
                            invariant=invariant,
                            environment=environment
                        )
                    )
                    # fmt: on

                    assert (
                        inference_error is None
                    ), tests.common.most_underlying_messages([inference_error])

        for verification in symbol_table.verification_functions:
            if not isinstance(verification, intermediate.TranspilableVerification):
                continue

            # fmt: off
            _, inference_error = (
                intermediate_type_inference.infer_for_verification(
                    verification=verification,
                    base_environment=base_environment
                )
            )
            # fmt: on

            assert inference_error is None, tests.common.most_underlying_messages(
                [inference_error]
            )

    def expect_type_inference_to_fail(
        self, source: str, expected_joined_message: str
    ) -> None:
        """Execute a smoke test and expect type inference to fail."""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)

        assert symbol_table is not None

        base_environment = intermediate_type_inference.populate_base_environment(
            symbol_table=symbol_table
        )

        type_inference_errors: List[str] = []

        for our_type in symbol_table.our_types:
            if isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                environment = intermediate_type_inference.MutableEnvironment(
                    parent=base_environment
                )
                environment.set(
                    Identifier("self"),
                    intermediate_type_inference.OurTypeAnnotation(our_type=our_type),
                )

                for invariant in our_type.invariants:
                    # fmt: off
                    _, inference_error = (
                        intermediate_type_inference.infer_for_invariant(
                            invariant=invariant,
                            environment=environment
                        )
                    )
                    # fmt: on

                    if inference_error is not None:
                        type_inference_errors.append(
                            tests.common.most_underlying_messages([inference_error])
                        )

        for verification in symbol_table.verification_functions:
            if not isinstance(verification, intermediate.TranspilableVerification):
                continue

            # fmt: off
            _, inference_error = (
                intermediate_type_inference.infer_for_verification(
                    verification=verification,
                    base_environment=base_environment
                )
            )
            # fmt: on

            if inference_error is not None:
                type_inference_errors.append(
                    tests.common.most_underlying_messages([inference_error])
                )

        assert len(type_inference_errors) > 0, (
            f"Expected one or more type inference errors, "
            f"but got none on the source code:\n{source}"
        )

        joined_message = "\n".join(type_inference_errors)
        self.assertEqual(expected_joined_message, joined_message, source)

    def test_enumeration_literal_as_member(self) -> None:
        source = """\
class Some_enum(Enum):
    Literal_a = "LITERAL-A"
    Literal_b = "LITERAL-B"
    Literal_c = "LITERAL-C"

@invariant(
    lambda self:
    self.something == Some_enum.Literal_a
    or self.something == Some_enum.Literal_b,
    "Something must be either LITERAL-A or LITERAL-B."
)
class Some_class:
    something: Some_enum

    def __init__(self, something: Some_enum) -> None:
        self.something = something


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_class_member(self) -> None:
        source = """\
@invariant(
    lambda self:
    self.something >= 1,
    "Something must be at least 1."
)
class Some_class:
    something: int

    def __init__(self, something: int) -> None:
        self.something = something


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_non_nullness_of_members_member_in_implication(self) -> None:
        source = """\
class Some_class:
    something: Optional[str]

    def __init__(self, something: Optional[str] = None) -> None:
        self.something = something

@invariant(
    lambda self:
    not (
        self.some_instance is not None
        and self.some_instance.something is not None
    ) or (
        self.some_instance.something == "some-literal"
    ),
    "If something of some instance is defined, it must be set "
    "to some-literal."
)
class Another_class:
    some_instance: Optional[Some_class]

    def __init__(self, some_instance: Optional[Some_class] = None) -> None:
        self.some_instance = some_instance


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_non_nullness_of_members_member_in_conjunction(self) -> None:
        source = """\
class Some_class:
    something: Optional[str]

    def __init__(self, something: Optional[str] = None) -> None:
        self.something = something

@invariant(
    lambda self:
    self.some_instance is not None
    and self.some_instance.something is not None
    and self.some_instance.something == "some-literal",
    "Something of some instance must be defined and set to some-literal."
)
class Another_class:
    some_instance: Optional[Some_class]

    def __init__(self, some_instance: Optional[Some_class] = None) -> None:
        self.some_instance = some_instance


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_non_nullness_in_disjunction_with_is_none(self) -> None:
        source = """\
@invariant(
    lambda self:
    (self.some_property is None) or (self.some_property == "dummy"),
    "Dummy description"
)
class Something:
    some_property: Optional[str]

    def __init__(self, some_property: Optional[str] = None) -> None:
        self.some_property = some_property


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_tuple_literal(self) -> None:
        source = """\
@verification
def some_verification(x: str, y: int) -> bool:
    return (x, y)[0] == x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_tuple_of_classes(self) -> None:
        source = """\
class Some_class:
    something: int

    def __init__(self, something: int) -> None:
        self.something = something

@invariant(
    lambda self:
    self.pair[0].something >= 1,
    "Something of the first item must be at least 1."
)
class Another_class:
    pair: Tuple[Some_class, Some_class]

    def __init__(self, pair: Tuple[Some_class, Some_class]) -> None:
        self.pair = pair


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_len_and_index_on_json_array(self) -> None:
        source = """\
@verification
def is_acceptable(value: JSONValue) -> bool:
    return True

@invariant(
    lambda self:
    len(self.values) >= 1 and is_acceptable(self.values[0]),
    "There must be at least one value, and it must be acceptable."
)
class Something:
    values: JSONArray

    def __init__(self, values: JSONArray) -> None:
        self.values = values


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_len_index_and_in_on_json_object(self) -> None:
        source = """\
@verification
def is_acceptable(value: JSONValue) -> bool:
    return True

@invariant(
    lambda self:
    len(self.value) >= 1
    and ("modelType" in self.value)
    and is_acceptable(self.value["modelType"]),
    "The value must specify an acceptable model type."
)
class Something:
    value: JSONObject[str]

    def __init__(self, value: JSONObject[str]) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_len_on_json_value_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    len(self.value) >= 1,
    "Dummy invariant description"
)
class Something:
    value: JSONValue

    def __init__(self, value: JSONValue) -> None:
        self.value = value

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "JSONValue represents an arbitrary, open JSON-able value "
                "whose shape can not be determined statically, so we treat "
                "it analogous to Unknown -- computing its length is not "
                "supported. Only a JSONArray and a JSONObject have a length "
                "which we can compute."
            ),
        )

    def test_protected_method_in_invariant_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    self._is_valid(),
    "Dummy invariant description"
)
class Something:
    value: str

    @implementation_specific
    @non_mutating
    def _is_valid(self) -> bool:
        pass

    def __init__(self, value: str) -> None:
        self.value = value

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The method '_is_valid' of the class 'Something' is protected, "
                "so it can be only called on self from the methods of the class "
                "and its descendants"
            ),
        )

    def test_private_method_in_verification_function_fails(self) -> None:
        source = """\
class Something:
    value: str

    @implementation_specific
    @non_mutating
    def __is_valid(self) -> bool:
        pass

    def __init__(self, value: str) -> None:
        self.value = value

@verification
def is_valid(something: Something) -> bool:
    return something.__is_valid()

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The method '__is_valid' of the class 'Something' is private, "
                "so it can be only called on self from the methods of the class"
            ),
        )

    def test_internal_function_in_invariant(self) -> None:
        source = """\
@verification
def _is_valid(text: str) -> bool:
    return len(text) > 0

@invariant(
    lambda self:
    _is_valid(self.value),
    "Dummy invariant description"
)
class Something:
    value: str

    def __init__(self, value: str) -> None:
        self.value = value

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_index_on_json_value_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    len(self.value[0]) >= 0,
    "Dummy invariant description"
)
class Something:
    value: JSONValue

    def __init__(self, value: JSONValue) -> None:
        self.value = value

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "JSONValue represents an arbitrary, open JSON-able value "
                "whose shape can not be determined statically, so we treat "
                "it analogous to Unknown -- indexing into it is not "
                "supported"
            ),
        )

    def test_index_on_json_array_with_non_integer_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    len(self.values["x"]) >= 0,
    "Dummy invariant description"
)
class Something:
    values: JSONArray

    def __init__(self, values: JSONArray) -> None:
        self.values = values

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the index into a JSONArray to be an integer, but got: str"
            ),
        )

    def test_index_on_json_object_with_non_string_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    len(self.value[1]) >= 0,
    "Dummy invariant description"
)
class Something:
    value: JSONObject[str]

    def __init__(self, value: JSONObject[str]) -> None:
        self.value = value

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the index into a JSONObject to be a string "
                "(or a class constraining ``str``), but got: int"
            ),
        )

    def test_is_none_fails_on_non_optional(self) -> None:
        source = """\
@invariant(
    lambda self:
    self.something is None,
    "Dummy invariant description"
)
class Some_class:
    something: str

    def __init__(self, something: str) -> None:
        self.something = something

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the value to be of an optional type "
                "for a nullness check (``is None``), but got str"
            ),
        )

    def test_is_not_none_fails_on_non_optional(self) -> None:
        source = """\
@invariant(
    lambda self:
    self.something is not None,
    "Dummy invariant description"
)
class Some_class:
    something: str

    def __init__(self, something: str) -> None:
        self.something = something

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the value to be of an optional type "
                "for a non-nullness check (``is not None``), but got str"
            ),
        )

    def test_switch_variable_used_after_the_branch_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    if kind == Kind.Alpha:
        x = 1
    else:
        x = 2

    return x > 0


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The variable 'x' has been defined in a nested block before, "
                "such as a for-loop or a branch of a switch or of an if-statement, "
                "and is not visible here. While Python keeps the variable after "
                "the block, the other targets scope it to the block. Please define "
                "the variable before the block."
            ),
        )

    def test_switch_variable_of_a_sibling_branch_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    if kind == Kind.Alpha:
        x = 1
        return x > 0
    else:
        return x > 0


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The variable 'x' has been defined in a nested block before, "
                "such as a for-loop or a branch of a switch or of an if-statement, "
                "and is not visible here. While Python keeps the variable after "
                "the block, the other targets scope it to the block. Please define "
                "the variable before the block."
            ),
        )

    def test_switch_variable_redeclared_after_the_switch_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    if kind == Kind.Alpha:
        x = 1
        return x > 0

    x = 2
    return x > 0


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The variable 'x' has been already defined in a nested block "
                "before, such as a for-loop or a branch of a switch or of "
                "an if-statement. In Python, "
                "both definitions denote the same variable, while they denote "
                "two different variables in the target languages with block "
                "scopes, and some target languages, such as C#, refuse such "
                "re-declarations altogether. Please use a different name."
            ),
        )

    def test_switch_variable_redeclared_after_a_nested_switch_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind, number: int) -> bool:
    if kind == Kind.Alpha:
        if number == 0:
            x = 1
            return x > 0

        x = 2
        return x > 0

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The variable 'x' has been already defined in a nested block "
                "before, such as a for-loop or a branch of a switch or of "
                "an if-statement. In Python, "
                "both definitions denote the same variable, while they denote "
                "two different variables in the target languages with block "
                "scopes, and some target languages, such as C#, refuse such "
                "re-declarations altogether. Please use a different name."
            ),
        )

    def test_switch_variable_reused_in_sibling_branches(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind, text: str) -> bool:
    if kind == Kind.Alpha:
        x = len(text)
        return x > 0
    else:
        x = len(text)
        return x > 1


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.execute(source=source)

    def test_switch_assignment_to_a_variable_before_the_switch(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    x = 1
    if kind == Kind.Alpha:
        x = 2

    return x > 1


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.execute(source=source)

    def test_switch_on_optional_subject_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Optional[Kind]) -> bool:
    if kind == Kind.Alpha:
        return False
    elif kind == Kind.Beta:
        return True

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the subject of the switch to be a non-None, but "
                "got: Optional[Kind]"
            ),
        )

    def test_switch_on_bool_subject_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(flag: bool) -> bool:
    if flag == 1:
        return False
    elif flag == 0:
        return True

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the subject of the switch to be an enumeration, a "
                "string, an integer or a length, but got: bool"
            ),
        )

    def test_switch_label_of_another_enumeration_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    if kind == Other_kind.Alpha:
        return False
    elif kind == Kind.Beta:
        return True

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the label to be a literal of the enumeration "
                "'Kind', the type of the subject of the switch, but got: "
                "Other_kind"
            ),
        )

    def test_switch_label_with_unknown_literal_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    if kind == Kind.Gamma:
        return False

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The literal 'Gamma' could not be found in the enumeration 'Kind'"
            ),
        )

    def test_switch_int_label_on_str_subject_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(text: str) -> bool:
    if text == 1:
        return False
    elif text == "beta":
        return True

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the label to be a str literal, the type of the "
                "subject of the switch, but got: int"
            ),
        )

    def test_switch_negative_label_on_length_subject_fails(self) -> None:
        source = """\
@verification
def some_func(text: str) -> bool:
    if len(text) == -1:
        return False
    elif len(text) == 1:
        return True

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the label to be a non-negative int literal, as "
                "the subject of the switch is a length, but got: -1"
            ),
        )

    def test_switch_str_label_on_enum_subject_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    if kind == "alpha":
        return False
    elif kind == Kind.Beta:
        return True

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the label to be a literal of the enumeration "
                "'Kind', the type of the subject of the switch, but got: str"
            ),
        )

    def test_comparison_of_length_with_constant(self) -> None:
        source = """\
@invariant(lambda self: len(self) > 0, "At least one character")
class Non_empty_string(str, DBC):
    pass


@verification
def some_func(text: str, name: Non_empty_string) -> bool:
    if len(text) == 0:
        return False

    return name == text


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.execute(source=source)

    def test_comparison_of_str_with_int_fails(self) -> None:
        source = """\
@verification
def some_func(text: str) -> bool:
    if text == 1:
        return False

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the operands of the comparison to be of comparable "
                "types, but got: str and int"
            ),
        )

    def test_comparison_of_bool_with_int_fails(self) -> None:
        source = """\
@verification
def some_func(flag: bool) -> bool:
    return flag == 1


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the operands of the comparison to be of comparable "
                "types, but got: bool and int"
            ),
        )

    def test_comparison_of_different_enumerations_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"


class Other_kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    if kind == Other_kind.Alpha:
        return False

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the operands of the comparison to be of comparable "
                "types, but got: Kind and Other_kind"
            ),
        )

    def test_comparison_of_enumeration_with_str_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"


@verification
def some_func(kind: Kind) -> bool:
    return kind != "alpha"


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the operands of the comparison to be of comparable "
                "types, but got: Kind and str"
            ),
        )

    def test_ordering_of_strings_and_booleans(self) -> None:
        source = """\
@invariant(lambda self: len(self) > 0, "At least one character")
class Non_empty_string(str, DBC):
    pass


@verification
def some_func(
    text: str, name: Non_empty_string, flag: bool, other_flag: bool
) -> bool:
    return "a" < text and name >= text and flag <= other_flag and flag > False


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.execute(source=source)

    def test_ordering_of_enumerations_fails(self) -> None:
        source = """\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


@verification
def some_func(kind: Kind) -> bool:
    return kind < Kind.Beta


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "We support the ordering comparisons only on the booleans, "
                "the numbers and the strings, but got: Kind and Kind"
            ),
        )

    def test_ordering_of_instances_fails(self) -> None:
        source = """\
class Something:
    some_property: int

    def __init__(self, some_property: int) -> None:
        self.some_property = some_property


@verification
def some_func(that: Something, other: Something) -> bool:
    return that >= other


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "We support the ordering comparisons only on the booleans, "
                "the numbers and the strings, but got: Something and Something"
            ),
        )

    def test_ordering_of_bytearrays_fails(self) -> None:
        source = """\
@verification
def some_func(that: bytearray, other: bytearray) -> bool:
    return that > other


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "We support the ordering comparisons only on the booleans, "
                "the numbers and the strings, but got: bytearray and bytearray"
            ),
        )

    def test_ordering_of_str_with_bool_fails(self) -> None:
        source = """\
@verification
def some_func(text: str, flag: bool) -> bool:
    return text < flag


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the operands of the comparison to be of comparable "
                "types, but got: str and bool"
            ),
        )

    def test_ordering_of_optional_str_fails(self) -> None:
        source = """\
@verification
def some_func(text: Optional[str]) -> bool:
    return text < "z"


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the left operand to be a non-None, but got: Optional[str]"
            ),
        )

    def test_modulo_negation_and_abs(self) -> None:
        source = """\
@invariant(lambda self: self % 2 == 0, "Even")
class Even_int(int, DBC):
    pass


@verification
def has_small_remainder(number: int) -> bool:
    remainder = number % 7
    return remainder < 3


@invariant(
    lambda self:
    self.even % -3 == 0
    and len(self.text) % 2 == 0
    and -self.number < 0
    and -(-self.number) > 0
    and -self.ratio < 0.0
    and abs(self.number) + abs(self.even) > 0
    and abs(self.ratio) < 1.0
    and has_small_remainder(self.number)
    and (
        not (self.optional_number is not None)
        or (
            self.optional_number % 5 == 4
            and -self.optional_number < 0
            and abs(self.optional_number) < 100
        )
    ),
    "Dummy invariant description"
)
class Something:
    even: Even_int
    text: str
    number: int
    ratio: float
    optional_number: Optional[int]

    def __init__(
        self,
        even: Even_int,
        text: str,
        number: int,
        ratio: float,
        optional_number: Optional[int] = None
    ) -> None:
        self.even = even
        self.text = text
        self.number = number
        self.ratio = ratio
        self.optional_number = optional_number

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        Test_with_smoke.execute(source=source)

    def test_modulo_on_float_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    self.ratio % 2 == 0,
    "Dummy invariant description"
)
class Something:
    ratio: float

    def __init__(self, ratio: float) -> None:
        self.ratio = ratio

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The modulo operation is only defined on integer numbers, "
                "but got as a left operand: float"
            ),
        )

    def test_modulo_on_optional_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    self.number % 2 == 0,
    "Dummy invariant description"
)
class Something:
    number: Optional[int]

    def __init__(self, number: Optional[int] = None) -> None:
        self.number = number

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the left operand to be a non-None, but got: Optional[int]"
            ),
        )

    def test_negation_of_length_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    -len(self.text) < 0,
    "Dummy invariant description"
)
class Something:
    text: str

    def __init__(self, text: str) -> None:
        self.text = text

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The arithmetic negation is only defined on integer and "
                "floating-point numbers, but got: length"
            ),
        )

    def test_negation_of_str_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    -self.text == self.text,
    "Dummy invariant description"
)
class Something:
    text: str

    def __init__(self, text: str) -> None:
        self.text = text

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The arithmetic negation is only defined on integer and "
                "floating-point numbers, but got: str"
            ),
        )

    def test_negation_of_optional_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    -self.number < 0,
    "Dummy invariant description"
)
class Something:
    number: Optional[int]

    def __init__(self, number: Optional[int] = None) -> None:
        self.number = number

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the operand to be a non-None, but got: Optional[int]"
            ),
        )

    def test_abs_of_length_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    abs(len(self.text)) > 0,
    "Dummy invariant description"
)
class Something:
    text: str

    def __init__(self, text: str) -> None:
        self.text = text

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "The absolute value is only defined on integer and "
                "floating-point numbers, but got: length"
            ),
        )

    def test_abs_of_optional_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    abs(self.number) > 0,
    "Dummy invariant description"
)
class Something:
    number: Optional[int]

    def __init__(self, number: Optional[int] = None) -> None:
        self.number = number

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the operand to be a non-None, but got: Optional[int]"
            ),
        )

    def test_len_of_optional_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    len(self.text) > 0,
    "Dummy invariant description"
)
class Something:
    text: Optional[str]

    def __init__(self, text: Optional[str] = None) -> None:
        self.text = text

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the argument of ``len`` to be a non-None, "
                "but got: Optional[str]. Please check for ``is not None`` first."
            ),
        )

    def test_len_of_optional_after_none_check_passes(self) -> None:
        source = """\
@invariant(
    lambda self:
    not (self.text is not None) or len(self.text) > 0,
    "Dummy invariant description"
)
class Something:
    text: Optional[str]

    def __init__(self, text: Optional[str] = None) -> None:
        self.text = text

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        Test_with_smoke.execute(source=source)

    def test_len_of_int_fails(self) -> None:
        source = """\
@invariant(
    lambda self:
    len(self.number) > 0,
    "Dummy invariant description"
)
class Something:
    number: int

    def __init__(self, number: int) -> None:
        self.number = number

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the argument of ``len`` to be a string, "
                "a bytearray, a list, a set, a tuple, a JSONArray or a JSONObject, "
                "since we know how to compute the length only of these types "
                "in all the target languages, but got: int"
            ),
        )


class Test_for_statement(unittest.TestCase):
    @staticmethod
    def source_with_verification(verification: str) -> str:
        return f"""\
{verification}

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

    def test_early_return(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for number in numbers:
        return number > 0

    return True"""
            )
        )

    def test_range_and_nested_loops(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for i in range(0, len(numbers)):
        number = numbers[i]
        for j in range(i, len(numbers)):
            return number > numbers[j]

    return True"""
            )
        )

    def test_reusing_loop_variable_in_another_loop(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], other_numbers: List[int]) -> bool:
    for x in numbers:
        return x > 0

    for x in other_numbers:
        return x > 1

    return True"""
            )
        )

    def test_redefining_variable_in_the_body_of_a_later_loop(self) -> None:
        # NOTE (mristin):
        # Each loop body is a block of its own in the targets, so each loop
        # declares its own ``y``. This is allowed, since neither loop can observe
        # the ``y`` of the other loop, and the behavior is the same as in Python.
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], other_numbers: List[int]) -> bool:
    for x in numbers:
        y = x + 1
        if y > 3:
            return False

    for x in other_numbers:
        y = x + 2
        if y > 3:
            return False

    return True"""
            )
        )

    def test_using_variable_of_the_previous_iteration_fails(self) -> None:
        # NOTE (mristin):
        # In Python, ``y`` holds the value of the previous iteration from
        # the second iteration on, while in the targets ``y`` is declared anew in
        # each iteration. Hence, reading ``y`` before it is assigned in the loop
        # body must fail.
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for x in numbers:
        if x > 0:
            y = y + x

        y = x

    return True"""
            ),
            expected_joined_message=(
                "The variable 'y' is read here before it is assigned in the body "
                "of the for-loop. While Python keeps the value of the previous "
                "iteration, the other targets define the variable anew in each "
                "iteration. Please define the variable before the for-loop."
            ),
        )

    def test_using_variable_of_the_previous_iteration_of_nested_loop_fails(
        self,
    ) -> None:
        # NOTE (mristin):
        # The ``y`` is assigned only in the inner loop, but read in the body of
        # the outer loop before the inner loop. In Python, the read observes
        # the ``y`` of the previous iteration of the outer loop, which is not
        # visible in the targets, so it must fail.
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], other_numbers: List[int]) -> bool:
    for x in numbers:
        if x > 0:
            if y > x:
                return False

        for z in other_numbers:
            y = z

    return True"""
            ),
            expected_joined_message=(
                "The variable 'y' is read here before it is assigned in the body "
                "of the for-loop. While Python keeps the value of the previous "
                "iteration, the other targets define the variable anew in each "
                "iteration. Please define the variable before the for-loop."
            ),
        )

    def test_reusing_loop_variable_with_another_type_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], texts: List[str]) -> bool:
    for x in numbers:
        return x > 0

    for x in texts:
        return len(x) > 0

    return True"""
            ),
            expected_joined_message=(
                "The variable 'x' has been already defined before with the type "
                "int, but now we inferred its type to be str. Python has only "
                "function-level scopes, and the static type checkers such as mypy "
                "refuse such re-definitions. Please use a different name."
            ),
        )

    def test_reusing_loop_variable_with_another_type_in_sibling_branches_fails(
        self,
    ) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], texts: List[str], text: str) -> bool:
    if text == "numbers":
        for x in numbers:
            return x > 0
    elif text == "texts":
        for x in texts:
            return len(x) > 0

    return True"""
            ),
            expected_joined_message=(
                "The variable 'x' has been already defined before with the type "
                "int, but now we inferred its type to be str. Python has only "
                "function-level scopes, and the static type checkers such as mypy "
                "refuse such re-definitions. Please use a different name."
            ),
        )

    def test_redefining_variable_of_loop_after_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for x in numbers:
        y = x

    y = "something"
    return len(y) > 0"""
            ),
            expected_joined_message=(
                "The variable 'y' has been already defined in a nested block "
                "before, such as a for-loop or a branch of a switch or of "
                "an if-statement. In Python, "
                "both definitions denote the same variable, while they denote "
                "two different variables in the target languages with block "
                "scopes, and some target languages, such as C#, refuse such "
                "re-declarations altogether. Please use a different name."
            ),
        )

    def test_redefining_loop_variable_after_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for x in numbers:
        return x > 0

    x = 1
    return x > 0"""
            ),
            expected_joined_message=(
                "The variable 'x' has been already defined in a nested block "
                "before, such as a for-loop or a branch of a switch or of "
                "an if-statement. In Python, "
                "both definitions denote the same variable, while they denote "
                "two different variables in the target languages with block "
                "scopes, and some target languages, such as C#, refuse such "
                "re-declarations altogether. Please use a different name."
            ),
        )

    def test_loop_in_switch_branch(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], text: str) -> bool:
    if text == "positive":
        for number in numbers:
            return number > 0
    elif text == "negative":
        for number in numbers:
            return number < 0

    return True"""
            )
        )

    def test_ending_with_exhaustive_switch_in_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], text: str) -> bool:
    for number in numbers:
        if text == "positive":
            return number > 0
        else:
            return number < 0"""
            ),
            expected_joined_message=(
                "Expected the verification function 'some_func' to end with "
                "a return statement, since it returns a value"
            ),
        )

    def test_using_loop_variable_after_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for x in numbers:
        return x > 0

    y = x

    for x in numbers:
        return x > 0

    return True"""
            ),
            expected_joined_message=(
                "The variable 'x' has been defined in a nested block before, "
                "such as a for-loop or a branch of a switch or of an if-statement, "
                "and is not visible here. While Python keeps the variable after "
                "the block, the other targets scope it to the block. Please define "
                "the variable before the block."
            ),
        )

    def test_using_variable_defined_in_loop_after_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for x in numbers:
        y = x

    return y > 0"""
            ),
            expected_joined_message=(
                "The variable 'y' has been defined in a nested block before, "
                "such as a for-loop or a branch of a switch or of an if-statement, "
                "and is not visible here. While Python keeps the variable after "
                "the block, the other targets scope it to the block. Please define "
                "the variable before the block."
            ),
        )

    def test_shadowing_argument_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], x: int) -> bool:
    for x in numbers:
        return x > 0

    return True"""
            ),
            expected_joined_message="The variable x has been already defined before",
        )

    def test_shadowing_in_nested_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for x in numbers:
        for x in numbers:
            return x > 0

    return True"""
            ),
            expected_joined_message="The variable x has been already defined before",
        )

    def test_assigning_to_loop_variable_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for x in numbers:
        x = 1

    return True"""
            ),
            expected_joined_message=(
                "The loop variable 'x' can not be assigned to in the body of "
                "the for-loop. Python does not change the iteration on such "
                "an assignment, while the targets would skip or repeat "
                "the iterations over a range, or refuse to compile "
                "the assignment to a read-only loop variable. Please use "
                "a different variable."
            ),
        )

    def test_missing_return_at_the_end_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    for x in numbers:
        return x > 0"""
            ),
            expected_joined_message=(
                "Expected the verification function 'some_func' to end with "
                "a return statement, since it returns a value"
            ),
        )

    def test_continue_in_nested_loops(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], text: str) -> bool:
    for number in numbers:
        if number == 0:
            continue

        for i in range(0, number):
            if text == "skip":
                continue
            else:
                continue

        if number == 1:
            return False

    return True"""
            )
        )

    def test_continue_outside_of_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    continue
    return True"""
            ),
            expected_joined_message=(
                "The ``continue`` statement is not within a for-loop"
            ),
        )

    def test_continue_in_switch_outside_of_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: str) -> bool:
    if text == "skip":
        continue

    return True"""
            ),
            expected_joined_message=(
                "The ``continue`` statement is not within a for-loop"
            ),
        )

    def test_break_in_nested_loops(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int], text: str) -> bool:
    for number in numbers:
        if number == 0:
            break

        for i in range(0, number):
            if text == "skip":
                break
            else:
                break

        if number == 1:
            return False

    return True"""
            )
        )

    def test_break_outside_of_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(numbers: List[int]) -> bool:
    break
    return True"""
            ),
            expected_joined_message=(
                "The ``break`` statement is not within a for-loop"
            ),
        )

    def test_break_in_switch_outside_of_loop_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: str) -> bool:
    if text == "skip":
        break

    return True"""
            ),
            expected_joined_message=(
                "The ``break`` statement is not within a for-loop"
            ),
        )


class Test_assignment_target(unittest.TestCase):
    @staticmethod
    def source_with_verification(verification: str) -> str:
        return f"""\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


class Item(DBC):
    text: str
    texts: List[str]
    pair: Tuple[str, int]
    values: JSONArray
    mapping: JSONObject[str]

    @implementation_specific
    @non_mutating
    def do_something(self) -> bool:
        pass

    def __init__(
        self,
        text: str,
        texts: List[str],
        pair: Tuple[str, int],
        values: JSONArray,
        mapping: JSONObject[str],
    ) -> None:
        self.text = text
        self.texts = texts
        self.pair = pair
        self.values = values
        self.mapping = mapping


{verification}


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

    def test_property_and_list_items(self) -> None:
        Test_with_smoke.execute(
            Test_assignment_target.source_with_verification(
                """\
@verification
def some_func(items: List[Item], text: str) -> bool:
    items[0].text = text
    items[-1].texts[0] = text
    texts = items[0].texts
    texts[-1] = text
    return True"""
            )
        )

    def test_tuple_item_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_assignment_target.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    item.pair[0] = "x"
    return True"""
            ),
            expected_joined_message=(
                "Tuples are immutable in Python, so the item of "
                "Tuple[str, int] can not be assigned to."
            ),
        )

    def test_json_array_item_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_assignment_target.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    item.values[0] = item.mapping
    return True"""
            ),
            expected_joined_message=(
                "We do not support mutating JSON-able values, so the item of "
                "JSONArray can not be assigned to."
            ),
        )

    def test_json_object_item_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_assignment_target.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    item.mapping["x"] = item.values
    return True"""
            ),
            expected_joined_message=(
                "We do not support mutating JSON-able values, so the item of "
                "JSONObject[str] can not be assigned to."
            ),
        )

    def test_method_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_assignment_target.source_with_verification(
                """\
@verification
def some_func(item: Item, other: Item) -> bool:
    item.do_something = other.do_something
    return True"""
            ),
            expected_joined_message=(
                "The method 'do_something' of Item can not be assigned to."
            ),
        )

    def test_enumeration_literal_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_assignment_target.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    Kind.Alpha = Kind.Beta
    return True"""
            ),
            expected_joined_message=(
                "The enumeration literal Kind.Alpha can not be assigned to."
            ),
        )

    def test_string_method_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_assignment_target.source_with_verification(
                """\
@verification
def some_func(item: Item, other: Item) -> bool:
    item.text.find = other.text.find
    return True"""
            ),
            expected_joined_message=(
                "The method 'find' of strings can not be assigned to."
            ),
        )

    def test_slice_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_assignment_target.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    item.text[0:1] = "x"
    return True"""
            ),
            expected_joined_message=(
                "Expected the target of an assignment to be a variable, "
                "a property of a class or an item of a list, but got: Slice"
            ),
        )


class Test_mutability(unittest.TestCase):
    @staticmethod
    def source_with_verification(verification: str) -> str:
        return f"""\
class Item(DBC):
    text: str
    texts: List[str]

    @implementation_specific
    @non_mutating
    def child(self) -> "Item":
        pass

    @implementation_specific
    def touch(self) -> bool:
        pass

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

    def test_mutations_of_mutable_values(self) -> None:
        Test_with_smoke.execute(
            Test_mutability.source_with_verification(
                """\
@verification
def some_func(items: List[Item], lists: List[List[str]], text: str) -> bool:
    for item in items:
        item.text = text
        item.texts = list(item.texts)

    for texts in lists:
        texts[0] = text

    alias = items[0]
    alias.texts[0] = text
    return fill(items[0].texts, text)"""
            )
        )

    def test_index_on_sequence_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(texts: Sequence[str]) -> bool:
    texts[0] = "x"
    return True"""
            ),
            expected_joined_message=(
                "We can not assign to an item of the list of texts, since the "
                "argument 'texts' is declared as a Sequence, which is "
                "read-only. Please declare it as a List if the function "
                "mutates it."
            ),
        )

    def test_member_on_read_only_object_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    item.text = "x"
    return True"""
            ),
            expected_joined_message=(
                "We can not assign to the property 'text' of item, since the "
                "argument 'item' is read-only. Please declare it as "
                "Mutable[...] if the function mutates it."
            ),
        )

    def test_temporary_to_mutable_argument_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Mutable["Item"]) -> bool:
    return fill(list(item.texts), "x")"""
            ),
            expected_joined_message=(
                "The argument 'texts' of the verification function 'fill' is "
                "mutable, so we expect a variable, a property or an item of a "
                "list or a tuple so that the mutation is observable, but got "
                "a temporary value."
            ),
        )

    def test_read_only_to_mutable_argument_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    return fill(item.texts, "x")"""
            ),
            expected_joined_message=(
                "The argument 'texts' of the verification function 'fill' is "
                "mutable, but the argument 'item' is read-only. Please "
                "declare it as Mutable[...] if the function mutates it."
            ),
        )

    def test_mutating_method_on_read_only_instance_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    return item.touch()"""
            ),
            expected_joined_message=(
                "The method 'touch' is not marked as @non_mutating, so it "
                "might mutate its instance, but the argument 'item' is "
                "read-only. Please declare it as Mutable[...] if the function "
                "mutates it."
            ),
        )

    def test_tuple_with_read_only_item_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Item) -> bool:
    t = (item, 1)
    t[0].text = "x"
    return True"""
            ),
            expected_joined_message=(
                "We can not assign to the property 'text' of t[0], since the "
                "variable 't' has been defined from a read-only value, and "
                "the mutability of a variable is fixed at its definition; the "
                "value was read-only, as the tuple holds a read-only item, as "
                "the argument 'item' is read-only. Please declare it as "
                "Mutable[...] if the function mutates it."
            ),
        )

    def test_method_result_is_read_only(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Mutable["Item"]) -> bool:
    c = item.child()
    c.text = "x"
    return True"""
            ),
            expected_joined_message=(
                "We can not assign to the property 'text' of c, since the "
                "variable 'c' has been defined from a read-only value, and "
                "the mutability of a variable is fixed at its definition; the "
                "value was read-only, as the result of a method call is "
                "read-only."
            ),
        )

    def test_mutable_variable_reassigned_read_only_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(a: List[str], b: Sequence[str]) -> bool:
    ys = a
    ys = b
    return True"""
            ),
            expected_joined_message=(
                "The variable 'ys' is mutable, so it can be re-assigned only "
                "a mutable value, but the argument 'b' is declared as a "
                "Sequence, which is read-only. Please declare it as a List if "
                "the function mutates it."
            ),
        )

    def test_read_only_variable_stays_read_only(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(a: List[str], b: Sequence[str]) -> bool:
    zs = b
    zs = a
    zs[0] = "x"
    return True"""
            ),
            expected_joined_message=(
                "We can not assign to an item of the list of zs, since the "
                "variable 'zs' has been defined from a read-only value, and "
                "the mutability of a variable is fixed at its definition; the "
                "value was read-only, as the argument 'b' is declared as a "
                "Sequence, which is read-only. Please declare it as a List if "
                "the function mutates it."
            ),
        )

    def test_storing_read_only_object_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(items: List[Item], item: Item) -> bool:
    items[0] = item
    return True"""
            ),
            expected_joined_message=(
                "The value assigned to an item of the list of items would "
                "become mutable through it, so it needs to be mutable itself, "
                "but the argument 'item' is read-only. Please declare it as "
                "Mutable[...] if the function mutates it."
            ),
        )

    def test_storing_reference_to_list_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Mutable["Item"], texts: List[str]) -> bool:
    item.texts = texts
    return True"""
            ),
            expected_joined_message=(
                "The value assigned to the property 'texts' of item holds a "
                "list, which Python would share, but C++ would copy. We can "
                "not transpile the sharing to C++, so please assign an "
                "explicit copy of the list, *e.g.*, ``list(texts)``."
            ),
        )

    def test_slice_of_list_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Mutable["Item"], texts: List[str]) -> bool:
    item.texts = texts[:]
    return True"""
            ),
            expected_joined_message=(
                "We do not support slicing a list. If you want to copy the list, "
                "please use ``list(texts)``, which mypy accepts for a read-only "
                "``Sequence`` as well."
            ),
        )

    def test_copy_of_read_only_list_is_mutable(self) -> None:
        Test_with_smoke.execute(
            Test_mutability.source_with_verification(
                """\
@verification
def some_func(item: Mutable["Item"], texts: Sequence[str]) -> bool:
    item.texts = list(texts)

    copied: List[str] = list(texts)
    copied[0] = "x"
    return fill(copied, "y")"""
            )
        )

    def test_list_without_arguments_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(texts: Sequence[str]) -> bool:
    return len(list()) > 0"""
            ),
            expected_joined_message=(
                "We support ``list(...)`` only to copy a list, so we expect "
                "exactly one argument, but got 0."
            ),
        )

    def test_list_of_string_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(text: str) -> bool:
    return len(list(text)) > 0"""
            ),
            expected_joined_message=(
                "We support ``list(...)`` only to copy a non-None list, but got: str"
            ),
        )

    def test_list_of_optional_list_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(texts: Optional[Sequence[str]]) -> bool:
    return len(list(texts)) > 0"""
            ),
            expected_joined_message=(
                "We support ``list(...)`` only to copy a non-None list, "
                "but got: Optional[List[str]]. Please check for ``is not None`` "
                "first."
            ),
        )

    def test_read_only_value_in_mutable_variable_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(texts: Optional[Sequence[str]]) -> bool:
    maybe_texts: Optional[List[str]] = texts
    return maybe_texts is not None"""
            ),
            expected_joined_message=(
                "The variable 'maybe_texts' is declared as mutable with "
                "``Optional[List[str]]``, but the argument 'texts' is declared as "
                "a Sequence, which is read-only. Please declare it as a List if "
                "the function mutates it. Alternatively, please copy the list with "
                "``list(texts)``, or declare "
                "the variable with ``Sequence[...]`` instead of ``List[...]`` if "
                "you do not mutate it."
            ),
        )

    def test_read_only_value_in_read_only_variable_passes(self) -> None:
        Test_with_smoke.execute(
            Test_mutability.source_with_verification(
                """\
@verification
def some_func(texts: Optional[Sequence[str]]) -> bool:
    maybe_texts: Optional[Sequence[str]] = texts
    return maybe_texts is not None"""
            )
        )

    def test_copy_of_nested_lists_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(lists: List[List[str]]) -> bool:
    return len(list(lists)) > 0"""
            ),
            expected_joined_message=(
                "We can not copy the list of type List[List[str]] with "
                "``list(...)``, since its items hold lists or sets themselves. "
                "Python copies the list shallowly, so that the copy shares "
                "the inner lists and sets, while C++ copies them as well. We do "
                "not support deep copies at the moment. Please contact "
                "the developers if you need this feature."
            ),
        )

    def test_loop_over_read_only_collection_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_mutability.source_with_verification(
                """\
@verification
def some_func(items: Sequence[Item]) -> bool:
    for item in items:
        item.text = "x"
    return True"""
            ),
            expected_joined_message=(
                "We can not assign to the property 'text' of item, since the "
                "loop variable 'item' iterates over a read-only collection."
            ),
        )


class Test_if_statement(unittest.TestCase):
    def test_chain_with_default(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: str, number: int) -> bool:
    if len(text) > 3 and number > 0:
        return False
    elif number < 0 or text == "something":
        pass
    else:
        x = number + 1
        return x > 0

    return True"""
            )
        )

    def test_if_in_default_of_switch(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: str, number: int) -> bool:
    if number == 1:
        return False
    elif len(text) > 0:
        return True
    elif number == 2:
        return True

    return False"""
            )
        )

    def test_non_boolean_condition_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: str) -> bool:
    if len(text):
        return False

    return True"""
            ),
            expected_joined_message=(
                "Expected the condition of the if-statement to be a boolean, "
                "but got: length"
            ),
        )

    def test_optional_condition_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(flag: Optional[bool]) -> bool:
    if flag:
        return False

    return True"""
            ),
            expected_joined_message=(
                "Expected the condition of the if-statement to be a boolean, "
                "but got: Optional[bool]"
            ),
        )

    def test_using_variable_defined_in_branch_after_if_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(number: int) -> bool:
    if number > 0:
        x = 1
    else:
        x = 2

    return x > 0"""
            ),
            expected_joined_message=(
                "The variable 'x' has been defined in a nested block before, "
                "such as a for-loop or a branch of a switch or of an if-statement, "
                "and is not visible here. While Python keeps the variable after "
                "the block, the other targets scope it to the block. Please define "
                "the variable before the block."
            ),
        )

    def test_redefining_variable_in_a_later_if(self) -> None:
        # NOTE (mristin):
        # Each if-statement is a block of its own in the targets, so each one
        # declares its own ``x``. This is allowed, since the later if-statement
        # assigns ``x`` before reading it, and never observes the ``x`` of
        # the earlier one.
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(number: int) -> bool:
    if number > 0:
        x = 1
        if x > number:
            return False

    if number > 1:
        x = 2
        if x > number:
            return False

    return True"""
            )
        )

    def test_using_variable_of_an_earlier_if_in_a_later_if_fails(self) -> None:
        # NOTE (mristin):
        # In Python, the later if-statement reads the ``x`` of the earlier one,
        # while in the targets that ``x`` is not visible outside its block.
        # Hence, reading ``x`` before it is assigned in the later block must fail.
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(number: int) -> bool:
    if number > 0:
        x = 1
        if x > number:
            return False

    if number > 1:
        return x > number

    return True"""
            ),
            expected_joined_message=(
                "The variable 'x' has been defined in a nested block before, "
                "such as a for-loop or a branch of a switch or of an if-statement, "
                "and is not visible here. While Python keeps the variable after "
                "the block, the other targets scope it to the block. Please define "
                "the variable before the block."
            ),
        )

    def test_incrementing_variable_of_an_earlier_if_in_a_later_if_fails(
        self,
    ) -> None:
        # NOTE (mristin):
        # Re-assigning ``x`` in the later block would be allowed, but ``x + 1``
        # reads ``x`` before it is assigned in the block. In Python, it would read
        # the ``x`` of the earlier if-statement, which is not visible in
        # the targets, so it must fail.
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(number: int) -> bool:
    if number > 0:
        x = 1
        if x > number:
            return False

    if number > 1:
        x = x + 1

    return True"""
            ),
            expected_joined_message=(
                "The variable 'x' has been defined in a nested block before, "
                "such as a for-loop or a branch of a switch or of an if-statement, "
                "and is not visible here. While Python keeps the variable after "
                "the block, the other targets scope it to the block. Please define "
                "the variable before the block."
            ),
        )


class Test_assert_statement(unittest.TestCase):
    def test_narrowing_after_assertion(self) -> None:
        Test_with_smoke.execute(
            Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: Optional[str]) -> bool:
    assert text is not None, "Expected a text, but got none"
    return len(text) > 0"""
            )
        )

    def test_non_boolean_condition_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: str) -> bool:
    assert len(text)
    return True"""
            ),
            expected_joined_message=(
                "Expected the condition of the assertion to be a boolean, "
                "but got: length"
            ),
        )

    def test_optional_condition_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(flag: Optional[bool]) -> bool:
    assert flag
    return True"""
            ),
            expected_joined_message=(
                "Expected the condition of the assertion to be a boolean, "
                "but got: Optional[bool]"
            ),
        )

    def test_message_is_not_narrowed_by_condition_fails(self) -> None:
        # NOTE (mristin):
        # The message is evaluated only if the condition does not hold.
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: Optional[str]) -> bool:
    assert text is not None, f"Unexpected text of length {len(text)}"
    return True"""
            ),
            expected_joined_message=(
                "Expected the argument of ``len`` to be a non-None, but got: "
                "Optional[str]. Please check for ``is not None`` first."
            ),
        )

    def test_narrowing_does_not_leak_out_of_branch_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_for_statement.source_with_verification(
                """\
@verification
def some_func(text: Optional[str], flag: bool) -> bool:
    if flag:
        assert text is not None

    return len(text) > 0"""
            ),
            expected_joined_message=(
                "Expected the argument of ``len`` to be a non-None, but got: "
                "Optional[str]. Please check for ``is not None`` first."
            ),
        )


class Test_narrowing_in_statements(unittest.TestCase):
    @staticmethod
    def source_with_verification(verification: str) -> str:
        return f"""\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    optional_text: Optional[str]

    def __init__(self, optional_text: Optional[str] = None) -> None:
        self.optional_text = optional_text


class Child_a(Parent, DBC):
    a_only: int

    def __init__(self, a_only: int, optional_text: Optional[str] = None) -> None:
        Parent.__init__(self, optional_text)
        self.a_only = a_only


class Child_b(Parent, DBC):
    b_only: int

    def __init__(self, b_only: int, optional_text: Optional[str] = None) -> None:
        Parent.__init__(self, optional_text)
        self.b_only = b_only


class Holder(DBC):
    parents: List[Parent]
    number: int
    parent: Optional[Parent]

    def __init__(
        self, parents: List[Parent], number: int, parent: Optional[Parent] = None
    ) -> None:
        self.parent = parent
        self.parents = parents
        self.number = number


{verification}


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

    def expect_success(self, verification: str) -> None:
        Test_with_smoke.execute(
            Test_narrowing_in_statements.source_with_verification(verification)
        )

    def expect_failure(self, verification: str, expected_message: str) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_narrowing_in_statements.source_with_verification(verification),
            expected_joined_message=expected_message,
        )

    def test_narrowing_in_body(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent]) -> bool:
    if x is not None and isinstance(x, Child_a):
        return x.a_only > 0

    return True"""
        )

    def test_narrowing_in_elif_and_else_by_negation(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent]) -> bool:
    if x is None:
        return False
    elif not isinstance(x, Child_a):
        return x.optional_text is None
    else:
        return x.a_only > 0"""
        )

    def test_narrowing_by_de_morgan_and_not(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent]) -> bool:
    if not (x is None or not isinstance(x, Child_a)):
        return x.a_only > 0

    return True"""
        )

    def test_narrowing_after_early_return(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent]) -> bool:
    if x is None or not isinstance(x, Child_a):
        return False

    return x.a_only > 0"""
        )

    def test_narrowing_after_continue(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(parents: List[Parent]) -> bool:
    for parent in parents:
        if not isinstance(parent, Child_a):
            continue

        if parent.optional_text is None:
            return False

        if len(parent.optional_text) > parent.a_only:
            return False

    return True"""
        )

    def test_narrowing_after_the_only_completing_branch(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent]) -> bool:
    if x is not None and isinstance(x, Child_a):
        pass
    else:
        return False

    return x.a_only > 0"""
        )

    def test_narrowing_after_the_only_completing_middle_branch(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent], flag: bool) -> bool:
    if flag:
        return False
    elif x is not None:
        pass
    else:
        return False

    return x.optional_text is None"""
        )

    def test_narrowing_common_to_all_completing_branches(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent], flag: bool) -> bool:
    if x is None:
        return False
    elif flag:
        pass
    else:
        pass

    return x.optional_text is None"""
        )

    def test_no_narrowing_on_two_different_completing_branches_fails(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(x: Optional[Parent], flag: bool) -> bool:
    if x is not None:
        pass
    elif flag:
        pass
    else:
        return False

    return x.optional_text is None""",
            "Expected an instance type to be a non-None, either an "
            "enumeration-as-type or our type, but inferred an Optional: "
            "Optional[Parent]",
        )

    def test_no_narrowing_after_if_whose_body_can_complete_fails(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(x: Optional[Parent]) -> bool:
    if x is not None:
        pass

    return x.optional_text is None""",
            "Expected an instance type to be a non-None, either an "
            "enumeration-as-type or our type, but inferred an Optional: "
            "Optional[Parent]",
        )

    def test_narrowing_does_not_leak_out_of_branch(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(x: Optional[Parent], flag: bool) -> bool:
    if flag:
        if x is None:
            return False

        if x.optional_text is None:
            return False

    return x.optional_text is None""",
            "Expected an instance type to be a non-None, either an "
            "enumeration-as-type or our type, but inferred an Optional: "
            "Optional[Parent]",
        )

    def test_assignment_in_branch_does_not_leak_into_sibling(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent], y: Optional[Parent], flag: bool) -> bool:
    if x is None:
        return False

    if flag:
        x = y
    elif x.optional_text is None:
        return False

    return True"""
        )

    def test_assignment_invalidates_narrowing(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(x: Optional[Parent], y: Optional[Parent]) -> bool:
    if x is None:
        return False

    x = y
    return x.optional_text is None""",
            "Expected an instance type to be a non-None, either an "
            "enumeration-as-type or our type, but inferred an Optional: "
            "Optional[Parent]",
        )

    def test_assignment_in_completing_branch_invalidates_narrowing(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(x: Optional[Parent], y: Optional[Parent], flag: bool) -> bool:
    if x is None:
        return False

    if flag:
        x = y

    return x.optional_text is None""",
            "Expected an instance type to be a non-None, either an "
            "enumeration-as-type or our type, but inferred an Optional: "
            "Optional[Parent]",
        )

    def test_assignment_in_exiting_branch_keeps_narrowing(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent], y: Optional[Parent], flag: bool) -> bool:
    if x is None:
        return False

    if flag:
        x = y
        return True

    return x.optional_text is None"""
        )

    def test_assignment_later_in_loop_invalidates_narrowing(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(
    x: Optional[Parent], y: Optional[Parent], numbers: List[int]
) -> bool:
    if x is None:
        return False

    for number in numbers:
        if x.optional_text is None:
            return False

        x = y

    return True""",
            "Expected an instance type to be a non-None, either an "
            "enumeration-as-type or our type, but inferred an Optional: "
            "Optional[Parent]",
        )

    def test_assignment_to_other_property_keeps_narrowing(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(holder: Mutable[Holder]) -> bool:
    if holder.parent is None:
        return False

    holder.number = 5
    return holder.parent.optional_text is None"""
        )

    def test_assignment_to_prefix_invalidates_narrowing(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(holder: Mutable[Holder], parent: Mutable[Parent]) -> bool:
    if holder.parent is None or holder.parent.optional_text is None:
        return False

    holder.parent = parent
    return len(holder.parent.optional_text) > 0""",
            "Expected the argument of ``len`` to be a non-None, but got: "
            "Optional[str]. Please check for ``is not None`` first.",
        )

    def test_assignment_to_other_literal_index_keeps_narrowing(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(holder: Mutable[Holder], child: Mutable[Child_b]) -> bool:
    if not isinstance(holder.parents[0], Child_a):
        return False

    holder.parents[1] = child
    return holder.parents[0].a_only > 0"""
        )

    def test_assignment_to_non_literal_index_invalidates_narrowing(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(
    holder: Mutable[Holder], child: Mutable[Child_b], i: int
) -> bool:
    if not isinstance(holder.parents[0], Child_a):
        return False

    holder.parents[i] = child
    return holder.parents[0].a_only > 0""",
            "The member 'a_only' could not be found in the class 'Parent'",
        )

    def test_assignment_to_index_variable_invalidates_only_its_narrowing(
        self,
    ) -> None:
        self.expect_failure(
            """\
@verification
def some_func(parents: List[Parent], i: int, j: int) -> bool:
    if not isinstance(parents[i], Child_a) or not isinstance(parents[j], Child_b):
        return False

    i = i + 1
    if parents[j].b_only > 0:
        return False

    return parents[i].a_only > 0""",
            "The member 'a_only' could not be found in the class 'Parent'",
        )

    def test_narrowing_from_assigned_value(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(parent: Parent, child: Child_a) -> bool:
    x = parent
    x = child
    return x.a_only > 0"""
        )

    def test_narrowing_from_assigned_value_in_all_completing_branches(
        self,
    ) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Parent) -> bool:
    text = x.optional_text
    if text is None:
        text = "default"

    return len(text) > 0"""
        )

    def test_narrowing_survives_assignment_satisfying_it(self) -> None:
        self.expect_success(
            """\
@verification
def some_func(x: Optional[Parent], y: Parent, flag: bool) -> bool:
    if x is None:
        return False

    if flag:
        x = y

    return x.optional_text is None"""
        )

    def test_narrowing_from_assigned_value_does_not_outlive_its_branch(
        self,
    ) -> None:
        self.expect_failure(
            """\
@verification
def some_func(parent: Parent, child: Child_a, flag: bool) -> bool:
    x = parent
    if flag:
        x = child

    return x.a_only > 0""",
            "The member 'a_only' could not be found in the class 'Parent'",
        )

    def test_narrowing_of_variable_does_not_outlive_its_scope(self) -> None:
        self.expect_failure(
            """\
@verification
def some_func(parent: Parent, child: Child_a, flag: bool) -> bool:
    if flag:
        x = parent
        x = child
    else:
        return False

    if not flag:
        x = parent
        return x.a_only > 0

    return True""",
            "The member 'a_only' could not be found in the class 'Parent'",
        )

    def test_narrowing_of_self_in_method(self) -> None:
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source="""\
class Something(DBC):
    y: int
    x: Optional[str]

    def update(self) -> int:
        if self.x is None:
            return 0

        self.y = 5
        return len(self.x)

    def __init__(self, y: int, x: Optional[str] = None) -> None:
        self.x = x
        self.y = y


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        _, errors = intermediate_type_inference.infer(symbol_table=symbol_table)
        assert errors is None, tests.common.most_underlying_messages(errors)


class Test_is_instance(unittest.TestCase):
    @staticmethod
    def infer(source: str) -> intermediate_type_inference.InferenceOfInvariant:
        """Infer the types in the only invariant of the class ``Something``."""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        something = symbol_table.must_find_concrete_class(Identifier("Something"))
        assert len(something.invariants) == 1

        environment = intermediate_type_inference.MutableEnvironment(
            parent=intermediate_type_inference.populate_base_environment(
                symbol_table=symbol_table
            )
        )
        environment.set(
            Identifier("self"),
            intermediate_type_inference.OurTypeAnnotation(our_type=something),
        )

        inference, inference_error = intermediate_type_inference.infer_for_invariant(
            invariant=something.invariants[0], environment=environment
        )

        if inference_error is not None:
            raise AssertionError(
                tests.common.most_underlying_messages([inference_error])
            )

        assert inference is not None
        return inference

    def expect_downcasts(
        self, source: str, expected_downcasts: List[Tuple[str, str]]
    ) -> None:
        """Expect the down-casts as pairs (source code of the node, class)."""
        inference = Test_is_instance.infer(source)

        self.assertListEqual(
            expected_downcasts,
            [
                (ast.unparse(node.original_node), str(downcast.target))
                for node, downcast in inference.downcast_map.items()
            ],
        )

    def expect_error(self, source: str, expected_message: str) -> None:
        with self.assertRaises(AssertionError) as context:
            Test_is_instance.infer(source)

        self.assertEqual(expected_message, str(context.exception))

    def test_narrowing_in_conjunction(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self: isinstance(self.parent, Child) and len(self.parent.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_downcasts(source, [("self.parent", "Child")])

    def test_narrowing_in_implication(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self: not isinstance(self.parent, Child) or len(self.parent.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_downcasts(source, [("self.parent", "Child")])

    def test_narrowing_in_disjunction_with_negation(self) -> None:
        # NOTE (mristin):
        # A disjunction of two values with the first one negated is parsed as
        # an implication, so we need three values here.
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self:
    not isinstance(self.parent, Child)
    or len(self.parent.text) == 0
    or self.parent.text == "something",
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_downcasts(
            source, [("self.parent", "Child"), ("self.parent", "Child")]
        )

    def test_narrowing_in_all(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self:
    all(
        not isinstance(parent, Child) or len(parent.text) > 0
        for parent in self.parents
    ),
    "Dummy invariant description"
)
class Something(DBC):
    parents: List[Parent]

    def __init__(self, parents: List[Parent]) -> None:
        self.parents = parents


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_downcasts(source, [("parent", "Child")])

    def test_narrowing_over_two_levels_of_class_hierarchy(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    pass


class Grandchild(Child, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self:
    isinstance(self.parent, Child)
    and isinstance(self.parent, Grandchild)
    and len(self.parent.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_downcasts(
            source, [("self.parent", "Child"), ("self.parent", "Grandchild")]
        )

    def test_narrowing_of_nested_named_unions(self) -> None:
        source = """\
@serialization(with_model_type=True)
class Leaf(DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@serialization(with_model_type=True)
class Other_leaf(DBC):
    pass


Inner = Union[Leaf, Other_leaf]


@serialization(with_model_type=True)
class Wrapper(DBC):
    inner: Inner

    def __init__(self, inner: Inner) -> None:
        self.inner = inner


Outer = Union[Wrapper, Inner]


@invariant(
    lambda self:
    isinstance(self.outer, Wrapper)
    and isinstance(self.outer.inner, Leaf)
    and len(self.outer.inner.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    outer: Outer

    def __init__(self, outer: Outer) -> None:
        self.outer = outer


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_downcasts(
            source,
            [
                ("self.outer", "Wrapper"),
                ("self.outer", "Wrapper"),
                ("self.outer.inner", "Leaf"),
            ],
        )

    def test_narrowing_of_named_union_with_abstract_root(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@serialization(with_model_type=True)
class Other(DBC):
    pass


Some_union = Union[Parent, Other]


@invariant(
    lambda self:
    isinstance(self.value, Parent)
    and isinstance(self.value, Child)
    and len(self.value.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    value: Some_union

    def __init__(self, value: Some_union) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        inference = Test_is_instance.infer(source)

        # NOTE (mristin):
        # The source of every down-cast is the named union, as the targets need
        # to extract the underlying instance of the union before casting it.
        self.assertListEqual(
            [
                ("self.value", "Some_union as Parent"),
                ("self.value", "Some_union as Child"),
            ],
            [
                (ast.unparse(node.original_node), str(downcast))
                for node, downcast in inference.downcast_map.items()
            ],
        )

    def test_narrowing_does_not_leak_out_of_its_scope(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


@invariant(
    lambda self:
    (isinstance(self.parent, Child) and len(self.parent.text) > 0)
    or self.parent.text == "something",
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source, "The member 'text' could not be found in the class 'Parent'"
        )

    def test_no_narrowing_on_tuple(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


class Another_child(Parent, DBC):
    pass


@invariant(
    lambda self:
    isinstance(self.parent, (Child, Another_child))
    and len(self.parent.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source, "The member 'text' could not be found in the class 'Parent'"
        )

    def test_fails_on_optional_value(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    pass


@invariant(
    lambda self: isinstance(self.parent, Child),
    "Dummy invariant description"
)
class Something(DBC):
    parent: Optional[Parent]

    def __init__(self, parent: Optional[Parent] = None) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the value to be a non-None for ``isinstance``, "
            "but got: Optional[Parent]. Please check for ``is not None`` first.",
        )

    def test_fails_on_primitive_value(self) -> None:
        source = """\
class Some_class(DBC):
    pass


@invariant(
    lambda self: isinstance(self.text, Some_class),
    "Dummy invariant description"
)
class Something(DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the value to be an instance of a class or "
            "of a named union for ``isinstance``, but got: str",
        )

    def test_fails_on_the_same_class(self) -> None:
        source = """\
class Parent(DBC):
    pass


@invariant(
    lambda self: isinstance(self.parent, Parent),
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Parent' to be a strict descendant of the class "
            "'Parent' of the value in ``isinstance``, but it is not, "
            "so the check always holds",
        )

    def test_fails_on_class_not_in_named_union(self) -> None:
        source = """\
@serialization(with_model_type=True)
class First(DBC):
    pass


@serialization(with_model_type=True)
class Second(DBC):
    pass


class Unrelated(DBC):
    pass


Some_union = Union[First, Second]


@invariant(
    lambda self: isinstance(self.value, Unrelated),
    "Dummy invariant description"
)
class Something(DBC):
    value: Some_union

    def __init__(self, value: Some_union) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Unrelated' to be a root of the named union "
            "'Some_union' of the value in ``isinstance``, or a descendant of "
            "a root, but it is not. The roots are: First, Second",
        )

    def test_fails_on_an_unrelated_class(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    pass


class Unrelated(DBC):
    pass


@invariant(
    lambda self: isinstance(self.parent, Unrelated),
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Unrelated' to be a strict descendant of the class "
            "'Parent' of the value in ``isinstance``, but it is not, "
            "so the check never holds",
        )

    def test_fails_on_a_sibling_class(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    pass


class Another_child(Parent, DBC):
    pass


@invariant(
    lambda self: isinstance(self.child, Another_child),
    "Dummy invariant description"
)
class Something(DBC):
    child: Child

    def __init__(self, child: Child) -> None:
        self.child = child


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Another_child' to be a strict descendant "
            "of the class 'Child' of the value in ``isinstance``, but it is not, "
            "so the check never holds",
        )

    def test_fails_on_an_ancestor_class(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    pass


@invariant(
    lambda self: isinstance(self.child, Parent),
    "Dummy invariant description"
)
class Something(DBC):
    child: Child

    def __init__(self, child: Child) -> None:
        self.child = child


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Parent' to be a strict descendant of the class "
            "'Child' of the value in ``isinstance``, but it is not, "
            "so the check always holds",
        )

    def test_fails_on_an_unrelated_class_in_a_tuple(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class Child(Parent, DBC):
    pass


class Unrelated(DBC):
    pass


@invariant(
    lambda self: isinstance(self.parent, (Child, Unrelated)),
    "Dummy invariant description"
)
class Something(DBC):
    parent: Parent

    def __init__(self, parent: Parent) -> None:
        self.parent = parent


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Unrelated' to be a strict descendant of the class "
            "'Parent' of the value in ``isinstance``, but it is not, "
            "so the check never holds",
        )

    def test_fails_on_narrowing_to_a_sibling_outside_named_union(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class First(Parent, DBC):
    pass


class Second(Parent, DBC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text


Some_union = Union[First]


@invariant(
    lambda self: isinstance(self.value, Second) and len(self.value.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    value: Some_union

    def __init__(self, value: Some_union) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Second' to be a root of the named union "
            "'Some_union' of the value in ``isinstance``, or a descendant of "
            "a root, but it is not. The roots are: First",
        )

    def test_fails_on_narrowing_to_an_abstract_parent_of_named_union(self) -> None:
        source = """\
@abstract
@serialization(with_model_type=True)
class Parent(DBC):
    pass


class First(Parent, DBC):
    pass


class Second(Parent, DBC):
    pass


Some_union = Union[First, Second]


@invariant(
    lambda self: isinstance(self.value, Parent),
    "Dummy invariant description"
)
class Something(DBC):
    value: Some_union

    def __init__(self, value: Some_union) -> None:
        self.value = value


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Parent' to be a root of the named union "
            "'Some_union' of the value in ``isinstance``, or a descendant of "
            "a root, but it is not. The roots are: First, Second",
        )

    def test_fails_on_narrowing_to_a_class_outside_nested_named_union(self) -> None:
        source = """\
@serialization(with_model_type=True)
class Leaf(DBC):
    pass


@serialization(with_model_type=True)
class Other_leaf(DBC):
    pass


Inner = Union[Leaf, Other_leaf]


@serialization(with_model_type=True)
class Wrapper(DBC):
    inner: Inner

    def __init__(self, inner: Inner) -> None:
        self.inner = inner


Outer = Union[Wrapper, Inner]


@invariant(
    lambda self:
    isinstance(self.outer, Wrapper)
    and isinstance(self.outer.inner, Wrapper),
    "Dummy invariant description"
)
class Something(DBC):
    outer: Outer

    def __init__(self, outer: Outer) -> None:
        self.outer = outer


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_error(
            source,
            "Expected the class 'Wrapper' to be a root of the named union "
            "'Inner' of the value in ``isinstance``, or a descendant of "
            "a root, but it is not. The roots are: Leaf, Other_leaf",
        )


class Test_string_slicing_and_find(unittest.TestCase):
    @staticmethod
    def source_with_invariant(condition: str, property_type: str = "str") -> str:
        """Generate the source of a meta-model with a single invariant."""
        return f"""\
@invariant(
    lambda self: {condition},
    "Dummy invariant description"
)
class Something(DBC):
    text: {property_type}

    def __init__(self, text: {property_type}) -> None:
        self.text = text


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

    @staticmethod
    def infer_type_map(source: str) -> Mapping[str, str]:
        """Infer the types in the only invariant, keyed by the source code."""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        something = symbol_table.must_find_concrete_class(Identifier("Something"))
        assert len(something.invariants) == 1

        environment = intermediate_type_inference.MutableEnvironment(
            parent=intermediate_type_inference.populate_base_environment(
                symbol_table=symbol_table
            )
        )
        environment.set(
            Identifier("self"),
            intermediate_type_inference.OurTypeAnnotation(our_type=something),
        )

        inference, inference_error = intermediate_type_inference.infer_for_invariant(
            invariant=something.invariants[0], environment=environment
        )

        if inference_error is not None:
            raise AssertionError(
                tests.common.most_underlying_messages([inference_error])
            )

        assert inference is not None
        return {
            ast.unparse(node.original_node): str(type_anno)
            for node, type_anno in inference.type_map.items()
        }

    def expect_error(
        self, condition: str, expected_message: str, property_type: str = "str"
    ) -> None:
        source = Test_string_slicing_and_find.source_with_invariant(
            condition=condition, property_type=property_type
        )
        with self.assertRaises(AssertionError) as context:
            Test_string_slicing_and_find.infer_type_map(source)

        self.assertEqual(expected_message, str(context.exception))

    def test_slice_and_find(self) -> None:
        type_map = Test_string_slicing_and_find.infer_type_map(
            Test_string_slicing_and_find.source_with_invariant(
                'self.text[self.text.find("-", 1) + 1 : len(self.text)] != "x"'
            )
        )

        self.assertEqual("find", type_map["self.text.find"])
        self.assertEqual("int", type_map["self.text.find('-', 1)"])
        self.assertEqual(
            "str", type_map["self.text[self.text.find('-', 1) + 1:len(self.text)]"]
        )

    def test_negative_literal_positions(self) -> None:
        type_map = Test_string_slicing_and_find.infer_type_map(
            Test_string_slicing_and_find.source_with_invariant(
                'self.text[-3:-1] != "x" and self.text.find("x", -2) == -1'
            )
        )

        self.assertEqual("str", type_map["self.text[-3:-1]"])
        self.assertEqual("int", type_map["self.text.find('x', -2)"])

    def test_slice_of_a_constrained_primitive_is_a_plain_string(self) -> None:
        source = """\
@invariant(lambda self: len(self) > 0, "Dummy constraint")
class Non_empty_string(str, DBC):
    pass


@invariant(
    lambda self: self.text[:1].find("x") == -1,
    "Dummy invariant description"
)
class Something(DBC):
    text: Non_empty_string

    def __init__(self, text: Non_empty_string) -> None:
        self.text = text


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        type_map = Test_string_slicing_and_find.infer_type_map(source)

        self.assertEqual("Non_empty_string", type_map["self.text"])
        self.assertEqual("str", type_map["self.text[:1]"])
        self.assertEqual("int", type_map["self.text[:1].find('x')"])

    def test_slice_of_a_list_fails(self) -> None:
        self.expect_error(
            "len(self.text[0:1]) == 1",
            "We do not support slicing a list. If you want to copy the list, "
            "please use ``list(self.text)``, which mypy accepts for a read-only "
            "``Sequence`` as well.",
            property_type="List[str]",
        )

    def test_slice_of_a_tuple_fails(self) -> None:
        self.expect_error(
            "len(self.text[0:1]) == 1",
            "We support slicing only of non-None strings, but got: Tuple[int, int]",
            property_type="Tuple[int, int]",
        )

    def test_slice_of_an_optional_string_fails(self) -> None:
        source = """\
@invariant(
    lambda self: self.text[0:1] == "a",
    "Dummy invariant description"
)
class Something(DBC):
    text: Optional[str]

    def __init__(self, text: Optional[str] = None) -> None:
        self.text = text


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        with self.assertRaises(AssertionError) as context:
            Test_string_slicing_and_find.infer_type_map(source)

        self.assertEqual(
            "We support slicing only of non-None strings, but got: Optional[str]",
            str(context.exception),
        )

    def test_slice_with_a_string_end_fails(self) -> None:
        self.expect_error(
            'self.text[:"1"] == "a"',
            "Expected the end of a slice to be an integer, but got: str",
        )

    def test_find_with_a_non_string_argument_fails(self) -> None:
        self.expect_error(
            "self.text.find(1) == 0",
            "Expected the searched value of ``find`` to be a string, but got: int",
        )

    def test_find_with_no_arguments_fails(self) -> None:
        self.expect_error(
            "self.text.find() == 0",
            "Expected between 1 and 2 argument(s) to the built-in method 'find', "
            "but got 0",
        )

    def test_find_with_too_many_arguments_fails(self) -> None:
        self.expect_error(
            'self.text.find("a", 0, 1) == 0',
            "Expected between 1 and 2 argument(s) to the built-in method 'find', "
            "but got 3",
        )

    def test_find_with_a_string_start_fails(self) -> None:
        self.expect_error(
            'self.text.find("a", "0") == 0',
            "Expected the start of ``find`` to be an integer, but got: str",
        )

    def test_unsupported_string_method_fails(self) -> None:
        self.expect_error(
            'self.text.upper() == "A"',
            "The member 'upper' is not supported on strings; we support only "
            "the following methods: 'endswith', 'find', 'lstrip', 'rstrip', "
            "'startswith'",
        )

    def test_lstrip_and_int(self) -> None:
        type_map = Test_string_slicing_and_find.infer_type_map(
            Test_string_slicing_and_find.source_with_invariant(
                'int(self.text.lstrip("+-").lstrip("0")) > 0'
            )
        )

        self.assertEqual("lstrip", type_map["self.text.lstrip"])
        self.assertEqual("str", type_map["self.text.lstrip('+-').lstrip('0')"])
        self.assertEqual("int", type_map["int(self.text.lstrip('+-').lstrip('0'))"])

    def test_rstrip(self) -> None:
        type_map = Test_string_slicing_and_find.infer_type_map(
            Test_string_slicing_and_find.source_with_invariant(
                'self.text.lstrip("0").rstrip("0") != ""'
            )
        )

        self.assertEqual("rstrip", type_map["self.text.lstrip('0').rstrip"])
        self.assertEqual("str", type_map["self.text.lstrip('0').rstrip('0')"])

    def test_int_of_a_constrained_primitive(self) -> None:
        source = """\
@invariant(lambda self: len(self) > 0, "Dummy constraint")
class Non_empty_string(str, DBC):
    pass


@invariant(
    lambda self: int(self.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    text: Non_empty_string

    def __init__(self, text: Non_empty_string) -> None:
        self.text = text


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        type_map = Test_string_slicing_and_find.infer_type_map(source)

        self.assertEqual("int", type_map["int(self.text)"])

    def test_lstrip_with_a_non_string_argument_fails(self) -> None:
        self.expect_error(
            'self.text.lstrip(1) == ""',
            "Expected the stripped characters of ``lstrip`` to be a string, "
            "but got: int",
        )

    def test_lstrip_with_no_arguments_fails(self) -> None:
        self.expect_error(
            'self.text.lstrip() == ""',
            "Expected 1 argument(s) to the built-in method 'lstrip', but got 0",
        )

    def test_rstrip_with_a_non_string_argument_fails(self) -> None:
        self.expect_error(
            'self.text.rstrip(1) == ""',
            "Expected the stripped characters of ``rstrip`` to be a string, "
            "but got: int",
        )

    def test_rstrip_with_no_arguments_fails(self) -> None:
        self.expect_error(
            'self.text.rstrip() == ""',
            "Expected 1 argument(s) to the built-in method 'rstrip', but got 0",
        )

    def test_startswith_and_endswith(self) -> None:
        type_map = Test_string_slicing_and_find.infer_type_map(
            Test_string_slicing_and_find.source_with_invariant(
                'self.text.startswith("a") and self.text.endswith("z")'
            )
        )

        self.assertEqual("startswith", type_map["self.text.startswith"])
        self.assertEqual("bool", type_map["self.text.startswith('a')"])
        self.assertEqual("endswith", type_map["self.text.endswith"])
        self.assertEqual("bool", type_map["self.text.endswith('z')"])

    def test_startswith_with_a_non_string_argument_fails(self) -> None:
        self.expect_error(
            "self.text.startswith(1)",
            "Expected the prefix of ``startswith`` to be a string, but got: int",
        )

    def test_startswith_with_a_tuple_fails(self) -> None:
        self.expect_error(
            'self.text.startswith(("a", "b"))',
            "Expected the prefix of ``startswith`` to be a string, "
            "but got: Tuple[str, str]",
        )

    def test_startswith_with_a_start_fails(self) -> None:
        self.expect_error(
            'self.text.startswith("a", 1)',
            "Expected 1 argument(s) to the built-in method 'startswith', but got 2",
        )

    def test_endswith_with_a_non_string_argument_fails(self) -> None:
        self.expect_error(
            "self.text.endswith(1)",
            "Expected the suffix of ``endswith`` to be a string, but got: int",
        )

    def test_endswith_with_no_arguments_fails(self) -> None:
        self.expect_error(
            "self.text.endswith()",
            "Expected 1 argument(s) to the built-in method 'endswith', but got 0",
        )

    def test_concatenation(self) -> None:
        type_map = Test_string_slicing_and_find.infer_type_map(
            Test_string_slicing_and_find.source_with_invariant(
                'len(self.text + "a" + ("b" + "c")) > 0'
            )
        )

        self.assertEqual("str", type_map["self.text + 'a'"])
        self.assertEqual("str", type_map["'b' + 'c'"])
        self.assertEqual("str", type_map["self.text + 'a' + ('b' + 'c')"])

    def test_concatenation_of_a_constrained_primitive(self) -> None:
        source = """\
@invariant(lambda self: len(self) > 0, "Dummy constraint")
class Non_empty_string(str, DBC):
    pass


@invariant(
    lambda self: len(self.text + "a") > 0,
    "Dummy invariant description"
)
class Something(DBC):
    text: Non_empty_string

    def __init__(self, text: Non_empty_string) -> None:
        self.text = text


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        type_map = Test_string_slicing_and_find.infer_type_map(source)

        self.assertEqual("str", type_map["self.text + 'a'"])

    def test_concatenation_with_an_integer_fails(self) -> None:
        self.expect_error(
            "len(self.text + 1) > 0",
            "The concatenation is only defined on two strings, "
            "but got as a right operand: int",
        )

    def test_concatenation_with_an_integer_on_the_left_fails(self) -> None:
        self.expect_error(
            "len(1 + self.text) > 0",
            "The concatenation is only defined on two strings, "
            "but got as a left operand: int",
        )

    def test_subtraction_of_strings_fails(self) -> None:
        self.expect_error(
            "self.text - 1 > 0",
            "The subtraction is only defined on integer and floating-point numbers, "
            "but got as a left operand: str",
        )

    def test_int_of_a_float_fails(self) -> None:
        self.expect_error(
            "int(self.text) > 0",
            "Expected the argument of ``int`` to be a non-None string, since we "
            "support only parsing the integers from the strings, but got: float",
            property_type="float",
        )

    def test_int_of_an_optional_string_fails(self) -> None:
        source = """\
@invariant(
    lambda self: int(self.text) > 0,
    "Dummy invariant description"
)
class Something(DBC):
    text: Optional[str]

    def __init__(self, text: Optional[str] = None) -> None:
        self.text = text


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        with self.assertRaises(AssertionError) as context:
            Test_string_slicing_and_find.infer_type_map(source)

        self.assertEqual(
            "Expected the argument of ``int`` to be a non-None string, since we "
            "support only parsing the integers from the strings, "
            "but got: Optional[str]",
            str(context.exception),
        )


_ANNOTATED_ASSIGNMENT_PRELUDE: Final[
    str
] = """\
@abstract
class Parent(DBC):
    def __init__(self) -> None:
        pass


class Child_a(Parent):
    a_only: int

    def __init__(self, a_only: int) -> None:
        self.a_only = a_only


class Item(DBC):
    name: str

    def __init__(self, name: str) -> None:
        self.name = name


Some_union = Union[Child_a, Item]

"""

_ANNOTATED_ASSIGNMENT_EPILOGUE: Final[
    str
] = """
__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""


class Test_annotated_assignment(unittest.TestCase):
    def expect_type_inference_to_fail(self, body: str, expected_message: str) -> None:
        """Expect the type inference of the verification functions to fail."""
        source = _ANNOTATED_ASSIGNMENT_PRELUDE + body + _ANNOTATED_ASSIGNMENT_EPILOGUE

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        base_environment = intermediate_type_inference.populate_base_environment(
            symbol_table=symbol_table
        )

        messages: List[str] = []
        for verification in symbol_table.verification_functions:
            assert isinstance(verification, intermediate.TranspilableVerification)

            # fmt: off
            _, inference_error = (
                intermediate_type_inference.infer_for_verification(
                    verification=verification,
                    base_environment=base_environment
                )
            )
            # fmt: on

            if inference_error is not None:
                messages.append(
                    tests.common.most_underlying_messages([inference_error])
                )

        self.assertEqual(expected_message, "\n".join(messages), source)

    def test_mismatched_declared_type_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    x: int = text
    return x > 0
""",
            expected_message=(
                "We inferred the target type of the assignment to be int, while the "
                "value type is inferred to be str. We do not know how to model this "
                "assignment."
            ),
        )

    def test_reannotated_variable_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x: int = number
    x: int = 0
    return x > 0
""",
            expected_message=(
                "The variable 'x' has been already defined before with the type "
                "int, so it can not be declared again with a type annotation. "
                "Please assign to it without the annotation, or use a different "
                "name."
            ),
        )

    def test_unknown_type_in_annotation_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x: Unknown_type = number
    return True
""",
            expected_message=(
                "The type 'Unknown_type' in the type annotation is not defined."
            ),
        )

    def test_unsupported_generic_in_annotation_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Sequence[str]) -> bool:
    x: Mapping[str, str] = texts
    return True
""",
            expected_message=(
                "We support only ``Optional[...]``, ``List[...]``, "
                "``Sequence[...]``, ``Set[...]`` and ``Tuple[...]`` as generic "
                "types in the type annotations of the variables, but got: "
                "Mapping[...]"
            ),
        )

    def test_nested_optional_in_annotation_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x: Optional[Optional[int]] = None
    return True
""",
            expected_message=(
                "We do not support nested optionals, but got: "
                "Optional[Optional[int]]"
            ),
        )

    def test_inline_union_in_annotation_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(item: Item) -> bool:
    x: Union[Child_a, Item] = item
    return True
""",
            expected_message=(
                "We do not support inline unions such as ``Union[A, B]`` in the "
                "type annotations of the variables. The targets need a named type "
                "to represent a union, such as a variant in C++ or a wrapper class "
                "in C#, so only the named unions of the meta-model are accepted. "
                "Please define a named union at the module level, *e.g.*, "
                "``Some_union = Union[A, B]``, and annotate the variable with it, "
                "*e.g.*, ``x: Some_union = ...``. For an optional value, please use "
                "``Optional[...]``."
            ),
        )

    def test_new_variable_from_none_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x = None
    return True
""",
            expected_message=(
                "We can not infer the type of the variable 'x' from ``None``. "
                "Please declare the variable with a type annotation, *e.g.*, ``x: "
                "Optional[...] = None``."
            ),
        )

    def test_member_access_after_reset_to_none_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(child: Child_a) -> bool:
    x: Optional[Child_a] = child
    x = None
    return x.a_only > 0
""",
            expected_message=(
                "Expected an instance type to be a non-None, either an "
                "enumeration-as-type or our type, but inferred an Optional: "
                "Optional[Child_a]"
            ),
        )

    def test_none_for_non_optional_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def is_short(text: str) -> bool:
    return len(text) < 10


@verification
def some_func(number: int) -> bool:
    return is_short(None)
""",
            expected_message=(
                "The argument 'text' of the verification function 'is_short' is not "
                "optional, but got None."
            ),
        )

    def test_none_returned_from_non_optional_function_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    if number > 0:
        return None

    return True
""",
            expected_message=(
                "The function returns a non-optional bool, but got a ``return "
                "None``."
            ),
        )

    def test_none_in_comparison_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: Optional[str]) -> bool:
    return text == None
""",
            expected_message=(
                "We can transpile ``None`` only as the value of an assignment, as "
                "an argument of a call or as the returned value, since the targets "
                "need to know the type of the optional which is ``None``. To check "
                "whether a value is ``None``, please use ``is None`` or ``is not "
                "None``.\n"
                "Expected the left operand to be a non-None, but got: Optional[str]"
            ),
        )

    def test_none_in_tuple_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x = (None, number)
    return True
""",
            expected_message=(
                "We can transpile ``None`` only as the value of an assignment, as "
                "an argument of a call or as the returned value, since the targets "
                "need to know the type of the optional which is ``None``. To check "
                "whether a value is ``None``, please use ``is None`` or ``is not "
                "None``."
            ),
        )

    def test_class_not_in_named_union_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
class Other(DBC):
    def __init__(self) -> None:
        pass


@verification
def some_func(other: Other) -> bool:
    x: Some_union = other
    return True
""",
            expected_message=(
                "We inferred the target type of the assignment to be Some_union, "
                "while the value type is inferred to be Other. We do not know how "
                "to model this assignment."
            ),
        )

    def test_named_union_assigned_to_class_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(union_value: Some_union) -> bool:
    x: Child_a = union_value
    return True
""",
            expected_message=(
                "We inferred the target type of the assignment to be Child_a, while "
                "the value type is inferred to be Some_union. We do not know how to "
                "model this assignment."
            ),
        )

    def test_optional_class_assigned_to_named_union_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(child: Optional[Child_a]) -> bool:
    x: Some_union = child
    return True
""",
            expected_message=(
                "The value assigned to the named union 'Some_union' might be None, "
                "since it is inferred to be Optional[Child_a]. We need to wrap the "
                "instance into the named union in some targets, which we can not do "
                "for a None. Please check first that the value is not None, *e.g.*, "
                "with ``if child is not None:``."
            ),
        )

    def test_parent_assigned_to_optional_child_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(parent: Parent) -> bool:
    x: Optional[Child_a] = parent
    return True
""",
            expected_message=(
                "We inferred the target type of the assignment to be "
                "Optional[Child_a], while the value type is inferred to be Parent. "
                "We do not know how to model this assignment."
            ),
        )

    def test_reassigned_final_variable_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x: Final[int] = number
    x = 0
    return x > 0
""",
            expected_message=(
                "The variable 'x' is declared as ``Final[...]``, so it can not be "
                "re-assigned."
            ),
        )

    def test_list_in_final_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(numbers: Sequence[int]) -> bool:
    x: Final[List[int]] = numbers
    return True
""",
            expected_message=(
                "A variable declared as ``Final[...]`` is immutable, but ``List[...]`` is"
                " mutable. Please declare it as ``Sequence[...]`` instead."
            ),
        )

    def test_set_in_final_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x: Final[Set[int]] = set()
    return True
""",
            expected_message=(
                "A variable declared as ``Final[...]`` is immutable, but ``Set[...]`` is "
                "mutable. Please declare it as ``AbstractSet[...]`` instead."
            ),
        )

    def test_nested_list_in_final_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(numbers: Sequence[int]) -> bool:
    x: Final[Optional[Tuple[List[int], int]]] = None
    return True
""",
            expected_message=(
                "A variable declared as ``Final[...]`` is immutable, but ``List[...]`` is"
                " mutable. Please declare it as ``Sequence[...]`` instead."
            ),
        )

    def test_bare_final_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x: Final = number
    return True
""",
            expected_message=(
                "Please specify the type of the variable 'x' as a subscript of "
                "``Final[...]``, *e.g.*, ``x: Final[int] = ...``, since the targets need "
                "to declare it with the type."
            ),
        )

    def test_nested_final_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x: Optional[Final[int]] = number
    return True
""",
            expected_message=(
                "We support ``Final[...]`` only as the outermost type annotation of a "
                "variable, *e.g.*, ``x: Final[Optional[int]] = ...``."
            ),
        )

    def test_final_in_loop_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(numbers: Sequence[int]) -> bool:
    for number in numbers:
        x: Final[int] = number
    return True
""",
            expected_message=(
                "The variable 'x' can not be declared as ``Final[...]`` in the body of a "
                "for-loop, as mypy refuses it. Please declare it without ``Final[...]``, "
                "or move it out of the loop."
            ),
        )

    def test_assignment_to_property_of_final_variable_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(child: Mutable[Child_a]) -> bool:
    x: Final[Child_a] = child
    x.a_only = 1
    return True
""",
            expected_message=(
                "We can not assign to the property 'a_only' of x, since the variable 'x' "
                "is declared as ``Final[...]``."
            ),
        )

    def test_assignment_to_item_of_final_variable_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(numbers: List[int]) -> bool:
    x: Final[Sequence[int]] = numbers
    x[0] = 1
    return True
""",
            expected_message=(
                "We can not assign to an item of the list of x, since the variable 'x' is"
                " declared as ``Final[...]``."
            ),
        )

    def test_add_to_final_set_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    x: Final[AbstractSet[int]] = set()
    x.add(1)
    return True
""",
            expected_message=(
                "The ``add`` mutates the set, but the variable 'x' is declared as "
                "``Final[...]``."
            ),
        )

    def test_final_variable_passed_as_mutable_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def mutate(numbers: List[int]) -> bool:
    numbers[0] = 1
    return True


@verification
def some_func(numbers: List[int]) -> bool:
    x: Final[Sequence[int]] = numbers
    return mutate(x)
""",
            expected_message=(
                "The argument 'numbers' of the verification function 'mutate' is mutable,"
                " but the variable 'x' is declared as ``Final[...]``."
            ),
        )


_COLLECTION_INVARIANCE_EXPLANATION: Final[str] = (
    "The lists and the sets are invariant, so their items need to be of exactly "
    "the same type. A mutable List[...] can not hold the instances of a subclass, "
    "since the callee could insert an instance of another subclass into it. Only "
    "a read-only Sequence[...] argument of a verification function accepts "
    "the instances of a subclass, since the targets with invariant lists declare "
    "it generic: Go with a type parameter, C++ with a template, C# with "
    "IReadOnlyList<T> and Java with List<? extends T>. The methods can not accept "
    "them, since Go methods can not have type parameters, and C++ virtual methods "
    "can not be templates. We do not copy the list implicitly either, as that "
    "would cost linear time and memory on each call. Please declare the argument "
    "with the exact type of the items."
)


def _generic_sequence_explanation(name: str) -> str:
    return (
        f"The argument {name!r} is a read-only Sequence[...] of a class with "
        f"descendants, so the targets declare it generic to accept the sequences "
        f"of the descendants without a copy: Go with a type parameter, C++ with "
        f"a template, C# with IReadOnlyList<T>, and Java with List<? extends T>. "
        f"Hence, we support it only as the collection of a for-loop or of "
        f"all/any, the collection of an index, the container of in, the argument "
        f"of len, the value of a nullness check, an argument of a verification "
        f"function, and the value of an immutable alias of the very same type, "
        f"*e.g.*, ``alias: Final[Sequence[...]] = {name}``. Elsewhere, *e.g.*, "
        f"passed to a method, assigned to a mutable variable or copied with list, "
        f"the targets would expect the non-generic list."
    )


_SET_PRELUDE: Final[
    str
] = """\
class Item(DBC):
    name: str

    def __init__(self, name: str) -> None:
        self.name = name


Reserved_texts: Final[AbstractSet[str]] = constant_set(values=["reserved"])


@verification
def is_in(text: str, texts: AbstractSet[str]) -> bool:
    return text in texts


@verification
def collect(text: str, texts: Set[str]) -> bool:
    texts.add(text)
    return True


"""


class Test_invariant_list_arguments(unittest.TestCase):
    @staticmethod
    def source_with_verification(verification: str) -> str:
        return f"""\
class Abstract_item(DBC):
    @implementation_specific
    @non_mutating
    def count(self, items: Sequence["Abstract_item"]) -> int:
        pass


class Some_item(Abstract_item):
    def __init__(self) -> None:
        pass


@verification
def check(items: Sequence[Abstract_item]) -> bool:
    return len(items) > 0


@verification
def fill(items: List[Abstract_item]) -> bool:
    return len(items) > 0


@verification
@implementation_specific
def check_specifically(items: Sequence[Abstract_item]) -> bool:
    pass


@verification
@implementation_specific
def check_optional_specifically(items: Optional[Sequence[Abstract_item]]) -> bool:
    pass


@verification
@implementation_specific
def fill_specifically(items: List[Abstract_item]) -> bool:
    pass


{verification}


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

    def test_sequence_of_same_items(self) -> None:
        Test_with_smoke.execute(
            Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: List[Abstract_item]) -> bool:
    return check(items) and fill(items) and check_specifically(items)"""
            )
        )

    def test_sequence_of_descendants_to_implementation_specific(self) -> None:
        Test_with_smoke.execute(
            Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(
    items: Sequence[Some_item], optional_items: Optional[Sequence[Some_item]]
) -> bool:
    return (
        check_specifically(items)
        and check_optional_specifically(items)
        and check_optional_specifically(optional_items)
    )"""
            )
        )

    def test_sequence_of_descendants_to_transpiled_verification(self) -> None:
        Test_with_smoke.execute(
            Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: Sequence[Some_item]) -> bool:
    return check(items)"""
            )
        )

    def test_supported_usages_of_generic_sequence(self) -> None:
        Test_with_smoke.execute(
            Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(
    items: Sequence[Abstract_item], optional_items: Optional[Sequence[Abstract_item]]
) -> bool:
    for item in items:
        if not isinstance(item, Some_item):
            return False

    if optional_items is not None:
        if len(optional_items) > 0:
            return check(optional_items)

    return (
        len(items) > 0
        and isinstance(items[0], Some_item)
        and all(isinstance(item, Some_item) for item in items)
        and check(items)
        and check_specifically(items)
        and check_optional_specifically(optional_items)
    )"""
            )
        )

    def test_generic_sequence_to_method_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(item: Some_item, items: Sequence[Abstract_item]) -> bool:
    return item.count(items) > 0"""
            ),
            expected_joined_message=_generic_sequence_explanation("items"),
        )

    def test_generic_sequence_assigned_to_variable_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: Sequence[Abstract_item]) -> bool:
    alias: Sequence[Abstract_item] = items
    return len(alias) > 0"""
            ),
            expected_joined_message=_generic_sequence_explanation("items"),
        )

    def test_immutable_alias_of_generic_sequence(self) -> None:
        Test_with_smoke.execute(
            Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(
    items: Sequence[Abstract_item], optional_items: Optional[Sequence[Abstract_item]]
) -> bool:
    alias: Final[Sequence[Abstract_item]] = items
    alias_of_alias: Final[Sequence[Abstract_item]] = alias
    optional_alias: Final[Optional[Sequence[Abstract_item]]] = optional_items
    return (
        all(isinstance(item, Some_item) for item in alias_of_alias)
        and check(alias)
        and (optional_alias is None or check(optional_alias))
    )"""
            )
        )

    def test_immutable_alias_of_another_type_fails(self) -> None:
        # NOTE (mristin):
        # The optional alias does not share the type annotation of the required
        # generic sequence, so the targets would need to convert it.
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: Sequence[Abstract_item]) -> bool:
    alias: Final[Optional[Sequence[Abstract_item]]] = items
    return alias is not None"""
            ),
            expected_joined_message=_generic_sequence_explanation("items"),
        )

    def test_copy_of_immutable_alias_of_generic_sequence_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: Sequence[Abstract_item]) -> bool:
    alias: Final[Sequence[Abstract_item]] = items
    copy = list(alias)
    return len(copy) > 0"""
            ),
            expected_joined_message=_generic_sequence_explanation("alias"),
        )

    def test_generic_sequence_copied_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: Sequence[Abstract_item]) -> bool:
    copy = list(items)
    return len(copy) > 0"""
            ),
            expected_joined_message=_generic_sequence_explanation("items"),
        )

    def test_generic_sequence_as_container_of_in(self) -> None:
        Test_with_smoke.execute(
            Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(item: Some_item, items: Sequence[Abstract_item]) -> bool:
    return item in items"""
            )
        )

    def test_sequence_without_descendants_is_not_generic(self) -> None:
        Test_with_smoke.execute(
            Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(item: Some_item, items: Sequence[Some_item]) -> bool:
    copy = list(items)
    return len(copy) > 0"""
            )
        )

    def test_mutable_list_of_descendants_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: List[Some_item]) -> bool:
    return fill(items)"""
            ),
            expected_joined_message=(
                "The argument 'items' of the verification function 'fill' is "
                "of type List[Abstract_item], but got: List[Some_item]. "
                + _COLLECTION_INVARIANCE_EXPLANATION
            ),
        )

    def test_mutable_list_of_descendants_to_implementation_specific_fails(
        self,
    ) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: List[Some_item]) -> bool:
    return fill_specifically(items)"""
            ),
            expected_joined_message=(
                "The argument 'items' of the verification function "
                "'fill_specifically' is of type List[Abstract_item], but got: "
                "List[Some_item]. " + _COLLECTION_INVARIANCE_EXPLANATION
            ),
        )

    def test_optional_sequence_of_descendants_to_non_optional_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(items: Optional[Sequence[Some_item]]) -> bool:
    return check_specifically(items)"""
            ),
            expected_joined_message=(
                "The argument 'items' of the verification function "
                "'check_specifically' is of type List[Abstract_item], but got: "
                "Optional[List[Some_item]]. " + _COLLECTION_INVARIANCE_EXPLANATION
            ),
        )

    def test_sequence_of_descendants_to_method_fails(self) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_invariant_list_arguments.source_with_verification(
                """\
@verification
def some_func(item: Some_item, items: Sequence[Some_item]) -> bool:
    return item.count(items) > 0"""
            ),
            expected_joined_message=(
                "The argument 'items' of the method 'count' is of type "
                "List[Abstract_item], but got: List[Some_item]. "
                + _COLLECTION_INVARIANCE_EXPLANATION
            ),
        )


class Test_set(unittest.TestCase):
    def expect_type_inference_to_fail(self, body: str, expected_message: str) -> None:
        """Expect the type inference of the verification functions to fail."""
        source = _SET_PRELUDE + body + _ANNOTATED_ASSIGNMENT_EPILOGUE

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        base_environment = intermediate_type_inference.populate_base_environment(
            symbol_table=symbol_table
        )

        messages: List[str] = []
        for verification in symbol_table.verification_functions:
            assert isinstance(verification, intermediate.TranspilableVerification)

            # fmt: off
            _, inference_error = (
                intermediate_type_inference.infer_for_verification(
                    verification=verification,
                    base_environment=base_environment
                )
            )
            # fmt: on

            if inference_error is not None:
                messages.append(
                    tests.common.most_underlying_messages([inference_error])
                )

        self.assertEqual(expected_message, "\n".join(messages), source)

    def test_set_without_annotation_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Sequence[str]) -> bool:
    seen = set()
    return True
""",
            expected_message=(
                "We support ``set()`` only as the value assigned to a variable "
                "declared as a set, *e.g.*, ``x: Set[str] = set()``, since the "
                "targets need to know the type of the items of the new set."
            ),
        )

    def test_set_with_arguments_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Sequence[str]) -> bool:
    seen: Set[str] = set(texts)
    return True
""",
            expected_message=(
                "We support only ``set()`` without arguments to create a new set, "
                "but got 1 argument(s). Please add the items one by one with "
                "``add``."
            ),
        )

    def test_set_assigned_to_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Sequence[str]) -> bool:
    seen: List[str] = set()
    return True
""",
            expected_message=(
                "We support ``set()`` only as the value assigned to a variable "
                "declared as a set, *e.g.*, ``x: Set[str] = set()``, since the "
                "targets need to know the type of the items of the new set, but the "
                "target is of type List[str]."
            ),
        )

    def test_set_as_argument_of_call_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    return is_in(text, set())
""",
            expected_message=(
                "We support ``set()`` only as the value assigned to a variable "
                "declared as a set, *e.g.*, ``x: Set[str] = set()``, since the "
                "targets need to know the type of the items of the new set."
            ),
        )

    def test_set_of_floats_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(numbers: Sequence[float]) -> bool:
    seen: Set[float] = set()
    return True
""",
            expected_message=(
                "We do not support the sets of floating-point numbers, but got the "
                "items of type float. The targets disagree on the equality of "
                "floating-point numbers in a set: Python finds a NaN only if it is "
                "the very same object, C++ and Go never find a NaN, while C#, Java "
                "and TypeScript always do. Moreover, Java tells 0.0 and -0.0 apart, "
                "while the other targets do not."
            ),
        )

    def test_set_of_byte_arrays_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(data: bytearray) -> bool:
    seen: Set[bytearray] = set()
    return True
""",
            expected_message=(
                "We do not support the sets of byte arrays, but got the items of "
                "type bytearray. A bytearray is mutable and hence unhashable in "
                "Python, so ``set().add(bytearray(...))`` raises a ``TypeError``."
            ),
        )

    def test_set_of_instances_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(item: Item) -> bool:
    seen: Set[Item] = set()
    return True
""",
            expected_message=(
                "We support only the sets of primitive values and enumeration "
                "literals, but got the items of type Item, which is a class. Please "
                "contact the developers if you need the sets of instances."
            ),
        )

    def test_set_of_optionals_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    seen: Set[Optional[str]] = set()
    return True
""",
            expected_message=(
                "We do not support None as an item of a set, but got the items of "
                "type Optional[str]. Some targets can not hold a null item in a "
                "set, *e.g.*, a string key of a map in Go can not be nil. If the "
                "whole set is optional, please declare it as ``Optional[Set[...]]``."
            ),
        )

    def test_set_of_lists_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    seen: Set[List[str]] = set()
    return True
""",
            expected_message=(
                "We do not support the sets of lists or sets, but got the items of "
                "type List[str]. The lists and the sets are mutable and hence "
                "unhashable in Python, so they can not be items of a set."
            ),
        )

    def test_abstract_set_declared_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    seen: AbstractSet[str] = Reserved_texts
    return True
""",
            expected_message=(
                "We do not support declaring a variable as an ``AbstractSet[...]``, "
                "since it would share a set with another variable, and the targets "
                "disagree on that: C++ copies the set, while the other targets "
                "share it. Please declare a new set as ``Set[...]`` and initialize "
                "it with ``set()``."
            ),
        )

    def test_add_to_constant_set_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    Reserved_texts.add(text)
    return True
""",
            expected_message=(
                "The ``add`` mutates the set, but the constant set 'Reserved_texts' "
                "is immutable."
            ),
        )

    def test_add_to_read_only_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str, texts: AbstractSet[str]) -> bool:
    texts.add(text)
    return True
""",
            expected_message=(
                "The ``add`` mutates the set, but the argument 'texts' is declared "
                "as an AbstractSet, which is read-only. Please declare it as a Set "
                "if the function mutates it."
            ),
        )

    def test_add_of_wrong_type_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    seen: Set[str] = set()
    seen.add(number)
    return True
""",
            expected_message=(
                "Expected the item added to Set[str] to be assignable to str, but "
                "got: int"
            ),
        )

    def test_add_as_expression_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    seen: Set[str] = set()
    result = seen.add(text)
    return True
""",
            expected_message=(
                "The ``add`` of a set returns nothing, so it can only be called as "
                "a statement on its own.\n"
                "We can not infer the type of the variable 'result' from ``None``. "
                "Please declare the variable with a type annotation, *e.g.*, "
                "``result: Optional[...] = None``."
            ),
        )

    def test_unknown_method_on_set_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    seen: Set[str] = set()
    seen.discard(text)
    return True
""",
            expected_message=(
                "The member 'discard' is not supported on sets; we support only the "
                "following methods: 'add', 'difference', 'intersection'"
            ),
        )

    def test_is_in_of_wrong_type_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    return number in Reserved_texts
""",
            expected_message=(
                "Expected the member to be of the type of the items of the set "
                "Set[str], but got: int"
            ),
        )

    def test_aliasing_of_set_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    seen: Set[str] = set()
    other = seen
    return True
""",
            expected_message=(
                "We support a set only as the container of ``in``, the collection "
                "or the variable of a for-loop, the receiver of its methods, "
                "an argument of a call, "
                "the target of an assignment, the value of a nullness check, "
                "the returned value, and a new set or the result of a call as "
                "the assigned value. Elsewhere, the targets would need "
                "to either copy or share the set, and they disagree on that: C++ "
                "copies it, while the other targets share it."
            ),
        )

    def test_constant_set_to_mutable_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    return collect(text, Reserved_texts)
""",
            expected_message=(
                "The argument 'texts' of the verification function 'collect' is "
                "mutable, but the constant set 'Reserved_texts' is immutable."
            ),
        )

    def test_set_of_other_items_as_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    seen: Set[int] = set()
    return is_in("x", seen)
""",
            expected_message=(
                "The argument 'texts' of the verification function 'is_in' is of "
                "type Set[str], but got: Set[int]. "
                + _COLLECTION_INVARIANCE_EXPLANATION
            ),
        )

    def test_list_as_set_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Sequence[str]) -> bool:
    return is_in("x", texts)
""",
            expected_message=(
                "The argument 'texts' of the verification function 'is_in' is of "
                "type Set[str], but got: List[str]. "
                + _COLLECTION_INVARIANCE_EXPLANATION
            ),
        )

    def test_add_in_loop_over_set_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Set[str]) -> bool:
    for text in texts:
        texts.add(text)
    return True
""",
            expected_message=(
                "The set texts can not be mutated in the for-loop over it, since "
                "the targets disagree on that: Python and Java throw an exception, "
                "the behavior is undefined in C++, while Go and TypeScript carry on."
            ),
        )

    def test_mutable_argument_in_loop_over_set_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Set[str]) -> bool:
    for text in texts:
        collect(text, texts)
    return True
""",
            expected_message=(
                "The set texts can not be mutated in the for-loop over it, since "
                "the targets disagree on that: Python and Java throw an exception, "
                "the behavior is undefined in C++, while Go and TypeScript carry on."
            ),
        )

    def test_intersection_with_other_items_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: AbstractSet[str], numbers: AbstractSet[int]) -> bool:
    return len(texts.intersection(numbers)) > 0
""",
            expected_message=(
                "Expected the argument of ``intersection`` to be a set of the same "
                "items, Set[str], but got: Set[int]"
            ),
        )

    def test_difference_with_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: AbstractSet[str], others: Sequence[str]) -> bool:
    return len(texts.difference(others)) > 0
""",
            expected_message=(
                "Expected the argument of ``difference`` to be a set of the same "
                "items, Set[str], but got: List[str]"
            ),
        )

    def test_intersection_assigned_to_other_items_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: AbstractSet[str]) -> bool:
    numbers: Set[int] = texts.intersection(texts)
    return True
""",
            expected_message=(
                "We inferred the target type of the assignment to be Set[int], "
                "while the value type is inferred to be Set[str]. We do not know "
                "how to model this assignment."
            ),
        )

    def test_returned_set_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Set[str]) -> Set[str]:
    return texts
""",
            expected_message=(
                "The returned value texts holds lists or sets, which Python "
                "would share with the caller, but C++ would copy. We can not "
                "transpile the sharing to C++, so please return fresh values: "
                "a list copied with ``list(...)`` whose items hold no lists and "
                "no sets, a local set variable, a new set, the result of a call, "
                "or a tuple literal of them."
            ),
        )

    def test_returned_constant_set_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> Set[str]:
    return Reserved_texts
""",
            expected_message=(
                "The returned value Reserved_texts holds lists or sets, which Python "
                "would share with the caller, but C++ would copy. We can not "
                "transpile the sharing to C++, so please return fresh values: "
                "a list copied with ``list(...)`` whose items hold no lists and "
                "no sets, a local set variable, a new set, the result of a call, "
                "or a tuple literal of them."
            ),
        )

    def test_returned_loop_variable_over_list_of_sets_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(groups: List[Set[str]]) -> Set[str]:
    for group in groups:
        return group

    result: Set[str] = set()
    return result
""",
            expected_message=(
                "The returned value group holds lists or sets, which Python "
                "would share with the caller, but C++ would copy. We can not "
                "transpile the sharing to C++, so please return fresh values: "
                "a list copied with ``list(...)`` whose items hold no lists and "
                "no sets, a local set variable, a new set, the result of a call, "
                "or a tuple literal of them."
            ),
        )

    def test_returned_list_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: List[str]) -> List[str]:
    return texts
""",
            expected_message=(
                "The returned value texts holds lists or sets, which Python "
                "would share with the caller, but C++ would copy. We can not "
                "transpile the sharing to C++, so please return fresh values: "
                "a list copied with ``list(...)`` whose items hold no lists and "
                "no sets, a local set variable, a new set, the result of a call, "
                "or a tuple literal of them."
            ),
        )

    def test_returned_tuple_with_set_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Set[str]) -> Tuple[Set[str], int]:
    return (texts, 1)
""",
            expected_message=(
                "The returned value (texts, 1) holds lists or sets, which Python "
                "would share with the caller, but C++ would copy. We can not "
                "transpile the sharing to C++, so please return fresh values: "
                "a list copied with ``list(...)`` whose items hold no lists and "
                "no sets, a local set variable, a new set, the result of a call, "
                "or a tuple literal of them."
            ),
        )

    def test_returned_value_of_another_type_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: AbstractSet[str]) -> List[str]:
    result: Set[str] = set()
    return result
""",
            expected_message=(
                "Expected the returned value to be assignable to the return type "
                "List[str], but got Set[str]."
            ),
        )

    def test_returned_tuple_with_length_fails(self) -> None:
        # NOTE (mristin):
        # The tuples are invariant, so the length needs to be assigned to
        # an integer variable first.
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> Tuple[str, int]:
    return (text, len(text))
""",
            expected_message=(
                "Expected the returned value to be assignable to the return type "
                "Tuple[str, int], but got Tuple[str, length]."
            ),
        )


class Test_list_literal_and_append(unittest.TestCase):
    def expect_type_inference_to_fail(self, body: str, expected_message: str) -> None:
        """Expect the type inference of the verification functions to fail."""
        source = _ANNOTATED_ASSIGNMENT_PRELUDE + body + _ANNOTATED_ASSIGNMENT_EPILOGUE

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        base_environment = intermediate_type_inference.populate_base_environment(
            symbol_table=symbol_table
        )

        messages: List[str] = []
        for verification in symbol_table.verification_functions:
            assert isinstance(verification, intermediate.TranspilableVerification)

            # fmt: off
            _, inference_error = (
                intermediate_type_inference.infer_for_verification(
                    verification=verification,
                    base_environment=base_environment
                )
            )
            # fmt: on

            if inference_error is not None:
                messages.append(
                    tests.common.most_underlying_messages([inference_error])
                )

        self.assertEqual(expected_message, "\n".join(messages), source)

    def test_append_on_argument_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: List[str], text: str) -> bool:
    texts.append(text)
    return True
""",
            expected_message=(
                "We support ``append`` only on a local list variable, but texts "
                "is an argument. Python appends to the list in place, while Go "
                "appends to a slice with ``items = append(items, item)``, which "
                "gives a new slice whenever the array beneath it has to grow. "
                "Only the appended variable sees the new slice, so that the "
                "caller, the instance or the collection holding the list would "
                "miss the appended item in Go. Please build a local list "
                "instead, *e.g.*, ``items: List[...] = []``, append to it, and "
                "then return it, or assign a copy of it with ``list(items)``."
            ),
        )

    def test_append_on_loop_variable_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(lists: List[List[str]], text: str) -> bool:
    for texts in lists:
        texts.append(text)
    return True
""",
            expected_message=(
                "We support ``append`` only on a local list variable, but texts "
                "is a loop variable. Python appends to the list in place, while "
                "Go appends to a slice with ``items = append(items, item)``, "
                "which gives a new slice whenever the array beneath it has to "
                "grow. Only the appended variable sees the new slice, so that "
                "the caller, the instance or the collection holding the list "
                "would miss the appended item in Go. Please build a local list "
                "instead, *e.g.*, ``items: List[...] = []``, append to it, and "
                "then return it, or assign a copy of it with ``list(items)``."
            ),
        )

    def test_append_on_property_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
class Bag(DBC):
    texts: List[str]

    def __init__(self, texts: List[str]) -> None:
        self.texts = texts


@verification
def some_func(bag: Mutable[Bag], text: str) -> bool:
    bag.texts.append(text)
    return True
""",
            expected_message=(
                "We support ``append`` only on a local list variable, but "
                "bag.texts is not a variable. Python appends to the list in "
                "place, while Go appends to a slice with ``items = "
                "append(items, item)``, which gives a new slice whenever the "
                "array beneath it has to grow. Only the appended variable sees "
                "the new slice, so that the caller, the instance or the "
                "collection holding the list would miss the appended item in "
                "Go. Please build a local list instead, *e.g.*, ``items: "
                "List[...] = []``, append to it, and then return it, or assign "
                "a copy of it with ``list(items)``."
            ),
        )

    def test_alias_of_appended_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    texts: List[str] = []
    other = texts
    texts.append(text)
    return len(other) > 0
""",
            expected_message=(
                "The list 'texts' is appended to, so we support it only as the "
                "receiver of ``append``, the container of ``in``, the "
                "collection of a for-loop, an argument of a call, such as "
                "``len(texts)``, the collection of an index or of a slice, the "
                "returned value, and the target of an assignment of a fresh "
                "list. Here it would be aliased, *e.g.*, as in ``other = "
                "texts``, in a tuple literal or as the value assigned to a "
                "property, and the targets disagree on the aliases of a list "
                "appended to: Python appends to the list in place, so that all "
                "the aliases see the appended items. Go appends to a slice with "
                "``texts = append(texts, item)``, which gives a new slice "
                "whenever the array beneath it has to grow, so that the aliases "
                "miss the items appended afterwards. C++ copies the list on an "
                "assignment, so that the copy never sees the items appended "
                "afterwards. Please copy the list explicitly with "
                "``list(texts)`` instead."
            ),
        )

    def test_assignment_of_non_fresh_list_to_appended_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: List[str], text: str) -> bool:
    result: List[str] = []
    result = texts
    result.append(text)
    return True
""",
            expected_message=(
                "The list 'result' is appended to, so it can be assigned only a "
                "fresh list, *i.e.*, a list literal, a list copied with "
                "``list(...)`` or the result of a call, but got: texts. The "
                "list 'result' would be an alias of texts, and the targets "
                "disagree on the aliases of a list appended to: Python appends "
                "to the list in place, so that texts would see the appended "
                "items as well. Go appends to a slice with ``result = "
                "append(result, item)``, which gives a new slice whenever the "
                "array beneath it has to grow, so that texts would miss the "
                "items appended afterwards. C++ copies the list on an "
                "assignment, so that texts would never see the appended items. "
                "Please assign an explicit copy, ``result = list(texts)``, "
                "instead."
            ),
        )

    def test_appended_list_in_tuple_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> Tuple[List[str], int]:
    texts: List[str] = []
    texts.append(text)
    return (texts, 1)
""",
            expected_message=(
                "The list 'texts' is appended to, so we support it only as the "
                "receiver of ``append``, the container of ``in``, the "
                "collection of a for-loop, an argument of a call, such as "
                "``len(texts)``, the collection of an index or of a slice, the "
                "returned value, and the target of an assignment of a fresh "
                "list. Here it would be aliased, *e.g.*, as in ``other = "
                "texts``, in a tuple literal or as the value assigned to a "
                "property, and the targets disagree on the aliases of a list "
                "appended to: Python appends to the list in place, so that all "
                "the aliases see the appended items. Go appends to a slice with "
                "``texts = append(texts, item)``, which gives a new slice "
                "whenever the array beneath it has to grow, so that the aliases "
                "miss the items appended afterwards. C++ copies the list on an "
                "assignment, so that the copy never sees the items appended "
                "afterwards. Please copy the list explicitly with "
                "``list(texts)`` instead."
            ),
        )

    def test_append_in_loop_over_the_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    texts = [text]
    for other in texts:
        texts.append(other)
    return True
""",
            expected_message=(
                "The list texts can not be appended to in the for-loop over it, "
                "since the targets disagree on that: Python and TypeScript "
                "iterate over the appended items as well, Go does not, C# and "
                "Java throw an exception, and the behavior is undefined in C++."
            ),
        )

    def test_append_as_value_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    texts = [text]
    result = texts.append(text)
    return True
""",
            expected_message=(
                "The ``append`` of a list returns nothing, so it can only be "
                "called as a statement on its own.\n"
                "We can not infer the type of the variable 'result' from "
                "``None``. Please declare the variable with a type annotation, "
                "*e.g.*, ``result: Optional[...] = None``."
            ),
        )

    def test_empty_list_literal_without_annotation_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    texts = []
    return True
""",
            expected_message=(
                "We support an empty list literal ``[]`` only as the value "
                "assigned to a list, *e.g.*, ``x: List[str] = []``, or as the "
                "value returned from a function which returns a list, since the "
                "targets need to know the type of the items of the new list."
            ),
        )

    def test_list_literal_of_mixed_types_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str, number: int) -> bool:
    things = [text, number]
    return True
""",
            expected_message=(
                "Expected the items of the list literal to be assignable to "
                "str, but got: int. If the items are of different types, please "
                "declare the type of the list explicitly, *e.g.*, ``x: "
                "List[...] = [text, number]``."
            ),
        )

    def test_append_on_optional_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    texts: Optional[List[str]] = []
    if texts is not None:
        texts.append(text)
    return True
""",
            expected_message=(
                "We support ``append`` only on a local list variable which is "
                "not optional, but the variable 'texts' is declared as "
                "Optional[List[str]]. The targets represent an optional list "
                "differently, *e.g.*, Go as a pointer to a slice and C++ as an "
                "optional, so that they disagree on how to append to it. Please "
                "declare the variable as a list, *e.g.*, ``texts: List[str] = "
                "[]``."
            ),
        )

    def test_unknown_method_on_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str) -> bool:
    texts = [text]
    texts.extend([text])
    return True
""",
            expected_message=(
                "The member 'extend' is not supported on lists; we support only "
                "the following methods: 'append'"
            ),
        )

    def test_list_literal_of_shared_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Sequence[str]) -> bool:
    nested = [texts]
    return True
""",
            expected_message=(
                "The item texts of the list literal holds lists or sets, which "
                "Python would share, but C++ would copy. We can not transpile "
                "the sharing to C++, so please use an explicit copy, *e.g.*, a "
                "list copied with ``list(...)``, a list literal or a new set."
            ),
        )

    def test_append_of_shared_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Sequence[str]) -> bool:
    nested: List[List[str]] = []
    nested.append(texts)
    return True
""",
            expected_message=(
                "The item appended to nested holds lists or sets, which Python "
                "would share, but C++ would copy. We can not transpile the "
                "sharing to C++, so please append an explicit copy, *e.g.*, a "
                "list copied with ``list(...)``, a list literal or a new set."
            ),
        )

    def test_append_of_wrong_type_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int) -> bool:
    texts: List[str] = []
    texts.append(number)
    return True
""",
            expected_message=(
                "Expected the item appended to List[str] to be assignable to "
                "str, but got: int"
            ),
        )

    def test_list_literal_of_optional_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: Optional[str]) -> bool:
    texts = [text]
    return True
""",
            expected_message=(
                "The items of a list literal can not be None, as we support "
                "Optional only at the top of a type annotation, but the item is "
                "inferred to be Optional[str]. Please check first that the item "
                "is not None, *e.g.*, with ``if text is not None:``."
            ),
        )


class Test_method(unittest.TestCase):
    @staticmethod
    def source_with_methods(methods: str) -> str:
        return f"""\
class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"


@abstract
class Parent(DBC):
    count: int
    texts: List[str]

    @non_mutating
    def _parent_protected(self) -> int:
        return self.count

    @non_mutating
    def __parent_private(self) -> int:
        return self.count

    def reset(self) -> None:
        self.count = 0

{textwrap.indent(methods, "    ")}

    def __init__(self, count: int, texts: List[str]) -> None:
        self.count = count
        self.texts = texts


class Child(Parent):
    @non_mutating
    def calls_parent_private(self) -> int:
        return self.__parent_private()

    def __init__(self, count: int, texts: List[str]) -> None:
        Parent.__init__(self, count, texts)


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

    @staticmethod
    def infer(source: str) -> List[str]:
        """Infer the types in the meta-model, and return the error messages."""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        _, errors = intermediate_type_inference.infer(symbol_table=symbol_table)

        if errors is None:
            return []

        return [tests.common.most_underlying_messages([error]) for error in errors]

    def expect_errors(self, methods: str, expected_messages: List[str]) -> None:
        self.assertEqual(
            expected_messages,
            Test_method.infer(Test_method.source_with_methods(methods)),
        )

    def test_sequence_of_descendants_to_method_fails(self) -> None:
        # NOTE (mristin):
        # The arguments of the methods are never generic, since Go methods can not
        # have type parameters, and C++ virtual methods can not be templates.
        self.expect_errors(
            methods="""\
@non_mutating
def count_parents(self, parents: Sequence["Parent"]) -> int:
    return len(parents)

@non_mutating
def count_children(self, children: Sequence["Child"]) -> int:
    return self.count_parents(children)""",
            expected_messages=[
                "The argument 'parents' of the method 'count_parents' is of type "
                "List[Parent], but got: List[Child]. "
                + _COLLECTION_INVARIANCE_EXPLANATION,
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                ),
            ],
        )

    def test_sequence_argument_of_method_is_not_generic(self) -> None:
        # NOTE (mristin):
        # The usages of the sequence arguments of the methods are not restricted,
        # in contrast to the generic sequences of the verification functions, as
        # the methods take the sequences of the exact items.
        self.expect_errors(
            methods="""\
@non_mutating
def count_parents(self, parents: Sequence["Parent"]) -> int:
    return len(parents)

@non_mutating
def count_copies(self, parents: Sequence["Parent"]) -> int:
    copies = list(parents)
    return self.count_parents(parents) + len(copies)""",
            expected_messages=[
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                ),
            ],
        )

    def test_mutating_method_on_self(self) -> None:
        self.expect_errors(
            methods="""\
def increment(self, delta: int) -> int:
    self.count = self.count + delta + self._parent_protected()
    for i in range(0, len(self.texts)):
        self.texts[i] = ""
    self.reset()
    return self.count""",
            expected_messages=[
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                )
            ],
        )

    def test_assignment_to_self_in_non_mutating_method_fails(self) -> None:
        self.expect_errors(
            methods="""\
@non_mutating
def increment(self) -> None:
    self.count = self.count + 1""",
            expected_messages=[
                (
                    "We can not assign to the property 'count' of self, since "
                    "the method 'increment' is marked as @non_mutating, so it must "
                    "not change its instance."
                ),
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                ),
            ],
        )

    def test_mutating_call_in_non_mutating_method_fails(self) -> None:
        self.expect_errors(
            methods="""\
@non_mutating
def reset_twice(self) -> None:
    self.reset()""",
            expected_messages=[
                (
                    "The method 'reset' is not marked as @non_mutating, so it might "
                    "mutate its instance, but the method 'reset_twice' is marked as "
                    "@non_mutating, so it must not change its instance."
                ),
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                ),
            ],
        )

    def test_mutating_arguments_declared_mutable(self) -> None:
        self.expect_errors(
            methods="""\
@non_mutating
def clear(self, texts: List[str], other: Mutable["Parent"]) -> None:
    texts[0] = 'cleared'
    other.count = 0

def clear_own_texts(self, other: Mutable["Parent"]) -> None:
    self.clear(self.texts, other)""",
            expected_messages=[
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                )
            ],
        )

    def test_mutating_a_sequence_argument_fails(self) -> None:
        self.expect_errors(
            methods="""\
def clear(self, texts: Sequence[str]) -> None:
    texts[0] = 'cleared'""",
            expected_messages=[
                (
                    "We can not assign to an item of the list of texts, since "
                    "the argument 'texts' is declared as a Sequence, which is "
                    "read-only. Please declare it as a List if the method mutates it."
                ),
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                ),
            ],
        )

    def test_passing_read_only_to_mutable_argument_fails(self) -> None:
        self.expect_errors(
            methods="""\
@non_mutating
def clear(self, texts: List[str]) -> None:
    texts[0] = 'cleared'

@non_mutating
def clear_own_texts(self) -> None:
    self.clear(self.texts)""",
            expected_messages=[
                (
                    "The argument 'texts' of the method 'clear' is mutable, but "
                    "the method 'clear_own_texts' is marked as @non_mutating, so it "
                    "must not change its instance."
                ),
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                ),
            ],
        )

    def test_missing_return_fails(self) -> None:
        self.expect_errors(
            methods="""\
def count_texts(self) -> int:
    self.count = len(self.texts)""",
            expected_messages=[
                (
                    "Expected the method 'count_texts' of the class 'Parent' to end "
                    "with a return statement, since it returns a value"
                ),
                (
                    "The method '__parent_private' of the class 'Child' is private, "
                    "so it can be only called on self from the methods of the class"
                ),
            ],
        )


class Test_nested_collections(unittest.TestCase):
    maxDiff = None

    _PRELUDE = """\
class Item(DBC):
    lists: List[List[str]]
    pair: Tuple[List[str], int]
    list_of_sets: List[Set[str]]

    def __init__(
        self,
        lists: List[List[str]],
        pair: Tuple[List[str], int],
        list_of_sets: List[Set[str]],
    ) -> None:
        self.lists = lists
        self.pair = pair
        self.list_of_sets = list_of_sets


"""

    _EPILOGUE = """


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

    def expect_type_inference_to_fail(
        self, body: str, expected_joined_message: str
    ) -> None:
        Test_with_smoke().expect_type_inference_to_fail(
            source=Test_nested_collections._PRELUDE
            + body
            + Test_nested_collections._EPILOGUE,
            expected_joined_message=expected_joined_message,
        )

    def test_iteration_and_indexing_pass(self) -> None:
        Test_with_smoke.execute(
            source=Test_nested_collections._PRELUDE
            + """\
@verification
def some_func(
    lists: Sequence[Sequence[Tuple[int, AbstractSet[str]]]],
    text: str
) -> bool:
    for inner in lists:
        for pair in inner:
            if pair[0] > 0 and text in pair[1]:
                return len(lists[0][1][1]) > 0

    return all(
        all(len(pair[1]) > 0 for pair in inner)
        for inner in lists
    )"""
            + Test_nested_collections._EPILOGUE
        )

    def test_comparison_of_lists_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(lists: Sequence[Sequence[str]]) -> bool:
    return lists[0] == lists[1]""",
            expected_joined_message=(
                "We do not support comparing the lists, the tuples or the sets, "
                "but the right operand is inferred to be List[str]. The targets "
                "disagree on the comparison: Python compares them item by item, "
                "while C#, Java and TypeScript compare their references. Please "
                "compare their items instead, *e.g.*, in a for-loop.\n"
                "We do not support comparing the lists, the tuples or the sets, "
                "but the left operand is inferred to be List[str]. The targets "
                "disagree on the comparison: Python compares them item by item, "
                "while C#, Java and TypeScript compare their references. Please "
                "compare their items instead, *e.g.*, in a for-loop."
            ),
        )

    def test_comparison_of_tuples_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: str, number: int) -> bool:
    return (text, number) != (text, 1)""",
            expected_joined_message=(
                "We do not support comparing the lists, the tuples or the sets, "
                "but the right operand is inferred to be Tuple[str, int]. The targets "
                "disagree on the comparison: Python compares them item by item, "
                "while C#, Java and TypeScript compare their references. Please "
                "compare their items instead, *e.g.*, in a for-loop.\n"
                "We do not support comparing the lists, the tuples or the sets, "
                "but the left operand is inferred to be Tuple[str, int]. The targets "
                "disagree on the comparison: Python compares them item by item, "
                "while C#, Java and TypeScript compare their references. Please "
                "compare their items instead, *e.g.*, in a for-loop."
            ),
        )

    def test_list_as_member_of_in_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(lists: Sequence[Sequence[str]], texts: Sequence[str]) -> bool:
    return texts in lists""",
            expected_joined_message=(
                "We do not support looking up a list, a tuple or a set with "
                "``in``, but the member is inferred to be List[str]. The targets "
                "disagree on the comparison: Python compares the items item by "
                "item, while C#, Java and TypeScript compare their references."
            ),
        )

    def test_is_in_list_of_wrong_type_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int, texts: Sequence[str]) -> bool:
    return number in texts""",
            expected_joined_message=(
                "Expected the member to be of the type of the items of the list "
                "List[str], but got: int"
            ),
        )

    def test_is_in_str_of_non_str_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(number: int, text: str) -> bool:
    return number in text""",
            expected_joined_message=(
                "Expected the member to be a string as we check for a sub-string "
                "in the container str, but got: int"
            ),
        )

    def test_bytearray_as_member_of_in_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(blob: bytearray, blobs: Sequence[bytearray]) -> bool:
    return blob in blobs""",
            expected_joined_message=(
                "We do not support looking up a byte array with ``in``, but "
                "the member is inferred to be bytearray. The targets disagree on "
                "the comparison: Python compares the byte arrays byte by byte, "
                "C# and Java compare the references of their ``byte[]``'s, while "
                "Go can not compare ``[]byte`` with ``==`` at all. Please compare "
                "the byte arrays explicitly instead, *e.g.*, in a for-loop."
            ),
        )

    def test_json_value_as_member_of_in_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(value: JSONValue, values: Sequence[JSONValue]) -> bool:
    return value in values""",
            expected_joined_message=(
                "We do not support searching for a JSON-able value in a list "
                "with ``in``, but the member is inferred to be JSONValue. "
                "The targets disagree on the comparison: Python compares "
                "the JSON-able values by value, while C#, Java and TypeScript "
                "compare the references of their arrays and objects, and Go "
                "panics when comparing them. Please contact the developers if "
                "you need this feature."
            ),
        )

    def test_copy_of_list_of_sets_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(item: Mutable[Item]) -> bool:
    item.list_of_sets = list(item.list_of_sets)
    return True""",
            expected_joined_message=(
                "We can not copy the list of type List[Set[str]] with "
                "``list(...)``, since its items hold lists or sets themselves. "
                "Python copies the list shallowly, so that the copy shares "
                "the inner lists and sets, while C++ copies them as well. We do "
                "not support deep copies at the moment. Please contact "
                "the developers if you need this feature."
            ),
        )

    def test_storing_tuple_holding_list_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(item: Mutable[Item], other: Item) -> bool:
    item.pair = other.pair
    return True""",
            expected_joined_message=(
                "The value assigned to the property 'pair' of item holds lists or "
                "sets, "
                "which Python would share, but C++ would copy. We can not "
                "transpile the sharing to C++, so please assign explicit copies "
                "of them, *e.g.*, a tuple literal of the lists copied with "
                "``list(...)``. We do not support deep copies of the nested lists and "
                "sets at the moment. Please contact the developers if you need "
                "this feature."
            ),
        )

    def test_storing_tuple_literal_of_copies_passes(self) -> None:
        Test_with_smoke.execute(
            source=Test_nested_collections._PRELUDE
            + """\
@verification
def some_func(item: Mutable[Item], other: Item) -> bool:
    item.pair = (list(other.pair[0]), other.pair[1])
    return True"""
            + Test_nested_collections._EPILOGUE
        )

    def test_optional_in_tuple_literal_fails(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(text: Optional[str]) -> bool:
    pair = (text, 1)
    return True""",
            expected_joined_message=(
                "The items of a tuple can not be None, as we support Optional "
                "only at the top of a type annotation, but the item is inferred "
                "to be Optional[str]. Please check first that the item is not "
                "None, *e.g.*, with ``if text is not None:``."
            ),
        )

    def test_optional_items_in_local_annotation_fail(self) -> None:
        self.expect_type_inference_to_fail(
            body="""\
@verification
def some_func(texts: Sequence[Sequence[str]]) -> bool:
    lists: Optional[List[List[Optional[str]]]] = None
    return True""",
            expected_joined_message=(
                "We support Optional only at the top of a type annotation, so "
                "the items of a list can not be optional, but got: "
                "List[Optional[str]]"
            ),
        )


if __name__ == "__main__":
    unittest.main()
