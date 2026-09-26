"""Generate Python code based on the meta-model."""

import pathlib
from typing import TextIO, Sequence, Callable, Tuple, Optional, List

from aas_core_codegen import specific_implementations, run, intermediate, python
from aas_core_codegen.common import Error
from aas_core_codegen.python import (
    common as python_common,
    lib as python_lib,
    tests as python_tests,
)


def execute(context: run.Context, stdout: TextIO, stderr: TextIO) -> int:
    """Generate code."""
    verified_ir_table, errors = python_lib.verify_for_types(
        symbol_table=context.symbol_table
    )

    if errors is not None:
        run.write_error_report(
            message=f"Failed to verify the intermediate symbol table "
            f"for generation of Python code "
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

    qualified_module_name_key = specific_implementations.ImplementationKey(
        "qualified_module_name.txt"
    )

    qualified_module_name_text = context.spec_impls.get(qualified_module_name_key, None)
    if qualified_module_name_text is None:
        stderr.write(
            f"The snippet with the qualified module name is missing: "
            f"{qualified_module_name_key}\n"
        )
        return 1

    if not python_common.QUALIFIED_MODULE_NAME_RE.fullmatch(qualified_module_name_text):
        stderr.write(
            f"The text from the snippet {qualified_module_name_key} "
            f"is not a valid qualified module name: {qualified_module_name_text!r}\n"
        )
        return 1

    qualified_module_name = python_common.QualifiedModuleName(
        qualified_module_name_text
    )

    verify_errors = python_lib.verify_for_verification(
        spec_impls=context.spec_impls,
        verification_functions=verified_ir_table.verification_functions,
    )

    if verify_errors is not None:
        run.write_error_report(
            message=("Failed to verify the verification functions for code generation"),
            errors=verify_errors,
            stderr=stderr,
        )
        return 1

    module_rel_path = pathlib.Path(qualified_module_name.replace(".", "/"))
    assert not module_rel_path.is_absolute()

    tests_rel_path = pathlib.Path("dev/tests")

    rel_paths_generators: Sequence[
        Tuple[pathlib.Path, Callable[[], Tuple[Optional[str], Optional[List[Error]]]]]
    ] = [
        (
            module_rel_path / "common.py",
            lambda: (python_lib.generate_common(context.symbol_table), None),
        ),
        (
            module_rel_path / "constants.py",
            lambda: python_lib.generate_constants(
                symbol_table=context.symbol_table,
                qualified_module_name=qualified_module_name,
            ),
        ),
        (
            module_rel_path / "jsonization.py",
            lambda: python_lib.generate_jsonization(
                symbol_table=context.symbol_table,
                qualified_module_name=qualified_module_name,
            ),
        ),
        (
            module_rel_path / "reporting.py",
            lambda: (
                python_lib.generate_reporting(
                    qualified_module_name=qualified_module_name
                ),
                None,
            ),
        ),
        (
            module_rel_path / "stringification.py",
            lambda: python_lib.generate_stringification(
                symbol_table=context.symbol_table,
                qualified_module_name=qualified_module_name,
            ),
        ),
        (
            module_rel_path / "types.py",
            lambda: python_lib.generate_types(
                symbol_table=verified_ir_table,
                qualified_module_name=qualified_module_name,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            module_rel_path / "verification.py",
            lambda: python_lib.generate_verification(
                symbol_table=verified_ir_table,
                qualified_module_name=qualified_module_name,
                spec_impls=context.spec_impls,
            ),
        ),
        (
            module_rel_path / "xmlcommon.py",
            lambda: (
                python_lib.generate_xml_common(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            module_rel_path / "xmlization.py",
            lambda: python_lib.generate_xmlization(
                symbol_table=context.symbol_table,
                qualified_module_name=qualified_module_name,
            ),
        ),
        (
            tests_rel_path / "common.py",
            lambda: (
                python_tests.generate_common(
                    qualified_module_name=qualified_module_name
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "common_jsonization.py",
            lambda: (
                python_tests.generate_common_jsonization(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "common_xmlization.py",
            lambda: (
                python_tests.generate_common_xmlization(
                    qualified_module_name=qualified_module_name
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_descend_and_pass_through_visitor.py",
            lambda: (
                python_tests.generate_test_descend_and_pass_through_visitor(
                    qualified_module_name=qualified_module_name
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_descend_once.py",
            lambda: (
                python_tests.generate_test_descend_once(
                    qualified_module_name=qualified_module_name
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_for_over_X_or_empty.py",
            lambda: (
                python_tests.generate_test_for_over_x_or_empty(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_for_x_or_default.py",
            lambda: (
                python_tests.generate_test_for_x_or_default(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_jsonization_of_classes_with_descendants.py",
            lambda: (
                python_tests.generate_test_jsonization_of_classes_with_descendants(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_jsonization_of_concrete_classes.py",
            lambda: (
                python_tests.generate_test_jsonization_of_concrete_classes(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_jsonization_of_enums.py",
            lambda: (
                python_tests.generate_test_jsonization_of_enums(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_verification.py",
            lambda: (
                python_tests.generate_test_verification(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_xmlization_of_classes_with_descendants.py",
            lambda: (
                python_tests.generate_test_xmlization_of_classes_with_descendants(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
        (
            tests_rel_path / "test_xmlization_of_concrete_classes.py",
            lambda: (
                python_tests.generate_test_xmlization_of_concrete_classes(
                    symbol_table=context.symbol_table,
                    qualified_module_name=qualified_module_name,
                ),
                None,
            ),
        ),
    ]

    # NOTE (mristin):
    # ``jsonvalueverification.py``, ``xmlrpc.py`` and the unit tests which
    # exercise the two in isolation are only needed when the meta-model actually
    # uses a JSON-able type (``JSONValue``, ``JSONArray`` or ``JSONObject[K]``)
    # -- unlike the other modules above, which are always generated regardless
    # of the model.
    if intermediate.uses_json_types(context.symbol_table):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                module_rel_path / "jsonvalueverification.py",
                lambda: (
                    python_lib.generate_json_value_verification(
                        qualified_module_name=qualified_module_name
                    ),
                    None,
                ),
            ),
            (
                module_rel_path / "xmlrpc.py",
                lambda: (
                    python_lib.generate_xml_rpc(
                        qualified_module_name=qualified_module_name
                    ),
                    None,
                ),
            ),
            (
                tests_rel_path / "test_json_value_verification.py",
                lambda: (
                    python_tests.generate_test_json_value_verification(
                        qualified_module_name=qualified_module_name
                    ),
                    None,
                ),
            ),
            (
                tests_rel_path / "test_xml_rpc.py",
                lambda: (
                    python_tests.generate_test_xml_rpc(
                        qualified_module_name=qualified_module_name
                    ),
                    None,
                ),
            ),
        ]

    # NOTE (mristin):
    # The tests of slicing strings and ``find`` are only relevant for
    # a meta-model which uses them.
    if intermediate.uses_string_slicing_or_find(context.symbol_table):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                tests_rel_path / "test_slicing_and_find.py",
                lambda: (python_tests.generate_test_slicing_and_find(), None),
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

        # NOTE (mristin):
        # We add this type check since we had many problems during the development.
        assert isinstance(
            code, str
        ), f"Unexpected code {code} for the generator for {rel_path}"

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


assert python.__doc__ == __doc__
