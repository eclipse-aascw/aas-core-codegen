"""Generate Golang code based on the meta-model."""

import pathlib
from typing import TextIO, Sequence, Tuple, Callable, Optional, List

from aas_core_codegen import run, intermediate, specific_implementations, golang
from aas_core_codegen.common import Stripped, Error
from aas_core_codegen.golang import lib as golang_lib, tests as golang_tests


def execute(context: run.Context, stdout: TextIO, stderr: TextIO) -> int:
    """Generate code."""
    verified_ir_table, errors = golang_lib.verify_for_types(
        symbol_table=context.symbol_table
    )

    if errors is not None:
        run.write_error_report(
            message=f"Failed to verify the intermediate symbol table "
            f"for generation of Golang code "
            f"based on {context.model_path}",
            errors=[context.lineno_columner.error_message(error) for error in errors],
            stderr=stderr,
        )
        return 1

    assert verified_ir_table is not None

    unsupported_contracts_errors = (
        intermediate.errors_if_contracts_for_functions_or_methods_defined(
            verified_ir_table
        )
    )
    if unsupported_contracts_errors is not None:
        run.write_error_report(
            message=f"We do not support pre and post-conditions and snapshots "
            f"at the moment. Please notify the developers if you need this "
            f"feature (based on meta-model {context.model_path})",
            errors=[
                context.lineno_columner.error_message(error)
                for error in unsupported_contracts_errors
            ],
            stderr=stderr,
        )
        return 1

    unsupported_methods_errors = (
        intermediate.errors_if_non_implementation_specific_methods(verified_ir_table)
    )
    if unsupported_methods_errors is not None:
        run.write_error_report(
            message=f"We added some support for understood methods already and keep "
            f"maintaining it as it is only a matter of time when we will "
            f"introduce their transpilation. Introducing them after the fact "
            f"would have been much more difficult.\n"
            f"\n"
            f"At the given moment, however, we deliberately focus only on "
            f"implementation-specific methods. "
            f"(based on meta-model {context.model_path})",
            errors=[
                context.lineno_columner.error_message(error)
                for error in unsupported_methods_errors
            ],
            stderr=stderr,
        )
        return 1

    verification_functions_errors = golang_lib.verify_verification_functions(
        spec_impls=context.spec_impls,
        verification_functions=verified_ir_table.verification_functions,
    )

    if verification_functions_errors is not None:
        run.write_error_report(
            message="Failed to verify for the generation of Golang verification code",
            errors=verification_functions_errors,
            stderr=stderr,
        )
        return 1

    # region Repo URL

    repo_url_key = specific_implementations.ImplementationKey("repo_url.txt")
    repo_url_text = context.spec_impls.get(repo_url_key, None)
    if repo_url_text is None:
        stderr.write(f"The repo URL snippet is missing: {repo_url_key}\n")
        return 1

    repo_url = Stripped(repo_url_text.strip())

    # endregion

    base_rel_path = pathlib.Path(".")
    assert not base_rel_path.is_absolute()

    rel_paths_generators: Sequence[
        Tuple[pathlib.Path, Callable[[], Tuple[Optional[str], Optional[List[Error]]]]]
    ] = [
        (
            base_rel_path / "common/common.go",
            lambda: (golang_lib.generate_common(), None),
        ),
        (
            base_rel_path / "constants/constants.go",
            lambda: golang_lib.generate_constants(
                symbol_table=context.symbol_table, repo_url=repo_url
            ),
        ),
        (
            base_rel_path / "enhancing/enhancing.go",
            lambda: golang_lib.generate_enhancing(
                symbol_table=context.symbol_table,
                spec_impls=context.spec_impls,
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "jsonization/jsonization.go",
            lambda: golang_lib.generate_jsonization(
                symbol_table=context.symbol_table,
                spec_impls=context.spec_impls,
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "reporting/reporting.go",
            lambda: (golang_lib.generate_reporting(), None),
        ),
        (
            base_rel_path / "stringification/stringification.go",
            lambda: golang_lib.generate_stringification(
                symbol_table=context.symbol_table, repo_url=repo_url
            ),
        ),
        (
            base_rel_path / "types/types.go",
            lambda: golang_lib.generate_types(
                symbol_table=verified_ir_table,
                spec_impls=context.spec_impls,
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "verification/verification.go",
            lambda: golang_lib.generate_verification(
                symbol_table=verified_ir_table,
                spec_impls=context.spec_impls,
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "xmlization/xmlization.go",
            lambda: golang_lib.generate_xmlization(
                symbol_table=context.symbol_table,
                spec_impls=context.spec_impls,
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "aastesting/common_jsonization.go",
            lambda: (
                golang_tests.generate_aastesting_common_jsonization(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "aastesting/constants.go",
            lambda: (
                golang_tests.generate_aastesting_constants(repo_url=repo_url),
                None,
            ),
        ),
        (
            base_rel_path / "aastesting/deep_equal.go",
            lambda: (
                golang_tests.generate_aastesting_deep_equal(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "aastesting/doc.go",
            lambda: (golang_tests.generate_aastesting_doc(), None),
        ),
        (
            base_rel_path / "aastesting/filesystem.go",
            lambda: (golang_tests.generate_aastesting_filesystem(), None),
        ),
        (
            base_rel_path / "aastesting/tracing.go",
            lambda: (
                golang_tests.generate_aastesting_tracing(repo_url=repo_url),
                None,
            ),
        ),
        (
            base_rel_path / "enhancing/test/enhancing_test.go",
            lambda: (
                golang_tests.generate_enhancing_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "jsonization/test/classes_with_descendants_test.go",
            lambda: (
                golang_tests.generate_jsonization_test_classes_with_descendants_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "jsonization/test/common_test.go",
            lambda: (
                golang_tests.generate_jsonization_test_common_test(repo_url=repo_url),
                None,
            ),
        ),
        (
            base_rel_path / "jsonization/test/concrete_classes_test.go",
            lambda: (
                golang_tests.generate_jsonization_test_concrete_classes_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "jsonization/test/enums_test.go",
            lambda: (
                golang_tests.generate_jsonization_test_enums_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "types/descend_test/common.go",
            lambda: (
                golang_tests.generate_descend_test_common(repo_url=repo_url),
                None,
            ),
        ),
        (
            base_rel_path / "types/descend_test/descend_once_test.go",
            lambda: (
                golang_tests.generate_descend_test_descend_once_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "types/descend_test/descend_test.go",
            lambda: (
                golang_tests.generate_descend_test_descend_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "types/is_xxx_test/is_xxx_test.go",
            lambda: (
                golang_tests.generate_is_xxx_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "types/xxx_or_default_test/xxx_or_default_test.go",
            lambda: (
                golang_tests.generate_xxx_or_default_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "verification/test/verification_test.go",
            lambda: (
                golang_tests.generate_verification_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "xmlization/test/common_test.go",
            lambda: (
                golang_tests.generate_xmlization_test_common_test(repo_url=repo_url),
                None,
            ),
        ),
        (
            base_rel_path / "xmlization/test/concrete_classes_test.go",
            lambda: (
                golang_tests.generate_xmlization_test_concrete_classes_test(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
    ]

    for rel_path, generator_func in rel_paths_generators:
        assert not rel_path.is_absolute()

        code, errors = generator_func()

        if errors is not None:
            run.write_error_report(
                message=f"Failed to generate {rel_path} "
                f"based on {context.model_path}",
                errors=[
                    context.lineno_columner.error_message(error) for error in errors
                ],
                stderr=stderr,
            )
            return 1

        assert code is not None

        pth = context.output_dir / rel_path

        try:
            pth.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exception:
            run.write_error_report(
                message=f"Failed to create the directory {pth.parent}",
                errors=[str(exception)],
                stderr=stderr,
            )
            return 1

        try:
            pth.write_text(code, encoding="utf-8")
        except Exception as exception:
            run.write_error_report(
                message=f"Failed to write to {pth}",
                errors=[str(exception)],
                stderr=stderr,
            )
            return 1

    stdout.write(f"Code generated to: {context.output_dir}\n")
    return 0


assert golang.__doc__ == __doc__
