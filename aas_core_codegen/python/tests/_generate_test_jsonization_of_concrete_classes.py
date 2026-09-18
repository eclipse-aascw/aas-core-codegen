"""Generate code to test the JSON de/serialization of concrete classes."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.python import common as python_common, naming as python_naming
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


def _generate_test_case(symbol_table: intermediate.SymbolTable) -> Stripped:
    test_methods = []  # type: List[Stripped]

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

{II}instance = aas_jsonization.{from_jsonable}(
{III}original_jsonable
{II})

{II}another_jsonable = aas_jsonization.to_jsonable(instance)

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


def _generate_serialization_failure_test_case(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the tests that a number unrepresentable in JSON is refused."""
    test_methods = []  # type: List[Stripped]

    for numeric_place in intermediate.numeric_places(symbol_table):
        if numeric_place.a_type is intermediate.PrimitiveType.FLOAT:
            what = "non_finite"
            zero_literal = "0.0"
            values_literal = "[math.inf, -math.inf, math.nan]"
        else:
            what = "out_of_range"
            zero_literal = "0"
            values_literal = "[9007199254740992, -9007199254740992]"

        prop_name = python_naming.property_name(numeric_place.prop.name)

        if numeric_place.index is None:
            mutation = Stripped(f"instance.{prop_name} = value")
            expected_path = f".{numeric_place.prop.name}"
        elif numeric_place.in_list:
            # NOTE (mristin):
            # The value goes to the position indicated by the numeric place so
            # that a serializer which always reports the index 0 does not pass.
            items_joined = ", ".join(
                "value" if i == numeric_place.index else zero_literal
                for i in range(numeric_place.index + 1)
            )

            mutation = Stripped(f"instance.{prop_name} = [{items_joined}]")
            expected_path = f".{numeric_place.prop.name}[{numeric_place.index}]"
        else:
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

            mutation = Stripped(f"instance.{prop_name} = ({items_joined})")
            expected_path = f".{numeric_place.prop.name}[{numeric_place.index}]"

        model_type = naming.json_model_type(numeric_place.cls.name)

        from_jsonable = python_naming.function_name(
            Identifier(f"{numeric_place.cls.name}_from_jsonable")
        )

        test_method_name = python_naming.method_name(
            Identifier(
                f"test_{numeric_place.cls.name}_{numeric_place.prop.name}_{what}"
            )
        )

        test_methods.append(
            Stripped(
                f"""\
def {test_method_name}(self) -> None:
{I}for value in {values_literal}:
{II}instance = aas_jsonization.{from_jsonable}(
{III}_load_the_first_expected({model_type!r})
{II})

{II}{indent_but_first_line(mutation, II)}

{II}with self.assertRaises(
{III}aas_jsonization.SerializationException
{II}) as context_manager:
{III}aas_jsonization.to_jsonable(instance)

{II}self.assertEqual(
{III}{expected_path!r},
{III}context_manager.exception.path
{II})"""
            )
        )

    if len(test_methods) == 0:
        return Stripped("")

    body = "\n\n".join(test_methods)

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


class TestSerializationFailures(unittest.TestCase):
{I}{indent_but_first_line(body, I)}"""
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
    # Only the tests of the serialization failures need the non-finite floats and
    # the type of a JSON-able loaded from a file.
    extra_imports = (
        "\nimport math\nfrom typing import Any" if serialization_failures != "" else ""
    )

    blocks = [
        Stripped(
            '''\
"""Test JSON de/serialization of concrete classes."""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped(
            f"""\
import json{extra_imports}
import unittest"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.jsonization as aas_jsonization"""
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
