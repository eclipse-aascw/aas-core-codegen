"""Generate code to test that the integers are checked against the safe range."""

import io
from typing import List, Optional, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.python import common as python_common, naming as python_naming
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)
from aas_core_codegen.python.tests import (
    _generate_test_jsonization_of_concrete_classes as python_tests_jsonization,
)


def _generate_predicate_test_case(integers: bool, json_types: bool) -> Stripped:
    """Generate the tests of the predicate and of the messages of the common module."""
    methods: List[Stripped] = [
        Stripped(
            f"""\
def test_is_safe_integer(self) -> None:
{I}for value in [0, 2 ** 53 - 1, -(2 ** 53 - 1)]:
{II}self.assertTrue(our_common.is_safe_integer(value), f"for {{value}}")

{I}for value in [2 ** 53, -(2 ** 53), 10 ** 400]:
{II}self.assertFalse(our_common.is_safe_integer(value), f"for {{value}}")"""
        )
    ]

    if integers:
        methods.append(
            Stripped(
                f"""\
def test_unsafe_integer_message(self) -> None:
{I}self.assertEqual(
{II}"Expected an integer, but got 9007199254740992, "
{II}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]",
{II}our_common.unsafe_integer_message(2 ** 53)
{I})"""
            )
        )

    if json_types:
        methods.append(
            Stripped(
                f"""\
def test_unsafe_json_able_integer_message(self) -> None:
{I}self.assertEqual(
{II}"Expected a JSON-able value, but got the integer -9007199254740992, "
{II}"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]",
{II}our_common.unsafe_json_able_integer_message(-(2 ** 53))
{I})"""
            )
        )

    body = "\n\n".join(methods)

    return Stripped(
        f"""\
class TestPredicateAndMessages(unittest.TestCase):
{I}{indent_but_first_line(body, I)}"""
    )


def _generate_place_tests(
    cls: intermediate.ConcreteClass,
    prop: intermediate.Property,
    mutation: Stripped,
    subscript: str,
    cause_prefix: str,
) -> List[Stripped]:
    """
    Generate the tests which put a value from outside at a place of an instance.

    The unsafe values have to be reported with the same cause by the verification,
    the JSON serialization and the XML serialization, while the safe values have
    to pass all three.
    """
    model_type = naming.json_model_type(cls.name)
    from_jsonable = python_naming.function_name(Identifier(f"{cls.name}_from_jsonable"))
    prop_name = python_naming.property_name(prop.name)

    # NOTE (mristin):
    # The JSON serialization reports the path by the names of the properties in
    # the meta-model, while the verification and the XML serialization by
    # the Python names.
    json_path = f".{prop.name}{subscript}"
    python_path = f".{prop_name}{subscript}"

    test_name_prefix = f"test_{cls.name}_{prop.name}"

    return [
        Stripped(
            f"""\
def {python_naming.method_name(Identifier(f"{test_name_prefix}_unsafe"))}(self) -> None:
{I}for value in [2 ** 53, -(2 ** 53)]:
{II}instance = our_jsonization.{from_jsonable}(
{III}_load_the_first_expected({model_type!r})
{II})

{II}{indent_but_first_line(mutation, II)}

{II}expected_cause = (
{III}f"{cause_prefix}{{value}}, "
{III}f"which is outside the safe integer range [-2^53 + 1, 2^53 - 1]"
{II})

{II}self.assertIn(
{III}({python_path!r}, expected_cause),
{III}_paths_and_causes(our_verification.verify(instance))
{II})

{II}with self.assertRaises(
{III}our_jsonization.SerializationException
{II}) as json_context:
{III}our_jsonization.to_jsonable(instance)

{II}self.assertEqual(
{III}({json_path!r}, expected_cause),
{III}(json_context.exception.path, json_context.exception.cause)
{II})

{II}with self.assertRaises(
{III}our_xmlization.SerializationException
{II}) as xml_context:
{III}our_xmlization.to_str(instance)

{II}self.assertEqual(
{III}({python_path!r}, expected_cause),
{III}(xml_context.exception.path, xml_context.exception.cause)
{II})"""
        ),
        Stripped(
            f"""\
def {python_naming.method_name(Identifier(f"{test_name_prefix}_safe"))}(self) -> None:
{I}for value in [2 ** 53 - 1, -(2 ** 53 - 1)]:
{II}instance = our_jsonization.{from_jsonable}(
{III}_load_the_first_expected({model_type!r})
{II})

{II}{indent_but_first_line(mutation, II)}

{II}# NOTE (mristin):
{II}# The value might still violate an invariant, so we only check that
{II}# the range is not reported.
{II}self.assertListEqual(
{III}[],
{III}[
{IIII}(path, cause)
{IIII}for path, cause in _paths_and_causes(our_verification.verify(instance))
{IIII}if "safe integer range" in cause
{III}]
{II})

{II}our_jsonization.to_jsonable(instance)
{II}our_xmlization.to_str(instance)"""
        ),
    ]


def _json_able_mutation(
    prop: intermediate.Property,
) -> Optional[Tuple[Stripped, str]]:
    """
    Generate the statement which nests ``value`` in the JSON-able ``prop``.

    Return the statement and the subscript which follows the property in the path,
    or None if the property is not a required JSON-able one which we can simply set.
    """
    type_anno = prop.type_annotation
    prop_name = python_naming.property_name(prop.name)

    if isinstance(
        type_anno,
        (intermediate.JsonValueTypeAnnotation, intermediate.JsonArrayTypeAnnotation),
    ):
        return Stripped(f"instance.{prop_name} = [value]"), "[0]"

    # NOTE (mristin):
    # A constrained key might refuse any key that we come up with here.
    if (
        isinstance(type_anno, intermediate.JsonObjectTypeAnnotation)
        and isinstance(type_anno.key, intermediate.PrimitiveTypeAnnotation)
        and type_anno.key.a_type is intermediate.PrimitiveType.STR
    ):
        return Stripped(f'instance.{prop_name} = {{"a": value}}'), '["a"]'

    return None


@ensure(
    lambda result: result.endswith("\n"),
    "Trailing newline mandatory for valid end-of-files",
)
def generate(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> str:
    """
    Generate code to test that the integers are checked against the safe range.

    The same predicate decides in the verification, the JSON de/serialization and
    the XML de/serialization, so that an instance which passes the verification
    is guaranteed to be serializable.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    integers = intermediate_uses.integers(symbol_table)
    json_types = intermediate_uses.json_types(symbol_table)

    integer_methods: List[Stripped] = []
    for numeric_place in intermediate.numeric_places(symbol_table):
        if numeric_place.a_type is not intermediate.PrimitiveType.INT:
            continue

        mutation, subscript = python_tests_jsonization.numeric_place_mutation(
            numeric_place=numeric_place, zero_literal="0"
        )

        methods = _generate_place_tests(
            cls=numeric_place.cls,
            prop=numeric_place.prop,
            mutation=mutation,
            subscript=subscript,
            cause_prefix="Expected an integer, but got ",
        )
        integer_methods.extend(methods)

    json_able_methods: List[Stripped] = []
    if json_types:
        for cls in symbol_table.concrete_classes:
            for prop in cls.properties:
                mutation_and_subscript = _json_able_mutation(prop)
                if mutation_and_subscript is None:
                    continue

                methods = _generate_place_tests(
                    cls=cls,
                    prop=prop,
                    mutation=mutation_and_subscript[0],
                    subscript=mutation_and_subscript[1],
                    cause_prefix="Expected a JSON-able value, but got the integer ",
                )
                json_able_methods.extend(methods)

    has_places = len(integer_methods) > 0 or len(json_able_methods) > 0

    imports = [f"import {qualified_module_name}.common as our_common"]
    if has_places:
        imports.extend(
            [
                f"import {qualified_module_name}.jsonization as our_jsonization",
                f"import {qualified_module_name}.reporting as our_reporting",
                f"import {qualified_module_name}.verification as our_verification",
            ]
        )
        imports.append(f"import {qualified_module_name}.xmlization as our_xmlization")
    imports_joined = "\n".join(imports)

    paths_and_causes = f"""


def _paths_and_causes(
{II}errors: Iterable[our_reporting.Error]
) -> List[Tuple[str, str]]:
{I}return [(str(error.path), error.cause) for error in errors]"""

    blocks: List[Stripped] = [
        Stripped(
            '''\
"""Test that the integers are checked against the safe integer range."""'''
        ),
        python_common.WARNING,
    ]

    if has_places:
        blocks.extend(
            [
                Stripped(
                    """\
import json
from typing import Any, Iterable, List, Tuple
import unittest"""
                ),
                Stripped(imports_joined),
                Stripped("import tests.common"),
                Stripped(
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
{II}return json.load(fid){paths_and_causes}"""
                ),
            ]
        )
    else:
        blocks.extend([Stripped("import unittest"), Stripped(imports_joined)])

    blocks.append(
        _generate_predicate_test_case(integers=integers, json_types=json_types)
    )

    for class_name, methods in (
        ("TestIntegerProperties", integer_methods),
        ("TestJsonAbleProperties", json_able_methods),
    ):
        if len(methods) == 0:
            continue

        body = "\n\n".join(methods)
        blocks.append(
            Stripped(
                f"""\
class {class_name}(unittest.TestCase):
{I}{indent_but_first_line(body, I)}"""
            )
        )

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
