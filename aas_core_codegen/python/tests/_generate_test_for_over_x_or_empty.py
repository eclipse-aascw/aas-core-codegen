"""Generate code to test the ``over_X_or_empty`` methods."""

import io
from typing import List, Optional

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
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

    If there are no ``over_X_or_empty`` methods, return None.
    """
    xml_cls_name = naming.xml_class_name(cls.name)

    python_cls_name = python_naming.class_name(cls.name)

    test_methods: List[Stripped] = []

    for prop in cls.properties:
        if not (
            isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
            and isinstance(
                prop.type_annotation.value,
                (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
            )
        ):
            continue

        over_x_or_empty_name = python_naming.method_name(
            Identifier(f"over_{prop.name}_or_empty")
        )

        test_case_method_name = python_naming.method_name(
            Identifier(f"test_{over_x_or_empty_name}_against_recorded")
        )

        file_name = f"{over_x_or_empty_name}.trace"

        traced: Stripped
        if isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            if python_tests_common.contains_json(prop.type_annotation.value):
                traced = python_tests_common.generate_trace_argument(
                    type_annotation=prop.type_annotation.value,
                    expression=f"instance.{over_x_or_empty_name}()",
                )
            else:
                traced = Stripped(f"list(instance.{over_x_or_empty_name}())")
        elif isinstance(prop.type_annotation.value, intermediate.SetTypeAnnotation):
            # NOTE (mristin):
            # The order of the items of a set is undefined, so we sort the traces of
            # the items to make the test independent of it.
            traced = Stripped(
                f"""\
sorted(
{I}tests.common.trace(item)
{I}for item in instance.{over_x_or_empty_name}()
)"""
            )
        else:
            assert_never(prop.type_annotation.value)

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

{II}log = [
{III}tests.common.trace(
{IIII}{indent_but_first_line(traced, IIII)}
{III})
{II}]

{II}got_text = tests.common.trace_log_as_text_file_content(log)

{II}expected_path = pathlib.Path(
{III}tests.common.TEST_DATA_DIR
{III}/ "test_over_X_or_empty"
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
    Generate code to test the ``over_X_or_empty`` methods.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks = [
        Stripped(
            '''\
"""Test ``over_X_or_empty`` methods."""'''
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
