# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate C++ code based on the meta-model."""

import pathlib
from typing import TextIO, Sequence, Tuple, Callable, Optional, List

from aas_core_codegen import run, intermediate, specific_implementations, cpp
from aas_core_codegen.common import Stripped, Error
from aas_core_codegen.cpp import (
    common as cpp_common,
    lib as cpp_lib,
    tests as cpp_tests,
)
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
)


def execute(context: run.Context, stdout: TextIO, stderr: TextIO) -> int:
    """Generate code."""
    verified_ir_table, errors = cpp_lib.verify_for_types(
        symbol_table=context.symbol_table
    )

    if errors is not None:
        run.write_error_report(
            message=f"Failed to verify the intermediate symbol table "
            f"for generation of C++ code "
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

    # region Namespace

    namespace_key = specific_implementations.ImplementationKey("namespace.txt")
    namespace_text = context.spec_impls.get(namespace_key, None)
    if namespace_text is None:
        stderr.write(f"The namespace snippet is missing: {namespace_key}\n")
        return 1

    library_namespace = Stripped(namespace_text.strip())

    # endregion

    try:
        context.output_dir.mkdir(exist_ok=True, parents=True)
    except Exception as exception:
        stderr.write(
            f"Failed to create the output directory {context.output_dir}: {exception}"
        )
        return 1

    src_dir = pathlib.Path("src")
    assert not src_dir.is_absolute()

    include_dir = pathlib.Path("include") / library_namespace.replace("::", "/")
    assert not include_dir.is_absolute()

    test_dir = pathlib.Path("test")
    assert not test_dir.is_absolute()

    rel_paths_generators: Sequence[
        Tuple[pathlib.Path, Callable[[], Tuple[Optional[str], Optional[List[Error]]]]]
    ] = [
        (
            include_dir / "common.hpp",
            lambda: (
                cpp_lib.generate_common_header(
                    symbol_table=context.symbol_table,
                    type_inference=type_inference,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            src_dir / "common.cpp",
            lambda: (
                cpp_lib.generate_common_implementation(
                    symbol_table=context.symbol_table,
                    type_inference=type_inference,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            include_dir / "constants.hpp",
            lambda: cpp_lib.generate_constants_header(
                symbol_table=context.symbol_table, library_namespace=library_namespace
            ),
        ),
        (
            src_dir / "constants.cpp",
            lambda: cpp_lib.generate_constants_implementation(
                symbol_table=context.symbol_table, library_namespace=library_namespace
            ),
        ),
        (
            include_dir / "enhancing.hpp",
            lambda: cpp_lib.generate_enhancing_header(
                symbol_table=context.symbol_table, library_namespace=library_namespace
            ),
        ),
        (
            include_dir / "iteration.hpp",
            lambda: cpp_lib.generate_iteration_header(
                symbol_table=context.symbol_table, library_namespace=library_namespace
            ),
        ),
        (
            src_dir / "iteration.cpp",
            lambda: cpp_lib.generate_iteration_implementation(
                symbol_table=context.symbol_table, library_namespace=library_namespace
            ),
        ),
        (
            include_dir / "jsonization.hpp",
            lambda: (
                cpp_lib.generate_jsonization_header(
                    symbol_table=verified_ir_table, library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            src_dir / "jsonization.cpp",
            lambda: (
                cpp_lib.generate_jsonization_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            include_dir / "pattern.hpp",
            lambda: (
                cpp_lib.generate_pattern_header(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            src_dir / "pattern.cpp",
            lambda: cpp_lib.generate_pattern_implementation(
                symbol_table=context.symbol_table,
                library_namespace=library_namespace,
            ),
        ),
        (
            include_dir / "revm.hpp",
            lambda: (
                cpp_lib.generate_revm_header(library_namespace=library_namespace),
                None,
            ),
        ),
        (
            src_dir / "revm.cpp",
            lambda: (
                cpp_lib.generate_revm_implementation(
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            include_dir / "stringification.hpp",
            lambda: (
                cpp_lib.generate_stringification_header(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            src_dir / "stringification.cpp",
            lambda: (
                cpp_lib.generate_stringification_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            include_dir / "types.hpp",
            lambda: cpp_lib.generate_types_header(
                symbol_table=verified_ir_table,
                library_namespace=library_namespace,
            ),
        ),
        (
            src_dir / "types.cpp",
            lambda: cpp_lib.generate_types_implementation(
                symbol_table=context.symbol_table,
                type_inference=type_inference,
                spec_impls=context.spec_impls,
                library_namespace=library_namespace,
            ),
        ),
        (
            include_dir / "verification.hpp",
            lambda: cpp_lib.generate_verification_header(
                symbol_table=verified_ir_table,
                type_inference=type_inference,
                spec_impls=context.spec_impls,
                library_namespace=library_namespace,
            ),
        ),
        (
            src_dir / "verification.cpp",
            lambda: cpp_lib.generate_verification_implementation(
                symbol_table=context.symbol_table,
                type_inference=type_inference,
                spec_impls=context.spec_impls,
                library_namespace=library_namespace,
            ),
        ),
        (
            include_dir / "visitation.hpp",
            lambda: (
                cpp_lib.generate_visitation_header(
                    symbol_table=verified_ir_table, library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            src_dir / "visitation.cpp",
            lambda: (
                cpp_lib.generate_visitation_implementation(
                    symbol_table=verified_ir_table, library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            include_dir / "wstringification.hpp",
            lambda: (
                cpp_lib.generate_wstringification_header(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            src_dir / "wstringification.cpp",
            lambda: (
                cpp_lib.generate_wstringification_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            include_dir / "xml_path.hpp",
            lambda: (
                cpp_lib.generate_xml_path_header(library_namespace=library_namespace),
                None,
            ),
        ),
        (
            src_dir / "xml_path.cpp",
            lambda: (
                cpp_lib.generate_xml_path_implementation(
                    library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            src_dir / "xml_common.hpp",
            lambda: (
                cpp_lib.generate_xml_common_header(
                    symbol_table=verified_ir_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            src_dir / "xml_common.cpp",
            lambda: (
                cpp_lib.generate_xml_common_implementation(
                    symbol_table=verified_ir_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            include_dir / "xmlization.hpp",
            lambda: (
                cpp_lib.generate_xmlization_header(
                    symbol_table=verified_ir_table, library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            src_dir / "xmlization.cpp",
            lambda: (
                cpp_lib.generate_xmlization_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "catch_main.cpp",
            lambda: (
                f"""\
{cpp_common.WARNING}

/**
 * Define the main function of Catch2 for all the tests.
 *
 * Compiling the implementation of Catch2 takes long, so we compile it only once
 * in this translation unit, and link all the tests against it.
 */

#define CATCH_CONFIG_MAIN
#include <catch2/catch.hpp>
""",
                None,
            ),
        ),
        (
            test_dir / "common.hpp",
            lambda: (
                cpp_tests.generate_common_header(library_namespace=library_namespace),
                None,
            ),
        ),
        (
            test_dir / "common.cpp",
            lambda: (
                cpp_tests.generate_common_implementation(
                    library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            test_dir / "common_examples.hpp",
            lambda: (
                cpp_tests.generate_common_examples_header(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "common_examples.cpp",
            lambda: (
                cpp_tests.generate_common_examples_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "common_jsonization.hpp",
            lambda: (
                cpp_tests.generate_common_jsonization_header(
                    library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            test_dir / "common_jsonization.cpp",
            lambda: (
                cpp_tests.generate_common_jsonization_implementation(
                    library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            test_dir / "common_xmlization.hpp",
            lambda: (
                cpp_tests.generate_common_xmlization_header(
                    library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            test_dir / "common_xmlization.cpp",
            lambda: (
                cpp_tests.generate_common_xmlization_implementation(
                    library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            test_dir / "test_descent_and_descent_once.cpp",
            lambda: (
                cpp_tests.generate_test_descent_and_descent_once_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_jsonization_dispatch.cpp",
            lambda: (
                cpp_tests.generate_test_jsonization_dispatch_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_jsonization_of_concrete_classes.cpp",
            lambda: (
                cpp_tests.generate_test_jsonization_of_concrete_classes_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_revm.cpp",
            lambda: (
                cpp_tests.generate_test_revm_implementation(
                    library_namespace=library_namespace
                ),
                None,
            ),
        ),
        (
            test_dir / "test_stringification_base64.cpp",
            lambda: (
                cpp_tests.generate_test_stringification_base64_implementation(
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_stringification_of_enums.cpp",
            lambda: (
                cpp_tests.generate_test_stringification_of_enums_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_verification.cpp",
            lambda: (
                cpp_tests.generate_test_verification_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_wstringification_of_enums.cpp",
            lambda: (
                cpp_tests.generate_test_wstringification_of_enums_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_xmlization_dispatch.cpp",
            lambda: (
                cpp_tests.generate_test_xmlization_dispatch_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_xmlization_of_concrete_classes.cpp",
            lambda: (
                cpp_tests.generate_test_xmlization_of_concrete_classes_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
        (
            test_dir / "test_x_or_default.cpp",
            lambda: (
                cpp_tests.generate_test_x_or_default_implementation(
                    symbol_table=context.symbol_table,
                    library_namespace=library_namespace,
                ),
                None,
            ),
        ),
    ]

    # NOTE (mristin):
    # ``xml_rpc`` and ``json_value_verification`` are only needed when the
    # meta-model actually uses a JSON-able type (``JSONValue``, ``JSONArray``
    # or ``JSONObject[K]``) -- unlike the other library modules above, which
    # are always generated regardless of the model.
    if intermediate_uses.json_types(context.symbol_table):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                src_dir / "xml_rpc.hpp",
                lambda: (
                    cpp_lib.generate_xml_rpc_header(
                        library_namespace=library_namespace
                    ),
                    None,
                ),
            ),
            (
                src_dir / "xml_rpc.cpp",
                lambda: (
                    cpp_lib.generate_xml_rpc_implementation(
                        library_namespace=library_namespace
                    ),
                    None,
                ),
            ),
            (
                src_dir / "json_value_verification.hpp",
                lambda: (
                    cpp_lib.generate_json_value_verification_header(
                        library_namespace=library_namespace
                    ),
                    None,
                ),
            ),
            (
                src_dir / "json_value_verification.cpp",
                lambda: (
                    cpp_lib.generate_json_value_verification_implementation(
                        library_namespace=library_namespace
                    ),
                    None,
                ),
            ),
            (
                test_dir / "test_xml_rpc.cpp",
                lambda: (
                    cpp_tests.generate_test_xml_rpc_implementation(
                        library_namespace=library_namespace
                    ),
                    None,
                ),
            ),
            (
                test_dir / "test_json_value_verification.cpp",
                lambda: (
                    cpp_tests.generate_test_json_value_verification_implementation(
                        library_namespace=library_namespace
                    ),
                    None,
                ),
            ),
        ]

    # NOTE (mristin):
    # The helpers for the operations on strings are only generated for
    # a meta-model which uses them, and so are their tests.
    if intermediate_uses.string_operations(type_inference):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                test_dir / "test_string_helpers.cpp",
                lambda: (
                    cpp_tests.generate_test_string_helpers_implementation(
                        library_namespace=library_namespace,
                        type_inference=type_inference,
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
                test_dir / "test_arithmetic.cpp",
                lambda: (
                    cpp_tests.generate_test_arithmetic_implementation(
                        symbol_table=context.symbol_table,
                        library_namespace=library_namespace,
                    ),
                    None,
                ),
            ),
        ]

    # NOTE (mristin):
    # We test ``int`` only if the meta-model uses it, as we generate the helper
    # function only in that case.
    if intermediate_uses.int_call(context.symbol_table):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                test_dir / "test_parse_int.cpp",
                lambda: (
                    cpp_tests.generate_test_parse_int_implementation(
                        symbol_table=context.symbol_table,
                        library_namespace=library_namespace,
                    ),
                    None,
                ),
            ),
        ]

    # NOTE (mristin):
    # Unlike the other targets, C++ copies the vectors by value, so we execute
    # the assignments to the properties and to the list items in the unit tests to
    # make sure that the transpiled code references and copies the vectors as
    # Python shares them. We generate these tests only for the meta-model which
    # defines the corresponding verification functions,
    # see :py:mod:`aas_core_codegen.cpp.tests._generate_test_assignment_targets`.
    if cpp_tests.defines_assignment_target_verifications(context.symbol_table):
        rel_paths_generators = list(rel_paths_generators) + [
            (
                test_dir / "test_assignment_targets.cpp",
                lambda: (
                    cpp_tests.generate_test_assignment_targets_implementation(
                        symbol_table=context.symbol_table,
                        library_namespace=library_namespace,
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


assert cpp.__doc__ == __doc__
