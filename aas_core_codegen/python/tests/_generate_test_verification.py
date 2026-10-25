"""Generate code to test the verification of valid and invalid instances."""

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
)


def _generate_test_verification_of_valid_instances(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the test class for verifying valid instances."""
    methods: List[Stripped] = []

    for cls in symbol_table.concrete_classes:
        method_name = python_naming.method_name(Identifier(f"test_{cls.name}"))

        from_jsonable = python_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        model_type = naming.json_model_type(cls.name)

        methods.append(
            Stripped(
                f"""\
def {method_name}(self) -> None:
{I}for path in sorted(
{II}(
{III}tests.common.TEST_DATA_DIR
{III}/ "Json"
{III}/ "Expected"
{III}/ {model_type!r}
{II}).glob("**/*.json")
{I}):
{II}with path.open("rt") as fid:
{III}jsonable = json.load(fid)

{II}instance = our_jsonization.{from_jsonable}(jsonable)

{II}errors = list(our_verification.verify(instance))

{II}if len(errors) > 0:
{III}self.fail(
{IIII}f"Expected no errors when verifying the instance de-serialized "
{IIII}f"from {{path}}, but got {{len(errors)}} error(s):\\n"
{IIII}+ "\\n".join(
{IIIII}f"{{error.path}}: {{error.cause}}" for error in errors
{IIII})
{III})"""
            )
        )

    body = "\n\n".join(methods) if methods else "# There are no concrete classes.\npass"

    return Stripped(
        f"""\
class TestVerificationOfValidInstances(unittest.TestCase):
{I}{indent_but_first_line(body, I)}"""
    )


def _generate_test_verification_of_invalid_instances(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the test class for verifying invalid instances."""
    methods: List[Stripped] = []

    for cls in symbol_table.concrete_classes:
        method_name = python_naming.method_name(Identifier(f"test_{cls.name}"))

        from_jsonable = python_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        model_type = naming.json_model_type(cls.name)

        methods.append(
            Stripped(
                f"""\
def {method_name}(self) -> None:
{I}for cause_dir in sorted(
{II}(
{III}tests.common.TEST_DATA_DIR
{III}/ "Json"
{III}/ "Unexpected"
{III}/ "Invalid"
{II}).iterdir()
{I}):
{II}for path in sorted(
{III}(cause_dir / {model_type!r}).glob("**/*.json")
{II}):
{III}rel_path = path.relative_to(tests.common.TEST_DATA_DIR)

{III}expected_path = (
{IIII}tests.common.TEST_DATA_DIR
{IIII}/ "VerificationError"
{IIII}/ rel_path.parent
{IIII}/ f"{{rel_path.name}}.errors"
{III})

{III}with path.open("rt") as fid:
{IIII}jsonable = json.load(fid)

{III}instance = our_jsonization.{from_jsonable}(jsonable)

{III}errors = list(our_verification.verify(instance))

{III}if len(errors) == 0:
{IIII}self.fail(
{IIIII}f"Expected at least one verification error "
{IIIII}f"when verifying the instance de-serialized "
{IIIII}f"from {{path}}, but got none"
{IIII})

{III}got = "\\n".join(
{IIII}f"{{error.path}}: {{error.cause}}" for error in errors
{III}) + "\\n"

{III}tests.common.record_or_check(expected_path, got)"""
            )
        )

    body = "\n\n".join(methods) if methods else "# There are no concrete classes.\npass"

    return Stripped(
        f"""\
class TestVerificationOfInvalidInstances(unittest.TestCase):
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
    Generate code to test the verification of valid and invalid instances.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    blocks: List[Stripped] = [
        Stripped('"""Test the verification of instances."""'),
        python_common.WARNING,
        Stripped(
            """\
import json
import unittest"""
        ),
        Stripped(
            f"""\
import {qualified_module_name}.jsonization as our_jsonization
import {qualified_module_name}.verification as our_verification"""
        ),
        Stripped("import tests.common"),
        _generate_test_verification_of_valid_instances(symbol_table=symbol_table),
        _generate_test_verification_of_invalid_instances(symbol_table=symbol_table),
        Stripped(
            f"""\
if __name__ == "__main__":
{I}unittest.main()"""
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
