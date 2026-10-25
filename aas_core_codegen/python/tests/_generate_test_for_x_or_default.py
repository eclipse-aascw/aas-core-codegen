"""Generate code to test the ``X_or_default`` methods."""

import io
from typing import List, Optional

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.python import common as python_common, naming as python_naming
from aas_core_codegen.python.tests import _generate_common as python_tests_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_test_case(cls: intermediate.ConcreteClass) -> Optional[Stripped]:
    """
    Generate the test case class for the given ``cls``.

    If there are no ``X_or_default`` methods, return None.
    """
    xml_cls_name = naming.xml_class_name(cls.name)

    python_cls_name = python_naming.class_name(cls.name)

    test_methods: List[Stripped] = []

    for method in cls.methods:
        if (
            not method.name.endswith("_or_default")
            or method.visibility is not intermediate.Visibility.PUBLIC
        ):
            continue

        if method.returns is None:
            continue

        test_case_method_name = python_naming.method_name(
            Identifier(f"test_{method.name}_against_recorded")
        )

        x_or_default_name = python_naming.method_name(method.name)

        file_name = f"{x_or_default_name}.trace"

        log_assignment: Stripped
        if not isinstance(
            method.returns, intermediate.OptionalTypeAnnotation
        ) and python_tests_common.contains_json(method.returns):
            trace_argument = python_tests_common.generate_trace_argument(
                type_annotation=method.returns, expression="value"
            )

            log_assignment = Stripped(
                f"""\
value = instance.{x_or_default_name}()
log = [
{I}tests.common.trace(
{II}{indent_but_first_line(trace_argument, II)}
{I})
]"""
            )
        else:
            log_assignment = Stripped(
                f"log = [tests.common.trace(instance.{x_or_default_name}())]"
            )

        test_methods.append(
            Stripped(
                f"""\
def {test_case_method_name}(self) -> None:
{I}for minimal_or_maximal in ["minimal", "maximal"]:
{II}instance = tests.common_xmlization.must_load(
{III}pathlib.Path(
{IIII}tests.common.TEST_DATA_DIR
{IIII}/ "Xml"
{IIII}/ "Expected"
{IIII}/ {xml_cls_name!r}
{IIII}/ f"{{minimal_or_maximal}}.xml"
{III})
{II})

{II}assert isinstance(
{III}instance,
{III}our_types.{python_cls_name}
{II})

{II}{indent_but_first_line(log_assignment, II)}

{II}got_text = tests.common.trace_log_as_text_file_content(log)

{II}expected_path = pathlib.Path(
{III}tests.common.TEST_DATA_DIR
{III}/ "test_X_or_default"
{III}/ {xml_cls_name!r}
{III}/ f"on_{{minimal_or_maximal}}.xml"
{III}/ {file_name!r}
{II})

{II}tests.common.record_or_check(expected_path, got_text)"""
            )
        )

    if len(test_methods) == 0:
        return None

    test_class_name = python_naming.class_name(Identifier(f"Test_{cls.name}"))

    body = "\n\n".join(test_methods)

    return Stripped(
        f"""\
class {test_class_name}(unittest.TestCase):
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
    Generate code to test the ``X_or_default`` methods.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            '''\
"""Test ``X_or_default`` methods."""'''
        ),
        python_common.WARNING,
    ]

    test_cases: List[Stripped] = []
    for cls in symbol_table.concrete_classes:
        test_case = _generate_test_case(cls=cls)

        if test_case is None:
            continue

        test_cases.append(test_case)

    # NOTE (mristin):
    # We import the modules only if there is anything to test so that
    # the imports are never unused.
    if len(test_cases) == 0:
        blocks.append(Stripped("import unittest"))
    else:
        blocks.extend(
            [
                Stripped(
                    """\
import pathlib
import unittest"""
                ),
                Stripped(
                    f"""\
import {qualified_module_name}.types as our_types"""
                ),
                Stripped(
                    """\
import tests.common
import tests.common_xmlization"""
                ),
            ]
        )

    blocks.extend(test_cases)

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
