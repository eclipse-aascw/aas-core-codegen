# pylint: disable=missing-docstring

import ast
import unittest
from typing import List, Mapping, Tuple

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

        type_inference_errors = []  # type: List[str]

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
                "We do not know how to infer the type of the variable with "
                "the identifier 'x' from the given environment. Mind that we "
                "do not consider the module scope nor handle all built-in "
                "functions due to simplicity! If you believe this needs to "
                "work, please notify the developers."
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
                "We do not know how to infer the type of the variable with "
                "the identifier 'x' from the given environment. Mind that we "
                "do not consider the module scope nor handle all built-in "
                "functions due to simplicity! If you believe this needs to "
                "work, please notify the developers."
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
                "The variable 'x' has been already defined in a branch of a "
                "switch before. In Python, both definitions denote the same "
                "variable, while they denote two different variables in the "
                "target languages with block scopes, and some target "
                "languages, such as C#, refuse such re-declarations "
                "altogether. Please use a different name."
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
                "The variable 'x' has been already defined in a branch of a "
                "switch before. In Python, both definitions denote the same "
                "variable, while they denote two different variables in the "
                "target languages with block scopes, and some target "
                "languages, such as C#, refuse such re-declarations "
                "altogether. Please use a different name."
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

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the subject of the switch to be an enumeration, a "
                "string or an integer, but got: bool"
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
                "The literal 'Gamma' could not be found in the enumeration " "'Kind'"
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
            "We support slicing only of non-None strings, but got: List[str]",
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
            "the following methods: 'find'",
        )


if __name__ == "__main__":
    unittest.main()
