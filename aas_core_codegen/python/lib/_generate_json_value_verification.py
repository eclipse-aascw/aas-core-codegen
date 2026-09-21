"""Generate the code which verifies that a value is JSON-able."""

import io
from typing import List

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


def _generate_module_docstring(
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the docstring of the module."""
    return Stripped(
        f'''\
"""
Verify that a value is JSON-able.

A JSON-able value is, recursively, exactly as JSON itself is defined:
a boolean, a finite number, a string, an array of JSON-able values or
an object of JSON-able values with string keys. Python offers no type which
says exactly that, so a value has to be walked to make sure of it.

This module depends on no class of the meta-model. It is invoked from
the ordinary per-class dispatch of
:py:mod:`{qualified_module_name}.verification`, exactly as every other kind
of property is -- save for the keys of a ``JSONObject`` with a constrained
primitive as its key, which the verification checks itself, by reusing
the function it already generated for that constrained primitive.
"""'''
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(qualified_module_name: python_common.QualifiedModuleName) -> str:
    """
    Generate the code which verifies that a value is JSON-able.

    The ``qualified_module_name`` indicates the fully-qualified name of the base
    module.
    """
    blocks = [
        _generate_module_docstring(qualified_module_name=qualified_module_name),
        python_common.WARNING,
        Stripped(
            f"""\
import collections.abc
import math
from typing import Iterator

import {qualified_module_name}.common as aas_common
import {qualified_module_name}.types as aas_types
from {qualified_module_name}.reporting import (
{I}Error,
{I}IndexSegment,
{I}KeySegment
)"""
        ),
        Stripped(
            f'''\
def verify_json_value(
{I}value: aas_types.JsonValue
) -> Iterator[Error]:
{I}"""
{I}Verify that :paramref:`value` is a JSON-able value, at any depth.

{I}The path of an error points into :paramref:`value` itself: an item of
{I}an array contributes an index segment and a member of an object a key
{I}segment, so that the path leads all the way down to the culprit.

{I}The value is walked depth first, so an error deep inside the first member
{I}is reported before an error on the second one. The errors thus come in
{I}the order in which a reader meets them going through the value.

{I}:param value: to be verified
{I}:yield: errors, if any
{I}"""
{I}# NOTE (mristin):
{I}# A ``bool`` is an ``int`` in Python, so it has to be checked first --
{I}# otherwise every boolean would be taken for a number.
{I}if isinstance(value, bool):
{II}return

{I}if isinstance(value, int):
{II}# NOTE (mristin):
{II}# JSON knows a single numeric type, so an ``int`` becomes a ``float``
{II}# on the way out. Only an ``int`` which that conversion can not carry
{II}# exactly is an error here -- see
{II}# :py:func:`.common.try_to_convert_int_to_float`.
{II}if aas_common.try_to_convert_int_to_float(value) is None:
{III}yield Error(
{IIII}f"Expected a JSON-able value, but got the integer {{value}}, "
{IIII}f"which is not exactly representable as a JSON number"
{III})

{II}return

{I}if isinstance(value, float):
{II}# NOTE (mristin):
{II}# JSON knows neither an infinity nor a not-a-number, so neither is
{II}# a JSON-able value, even though a Python ``float`` is happy to hold
{II}# either.
{II}if not math.isfinite(value):
{III}yield Error(
{IIII}f"Expected a JSON-able value, but got the number {{value}}, "
{IIII}f"which is neither finite nor representable in JSON"
{III})

{II}return

{I}if isinstance(value, str):
{II}return

{I}if isinstance(value, (dict, collections.abc.Mapping)):
{II}for key, item_value in value.items():
{III}if not isinstance(key, str):
{IIII}# NOTE (mristin):
{IIII}# There is no key segment to report here: a key which is no
{IIII}# string names nothing which the path could descend into, so
{IIII}# the path stops at the object which holds it.
{IIII}yield Error(
{IIIII}f"Expected only string keys in a JSON-able object, but got "
{IIIII}f"a key of type: {{type(key)}}"
{IIII})
{IIII}continue

{III}for error in verify_json_value(item_value):
{IIII}error.path._prepend(KeySegment(value, key))
{IIII}yield error

{II}return

{I}array_like = aas_common.try_to_cast_to_array_like(value)
{I}if array_like is not None:
{II}for i, item_value in enumerate(array_like):
{III}for error in verify_json_value(item_value):
{IIII}error.path._prepend(IndexSegment(array_like, i))
{IIII}yield error

{II}return

{I}yield Error(
{II}f"Expected a JSON-able value (a boolean, a number, a string, an array "
{II}f"or an object), but got: {{type(value)}}"
{I})'''
        ),
        Stripped(
            f'''\
def verify_json_array(
{I}value: aas_types.JsonArray
) -> Iterator[Error]:
{I}"""
{I}Verify that :paramref:`value` is a JSON-able array.

{I}:param value: to be verified
{I}:yield: errors, if any
{I}"""
{I}if aas_common.try_to_cast_to_array_like(value) is None:
{II}yield Error(
{III}f"Expected a JSON-able array, but got: {{type(value)}}"
{II})
{II}return

{I}yield from verify_json_value(value)'''
        ),
        Stripped(
            f'''\
def verify_json_object(
{I}value: aas_types.JsonObject
) -> Iterator[Error]:
{I}"""
{I}Verify that :paramref:`value` is a JSON-able object.

{I}:param value: to be verified
{I}:yield: errors, if any
{I}"""
{I}if not isinstance(value, (dict, collections.abc.Mapping)):
{II}yield Error(
{III}f"Expected a JSON-able object, but got: {{type(value)}}"
{II})
{II}return

{I}yield from verify_json_value(value)'''
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()
