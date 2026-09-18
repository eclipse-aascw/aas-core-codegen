"""Generate code to test the XML de/serialization of concrete classes."""

import io
from typing import Dict, List, Optional, Tuple

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


def _slug(text: str) -> str:
    """
    Make a chunk of a test name out of ``text``.

    The result has to satisfy :py:attr:`aas_core_codegen.common.IDENTIFIER_RE`,
    so every character which is not a letter or a digit is spelled out, and
    an empty text is named as such.
    """
    if text == "":
        return "empty"

    mapping = {
        "+": "plus_",
        "-": "minus_",
        ".": "_point_",
        " ": "_space_",
        "=": "_pad",
    }

    result = "".join(mapping.get(character, character) for character in text)
    return result.lower()


def _generate_lexical_test_case(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Stripped]:
    """
    Generate the tests over the lexical forms which no recorded example can hold.

    A recorded example under ``Xml/Expected`` has to serialize back to itself,
    character for character, so it can hold neither a value which is written
    in another form than it was read -- ``1`` for a boolean comes back as
    ``true`` -- nor one whose written form the six SDKs spell differently,
    which is the case for every interesting double. Both are put here instead,
    where the test says what the *value* must be and never compares any text.
    """
    cls = intermediate.first_class_of_only_required_primitives(symbol_table)
    if cls is None:
        return None

    prop_by_a_type = (
        dict()
    )  # type: Dict[intermediate.PrimitiveType, intermediate.Property]
    for prop in cls.properties:
        assert isinstance(prop.type_annotation, intermediate.PrimitiveTypeAnnotation)
        prop_by_a_type.setdefault(prop.type_annotation.a_type, prop)

    float_prop = prop_by_a_type.get(intermediate.PrimitiveType.FLOAT, None)
    bool_prop = prop_by_a_type.get(intermediate.PrimitiveType.BOOL, None)

    if float_prop is None and bool_prop is None:
        return None

    xml_class_name = naming.xml_class_name(cls.name)
    from_str = python_naming.function_name(Identifier(f"{cls.name}_from_str"))

    cases = []  # type: List[Tuple[intermediate.Property, str, str]]

    if float_prop is not None:
        # NOTE (mristin):
        # A literal too large for a double is not an error: XSD rounds it to
        # an infinity, and one too small to zero.
        #
        # See: https://www.w3.org/TR/xmlschema11-2/#double
        cases.extend(
            [
                (float_prop, "1e400", "math.inf"),
                (float_prop, "-1e400", "-math.inf"),
                (float_prop, "1e-400", "0.0"),
                (float_prop, "INF", "math.inf"),
                (float_prop, "+INF", "math.inf"),
                (float_prop, "-INF", "-math.inf"),
            ]
        )

    bytes_prop = prop_by_a_type.get(intermediate.PrimitiveType.BYTEARRAY, None)

    if bytes_prop is not None:
        # NOTE (mristin):
        # ``xs:base64Binary`` admits whitespace *between* the characters and
        # not only around them, and an empty value stands for zero bytes.
        # Neither can be a recorded example: the first is written back without
        # the space, and the second is written as an empty element.
        #
        # See: https://www.w3.org/TR/xmlschema-2/#base64Binary
        cases.extend(
            [
                (bytes_prop, "SGk=", "b'Hi'"),
                (bytes_prop, "SG k=", "b'Hi'"),
                (bytes_prop, "S G k =", "b'Hi'"),
                (bytes_prop, "", "b''"),
            ]
        )

    if bool_prop is not None:
        # NOTE (mristin):
        # ``xs:boolean`` spells the two values in four ways, not two.
        cases.extend(
            [
                (bool_prop, "1", "True"),
                (bool_prop, "0", "False"),
                (bool_prop, "true", "True"),
                (bool_prop, "false", "False"),
            ]
        )

    blocks = [
        Stripped(
            f"""\
def _read_with(self, xml_name: str, text: str) -> aas_types.{python_naming.class_name(cls.name)}:
{I}\"\"\"Read a recorded example with the content of ``xml_name`` put to ``text``.\"\"\"
{I}paths = sorted(
{II}(
{III}tests.common.TEST_DATA_DIR
{III}/ "Xml"
{III}/ "Expected"
{III}/ {xml_class_name!r}
{II}).glob("**/*.xml")
{I})
{I}self.assertGreater(
{II}len(paths),
{II}0,
{II}f"Expected at least one recorded example of {xml_class_name}, but got none",
{I})

{I}original = paths[0].read_text(encoding="utf-8")

{I}start = original.index(f"<{{xml_name}}>") + len(xml_name) + 2
{I}end = original.index(f"</{{xml_name}}>")

{I}return aas_xmlization.{from_str}(
{II}original[:start] + text + original[end:]
{I})"""
        )
    ]  # type: List[Stripped]

    for prop, text, expected in cases:
        prop_xml_name = naming.xml_property(prop.name)
        prop_name = python_naming.property_name(prop.name)

        test_name = python_naming.method_name(
            Identifier(f"test_{prop.name}_read_from_{_slug(text)}")
        )

        if expected.startswith("b'"):
            assertion = f"self.assertEqual({expected}, instance.{prop_name})"
        elif expected in ("math.inf", "-math.inf"):
            assertion = f"self.assertEqual({expected}, instance.{prop_name})"
        elif expected == "0.0":
            assertion = f"self.assertEqual(0.0, instance.{prop_name})"
        else:
            assertion = f"self.assertIs({expected}, instance.{prop_name})"

        blocks.append(
            Stripped(
                f"""\
def {test_name}(self) -> None:
{I}instance = self._read_with({prop_xml_name!r}, {text!r})
{I}{assertion}"""
            )
        )

    body = "\n\n".join(blocks)

    return Stripped(
        f"""\
class TestLexicalForms(unittest.TestCase):
{I}\"\"\"Test the lexical forms which a recorded example can not hold.\"\"\"

{I}{indent_but_first_line(body, I)}"""
    )


def _generate_test_case(symbol_table: intermediate.SymbolTable) -> Stripped:
    test_methods = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        xml_class_name = naming.xml_class_name(cls.name)

        test_method_name = python_naming.method_name(Identifier(f"test_{cls.name}"))

        from_iterparse = python_naming.function_name(
            Identifier(f"{cls.name}_from_iterparse")
        )

        from_stream = python_naming.function_name(Identifier(f"{cls.name}_from_stream"))

        from_file = python_naming.function_name(Identifier(f"{cls.name}_from_file"))

        from_str = python_naming.function_name(Identifier(f"{cls.name}_from_str"))

        test_methods.append(
            Stripped(
                f"""\
def {test_method_name}(self) -> None:
{I}for path in sorted(
{II}(
{III}tests.common.TEST_DATA_DIR
{III}/ "Xml"
{III}/ "Expected"
{III}/ {xml_class_name!r}
{II}).glob("**/*.xml")
{I}):
{II}text = path.read_text(encoding="utf-8")
{II}et_concrete = ET.fromstring(text)
{II}tests.common_xmlization.remove_redundant_whitespace(et_concrete)

{II}# region From iterparse
{II}iterator = ET.iterparse(source=io.StringIO(text), events=["start", "end"])
{II}got_from_iterparse = (
{III}aas_xmlization.{from_iterparse}(iterator)
{II})

{II}et_from_iterparse = ET.fromstring(aas_xmlization.to_str(got_from_iterparse))
{II}tests.common_xmlization.remove_redundant_whitespace(et_from_iterparse)
{II}tests.common_xmlization.assert_elements_equal(et_concrete, et_from_iterparse)
{II}# endregion

{II}# region From stream
{II}got_from_stream = (
{III}aas_xmlization
{III}.{from_stream}(
{IIII}io.StringIO(text)
{III})
{II})
{II}et_from_stream = ET.fromstring(aas_xmlization.to_str(got_from_stream))
{II}tests.common_xmlization.remove_redundant_whitespace(et_from_stream)
{II}tests.common_xmlization.assert_elements_equal(et_concrete, et_from_stream)
{II}# endregion

{II}# region From file
{II}with tempfile.TemporaryDirectory() as tmp_dir:
{III}path = pathlib.Path(tmp_dir) / "something.xml"
{III}path.write_text(text, encoding="utf-8")

{III}got_from_file = (
{IIII}aas_xmlization
{IIII}.{from_file}(path)
{III})
{II}et_from_file = ET.fromstring(aas_xmlization.to_str(got_from_file))
{II}tests.common_xmlization.remove_redundant_whitespace(et_from_file)
{II}tests.common_xmlization.assert_elements_equal(et_concrete, et_from_file)
{II}# endregion

{II}# region From string
{II}got_from_str = (
{III}aas_xmlization
{III}.{from_str}(text)
{II})
{II}et_from_str = ET.fromstring(aas_xmlization.to_str(got_from_str))
{II}tests.common_xmlization.remove_redundant_whitespace(et_from_str)
{II}tests.common_xmlization.assert_elements_equal(et_concrete, et_from_str)
{II}# endregion"""
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


@ensure(
    lambda result: result.endswith("\n"),
    "Trailing newline mandatory for valid end-of-files",
)
def generate(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> str:
    """
    Generate code to test the XML de/serialization of concrete classes.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            '''\
"""Test XML de/serialization of concrete classes."""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped(
            """\
import io
import pathlib
import tempfile
import math
import unittest
import xml.etree.ElementTree as ET"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.types as aas_types
import {qualified_module_name}.xmlization as aas_xmlization"""
        ),
        Stripped(
            """\
import tests.common
import tests.common_xmlization"""
        ),
        _generate_test_case(symbol_table=symbol_table),
        Stripped(
            f"""\
if __name__ == "__main__":
{I}unittest.main()"""
        ),
        python_common.WARNING,
    ]

    lexical_test_case = _generate_lexical_test_case(symbol_table=symbol_table)
    if lexical_test_case is not None:
        # NOTE (mristin):
        # The class goes right after the round trips, and before the main.
        blocks.insert(-2, lexical_test_case)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue()
