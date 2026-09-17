"""Generate implementations and schemas based on an AAS meta-model."""

import argparse
import enum
import pathlib
import sys
from typing import TextIO

import aas_core_codegen
import aas_core_codegen.csharp.main as csharp_main
import aas_core_codegen.cpp.main as cpp_main
import aas_core_codegen.golang.main as golang_main
import aas_core_codegen.java.main as java_main
import aas_core_codegen.jsonschema.main as jsonschema_main
import aas_core_codegen.python.main as python_main
import aas_core_codegen.typescript.main as typescript_main
import aas_core_codegen.xsd.main as xsd_main
from aas_core_codegen import run, specific_implementations
from aas_core_codegen.common import LinenoColumner, assert_never

assert aas_core_codegen.__doc__ == __doc__


class Target(enum.Enum):
    """List available target implementations."""

    CPP = "cpp"
    CSHARP = "csharp"
    GOLANG = "golang"
    JAVA = "java"
    JSONSCHEMA = "jsonschema"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    XSD = "xsd"


assert [target.name for target in Target] == sorted(
    another_target.name for another_target in Target
), f"{[target.name for target in Target]=}, {sorted(another_target.name for another_target in Target)=}"


class Parameters:
    """Represent the program parameters."""

    def __init__(
        self,
        model_path: pathlib.Path,
        target: Target,
        snippets_dir: pathlib.Path,
        output_dir: pathlib.Path,
        cache_model: bool = False,
    ) -> None:
        """Initialize with the given values."""
        self.model_path = model_path
        self.target = target
        self.snippets_dir = snippets_dir
        self.output_dir = output_dir
        self.cache_model = True


# noinspection SpellCheckingInspection
def execute(params: Parameters, stdout: TextIO, stderr: TextIO) -> int:
    """Run the program."""
    # region Basic checks
    if not params.model_path.exists():
        stderr.write(f"The --model_path does not exist: {params.model_path}\n")
        return 1

    if not params.model_path.is_file():
        stderr.write(
            f"The --model_path does not point to a file: {params.model_path}\n"
        )
        return 1

    if not params.snippets_dir.exists():
        stderr.write(f"The --snippets_dir does not exist: {params.snippets_dir}\n")
        return 1

    if not params.snippets_dir.is_dir():
        stderr.write(
            f"The --snippets_dir does not point to a directory: "
            f"{params.snippets_dir}\n"
        )
        return 1

    if not params.output_dir.exists():
        params.output_dir.mkdir(parents=True, exist_ok=True)
    else:
        if not params.output_dir.is_dir():
            stderr.write(
                f"The --output_dir does not point to a directory: "
                f"{params.output_dir}\n"
            )
            return 1

    # endregion

    # region Parse and understand

    spec_impls, spec_impls_errors = specific_implementations.read_from_directory(
        snippets_dir=params.snippets_dir
    )

    if spec_impls_errors:
        run.write_error_report(
            message="Failed to resolve the implementation-specific snippets",
            errors=spec_impls_errors,
            stderr=stderr,
        )
        return 1

    assert spec_impls is not None

    symbol_table_atok, error_message = run.load_model(
        model_path=params.model_path, cache_model=params.cache_model
    )
    if error_message is not None:
        stderr.write(error_message)
        return 1
    assert symbol_table_atok is not None

    ir_symbol_table, atok = symbol_table_atok

    # endregion

    # region Dispatch

    lineno_columner = LinenoColumner(atok=atok)

    run_context = run.Context(
        model_path=params.model_path,
        symbol_table=ir_symbol_table,
        spec_impls=spec_impls,
        lineno_columner=lineno_columner,
        output_dir=params.output_dir,
    )

    if params.target is Target.CSHARP:
        return csharp_main.execute(context=run_context, stdout=stdout, stderr=stderr)

    elif params.target is Target.CPP:
        return cpp_main.execute(context=run_context, stdout=stdout, stderr=stderr)

    elif params.target is Target.GOLANG:
        return golang_main.execute(context=run_context, stdout=stdout, stderr=stderr)

    elif params.target is Target.JAVA:
        return java_main.execute(context=run_context, stdout=stdout, stderr=stderr)

    elif params.target is Target.JSONSCHEMA:
        return jsonschema_main.execute(
            context=run_context, stdout=stdout, stderr=stderr
        )

    elif params.target is Target.PYTHON:
        return python_main.execute(context=run_context, stdout=stdout, stderr=stderr)

    elif params.target is Target.TYPESCRIPT:
        return typescript_main.execute(
            context=run_context, stdout=stdout, stderr=stderr
        )

    elif params.target is Target.XSD:
        return xsd_main.execute(context=run_context, stdout=stdout, stderr=stderr)

    else:
        assert_never(params.target)

    # endregion

    stdout.write(f"Code generated to: {params.output_dir}\n")
    return 0


def main(prog: str) -> int:
    """
    Execute the main routine.

    :param prog: name of the program to be displayed in the help
    :return: exit code
    """
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--model_path", help="path to the meta-model", required=True)
    parser.add_argument(
        "--snippets_dir",
        help="path to the directory containing implementation-specific code snippets",
        required=True,
    )
    parser.add_argument(
        "--output_dir", help="path to the generated code", required=True
    )
    parser.add_argument(
        "--target",
        help="target language or schema",
        required=True,
        choices=[literal.value for literal in Target],
    )
    parser.add_argument(
        "--cache_model",
        help=(
            "If set, cache the parsed meta-model in the temporary directory of your OS. "
            "This makes the repeated runs faster as the meta-model does not need to be "
            "reparsed."
        ),
        action="store_true",
    )
    parser.add_argument(
        "--version", help="show the current version and exit", action="store_true"
    )

    # NOTE (mristin):
    # The module ``argparse`` is not flexible enough to understand special options such
    # as ``--version`` so we manually hard-wire.
    if "--version" in sys.argv and "--help" not in sys.argv:
        print(aas_core_codegen.__version__)
        return 0

    args = parser.parse_args()

    target_to_str = {literal.value: literal for literal in Target}

    params = Parameters(
        model_path=pathlib.Path(args.model_path),
        target=target_to_str[args.target],
        snippets_dir=pathlib.Path(args.snippets_dir),
        output_dir=pathlib.Path(args.output_dir),
        cache_model=bool(args.cache_model),
    )

    return execute(params=params, stdout=sys.stdout, stderr=sys.stderr)


def entry_point() -> int:
    """Provide an entry point for a console script."""
    return main(prog="aas-core-codegen")


if __name__ == "__main__":
    sys.exit(main(prog="aas-core-codegen"))
