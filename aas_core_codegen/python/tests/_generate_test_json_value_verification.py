"""Generate code to test the verification of the JSON-able values."""

import io

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


@ensure(
    lambda result: result.endswith("\n"),
    "Trailing newline mandatory for valid end-of-files",
)
def generate(qualified_module_name: python_common.QualifiedModuleName) -> str:
    """
    Generate code to unit test the verification of the JSON-able values.

    The module under test depends on no class of the meta-model, so neither does
    this test: it pins the shape of the walk and of the paths which it reports,
    and nothing about any particular model.

    The ``qualified_module_name`` indicates the fully-qualified name of the base
    module.
    """
    blocks = [
        Stripped(
            f'''\
"""Test :py:mod:`{qualified_module_name}.jsonvalueverification`."""'''
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped(
            f"""\
import math
import unittest
from typing import Any, cast, Iterable, List, Mapping, Sequence, Tuple

import {qualified_module_name}.jsonvalueverification as aas_json_value_verification
import {qualified_module_name}.reporting as aas_reporting"""
        ),
        Stripped(
            f"""\
def _paths_and_causes(
{II}errors: Iterable[aas_reporting.Error]
) -> List[Tuple[str, str]]:
{I}return [(str(error.path), error.cause) for error in errors]"""
        ),
        Stripped(
            f"""\
class TestJsonValue(unittest.TestCase):
{I}def test_a_deeply_nested_value_is_json_able(self) -> None:
{II}value = {{
{III}"a": [1, 1.5, "x", True, [2], {{"b": "text"}}],
{III}"c": {{"d": {{"e": []}}}}
{II}}}

{II}self.assertListEqual(
{III}[],
{III}_paths_and_causes(
{IIII}aas_json_value_verification.verify_json_value(value)
{III})
{II})

{I}def test_the_walk_is_depth_first(self) -> None:
{II}# NOTE (mristin):
{II}# A breadth-first walk would report the shallow ``['z']`` before
{II}# the deeper ``['a']['deep']``, although the latter comes first in
{II}# the value.
{II}value = {{
{III}"a": {{"deep": math.nan}},
{III}"z": math.inf
{II}}}

{II}self.assertListEqual(
{III}["['a']['deep']", "['z']"],
{III}[
{IIII}path
{IIII}for path, _ in _paths_and_causes(
{IIIII}aas_json_value_verification.verify_json_value(value)
{IIII})
{III}]
{II})

{I}def test_an_index_and_a_key_render_as_a_subscript(self) -> None:
{II}value = {{"a b": [0, {{"c'd": math.nan}}]}}

{II}paths_and_causes = _paths_and_causes(
{III}aas_json_value_verification.verify_json_value(value)
{II})

{II}self.assertEqual(1, len(paths_and_causes))
{II}self.assertEqual(
{III}"['a b'][1][\\"c'd\\"]",
{III}paths_and_causes[0][0]
{II})

{I}def test_a_non_string_key_stops_at_the_object_which_holds_it(self) -> None:
{II}value = {{"a": {{1: "the key is no string"}}}}

{II}paths_and_causes = _paths_and_causes(
{III}aas_json_value_verification.verify_json_value(value)
{II})

{II}self.assertEqual(1, len(paths_and_causes))
{II}self.assertEqual("['a']", paths_and_causes[0][0])
{II}self.assertIn("but got a key of type", paths_and_causes[0][1])

{I}def test_the_segments_carry_their_container(self) -> None:
{II}inner = {{"deep": math.nan}}
{II}value = {{"a": inner}}

{II}errors = list(aas_json_value_verification.verify_json_value(value))

{II}self.assertEqual(1, len(errors))

{II}segments = errors[0].path.segments
{II}self.assertEqual(2, len(segments))

{II}outer_segment = segments[0]
{II}assert isinstance(outer_segment, aas_reporting.KeySegment)
{II}self.assertIs(value, outer_segment.mapping)
{II}self.assertEqual("a", outer_segment.key)

{II}inner_segment = segments[1]
{II}assert isinstance(inner_segment, aas_reporting.KeySegment)
{II}self.assertIs(inner, inner_segment.mapping)
{II}self.assertEqual("deep", inner_segment.key)

{I}def test_neither_an_infinity_nor_a_not_a_number_is_json_able(self) -> None:
{II}for number in (math.inf, -math.inf, math.nan):
{III}paths_and_causes = _paths_and_causes(
{IIII}aas_json_value_verification.verify_json_value([number])
{III})

{III}self.assertEqual(1, len(paths_and_causes), f"for the number {{number}}")
{III}self.assertEqual("[0]", paths_and_causes[0][0])
{III}self.assertIn(
{IIII}"neither finite nor representable in JSON",
{IIII}paths_and_causes[0][1]
{III})

{I}def test_an_integer_is_json_able_while_it_fits_a_float(self) -> None:
{II}for number in (0, 1, -3, 2 ** 53):
{III}self.assertListEqual(
{IIII}[],
{IIII}_paths_and_causes(
{IIIII}aas_json_value_verification.verify_json_value([number])
{IIII}),
{IIII}f"for the number {{number}}"
{III})

{I}def test_an_integer_too_large_for_a_float_is_refused(self) -> None:
{II}# NOTE (mristin):
{II}# JSON knows a single numeric type, so an ``int`` has to become
{II}# a ``float``. 2**53 + 1 is the first whole number which a ``float``
{II}# can not tell from its neighbour, and 10**400 exceeds a ``float``
{II}# altogether.
{II}for number in (2 ** 53 + 1, 10 ** 400):
{III}paths_and_causes = _paths_and_causes(
{IIII}aas_json_value_verification.verify_json_value([number])
{III})

{III}self.assertEqual(1, len(paths_and_causes), f"for the number {{number}}")
{III}self.assertEqual("[0]", paths_and_causes[0][0])
{III}self.assertIn(
{IIII}"not exactly representable as a JSON number",
{IIII}paths_and_causes[0][1]
{III})

{I}def test_a_value_of_an_unexpected_type_is_refused(self) -> None:
{II}paths_and_causes = _paths_and_causes(
{III}aas_json_value_verification.verify_json_value({{"a": object()}})
{II})

{II}self.assertEqual(1, len(paths_and_causes))
{II}self.assertEqual("['a']", paths_and_causes[0][0])
{II}self.assertIn("but got: ", paths_and_causes[0][1])"""
        ),
        Stripped(
            f"""\
class TestJsonArrayAndJsonObject(unittest.TestCase):
{I}def test_an_array_has_to_be_an_array(self) -> None:
{II}paths_and_causes = _paths_and_causes(
{III}aas_json_value_verification.verify_json_array(
{IIII}cast(Sequence[Any], {{"a": 1}})
{III})
{II})

{II}self.assertEqual(1, len(paths_and_causes))
{II}self.assertEqual("", paths_and_causes[0][0])
{II}self.assertIn("Expected a JSON-able array", paths_and_causes[0][1])

{I}def test_a_string_is_no_array(self) -> None:
{II}# NOTE (mristin):
{II}# A ``str`` is a ``Sequence`` in Python, so it has to be ruled out
{II}# explicitly.
{II}paths_and_causes = _paths_and_causes(
{III}aas_json_value_verification.verify_json_array("not an array")
{II})

{II}self.assertEqual(1, len(paths_and_causes))
{II}self.assertIn("Expected a JSON-able array", paths_and_causes[0][1])

{I}def test_an_object_has_to_be_an_object(self) -> None:
{II}paths_and_causes = _paths_and_causes(
{III}aas_json_value_verification.verify_json_object(
{IIII}cast(Mapping[str, Any], [1, 2])
{III})
{II})

{II}self.assertEqual(1, len(paths_and_causes))
{II}self.assertEqual("", paths_and_causes[0][0])
{II}self.assertIn("Expected a JSON-able object", paths_and_causes[0][1])

{I}def test_the_content_is_verified_beneath_the_shape(self) -> None:
{II}paths_and_causes = _paths_and_causes(
{III}aas_json_value_verification.verify_json_object(
{IIII}{{"a": [{{"b": math.nan}}]}}
{III})
{II})

{II}self.assertEqual(1, len(paths_and_causes))
{II}self.assertEqual("['a'][0]['b']", paths_and_causes[0][0])"""
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
