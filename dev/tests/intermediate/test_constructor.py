# pylint: disable=missing-docstring

import re
import unittest
from typing import Tuple, Optional, Sequence

from icontract import ensure

import tests.common
from aas_core_codegen import parse
from aas_core_codegen.common import Error
from aas_core_codegen.intermediate import construction


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def understand_constructor_table(
    source: str,
) -> Tuple[Optional[construction.ConstructorTable], Optional[Error]]:
    """Parse the source and try to understand all the constructors."""
    atok, parse_exception = parse.source_to_atok(source=source)
    assert atok is not None
    assert parse_exception is None, f"{parse_exception=}"

    import_errors = parse.check_expected_imports(atok=atok)
    assert len(import_errors) == 0

    parsed_symbol_table, error = parse.atok_to_symbol_table(atok=atok)
    assert error is None, f"{tests.common.most_underlying_messages(error)}"
    assert parsed_symbol_table is not None

    either = construction.understand_all(
        parsed_symbol_table=parsed_symbol_table, atok=atok
    )

    return either


def must_find_item_for(
    constructor_table: construction.ConstructorTable, name: str
) -> Tuple[parse.Class, Sequence[construction.Statement]]:
    """
    Find the constructor statements for the class given with ``identifier``.

    :raise: :py:class:`KeyError` if not found in the table
    """
    for cls, statements in constructor_table.entries():
        if cls.name == name:
            return cls, statements

    raise KeyError(
        f"Could not find_our_type the constructor statements for the class: {name}"
    )


class Test_empty_ok(unittest.TestCase):
    def test_no_constructor(self) -> None:
        source = """\
class Something:
    pass

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        constructor_table, error = understand_constructor_table(source=source)
        assert error is None, tests.common.most_underlying_messages(error)
        assert constructor_table is not None

        self.assertEqual(1, len(constructor_table.entries()))

        cls, statements = must_find_item_for(constructor_table, "Something")
        self.assertEqual("Something", cls.name)
        self.assertEqual(0, len(statements))

    def test_pass(self) -> None:
        source = """\
class Something:
    def __init__(self) -> None:
        pass

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        constructor_table, error = understand_constructor_table(source=source)
        assert error is None, tests.common.most_underlying_messages(error)
        assert constructor_table is not None

        self.assertEqual(1, len(constructor_table.entries()))

        _, statements = must_find_item_for(constructor_table, "Something")
        self.assertEqual(0, len(statements))


class Test_call_to_super_constructor_ok(unittest.TestCase):
    def test_without_arguments(self) -> None:
        source = """\
@abstract
class Parent:
    def __init__(self) -> None:
        pass

class Something(Parent):
    def __init__(self) -> None:
        Parent.__init__(self)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        constructor_table, error = understand_constructor_table(source=source)
        assert error is None, tests.common.most_underlying_messages(error)
        assert constructor_table is not None

        self.assertEqual(2, len(constructor_table.entries()))

        _, statements = must_find_item_for(constructor_table, "Something")
        self.assertEqual(1, len(statements))

        statement = statements[0]
        assert isinstance(statement, construction.CallSuperConstructor)
        self.assertEqual("Parent", statement.super_name)

    def test_with_arguments(self) -> None:
        source = """\
@abstract
class Parent:
    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something(Parent):
    def __init__(self, a: int, b: int) -> None:
        Parent.__init__(self, a, b)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        constructor_table, error = understand_constructor_table(source=source)
        assert error is None, tests.common.most_underlying_messages(error)
        assert constructor_table is not None

        self.assertEqual(2, len(constructor_table.entries()))

        _, statements = must_find_item_for(constructor_table, "Something")
        self.assertEqual(1, len(statements))

        statement = statements[0]
        assert isinstance(statement, construction.CallSuperConstructor)
        self.assertEqual("Parent", statement.super_name)


class Test_assign_property_ok(unittest.TestCase):
    def test_argument_assignment(self) -> None:
        source = """\
class Something:
    x: int

    def __init__(self, x: int) -> None:
        self.x = x

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        constructor_table, error = understand_constructor_table(source=source)
        assert error is None, tests.common.most_underlying_messages(error)
        assert constructor_table is not None

        _, statements = must_find_item_for(constructor_table, "Something")
        self.assertEqual(1, len(statements))

        statement = statements[0]
        assert isinstance(statement, construction.AssignArgument)
        self.assertEqual("x", statement.name)


class Test_assign_fail(unittest.TestCase):
    def test_multiple_targets_in_assignment(self) -> None:
        source = """\
class Something:
    a: int
    b: int

    def __init__(self, a: int) -> None:
        self.a = self.b = a

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected only a single target for property assignment, but got 2 targets",
            tests.common.most_underlying_messages(error),
        )

    def test_tuple_in_assignment_targets(self) -> None:
        source = """\
class Something:
    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        self.a, self.b = a, b

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected a property as the target of an assignment, "
            "but got: self.a, self.b",
            tests.common.most_underlying_messages(error),
        )

    def test_variable_instead_of_property_assignment(self) -> None:
        source = """\
class Something:
    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        x = a

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected a property as the target of an assignment, but got: x",
            tests.common.most_underlying_messages(error),
        )

    def test_assignment_to_undefined_property(self) -> None:
        source = """\
class Something:
    def __init__(self, a: int) -> None:
        self.a = a

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "The property has not been previously defined in the class 'Something': a",
            tests.common.most_underlying_messages(error),
        )

    def test_assignment_value_is_not_a_name(self) -> None:
        source = """\
class Something:
    a: int

    def __init__(self, a: int) -> None:
        self.a = a + 100

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        error_str = tests.common.most_underlying_messages(error)
        error_str = re.sub(r"Assign\(.*\); ", "Assign(...); ", error_str)

        self.assertEqual(
            "The handling of the constructor statement has not been implemented: "
            "Assign(...); please notify the developers if you really need this feature",
            error_str,
        )

    def test_argument_and_property_name_differ(self) -> None:
        source = """\
class Something:
    a: int

    def __init__(self, b: int) -> None:
        self.a = b


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected the property a to be assigned exactly the argument "
            "with the same name, but got: b",
            tests.common.most_underlying_messages(error),
        )


class Test_call_to_super_constructor_fail(unittest.TestCase):
    def test_super_class_not_a_name(self) -> None:
        source = '''\
@abstract
class Parent:
    """Represent something abstract."""

    a: int
    b: int

    @require(lambda a: a > 0)
    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something(Parent):
    """Represent something concrete."""

    def __init__(self, a: int, b: int) -> None:
        super().__init__(self, a, b)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected a super class as a name for a call to super ``__init__``, "
            "but got: super()",
            tests.common.most_underlying_messages(error),
        )

    def test_passed_double_start_keyword_argument(self) -> None:
        source = '''\
@abstract
class Parent(DBC):
    """Represent something abstract."""

    a: int
    b: int

    @require(lambda a: a > 0)
    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something(DBC, Parent):
    """Represent something concrete."""

    def __init__(self, a: int, b: int) -> None:
        Parent.__init__(self, **{'a': a, 'b': b})

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected a call to a super ``__init__`` to provide only "
            "explicit keyword arguments, but got a double-star keyword argument",
            tests.common.most_underlying_messages(error),
        )

    def test_calling_constructor_from_a_non_super_class(self) -> None:
        source = """\
class Unrelated:
    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something:
    def __init__(self, a: int, b: int) -> None:
        Unrelated.__init__(self, a=a, b=b)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected a super class in the call to a super ``__init__``, "
            "but Something does not inherit from Unrelated",
            tests.common.most_underlying_messages(error),
        )

    def test_super_class_has_no_init(self) -> None:
        source = """\
@abstract
class Parent:
    pass

class Something(Parent):

    def __init__(self, a: int, b: int) -> None:
        Parent.__init__(self)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "The super class Parent does not define a ``__init__``",
            tests.common.most_underlying_messages(error),
        )

    def test_positional_argument_to_super_init_transformed(self) -> None:
        source = """\
@abstract
class Parent(DBC):
    a: int

    def __init__(self, a: int) -> None:
        self.a = a

class Something(DBC, Parent):
    def __init__(self, a: int) -> None:
        Parent.__init__(self, a + 100)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected only names in the arguments to super ``__init__``, "
            "but got: a + 100",
            tests.common.most_underlying_messages(error),
        )

    def test_keyword_argument_to_super_init_transformed(self) -> None:
        source = """\
@abstract
class Parent(DBC):
    a: int

    def __init__(self, a: int) -> None:
        self.a = a

class Something(DBC, Parent):
    def __init__(self, a: int) -> None:
        Parent.__init__(self, a=a + 100)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected only names in the arguments to super ``__init__``, "
            "but got: a + 100",
            tests.common.most_underlying_messages(error),
        )

    def test_too_many_positional_arguments(self) -> None:
        source = """\
@abstract
class Parent:
    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something(Parent):
    def __init__(self, a: int, b: int, c: int) -> None:
        Parent.__init__(self, a, b, c)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "The ``Parent.__init__`` expected 3 argument(s), "
            "but the call provides 4 positional argument(s)",
            tests.common.most_underlying_messages(error),
        )

    def test_unexpected_keyword_arguments_supplied_to_super_init(self) -> None:
        source = """\
@abstract
class Parent:
    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something(DBC, Parent):
    def __init__(self, a: int, b: int, c: int) -> None:
        Parent.__init__(self, a=a, b=b, c=c)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "The ``Parent.__init__`` does not expect the argument c",
            tests.common.most_underlying_messages(error),
        )

    def test_non_init_names_passed_to_super_init(self) -> None:
        source = '''\
@abstract
class Parent:
    """Represent something abstract."""

    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something(Parent):
    def __init__(self, a: int) -> None:
        Parent.__init__(self, a, b)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Expected all the arguments to ``Parent.__init__`` "
            "to be propagation of the original ``__init__`` arguments, "
            "but the name b is not an argument of ``Something.__init__``",
            tests.common.most_underlying_messages(error),
        )

    def test_arguments_not_passed_as_are(self) -> None:
        source = """\
@abstract
class Parent:
    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something(DBC, Parent):
    def __init__(self, a: int, y: int) -> None:
        Parent.__init__(self, a, b=y)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        # This behavior is necessary so that we can easily in-line super-constructors
        # and stack the contracts from the super classes.
        self.assertEqual(
            "Expected the arguments to super ``__init__`` to be passed with "
            "the same names, but the argument b is passed as the name y",
            tests.common.most_underlying_messages(error),
        )

    def test_missing_argument_to_super_init(self) -> None:
        source = """\
@abstract
class Parent:
    a: int
    b: int

    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

class Something(Parent):
    def __init__(self, a: int) -> None:
        Parent.__init__(self, a)

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "The call to ``Parent.__init__`` is missing one or more arguments: b",
            tests.common.most_underlying_messages(error),
        )


class Test_unexpected_statements(unittest.TestCase):
    def test_unexpected_call(self) -> None:
        source = """\
class Something:
    a: int

    def __init__(self, a: int) -> None:
        print("something")

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Unexpected call in the body of ``__init__``: print; "
            "only calls to super ``__init__``'s are expected",
            tests.common.most_underlying_messages(error),
        )

    def test_unexpected_expr(self) -> None:
        source = """\
class Something:
    a: int

    def __init__(self, a: int) -> None:
        1 + 2

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
"""

        _, error = understand_constructor_table(source=source)
        assert error is not None

        self.assertEqual(
            "Unexpected statement in the body of ``__init__``: 1 + 2; "
            "only calls to super ``__init__``'s and property assignments expected",
            tests.common.most_underlying_messages(error),
        )


if __name__ == "__main__":
    unittest.main()
