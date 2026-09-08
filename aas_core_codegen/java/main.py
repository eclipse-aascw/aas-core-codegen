"""Generate Java code based on the meta-model."""

import pathlib
from typing import TextIO, Sequence, Tuple, Callable, Optional, List

from aas_core_codegen import specific_implementations, run, java, intermediate
from aas_core_codegen.common import Error
from aas_core_codegen.java import (
    common as java_common,
    lib as java_lib,
    tests as java_tests,
)


def execute(context: run.Context, stdout: TextIO, stderr: TextIO) -> int:
    """Generate the code."""

    verified_ir_table, errors = java_lib.verify_for_types(
        symbol_table=context.symbol_table
    )

    if errors is not None:
        run.write_error_report(
            message=f"Failed to verify the intermediate symbol table "
            f"for generation of Java code "
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

    package_key = specific_implementations.ImplementationKey("package.txt")
    package_text = context.spec_impls.get(package_key, None)
    if package_text is None:
        stderr.write(f"The package snippet is missing: {package_key}\n")
        return 1

    if not java_common.PACKAGE_IDENTIFIER_RE.fullmatch(package_text):
        stderr.write(
            f"The text from the snippet {package_key} "
            f"is not a valid package identifier: {package_text!r}\n"
        )
        return 1

    package = java_common.PackageIdentifier(package_text)

    verify_errors = java_lib.verify_for_verification(
        spec_impls=context.spec_impls,
        verification_functions=verified_ir_table.verification_functions,
    )

    if verify_errors is not None:
        run.write_error_report(
            message="Failed to verify the verification functions for code generation",
            errors=verify_errors,
            stderr=stderr,
        )
        return 1

    project_rel_path = pathlib.Path("src") / "main" / "java" / package.replace(".", "/")
    assert not project_rel_path.is_absolute()

    tests_rel_path = pathlib.Path("src") / "test" / "java"
    assert not tests_rel_path.is_absolute()

    rel_paths_generators: Sequence[
        Tuple[
            pathlib.Path,
            Callable[
                [], Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]
            ],
        ]
    ] = [
        (
            project_rel_path / "common",
            lambda: (java_lib.generate_common(package=package), None),
        ),
        (
            project_rel_path / "constants",
            lambda: java_lib.generate_constants(
                symbol_table=context.symbol_table, package=package
            ),
        ),
        (
            project_rel_path / "copying",
            lambda: java_lib.generate_copying(
                symbol_table=context.symbol_table,
                package=package,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            project_rel_path / "enhancing",
            lambda: java_lib.generate_enhancing(
                symbol_table=context.symbol_table,
                package=package,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            project_rel_path / "generation",
            lambda: java_lib.generate_generation(
                symbol_table=context.symbol_table,
                package=package,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            project_rel_path / "jsonization",
            lambda: java_lib.generate_jsonization(
                symbol_table=context.symbol_table,
                package=package,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            project_rel_path / "reporting",
            lambda: (java_lib.generate_reporting(package=package), None),
        ),
        (
            project_rel_path / "stringification",
            lambda: java_lib.generate_stringification(
                symbol_table=context.symbol_table, package=package
            ),
        ),
        (
            project_rel_path / "types",
            lambda: java_lib.generate_types(
                symbol_table=verified_ir_table,
                package=package,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            project_rel_path / "verification",
            lambda: java_lib.generate_verification(
                symbol_table=verified_ir_table,
                package=package,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            project_rel_path / "visitation",
            lambda: java_lib.generate_visitation(
                symbol_table=context.symbol_table, package=package
            ),
        ),
        (
            project_rel_path / "xmlization",
            lambda: java_lib.generate_xmlization(
                symbol_table=context.symbol_table,
                package=package,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            tests_rel_path,
            lambda: (java_tests.generate_common(package=package), None),
        ),
        (
            tests_rel_path,
            lambda: (java_tests.generate_common_json(package=package), None),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_common_jsonization(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_copying(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_descend_and_visitor_through(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_descend_once(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_enhancing(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_jsonization_of_concrete_classes(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_jsonization_of_enums(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_jsonization_of_interfaces(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_over_x_or_empty(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_verification_of_enums(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_x_or_default(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_xmlization_of_concrete_classes(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
        (
            tests_rel_path,
            lambda: (
                java_tests.generate_test_xmlization_of_interfaces(
                    package=package, symbol_table=context.symbol_table
                ),
                None,
            ),
        ),
    ]

    for rel_path, generator_func in rel_paths_generators:
        assert not rel_path.is_absolute()

        java_files, errors = generator_func()

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

        assert java_files is not None

        for java_file in java_files:
            pth = context.output_dir / rel_path / java_file.name

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
                pth.write_text(java_file.content, encoding="utf-8")
            except Exception as exception:
                run.write_error_report(
                    message=f"Failed to write to {pth}",
                    errors=[str(exception)],
                    stderr=stderr,
                )
                return 1

    stdout.write(f"Code generated to: {context.output_dir}\n")
    return 0


assert java.__doc__ == __doc__
