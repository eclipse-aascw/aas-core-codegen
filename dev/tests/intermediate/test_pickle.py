#!/usr/bin/env python3

# pylint: disable=missing-docstring

import ast
import inspect
import pathlib
import pickle
import re
import textwrap
import unittest
from typing import List, Dict, Optional, Final, Sequence

from icontract import require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier

# noinspection PyProtectedMember
from aas_core_codegen.intermediate import _types as intermediate_types

import tests.common


class TestPickle(unittest.TestCase):
    def test_enumeration(self) -> None:
        source = textwrap.dedent(
            """\
            from enum import Enum

            class Some_enum(Enum):
                Literal1 = "literal_1"
                Literal2 = "literal_2"

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None and symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("Some_enum"))

        # NOTE (mristin):
        # We first test that ID sets are working before pickling.
        original_id_set = some_enum.literal_id_set
        self.assertEqual(len(original_id_set), 2)
        self.assertIn(id(some_enum.literals[0]), original_id_set)
        self.assertIn(id(some_enum.literals[1]), original_id_set)

        pickled_data = pickle.dumps(some_enum)
        unpickled_enum = pickle.loads(pickled_data)

        # NOTE (mristin):
        # We now test that the unpickled ID sets are also working.
        self.assertEqual(unpickled_enum.name, "Some_enum")
        self.assertEqual(len(unpickled_enum.literals), 2)
        self.assertEqual(unpickled_enum.literals[0].name, "Literal1")
        self.assertEqual(unpickled_enum.literals[1].name, "Literal2")

        new_id_set = unpickled_enum.literal_id_set
        self.assertEqual(len(new_id_set), 2)
        self.assertIn(id(unpickled_enum.literals[0]), new_id_set)
        self.assertIn(id(unpickled_enum.literals[1]), new_id_set)

        # NOTE (mristin):
        # The ID sets should be different since objects have new IDs after unpickling.
        self.assertNotEqual(original_id_set, new_id_set)

    def test_abstract_class(self) -> None:
        source = textwrap.dedent(
            """\
            @abstract
            class Some_abstract_class:
                some_property: int

                @require(lambda some_property: some_property > 0)
                def __init__(self, some_property: int) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None and symbol_table is not None

        some_abstract_class = symbol_table.must_find_abstract_class(
            Identifier("Some_abstract_class")
        )

        pickled_data = pickle.dumps(some_abstract_class)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.AbstractClass)

        self.assertEqual(unpickled.name, "Some_abstract_class")
        self.assertEqual(len(unpickled.properties), 1)
        self.assertEqual(unpickled.properties[0].name, "some_property")

        # Test that ID sets are rebuilt correctly
        self.assertIn(id(unpickled.properties[0]), unpickled.property_id_set)

    def test_argument(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                def some_method(self, some_arg: int) -> None:
                    pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None and symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_method = some_class.methods[0]
        some_arg = some_method.arguments[0]

        pickled_data = pickle.dumps(some_arg)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Argument)

        self.assertEqual(unpickled.name, "some_arg")

    def test_class(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: int
                
                def __init__(
                        self,
                        some_property: int
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_class(Identifier("Some_class"))

        pickled_data = pickle.dumps(some_class)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.ConcreteClass)

        self.assertEqual(unpickled.name, "Some_class")

        self.assertIn(id(unpickled.properties[0]), unpickled.property_id_set)

    def test_concrete_class(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_concrete_class:
                some_property: int

                def __init__(
                        self,
                        some_property: int
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_concrete_class = symbol_table.must_find_concrete_class(
            Identifier("Some_concrete_class")
        )

        pickled_data = pickle.dumps(some_concrete_class)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.ConcreteClass)

        self.assertEqual(unpickled.name, "Some_concrete_class")
        self.assertEqual(len(unpickled.properties), 1)

        self.assertIn(id(unpickled.properties[0]), unpickled.property_id_set)

    def test_constant_primitive(self) -> None:
        source = textwrap.dedent(
            """\
            Some_constant: str = constant_str(
                value="some_value",
            )

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_constant = symbol_table.must_find_constant_primitive(
            Identifier("Some_constant")
        )

        pickled_data = pickle.dumps(some_constant)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.ConstantPrimitive)

        self.assertEqual(unpickled.name, "Some_constant")
        self.assertEqual(unpickled.value, "some_value")

    def test_constant_set_of_primitives(self) -> None:
        source = textwrap.dedent(
            """\
            from aas_core_meta.marker import (
                constant_set
            )

            Some_constant_set: Set[str] = constant_set(
                values=["value1", "value2"]
            )

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_constant_set = symbol_table.must_find_constant_set_of_primitives(
            Identifier("Some_constant_set")
        )

        pickled_data = pickle.dumps(some_constant_set)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.ConstantSetOfPrimitives)

        self.assertEqual(unpickled.name, "Some_constant_set")
        self.assertEqual(len(unpickled.literals), 2)

    def test_constrained_primitive(self) -> None:
        source = textwrap.dedent(
            """\
            @invariant(lambda self: len(self) > 0, "Non-empty")
            class Some_constrained_primitive(str):
                pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_constrained_primitive = symbol_table.must_find_constrained_primitive(
            Identifier("Some_constrained_primitive")
        )

        pickled_data = pickle.dumps(some_constrained_primitive)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.ConstrainedPrimitive)

        self.assertEqual(unpickled.name, "Some_constrained_primitive")

        self.assertIn(id(unpickled.invariants[0]), unpickled.invariant_id_set)

    def test_constructor(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: int

                def __init__(self, some_property: int) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        constructor = some_class.constructor

        pickled_data = pickle.dumps(constructor)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Constructor)

        self.assertEqual(len(unpickled.arguments), 1)

    def test_contract(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                @require(lambda self: True)
                @ensure(lambda result: True)
                def some_method(self) -> bool:
                    return True

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_method = some_class.methods[0]
        contract = some_method.contracts.preconditions[0]

        pickled_data = pickle.dumps(contract)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Contract)

        self.assertIsNotNone(unpickled.body)

    def test_contracts(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                @require(lambda self: True)
                def some_method(self) -> None:
                    pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_method = some_class.methods[0]
        contracts = some_method.contracts

        pickled_data = pickle.dumps(contracts)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Contracts)

        self.assertEqual(len(unpickled.preconditions), 1)

    def test_default_primitive(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: str
            
                def __init__(self, some_property: str = 'some_default') -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))

        arg = some_class.constructor.arguments_by_name[Identifier("some_property")]

        default = arg.default

        pickled_data = pickle.dumps(default)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.DefaultPrimitive)

    def test_default_enumeration_literal(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_enum(Enum):
                Literal1 = "literal-1"
                Literal2 = "literal-2"
            
            class Some_class:
                some_property: Some_enum

                def __init__(
                        self, 
                        some_property: Some_enum = Some_enum.Literal1
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))

        arg = some_class.constructor.arguments_by_name[Identifier("some_property")]

        default = arg.default

        pickled_data = pickle.dumps(default)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.DefaultEnumerationLiteral)

    def test_description_of_constant(self) -> None:
        source = textwrap.dedent(
            """\
            Some_constant: str = constant_str(
                value="some_value",
                description="This is some constant."
            )

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_constant = symbol_table.must_find_constant_primitive(
            Identifier("Some_constant")
        )
        description = some_constant.description
        assert description is not None

        pickled_data = pickle.dumps(description)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.DescriptionOfConstant), str(
            type(unpickled)
        )

        self.assertEqual(unpickled.summary[0], "This is some constant.")

    def test_description_of_enumeration_literal(self) -> None:
        source = textwrap.dedent(
            """\
            from enum import Enum

            class Some_enum(Enum):
                literal1 = "value1"
                \"\"\"Describe the literal.\"\"\"

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("Some_enum"))
        literal = some_enum.literals[0]
        description = literal.description

        pickled_data = pickle.dumps(description)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.DescriptionOfEnumerationLiteral)

        self.assertEqual(unpickled.summary[0], "Describe the literal.")

    def test_description_of_meta_model(self) -> None:
        source = textwrap.dedent(
            """\
            \"\"\"Meta-model description.\"\"\"

            class Some_class:
                pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        meta_model = symbol_table.meta_model
        description = meta_model.description

        pickled_data = pickle.dumps(description)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.DescriptionOfMetaModel)

        self.assertEqual(unpickled.summary[0], "Meta-model description.")

    def test_description_of_our_type(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                \"\"\"Describe the class.\"\"\"
                pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        description = some_class.description

        pickled_data = pickle.dumps(description)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.DescriptionOfOurType)

        self.assertEqual(unpickled.summary[0], "Describe the class.")

    def test_description_of_property(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: int
                \"\"\"Describe the property.\"\"\"
                
                def __init__(
                        self,
                        some_property: int
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_property = some_class.properties[0]
        description = some_property.description

        pickled_data = pickle.dumps(description)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.DescriptionOfProperty)

        self.assertEqual(unpickled.summary[0], "Describe the property.")

    def test_description_of_signature(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                def some_method(self) -> None:
                    \"\"\"Describe the method.\"\"\"
                    pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_method = some_class.methods[0]
        description = some_method.description

        pickled_data = pickle.dumps(description)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.DescriptionOfSignature)

        self.assertEqual(unpickled.summary[0], "Describe the method.")

    def test_enumeration_literal(self) -> None:
        source = textwrap.dedent(
            """\
            from enum import Enum

            class Some_enum(Enum):
                literal1 = "value1"

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("Some_enum"))
        literal = some_enum.literals[0]

        pickled_data = pickle.dumps(literal)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.EnumerationLiteral)

        self.assertEqual(unpickled.name, "literal1")
        self.assertEqual(unpickled.value, "value1")

    def test_implementation_specific_method(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                @implementation_specific
                def some_method(self) -> None:
                    pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_method = some_class.methods[0]

        pickled_data = pickle.dumps(some_method)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.ImplementationSpecificMethod)

        self.assertEqual(unpickled.name, "some_method")

    def test_implementation_specific_verification(self) -> None:
        source = textwrap.dedent(
            """\
            @verification
            @implementation_specific
            def some_verification(x: int) -> bool:
                pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        verification = symbol_table.verification_functions[0]

        pickled_data = pickle.dumps(verification)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.ImplementationSpecificVerification)

        self.assertEqual(unpickled.name, "some_verification")

    def test_interface(self) -> None:
        source = textwrap.dedent(
            """\
            @abstract
            class Some_abstract_class:
                some_property: int
                
                def __init__(
                        self,
                        some_property: int
                ) -> None:
                    self.some_property = some_property
                
                def some_func(self) -> None:
                    pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_abstract_class = symbol_table.must_find_abstract_class(
            Identifier("Some_abstract_class")
        )

        interface = some_abstract_class.interface

        pickled_data = pickle.dumps(interface)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Interface)

        self.assertEqual(unpickled.name, "Some_abstract_class")

        self.assertIn(id(unpickled.properties[0]), unpickled.property_id_set)

    def test_invariant(self) -> None:
        source = textwrap.dedent(
            """\
            @invariant(lambda self: self.some_property > 0, "Some property is positive")
            class Some_class:
                some_property: int                                

                def __init__(self, some_property: int) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        invariant = some_class.invariants[0]

        pickled_data = pickle.dumps(invariant)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Invariant)

        self.assertIsNotNone(unpickled.body)

    def test_list_type_annotation(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: List[str]
                
                def __init__(
                        self,
                        some_property: List[str]
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_property = some_class.properties[0]
        type_annotation = some_property.type_annotation

        pickled_data = pickle.dumps(type_annotation)
        unpickled = pickle.loads(pickled_data)

        self.assertIsInstance(unpickled, intermediate_types.ListTypeAnnotation)

    def test_tuple_type_annotation(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: Tuple[str, int]

                def __init__(
                        self,
                        some_property: Tuple[str, int]
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_property = some_class.properties[0]
        type_annotation = some_property.type_annotation

        pickled_data = pickle.dumps(type_annotation)
        unpickled = pickle.loads(pickled_data)

        self.assertIsInstance(unpickled, intermediate_types.TupleTypeAnnotation)

    def test_meta_model(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        meta_model = symbol_table.meta_model

        pickled_data = pickle.dumps(meta_model)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate_types.MetaModel)

        self.assertEqual(unpickled.version, "dummy")

    def test_method(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                def some_method(self) -> None:
                    pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_method = some_class.methods[0]

        pickled_data = pickle.dumps(some_method)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.UnderstoodMethod)

        self.assertEqual(unpickled.name, "some_method")

    def test_optional_type_annotation(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: Optional[str]

                def __init__(
                    self,
                    some_property: Optional[str] = None
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_property = some_class.properties[0]
        type_annotation = some_property.type_annotation

        pickled_data = pickle.dumps(type_annotation)
        unpickled = pickle.loads(pickled_data)

        self.assertIsInstance(unpickled, intermediate_types.OptionalTypeAnnotation)

    def test_our_type_annotation(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                pass

            class Some_another_class:
                some_property: Some_class
                
                def __init__(
                        self,
                        some_property: Some_class
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_another_class = symbol_table.must_find_concrete_class(
            Identifier("Some_another_class")
        )
        some_property = some_another_class.properties[0]
        type_annotation = some_property.type_annotation

        pickled_data = pickle.dumps(type_annotation)
        unpickled = pickle.loads(pickled_data)

        self.assertIsInstance(unpickled, intermediate_types.OurTypeAnnotation)

    def test_pattern_verification(self) -> None:
        source = textwrap.dedent(
            """\
            @verification
            def some_verification(x: str) -> bool:
                return match(r"^[a-z]+$", x) is not None

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        verification = symbol_table.verification_functions[0]

        pickled_data = pickle.dumps(verification)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.PatternVerification)

        self.assertEqual(unpickled.name, "some_verification")

    def test_primitive_set_literal(self) -> None:
        source = textwrap.dedent(
            """\
            from aas_core_meta.marker import (
                constant_set
            )

            Some_constant_set: Set[str] = constant_set(
                values=["value1", "value2"]
            )

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_constant_set = symbol_table.must_find_constant_set_of_primitives(
            Identifier("Some_constant_set")
        )
        literal = some_constant_set.literals[0]

        pickled_data = pickle.dumps(literal)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.PrimitiveSetLiteral)

        self.assertEqual(unpickled.value, "value1")

    def test_primitive_type(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: str
                
                def __init__(
                        self,
                        some_property: str
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_property = some_class.properties[0]
        type_annotation = some_property.type_annotation
        assert isinstance(type_annotation, intermediate_types.PrimitiveTypeAnnotation)
        primitive_type = type_annotation.a_type

        pickled_data = pickle.dumps(primitive_type)
        unpickled = pickle.loads(pickled_data)

        self.assertEqual(unpickled, intermediate_types.PrimitiveType.STR)

    def test_primitive_type_annotation(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: str
                
                def __init__(
                        self,
                        some_property: str
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_property = some_class.properties[0]
        type_annotation = some_property.type_annotation

        pickled_data = pickle.dumps(type_annotation)
        unpickled = pickle.loads(pickled_data)

        self.assertIsInstance(unpickled, intermediate_types.PrimitiveTypeAnnotation)

    def test_property(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: str
                
                def __init__(
                        self,
                        some_property: str
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_property = some_class.properties[0]

        pickled_data = pickle.dumps(some_property)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Property)

        self.assertEqual(unpickled.name, "some_property")

    def test_serialization(self) -> None:
        source = textwrap.dedent(
            """\
            @serialization(with_model_type=True)
            class Some_class:
                some_property: str
                
                def __init__(self, some_property: str) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        serialization = some_class.serialization

        pickled_data = pickle.dumps(serialization)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Serialization)

        self.assertEqual(unpickled.with_model_type, True)

    def test_signature(self) -> None:
        source = textwrap.dedent(
            """\
            @abstract
            class Some_abstract_class:
                some_property: int
            
                def __init__(self, some_property: int) -> None:
                    self.some_property = some_property
            
                def some_func(self) -> None:
                    pass
            
            
            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_abstract_class = symbol_table.must_find_abstract_class(
            Identifier("Some_abstract_class")
        )

        signature = some_abstract_class.interface.signatures[0]

        pickled_data = pickle.dumps(signature)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Signature)

        self.assertEqual(unpickled.name, "some_func")

    def test_signature_like(self) -> None:
        source = textwrap.dedent(
            """\
            @abstract
            class Some_abstract_class:
                some_property: int

                def __init__(self, some_property: int) -> None:
                    self.some_property = some_property
            
                def some_func(self) -> None:
                    pass
            
            
            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        source = textwrap.dedent(
            """\
            @abstract
            class Some_abstract_class:
                some_property: int

                @require(lambda some_property: some_property > 0)
                def __init__(self, some_property: int) -> None:
                    self.some_property = some_property

                def some_func(self) -> None:
                    pass


            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_abstract_class = symbol_table.must_find_abstract_class(
            Identifier("Some_abstract_class")
        )

        signature_like: intermediate_types.SignatureLike = some_abstract_class.methods[
            0
        ]

        pickled_data = pickle.dumps(signature_like)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate_types.SignatureLike)

        self.assertEqual(unpickled.name, "some_func")

    def test_snapshot(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: int
                
                def __init__(self, some_property: int) -> None:
                    self.some_property = some_property
            
                @snapshot(lambda self: self.some_property + 1)
                def some_method(self) -> None:
                    pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_method = some_class.methods[0]
        snapshot = some_method.contracts.snapshots[0]

        pickled_data = pickle.dumps(snapshot)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Snapshot)

        self.assertIsNotNone(unpickled.body)

    def test_summary_remarks_constraints_description(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                \"\"\"
                Summary line.

                Some remark.
                    
                :constraint A10: Soem constraint
                \"\"\"

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        description = some_class.description

        pickled_data = pickle.dumps(description)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.SummaryRemarksConstraintsDescription)

        self.assertEqual(unpickled.summary[0], "Summary line.")

    def test_summary_remarks_description(self) -> None:
        source = textwrap.dedent(
            """\
            from enum import Enum

            class Some_class:
                \"\"\"
                Summary line.

                Some remarks.

                Some description.
                \"\"\"

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_class(Identifier("Some_class"))
        description = some_class.description

        pickled_data = pickle.dumps(description)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.SummaryRemarksDescription), str(
            type(unpickled)
        )

        self.assertEqual(unpickled.summary[0], "Summary line.")

    def test_symbol_table(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        pickled_data = pickle.dumps(symbol_table)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.SymbolTable)

        self.assertEqual(len(unpickled.concrete_classes), 1)

    def test_transpilable_verification(self) -> None:
        source = textwrap.dedent(
            """\
            @verification
            def some_verification(x: int) -> bool:
                return x > 0

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        verification = symbol_table.verification_functions[0]

        pickled_data = pickle.dumps(verification)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.TranspilableVerification)

        self.assertEqual(unpickled.name, "some_verification")

    def test_type_annotation(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                some_property: str
                
                def __init__(
                        self,
                        some_property: str
                ) -> None:
                    self.some_property = some_property

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_property = some_class.properties[0]
        type_annotation = some_property.type_annotation

        pickled_data = pickle.dumps(type_annotation)
        unpickled = pickle.loads(pickled_data)

        self.assertIsInstance(unpickled, intermediate_types.TypeAnnotation)

    def test_understood_method(self) -> None:
        source = textwrap.dedent(
            """\
            class Some_class:
                def some_method(self) -> None:
                    pass

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_class = symbol_table.must_find_concrete_class(Identifier("Some_class"))
        some_method = some_class.methods[0]

        pickled_data = pickle.dumps(some_method)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.UnderstoodMethod)

        self.assertEqual(unpickled.name, "some_method")

    def test_verification(self) -> None:
        source = textwrap.dedent(
            """\
            @verification
            def some_verification(x: int) -> bool:
                return x > 0

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        verification = symbol_table.verification_functions[0]

        pickled_data = pickle.dumps(verification)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.Verification)

        self.assertEqual(unpickled.name, "some_verification")

    def test_constant_set_of_enumeration_literals(self) -> None:
        source = textwrap.dedent(
            """\
            from enum import Enum

            from aas_core_meta.marker import (
                constant_set
            )

            class Some_enum(Enum):
                Literal1 = "lit1"
                Literal2 = "lit2"

            Some_constant_set: Set[Some_enum] = constant_set(
                values=[
                    Some_enum.Literal1
                ]
            )

            __version__ = "dummy"
            __xml_namespace__ = "https://dummy.com"
            """
        )

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        if error is not None:
            raise AssertionError(tests.common.most_underlying_messages(error))
        assert symbol_table is not None

        some_constant_set = symbol_table.must_find_constant_set_of_enumeration_literals(
            Identifier("Some_constant_set")
        )

        # Test before pickling
        original_id_set = some_constant_set.literal_id_set
        self.assertEqual(len(original_id_set), 1)
        self.assertIn(id(some_constant_set.literals[0]), original_id_set)

        # Pickle and unpickle
        pickled_data = pickle.dumps(some_constant_set)
        unpickled = pickle.loads(pickled_data)

        assert isinstance(unpickled, intermediate.ConstantSetOfEnumerationLiterals)

        # Test after unpickling
        self.assertEqual(unpickled.name, "Some_constant_set")
        self.assertEqual(len(unpickled.literals), 1)
        self.assertEqual(unpickled.literals[0].name, "Literal1")

        # Test that ID sets are rebuilt correctly
        new_id_set = unpickled.literal_id_set
        self.assertEqual(len(new_id_set), 1)
        self.assertIn(id(unpickled.literals[0]), new_id_set)


def _to_lower_snake_case(cls_name: str) -> str:
    """
    Convert a class name from CamelCase to snake_case.

    >>> _to_lower_snake_case("Enumeration")
    'enumeration'

    >>> _to_lower_snake_case("EnumerationLiteral")
    'enumeration_literal'

    >>> _to_lower_snake_case("ConstrainedPrimitive")
    'constrained_primitive'

    >>> _to_lower_snake_case("ConstructorArgumentOfClass")
    'constructor_argument_of_class'

    >>> _to_lower_snake_case("_ConstructorArgumentOfClass")
    'constructor_argument_of_class'
    """
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", cls_name.lstrip("_"))
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


class TestAssertions(unittest.TestCase):
    def test_coverage(self) -> None:
        """Assert that all classes from intermediate._types are covered in test methods."""
        all_classes = []  # type: List[str]
        for class_name, obj in inspect.getmembers(intermediate_types, inspect.isclass):
            if obj.__module__ == intermediate_types.__name__:
                all_classes.append(class_name)

        expected_test_prefixes = [
            f"test_{_to_lower_snake_case(cls_name)}" for cls_name in all_classes
        ]

        test_methods = []  # type: List[str]
        for method_name in dir(TestPickle):
            if method_name.startswith("test_") and callable(
                getattr(TestPickle, method_name)
            ):
                test_methods.append(method_name)

        missing_tests = []  # type: List[str]
        for expected_prefix in expected_test_prefixes:
            found = any(
                test_method.startswith(expected_prefix) for test_method in test_methods
            )
            if not found:
                missing_tests.append(expected_prefix)

        if len(missing_tests) > 0:
            missing_classes = []
            for prefix in missing_tests:
                assert prefix.startswith("test_") and len("test_") == 5
                snake_case_name = prefix[5:]

                parts = snake_case_name.split("_")
                original_name = "".join(word.capitalize() for word in parts)
                missing_classes.append(original_name)

            missing_tests_joined = ",\n".join(missing_tests)

            raise AssertionError(
                f"Missing one or more test methods "
                f"in {TestPickle.__name__} for {len(missing_tests)} class(es):\n"
                f"{missing_tests_joined}"
            )

    def test_getstate_setstate_consistency(self) -> None:
        class _PickableClass:
            """Represent a class which has pickle/unpickle methods."""

            getstate: Final[Optional[ast.FunctionDef]]
            setstate: Final[Optional[ast.FunctionDef]]
            id_set_properties: Final[Sequence[str]]

            @require(
                lambda getstate: not (getstate is not None)
                or getstate.name == "__getstate__"
            )
            @require(
                lambda setstate: not (setstate is not None)
                or setstate.name == "__setstate__"
            )
            def __init__(
                self,
                id_set_properties: Sequence[str],
                getstate: Optional[ast.FunctionDef] = None,
                setstate: Optional[ast.FunctionDef] = None,
            ) -> None:
                self.id_set_properties = id_set_properties
                self.getstate = getstate
                self.setstate = setstate

        types_file = pathlib.Path(intermediate_types.__file__)
        source_code = types_file.read_text(encoding="utf-8")

        tree = ast.parse(source_code)

        class_map = {}  # type: Dict[str, _PickableClass]

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                id_set_properties = []  # type: List[str]

                # NOTE (mristin):
                # We go through all type-annotated properties and pick all properties
                # with suffix ``*_id_set``. This will give us some guard rails to make
                # sure that we did not forget to pop/set these properties in
                # ``__getstate__`` and ``__setstate__``. However, there might be more
                # runtime properties which need checking. Eventually, though unlikely,
                # the suffix ``_id_set`` might be misleading, so then we have to add
                # white listing here.
                for item in node.body:
                    if isinstance(item, ast.AnnAssign):
                        if isinstance(item.target, ast.Name):
                            property_name = item.target.id
                            if property_name.endswith("_id_set"):
                                id_set_properties.append(property_name)

                getstate = None  # type: Optional[ast.FunctionDef]
                setstate = None  # type: Optional[ast.FunctionDef]

                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        if item.name == "__getstate__":
                            getstate = item

                        elif item.name == "__setstate__":
                            setstate = item

                        else:
                            pass

                if getstate is not None or setstate is not None:
                    class_map[node.name] = _PickableClass(
                        id_set_properties=id_set_properties,
                        getstate=getstate,
                        setstate=setstate,
                    )

        for class_name, cls in class_map.items():
            if cls.getstate is None and cls.setstate is None:
                continue

            if cls.getstate is None and cls.setstate is not None:
                raise AssertionError(
                    f"Unexpected missing __getstate__ when __setstate__ is specified "
                    f"in the class {class_name!r}"
                )

            if cls.getstate is not None and cls.setstate is None:
                raise AssertionError(
                    f"Unexpected missing __setstate__ when __getstate__ is specified "
                    f"in the class {class_name!r}"
                )

            assert cls.getstate is not None and cls.setstate is not None

            # NOTE (mristin):
            # We extract popped attributes from ``__getstate__``.
            popped_attrs = []  # type: List[str]

            for node in ast.walk(cls.getstate):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "pop"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "state"
                ):
                    if (
                        len(node.args) > 0
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        popped_attrs.append(node.args[0].value)

            setattr_attrs = []  # type: List[str]

            for node in ast.walk(cls.setstate):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "setattr"
                ):
                    # NOTE (mristin):
                    # The second argument is the name of the attribute.
                    if (
                        len(node.args) >= 2
                        and isinstance(node.args[0], ast.Name)
                        and node.args[0].id == "self"
                        and isinstance(node.args[1], ast.Constant)
                        and isinstance(node.args[1].value, str)
                    ):
                        setattr_attrs.append(node.args[1].value)

            if set(popped_attrs) != set(setattr_attrs):
                raise AssertionError(
                    f"In class {class_name!r}, there is a mismatch between "
                    f"popped attributes in __getstate__: {sorted(popped_attrs)}, "
                    f"and setattr attributes in __setstate__: {sorted(setattr_attrs)}"
                )

            # NOTE (mristin):
            # We check that all properties with suffix ``_id_set`` are popped in
            # ``__getstate__`` and, consequently, set in ``__setstate__``.
            id_set_properties_set = set(cls.id_set_properties)
            popped_attrs_set = set(popped_attrs)
            if not id_set_properties_set.issubset(popped_attrs_set):
                missing_from_popped = id_set_properties_set - popped_attrs_set
                raise AssertionError(
                    f"In class {class_name!r}, the following properties "
                    f"containing runtime ID sets are not being popped in __getstate__: "
                    f"{sorted(missing_from_popped)}."
                )

            if len(cls.getstate.body) < 2:
                raise AssertionError(
                    f"Class {class_name}: __getstate__ should have at least 2 statements"
                )

            # First statement should be state = self.__dict__.copy().
            getstate_first_stmt = cls.getstate.body[0]
            if not (
                isinstance(getstate_first_stmt, ast.Assign)
                and len(getstate_first_stmt.targets) == 1
                and isinstance(getstate_first_stmt.targets[0], ast.Name)
                and getstate_first_stmt.targets[0].id == "state"
            ):
                raise AssertionError(
                    f"In class {class_name!r}, the method __getstate__ should start "
                    f"with 'state = ...'"
                )

            # Last statement should be return state.
            getstate_last_stmt = cls.getstate.body[-1]
            if not (
                isinstance(getstate_last_stmt, ast.Return)
                and isinstance(getstate_last_stmt.value, ast.Name)
                and getstate_last_stmt.value.id == "state"
            ):
                raise AssertionError(
                    f"In class {class_name!r}, the method __getstate__ should end "
                    f"with 'return state'"
                )

            if len(cls.setstate.body) == 0:
                raise AssertionError(
                    f"In class {class_name!r}, the method __setstate__ should have "
                    f"at least 1 statement"
                )

            # First statement should be self.__dict__.update(state).
            setstate_first_stmt = cls.setstate.body[0]
            if not (
                isinstance(setstate_first_stmt, ast.Expr)
                and isinstance(setstate_first_stmt.value, ast.Call)
                and isinstance(setstate_first_stmt.value.func, ast.Attribute)
                and setstate_first_stmt.value.func.attr == "update"
            ):
                raise AssertionError(
                    f"In class {class_name!r}, the method __setstate__ should start "
                    f"with 'self.__dict__.update(state)'"
                )


if __name__ == "__main__":
    unittest.main()
