"""Generate Golang code based on the meta-model."""

import pathlib
from typing import TextIO, Sequence, Tuple, Callable, Optional, List

from aas_core_codegen import run, intermediate, specific_implementations, golang
from aas_core_codegen.common import Stripped, Error
from aas_core_codegen.golang import lib as golang_lib, tests as golang_tests
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
)


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

    type_inference, inference_errors = intermediate_type_inference.infer(
        symbol_table=verified_ir_table
    )
    if inference_errors is not None:
        run.write_error_report(
            message=f"Failed to infer the types in the meta-model {context.model_path}",
            errors=[
                context.lineno_columner.error_message(error)
                for error in inference_errors
            ],
            stderr=stderr,
        )
        return 1

    assert type_inference is not None

    # region Repo URL

    repo_url_key = specific_implementations.ImplementationKey("repo_url.txt")
    repo_url_text = context.spec_impls.get(repo_url_key, None)
    if repo_url_text is None:
        stderr.write(f"The repo URL snippet is missing: {repo_url_key}\n")
        return 1

    repo_url = Stripped(repo_url_text.strip())

    # endregion

    base_rel_path = pathlib.Path()
    assert not base_rel_path.is_absolute()

    rel_paths_generators: Sequence[
        Tuple[pathlib.Path, Callable[[], Tuple[Optional[str], Optional[List[Error]]]]]
    ] = [
        (
            base_rel_path / "common/common.go",
            lambda: (
                golang_lib.generate_common(
                    symbol_table=context.symbol_table, type_inference=type_inference
                ),
                None,
            ),
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
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "jsonization/jsonization.go",
            lambda: golang_lib.generate_jsonization(
                symbol_table=context.symbol_table,
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
                type_inference=type_inference,
                spec_impls=context.spec_impls,
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "verification/verification.go",
            lambda: golang_lib.generate_verification(
                symbol_table=verified_ir_table,
                type_inference=type_inference,
                spec_impls=context.spec_impls,
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "internal/xmlcommon/xmlcommon.go",
            lambda: (
                golang_lib.generate_xml_common(
                    symbol_table=context.symbol_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "xmlization/xmlization.go",
            lambda: golang_lib.generate_xmlization(
                symbol_table=context.symbol_table,
                repo_url=repo_url,
            ),
        ),
        (
            base_rel_path / "ourtesting/common_jsonization.go",
            lambda: (
                golang_tests.generate_ourtesting_common_jsonization(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "ourtesting/constants.go",
            lambda: (
                golang_tests.generate_ourtesting_constants(repo_url=repo_url),
                None,
            ),
        ),
        (
            base_rel_path / "ourtesting/deep_equal.go",
            lambda: (
                golang_tests.generate_ourtesting_deep_equal(
                    symbol_table=verified_ir_table, repo_url=repo_url
                ),
                None,
            ),
        ),
        (
            base_rel_path / "ourtesting/doc.go",
            lambda: (golang_tests.generate_ourtesting_doc(), None),
        ),
        (
            base_rel_path / "ourtesting/filesystem.go",
            lambda: (golang_tests.generate_ourtesting_filesystem(), None),
        ),
        (
            base_rel_path / "ourtesting/tracing.go",
            lambda: (
                golang_tests.generate_ourtesting_tracing(repo_url=repo_url),
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

    # NOTE (mristin):
    # The ``xmlrpc`` package is only needed when the meta-model actually uses
    # a JSON-able type (``JSONValue``, ``JSONArray`` or ``JSONObject[K]``) --
    # unlike the other packages above, which are always generated regardless of
    # the model. The same holds for the tests of the JSON-able values.
    if intermediate_uses.json_types(context.symbol_table):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                base_rel_path / "xmlrpc/xmlrpc.go",
                lambda: (golang_lib.generate_xml_rpc(repo_url=repo_url), None),
            ),
            (
                base_rel_path / "jsonization/test/json_value_test.go",
                lambda: (
                    golang_tests.generate_jsonization_test_json_value_test(
                        repo_url=repo_url
                    ),
                    None,
                ),
            ),
        ]

    # NOTE (mristin):
    # The helpers for ``len``, slicing strings and ``find`` are only generated for
    # a meta-model which uses them, and so are their tests. We also test
    # the native comparison and stripping of strings so that the users can inspect
    # the same cases in all the SDKs.
    if intermediate_uses.string_operations(type_inference):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                base_rel_path / "common/string_helpers_test/string_helpers_test.go",
                lambda: (
                    golang_tests.generate_string_helpers_test(
                        repo_url=repo_url, type_inference=type_inference
                    ),
                    None,
                ),
            ),
        ]

    # NOTE (mristin):
    # We test the arithmetic operations only if the meta-model uses them, as we
    # generate the helper functions only in that case.
    if intermediate_uses.modulo(context.symbol_table) or intermediate_uses.abs_call(
        context.symbol_table
    ):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                base_rel_path / "common/arithmetic_test/arithmetic_test.go",
                lambda: (
                    golang_tests.generate_arithmetic_test(
                        symbol_table=verified_ir_table, repo_url=repo_url
                    ),
                    None,
                ),
            ),
        ]

    # NOTE (mristin):
    # We test ``int`` only if the meta-model uses it, as we generate its helper
    # function only in that case.
    if intermediate_uses.int_call(context.symbol_table):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                base_rel_path / "common/parse_int_test/parse_int_test.go",
                lambda: (
                    golang_tests.generate_parse_int_test(
                        symbol_table=verified_ir_table, repo_url=repo_url
                    ),
                    None,
                ),
            ),
        ]

    # NOTE (mristin):
    # We test the safe integer range whenever the SDK checks it, see
    # :py:func:`intermediate_uses.safe_integer_checks`.
    if intermediate_uses.safe_integer_checks(context.symbol_table):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                base_rel_path / "common/safe_integer_test/safe_integer_test.go",
                lambda: (
                    golang_tests.generate_safe_integer_test(
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
