# pylint: disable=missing-docstring

import unittest

import tests.common
from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier


class TestMappingOfPrimitiveTypesProperlyExposed(unittest.TestCase):
    def test_primitive_type_to_python_type(self) -> None:
        self.assertEqual(
            intermediate.PRIMITIVE_TYPE_TO_PYTHON_TYPE[intermediate.PrimitiveType.BOOL],
            bool,
        )

        self.assertEqual(
            intermediate.PRIMITIVE_TYPE_TO_PYTHON_TYPE[intermediate.PrimitiveType.INT],
            int,
        )

        self.assertEqual(
            intermediate.PRIMITIVE_TYPE_TO_PYTHON_TYPE[
                intermediate.PrimitiveType.FLOAT
            ],
            float,
        )

        self.assertEqual(
            intermediate.PRIMITIVE_TYPE_TO_PYTHON_TYPE[intermediate.PrimitiveType.STR],
            str,
        )

        self.assertEqual(
            intermediate.PRIMITIVE_TYPE_TO_PYTHON_TYPE[
                intermediate.PrimitiveType.BYTEARRAY
            ],
            bytearray,
        )

    def test_python_type_to_primitive_type(self) -> None:
        self.assertEqual(
            intermediate.PYTHON_TYPE_TO_PRIMITIVE_TYPE[bool],
            intermediate.PrimitiveType.BOOL,
        )

        self.assertEqual(
            intermediate.PYTHON_TYPE_TO_PRIMITIVE_TYPE[int],
            intermediate.PrimitiveType.INT,
        )

        self.assertEqual(
            intermediate.PYTHON_TYPE_TO_PRIMITIVE_TYPE[float],
            intermediate.PrimitiveType.FLOAT,
        )

        self.assertEqual(
            intermediate.PYTHON_TYPE_TO_PRIMITIVE_TYPE[str],
            intermediate.PrimitiveType.STR,
        )

        self.assertEqual(
            intermediate.PYTHON_TYPE_TO_PRIMITIVE_TYPE[bytearray],
            intermediate.PrimitiveType.BYTEARRAY,
        )


class TestIsSubclassOf(unittest.TestCase):
    def test_no_inheritances(self) -> None:
        source = """\
class Concrete:
    pass


class AnotherConcrete:
    pass


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)

        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))

        another_concrete = symbol_table.must_find_concrete_class(
            Identifier("AnotherConcrete")
        )

        self.assertTrue(concrete.is_subclass_of(cls=concrete))
        self.assertFalse(concrete.is_subclass_of(cls=another_concrete))

    def test_one_level_ancestor(self) -> None:
        source = """\
class Parent:
    pass


class Concrete(Parent):
    pass


class AnotherConcrete:
    pass


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)

        assert symbol_table is not None

        parent = symbol_table.must_find_concrete_class(Identifier("Parent"))

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))

        another_concrete = symbol_table.must_find_concrete_class(
            Identifier("AnotherConcrete")
        )

        self.assertTrue(concrete.is_subclass_of(cls=concrete))
        self.assertTrue(concrete.is_subclass_of(cls=parent))
        self.assertFalse(concrete.is_subclass_of(cls=another_concrete))

    def test_two_level_ancestor(self) -> None:
        source = """\
class GrandParent:
    pass


class Parent(GrandParent):
    pass


class Concrete(Parent):
    pass


class AnotherConcrete:
    pass


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)

        assert symbol_table is not None

        grand_parent = symbol_table.must_find_concrete_class(Identifier("GrandParent"))

        parent = symbol_table.must_find_concrete_class(Identifier("Parent"))

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))

        another_concrete = symbol_table.must_find_concrete_class(
            Identifier("AnotherConcrete")
        )

        self.assertTrue(concrete.is_subclass_of(cls=concrete))
        self.assertTrue(concrete.is_subclass_of(cls=parent))
        self.assertTrue(concrete.is_subclass_of(cls=grand_parent))
        self.assertFalse(concrete.is_subclass_of(cls=another_concrete))

    def test_common_ancestor_but_no_subclass(self) -> None:
        source = """\
class Parent:
    pass


class Concrete(Parent):
    pass


class AnotherConcrete(Parent):
    pass


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)

        assert symbol_table is not None

        parent = symbol_table.must_find_concrete_class(Identifier("Parent"))

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))

        another_concrete = symbol_table.must_find_concrete_class(
            Identifier("AnotherConcrete")
        )

        self.assertTrue(concrete.is_subclass_of(cls=concrete))
        self.assertTrue(concrete.is_subclass_of(cls=parent))
        self.assertFalse(concrete.is_subclass_of(cls=another_concrete))


class TestIsStructuralSubtypeOf(unittest.TestCase):
    def test_self(self) -> None:
        source = """\
class Concrete:
    x: int

    def __init__(self, x: int) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))

        self.assertTrue(concrete.is_structural_subtype_of(cls=concrete))

    def test_unrelated_classes_with_same_shape(self) -> None:
        source = """\
class Concrete:
    x: int
    y: str

    def __init__(self, x: int, y: str) -> None:
        self.x = x
        self.y = y


class Structurally_same:
    x: int
    y: str

    def __init__(self, x: int, y: str) -> None:
        self.x = x
        self.y = y


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        structurally_same = symbol_table.must_find_concrete_class(
            Identifier("Structurally_same")
        )

        self.assertTrue(structurally_same.is_structural_subtype_of(cls=concrete))
        self.assertTrue(concrete.is_structural_subtype_of(cls=structurally_same))

    def test_mismatch_in_property_type(self) -> None:
        source = """\
class Concrete:
    x: int

    def __init__(self, x: int) -> None:
        self.x = x


class Different_type:
    x: str

    def __init__(self, x: str) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        different_type = symbol_table.must_find_concrete_class(
            Identifier("Different_type")
        )

        self.assertFalse(different_type.is_structural_subtype_of(cls=concrete))
        self.assertFalse(concrete.is_structural_subtype_of(cls=different_type))

    def test_missing_property(self) -> None:
        source = """\
class Concrete:
    x: int
    y: str

    def __init__(self, x: int, y: str) -> None:
        self.x = x
        self.y = y


class Missing_property:
    x: int

    def __init__(self, x: int) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        missing_property = symbol_table.must_find_concrete_class(
            Identifier("Missing_property")
        )

        # ``Missing_property`` lacks ``y``, so it can not stand in for ``Concrete``.
        self.assertFalse(missing_property.is_structural_subtype_of(cls=concrete))

        # ``Concrete`` has all the properties of ``Missing_property`` (and more).
        self.assertTrue(concrete.is_structural_subtype_of(cls=missing_property))

    def test_nominal_subclass_is_not_automatically_a_structural_subtype(
        self,
    ) -> None:
        source = """\
class Parent:
    x: int

    def __init__(self, x: int) -> None:
        self.x = x


class Concrete(Parent):
    y: str

    def __init__(self, x: int, y: str) -> None:
        Parent.__init__(self, x)
        self.y = y


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        parent = symbol_table.must_find_concrete_class(Identifier("Parent"))
        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))

        self.assertTrue(concrete.is_subclass_of(cls=parent))
        self.assertTrue(concrete.is_structural_subtype_of(cls=parent))
        self.assertFalse(parent.is_structural_subtype_of(cls=concrete))

    def test_matching_primitive_type_but_different_constrained_primitive(
        self,
    ) -> None:
        source = """\
@invariant(lambda self: len(self) > 0, "Non-empty")
class Constrained_str_a(str):
    pass


@invariant(lambda self: len(self) < 100, "Not too long")
class Constrained_str_b(str):
    pass


class Concrete:
    x: Constrained_str_a

    def __init__(self, x: Constrained_str_a) -> None:
        self.x = x


class Different_constrained_primitive:
    x: Constrained_str_b

    def __init__(self, x: Constrained_str_b) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        different_constrained_primitive = symbol_table.must_find_concrete_class(
            Identifier("Different_constrained_primitive")
        )

        # Even though both properties are ``str`` at the primitive level, the
        # constrained primitives ``Constrained_str_a`` and ``Constrained_str_b``
        # are distinct our-types, so the classes are not structural subtypes of
        # one another.
        self.assertFalse(
            different_constrained_primitive.is_structural_subtype_of(cls=concrete)
        )
        self.assertFalse(
            concrete.is_structural_subtype_of(cls=different_constrained_primitive)
        )

    def test_constrained_primitive_is_not_substitutable_for_plain_primitive(
        self,
    ) -> None:
        source = """\
@invariant(lambda self: len(self) > 0, "Non-empty")
class Constrained_str(str):
    pass


class Concrete:
    x: str

    def __init__(self, x: str) -> None:
        self.x = x


class With_constrained_primitive:
    x: Constrained_str

    def __init__(self, x: Constrained_str) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        with_constrained_primitive = symbol_table.must_find_concrete_class(
            Identifier("With_constrained_primitive")
        )

        # NOTE (mristin):
        # We enforce invariance, not contra-variance.
        self.assertFalse(
            with_constrained_primitive.is_structural_subtype_of(cls=concrete)
        )
        self.assertFalse(
            concrete.is_structural_subtype_of(cls=with_constrained_primitive)
        )

    def test_different_list_items(self) -> None:
        source = """\
class Concrete:
    x: List[int]

    def __init__(self, x: List[int]) -> None:
        self.x = x


class Different_list_items:
    x: List[str]

    def __init__(self, x: List[str]) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        different_list_items = symbol_table.must_find_concrete_class(
            Identifier("Different_list_items")
        )

        # NOTE (mristin):
        # We enforce invariance, not contra-variance.
        self.assertFalse(different_list_items.is_structural_subtype_of(cls=concrete))
        self.assertFalse(concrete.is_structural_subtype_of(cls=different_list_items))

    def test_matching_list_items(self) -> None:
        source = """\
class Concrete:
    x: List[int]

    def __init__(self, x: List[int]) -> None:
        self.x = x


class Structurally_same:
    x: List[int]

    def __init__(self, x: List[int]) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        structurally_same = symbol_table.must_find_concrete_class(
            Identifier("Structurally_same")
        )

        self.assertTrue(structurally_same.is_structural_subtype_of(cls=concrete))
        self.assertTrue(concrete.is_structural_subtype_of(cls=structurally_same))

    def test_optional_property_is_invariant(self) -> None:
        source = """\
class Required:
    x: int

    def __init__(self, x: int) -> None:
        self.x = x


class Optional_property:
    x: Optional[int]

    def __init__(self, x: Optional[int] = None) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        required = symbol_table.must_find_concrete_class(Identifier("Required"))
        optional_property = symbol_table.must_find_concrete_class(
            Identifier("Optional_property")
        )

        # Optionality is invariant: a required property is not structurally the
        # same as an optional one, in either direction.
        self.assertFalse(required.is_structural_subtype_of(cls=optional_property))
        self.assertFalse(optional_property.is_structural_subtype_of(cls=required))

    def test_required_property_is_not_substitutable_for_optional(self) -> None:
        source = """\
class Required:
    x: int

    def __init__(self, x: int) -> None:
        self.x = x


class Optional_property:
    x: Optional[int]

    def __init__(self, x: Optional[int] = None) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        required = symbol_table.must_find_concrete_class(Identifier("Required"))
        optional_property = symbol_table.must_find_concrete_class(
            Identifier("Optional_property")
        )

        # Even though a value is always present for ``Required.x``, structural
        # subtyping is invariant, so a required property does *not* satisfy
        # an optional one -- ``Optional[int]`` and ``int`` are distinct type
        # annotations.
        self.assertFalse(required.is_structural_subtype_of(cls=optional_property))

    def test_matching_optional_property(self) -> None:
        source = """\
class Concrete:
    x: Optional[int]

    def __init__(self, x: Optional[int] = None) -> None:
        self.x = x


class Structurally_same:
    x: Optional[int]

    def __init__(self, x: Optional[int] = None) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        structurally_same = symbol_table.must_find_concrete_class(
            Identifier("Structurally_same")
        )

        self.assertTrue(structurally_same.is_structural_subtype_of(cls=concrete))
        self.assertTrue(concrete.is_structural_subtype_of(cls=structurally_same))

    def test_optional_list_with_different_items_is_not_a_subtype(self) -> None:
        source = """\
class Concrete:
    x: Optional[List[int]]

    def __init__(self, x: Optional[List[int]] = None) -> None:
        self.x = x


class Different_list_items:
    x: Optional[List[str]]

    def __init__(self, x: Optional[List[str]] = None) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        concrete = symbol_table.must_find_concrete_class(Identifier("Concrete"))
        different_list_items = symbol_table.must_find_concrete_class(
            Identifier("Different_list_items")
        )

        self.assertFalse(different_list_items.is_structural_subtype_of(cls=concrete))
        self.assertFalse(concrete.is_structural_subtype_of(cls=different_list_items))


class TestMustFindConstant(unittest.TestCase):
    def test_empty(self) -> None:
        source = """\
__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        with self.assertRaises(KeyError):
            _ = symbol_table.must_find_constant(Identifier("Something"))

    def test_constant(self) -> None:
        source = """\
Something: int = constant_int(value=1984)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        result = symbol_table.must_find_constant(Identifier("Something"))
        assert isinstance(result, intermediate.Constant)

    def test_constant_primitive(self) -> None:
        source = """\
Something: int = constant_int(value=1984)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        result = symbol_table.must_find_constant_primitive(Identifier("Something"))
        assert isinstance(result, intermediate.ConstantPrimitive)

        with self.assertRaises(TypeError):
            _ = symbol_table.must_find_constant_set_of_primitives(
                Identifier("Something")
            )

        with self.assertRaises(TypeError):
            _ = symbol_table.must_find_constant_set_of_enumeration_literals(
                Identifier("Something")
            )

    def test_constant_set_of_primitives(self) -> None:
        source = """\
Something: Set[str] = constant_set(
    values=["hello", "world"]
)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
        """
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        result = symbol_table.must_find_constant_set_of_primitives(
            Identifier("Something")
        )
        assert isinstance(result, intermediate.ConstantSetOfPrimitives)

        with self.assertRaises(TypeError):
            _ = symbol_table.must_find_constant_primitive(Identifier("Something"))

        with self.assertRaises(TypeError):
            _ = symbol_table.must_find_constant_set_of_enumeration_literals(
                Identifier("Something")
            )

    def test_constant_set_of_enumeration_literals(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"
    Another_literal = "ANOTHER-LITERAL"
    Yet_another_literal = "YET-ANOTHER-LITERAL"


Something: Set[SomeEnum] = constant_set(
    values=[SomeEnum.Some_literal, SomeEnum.Another_literal]
)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
        """
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        result = symbol_table.must_find_constant_set_of_enumeration_literals(
            Identifier("Something")
        )
        assert isinstance(result, intermediate.ConstantSetOfEnumerationLiterals)

        with self.assertRaises(TypeError):
            _ = symbol_table.must_find_constant_primitive(Identifier("Something"))

        with self.assertRaises(TypeError):
            _ = symbol_table.must_find_constant_set_of_primitives(
                Identifier("Something")
            )


class TestIsEnumerationLiteralOf(unittest.TestCase):
    def test_enumeration_literal_in_enumeration(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"
    Another_literal = "ANOTHER-LITERAL"

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("SomeEnum"))
        some_literal = some_enum.literals_by_name["Some_literal"]
        another_literal = some_enum.literals_by_name["Another_literal"]

        self.assertTrue(
            symbol_table.is_enumeration_literal_of(
                literal=some_literal,
                enumeration_or_constant_set_name=Identifier("SomeEnum"),
            )
        )
        self.assertTrue(
            symbol_table.is_enumeration_literal_of(
                literal=another_literal,
                enumeration_or_constant_set_name=Identifier("SomeEnum"),
            )
        )

    def test_enumeration_literal_not_in_different_enumeration(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"

class AnotherEnum(Enum):
    Different_literal = "DIFFERENT-LITERAL"

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("SomeEnum"))
        another_enum = symbol_table.must_find_enumeration(Identifier("AnotherEnum"))

        some_literal = some_enum.literals_by_name["Some_literal"]
        different_literal = another_enum.literals_by_name["Different_literal"]

        self.assertFalse(
            symbol_table.is_enumeration_literal_of(
                literal=some_literal,
                enumeration_or_constant_set_name=Identifier("AnotherEnum"),
            )
        )
        self.assertFalse(
            symbol_table.is_enumeration_literal_of(
                literal=different_literal,
                enumeration_or_constant_set_name=Identifier("SomeEnum"),
            )
        )

    def test_enumeration_literal_in_constant_set(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"
    Another_literal = "ANOTHER-LITERAL"
    Yet_another_literal = "YET-ANOTHER-LITERAL"

SomeSet: Set[SomeEnum] = constant_set(
    values=[SomeEnum.Some_literal, SomeEnum.Another_literal]
)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("SomeEnum"))
        some_literal = some_enum.literals_by_name["Some_literal"]
        another_literal = some_enum.literals_by_name["Another_literal"]
        yet_another_literal = some_enum.literals_by_name["Yet_another_literal"]

        # NOTE (mristin):
        # We check here for membership.
        self.assertTrue(
            symbol_table.is_enumeration_literal_of(
                literal=some_literal,
                enumeration_or_constant_set_name=Identifier("SomeSet"),
            )
        )
        self.assertTrue(
            symbol_table.is_enumeration_literal_of(
                literal=another_literal,
                enumeration_or_constant_set_name=Identifier("SomeSet"),
            )
        )

        # NOTE (mristin):
        # We check here for out-of-membership.
        self.assertFalse(
            symbol_table.is_enumeration_literal_of(
                literal=yet_another_literal,
                enumeration_or_constant_set_name=Identifier("SomeSet"),
            )
        )

    def test_type_error_for_concrete_class(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"

class SomeClass:
    pass

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("SomeEnum"))
        some_literal = some_enum.literals_by_name["Some_literal"]

        with self.assertRaises(TypeError):
            _ = symbol_table.is_enumeration_literal_of(
                literal=some_literal,
                enumeration_or_constant_set_name=Identifier("SomeClass"),
            )

    def test_type_error_for_constant_primitive(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"

SomeConstant: int = constant_int(value=42)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("SomeEnum"))
        some_literal = some_enum.literals_by_name["Some_literal"]

        with self.assertRaises(TypeError):
            _ = symbol_table.is_enumeration_literal_of(
                literal=some_literal,
                enumeration_or_constant_set_name=Identifier("SomeConstant"),
            )

    def test_type_error_for_constant_set_of_primitives(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"

SomeSet: Set[str] = constant_set(
    values=["hello", "world"]
)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("SomeEnum"))
        some_literal = some_enum.literals_by_name["Some_literal"]

        # Test that TypeError is raised when name refers to a constant set of primitives
        with self.assertRaises(TypeError):
            _ = symbol_table.is_enumeration_literal_of(
                literal=some_literal,
                enumeration_or_constant_set_name=Identifier("SomeSet"),
            )


class TestLiteralValueSet(unittest.TestCase):
    def test_enumeration(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"
    Another_literal = "ANOTHER-LITERAL"
    Yet_another_literal = "YET-ANOTHER-LITERAL"

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_enum = symbol_table.must_find_enumeration(Identifier("SomeEnum"))

        expected_literal_values = frozenset(
            ["SOME-LITERAL", "ANOTHER-LITERAL", "YET-ANOTHER-LITERAL"]
        )

        self.assertEqual(expected_literal_values, some_enum.literal_value_set)

    def test_constant_set_of_primitives(self) -> None:
        source = """\
SomeSet: Set[str] = constant_set(
    values=["hello", "world", "test"]
)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_set = symbol_table.must_find_constant_set_of_primitives(
            Identifier("SomeSet")
        )

        expected_literal_values = frozenset(["hello", "world", "test"])

        self.assertEqual(expected_literal_values, some_set.literal_value_set)

    def test_constant_set_of_enumeration_literals(self) -> None:
        source = """\
class SomeEnum(Enum):
    Some_literal = "SOME-LITERAL"
    Another_literal = "ANOTHER-LITERAL"
    Yet_another_literal = "YET-ANOTHER-LITERAL"

SomeSet: Set[SomeEnum] = constant_set(
    values=[SomeEnum.Some_literal, SomeEnum.Another_literal]
)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        some_set = symbol_table.must_find_constant_set_of_enumeration_literals(
            Identifier("SomeSet")
        )

        expected_literal_values = frozenset(["SOME-LITERAL", "ANOTHER-LITERAL"])

        self.assertEqual(expected_literal_values, some_set.literal_value_set)


if __name__ == "__main__":
    unittest.main()
