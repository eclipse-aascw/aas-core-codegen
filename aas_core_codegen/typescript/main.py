"""Generate TypeScript code based on the meta-model."""

import pathlib
from typing import TextIO, Sequence, Tuple, Callable, Optional, List

from aas_core_codegen import run, intermediate, typescript
from aas_core_codegen.common import Error
from aas_core_codegen.typescript import lib as typescript_lib, tests as typescript_tests


def execute(context: run.Context, stdout: TextIO, stderr: TextIO) -> int:
    """Generate code."""
    verified_ir_table, errors = typescript_lib.verify_for_types(
        symbol_table=context.symbol_table
    )

    if errors is not None:
        run.write_error_report(
            message=f"Failed to verify the intermediate symbol table "
            f"for generation of TypeScript code "
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

    verification_functions_errors = typescript_lib.verify_verification_functions(
        spec_impls=context.spec_impls,
        verification_functions=verified_ir_table.verification_functions,
    )

    if verification_functions_errors is not None:
        run.write_error_report(
            message=(
                "Failed to verify for the generation of TypeScript verification "
                "functions code"
            ),
            errors=verification_functions_errors,
            stderr=stderr,
        )
        return 1

    src_rel_path = pathlib.Path("src")
    assert not src_rel_path.is_absolute()

    test_rel_path = pathlib.Path("test")
    assert not test_rel_path.is_absolute()

    rel_paths_generators: Sequence[
        Tuple[pathlib.Path, Callable[[], Tuple[Optional[str], Optional[List[Error]]]]]
    ] = [
        (src_rel_path / "common.ts", lambda: (typescript_lib.generate_common(), None)),
        (
            src_rel_path / "constants.ts",
            lambda: typescript_lib.generate_constants(
                symbol_table=context.symbol_table
            ),
        ),
        (
            src_rel_path / "index.ts",
            lambda: typescript_lib.generate_index(
                spec_impls=context.spec_impls,
            ),
        ),
        (
            src_rel_path / "jsonization.ts",
            lambda: typescript_lib.generate_jsonization(
                symbol_table=context.symbol_table,
            ),
        ),
        (
            src_rel_path / "xmlization.ts",
            lambda: typescript_lib.generate_xmlization(
                symbol_table=context.symbol_table,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            src_rel_path / "stringification.ts",
            lambda: typescript_lib.generate_stringification(
                symbol_table=context.symbol_table
            ),
        ),
        (
            src_rel_path / "types.ts",
            lambda: typescript_lib.generate_types(
                symbol_table=verified_ir_table,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            src_rel_path / "verification.ts",
            lambda: typescript_lib.generate_verification(
                symbol_table=verified_ir_table,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            test_rel_path / "common.ts",
            lambda: typescript_tests.generate_common(spec_impls=context.spec_impls),
        ),
        (
            test_rel_path / "common.base64.spec.ts",
            lambda: (
                typescript_tests.generate_common_base64_spec(),
                None,
            ),
        ),
        (
            test_rel_path / "common.base64url.spec.ts",
            lambda: (
                typescript_tests.generate_common_base64url_spec(),
                None,
            ),
        ),
        (
            test_rel_path / "commonJsonization.ts",
            lambda: (
                typescript_tests.generate_common_jsonization(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "commonXmlization.ts",
            lambda: (
                typescript_tests.generate_common_xmlization(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "jsonization.concreteClasses.spec.ts",
            lambda: (
                typescript_tests.generate_jsonization_concrete_classes_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "jsonization.common.spec.ts",
            lambda: (
                typescript_tests.generate_jsonization_common_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "jsonization.enums.spec.ts",
            lambda: (
                typescript_tests.generate_jsonization_enums_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "jsonization.interfaces.spec.ts",
            lambda: (
                typescript_tests.generate_jsonization_interfaces_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "jsonization.negative.spec.ts",
            lambda: (
                typescript_tests.generate_jsonization_negative_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "stringification.enums.spec.ts",
            lambda: (
                typescript_tests.generate_stringification_enums_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "verification.spec.ts",
            lambda: (
                typescript_tests.generate_verification_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "xmlization.concreteClasses.spec.ts",
            lambda: (
                typescript_tests.generate_xmlization_concrete_classes_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "xmlization.basic.spec.ts",
            lambda: (
                typescript_tests.generate_xmlization_basic_spec(),
                None,
            ),
        ),
        (
            test_rel_path / "xmlization.common.spec.ts",
            lambda: (
                typescript_tests.generate_xmlization_common_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "xmlization.enums.spec.ts",
            lambda: (
                typescript_tests.generate_xmlization_enums_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "xmlization.interfaces.spec.ts",
            lambda: (
                typescript_tests.generate_xmlization_interfaces_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "xmlization.negative.spec.ts",
            lambda: (
                typescript_tests.generate_xmlization_negative_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "types.casts.spec.ts",
            lambda: (
                typescript_tests.generate_types_casts_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "types.descendAndPassThroughVisitor.spec.ts",
            lambda: (
                typescript_tests.generate_types_descend_and_pass_through_visitor_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "types.descendOnce.spec.ts",
            lambda: (
                typescript_tests.generate_types_descend_once_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "types.modelType.spec.ts",
            lambda: (
                typescript_tests.generate_types_model_type_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "types.overEnum.spec.ts",
            lambda: (
                typescript_tests.generate_types_over_enum_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "types.overXOrEmpty.spec.ts",
            lambda: (
                typescript_tests.generate_types_over_x_or_empty_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "types.typeMatches.spec.ts",
            lambda: (
                typescript_tests.generate_types_type_matches_spec(
                    symbol_table=verified_ir_table,
                ),
                None,
            ),
        ),
        (
            test_rel_path / "types.xOrDefault.spec.ts",
            lambda: (
                typescript_tests.generate_types_x_or_default_spec(
                    symbol_table=verified_ir_table,
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


assert typescript.__doc__ == __doc__
