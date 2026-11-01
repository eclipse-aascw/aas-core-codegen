"""Generate code to test the JSON de/serialization of concrete classes."""

import io
from typing import List, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.python import common as python_common, naming as python_naming
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_test_case(symbol_table: intermediate.SymbolTable) -> Stripped:
    test_methods: List[Stripped] = []

    for cls in symbol_table.concrete_classes:
        test_method_name = python_naming.method_name(Identifier(f"test_{cls.name}"))

        from_jsonable = python_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        model_type = naming.json_model_type(cls.name)

        test_methods.append(
            Stripped(
                f"""\
def {test_method_name}(self) -> None:
{I}for path in sorted(
{II}(
{III}tests.common.TEST_DATA_DIR
{III}/ "Json"
{III}/ "Expected"
{III}/ {model_type!r}
{II}).glob("**/*.json")
{I}):
{II}with path.open("rt") as fid:
{III}original_jsonable = json.load(fid)

{II}instance = our_jsonization.{from_jsonable}(
{III}original_jsonable
{II})

{II}another_jsonable = our_jsonization.to_jsonable(instance)

{II}mismatches = tests.common_jsonization.check_equal(
{III}original_jsonable,
{III}another_jsonable
{II})
{II}self.assertListEqual([], list(map(str, mismatches)))"""
            ),
        )

    body = (
        "\n\n".join(test_methods)
        if len(test_methods) > 0
        else """\
# There are no concrete classes.
pass"""
    )

    return Stripped(
        f"""\
class TestRoundTrips(unittest.TestCase):
{I}{indent_but_first_line(body, I)}"""
    )


def numeric_place_mutation(
    numeric_place: intermediate.NumericPlace, zero_literal: str
) -> Tuple[Stripped, str]:
    """
    Generate the statement which puts ``value`` at the ``numeric_place`` of ``instance``.

    Return the statement and the subscript, if any, which follows the property in
    the path to the value.

    :param numeric_place: where the value is put
    :param zero_literal: to fill the items before the value in a list
    :return: statement, and subscript of the path (empty if none)
    """
    prop_name = python_naming.property_name(numeric_place.prop.name)

    if numeric_place.index is None:
        return Stripped(f"instance.{prop_name} = value"), ""

    if numeric_place.in_list:
        # NOTE (mristin):
        # The value goes to the position indicated by the numeric place so
        # that a serializer which always reports the index 0 does not pass.
        items_joined = ", ".join(
            "value" if i == numeric_place.index else zero_literal
            for i in range(numeric_place.index + 1)
        )

        return (
            Stripped(f"instance.{prop_name} = [{items_joined}]"),
            f"[{numeric_place.index}]",
        )

    tuple_type_anno = numeric_place.prop.type_annotation
    assert isinstance(tuple_type_anno, intermediate.TupleTypeAnnotation), (
        f"Expected a tuple at the numeric place of "
        f"{numeric_place.cls.name}.{numeric_place.prop.name}, "
        f"but got: {tuple_type_anno}"
    )

    # NOTE (mristin):
    # A tuple is immutable, so it has to be rebuilt around the value.
    items_joined = ", ".join(
        "value" if i == numeric_place.index else f"instance.{prop_name}[{i}]"
        for i in range(len(tuple_type_anno.items))
    )

    return (
        Stripped(f"instance.{prop_name} = ({items_joined})"),
        f"[{numeric_place.index}]",
    )


def _generate_serialization_failure_test_case(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """
    Generate the tests that a number unrepresentable in JSON is refused.

    The integers outside of the safe integer range are tested together with
    the verification and the XML serialization in ``test_safe_integers.py``, so
    only the non-finite floats are tested here. The JSON de-serialization of
    the integers is tested here, though.
    """
    test_methods: List[Stripped] = []
    int_parsing_methods: List[Stripped] = []

    for numeric_place in intermediate.numeric_places(symbol_table):
        prop_name = python_naming.property_name(numeric_place.prop.name)

        model_type = naming.json_model_type(numeric_place.cls.name)

        from_jsonable = python_naming.function_name(
            Identifier(f"{numeric_place.cls.name}_from_jsonable")
        )

        if numeric_place.a_type is intermediate.PrimitiveType.FLOAT:
            mutation, subscript = numeric_place_mutation(
                numeric_place=numeric_place, zero_literal="0.0"
            )
            expected_path = f".{numeric_place.prop.name}{subscript}"

            test_method_name = python_naming.method_name(
                Identifier(
                    f"test_{numeric_place.cls.name}_{numeric_place.prop.name}"
                    f"_non_finite"
                )
            )

            test_methods.append(
                Stripped(
                    f"""\
def {test_method_name}(self) -> None:
{I}for value in [math.inf, -math.inf, math.nan]:
{II}instance = our_jsonization.{from_jsonable}(
{III}_load_the_first_expected({model_type!r})
{II})

{II}{indent_but_first_line(mutation, II)}

{II}with self.assertRaises(
{III}our_jsonization.SerializationException
{II}) as context_manager:
{III}our_jsonization.to_jsonable(instance)

{II}self.assertEqual(
{III}{expected_path!r},
{III}context_manager.exception.path
{II})"""
                )
            )

        if (
            numeric_place.a_type is intermediate.PrimitiveType.INT
            and numeric_place.index is None
        ):
            parsing_method_name = python_naming.method_name(
                Identifier(f"test_{numeric_place.cls.name}_{numeric_place.prop.name}")
            )

            json_name_literal = python_common.string_literal(
                numeric_place.prop.json_name
            )

            int_parsing_methods.append(
                Stripped(
                    f"""\
def {parsing_method_name}(self) -> None:
{I}jsonable = _load_the_first_expected({model_type!r})

{I}# NOTE (mristin):
{I}# JSON has a single number type, so a whole float is an integer.
{I}jsonable[{json_name_literal}] = 5.0
{I}instance = our_jsonization.{from_jsonable}(jsonable)
{I}self.assertIs(int, type(instance.{prop_name}))
{I}self.assertEqual(5, instance.{prop_name})

{I}for value, expected_cause in [
{II}("5", "Expected an integer, but got: <class 'str'>"),
{II}(
{III}1.5,
{III}"Expected an integer, but got 1.5, which is not a whole number"
{II}),
{II}(
{III}9007199254740992,
{III}(
{IIII}"Expected an integer, but got 9007199254740992, "
{IIII}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]"
{III})
{II}),
{II}(
{III}-9007199254740992.0,
{III}(
{IIII}"Expected an integer, but got -9007199254740992, "
{IIII}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]"
{III})
{II})
{I}]:
{II}jsonable[{json_name_literal}] = value

{II}with self.assertRaises(
{III}our_jsonization.DeserializationException
{II}) as context_manager:
{III}our_jsonization.{from_jsonable}(jsonable)

{II}self.assertEqual(
{III}expected_cause,
{III}context_manager.exception.cause
{II})"""
                )
            )

    if len(test_methods) == 0 and len(int_parsing_methods) == 0:
        return Stripped("")

    blocks: List[str] = []

    if len(test_methods) > 0:
        body = "\n\n".join(test_methods)
        blocks.append(
            f"""\
class TestSerializationFailures(unittest.TestCase):
{I}{indent_but_first_line(body, I)}"""
        )

    if len(int_parsing_methods) > 0:
        int_parsing_body = "\n\n".join(int_parsing_methods)
        blocks.append(
            f"""\
class TestDeserializationOfIntegers(unittest.TestCase):
{I}{indent_but_first_line(int_parsing_body, I)}"""
        )

    blocks_joined = "\n\n\n".join(blocks)

    return Stripped(
        f"""\
def _load_the_first_expected(model_type: str) -> Any:
{I}\"\"\"Load the first recorded example of the ``model_type``.\"\"\"
{I}paths = sorted(
{II}(
{III}tests.common.TEST_DATA_DIR
{III}/ "Json"
{III}/ "Expected"
{III}/ model_type
{II}).glob("**/*.json")
{I})

{I}assert len(paths) > 0, (
{II}f"Expected at least one recorded example of {{model_type}}, but got none"
{I})

{I}with paths[0].open("rt") as fid:
{II}return json.load(fid)


{blocks_joined}"""
    )


@ensure(
    lambda result: result.endswith("\n"),
    "Trailing newline mandatory for valid end-of-files",
)
def generate(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> str:
    """
    Generate code to test the JSON de/serialization of concrete classes.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    serialization_failures = _generate_serialization_failure_test_case(
        symbol_table=symbol_table
    )

    # NOTE (mristin):
    # Only the tests of the serialization failures need the type of a JSON-able
    # loaded from a file, and only those over the floats need the non-finite ones.
    extra_imports = ""
    if serialization_failures != "":
        if any(
            numeric_place.a_type is intermediate.PrimitiveType.FLOAT
            for numeric_place in intermediate.numeric_places(symbol_table)
        ):
            extra_imports = "\nimport math"

        extra_imports += "\nfrom typing import Any"

    blocks = [
        Stripped(
            '''\
"""Test JSON de/serialization of concrete classes."""'''
        ),
        python_common.WARNING,
        Stripped(
            f"""\
import json{extra_imports}
import unittest"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.jsonization as our_jsonization"""
        ),
        Stripped(
            """\
import tests.common
import tests.common_jsonization"""
        ),
        _generate_test_case(symbol_table=symbol_table),
    ]

    if serialization_failures != "":
        blocks.append(serialization_failures)

    blocks.extend(
        [
            Stripped(
                f"""\
if __name__ == "__main__":
{I}unittest.main()"""
            ),
            python_common.WARNING,
        ]
    )

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue()
