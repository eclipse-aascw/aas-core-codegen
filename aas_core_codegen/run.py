"""Encapsulate the entry point to different generators."""
import hashlib
import io
import pathlib
import pickle
import tempfile
import textwrap
import uuid
from typing import Sequence, TextIO, Tuple, Optional, Final

import asttokens
from icontract import require, ensure

import aas_core_codegen
from aas_core_codegen import specific_implementations, intermediate, parse
from aas_core_codegen.common import LinenoColumner


class Context:
    """Represent the context of a code generation."""

    @require(lambda model_path: model_path.exists() and model_path.is_file())
    @require(lambda output_dir: output_dir.exists() and output_dir.is_dir())
    def __init__(
        self,
        model_path: pathlib.Path,
        symbol_table: intermediate.SymbolTable,
        spec_impls: specific_implementations.SpecificImplementations,
        lineno_columner: LinenoColumner,
        output_dir: pathlib.Path,
    ) -> None:
        """Initialize with the given values."""
        self.model_path = model_path
        self.symbol_table = symbol_table
        self.spec_impls = spec_impls
        self.lineno_columner = lineno_columner
        self.output_dir = output_dir


@require(
    lambda errors: all(
        len(error) > 0 and not error.startswith("\n")
        # This is necessary so that we do not have double bullet point.
        and not error.startswith("*") and not error.endswith("\n")
        for error in errors
    )
)
@require(lambda message: not message.endswith(":"))
@require(lambda message: not message.endswith("\n"))
@require(lambda message: not message.startswith("\n") and not message.startswith("*"))
# fmt: on
def write_error_report(message: str, errors: Sequence[str], stderr: TextIO) -> None:
    """
    Write the report (main ``message`` and details as ``errors``) to ``stderr``.

    This method helps us to have a unified way of showing errors.
    """
    stderr.write(f"{message}:\n")
    for error in errors:
        indented = textwrap.indent(error, "  ")
        indented = "* " + indented[2:]
        stderr.write(f"{indented}\n")


class _Cached:
    symbol_table: Final[intermediate.SymbolTable]
    atok: Final[asttokens.ASTTokens]

    def __init__(
        self, symbol_table: intermediate.SymbolTable, atok: asttokens.ASTTokens
    ) -> None:
        self.symbol_table = symbol_table
        self.atok = atok


@require(lambda model_path: model_path.exists() and model_path.is_file())
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def load_model(
    model_path: pathlib.Path, cache_model: bool = False
) -> Tuple[
    Optional[Tuple[intermediate.SymbolTable, asttokens.ASTTokens]], Optional[str]
]:
    """
    Load the given meta-model from the file system and understand it.

    If the ``cache_model`` is set, the symbol table will be stored in the temporary
    directory of your OS keyed on the hash of the model source code and of the code
    which translates it. On subsequent calls to this function, the model will be
    loaded from the cache instead of reparsed as long as neither of them changed.
    """
    text = model_path.read_text(encoding="utf-8")

    cache_path: Optional[pathlib.Path] = None
    if cache_model:
        hasher = hashlib.sha256()

        # NOTE (mristin):
        # We include the code of the parse and intermediate stages in the key so that
        # the cache is invalidated when we change them, and so that the checkouts in
        # different worktrees do not share stale pickles. This is the closed set of
        # modules which the translation imports, including ``_Cached`` in this module.
        package_dir = pathlib.Path(aas_core_codegen.__file__).parent
        code_paths = sorted(
            [
                *(package_dir / "parse").rglob("*.py"),
                *(package_dir / "intermediate").rglob("*.py"),
                package_dir / "common.py",
                package_dir / "naming.py",
                package_dir / "stringify.py",
                package_dir / "run.py",
            ]
        )
        for code_path in code_paths:
            hasher.update(code_path.relative_to(package_dir).as_posix().encode())
            hasher.update(code_path.read_bytes())

        hasher.update(text.encode())

        cache_path = (
            pathlib.Path(tempfile.gettempdir())
            / f"aas-core-codegen-{aas_core_codegen.__version__}"
            / f"model-{hasher.hexdigest()}.pickle"
        )

    if cache_path is not None:
        if cache_path.exists():
            with cache_path.open("rb") as fid:
                cached = pickle.load(fid)
                assert isinstance(cached, _Cached)

                return (cached.symbol_table, cached.atok), None

    atok, parse_exception = parse.source_to_atok(source=text)
    if parse_exception:
        if isinstance(parse_exception, SyntaxError):
            return None, (
                f"Failed to parse the meta-model: "
                f"invalid syntax at line {parse_exception.lineno}"
            )
        else:
            return None, f"Failed to parse the meta-model: {parse_exception}"

    assert atok is not None

    import_errors = parse.check_expected_imports(atok=atok)
    if import_errors:
        writer = io.StringIO()
        write_error_report(
            message="One or more unexpected imports in the meta-model",
            errors=import_errors,
            stderr=writer,
        )
        return None, writer.getvalue()

    lineno_columner = LinenoColumner(atok=atok)

    parsed_symbol_table, error = parse.atok_to_symbol_table(atok=atok)
    if error is not None:
        writer = io.StringIO()
        write_error_report(
            message="Failed to construct the symbol table",
            errors=[lineno_columner.error_message(error)],
            stderr=writer,
        )
        return None, writer.getvalue()

    assert parsed_symbol_table is not None

    ir_symbol_table, error = intermediate.translate(
        parsed_symbol_table=parsed_symbol_table,
        atok=atok,
    )
    if error is not None:
        writer = io.StringIO()
        write_error_report(
            message=(
                "Failed to translate the parsed symbol table "
                "to intermediate symbol table"
            ),
            errors=[lineno_columner.error_message(error)],
            stderr=writer,
        )
        return None, writer.getvalue()

    assert ir_symbol_table is not None

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = cache_path.with_suffix(f".{uuid.uuid4()}.tmp")
        try:
            with tmp_path.open("wb") as fid:
                pickle.dump(_Cached(symbol_table=ir_symbol_table, atok=atok), fid)

            tmp_path.rename(cache_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    return (ir_symbol_table, atok), None
