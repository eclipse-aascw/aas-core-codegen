# pylint: disable=missing-docstring

import textwrap
import unittest
from typing import List

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
        source = textwrap.dedent(
            """\
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
        )

        Test_with_smoke.execute(source=source)

    def test_class_member(self) -> None:
        source = textwrap.dedent(
            """\
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
        )

        Test_with_smoke.execute(source=source)

    def test_non_nullness_of_members_member_in_implication(self) -> None:
        source = textwrap.dedent(
            """\
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
        )

        Test_with_smoke.execute(source=source)

    def test_non_nullness_of_members_member_in_conjunction(self) -> None:
        source = textwrap.dedent(
            """\
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
        )

        Test_with_smoke.execute(source=source)

    def test_non_nullness_in_disjunction_with_is_none(self) -> None:
        source = textwrap.dedent(
            """\
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
        )

        Test_with_smoke.execute(source=source)

    def test_tuple_literal(self) -> None:
        source = textwrap.dedent(
            """\
            @verification
            def some_verification(x: str, y: int) -> bool:
                return (x, y)[0] == x


            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        Test_with_smoke.execute(source=source)

    def test_tuple_of_classes(self) -> None:
        source = textwrap.dedent(
            """\
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
        )

        Test_with_smoke.execute(source=source)

    def test_is_none_fails_on_non_optional(self) -> None:
        source = textwrap.dedent(
            """\
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
        )

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the value to be of an optional type "
                "for a nullness check (``is None``), but got str"
            ),
        )

    def test_is_not_none_fails_on_non_optional(self) -> None:
        source = textwrap.dedent(
            """\
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
        )

        self.expect_type_inference_to_fail(
            source=source,
            expected_joined_message=(
                "Expected the value to be of an optional type "
                "for a non-nullness check (``is not None``), but got str"
            ),
        )


if __name__ == "__main__":
    unittest.main()
