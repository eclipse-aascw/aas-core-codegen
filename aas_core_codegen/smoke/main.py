# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Run a smoke-test as a preliminary test that a meta-model is ready for generation."""

import argparse
import io
import pathlib
import sys
import tempfile
import xml.sax.saxutils
from typing import Iterator, Mapping, TextIO

import aas_core_codegen
import aas_core_codegen.smoke
from aas_core_codegen import (
    parse,
    run,
    intermediate,
    infer_for_schema,
    specific_implementations,
)
from aas_core_codegen.common import LinenoColumner, Stripped
from aas_core_codegen.cpp import main as cpp_main
from aas_core_codegen.csharp import main as csharp_main
from aas_core_codegen.golang import main as golang_main
from aas_core_codegen.java import main as java_main
from aas_core_codegen.jsonschema import main as jsonschema_main
from aas_core_codegen.python import main as python_main
from aas_core_codegen.typescript import main as typescript_main
from aas_core_codegen.xsd import main as xsd_main

assert __doc__ == aas_core_codegen.smoke.__doc__


class _SnippetsWithDummies(
    Mapping[specific_implementations.ImplementationKey, Stripped]
):
    """
    Map the given ``snippets``, and every other key to a dummy snippet.

    The generators only look up the snippets with ``in`` and ``get``, so we do not
    have to replicate the snippet keys of each target here.
    """

    def __init__(
        self, snippets: Mapping[specific_implementations.ImplementationKey, Stripped]
    ) -> None:
        """Initialize with the given values."""
        self.snippets = snippets

    def __getitem__(self, key: specific_implementations.ImplementationKey) -> Stripped:
        return self.snippets.get(key, Stripped("DUMMY IMPLEMENTATION"))

    def __iter__(self) -> Iterator[specific_implementations.ImplementationKey]:
        # NOTE (mristin):
        # We can not enumerate all the possible keys, so we enumerate only
        # the given snippets.
        return iter(self.snippets)

    def __len__(self) -> int:
        return len(self.snippets)


def _smoke_generate_cpp(context: run.Context, stderr: TextIO) -> int:
    """Generate C++ to ``context.output_dir``, and report the errors, if any."""
    cpp_stderr = io.StringIO()

    return_code = cpp_main.execute(
        context=context, stdout=io.StringIO(), stderr=cpp_stderr
    )

    if return_code != 0:
        run.write_error_report(
            message=f"Failed to smoke-generate C++ based on {context.model_path}",
            errors=[cpp_stderr.getvalue().rstrip()],
            stderr=stderr,
        )

    return return_code


def _smoke_generate_csharp(context: run.Context, stderr: TextIO) -> int:
    """Generate C# to ``context.output_dir``, and report the errors, if any."""
    csharp_stderr = io.StringIO()

    return_code = csharp_main.execute(
        context=context, stdout=io.StringIO(), stderr=csharp_stderr
    )

    if return_code != 0:
        run.write_error_report(
            message=f"Failed to smoke-generate C# based on {context.model_path}",
            errors=[csharp_stderr.getvalue().rstrip()],
            stderr=stderr,
        )

    return return_code


def _smoke_generate_golang(context: run.Context, stderr: TextIO) -> int:
    """Generate Go to ``context.output_dir``, and report the errors, if any."""
    golang_stderr = io.StringIO()

    return_code = golang_main.execute(
        context=context, stdout=io.StringIO(), stderr=golang_stderr
    )

    if return_code != 0:
        run.write_error_report(
            message=f"Failed to smoke-generate Go based on {context.model_path}",
            errors=[golang_stderr.getvalue().rstrip()],
            stderr=stderr,
        )

    return return_code


def _smoke_generate_java(context: run.Context, stderr: TextIO) -> int:
    """Generate Java to ``context.output_dir``, and report the errors, if any."""
    java_stderr = io.StringIO()

    return_code = java_main.execute(
        context=context, stdout=io.StringIO(), stderr=java_stderr
    )

    if return_code != 0:
        run.write_error_report(
            message=f"Failed to smoke-generate Java based on {context.model_path}",
            errors=[java_stderr.getvalue().rstrip()],
            stderr=stderr,
        )

    return return_code


def _smoke_generate_jsonschema(context: run.Context, stderr: TextIO) -> int:
    """Generate JSON Schema to ``context.output_dir``, and report the errors, if any."""
    jsonschema_stderr = io.StringIO()

    return_code = jsonschema_main.execute(
        context=context, stdout=io.StringIO(), stderr=jsonschema_stderr
    )

    if return_code != 0:
        run.write_error_report(
            message=f"Failed to smoke-generate JSON Schema based on {context.model_path}",
            errors=[jsonschema_stderr.getvalue().rstrip()],
            stderr=stderr,
        )

    return return_code


def _smoke_generate_python(context: run.Context, stderr: TextIO) -> int:
    """Generate Python to ``context.output_dir``, and report the errors, if any."""
    python_stderr = io.StringIO()

    return_code = python_main.execute(
        context=context, stdout=io.StringIO(), stderr=python_stderr
    )

    if return_code != 0:
        run.write_error_report(
            message=f"Failed to smoke-generate Python based on {context.model_path}",
            errors=[python_stderr.getvalue().rstrip()],
            stderr=stderr,
        )

    return return_code


def _smoke_generate_typescript(context: run.Context, stderr: TextIO) -> int:
    """Generate TypeScript to ``context.output_dir``, and report the errors, if any."""
    typescript_stderr = io.StringIO()

    return_code = typescript_main.execute(
        context=context, stdout=io.StringIO(), stderr=typescript_stderr
    )

    if return_code != 0:
        run.write_error_report(
            message=f"Failed to smoke-generate TypeScript based on {context.model_path}",
            errors=[typescript_stderr.getvalue().rstrip()],
            stderr=stderr,
        )

    return return_code


def _smoke_generate_xsd(context: run.Context, stderr: TextIO) -> int:
    """Generate XSD to ``context.output_dir``, and report the errors, if any."""
    xsd_stderr = io.StringIO()

    return_code = xsd_main.execute(
        context=context, stdout=io.StringIO(), stderr=xsd_stderr
    )

    if return_code != 0:
        run.write_error_report(
            message=f"Failed to smoke-generate XSD based on {context.model_path}",
            errors=[xsd_stderr.getvalue().rstrip()],
            stderr=stderr,
        )

    return return_code


def execute(model_path: pathlib.Path, stderr: TextIO) -> int:
    """Run the smoke test."""
    text = model_path.read_text(encoding="utf-8")

    atok, parse_exception = parse.source_to_atok(source=text)
    if parse_exception:
        if isinstance(parse_exception, SyntaxError):
            stderr.write(
                f"Failed to parse the meta-model {model_path}: "
                f"invalid syntax at line {parse_exception.lineno}\n"
            )
        else:
            stderr.write(
                f"Failed to parse the meta-model {model_path}: {parse_exception}\n"
            )

        return 1

    assert atok is not None

    import_errors = parse.check_expected_imports(atok=atok)
    if import_errors:
        run.write_error_report(
            message="One or more unexpected imports in the meta-model",
            errors=import_errors,
            stderr=stderr,
        )

        return 1

    lineno_columner = LinenoColumner(atok=atok)

    parsed_symbol_table, error = parse.atok_to_symbol_table(atok=atok)
    if error is not None:
        run.write_error_report(
            message=f"Failed to construct the symbol table from {model_path}",
            errors=[lineno_columner.error_message(error)],
            stderr=stderr,
        )

        return 1

    assert parsed_symbol_table is not None

    ir_symbol_table, error = intermediate.translate(
        parsed_symbol_table=parsed_symbol_table,
        atok=atok,
    )
    if error is not None:
        run.write_error_report(
            message=f"Failed to translate the parsed symbol table "
            f"to intermediate symbol table "
            f"based on {model_path}",
            errors=[lineno_columner.error_message(error)],
            stderr=stderr,
        )

        return 1

    assert ir_symbol_table is not None

    constraints_by_class, errors = infer_for_schema.infer_constraints_by_class(
        symbol_table=ir_symbol_table
    )
    if errors is not None:
        run.write_error_report(
            message=f"Failed to infer the constraints by class for the schemas "
            f"based on {model_path}",
            errors=[lineno_columner.error_message(error) for error in errors],
            stderr=stderr,
        )

        return 1

    assert constraints_by_class is not None

    unsupported_contracts_errors = (
        intermediate.errors_if_contracts_for_functions_or_methods_defined(
            ir_symbol_table
        )
    )
    if unsupported_contracts_errors is not None:
        run.write_error_report(
            message=f"We do not support pre and post-conditions and snapshots "
            f"at the moment in any of the generators "
            f"(based on meta-model {model_path})",
            errors=[
                lineno_columner.error_message(error)
                for error in unsupported_contracts_errors
            ],
            stderr=stderr,
        )

        return 1

    # NOTE (mristin):
    # The generators parse and check some of the snippets, so we provide valid
    # ones. The rest are dummies.
    xml_namespace = xml.sax.saxutils.quoteattr(ir_symbol_table.meta_model.xml_namespace)

    spec_impls = _SnippetsWithDummies(
        {
            # NOTE (mristin):
            # The namespace is shared between C++ and C#.
            specific_implementations.ImplementationKey("namespace.txt"): Stripped(
                "dummy"
            ),
            specific_implementations.ImplementationKey("repo_url.txt"): Stripped(
                "example.com/dummy"
            ),
            specific_implementations.ImplementationKey("package.txt"): Stripped(
                "dummy"
            ),
            specific_implementations.ImplementationKey(
                "qualified_module_name.txt"
            ): Stripped("dummy"),
            specific_implementations.ImplementationKey("schema_base.json"): Stripped(
                '{"$schema": "https://json-schema.org/draft/2019-09/schema"}'
            ),
            specific_implementations.ImplementationKey("root_element.xml"): Stripped(
                f"""\
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns={xml_namespace}
    elementFormDefault="qualified"
    targetNamespace={xml_namespace}
/>"""
            ),
        }
    )

    # NOTE (mristin):
    # We smoke-generate all the targets, even if one of them fails, so that
    # the developers of the meta-model see all the problems at once.
    return_code = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        cpp_output_dir = pathlib.Path(tmp_dir) / "cpp"
        cpp_output_dir.mkdir()

        cpp_return_code = _smoke_generate_cpp(
            context=run.Context(
                model_path=model_path,
                symbol_table=ir_symbol_table,
                spec_impls=spec_impls,
                lineno_columner=lineno_columner,
                output_dir=cpp_output_dir,
            ),
            stderr=stderr,
        )
        if cpp_return_code != 0:
            return_code = 1

        csharp_output_dir = pathlib.Path(tmp_dir) / "csharp"
        csharp_output_dir.mkdir()

        csharp_return_code = _smoke_generate_csharp(
            context=run.Context(
                model_path=model_path,
                symbol_table=ir_symbol_table,
                spec_impls=spec_impls,
                lineno_columner=lineno_columner,
                output_dir=csharp_output_dir,
            ),
            stderr=stderr,
        )
        if csharp_return_code != 0:
            return_code = 1

        golang_output_dir = pathlib.Path(tmp_dir) / "golang"
        golang_output_dir.mkdir()

        golang_return_code = _smoke_generate_golang(
            context=run.Context(
                model_path=model_path,
                symbol_table=ir_symbol_table,
                spec_impls=spec_impls,
                lineno_columner=lineno_columner,
                output_dir=golang_output_dir,
            ),
            stderr=stderr,
        )
        if golang_return_code != 0:
            return_code = 1

        java_output_dir = pathlib.Path(tmp_dir) / "java"
        java_output_dir.mkdir()

        java_return_code = _smoke_generate_java(
            context=run.Context(
                model_path=model_path,
                symbol_table=ir_symbol_table,
                spec_impls=spec_impls,
                lineno_columner=lineno_columner,
                output_dir=java_output_dir,
            ),
            stderr=stderr,
        )
        if java_return_code != 0:
            return_code = 1

        jsonschema_output_dir = pathlib.Path(tmp_dir) / "jsonschema"
        jsonschema_output_dir.mkdir()

        jsonschema_return_code = _smoke_generate_jsonschema(
            context=run.Context(
                model_path=model_path,
                symbol_table=ir_symbol_table,
                spec_impls=spec_impls,
                lineno_columner=lineno_columner,
                output_dir=jsonschema_output_dir,
            ),
            stderr=stderr,
        )
        if jsonschema_return_code != 0:
            return_code = 1

        python_output_dir = pathlib.Path(tmp_dir) / "python"
        python_output_dir.mkdir()

        python_return_code = _smoke_generate_python(
            context=run.Context(
                model_path=model_path,
                symbol_table=ir_symbol_table,
                spec_impls=spec_impls,
                lineno_columner=lineno_columner,
                output_dir=python_output_dir,
            ),
            stderr=stderr,
        )
        if python_return_code != 0:
            return_code = 1

        typescript_output_dir = pathlib.Path(tmp_dir) / "typescript"
        typescript_output_dir.mkdir()

        typescript_return_code = _smoke_generate_typescript(
            context=run.Context(
                model_path=model_path,
                symbol_table=ir_symbol_table,
                spec_impls=spec_impls,
                lineno_columner=lineno_columner,
                output_dir=typescript_output_dir,
            ),
            stderr=stderr,
        )
        if typescript_return_code != 0:
            return_code = 1

        xsd_output_dir = pathlib.Path(tmp_dir) / "xsd"
        xsd_output_dir.mkdir()

        xsd_return_code = _smoke_generate_xsd(
            context=run.Context(
                model_path=model_path,
                symbol_table=ir_symbol_table,
                spec_impls=spec_impls,
                lineno_columner=lineno_columner,
                output_dir=xsd_output_dir,
            ),
            stderr=stderr,
        )
        if xsd_return_code != 0:
            return_code = 1

    return return_code


def main(prog: str) -> int:
    """Execute the main routine."""
    # NOTE (mristin):
    # The module ``argparse`` is not flexible enough to understand special options such
    # as ``--version`` so we manually hard-wire.
    if "--version" in sys.argv and "--help" not in sys.argv:
        print(aas_core_codegen.__version__)
        return 0

    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--model_path", help="path to the meta-model", required=True)
    parser.add_argument(
        "--version", help="show the current version and exit", action="store_true"
    )
    args = parser.parse_args()

    return execute(model_path=pathlib.Path(args.model_path), stderr=sys.stderr)


def entry_point() -> int:
    """Provide an entry point for a console script."""
    return main(prog="aas-core-codegen-smoke")


if __name__ == "__main__":
    sys.exit(main(prog="aas-core-codegen-smoke"))
