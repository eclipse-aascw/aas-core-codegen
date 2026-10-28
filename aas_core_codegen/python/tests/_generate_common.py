"""Generate code for common functionality shared across the tests."""
import io

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, assert_never, indent_but_first_line
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.python import (
    common as python_common,
)
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def contains_json(type_annotation: intermediate.TypeAnnotationUnion) -> bool:
    """Check whether ``type_annotation`` refers to a JSON-able type at any depth."""
    return any(
        isinstance(
            nested,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        )
        for nested in intermediate.over_type_annotation_and_nested_type_annotations(
            type_annotation
        )
    )


def generate_trace_argument(
    type_annotation: intermediate.TypeAnnotationExceptOptional,
    expression: str,
) -> Stripped:
    """
    Generate the argument for ``tests.common.trace`` from ``expression``.

    The ``expression`` is of the type ``type_annotation``. The function
    ``tests.common.trace`` does not accept JSON-able values, so we convert them
    with ``tests.common.trace_json`` to JSON texts, at any depth. If
    the ``type_annotation`` involves no JSON-able type, we return
    the ``expression`` as-is.

    The ``expression`` is repeated for the items of a tuple, so it should be
    cheap to evaluate, *e.g.*, a variable.
    """

    def generate_at(
        a_type_annotation: intermediate.TypeAnnotationExceptOptional,
        an_expression: str,
        depth: int,
    ) -> str:
        # NOTE (mristin):
        # The sets hold only primitives and enumeration literals, so they never
        # involve a JSON-able type.
        if isinstance(
            a_type_annotation,
            (
                intermediate.PrimitiveTypeAnnotation,
                intermediate.OurTypeAnnotation,
                intermediate.SetTypeAnnotation,
            ),
        ) or not contains_json(a_type_annotation):
            return an_expression

        elif isinstance(
            a_type_annotation,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            return f"tests.common.trace_json({an_expression})"

        elif isinstance(a_type_annotation, intermediate.ListTypeAnnotation):
            item_name = "item" if depth == 0 else f"item_{depth}"
            item_expression = generate_at(a_type_annotation.items, item_name, depth + 1)
            return f"""\
[
{I}{indent_but_first_line(item_expression, I)}
{I}for {item_name} in {indent_but_first_line(an_expression, I)}
]"""

        elif isinstance(a_type_annotation, intermediate.TupleTypeAnnotation):
            item_expressions = ",\n".join(
                generate_at(item_type_annotation, f"{an_expression}[{i}]", depth)
                for i, item_type_annotation in enumerate(a_type_annotation.items)
            )
            return f"""\
[
{I}{indent_but_first_line(item_expressions, I)}
]"""

        else:
            assert_never(a_type_annotation)

    return Stripped(generate_at(type_annotation, expression, 0))


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> str:
    """
    Generate code for common functionality shared across the tests.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    record_variable_name = (
        qualified_module_name.replace(".", "_").upper() + "_TESTS_RECORD_MODE"
    )

    uses_json_types = intermediate_uses.json_types(symbol_table)

    maybe_import_json = "\nimport json" if uses_json_types else ""

    blocks = [
        Stripped(
            '"""Provide functionality used across the tests."""',
        ),
        python_common.WARNING,
        Stripped(
            f"""\
import base64
import collections.abc
import difflib
import enum
import io{maybe_import_json}
import os
import pathlib
import textwrap
from typing import Union, Sequence"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.common as our_common
import {qualified_module_name}.types as our_types"""
        ),
        Stripped(
            """\
_REPO_ROOT = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent"""
        ),
        Stripped(
            '''\
#: Path to the directory which contains input and golden files
TEST_DATA_DIR = _REPO_ROOT / "dev" / "test_data"'''
        ),
        Stripped(
            f"""\
#: If set, the golden files in the tests should be re-recorded instead
#: of checked against.
RECORD_MODE = os.environ.get("{record_variable_name}", "").lower() in (
{I}"1",
{I}"on",
{I}"true",
)"""
        ),
        Stripped(
            f'''\
def record_or_check(path: pathlib.Path, got: str) -> None:
{I}"""
{I}Re-record or check that :paramref:`got` content matches the content of
{I}:paramref:`path`.

{I}If :py:attr:`~RECORD_MODE` is set, the content of :paramref:`path` will be
{I}simply overwritten with :paramref:`got` content, and no checks are performed.

{I}:param path: to the golden file
{I}:param got: obtained content
{I}:raise: :py:class:`AssertionError` if the contents do not match
{I}"""
{I}if RECORD_MODE:
{II}path.parent.mkdir(exist_ok=True, parents=True)
{II}path.write_text(got, encoding="utf-8")
{I}else:
{II}if not path.exists():
{III}raise FileNotFoundError(
{IIII}f"The golden file could not be found: {{path}}; did you record it?"
{III})

{II}expected = path.read_text(encoding="utf-8")
{II}if expected != got:
{III}writer = io.StringIO()

{III}diff = difflib.ndiff(
{IIII}expected.splitlines(keepends=True), got.splitlines(keepends=True)
{III})

{III}diff_text = "".join(diff)
{III}writer.write(
{IIII}f"""\\
The obtained content and the content of {{path}} do not match:
{{diff_text}}"""
{III})

{III}raise AssertionError(writer.getvalue())'''
        ),
        Stripped(
            f"""\
#: Represent a value which can be traced, including the nested sequences
Traceable = Union[
{I}bool,
{I}int,
{I}float,
{I}str,
{I}bytes,
{I}enum.Enum,
{I}our_types.Class,
{I}Sequence["Traceable"],
]"""
        ),
        Stripped(
            f'''\
def trace(that: Traceable) -> str:
{I}"""
{I}Generate a segment in a trace of an iteration.

{I}:param that: to be traced
{I}:return: segment in the descent trace
{I}"""
{I}if isinstance(that, our_types.Class):
{II}return that.__class__.__name__
{I}elif isinstance(that, (bool, int, float, str, enum.Enum)):
{II}return str(that)
{I}elif isinstance(that, bytes):
{II}return base64.b64encode(that).decode("ascii")
{I}elif isinstance(that, collections.abc.Sequence):
{II}if len(that) == 0:
{III}return "[]"
{II}writer = io.StringIO()
{II}writer.write("[\\n")
{II}for i, item in enumerate(that):
{III}writer.write(textwrap.indent(trace(item), "  "))

{III}if i < len(that) - 1:
{IIII}writer.write(",\\n")
{III}else:
{IIII}writer.write("\\n")

{II}writer.write("]")
{II}return writer.getvalue()
{I}else:
{II}our_common.assert_never(that)'''
        ),
    ]

    if uses_json_types:
        blocks.append(
            Stripped(
                f'''\
def trace_json(that: our_types.JsonValue) -> str:
{I}"""
{I}Trace the JSON-able value as its JSON text.

{I}We sort the keys so that the trace does not depend on their order.

{I}:param that: to be traced
{I}:return: JSON text of :paramref:`that`
{I}"""
{I}return json.dumps(that, sort_keys=True)'''
            )
        )

    blocks.extend(
        [
            Stripped(
                f'''\
def trace_log_as_text_file_content(log: Sequence[str]) -> str:
{I}"""
{I}Convert the trace log to a text to be stored in a file.

{I}:param log: to be converted to text
{I}:return: content of the file, including the new-line at the end
{I}"""
{I}writer = io.StringIO()
{I}for entry in log:
{II}writer.write(f"{{entry}}\\n")
{I}writer.write("\\n")
{I}return writer.getvalue()'''
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
