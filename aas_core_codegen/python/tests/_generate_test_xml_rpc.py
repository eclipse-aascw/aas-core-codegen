"""Generate code to test the XML-RPC de/serialization of the JSON-able values."""

import io

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


@ensure(
    lambda result: result.endswith("\n"),
    "Trailing newline mandatory for valid end-of-files",
)
def generate(
    qualified_module_name: python_common.QualifiedModuleName,
) -> str:
    """
    Generate code to unit test the XML-RPC de/serialization in isolation.

    The module under test drives no document of its own, so the test hands it
    the iterator, and the writer, which an enclosing document would. That is what
    lets it assert on the paths which the two no-wrapper entry points --
    the reading of an ``<array>`` body and of a ``<struct>`` body -- grow.

    The ``qualified_module_name`` indicates the fully-qualified name of the base
    module.
    """
    blocks = [
        Stripped(
            f'''\
"""Test :py:mod:`{qualified_module_name}.xmlrpc`."""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped(
            f"""\
import io
import unittest
import xml.etree.ElementTree
from typing import Any, cast, Iterator, List, Mapping, Tuple

import {qualified_module_name}.types as aas_types
import {qualified_module_name}.xmlcommon as aas_xmlcommon
import {qualified_module_name}.xmlrpc as aas_xmlrpc"""
        ),
        Stripped(
            f'''\
def _enter(
{II}text: str
) -> Tuple[
{II}aas_xmlcommon.Element,
{II}Iterator[Tuple[str, aas_xmlcommon.Element]]
]:
{I}"""
{I}Parse :paramref:`text` and consume the start event of its root element.

{I}The module under test expects to be handed a stream which is already
{I}positioned *inside* the element whose content it is to read, exactly as
{I}the xmlization hands it over.

{I}:param text: XML document to be read
{I}:return: the root element and the iterator positioned after its start event
{I}"""
{I}iterator = xml.etree.ElementTree.iterparse(
{II}io.StringIO(text),
{II}['start', 'end']
{I})

{I}event, element = next(iterator)
{I}assert event == 'start', f"Expected a start event, but got: {{event!r}}"

{I}return element, iterator'''
        ),
        Stripped(
            f"""\
class TestReading(unittest.TestCase):
{I}def test_a_value_round_trips_through_every_discriminator(self) -> None:
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\"><struct xmlns=\"\">'
{III}f'<member><name>b</name><value><boolean>1</boolean></value></member>'
{III}f'<member><name>n</name><value><double>1</double></value></member>'
{III}f'<member><name>f</name><value><double>1.5</double></value></member>'
{III}f'<member><name>s</name><value><string>x</string></value></member>'
{III}f'<member><name>a</name><value><array><data>'
{III}f'<value><double>0</double></value>'
{III}f'</data></array></value></member>'
{III}f'</struct></v>'
{II})

{II}self.assertEqual(
{III}{{"b": True, "n": 1.0, "f": 1.5, "s": "x", "a": [0.0]}},
{III}aas_xmlrpc.read_value_content(element, iterator)
{II})

{I}def test_a_discriminator_in_the_document_namespace_is_refused(self) -> None:
{II}# NOTE (mristin):
{II}# The XML-RPC elements reside in no namespace at all, so a discriminator
{II}# which inherits the namespace of the enclosing document is no
{II}# discriminator of ours.
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\"><boolean>1</boolean></v>'
{II})

{II}with self.assertRaises(
{III}aas_xmlcommon.DeserializationException
{II}) as context:
{III}aas_xmlrpc.read_value_content(element, iterator)

{II}self.assertIn(
{III}'Expected the element in no namespace', context.exception.cause
{II})

{I}def test_a_double_is_always_read_as_a_float(self) -> None:
{II}# NOTE (mristin):
{II}# JSON knows a single numeric type, so a <double> gives a ``float``
{II}# whether or not its text carries a fraction.
{II}for text, expected in (('1', 1.0), ('1.0', 1.0), ('1e1', 10.0)):
{III}element, iterator = _enter(
{IIII}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\">'
{IIII}f'<double xmlns=\"\">{{text}}</double></v>'
{III})

{III}value = aas_xmlrpc.read_value_content(element, iterator)

{III}self.assertEqual(expected, value, f"for the text {{text!r}}")
{III}self.assertIs(float, type(value), f"for the text {{text!r}}")

{I}def test_the_discriminator_is_a_step_of_the_path(self) -> None:
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\">'
{III}f'<boolean xmlns=\"\">yes</boolean></v>'
{II})

{II}with self.assertRaises(
{III}aas_xmlcommon.DeserializationException
{II}) as context:
{III}aas_xmlrpc.read_value_content(element, iterator)

{II}self.assertEqual('boolean', str(context.exception.path))

{I}def test_an_element_which_is_no_discriminator_gets_no_step(self) -> None:
{II}# NOTE (mristin):
{II}# It is this very element which does not belong here, so naming it in
{II}# the path as well as in the message would say nothing more.
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\"><oops xmlns=\"\"/></v>'
{II})

{II}with self.assertRaises(
{III}aas_xmlcommon.DeserializationException
{II}) as context:
{III}aas_xmlrpc.read_value_content(element, iterator)

{II}self.assertEqual('', str(context.exception.path))
{II}self.assertIn('but got: ', context.exception.cause)

{I}def test_the_path_into_a_nested_value(self) -> None:
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\"><struct xmlns=\"\">'
{III}f'<member><name>nested</name><value><array><data>'
{III}f'<value><double>0</double></value>'
{III}f'<value><string><oops/></string></value>'
{III}f'</data></array></value></member>'
{III}f'</struct></v>'
{II})

{II}with self.assertRaises(
{III}aas_xmlcommon.DeserializationException
{II}) as context:
{III}aas_xmlrpc.read_value_content(element, iterator)

{II}self.assertEqual(
{III}'struct/member[name=\"nested\"]/value/array/data/*[1]/string',
{III}str(context.exception.path)
{II})

{I}def test_the_array_body_entered_without_its_wrapper(self) -> None:
{II}# NOTE (mristin):
{II}# A ``JSONArray`` property is represented by a <data> element directly,
{II}# with no <array> element around it, so the path has none either.
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\"><data xmlns=\"\">'
{III}f'<value><boolean>yes</boolean></value>'
{III}f'</data></v>'
{II})

{II}with self.assertRaises(
{III}aas_xmlcommon.DeserializationException
{II}) as context:
{III}aas_xmlrpc.read_array_body(element, iterator)

{II}self.assertEqual('data/*[0]/boolean', str(context.exception.path))

{I}def test_the_struct_body_entered_without_its_wrapper(self) -> None:
{II}# NOTE (mristin):
{II}# A ``JSONObject`` property is represented by its <member> elements
{II}# directly, with no <struct> element around them.
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\">'
{III}f'<member xmlns=\"\"><name>k</name><value><oops/></value></member>'
{III}f'</v>'
{II})

{II}with self.assertRaises(
{III}aas_xmlcommon.DeserializationException
{II}) as context:
{III}aas_xmlrpc.read_struct_body(element, iterator)

{II}self.assertEqual(
{III}'member[name=\"k\"]/value', str(context.exception.path)
{II})

{I}def test_the_key_of_a_member_is_escaped_in_the_path(self) -> None:
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\">'
{III}f'<member xmlns=\"\"><name>a&amp;b/c&lt;d</name><value><oops/></value></member>'
{III}f'</v>'
{II})

{II}with self.assertRaises(
{III}aas_xmlcommon.DeserializationException
{II}) as context:
{III}aas_xmlrpc.read_struct_body(element, iterator)

{II}self.assertEqual(
{III}'member[name=\"a&amp;b&#47;c&lt;d\"]/value',
{III}str(context.exception.path)
{II})

{I}def test_a_repeated_member_is_refused(self) -> None:
{II}element, iterator = _enter(
{III}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\">'
{III}f'<member xmlns=\"\"><name>k</name><value><double>1</double></value></member>'
{III}f'<member xmlns=\"\"><name>k</name><value><double>2</double></value></member>'
{III}f'</v>'
{II})

{II}with self.assertRaises(
{III}aas_xmlcommon.DeserializationException
{II}) as context:
{III}aas_xmlrpc.read_struct_body(element, iterator)

{II}self.assertEqual(
{III}'member[name=\"k\"]', str(context.exception.path)
{II})
{II}self.assertEqual(
{III}'The member occurred more than once', context.exception.cause
{II})

{I}def test_neither_an_infinity_nor_a_not_a_number_is_read(self) -> None:
{II}for text in ('INF', '-INF', 'NaN', '1e400'):
{III}element, iterator = _enter(
{IIII}f'<v xmlns=\"{{aas_xmlcommon.NAMESPACE}}\">'
{IIII}f'<double xmlns=\"\">{{text}}</double></v>'
{III})

{III}with self.assertRaises(
{IIII}aas_xmlcommon.DeserializationException,
{IIII}msg=f"for the text {{text!r}}"
{III}) as context:
{IIII}aas_xmlrpc.read_value_content(element, iterator)

{III}self.assertEqual('double', str(context.exception.path))"""
        ),
        Stripped(
            f"""\
class TestWriting(unittest.TestCase):
{I}def test_a_value_is_written_with_its_discriminator(self) -> None:
{II}cases = [
{III}(True, '<boolean>1</boolean>'),
{III}(False, '<boolean>0</boolean>'),
{III}(1.0, '<double>1.0</double>'),
{III}(1.5, '<double>1.5</double>'),
{III}# NOTE (mristin):
{III}# An ``int`` is admitted next to a ``float``, and written free of
{III}# the fraction which a ``float`` carries.
{III}(1, '<double>1</double>'),
{III}('a<b&c', '<string>a&lt;b&amp;c</string>'),
{III}(
{IIII}[0.0],
{IIII}'<array><data><value><double>0.0</double></value></data></array>'
{III}),
{III}(
{IIII}{{'k': 0.0}},
{IIII}'<struct><member><name>k</name>'
{IIII}'<value><double>0.0</double></value></member></struct>'
{III}),
{II}]  # type: List[Tuple[aas_types.JsonValue, str]]

{II}for value, expected in cases:
{III}stream = io.StringIO()
{III}writer = aas_xmlcommon.Writer(stream)

{III}aas_xmlrpc.write_discriminator(value, writer)

{III}# NOTE (mristin):
{III}# The outermost element in no namespace undeclares the default
{III}# namespace, and the elements nested in it inherit that.
{III}self.assertEqual(
{IIII}expected.replace('>', ' xmlns=\"\">', 1),
{IIII}stream.getvalue(),
{IIII}f"for the value {{value!r}}"
{III})

{I}def test_the_path_of_a_failure_points_into_the_value(self) -> None:
{II}stream = io.StringIO()
{II}writer = aas_xmlcommon.Writer(stream)

{II}with self.assertRaises(
{III}aas_xmlcommon.SerializationException
{II}) as context:
{III}aas_xmlrpc.write_struct_body(
{IIII}{{'a b': [0, float('inf')]}}, writer
{III})

{II}self.assertEqual(
{III}\"['a b'][1]\", context.exception.path
{II})

{I}def test_an_integer_too_large_for_a_float_is_not_written(self) -> None:
{II}# NOTE (mristin):
{II}# A <double> carries a JSON number, and a JSON number is a ``float``,
{II}# so an ``int`` which no ``float`` can hold exactly has no <double>
{II}# to be written as.
{II}for number in (2 ** 53 + 1, 10 ** 400):
{III}stream = io.StringIO()
{III}writer = aas_xmlcommon.Writer(stream)

{III}with self.assertRaises(
{IIII}aas_xmlcommon.SerializationException,
{IIII}msg=f"for the number {{number}}"
{III}) as context:
{IIII}aas_xmlrpc.write_discriminator(number, writer)

{III}self.assertIn(
{IIII}'not exactly representable as a JSON number',
{IIII}context.exception.cause
{III})

{I}def test_a_key_which_is_no_string_stops_the_path(self) -> None:
{II}stream = io.StringIO()
{II}writer = aas_xmlcommon.Writer(stream)

{II}with self.assertRaises(
{III}aas_xmlcommon.SerializationException
{II}) as context:
{III}aas_xmlrpc.write_struct_body(
{IIII}cast(Mapping[str, Any], {{1: 'no string key'}}), writer
{III})

{II}self.assertEqual('', context.exception.path)
{II}self.assertIn('but got a key of type', context.exception.cause)"""
        ),
        Stripped(
            f"""\
if __name__ == "__main__":
{I}unittest.main()"""
        ),
        python_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()
