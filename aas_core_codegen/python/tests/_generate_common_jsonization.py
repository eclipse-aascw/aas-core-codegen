"""Generate code for common JSON de/serialization shared across the tests."""
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
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


def _generate_model_type_to_from_jsonable(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the map from model type to the ``*_from_jsonable`` function."""
    items: List[Stripped] = []

    for cls in sorted(symbol_table.concrete_classes, key=lambda a_cls: a_cls.name):
        model_type = naming.json_model_type(cls.name)
        from_jsonable = python_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        items.append(Stripped(f"{model_type!r}:\n{I}our_jsonization.{from_jsonable}"))

    items_joined = ",\n".join(items)

    return Stripped(
        f"""\
_MODEL_TYPE_TO_FROM_JSONABLE: Mapping[
{I}str,
{I}Callable[[our_jsonization.Jsonable], our_types.Class]
] = {{
{I}{indent_but_first_line(items_joined, I)}
}}"""
    )


def _generate_model_type_to_class(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the map from the concrete class to model type."""
    items: List[Stripped] = []

    for cls in sorted(symbol_table.concrete_classes, key=lambda a_cls: a_cls.name):
        model_type = naming.json_model_type(cls.name)
        python_cls_name = python_naming.class_name(cls.name)

        items.append(Stripped(f"{model_type!r}:\n{I}our_types.{python_cls_name}"))

    items_joined = ",\n".join(items)

    return Stripped(
        f"""\
_MODEL_TYPE_TO_CLASS: Mapping[
{I}str,
{I}Type[our_types.Class]
] = {{
{I}{indent_but_first_line(items_joined, I)}
}}"""
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
    Generate code for common JSON de/serialization shared across the tests.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            '"""Provide common functionality for JSON de/serialization in tests."""',
        ),
        python_common.WARNING,
        Stripped(
            """\
# pylint: disable=missing-docstring"""
        ),
        Stripped(
            """\
import collections.abc
import json
import pathlib
import sys
from typing import Callable, Iterator, Mapping, Type"""
        ),
        Stripped(
            f"""\
if sys.version_info >= (3, 8):
{I}from typing import Final
else:
{I}from typing_extensions import Final"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.common as our_common
import {qualified_module_name}.jsonization as our_jsonization
import {qualified_module_name}.types as our_types"""
        ),
        Stripped(
            f'''\
class Difference:
{I}"""Represent a single difference between two JSON-ables."""

{I}#: Human-readable description of the difference
{I}message: Final[str]

{I}#: Path in the expected JSON-able value which is different from
{I}#: the obtained JSON-able value
{I}path: Final[our_jsonization.Path]

{I}def __init__(self, message: str) -> None:
{II}"""Initialize with the given message and empty path."""
{II}self.message = message
{II}self.path = our_jsonization.Path()

{I}def __str__(self) -> str:
{II}return f"#{{self.path}}: {{self.message}}"'''
        ),
        Stripped(
            f'''\
def check_equal(
{I}expected: our_jsonization.Jsonable,
{I}got: our_jsonization.Jsonable,
) -> Iterator[Difference]:
{I}"""
{I}Compare recursively two JSON-able values for equality.

{I}:param expected: expected JSON-able value
{I}:param got: obtained JSON-able value
{I}:yield: differences
{I}"""
{I}if isinstance(expected, (bool, int, float, str, bytes)):
{II}if type(expected) is not type(got):
{III}yield Difference(f"Expected {{type(expected)}}, but got {{type(got)}}")

{II}if expected != got:
{III}yield Difference(f"Expected {{expected!r}}, but got {{got!r}}")
{I}elif isinstance(expected, collections.abc.Sequence):
{II}if not isinstance(got, collections.abc.Sequence):
{III}yield Difference(f"Expected a sequence, but got {{type(got)}}")
{II}else:
{III}if len(expected) != len(got):
{IIII}yield Difference(
{IIIII}f"Expected a sequence of {{len(expected)}} item(s), "
{IIIII}f"but got {{len(got)}} item(s)"
{IIII})

{III}for i, (expected_item, got_item) in enumerate(zip(expected, got)):
{IIII}for difference in check_equal(expected_item, got_item):
{IIIII}difference.path._prepend(our_jsonization.IndexSegment(expected, i))
{IIIII}yield difference

{I}elif isinstance(expected, collections.abc.Mapping):
{II}if not isinstance(got, collections.abc.Mapping):
{III}yield Difference(f"Expected a mapping, but got {{type(got)}}")
{II}else:
{III}if not all(isinstance(key, str) for key in expected):
{IIII}raise ValueError(
{IIIII}f"Expected all keys in the expected JSON-able value to be strings, "
{IIIII}f"but got: {{list(expected.keys())}}"
{IIII})

{III}if not all(isinstance(key, str) for key in got):
{IIII}yield Difference(
{IIIII}f"Expected all keys in a mapping to be strings, "
{IIIII}f"but got: {{list(got.keys())}}"
{IIII})

{III}expected_key_set = set(expected.keys())
{III}got_key_set = set(got.keys())

{III}expected_got_diff = expected_key_set.difference(got_key_set)
{III}if expected_got_diff:
{IIII}yield Difference(f"Expected key(s) {{sorted(expected_got_diff)}} missing")

{III}got_expected_diff = got_key_set.difference(expected_key_set)
{III}if got_expected_diff:
{IIII}yield Difference(f"Unexpected key(s) {{sorted(got_expected_diff)}}")

{III}for key, expected_value in expected.items():
{IIII}got_value = got[key]

{IIII}for difference in check_equal(expected_value, got_value):
{IIIII}difference.path._prepend(
{IIIIII}our_jsonization.PropertySegment(expected, key)
{IIIII})
{IIIII}yield difference
{I}else:
{II}our_common.assert_never(expected)'''
        ),
        _generate_model_type_to_from_jsonable(symbol_table=symbol_table),
        _generate_model_type_to_class(symbol_table=symbol_table),
        Stripped(
            f'''\
def must_load(
{I}path: pathlib.Path,
{I}model_type: str
) -> our_types.Class:
{I}"""
{I}Load an instance from ``path``.

{I}The class of the instance must correspond to the ``model_type``.
{I}"""
{I}try:
{II}jsonable = json.loads(
{III}path.read_text(encoding='utf-8')
{II})
{I}except Exception as exception:
{II}raise RuntimeError(f"Failed to read from {{path}}") from exception

{I}from_jsonable = _MODEL_TYPE_TO_FROM_JSONABLE.get(model_type)
{I}if from_jsonable is None:
{II}raise AssertionError(
{III}"The model type is not mapped to "
{III}f"the from_jsonable function: {{model_type!r}}"
{II})

{I}try:
{II}instance = from_jsonable(jsonable)
{I}except Exception as exception:
{II}raise RuntimeError(
{III}"Failed to parse the instance "
{III}f"with model type {{model_type}} from {{path}}"
{II}) from exception

{I}cls = _MODEL_TYPE_TO_CLASS.get(model_type)
{I}if cls is None:
{II}raise AssertionError(
{III}"The model type is not mapped to the class: {{model_type!r}}"
{II})

{I}if not isinstance(instance, cls):
{II}raise RuntimeError(
{III}f"Expected an instance with model type {{model_type!r}}, "
{III}f"corresponding to class {{cls}}, "
{III}f"but got an instance {{instance}}"
{II})

{I}return instance'''
        ),
        python_common.WARNING,
    ]

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue()
