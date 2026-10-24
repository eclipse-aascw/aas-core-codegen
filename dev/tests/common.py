"""Provide common functionality across different tests."""
import difflib
import os
import pathlib
from typing import List, Tuple, Optional, Union, Sequence, Final, Set

import asttokens
from icontract import ensure, require

from aas_core_codegen import parse, intermediate
from aas_core_codegen.common import Error


def most_underlying_messages(error_or_errors: Union[Error, Sequence[Error]]) -> str:
    """Find the "leaf" errors and render them as a new-line separated list."""
    if isinstance(error_or_errors, Error):
        errors: Sequence[Error] = [error_or_errors]
    else:
        errors = error_or_errors

    most_underlying_errors: List[Error] = []

    for error in errors:
        if error.underlying is None or len(error.underlying) == 0:
            most_underlying_errors.append(error)
            continue

        stack: List[Error] = error.underlying

        while len(stack) > 0:
            top_error = stack.pop()

            if top_error.underlying is not None:
                stack.extend(top_error.underlying)

            if top_error.underlying is None or len(top_error.underlying) == 0:
                most_underlying_errors.append(top_error)

    return "\n".join(
        most_underlying_error.message
        for most_underlying_error in most_underlying_errors
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def parse_atok(
    atok: asttokens.ASTTokens,
) -> Tuple[Optional[parse.SymbolTable], Optional[Error]]:
    """Parse the ``atok``, an abstract syntax tree of a meta-model."""
    import_errors = parse.check_expected_imports(atok=atok)
    if len(import_errors) > 0:
        import_errors_str = "\n".join(
            f"* {import_error}" for import_error in import_errors
        )

        raise AssertionError(
            f"Unexpected imports in the source code:\n{import_errors_str}"
        )

    symbol_table, error = parse.atok_to_symbol_table(atok=atok)
    return symbol_table, error


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def parse_source(source: str) -> Tuple[Optional[parse.SymbolTable], Optional[Error]]:
    """Parse the given source text into a symbol table."""
    atok, parse_exception = parse.source_to_atok(source=source)
    if parse_exception:
        raise parse_exception

    assert atok is not None

    return parse_atok(atok=atok)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def translate_source_to_intermediate(
    source: str,
) -> Tuple[Optional[intermediate.SymbolTable], Optional[Error]]:
    atok, parse_exception = parse.source_to_atok(source=source)
    if parse_exception:
        raise parse_exception

    assert atok is not None

    parsed_symbol_table, error = parse_atok(atok=atok)
    assert error is None, f"{most_underlying_messages(error)}"
    assert parsed_symbol_table is not None

    return intermediate.translate(parsed_symbol_table=parsed_symbol_table, atok=atok)


def must_translate_source_to_intermediate(
    source: str,
) -> intermediate.SymbolTable:
    atok, parse_exception = parse.source_to_atok(source=source)
    if parse_exception:
        raise parse_exception

    assert atok is not None

    parsed_symbol_table, error = parse_atok(atok=atok)
    assert error is None, f"{most_underlying_messages(error)}"
    assert parsed_symbol_table is not None

    symbol_table, error = intermediate.translate(
        parsed_symbol_table=parsed_symbol_table, atok=atok
    )
    assert (
        error is None
    ), f"Unexpected error when parsing the source: {most_underlying_messages(error)}"
    assert symbol_table is not None
    return symbol_table


RERECORD_ENVIRONMENT_VARIABLE_NAME = "AAS_CORE_CODEGEN_TESTS_RERECORD"

#: If set, this environment variable indicates that the golden files should be
#: re-recorded instead of checked against.
RERECORD = os.environ.get(RERECORD_ENVIRONMENT_VARIABLE_NAME, "").lower() in (
    "1",
    "true",
    "on",
)

#: If set, the meta-models in test_main's will be cached in the temporary directory of
#: the OS.
CACHE_MAIN_MODELS = os.environ.get(
    "AAS_CORE_CODEGEN_TESTS_CACHE_MAIN_MODELS", ""
).lower() in ("1", "true", "on")


_REPO_ROOT: Final[pathlib.Path] = pathlib.Path(
    os.path.realpath(__file__)
).parent.parent.parent

COMMON_META_MODEL_PATHS: Final[Sequence[pathlib.Path]] = sorted(
    (_REPO_ROOT / "dev/test_data/common_meta_models").glob("*.py")
)


@require(lambda output_dir: output_dir.is_dir())
@require(lambda expected_output_dir: expected_output_dir.is_dir())
@require(lambda expected_output_dir: (expected_output_dir / "stdout.txt").exists())
def assert_got_as_expected_output_dir(
    output_dir: pathlib.Path, expected_output_dir: pathlib.Path, normalized_stdout: str
) -> None:
    """Assert that the recorded expected output coincides with the output."""
    output_files: Set[pathlib.Path] = set()
    for file_path in output_dir.rglob("*"):
        if file_path.is_file():
            output_files.add(file_path.relative_to(output_dir))

    expected_files: Set[pathlib.Path] = set()
    for file_path in expected_output_dir.rglob("*"):
        if file_path.is_file():
            expected_files.add(file_path.relative_to(expected_output_dir))

    # NOTE (mristin):
    # We check stdout.txt separately since it's not generated.
    stdout_rel_path = pathlib.Path("stdout.txt")
    if stdout_rel_path in expected_files:
        expected_stdout_path = expected_output_dir / stdout_rel_path
        try:
            expected_stdout = expected_stdout_path.read_text(encoding="utf-8")
        except Exception as exception:
            raise RuntimeError(
                f"Failed to read expected stdout from {expected_stdout_path}"
            ) from exception

        if normalized_stdout != expected_stdout:
            diff = "\n".join(
                difflib.unified_diff(
                    expected_stdout.splitlines(keepends=True),
                    normalized_stdout.splitlines(keepends=True),
                    fromfile=str(expected_stdout_path),
                    tofile="<actual stdout>",
                )
            )
            raise AssertionError(f"Mismatch against {expected_stdout_path}:\n{diff}")

        # NOTE (mristin):
        # We remove stdout.txt from expected_files since it's handled separately.
        expected_files.discard(stdout_rel_path)

    missing_files = expected_files - output_files
    if missing_files:
        missing_files_joined = "\n".join(f"{f}" for f in sorted(missing_files))
        raise AssertionError(
            f"Missing output files against {expected_output_dir}:\n"
            f"{missing_files_joined}"
        )

    # Check that no unexpected files exist in output
    unexpected_files = output_files - expected_files
    if unexpected_files:
        unexpected_list = "\n".join(f"  - {f}" for f in sorted(unexpected_files))
        raise AssertionError(
            f"Unexpected output files against {expected_output_dir}:\n"
            f"{unexpected_list}"
        )

    for rel_path in expected_files:
        expected_path = expected_output_dir / rel_path
        output_path = output_dir / rel_path

        try:
            expected_content = expected_path.read_text(encoding="utf-8")
        except Exception as exception:
            raise RuntimeError(
                f"Failed to read expected content from {expected_path}"
            ) from exception

        try:
            output_content = output_path.read_text(encoding="utf-8")
        except Exception as exception:
            raise RuntimeError(
                f"Failed to read output content from {output_path}"
            ) from exception

        if expected_content != output_content:
            diff = "\n".join(
                difflib.unified_diff(
                    expected_content.splitlines(keepends=True),
                    output_content.splitlines(keepends=True),
                    fromfile=str(expected_path),
                    tofile=str(output_path),
                )
            )
            raise AssertionError(f"File content mismatch in {rel_path}:\n{diff}")
